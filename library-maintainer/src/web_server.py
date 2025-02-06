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
from typing import Dict, List, Optional
from datetime import datetime

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
        
    def setup_routes(self):
        """Setup web server routes."""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/library', self.handle_library)
        self.app.router.add_post('/queue', self.handle_queue)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_static('/static', os.path.join(os.path.dirname(__file__), 'static'))
    
    async def start(self):
        """Start the web server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 3118)
        await site.start()
        log.info("web_server.started", port=3118)
    
    async def get_library_xml(self) -> Optional[List[Dict]]:
        """Get the library XML content, using cache if available."""
        now = datetime.now().timestamp()
        
        # Return cached data if still valid
        if self.library_cache and self.library_cache_time:
            if now - self.library_cache_time < self.cache_ttl:
                return self.library_cache
        
        try:
            # Fetch fresh data
            library_root = await self.content_manager._fetch_library_xml()
            if not library_root:
                return None
            
            # Parse books into a list of dictionaries
            books = []
            for book in library_root.findall(".//book"):
                try:
                    book_data = {
                        'id': book.get('id', ''),
                        'size': int(book.get('size', 0)),
                        'url': book.get('url', ''),
                        'title': book.get('title', ''),
                        'description': book.get('description', ''),
                        'language': book.get('language', ''),
                        'creator': book.get('creator', ''),
                        'publisher': book.get('publisher', ''),
                        'name': book.get('name', ''),
                        'date': book.get('date', ''),
                        'tags': book.get('tags', ''),
                        'favicon': book.get('favicon', ''),
                        'mediaCount': int(book.get('mediaCount', 0)),
                        'articleCount': int(book.get('articleCount', 0))
                    }
                    books.append(book_data)
                except Exception as e:
                    log.error("library_parse.book_failed", error=str(e))
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
            
            return web.Response(text=f"Queued {len(selected_books)} books for download")
            
        except Exception as e:
            log.error("queue.failed", error=str(e))
            return web.Response(text="Error queueing downloads", status=500)
    
    async def handle_status(self, request):
        """Handle status request."""
        try:
            status = {
                'downloads': self.content_manager.get_download_status(),
                'queue_size': len(self.content_manager.download_queue),
                'active_downloads': len(self.content_manager.active_downloads)
            }
            return web.json_response(status)
        except Exception as e:
            log.error("status.failed", error=str(e))
            return web.Response(text="Error fetching status", status=500) 