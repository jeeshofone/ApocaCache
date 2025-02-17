"""
Library management for ApocaCache library maintainer.
Handles library.xml generation and management for Kiwix-serve.
"""

import os
import time
from typing import Dict, List, Optional, Set
import xml.etree.ElementTree as ET
from xml.dom import minidom
import aiofiles
import structlog
import traceback
import re
from datetime import datetime

from config import Config, ContentItem
import monitoring

log = structlog.get_logger()

class LibraryManager:
    """Manages the library.xml file for Kiwix-serve."""
    
    def __init__(self, config: Config):
        """Initialize the library manager."""
        self.config = config
        self._processed_files: Set[str] = set()
    
    def _get_zim_metadata(self, filepath: str) -> Dict[str, str]:
        """Extract metadata from a ZIM file."""
        # TODO: Implement ZIM file metadata extraction
        # For now, return basic metadata from filename
        filename = os.path.basename(filepath)
        name_parts = filename.replace('.zim', '').split('_')
        
        # Extract category from filepath
        category = os.path.basename(os.path.dirname(filepath))
        
        # Extract name and language from filename
        if len(name_parts) > 1:
            name = '_'.join(name_parts[:-1])  # Everything except date
            language = name_parts[1] if len(name_parts) > 1 else 'eng'
            date = name_parts[-1]
            
            # Try to extract a meaningful title
            if '.' in name_parts[0]:
                title_parts = name_parts[0].split('.')
                title = ' '.join(part.capitalize() for part in title_parts)
            else:
                title = name_parts[0].replace('_', ' ').title()
        else:
            name = name_parts[0]
            language = 'eng'
            date = ''
            title = name.replace('_', ' ').title()
        
        # Provide all required metadata fields with defaults
        return {
            'name': name,
            'date': date,
            'language': language,
            'creator': category,  # Use category as creator
            'publisher': 'Kiwix',
            'description': f'Kiwix ZIM file for {title}',
            'title': title,
            'media_count': '0',
            'article_count': '0',
            'favicon': '',
            'favicon_mime_type': '',
            'tags': f'_category:{category};_ftindex:yes',  # Add basic tags
            'size': str(os.path.getsize(filepath))
        }
    
    def _get_base_name(self, filename: str) -> str:
        """Get the base name without version from filename."""
        return re.sub(r'_\d{4}-\d{2}\.zim$', '', filename)
    
    def _is_newer_version(self, current: str, new: str) -> bool:
        """Check if new version is newer than current version."""
        try:
            current_match = re.search(r'_(\d{4}-\d{2})\.zim$', current)
            new_match = re.search(r'_(\d{4}-\d{2})\.zim$', new)
            if current_match and new_match:
                current_date = datetime.strptime(current_match.group(1), "%Y-%m")
                new_date = datetime.strptime(new_match.group(1), "%Y-%m")
                return new_date > current_date
            return False
        except (ValueError, AttributeError):
            return False
    
    async def update_library(self):
        """Update the library.xml file with current content."""
        start_time = time.time()
        log.info("library_update.starting")
        temp_file = None
        
        try:
            # Create root element
            root = ET.Element('library')
            root.set('version', '20110515')
            
            # Track total library size
            total_size = 0
            book_count = 0
            
            # Keep track of processed base names to handle versioning
            processed_base_names = {}
            
            # First pass: collect all files and their versions
            all_files = []
            for root_dir, dirs, files in os.walk(self.config.data_dir):
                for filename in files:
                    if filename.endswith('.zim'):
                        filepath = os.path.join(root_dir, filename)
                        base_name = self._get_base_name(filename)
                        if base_name in processed_base_names:
                            # Compare versions
                            if self._is_newer_version(processed_base_names[base_name], filename):
                                processed_base_names[base_name] = filename
                        else:
                            processed_base_names[base_name] = filename
                        all_files.append((filepath, filename))
            
            # Second pass: add only the latest versions to library.xml
            for filepath, filename in all_files:
                base_name = self._get_base_name(filename)
                if processed_base_names[base_name] == filename:
                    try:
                        # Get relative path from data directory
                        rel_path = os.path.relpath(filepath, self.config.data_dir)
                        size = os.path.getsize(filepath)
                        total_size += size
                        
                        # Get metadata
                        metadata = self._get_zim_metadata(filepath)
                        
                        # Create book element with all attributes
                        book = ET.SubElement(root, 'book')
                        # Generate ID from filename if not present
                        book_id = metadata.get('id', os.path.splitext(os.path.basename(filepath))[0])
                        book.set('id', book_id)
                        book.set('path', rel_path)
                        book.set('size', str(size))
                        book.set('mediaCount', metadata.get('media_count', '0'))
                        book.set('articleCount', metadata.get('article_count', '0'))
                        book.set('favicon', metadata.get('favicon', ''))
                        book.set('faviconMimeType', metadata.get('favicon_mime_type', ''))
                        
                        # Add metadata elements
                        ET.SubElement(book, 'title').text = metadata.get('title', '')
                        ET.SubElement(book, 'description').text = metadata.get('description', '')
                        ET.SubElement(book, 'language').text = metadata.get('language', '')
                        ET.SubElement(book, 'creator').text = metadata.get('creator', '')
                        ET.SubElement(book, 'publisher').text = metadata.get('publisher', '')
                        ET.SubElement(book, 'name').text = metadata.get('name', '')
                        ET.SubElement(book, 'tags').text = metadata.get('tags', '')
                        ET.SubElement(book, 'date').text = metadata.get('date', '')
                        
                        # Add URL for source
                        if os.getenv("TESTING", "false").lower() == "true":
                            url = "https://github.com/openzim/zim-tools/blob/main/test/data/zimfiles/good.zim"
                        else:
                            # Extract category from filepath
                            category = os.path.basename(os.path.dirname(filepath))
                            url = f"{self.config.base_url}{category}/{filename}"
                        ET.SubElement(book, 'url').text = url
                        book_count += 1
                        
                        log.debug("library_update.added_book",
                                title=metadata.get('title', ''),
                                language=metadata.get('language', ''),
                                size=size,
                                version=metadata.get('date', ''))
                    except Exception as book_error:
                        log.error("library_update.book_failed",
                                filename=filename,
                                error=str(book_error))
                        continue
            
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
                     total_size=total_size,
                     books=book_count,
                     library_file=self.config.library_file)
            
        except Exception as e:
            log.error("library_update.failed", 
                     error=str(e),
                     traceback=traceback.format_exc())
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as cleanup_error:
                    log.error("library_update.cleanup_failed", 
                             error=str(cleanup_error))
            raise  # Re-raise to ensure the error is properly handled
    
    async def cleanup(self):
        """Clean up temporary library files."""
        try:
            temp_file = f"{self.config.library_file}.tmp"
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception as e:
            log.error("cleanup.failed", error=str(e)) 
