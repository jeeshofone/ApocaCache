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
import hashlib
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
import xml.etree.ElementTree as ET

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
    md5_url: str = ""
    mirrors: List[str] = None

    def __post_init__(self):
        if self.mirrors is None:
            self.mirrors = []

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
        self.library_xml_url = "https://download.kiwix.org/library/library_zim.xml"
        self.download_queue = asyncio.Queue()
        self.active_downloads = set()
        self._load_state()
        
        # Start download worker
        asyncio.create_task(self._download_worker())
        
        # Log initial configuration
        log.info("content_manager.initialized",
                base_url=self.base_url,
                language_filter=self.config.language_filter,
                download_all=self.config.download_all)
    
    def _parse_size(self, size_str: str) -> int:
        """Parse a human-readable size string into bytes."""
        if not size_str or size_str == '-':
            return 0
            
        # Remove any whitespace and handle 'M' suffix
        size_str = size_str.strip()
        
        # Parse size with units
        units = {
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }
        
        try:
            # Handle decimal numbers with units (e.g., "5.2M")
            match = re.match(r'^(\d+\.?\d*)([KMGT])?$', size_str)
            if match:
                number = float(match.group(1))
                unit = match.group(2)
                if unit and unit in units:
                    return int(number * units[unit])
                return int(number)
            
            # Try parsing as plain integer
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
    
    async def _fetch_library_xml(self) -> Optional[ET.Element]:
        """Fetch and parse the central library XML file."""
        try:
            # Check for cached local copy in shared data folder
            local_library_file = os.path.join(self.config.data_dir, "library_zim.xml")
            
            # Create data directory if it doesn't exist
            os.makedirs(self.config.data_dir, exist_ok=True)
            
            if os.path.exists(local_library_file):
                log.info("library_xml.using_local_cache", path=local_library_file)
                async with aiofiles.open(local_library_file, 'r') as f:
                    content = await f.read()
                return ET.fromstring(content)
            
            # If no local cache, fetch from remote
            log.info("library_xml.fetching", url=self.library_xml_url)
            async with aiohttp.ClientSession() as session:
                async with session.get(self.library_xml_url) as response:
                    if response.status != 200:
                        log.error("library_xml.fetch_failed", status=response.status)
                        return None
                    content = await response.text()
                    
                    # Cache the XML in shared data folder
                    try:
                        async with aiofiles.open(local_library_file, 'w') as f:
                            await f.write(content)
                        log.info("library_xml.cached", path=local_library_file)
                    except Exception as e:
                        log.error("library_xml.cache_failed", error=str(e), path=local_library_file)
                    
                    return ET.fromstring(content)
        except Exception as e:
            log.error("library_xml.fetch_failed", error=str(e))
            return None

    async def _fetch_meta4_file(self, url: str) -> Tuple[List[str], Optional[str]]:
        """
        Fetch and parse a meta4 file to get mirror URLs and MD5.
        
        Returns:
            Tuple of (mirror_urls, md5_hash)
        """
        try:
            log.info("meta4.fetching", url=url)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        log.error("meta4.fetch_failed", status=response.status)
                        return [], None
                    content = await response.text()
                    root = ET.fromstring(content)
                    
                    # Extract mirror URLs from meta4 file
                    mirrors = []
                    for url_elem in root.findall(".//{urn:ietf:params:xml:ns:metalink}url"):
                        mirror_url = url_elem.text
                        if mirror_url:
                            mirrors.append(mirror_url)
                    
                    # Extract MD5 hash
                    md5_hash = None
                    hash_elem = root.find(".//{urn:ietf:params:xml:ns:metalink}hash[@type='md5']")
                    if hash_elem is not None and hash_elem.text:
                        md5_hash = hash_elem.text
                    
                    log.info("meta4.parsed", mirrors=len(mirrors), md5=md5_hash)
                    return mirrors, md5_hash
        except Exception as e:
            log.error("meta4.fetch_failed", error=str(e))
            return [], None

    async def _get_remote_md5(self, url: str) -> Optional[str]:
        """Get MD5 hash from meta4 file."""
        try:
            if url.endswith('.meta4'):
                # Extract MD5 from meta4 file
                mirrors, md5_hash = await self._fetch_meta4_file(url)
                if md5_hash:
                    log.info("md5_fetch.from_meta4", url=url, md5=md5_hash)
                    return md5_hash
            return None
        except Exception as e:
            log.error("md5_fetch.error", url=url, error=str(e))
            return None

    def _calculate_file_md5(self, filepath: str) -> Optional[str]:
        """Calculate MD5 hash of a file."""
        try:
            log.info("md5_calculate.starting", filepath=filepath)
            md5_hash = hashlib.md5()
            with open(filepath, "rb") as f:
                # Read the file in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            result = md5_hash.hexdigest()
            log.info("md5_calculate.complete", filepath=filepath, md5=result)
            return result
        except Exception as e:
            log.error("md5_calculate.error", filepath=filepath, error=str(e))
            return None

    def _compare_versions(self, current_version: str, new_version: str) -> bool:
        """Compare version strings to determine if new version is newer.
        Returns True if new_version is newer than current_version."""
        try:
            current_date = datetime.strptime(current_version, "%Y-%m")
            new_date = datetime.strptime(new_version, "%Y-%m")
            return new_date > current_date
        except ValueError:
            log.error("version_compare.error", 
                     current=current_version, 
                     new=new_version)
            return False

    def _extract_version_from_filename(self, filename: str) -> Optional[str]:
        """Extract version (YYYY-MM) from filename."""
        match = re.search(r'_(\d{4}-\d{2})\.zim$', filename)
        return match.group(1) if match else None

    async def _verify_download(self, filepath: str, md5_url: str) -> bool:
        """Verify downloaded file using MD5."""
        expected_md5 = await self._get_remote_md5(md5_url)
        if not expected_md5:
            return False
            
        actual_md5 = self._calculate_file_md5(filepath)
        if not actual_md5:
            return False
            
        matches = expected_md5.lower() == actual_md5.lower()
        if not matches:
            log.error("md5_verify.mismatch",
                     filepath=filepath,
                     expected=expected_md5,
                     actual=actual_md5)
        return matches

    async def _download_file(self, url: str, dest_path: str, content: ContentItem, mirrors: List[str] = None, expected_md5: str = None) -> bool:
        """Download a file with MD5 verification and version management."""
        temp_path = f"{dest_path}.tmp"
        max_retries = self.config.options.retry_attempts
        retry_count = 0
        
        # Get MD5 from meta4 file if available
        expected_md5 = None
        meta4_mirrors = []
        if url.endswith('.meta4'):
            meta4_mirrors, meta4_md5 = await self._fetch_meta4_file(url)
            if meta4_md5:
                log.info("md5_verify.meta4_hash_found", 
                      content=content.name,
                      md5=meta4_md5)
                expected_md5 = meta4_md5
                mirrors = meta4_mirrors if meta4_mirrors else mirrors
                # Remove .meta4 extension from original URL for direct download
                url = url[:-6]
        
        # Check if we already have a version of this file
        dest_dir = os.path.dirname(dest_path)
        base_pattern = re.sub(r'_\d{4}-\d{2}\.zim$', '', os.path.basename(dest_path))
        existing_files = []
        if os.path.exists(dest_dir):
            for f in os.listdir(dest_dir):
                if f.startswith(base_pattern) and f.endswith('.zim'):
                    existing_files.append(os.path.join(dest_dir, f))
        
        try:
            async with self.download_semaphore:
                while retry_count <= max_retries:
                    # Try each mirror URL in sequence
                    urls_to_try = []
                    if meta4_mirrors:
                        urls_to_try.extend(meta4_mirrors)
                    elif mirrors:
                        urls_to_try.extend(mirrors)
                    else:
                        urls_to_try.append(url)
                    
                    for current_url in urls_to_try:
                        try:
                            # Remove any .meta4 extension from mirror URLs
                            if current_url.endswith('.meta4'):
                                current_url = current_url[:-6]
                            
                            download_url = current_url if current_url.startswith('http') else urljoin(self.base_url, current_url)
                            log.info("download.starting", 
                                    content=content.name,
                                    url=download_url,
                                    dest=dest_path,
                                    attempt=retry_count + 1,
                                    max_attempts=max_retries + 1,
                                    expected_md5=expected_md5)  # Log the expected MD5
                            
                            timeout = aiohttp.ClientTimeout(
                                total=None,
                                connect=120,
                                sock_read=600,
                                sock_connect=60
                            )
                            
                            connector = aiohttp.TCPConnector(
                                force_close=True,
                                enable_cleanup_closed=True,
                                limit=1
                            )
                            
                            async with aiohttp.ClientSession(
                                timeout=timeout,
                                connector=connector,
                                raise_for_status=True
                            ) as session:
                                async with session.get(download_url) as response:
                                    if response.status != 200:
                                        raise Exception(f"Download failed: {response.status}")
                                    
                                    total_size = int(response.headers.get('content-length', 0))
                                    downloaded = 0
                                    
                                    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                                    
                                    async with aiofiles.open(temp_path, 'wb') as f:
                                        async for chunk in response.content.iter_chunked(1024 * 1024):
                                            await f.write(chunk)
                                            downloaded += len(chunk)
                                            monitoring.update_content_size(
                                                content.name,
                                                content.language,
                                                downloaded
                                            )
                                            
                                            if total_size > 0 and downloaded % (10 * 1024 * 1024) == 0:
                                                progress = (downloaded / total_size) * 100
                                                log.debug("download.progress",
                                                        content=content.name,
                                                        progress=f"{progress:.1f}%",
                                                        downloaded=downloaded,
                                                        total=total_size)
                                    
                                    # Always verify MD5 if provided
                                    actual_md5 = self._calculate_file_md5(temp_path)
                                    if not actual_md5:
                                        log.error("md5_calculate.failed", 
                                                file=temp_path,
                                                content=content.name)
                                        continue
                                    
                                    if expected_md5:
                                        if actual_md5.lower() != expected_md5.lower():
                                            log.error("md5_verify.mismatch",
                                                    file=temp_path,
                                                    expected=expected_md5,
                                                    actual=actual_md5,
                                                    content=content.name,
                                                    url=download_url)
                                            if os.path.exists(temp_path):
                                                os.remove(temp_path)
                                            continue
                                        
                                        log.info("md5_verify.success",
                                                content=content.name,
                                                md5=actual_md5,
                                                expected=expected_md5,
                                                file=temp_path)
                                    
                                    # Move file to final location
                                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                    os.rename(temp_path, dest_path)
                                    
                                    # Remove old versions after successful download
                                    for old_file in existing_files:
                                        if old_file != dest_path:
                                            try:
                                                os.remove(old_file)
                                                log.info("old_version.removed", file=old_file)
                                            except Exception as e:
                                                log.error("old_version.remove_failed",
                                                        file=old_file,
                                                        error=str(e))
                                    
                                    log.info("download.complete",
                                            content=content.name,
                                            size=os.path.getsize(dest_path))
                                            
                                    monitoring.record_download("success", content.language)
                                    return True
                                    
                        except Exception as e:
                            log.error("download.mirror_failed",
                                    content=content.name,
                                    url=current_url,
                                    error=str(e))
                            continue  # Try next mirror
                    
                    # If we get here, all mirrors failed
                    retry_count += 1
                    if retry_count <= max_retries:
                        log.warning("download.retry",
                                  content=content.name,
                                  attempt=retry_count,
                                  max_attempts=max_retries + 1)
                        await asyncio.sleep(2 ** retry_count)
                        continue
                    
                    log.error("download.all_mirrors_failed",
                             content=content.name,
                             attempts=retry_count)
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
            log.error("download.failed",
                     content=content.name,
                     error=str(e),
                     traceback=traceback.format_exc())
            monitoring.record_download("failed", content.language)
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
                    
                    # Get MD5 before proceeding with download decision
                    remote_md5_url = f"{latest_version.url}.md5"
                    remote_md5 = await self._get_remote_md5(remote_md5_url)
                    
                    if not remote_md5:
                        log.error("md5_fetch.failed_pre_download",
                                content=content_item.name,
                                url=remote_md5_url)
                        continue
                        
                    log.info("md5_fetch.success_pre_download",
                            content=content_item.name,
                            md5=remote_md5,
                            url=remote_md5_url)
                    
                    # Create state for this content
                    state = {
                        'last_updated': latest_version.date,
                        'size': latest_version.size,
                        'path': dest_path,
                        'md5': remote_md5
                    }
                    
                    # Update state immediately
                    self.content_state[content_item.name] = state
                    
                    # Check if we already have a version of this file
                    dest_dir = os.path.dirname(dest_path)
                    base_pattern = re.sub(r'_\d{4}-\d{2}\.zim$', '', os.path.basename(dest_path))
                    existing_files = []
                    if os.path.exists(dest_dir):
                        for f in os.listdir(dest_dir):
                            if f.startswith(base_pattern) and f.endswith('.zim'):
                                existing_files.append(os.path.join(dest_dir, f))
                    
                    # Check if download/update needed
                    needs_download = not os.path.exists(dest_path)
                    
                    # Check both file size and date for updates
                    current_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                    size_mismatch = current_size != latest_version.size
                    
                    # Extract date from filename for comparison
                    date_match = re.search(r'_(\d{4}-\d{2}).zim$', os.path.basename(dest_path)) if os.path.exists(dest_path) else None
                    file_date = date_match.group(1) if date_match else None
                    latest_date = re.search(r'_(\d{4}-\d{2}).zim$', latest_version.path).group(1)
                    date_mismatch = file_date != latest_date if file_date else True
                    
                    # Verify MD5 of existing file if it exists
                    md5_mismatch = False
                    if os.path.exists(dest_path):
                        local_md5 = self._calculate_file_md5(dest_path)
                        if local_md5:
                            if local_md5 != remote_md5:
                                log.warning("md5_verify.mismatch_pre_download",
                                          file=dest_path,
                                          local_md5=local_md5,
                                          remote_md5=remote_md5)
                                md5_mismatch = True
                            else:
                                log.info("md5_verify.match_pre_download",
                                        file=dest_path,
                                        md5=local_md5)
                    
                    needs_update = size_mismatch or date_mismatch or md5_mismatch
                    
                    log.info("content_update.download_check",
                            content_name=content_item.name,
                            needs_download=needs_download,
                            needs_update=needs_update,
                            current_size=current_size,
                            new_size=latest_version.size,
                            size_mismatch=size_mismatch,
                            current_date=file_date,
                            new_date=latest_date,
                            date_mismatch=date_mismatch,
                            md5_mismatch=md5_mismatch)
                    
                    if needs_download or needs_update:
                        log.info("content_update.queueing_download",
                                content_name=content_item.name,
                                filename=filename,
                                size=latest_version.size,
                                md5=remote_md5)
                        download_task = self._download_file(
                            latest_version.url,
                            dest_path,
                            content_item,
                            latest_version.mirrors
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

    async def queue_download(self, book: Dict):
        """Queue a book for download."""
        try:
            # Create a content item from the book data
            content_item = ContentItem(
                name=book['name'],
                language=book['language'],
                category=book.get('creator', 'unknown')
            )
            
            # Get mirror URLs and MD5 from meta4 file if available
            mirrors = []
            md5_hash = None
            if book['url'].endswith('.meta4'):
                mirrors, md5_hash = await self._fetch_meta4_file(book['url'])
                if not mirrors:
                    log.error("download_worker.no_mirrors", book=book['name'])
                    return
                
                log.info("download_worker.meta4_parsed",
                        book=book['name'],
                        mirrors=len(mirrors),
                        md5=md5_hash)
            
            # Use first mirror as primary URL
            url = mirrors[0] if mirrors else book['url']
            
            # Create category subdirectory
            category_dir = os.path.join(self.config.data_dir, content_item.category)
            os.makedirs(category_dir, exist_ok=True)
            
            # Determine destination path
            filename = os.path.basename(url)
            if not filename.endswith('.zim'):
                filename = f"{book['name']}.zim"
            
            dest_path = os.path.join(category_dir, filename)
            
            # Add to active downloads
            self.active_downloads.add(book['name'])
            
            try:
                # Download the file
                success = await self._download_file(
                    url,
                    dest_path,
                    content_item,
                    mirrors[1:] if len(mirrors) > 1 else None,  # Rest of mirrors as fallbacks
                    md5_hash  # Pass the MD5 hash
                )
                
                if success:
                    log.info("download_worker.success", book=book['name'])
                else:
                    log.error("download_worker.failed", book=book['name'])
                    
            finally:
                # Remove from active downloads
                self.active_downloads.discard(book['name'])
                
        except Exception as e:
            log.error("queue_download.failed", error=str(e))
            raise

    async def _download_worker(self):
        """Background worker to process download queue."""
        while True:
            try:
                book, content_item = await self.download_queue.get()
                
                # Get mirror URLs from meta4 file
                mirrors = []
                if book['url'].endswith('.meta4'):
                    mirrors = await self._fetch_meta4_file(book['url'])
                
                if not mirrors:
                    log.error("download_worker.no_mirrors", book=book['name'])
                    continue
                
                # Use first mirror as primary URL
                url = mirrors[0]
                
                # Create category subdirectory
                category_dir = os.path.join(self.config.data_dir, content_item.category)
                os.makedirs(category_dir, exist_ok=True)
                
                # Determine destination path
                filename = os.path.basename(url)
                if not filename.endswith('.zim'):
                    filename = f"{book['name']}.zim"
                
                dest_path = os.path.join(category_dir, filename)
                
                # Add to active downloads
                self.active_downloads.add(book['name'])
                
                try:
                    # Download the file
                    success = await self._download_file(
                        url,
                        dest_path,
                        content_item,
                        mirrors[1:]  # Rest of mirrors as fallbacks
                    )
                    
                    if success:
                        log.info("download_worker.success", book=book['name'])
                    else:
                        log.error("download_worker.failed", book=book['name'])
                        
                finally:
                    # Remove from active downloads
                    self.active_downloads.discard(book['name'])
                    
            except Exception as e:
                log.error("download_worker.error", error=str(e))
            finally:
                self.download_queue.task_done()

    def get_download_status(self) -> List[Dict]:
        """Get status of current downloads."""
        return [
            {
                'name': name,
                'status': 'downloading'
            }
            for name in self.active_downloads
        ] 

    async def _process_meta4_batch(self, books: List[ET.Element]) -> List[ContentFile]:
        """Process a batch of books to fetch their meta4 files in parallel."""
        content_files = []
        tasks = []
        
        for book in books:
            url = book.get("url", "")
            if not url or not url.endswith(".meta4"):
                continue
                
            size = int(book.get("size", 0))
            name = book.get("name", "")
            date = book.get("date", "")
            
            # Create task for fetching meta4
            task = asyncio.create_task(self._fetch_meta4_file(url))
            tasks.append((book, task))
        
        # Wait for all meta4 fetches to complete
        for book, task in tasks:
            try:
                mirrors, md5_hash = await task
                if not mirrors:
                    log.warning("content.no_mirrors", name=book.get("name", ""))
                    continue

                log.info("content.meta4_parsed",
                        name=book.get("name", ""),
                        mirrors=len(mirrors),
                        md5=md5_hash)

                content_file = ContentFile(
                    name=book.get("name", ""),
                    path=book.get("name", ""),
                    url=book.get("url", ""),
                    size=int(book.get("size", 0)),
                    date=book.get("date", ""),
                    mirrors=mirrors,
                    md5_url=book.get("url", "")
                )
                content_files.append(content_file)
                
            except Exception as e:
                log.error("content.parse_failed", 
                         error=str(e),
                         name=book.get("name", ""))
                continue
                
        return content_files

    async def _get_available_content(self) -> List[ContentFile]:
        """Get list of available content from central library XML."""
        try:
            library_root = await self._fetch_library_xml()
            if not library_root:
                return []

            # Get all books
            books = library_root.findall(".//book")
            content_files = []
            batch_size = 100

            # Process books in batches
            for i in range(0, len(books), batch_size):
                batch = books[i:i + batch_size]
                log.info("content.processing_batch", 
                        start=i, 
                        size=len(batch),
                        total=len(books))
                
                batch_results = await self._process_meta4_batch(batch)
                content_files.extend(batch_results)

            log.info("content_list.complete", count=len(content_files))
            return content_files

        except Exception as e:
            log.error("content_list.failed", error=str(e))
            return []
