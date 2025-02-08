#!/usr/bin/env python3
"""
ApocaCache Library Maintainer
Main entry point for the library maintainer service that manages Kiwix content.
"""

import asyncio
import logging
import os
import signal
import sys
import shutil
from typing import Set

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Config
from content_manager import ContentManager
from library_manager import LibraryManager
from web_server import WebServer
from monitoring import setup_monitoring
from database import DatabaseManager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.BoundLogger,
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()

class LibraryMaintainerService:
    """Main service class for the library maintainer."""
    
    def __init__(self):
        self.config = Config()
        self.content_manager = ContentManager(self.config)
        self.library_manager = LibraryManager(self.config)
        self.db_manager = DatabaseManager(self.config.data_dir)
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        log.info("shutdown.signal_received", signal=signum)
        self.running = False
    
    async def _run_update_cycle(self):
        """Run a complete content and library update cycle."""
        try:
            # Update content first
            await self.content_manager.update_content()
            # Then update the library catalog
            await self.library_manager.update_library()
            # Clean up old cache entries
            self.db_manager.cleanup_old_entries(days=30)
            log.info("update_cycle.complete")
        except Exception as e:
            log.error("update_cycle.failed", error=str(e))
    
    async def start(self):
        """Start the library maintainer service."""
        log.info("service.starting")
        self.running = True
        
        # Setup monitoring
        setup_monitoring()
        
        # Schedule content updates
        self.scheduler.add_job(
            self._run_update_cycle,
            'cron',
            **self.config.update_schedule
        )
        
        # Schedule daily database cleanup
        self.scheduler.add_job(
            self.db_manager.cleanup_old_entries,
            'cron',
            hour=3,  # Run at 3 AM
            minute=0,
            kwargs={'days': 30}
        )
        
        self.scheduler.start()
        
        # Initial content update cycle
        await self._run_update_cycle()
        
        # Main service loop
        while self.running:
            await asyncio.sleep(1)
        
        await self.shutdown()
    
    async def shutdown(self):
        """Gracefully shutdown the service."""
        log.info("service.shutting_down")
        self.scheduler.shutdown()
        await self.content_manager.cleanup()
        log.info("service.shutdown_complete")

async def initialize_library_xml(config: Config) -> bool:
    """Initialize library.xml file if it doesn't exist."""
    library_path = os.path.join(config.data_dir, "library.xml")
    old_library_path = os.path.join(config.data_dir, "old", "library.xml")
    
    try:
        # If library.xml doesn't exist but we have an old one, copy it
        if not os.path.exists(library_path) and os.path.exists(old_library_path):
            log.info("library.copying_from_old", 
                    old_path=old_library_path, 
                    new_path=library_path)
            os.makedirs(os.path.dirname(library_path), exist_ok=True)
            shutil.copy2(old_library_path, library_path)
            return True
            
        # If no library file exists, create an empty one
        if not os.path.exists(library_path):
            log.info("library.creating_empty", path=library_path)
            os.makedirs(os.path.dirname(library_path), exist_ok=True)
            with open(library_path, 'w') as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n<library version="20110515">\n</library>')
            return True
            
        return True
        
    except Exception as e:
        log.error("library.init_failed", error=str(e))
        return False

async def main():
    """Main entry point."""
    try:
        # Load configuration
        config = Config()
        
        # Initialize library.xml
        if not await initialize_library_xml(config):
            log.error("startup.library_init_failed")
            sys.exit(1)
        
        # Initialize managers
        content_manager = ContentManager(config)
        library_manager = LibraryManager(config)
        
        # Connect managers
        content_manager.set_library_manager(library_manager)
        
        web_server = WebServer(content_manager, config)
        
        # Pre-fetch library XML and content
        log.info("startup.prefetching_library_xml")
        await content_manager._fetch_library_xml()
        
        # Initial content update
        log.info("startup.initial_content_update")
        await content_manager.update_content(force_update=True)
        
        # Start web server
        await web_server.start()
        log.info("web_server.started")
        
        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
        
        # Start monitoring server
        setup_monitoring()
        
        while True:
            try:
                # Only update library catalog
                await library_manager.update_library()
                
                # Wait for next update
                await asyncio.sleep(config.options.update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("update.failed", error=str(e))
                await asyncio.sleep(60)  # Wait before retry
        
    except Exception as e:
        log.error("startup.failed", error=str(e))
        sys.exit(1)

async def shutdown(sig):
    """Cleanup and shutdown."""
    log.info("shutdown.starting", signal=sig)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    log.info("shutdown.cancel_tasks", count=len(tasks))
    await asyncio.gather(*tasks, return_exceptions=True)
    loop = asyncio.get_running_loop()
    loop.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass 
