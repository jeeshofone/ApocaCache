"""
Database management for ApocaCache library maintainer.
Handles caching of meta4 file information in SQLite.
"""

import os
import sqlite3
import json
from datetime import datetime
import structlog
from typing import Dict, Optional, List, Set

log = structlog.get_logger()

class DatabaseManager:
    """Manages SQLite database for meta4 file caching."""
    
    def __init__(self, data_dir: str):
        """Initialize database connection."""
        self.db_path = os.path.join(data_dir, "meta4_cache.db")
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema if not exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create meta4 files table
                # Check if we need to migrate the schema
                cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='meta4_files'
                """)
                
                table_exists = cursor.fetchone() is not None
                
                if table_exists:
                    # Check if we need to add the book_date column
                    cursor.execute("PRAGMA table_info(meta4_files)")
                    columns = {row[1] for row in cursor.fetchall()}
                    
                    if 'book_date' not in columns:
                        log.info("database.adding_book_date_column")
                        cursor.execute("ALTER TABLE meta4_files ADD COLUMN book_date TEXT")
                else:
                    # Create new table with all columns
                    cursor.execute("""
                    CREATE TABLE meta4_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT UNIQUE,
                    file_name TEXT,
                    file_size INTEGER,
                    md5_hash TEXT,
                    sha1_hash TEXT,
                    sha256_hash TEXT,
                    mirrors TEXT,
                    last_updated TIMESTAMP,
                    meta4_url TEXT,
                    book_date TEXT,
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
                    tags TEXT
                )
                """)
                
                # Create meta4 download status table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta4_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_files INTEGER DEFAULT 0,
                    processed_files INTEGER DEFAULT 0,
                    last_updated TIMESTAMP,
                    is_complete BOOLEAN DEFAULT 0
                )
                """)
                
                conn.commit()
                log.info("database.initialized", path=self.db_path)
                
        except Exception as e:
            log.error("database.init_failed", error=str(e))
            raise
    
    async def batch_update_meta4_info(self, updates: List[Dict]):
        """Update multiple meta4 file records in a single transaction."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for meta4_data in updates:
                    mirrors = "|".join(meta4_data.get("mirrors", []))
                    cursor.execute("""
                    INSERT OR REPLACE INTO meta4_files 
                    (book_id, file_name, file_size, md5_hash, sha1_hash, sha256_hash, 
                    mirrors, last_updated, meta4_url, book_date, media_count, article_count,
                    favicon, favicon_mime_type, title, description, language, creator,
                    publisher, name, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        meta4_data["book_id"],
                        meta4_data.get("file_name"),
                        meta4_data.get("file_size", 0),
                        meta4_data.get("md5_hash"),
                        meta4_data.get("sha1_hash"),
                        meta4_data.get("sha256_hash"),
                        mirrors,
                        datetime.now().isoformat(),
                        meta4_data.get("meta4_url"),
                        meta4_data.get("book_date"),
                        meta4_data.get("media_count", 0),
                        meta4_data.get("article_count", 0),
                        meta4_data.get("favicon", ""),
                        meta4_data.get("favicon_mime_type", ""),
                        meta4_data.get("title", ""),
                        meta4_data.get("description", ""),
                        meta4_data.get("language", ""),
                        meta4_data.get("creator", ""),
                        meta4_data.get("publisher", ""),
                        meta4_data.get("name", ""),
                        meta4_data.get("tags", "")
                    ))
                
                conn.commit()
                log.info("database.batch_update_complete", count=len(updates))
                
        except Exception as e:
            log.error("database.batch_update_failed", error=str(e))
    
    async def update_meta4_info(self, book_id: str, meta4_data: Dict):
        """Update or insert meta4 file information."""
        try:
            mirrors = "|".join(meta4_data.get("mirrors", []))
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                INSERT OR REPLACE INTO meta4_files 
                (book_id, file_name, file_size, md5_hash, sha1_hash, sha256_hash,
                mirrors, last_updated, meta4_url, book_date, media_count, article_count,
                favicon, favicon_mime_type, title, description, language, creator,
                publisher, name, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    book_id,
                    meta4_data.get("file_name"),
                    meta4_data.get("file_size", 0),
                    meta4_data.get("md5_hash"),
                    meta4_data.get("sha1_hash"),
                    meta4_data.get("sha256_hash"),
                    mirrors,
                    datetime.now().isoformat(),
                    meta4_data.get("meta4_url"),
                    meta4_data.get("book_date"),
                    meta4_data.get("media_count", 0),
                    meta4_data.get("article_count", 0),
                    meta4_data.get("favicon", ""),
                    meta4_data.get("favicon_mime_type", ""),
                    meta4_data.get("title", ""),
                    meta4_data.get("description", ""),
                    meta4_data.get("language", ""),
                    meta4_data.get("creator", ""),
                    meta4_data.get("publisher", ""),
                    meta4_data.get("name", ""),
                    meta4_data.get("tags", "")
                ))
                
                conn.commit()
                log.info("database.meta4_updated", 
                        book_id=book_id, 
                        file_name=meta4_data.get("file_name"))
                
        except Exception as e:
            log.error("database.update_failed", 
                     book_id=book_id, 
                     error=str(e))
    
    def get_meta4_info(self, book_id: str) -> Optional[Dict]:
        """Get cached meta4 file information."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT file_name, file_size, md5_hash, sha1_hash, sha256_hash, 
                       mirrors, last_updated, meta4_url
                FROM meta4_files
                WHERE book_id = ?
                """, (book_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        "file_name": row[0],
                        "file_size": row[1],
                        "md5_hash": row[2],
                        "sha1_hash": row[3],
                        "sha256_hash": row[4],
                        "mirrors": row[5].split("|") if row[5] else [],
                        "last_updated": row[6],
                        "meta4_url": row[7]
                    }
                return None
                
        except Exception as e:
            log.error("database.get_failed", 
                     book_id=book_id, 
                     error=str(e))
            return None
    
    def get_all_meta4_info(self) -> List[Dict]:
        """Get all cached meta4 file information."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT book_id, file_name, file_size, md5_hash, sha1_hash, 
                       sha256_hash, mirrors, last_updated, meta4_url
                FROM meta4_files
                """)
                
                return [{
                    "book_id": row[0],
                    "file_name": row[1],
                    "file_size": row[2],
                    "md5_hash": row[3],
                    "sha1_hash": row[4],
                    "sha256_hash": row[5],
                    "mirrors": row[6].split("|") if row[6] else [],
                    "last_updated": row[7],
                    "meta4_url": row[8]
                } for row in cursor.fetchall()]
                
        except Exception as e:
            log.error("database.get_all_failed", error=str(e))
            return []
    
    def get_meta4_download_status(self) -> Dict:
        """Get the current meta4 download status."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT total_files, processed_files, last_updated, is_complete
                FROM meta4_status
                ORDER BY id DESC LIMIT 1
                """)
                
                row = cursor.fetchone()
                if row:
                    return {
                        "total_files": row[0],
                        "processed_files": row[1],
                        "last_updated": row[2],
                        "is_complete": bool(row[3])
                    }
                return {
                    "total_files": 0,
                    "processed_files": 0,
                    "last_updated": None,
                    "is_complete": False
                }
                
        except Exception as e:
            log.error("database.status_get_failed", error=str(e))
            return {
                "total_files": 0,
                "processed_files": 0,
                "last_updated": None,
                "is_complete": False
            }
    
    def update_meta4_download_status(self, total: int, processed: int, is_complete: bool = False):
        """Update the meta4 download status."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                INSERT INTO meta4_status 
                (total_files, processed_files, last_updated, is_complete)
                VALUES (?, ?, ?, ?)
                """, (
                    total,
                    processed,
                    datetime.now().isoformat(),
                    is_complete
                ))
                
                conn.commit()
                log.info("database.status_updated",
                        total=total,
                        processed=processed,
                        is_complete=is_complete)
                
        except Exception as e:
            log.error("database.status_update_failed", error=str(e))
    
    def cleanup_old_entries(self, days: int = 30):
        """Remove entries older than specified days."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                DELETE FROM meta4_files
                WHERE last_updated < datetime('now', '-? days')
                """, (days,))
                
                cursor.execute("""
                DELETE FROM meta4_status
                WHERE last_updated < datetime('now', '-? days')
                """, (days,))
                
                conn.commit()
                log.info("database.cleanup_completed", 
                        deleted_rows=cursor.rowcount)
                
        except Exception as e:
            log.error("database.cleanup_failed", error=str(e)) 

    def needs_update(self, book_id: str, new_date: str) -> bool:
        """Check if book needs updating based on date."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT book_date FROM meta4_files
                WHERE book_id = ?
                """, (book_id,))
                
                row = cursor.fetchone()
                if not row:
                    # No previous record, needs update
                    return True
                    
                old_date = row[0]
                if not old_date or old_date != new_date:
                    return True
                    
                return False
                
        except Exception as e:
            log.error("database.date_check_failed", 
                     book_id=book_id, 
                     error=str(e))
            # On error, assume update needed
            return True

    def get_meta4_info(self, book_id: str) -> Optional[Dict]:
        """Get meta4 info for a book from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM meta4_files WHERE book_id = ?',
                    (book_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    # Convert row to dictionary using column names
                    columns = [desc[0] for desc in cursor.description]
                    data = dict(zip(columns, row))
                    
                    # Parse JSON fields
                    if data.get('mirrors'):
                        data['mirrors'] = json.loads(data['mirrors'])
                    if data.get('tags'):
                        data['tags'] = json.loads(data['tags'])
                    
                    return data
                return None
                
        except Exception as e:
            log.error("database.get_meta4_info_failed", 
                     book_id=book_id, 
                     error=str(e))
            return None
    
    def batch_update_meta4_info(self, updates: List[Dict]):
        """Batch update meta4 info for multiple books."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for update in updates:
                    # Convert lists/dicts to JSON strings
                    if 'mirrors' in update:
                        update['mirrors'] = json.dumps(update['mirrors'])
                    if 'tags' in update:
                        update['tags'] = json.dumps(update['tags'])
                    
                    # Set last_updated timestamp
                    update['last_updated'] = datetime.now().isoformat()
                    
                    # Prepare column names and placeholders
                    columns = ', '.join(update.keys())
                    placeholders = ', '.join(['?' for _ in update])
                    
                    # Prepare UPDATE clause
                    update_clause = ', '.join([f"{k} = ?" for k in update.keys()])
                    
                    # Use UPSERT (INSERT OR REPLACE)
                    cursor.execute(f'''
                        INSERT OR REPLACE INTO meta4_files ({columns})
                        VALUES ({placeholders})
                    ''', list(update.values()))
                
                conn.commit()
                log.info("database.batch_update_complete", 
                        updates=len(updates))
                
        except Exception as e:
            log.error("database.batch_update_failed", error=str(e))
            raise
    
    def update_download_status(self, book_id: str, status: str, local_path: Optional[str] = None):
        """Update the download status and local path for a book."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if local_path:
                    cursor.execute('''
                        UPDATE meta4_files 
                        SET download_status = ?, local_path = ?, last_updated = ?
                        WHERE book_id = ?
                    ''', (status, local_path, datetime.now().isoformat(), book_id))
                else:
                    cursor.execute('''
                        UPDATE meta4_files 
                        SET download_status = ?, last_updated = ?
                        WHERE book_id = ?
                    ''', (status, datetime.now().isoformat(), book_id))
                conn.commit()
                
        except Exception as e:
            log.error("database.update_status_failed", 
                     book_id=book_id, 
                     error=str(e))
            raise
    
    def get_all_books(self) -> List[Dict]:
        """Get all books from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM meta4_files')
                
                books = []
                columns = [desc[0] for desc in cursor.description]
                
                for row in cursor.fetchall():
                    book = dict(zip(columns, row))
                    
                    # Parse JSON fields
                    if book.get('mirrors'):
                        book['mirrors'] = json.loads(book['mirrors'])
                    if book.get('tags'):
                        book['tags'] = json.loads(book['tags'])
                    
                    books.append(book)
                
                return books
                
        except Exception as e:
            log.error("database.get_all_books_failed", error=str(e))
            return []
