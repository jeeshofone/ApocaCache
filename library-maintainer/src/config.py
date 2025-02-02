"""
Configuration management for the ApocaCache library maintainer.
Handles environment variables and YAML configuration parsing.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
import yaml

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
        self.base_url = os.getenv("KIWIX_SERVER_URL", "http://kiwix-serve")
        
        # Environment variables
        self.language_filter = os.getenv("LANGUAGE_FILTER", "").split(",")
        self.download_all = os.getenv("DOWNLOAD_ALL", "false").lower() == "true"
        
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
        config_file = os.path.join(self.config_dir, "download-list.yaml")
        
        if not os.path.exists(config_file):
            return
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Parse content items
        if "content" in config:
            self.content_list = [
                ContentItem(**item)
                for item in config["content"]
            ]
        
        # Parse options
        if "options" in config:
            self.options = ContentOptions(**config["options"])
    
    def should_download_content(self, content: ContentItem) -> bool:
        """Determine if content should be downloaded based on filters."""
        if self.download_all:
            return True
        
        if not self.language_filter:
            return True
        
        return content.language in self.language_filter 