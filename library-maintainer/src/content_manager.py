"""
Content management for ApocaCache library maintainer.
Handles downloading, verifying, and managing ZIM files.
"""

import asyncio
import os
import time
import json
from datetime import datetime
import re
from typing import Dict, List, Optional, Tuple
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
import structlog
import traceback
from dataclasses import dataclass
from urllib.parse import urljoin
import aiofiles.os
import tempfile

from config import Config, ContentItem
import monitoring

log = structlog.get_logger()

@dataclass
class ContentFile:
    """Represents a content file found on the Kiwix server."""
    name: str
    path: str
    url: str
    size: int
    date: str

class ApacheDirectoryParser:
    """Parser for Apache's default directory listing format."""
    
    def __init__(self):
        self.date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')
        self.size_pattern = re.compile(r'(\d+\.?\d*[KMGT]?)')
        self.cache = {}  # Cache parsed directory listings
        self.cache_ttl = 300  # Cache TTL in seconds
    
    def _get_cached(self, url: str) -> Optional[List[Tuple[str, str, str]]]:
        """Get cached directory listing if still valid."""
        if url in self.cache:
            timestamp, entries = self.cache[url]
            if time.time() - timestamp < self.cache_ttl:
                return entries
            del self.cache[url]
        return None
    
    def _cache_result(self, url: str, entries: List[Tuple[str, str, str]]):
        """Cache directory listing results."""
        self.cache[url] = (time.time(), entries)
    
    def parse_directory_listing(self, content: str, url: str) -> List[Tuple[str, str, str]]:
        """
        Parse Apache directory listing HTML.
        
        Args:
            content: HTML content of directory listing
            url: URL of the directory (for caching)
            
        Returns:
            List of tuples (href, date_str, size_str)
        """
        # Check cache first
        cached = self._get_cached(url)
        if cached is not None:
            return cached
            
        soup = BeautifulSoup(content, 'html.parser')
        entries = []
        
        # Find the pre element containing the directory listing
        pre = soup.find('pre')
        if not pre:
            return []
            
        lines = pre.get_text().split('\n')
        current_link = None
        
        for link in pre.find_all('a'):
            href = link.get('href')
            if not href or href == "../" or href.startswith("?C="):
                continue
                
            # Find the line containing this link
            link_line = None
            for line in lines:
                if href in line:
                    link_line = line.strip()
                    break
                    
            if not link_line:
                continue
                
            # Parse date and size
            parts = link_line.split()
            date_str = None
            size_str = "-"
            
            for i, part in enumerate(parts):
                if self.date_pattern.match(part):
                    if i + 1 < len(parts):
                        date_str = f"{part} {parts[i+1]}"
                        if i + 2 < len(parts):
                            size_str = parts[i+2]
                    break
            
            if date_str:
                entries.append((href, date_str, size_str))
        
        # Cache the results
        self._cache_result(url, entries)
        return entries

