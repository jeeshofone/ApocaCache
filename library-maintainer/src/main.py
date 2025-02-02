#!/usr/bin/env python3
"""
ApocaCache Library Maintainer
Main entry point for the library maintainer service that manages Kiwix content.
"""

import asyncio
import logging
import os
import signal
from typing import Set

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Config
from content_manager import ContentManager
from library_manager import LibraryManager
from monitoring import setup_monitoring

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
    
    async def start(self):
        """Start the library maintainer service."""
        log.info("service.starting")
        self.running = True
        
        # Setup monitoring
        setup_monitoring()
        
        # Schedule content updates
        self.scheduler.add_job(
            self.content_manager.update_content,
            'cron',
            **self.config.update_schedule
        )
        self.scheduler.start()
        
        # Initial content update
        await self.content_manager.update_content()
        
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

def main():
    """Main entry point."""
    service = LibraryMaintainerService()
    
    try:
        asyncio.run(service.start())
    except Exception as e:
        log.error("service.fatal_error", error=str(e), exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 