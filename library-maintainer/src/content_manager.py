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

from config import Config, ContentItem
import monitoring

log = structlog.get_logger()

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
        self._load_state()
    
    def _load_state(self):
        """Load content state from state file."""
        state_file = os.path.join(self.config.data_dir, "content_state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    self.content_state = json.loads(f.read())
            except Exception as e:
                log.error("content_state.load_failed", error=str(e))
    
    async def _save_state(self):
        """Save content state to state file."""
        state_file = os.path.join(self.config.data_dir, "content_state.json")
        try:
            async with aiofiles.open(state_file, 'w') as f:
                await f.write(json.dumps(self.content_state, indent=2))
        except Exception as e:
            log.error("content_state.save_failed", error=str(e))
    
    async def _get_available_content(self) -> List[Tuple[str, str, int]]:
        """Fetch list of available content from Kiwix server."""
        async def scan_directory(url: str, path: str = "") -> List[Tuple[str, str, int]]:
            """Recursively scan a directory for content."""
            content_list = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch content list: {response.status}")
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')
                    
                    # Find the pre element containing the file list
                    pre = soup.find('pre')
                    if not pre:
                        log.error("content_list.parse_failed", error="No pre element found in directory listing")
                        return []
                    
                    # Process each line
                    for line in pre.get_text().split('\n'):
                        log.info("content_list.parsing_line", line=line)
                        if line.strip() and not line.startswith('../'):
                            # Try mock server format first (filename size date)
                            match = re.match(r'(.+?)\s+(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', line.strip())
                            if not match:
                                # Try production format
                                match = re.match(r'(.+?)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+(\d+)', line.strip())
                                if match:
                                    filename = match.group(1).strip()
                                    size = int(match.group(3))
                                    date_str = match.group(2)
                                    log.info("content_list.matched_production", filename=filename, size=size, date=date_str)
                                else:
                                    log.error("content_list.no_match", line=line)
                                    continue
                            else:
                                filename = match.group(1).strip()
                                size = int(match.group(2))
                                date_str = match.group(3)
                                log.info("content_list.matched_mock", filename=filename, size=size, date=date_str)
                            
                            if filename.endswith('.zim'):
                                full_path = os.path.join(path, filename) if path else filename
                                content_list.append((full_path, date_str, size))
                                log.info("content_list.added", filename=full_path)
                            elif filename.endswith('/'):
                                # This is a directory, scan it recursively
                                subdir_name = filename.rstrip('/')
                                subdir_url = f"{url.rstrip('/')}/{subdir_name}"
                                subdir_path = os.path.join(path, subdir_name) if path else subdir_name
                                subdir_content = await scan_directory(subdir_url, subdir_path)
                                content_list.extend(subdir_content)
                                log.info("content_list.scanned_subdir", subdir=subdir_path)
                    
                    return content_list
        
        content_list = await scan_directory(self.base_url)
        log.info("content_list.complete", count=len(content_list), items=content_list)
        return content_list
    
    async def _download_file(self, url: str, dest_path: str, content: ContentItem) -> bool:
        """Download a file with progress tracking and verification."""
        temp_path = f"{dest_path}.tmp"
        
        async with self.download_semaphore:
            try:
                async with aiohttp.ClientSession() as session:
                    # Handle full paths with subdirectories
                    download_url = f"{self.base_url.rstrip('/')}/{url}"
                    async with session.get(download_url) as response:
                        if response.status != 200:
                            raise Exception(f"Download failed: {response.status}")
                        
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0
                        
                        # Create parent directory if it doesn't exist
                        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                        
                        async with aiofiles.open(temp_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                                downloaded += len(chunk)
                                monitoring.update_content_size(
                                    content.name,
                                    content.language,
                                    downloaded
                                )
                
                if self.config.options.verify_downloads:
                    # Verify download
                    if os.path.getsize(temp_path) != total_size:
                        raise Exception("Download size mismatch")
                
                # Create parent directory if it doesn't exist
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                os.rename(temp_path, dest_path)
                monitoring.record_download("success", content.language)
                return True
                
            except Exception as e:
                log.error("download.failed",
                         content=content.name,
                         error=str(e))
                monitoring.record_download("failed", content.language)
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
    
    async def update_content(self):
        """Update content based on configuration."""
        start_time = time.time()
        log.info("content_update.starting")
        
        try:
            available_content = await self._get_available_content()
            download_tasks = []
            
            for content_item in self.config.content_list:
                # Find matching content
                for filepath, date_str, size in available_content:
                    filename = os.path.basename(filepath)
                    if filename == f"{content_item.name}.zim" or filename.startswith(f"{content_item.name}.zim"):
                        # Create category subdirectory
                        category_dir = os.path.join(self.config.data_dir, content_item.category)
                        os.makedirs(category_dir, exist_ok=True)
                        
                        dest_path = os.path.join(
                            category_dir,
                            filename
                        )
                        
                        # Create state for this content
                        state = {
                            'last_updated': date_str,
                            'size': size,
                            'path': dest_path
                        }
                        
                        # Update state immediately
                        self.content_state[content_item.name] = state
                        
                        # Check if download/update needed
                        if self.config.should_download_content(content_item) and \
                           (not os.path.exists(dest_path) or \
                           self.content_state.get(content_item.name, {}).get('last_updated') != date_str):
                            download_task = self._download_file(
                                filepath,  # Use the full path from the server
                                dest_path,
                                content_item
                            )
                            download_tasks.append(download_task)
                        break  # Found matching file, no need to check more
            
            if download_tasks:
                results = await asyncio.gather(*download_tasks)
                
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