class ContentManager:
    """Manages ZIM file content downloads and updates."""
    
    def __init__(self, config: Config):
        """Initialize the content manager."""
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.download_semaphore = asyncio.Semaphore(
            config.options.max_concurrent_downloads
        )
        self.content_state: Dict[str, Dict] = {}
        self.directory_parser = ApacheDirectoryParser()
        self._load_state()
        
        # Log initial configuration
        log.info("content_manager.initialized",
                base_url=self.base_url,
                language_filter=self.config.language_filter,
                content_pattern=self.config.content_pattern,
                scan_subdirs=self.config.scan_subdirs,
                download_all=self.config.download_all)
    
    def _parse_size(self, size_str: str) -> int:
        """Parse a human-readable size string into bytes."""
        if not size_str or size_str == '-':
            return 0
            
        # Remove any whitespace
        size_str = size_str.strip()
        
        # Parse size with units
        units = {
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }
        
        try:
            if size_str[-1] in units:
                number = float(size_str[:-1])
                return int(number * units[size_str[-1]])
            return int(size_str)
        except (ValueError, IndexError):
            log.warning("size_parse.failed", size_str=size_str)
            return 0
    
    def _load_state(self):
        """Load content state from state file."""
        state_file = os.path.join(self.config.data_dir, "content_state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    self.content_state = json.loads(f.read())
                log.info("content_state.loaded", items=len(self.content_state))
            except Exception as e:
                log.error("content_state.load_failed", error=str(e))
    
    async def _save_state(self):
        """Save content state to state file."""
        state_file = os.path.join(self.config.data_dir, "content_state.json")
        try:
            async with aiofiles.open(state_file, 'w') as f:
                await f.write(json.dumps(self.content_state, indent=2))
            log.info("content_state.saved", items=len(self.content_state))
        except Exception as e:
            log.error("content_state.save_failed", error=str(e))
    
    def _matches_content_pattern(self, filename: str) -> bool:
        """Check if filename matches content pattern."""
        if not self.config.content_pattern:
            return True
            
        patterns = self.config.content_pattern.split('|')
        
        for pattern in patterns:
            try:
                if re.search(pattern, filename):
                    return True
            except re.error as e:
                log.error("content_pattern.invalid", 
                         pattern=pattern,
                         error=str(e))
                continue
                
        return False
    
    def _matches_language_filter(self, filename: str) -> bool:
        """Check if filename matches language filter."""
        if not self.config.language_filter:
            return True
            
        for lang in self.config.language_filter:
            if not lang:  # Skip empty language codes
                continue
                
            # Match language codes in Kiwix format
            # Example: wikipedia_en_all_maxi_2024-05.zim
            patterns = [
                f"_{lang}_all_",  # Standard Kiwix format
                f"_{lang}_",      # Simple language code
                f".{lang}.",      # Language in extension
                f"_{lang}."       # Language at end
            ]
            
            for pattern in patterns:
                if pattern in filename:
                    return True
                    
        return False
    
    async def _get_available_content(self) -> List[ContentFile]:
        """Get list of available content from server."""
        
        async def scan_directory(url: str, path: str = "", depth: int = 0, visited: set = None) -> List[ContentFile]:
            """
            Scan a directory for content files.
            
            Args:
                url: The base URL to scan
                path: The relative path within the base URL
                depth: Current recursion depth
                visited: Set of visited URLs to prevent loops
                
            Returns:
                List of ContentFile objects found in the directory
            """
            # Initialize visited set on first call
            if visited is None:
                visited = set()
                
            # Skip if we've already visited this URL
            if url in visited:
                log.debug("directory.already_visited", url=url)
                return []
            visited.add(url)
                
            log.debug("directory.http_session.creating")
            timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout for directory listing
            async with aiohttp.ClientSession(timeout=timeout) as session:
                log.debug("directory.http_request.start", url=url)
                try:
                    async with session.get(url, timeout=timeout) as response:
                        if response.status != 200:
                            log.error("directory.http_request.failed", status=response.status)
                            return []

                        content = await response.text()
                        entries = self.directory_parser.parse_directory_listing(content, url)
                        content_files = []

                        for href, date_str, size_str in entries:
                            filename = href.rstrip('/')
                            full_path = os.path.join(path, filename) if path else filename

                            # Check if this is a directory
                            is_dir = href.endswith('/')
                            
                            if is_dir and self.config.scan_subdirs:
                                # Skip excluded directories
                                if filename in self.config.excluded_dirs:
                                    continue
                                    
                                # Recursively scan subdirectory
                                subdir_url = urljoin(url + '/', href)
                                try:
                                    subdir_files = await scan_directory(
                                        subdir_url, 
                                        full_path,
                                        depth + 1,
                                        visited
                                    )
                                    content_files.extend(subdir_files)
                                except Exception as e:
                                    log.error("directory.subdir.scan_failed",
                                            error=str(e),
                                            traceback=traceback.format_exc())
                                continue

                            # Check filters
                            matches_pattern = self._matches_content_pattern(filename)
                            matches_language = self._matches_language_filter(filename)
                            
                            if not (matches_pattern and matches_language):
                                continue

                            # Parse size
                            size = self._parse_size(size_str)

                            content_file = ContentFile(
                                name=filename,
                                path=full_path,
                                url=urljoin(url + '/', href),
                                size=size,
                                date=date_str
                            )
                            content_files.append(content_file)

                        total_files = len(entries)
                        matched_files = len(content_files)
                        log.info("directory.scan_summary",
                                directory=path or "root",
                                total_files=total_files,
                                matched_files=matched_files)
                        return content_files
                        
                except aiohttp.ClientError as e:
                    log.error("directory.http_request.failed",
                            error=str(e),
                            url=url)
                    return []
        
        try:
            log.info("content_list.scan.starting", base_url=self.base_url)
            content_list = await scan_directory(self.base_url, depth=0)
            log.info("content_list.scan.complete", 
                    count=len(content_list), 
                    items=[item.name for item in content_list])
            return content_list
        except Exception as e:
            log.error("content_list.scan.failed",
                     error=str(e),
                     traceback=traceback.format_exc())
            raise
    
    async def _download_file(self, url: str, dest_path: str, content: ContentItem) -> bool:
        """
        Download a file with progress tracking, verification and retries.
        
        Args:
            url: The URL to download from (can be relative or absolute)
            dest_path: The destination path to save the file
            content: The content item being downloaded
            
        Returns:
            bool: True if download was successful, False otherwise
        """
        temp_path = f"{dest_path}.tmp"
        max_retries = self.config.options.retry_attempts
        retry_count = 0
        
        async with self.download_semaphore:
            while retry_count <= max_retries:
                try:
                    # Ensure URL is absolute
                    download_url = url if url.startswith('http') else urljoin(self.base_url, url)
                    log.info("download.starting", 
                            content=content.name,
                            url=download_url,
                            dest=dest_path,
                            attempt=retry_count + 1,
                            max_attempts=max_retries + 1)
                    
                    # Configure timeouts for large downloads
                    timeout = aiohttp.ClientTimeout(
                        total=None,  # No total timeout
                        connect=120,  # 2 minutes to establish connection
                        sock_read=600,  # 10 minutes to read data chunks
                        sock_connect=60  # 1 minute for socket connection
                    )
                    
                    connector = aiohttp.TCPConnector(
                        force_close=True,
                        enable_cleanup_closed=True,
                        limit=1  # Limit concurrent connections per session
                    )
                    
                    async with aiohttp.ClientSession(
                        timeout=timeout,
                        connector=connector,
                        raise_for_status=True
                    ) as session:
                        try:
                            async with session.get(download_url) as response:
                                if response.status != 200:
                                    raise Exception(f"Download failed: {response.status}")
                                
                                total_size = int(response.headers.get('content-length', 0))
                                if total_size == 0:
                                    log.warning("download.no_content_length",
                                              content=content.name,
                                              url=download_url)
                                
                                downloaded = 0
                                
                                # Create parent directory if it doesn't exist
                                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                                
                                async with aiofiles.open(temp_path, 'wb') as f:
                                    async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                                        await f.write(chunk)
                                        downloaded += len(chunk)
                                        monitoring.update_content_size(
                                            content.name,
                                            content.language,
                                            downloaded
                                        )
                                
                                # Log progress for large files
                                if total_size > 0 and downloaded % (10 * 1024 * 1024) == 0:  # Every 10MB
                                    progress = (downloaded / total_size) * 100
                                    log.debug("download.progress",
                                            content=content.name,
                                            progress=f"{progress:.1f}%",
                                            downloaded=downloaded,
                                            total=total_size)
                                
                                if self.config.options.verify_downloads:
                                    # Verify download size if we know the expected size
                                    if total_size > 0 and os.path.getsize(temp_path) != total_size:
                                        raise Exception(f"Download size mismatch: expected {total_size}, got {os.path.getsize(temp_path)}")
                                
                                # Create parent directory if it doesn't exist
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                
                                # Atomic rename
                                os.rename(temp_path, dest_path)
                                
                                log.info("download.complete",
                                        content=content.name,
                                        size=os.path.getsize(dest_path))
                                        
                                monitoring.record_download("success", content.language)
                                return True
                        except Exception as e:
                            error_details = {
                                'type': type(e).__name__,
                                'message': str(e),
                                'traceback': traceback.format_exc()
                            }
                            retry_count += 1
                            if retry_count <= max_retries:
                                log.warning("download.retry",
                                          content=content.name,
                                          error=error_details,
                                          attempt=retry_count,
                                          max_attempts=max_retries + 1)
                        # Clean up failed temp file before retry
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception as cleanup_error:
                                log.error("download.cleanup_failed",
                                        content=content.name,
                                        error=str(cleanup_error))
                        # Wait before retry with exponential backoff
                        await asyncio.sleep(2 ** retry_count)
                        continue
                    
                    # All retries exhausted
                    log.error("download.failed",
                             content=content.name,
                             error=str(e),
                             attempts=retry_count,
                             traceback=traceback.format_exc())
                    monitoring.record_download("failed", content.language)
                    
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception as cleanup_error:
                            log.error("download.cleanup_failed",
                                    content=content.name,
                                    error=str(cleanup_error))
                    return False
                except Exception as e:
                    error_details = {
                        'type': type(e).__name__,
                        'message': str(e),
                        'traceback': traceback.format_exc()
                    }
                    retry_count += 1
                    if retry_count <= max_retries:
                        log.warning("download.retry",
                                  content=content.name,
                                  error=error_details,
                                  attempt=retry_count,
                                  max_attempts=max_retries + 1)
                        # Clean up failed temp file before retry
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception as cleanup_error:
                                log.error("download.cleanup_failed",
                                        content=content.name,
                                        error=str(cleanup_error))
                        # Wait before retry with exponential backoff
                        await asyncio.sleep(2 ** retry_count)
                        continue
                    
                    # All retries exhausted
                    log.error("download.failed",
                             content=content.name,
                             error=str(e),
                             attempts=retry_count,
                             traceback=traceback.format_exc())
                    monitoring.record_download("failed", content.language)
                    
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception as cleanup_error:
                            log.error("download.cleanup_failed",
                                    content=content.name,
                                    error=str(cleanup_error))
                    return False
    
    async def update_content(self):
        """Update content based on configuration."""
        start_time = time.time()
        log.info("content_update.starting")
        
        try:
            available_content = await self._get_available_content()
            download_tasks = []
            
            log.info("content_update.download_list", 
                     content_items=[(item.name, item.language, item.category) 
                                  for item in self.config.content_list])
            
            for content_item in self.config.content_list:
                log.info("content_update.checking_item", 
                         content_name=content_item.name,
                         content_language=content_item.language,
                         content_category=content_item.category)
                
                latest_version = None
                latest_date = None
                
                # Pattern for matching content files
                # Handle various formats:
                # - wikipedia_en_all_maxi_2024-05.zim
                # - devdocs_en_angular_2025-01.zim
                # - freecodecamp_en_javascript_2024-10.zim
                pattern = f"{content_item.name}.*_\\d{{4}}-\\d{{2}}.zim$"
                log.debug("content_update.pattern", pattern=pattern)
                
                for content_file in available_content:
                    filename = os.path.basename(content_file.path)
                    if re.search(pattern, filename):
                        log.info("content_update.found_match",
                                content_name=content_item.name,
                                filename=filename,
                                date=content_file.date,
                                size=content_file.size)
                        
                        # Keep track of the latest version
                        if not latest_date or content_file.date > latest_date:
                            latest_version = content_file
                            latest_date = content_file.date
                
                if latest_version:
                    filename = os.path.basename(latest_version.path)
                    
                    # Create category subdirectory
                    category_dir = os.path.join(self.config.data_dir, content_item.category)
                    os.makedirs(category_dir, exist_ok=True)
                    
                    dest_path = os.path.join(
                        category_dir,
                        filename
                    )
                    
                    # Create state for this content
                    state = {
                        'last_updated': latest_version.date,
                        'size': latest_version.size,
                        'path': dest_path
                    }
                    
                    # Update state immediately
                    self.content_state[content_item.name] = state
                    
                    # Check if download/update needed
                    if self.config.should_download_content(content_item):
                        needs_download = not os.path.exists(dest_path)
                        
                        # Check both file size and date for updates
                        current_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                        size_mismatch = current_size != latest_version.size
                        
                        # Extract date from filename for comparison
                        date_match = re.search(r'_(\d{4}-\d{2}).zim$', os.path.basename(dest_path)) if os.path.exists(dest_path) else None
                        file_date = date_match.group(1) if date_match else None
                        latest_date = re.search(r'_(\d{4}-\d{2}).zim$', latest_version.path).group(1)
                        date_mismatch = file_date != latest_date if file_date else True
                        
                        needs_update = size_mismatch or date_mismatch
                        
                        log.info("content_update.download_check",
                                content_name=content_item.name,
                                needs_download=needs_download,
                                needs_update=needs_update,
                                current_size=current_size,
                                new_size=latest_version.size,
                                size_mismatch=size_mismatch,
                                current_date=file_date,
                                new_date=latest_date,
                                date_mismatch=date_mismatch)
                        
                        if needs_download or needs_update:
                            log.info("content_update.queueing_download",
                                    content_name=content_item.name,
                                    filename=filename,
                                    size=latest_version.size)
                            download_task = self._download_file(
                                latest_version.url,
                                dest_path,
                                content_item
                            )
                            download_tasks.append(download_task)
                else:
                    log.warning("content_update.no_match_found",
                              content_name=content_item.name,
                              pattern=pattern)
            
            if download_tasks:
                log.info("content_update.starting_downloads", count=len(download_tasks))
                results = await asyncio.gather(*download_tasks)
                log.info("content_update.downloads_complete", 
                         successful=sum(1 for r in results if r),
                         failed=sum(1 for r in results if not r))
            else:
                log.info("content_update.no_downloads_needed")
            
            # Always save state after updates
            await self._save_state()
            
            duration = time.time() - start_time
            monitoring.set_update_duration(duration)
            log.info("content_update.complete",
                     duration=duration,
                     downloads=len(download_tasks))
            
        except Exception as e:
            log.error("content_update.failed", error=str(e))
            monitoring.set_update_duration(0)
    
    async def cleanup(self):
        """Clean up temporary files and incomplete downloads."""
        if not self.config.options.cleanup_incomplete:
            return
            
        try:
            for filename in os.listdir(self.config.data_dir):
                if filename.endswith('.tmp'):
                    os.remove(os.path.join(self.config.data_dir, filename))
        except Exception as e:
            log.error("cleanup.failed", error=str(e)) 
