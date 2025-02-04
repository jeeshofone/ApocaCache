"""
Configuration management for the ApocaCache library maintainer.
Handles environment variables and YAML configuration parsing.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
import yaml
import structlog

log = structlog.get_logger()

@dataclass
class ContentItem:
    """Represents a content item from the download list."""
    name: str
    language: str
    category: str
    description: Optional[str] = None

@dataclass
class ContentOptions:
    """Configuration options for content management."""
    max_concurrent_downloads: int = 2
    retry_attempts: int = 3
    verify_downloads: bool = True
    cleanup_incomplete: bool = True

class Config:
    """Main configuration class."""
    
    def __init__(self):
        """Initialize configuration from environment and files."""
        self.data_dir = "/data"
        self.config_dir = "/config"
        self.library_file = os.path.join(self.data_dir, "library.xml")
        
        # Always use the official Kiwix download server
        self.base_url = os.getenv("BASE_URL", "https://download.kiwix.org/zim/")
        
        # Directory scanning options
        self.max_scan_depth = int(os.getenv("MAX_SCAN_DEPTH", "5"))
        self.excluded_dirs = os.getenv("EXCLUDED_DIRS", "").split(",")
        
        # Environment variables
        self.language_filter = os.getenv("LANGUAGE_FILTER", "").split(",")
        self.download_all = os.getenv("DOWNLOAD_ALL", "false").lower() == "true"
        self.content_pattern = os.getenv('CONTENT_PATTERN', '.*')
        self.scan_subdirs = os.getenv('SCAN_SUBDIRS', 'false').lower() == 'true'
        
        # Parse update schedule
        schedule_str = os.getenv("UPDATE_SCHEDULE", "0 2 1 * *")
        minute, hour, day, month, day_of_week = schedule_str.split()
        self.update_schedule = {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week
        }
        
        # Load download list
        self.content_list: List[ContentItem] = []
        self.options = ContentOptions()
        self._load_download_list()
    
    def _load_download_list(self):
        """Load and parse the download list configuration."""
        config_file = os.path.join(self.data_dir, "download-list.yaml")
        
        if not os.path.exists(config_file):
            log.warning("download_list.not_found", path=config_file)
            return
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                log.info("download_list.loaded", path=config_file)
            
            # Parse content items
            if "content" in config:
                self.content_list = [
                    ContentItem(**item)
                    for item in config["content"]
                ]
                log.info("download_list.parsed", items=len(self.content_list))
            else:
                log.warning("download_list.no_content", path=config_file)
            
            # Parse options
            if "options" in config:
                self.options = ContentOptions(**config["options"])
                log.info("download_list.options_parsed", 
                        max_concurrent_downloads=self.options.max_concurrent_downloads,
                        retry_attempts=self.options.retry_attempts)
        except Exception as e:
            log.error("download_list.parse_failed", error=str(e))
    
    def should_download_content(self, content: ContentItem) -> bool:
        """Check if content should be downloaded based on filters."""
        if self.download_all:
            return True
        
        if not self.language_filter:
            return True
        
        return content.language in self.language_filter 
