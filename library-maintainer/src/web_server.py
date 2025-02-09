"""
Web server for ApocaCache library maintainer.
Provides a web interface to manage content downloads.
"""

import os
import json
import aiohttp
import aiofiles
from aiohttp import web
import structlog
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set
from datetime import datetime
import asyncio
import sqlite3

from database import DatabaseManager

log = structlog.get_logger()

class WebServer:
    """Web server for managing content downloads."""
    
    def __init__(self, content_manager, config):
        """Initialize the web server."""
        self.content_manager = content_manager
        self.config = config
        self.app = web.Application()
        self.setup_routes()
        self.library_cache = None
        self.library_cache_time = None
        self.cache_ttl = 3600  # 1 hour cache TTL
        self.db = DatabaseManager(config.data_dir)
        self.meta4_semaphore = asyncio.Semaphore(100)  # Increased to 100 concurrent downloads
        self.is_updating_meta4 = False
        self.successful_meta4_downloads = 0
        
    def setup_routes(self):
        """Setup web server routes."""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/library', self.handle_library)
        self.app.router.add_post('/queue', self.handle_queue)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_get('/meta4-status', self.handle_meta4_status)
        self.app.router.add_static('/static', os.path.join(os.path.dirname(__file__), 'static'))
    
    async def start(self):
        """Start the web server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 3118)
        await site.start()
        log.info("web_server.started", port=3118)
        
        # Start meta4 update process in background
        asyncio.create_task(self._update_meta4_files())
    
    async def _parse_meta4_file(self, url: str) -> Dict:
        """Parse meta4 file to extract size and hash information."""
        try:
            async with self.meta4_semaphore:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            log.error("meta4_download.failed", url=url, status=response.status)
                            return {}
                        
                        content = await response.text()
                        root = ET.fromstring(content)
                        
                        # Extract file information
                        file_elem = root.find(".//{urn:ietf:params:xml:ns:metalink}file")
                        if file_elem is None:
                            log.error("meta4_parse.no_file_element", url=url)
                            return {}
                        
                        # Get file name
                        file_name = file_elem.get("name", "")
                        
                        # Get file size
                        size_elem = file_elem.find(".//{urn:ietf:params:xml:ns:metalink}size")
                        file_size = int(size_elem.text) if size_elem is not None else 0
                        
                        # Get hashes
                        hashes = {}
                        for hash_elem in file_elem.findall(".//{urn:ietf:params:xml:ns:metalink}hash"):
                            hash_type = hash_elem.get("type", "")
                            if hash_type and hash_elem.text:
                                hashes[hash_type] = hash_elem.text
                        
                        # Get mirrors
                        mirrors = []
                        for url_elem in root.findall(".//{urn:ietf:params:xml:ns:metalink}url"):
                            if url_elem.text:
                                mirrors.append(url_elem.text)
                        
                        # Get additional metadata from parent XML
                        parent_book = root.find(".//book")
                        if parent_book is not None:
                            # Extract all available metadata
                            metadata = {}
                            
                            # Get attributes first
                            metadata.update({
                                "media_count": parent_book.get("mediaCount", "0"),
                                "article_count": parent_book.get("articleCount", "0"),
                                "favicon": parent_book.get("favicon", ""),
                                "favicon_mime_type": parent_book.get("faviconMimeType", ""),
                                "size": parent_book.get("size", "0")
                            })
                            
                            # Then get child elements
                            for elem in parent_book:
                                tag = elem.tag.split('}')[-1].lower()  # Handle namespaced tags
                                if elem.text:
                                    metadata[tag] = elem.text.strip()
                            
                            # Ensure all fields have defaults
                            metadata.setdefault("title", "")
                            metadata.setdefault("description", "")
                            metadata.setdefault("language", "")
                            metadata.setdefault("creator", "")
                            metadata.setdefault("publisher", "")
                            metadata.setdefault("name", "")
                            metadata.setdefault("tags", "")
                            metadata.setdefault("date", "")
                        else:
                            metadata = {
                                "media_count": "0", "article_count": "0",
                                "favicon": "", "favicon_mime_type": "",
                                "title": "", "description": "",
                                "language": "", "creator": "",
                                "publisher": "", "name": "",
                                "tags": "", "date": "",
                                "size": "0"
                            }
                        
                        self.successful_meta4_downloads += 1
                        if self.successful_meta4_downloads % 25 == 0:
                            log.info("meta4_download.status", 
                                   successful_downloads=self.successful_meta4_downloads)
                        
                        return {
                            "file_name": file_name,
                            "file_size": file_size,
                            "md5_hash": hashes.get("md5", ""),
                            "sha1_hash": hashes.get("sha-1", ""),
                            "sha256_hash": hashes.get("sha-256", ""),
                            "mirrors": mirrors,
                            "meta4_url": url,
                            "media_count": int(metadata.get("media_count", 0)),
                            "article_count": int(metadata.get("article_count", 0)),
                            "favicon": metadata.get("favicon", ""),
                            "favicon_mime_type": metadata.get("favicon_mime_type", ""),
                            "title": metadata.get("title", ""),
                            "description": metadata.get("description", ""),
                            "language": metadata.get("language", ""),
                            "creator": metadata.get("creator", ""),
                            "publisher": metadata.get("publisher", ""),
                            "name": metadata.get("name", ""),
                            "tags": metadata.get("tags", ""),
                            "book_date": metadata.get("date", "")  # Add book_date to returned data
                        }
                        
        except Exception as e:
            log.error("meta4_parse.failed", url=url, error=str(e))
            return {}
    
    async def _update_meta4_files(self):
        """Update all meta4 files in parallel."""
        if self.is_updating_meta4:
            return
            
        self.is_updating_meta4 = True
        self.successful_meta4_downloads = 0
        try:
            # Get library data
            library_root = await self.content_manager._fetch_library_xml()
            if not library_root:
                return
            
            # Get all meta4 URLs and check dates
            books = []
            for book in library_root.findall(".//book"):
                url = book.get('url', '')
                if url.endswith('.meta4'):
                    book_id = book.get('id', '')
                    book_date = book.get('date', '')
                    
                    # Only process if date has changed
                    if self.db.needs_update(book_id, book_date):
                        books.append({
                            'id': book_id,
                            'url': url,
                            'date': book_date
                        })
                        log.info("meta4_update.book_changed",
                                book_id=book_id,
                                date=book_date)
            
            total_files = len(books)
            processed_files = 0
            self.db.update_meta4_download_status(total_files, processed_files)
            
            # Process meta4 files in larger batches
            batch_size = 100  # Increased batch size
            for i in range(0, len(books), batch_size):
                batch = books[i:i+batch_size]
                tasks = []
                
                for book in batch:
                    task = asyncio.create_task(self._parse_meta4_file(book['url']))
                    tasks.append((book['id'], task))
                
                # Wait for batch to complete
                updates = []
                for book_id, task in tasks:
                    try:
                        meta4_data = await task
                        if meta4_data:
                            meta4_data['book_id'] = book_id
                            meta4_data['book_date'] = book['date']
                            updates.append(meta4_data)
                    except Exception as e:
                        log.error("meta4_batch.failed", book_id=book_id, error=str(e))
                
                # Batch update database
                if updates:
                    await self.db.batch_update_meta4_info(updates)
                
                processed_files += len(batch)
                self.db.update_meta4_download_status(total_files, processed_files)
            
            self.db.update_meta4_download_status(total_files, processed_files, True)
            log.info("meta4_update.complete", 
                    total=total_files, 
                    successful=self.successful_meta4_downloads,
                    failed=total_files - self.successful_meta4_downloads)
            
        except Exception as e:
            log.error("meta4_update.failed", error=str(e))
        finally:
            self.is_updating_meta4 = False
    
    async def get_library_xml(self) -> Optional[List[Dict]]:
        """Get the library XML content, using database for all metadata and state."""
        now = datetime.now().timestamp()
        
        # Return cached data if still valid
        if self.library_cache and self.library_cache_time:
            if now - self.library_cache_time < self.cache_ttl:
                return self.library_cache
        
        try:
            # Get all books from database
            books = []
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get books with their meta4 info
                cursor.execute("""
                SELECT b.*, m.file_size, m.md5_hash, m.sha1_hash, m.sha256_hash,
                       m.piece_length, m.last_meta4_update, m.meta4_url, m.id as meta4_id
                FROM books b
                LEFT JOIN meta4_info m ON b.id = m.book_id
                """)
                
                columns = [desc[0] for desc in cursor.description]
                
                for row in cursor.fetchall():
                    try:
                        book_data = dict(zip(columns, row))
                        meta4_id = book_data.pop('meta4_id', None)
                        
                        # Get mirror URLs if meta4 info exists
                        if meta4_id:
                            cursor.execute("""
                            SELECT url FROM mirror_urls
                            WHERE meta4_id = ?
                            ORDER BY priority
                            """, (meta4_id,))
                            book_data['mirrors'] = [row[0] for row in cursor.fetchall()]
                        else:
                            book_data['mirrors'] = []
                        
                        # Parse JSON fields
                        if book_data.get('tags'):
                            book_data['tags'] = json.loads(book_data['tags'])
                        
                        # Map database fields to web interface fields
                        book_data['mediaCount'] = book_data.pop('media_count', 0)
                        book_data['articleCount'] = book_data.pop('article_count', 0)
                        book_data['downloaded'] = book_data.get('download_status') == 'downloaded'
                        
                        books.append(book_data)
                        
                    except Exception as e:
                        log.error("library_parse.book_failed", 
                                book_id=row[0] if row else 'unknown',
                                error=str(e))
                        continue
            
            # Update cache
            self.library_cache = books
            self.library_cache_time = now
            
            return books
            
        except Exception as e:
            log.error("library_fetch.failed", error=str(e))
            return None
    
    async def handle_index(self, request):
        """Handle the index page request."""
        try:
            async with aiofiles.open(os.path.join(os.path.dirname(__file__), 'static/index.html'), 'r') as f:
                content = await f.read()
            return web.Response(text=content, content_type='text/html')
        except Exception as e:
            log.error("index.failed", error=str(e))
            return web.Response(text="Error loading page", status=500)
    
    async def handle_library(self, request):
        """Handle library data request."""
        try:
            books = await self.get_library_xml()
            if not books:
                return web.Response(text="Failed to fetch library data", status=500)
            
            return web.json_response(books)
        except Exception as e:
            log.error("library.failed", error=str(e))
            return web.Response(text="Error fetching library data", status=500)
    
    async def handle_meta4_status(self, request):
        """Handle meta4 download status request."""
        try:
            status = self.db.get_processing_status('meta4_update')
            return web.json_response(status)
        except Exception as e:
            log.error("meta4_status.failed", error=str(e))
            return web.Response(text="Error fetching meta4 status", status=500)
    
    async def handle_queue(self, request):
        """Handle download queue request."""
        try:
            data = await request.json()
            book_ids = data.get('books', [])
            
            if not book_ids:
                return web.Response(text="No books selected", status=400)
            
            # Get library data
            books = await self.get_library_xml()
            if not books:
                return web.Response(text="Failed to fetch library data", status=500)
            
            # Find selected books
            selected_books = [b for b in books if b['id'] in book_ids]
            
            # Queue downloads
            for book in selected_books:
                await self.content_manager.queue_download(book)
                log.info("queue.added_book", 
                        book=book['name'],
                        size=book.get('size', 0))
            
            return web.Response(text=f"Queued {len(selected_books)} books for download")
            
        except Exception as e:
            log.error("queue.failed", error=str(e))
            return web.Response(text="Error queueing downloads", status=500)
    
    async def handle_status(self, request):
        """Handle status request."""
        try:
            # Get queue size safely
            queue_size = self.content_manager.download_queue.qsize()
            status = {
                'downloads': self.content_manager.get_download_status(),
                'queue_size': queue_size,
                'active_downloads': len(self.content_manager.active_downloads)
            }
            return web.json_response(status)
        except Exception as e:
            log.error("status.failed", error=str(e))
            return web.Response(text="Error fetching status", status=500) 
