"""
Library management for ApocaCache library maintainer.
Handles library.xml generation and management for Kiwix-serve.
"""

import os
import time
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
from xml.dom import minidom
import aiofiles
import structlog

from config import Config, ContentItem
import monitoring

log = structlog.get_logger()

class LibraryManager:
    """Manages the library.xml file for Kiwix-serve."""
    
    def __init__(self, config: Config):
        """Initialize the library manager."""
        self.config = config
    
    def _get_zim_metadata(self, filepath: str) -> Dict[str, str]:
        """Extract metadata from a ZIM file."""
        # TODO: Implement ZIM file metadata extraction
        # For now, return basic metadata from filename
        filename = os.path.basename(filepath)
        name_parts = filename.replace('.zim', '').split('_')
        
        return {
            'name': '_'.join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0],
            'date': name_parts[-1] if len(name_parts) > 1 else '',
            'language': name_parts[1] if len(name_parts) > 1 else 'eng',
            'creator': name_parts[0],
            'publisher': 'Kiwix',
            'description': f'Kiwix ZIM file for {name_parts[0]}'
        }
    
    async def update_library(self):
        """Update the library.xml file with current content."""
        start_time = time.time()
        log.info("library_update.starting")
        
        try:
            # Create root element
            root = ET.Element('library')
            root.set('version', '20110515')
            
            # Track total library size
            total_size = 0
            
            # Add book elements for each ZIM file
            for filename in os.listdir(self.config.data_dir):
                if filename.endswith('.zim'):
                    filepath = os.path.join(self.config.data_dir, filename)
                    size = os.path.getsize(filepath)
                    total_size += size
                    
                    # Get metadata
                    metadata = self._get_zim_metadata(filepath)
                    
                    # Create book element
                    book = ET.SubElement(root, 'book')
                    book.set('id', f"kiwix_{metadata['name']}")
                    book.set('path', filepath)
                    
                    # Add metadata elements
                    ET.SubElement(book, 'title').text = metadata['name']
                    ET.SubElement(book, 'creator').text = metadata['creator']
                    ET.SubElement(book, 'publisher').text = metadata['publisher']
                    ET.SubElement(book, 'date').text = metadata['date']
                    ET.SubElement(book, 'description').text = metadata['description']
                    ET.SubElement(book, 'language').text = metadata['language']
                    ET.SubElement(book, 'size').text = str(size)
                    
                    # Add URL for source
                    if os.getenv("TESTING", "false").lower() == "true":
                        url = "https://github.com/openzim/zim-tools/blob/main/test/data/zimfiles/good.zim"
                    else:
                        url = f"{self.config.base_url}{metadata['creator']}/{filename}"
                    ET.SubElement(book, 'url').text = url
            
            # Format XML with proper indentation
            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
            
            # Write to temporary file first
            temp_file = f"{self.config.library_file}.tmp"
            async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                await f.write(xml_str)
            
            # Atomically replace the old file
            os.rename(temp_file, self.config.library_file)
            
            # Update metrics
            monitoring.set_library_size(total_size)
            
            duration = time.time() - start_time
            log.info("library_update.complete",
                     duration=duration,
                     total_size=total_size)
            
        except Exception as e:
            log.error("library_update.failed", error=str(e))
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    async def cleanup(self):
        """Clean up temporary library files."""
        try:
            temp_file = f"{self.config.library_file}.tmp"
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception as e:
            log.error("cleanup.failed", error=str(e)) 