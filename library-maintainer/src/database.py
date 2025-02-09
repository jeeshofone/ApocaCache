"""
Database management for ApocaCache library maintainer.
Handles caching of meta4 file information in SQLite.
"""

import os
import sqlite3
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
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta4_files (
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
                    book_date TEXT
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
                    mirrors, last_updated, meta4_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        meta4_data["book_id"],
                        meta4_data.get("file_name"),
                        meta4_data.get("file_size", 0),
                        meta4_data.get("md5_hash"),
                        meta4_data.get("sha1_hash"),
                        meta4_data.get("sha256_hash"),
                        mirrors,
                        datetime.now().isoformat(),
                        meta4_data.get("meta4_url")
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
                mirrors, last_updated, meta4_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    book_id,
                    meta4_data.get("file_name"),
                    meta4_data.get("file_size", 0),
                    meta4_data.get("md5_hash"),
                    meta4_data.get("sha1_hash"),
                    meta4_data.get("sha256_hash"),
                    mirrors,
                    datetime.now().isoformat(),
                    meta4_data.get("meta4_url")
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
