"""
Database management for ApocaCache library maintainer.
Handles storage of library and meta4 file information in SQLite.
"""

import os
import sqlite3
import json
from datetime import datetime
import structlog
from typing import Dict, Optional, List, Set

log = structlog.get_logger()

class DatabaseManager:
    """Manages SQLite database for library and meta4 file information."""
    
    def __init__(self, data_dir: str):
        """Initialize database connection."""
        self.db_path = os.path.join(data_dir, "library.db")
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize the database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create books table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY,
                    url TEXT,
                    size INTEGER,
                    media_count INTEGER,
                    article_count INTEGER,
                    favicon TEXT,
                    favicon_mime_type TEXT,
                    title TEXT,
                    description TEXT,
                    language TEXT,
                    creator TEXT,
                    publisher TEXT,
                    name TEXT,
                    tags TEXT,
                    book_date TEXT,
                    last_library_update TEXT,
                    needs_meta4_update BOOLEAN DEFAULT TRUE,
                    download_status TEXT DEFAULT 'not_downloaded',
                    local_path TEXT
                )
                """)
                
                # Create meta4_info table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta4_info (
                    book_id TEXT PRIMARY KEY,
                    mirrors TEXT,
                    md5_hash TEXT,
                    sha1_hash TEXT,
                    sha256_hash TEXT,
                    piece_length INTEGER,
                    file_size INTEGER,
                    last_meta4_update TEXT,
                    meta4_url TEXT,
                    FOREIGN KEY (book_id) REFERENCES books(id)
                )
                """)
                
                # Create processing_status table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    process_type TEXT NOT NULL,
                    total_items INTEGER DEFAULT 0,
                    processed_items INTEGER DEFAULT 0,
                    last_updated TEXT,
                    is_complete BOOLEAN DEFAULT FALSE,
                    error_count INTEGER DEFAULT 0
                )
                """)
                
                conn.commit()
                log.info("database.initialized", path=self.db_path)
                
        except Exception as e:
            log.error("database.init_failed", error=str(e))
            raise
    
    def update_book_from_library(self, book_data: Dict) -> bool:
        """Update or insert book data from library_zim.xml."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if book exists and compare data
                cursor.execute("""
                SELECT size, media_count, article_count, book_date,
                       title, description, language, creator, publisher, name, tags
                FROM books WHERE id = ?
                """, (book_data['id'],))
                
                existing = cursor.fetchone()
                needs_update = True
                
                if existing:
                    # Compare relevant fields to determine if update needed
                    old_size, old_media_count, old_article_count, old_date, \
                    old_title, old_desc, old_lang, old_creator, old_pub, old_name, old_tags = existing
                    needs_update = (
                        old_size != book_data.get('size', 0) or
                        old_media_count != book_data.get('media_count', 0) or
                        old_article_count != book_data.get('article_count', 0) or
                        old_date != book_data.get('book_date', '') or
                        old_title != book_data.get('title', '') or
                        old_desc != book_data.get('description', '') or
                        old_lang != book_data.get('language', '') or
                        old_creator != book_data.get('creator', '') or
                        old_pub != book_data.get('publisher', '') or
                        old_name != book_data.get('name', '') or
                        old_tags != book_data.get('tags', '')
                    )
                
                if needs_update:
                    log.info("database.updating_book",
                            book_id=book_data['id'],
                            title=book_data.get('title', ''),
                            language=book_data.get('language', ''))
                            
                    cursor.execute("""
                    INSERT OR REPLACE INTO books (
                        id, url, size, media_count, article_count,
                        favicon, favicon_mime_type, title, description,
                        language, creator, publisher, name, tags,
                        book_date, last_library_update, needs_meta4_update,
                        download_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_downloaded')
                    """, (
                        book_data['id'],
                        book_data.get('url', ''),
                        book_data.get('size', 0),
                        book_data.get('media_count', 0),
                        book_data.get('article_count', 0),
                        book_data.get('favicon', ''),
                        book_data.get('favicon_mime_type', ''),
                        book_data.get('title', ''),
                        book_data.get('description', ''),
                        book_data.get('language', ''),
                        book_data.get('creator', ''),
                        book_data.get('publisher', ''),
                        book_data.get('name', ''),
                        book_data.get('tags', ''),
                        book_data.get('book_date', ''),
                        datetime.now().isoformat(),
                        True
                    ))
                
                conn.commit()
                return needs_update
                
        except Exception as e:
            log.error("database.update_book_failed",
                     book_id=book_data.get('id', ''),
                     error=str(e))
            return False
    
    def update_meta4_info(self, book_id: str, meta4_data: Dict):
        """Update meta4 information for a book."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert/update meta4 info
                cursor.execute("""
                INSERT OR REPLACE INTO meta4_info (
                    book_id, mirrors, md5_hash, sha1_hash,
                    sha256_hash, piece_length, file_size, last_meta4_update,
                    meta4_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    book_id,
                    json.dumps(meta4_data.get('mirrors', [])),
                    meta4_data.get('md5_hash', ''),
                    meta4_data.get('sha1_hash', ''),
                    meta4_data.get('sha256_hash', ''),
                    meta4_data.get('piece_length', 0),
                    meta4_data.get('file_size', 0),
                    datetime.now().isoformat(),
                    meta4_data.get('meta4_url', '')
                ))
                
                # Mark book as not needing meta4 update
                cursor.execute("""
                UPDATE books 
                SET needs_meta4_update = 0 
                WHERE id = ?
                """, (book_id,))
                
                conn.commit()
                log.info("database.meta4_updated",
                        book_id=book_id)
                
        except Exception as e:
            log.error("database.update_meta4_failed",
                     book_id=book_id,
                     error=str(e))
    
    def get_books_needing_meta4_update(self) -> List[Dict]:
        """Get list of books that need meta4 updates."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT id, url, book_date
                FROM books
                WHERE needs_meta4_update = 1
                """)
                
                return [{
                    'id': row[0],
                    'url': row[1],
                    'date': row[2]
                } for row in cursor.fetchall()]
                
        except Exception as e:
            log.error("database.get_needs_update_failed", error=str(e))
            return []
    
    def get_book_info(self, book_id: str) -> Optional[Dict]:
        """Get complete book information including meta4 data."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get book data
                cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
                book_row = cursor.fetchone()
                if not book_row:
                    return None
                
                # Convert to dict
                columns = [desc[0] for desc in cursor.description]
                book_data = dict(zip(columns, book_row))
                
                # Get meta4 info
                cursor.execute("SELECT * FROM meta4_info WHERE book_id = ?", (book_id,))
                meta4_row = cursor.fetchone()
                if meta4_row:
                    meta4_columns = [desc[0] for desc in cursor.description]
                    meta4_data = dict(zip(meta4_columns, meta4_row))
                    
                    # Parse JSON fields
                    if meta4_data.get('mirrors'):
                        meta4_data['mirrors'] = json.loads(meta4_data['mirrors'])
                    
                    book_data['meta4_info'] = meta4_data
                
                # Parse JSON fields
                if book_data.get('tags'):
                    book_data['tags'] = json.loads(book_data['tags'])
                
                return book_data
                
        except Exception as e:
            log.error("database.get_book_failed",
                     book_id=book_id,
                     error=str(e))
            return None
    
    def update_processing_status(self, process_type: str, total: int, processed: int,
                               is_complete: bool = False, error_count: int = 0):
        """Update processing status for library or meta4 updates."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO processing_status 
                (process_type, total_items, processed_items, 
                 last_updated, is_complete, error_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    process_type,
                    total,
                    processed,
                    datetime.now().isoformat(),
                    is_complete,
                    error_count
                ))
                conn.commit()
                
        except Exception as e:
            log.error("database.status_update_failed",
                     process_type=process_type,
                     error=str(e))
    
    def get_processing_status(self, process_type: str) -> Dict:
        """Get latest processing status for a given type."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT total_items, processed_items, last_updated,
                       is_complete, error_count
                FROM processing_status
                WHERE process_type = ?
                ORDER BY id DESC LIMIT 1
                """, (process_type,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        "total_items": row[0],
                        "processed_items": row[1],
                        "last_updated": row[2],
                        "is_complete": bool(row[3]),
                        "error_count": row[4]
                    }
                return {
                    "total_items": 0,
                    "processed_items": 0,
                    "last_updated": None,
                    "is_complete": False,
                    "error_count": 0
                }
                
        except Exception as e:
            log.error("database.status_get_failed",
                     process_type=process_type,
                     error=str(e))
            return {
                "total_items": 0,
                "processed_items": 0,
                "last_updated": None,
                "is_complete": False,
                "error_count": 0
            }
