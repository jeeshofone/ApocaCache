"""
Content management for ApocaCache library maintainer.
Handles downloading, verifying, and managing ZIM files.
"""

import asyncio
import os
import time
import json
from datetime import datetime
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
        self.base_url = config.base_url
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
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch content list: {response.status}")
                
                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')
                content_list = []
                
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href and href.endswith('.zim'):
                        size = link.next_sibling.strip('()')
                        date_str = link.next_sibling.next_sibling.strip('[]')
                        try:
                            date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                            content_list.append((href, date_str, int(size)))
                        except ValueError:
                            continue
                
                return content_list
    
    async def _download_file(self, url: str, dest_path: str, content: ContentItem) -> bool:
        """Download a file with progress tracking and verification."""
        temp_path = f"{dest_path}.tmp"
        
        async with self.download_semaphore:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}{url}") as response:
                        if response.status != 200:
                            raise Exception(f"Download failed: {response.status}")
                        
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0
                        
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
                if not self.config.should_download_content(content_item):
                    continue
                
                # Find matching content
                for filename, date_str, size in available_content:
                    if filename.startswith(f"{content_item.category}/{content_item.name}"):
                        dest_path = os.path.join(
                            self.config.data_dir,
                            filename
                        )
                        
                        # Check if update needed
                        state = self.content_state.get(content_item.name, {})
                        if (not os.path.exists(dest_path) or
                            state.get('last_updated') != date_str):
                            
                            download_tasks.append(
                                self._download_file(
                                    filename,
                                    dest_path,
                                    content_item
                                )
                            )
                            
                            # Update state
                            self.content_state[content_item.name] = {
                                'last_updated': date_str,
                                'size': size,
                                'path': dest_path
                            }
            
            if download_tasks:
                results = await asyncio.gather(*download_tasks)
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