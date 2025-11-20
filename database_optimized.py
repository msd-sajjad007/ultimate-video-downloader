"""
database_optimized.py - Enterprise Database Layer with Connection Pooling
"""
import sqlite3
import threading
import queue
from contextlib import contextmanager
from typing import Optional, List, Tuple, Any
from datetime import datetime, timedelta
import json

class DatabaseConnectionPool:
    """Thread-safe database connection pool."""

    def __init__(self, db_path: str, pool_size: int = 5, timeout: int = 30):
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool = queue.Queue(maxsize=pool_size)
        self._active_connections = 0
        self._lock = threading.Lock()

        # Initialize pool
        for _ in range(pool_size):
            self._pool.put(self._create_connection())

    def _create_connection(self) -> sqlite3.Connection:
        """Create optimized database connection."""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=self.timeout,
            isolation_level=None  # Autocommit mode
        )

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        conn.execute("PRAGMA page_size=4096")
        conn.execute("PRAGMA foreign_keys=ON")

        # Set row factory
        conn.row_factory = sqlite3.Row

        return conn

    @contextmanager
    def get_connection(self):
        """Get connection from pool (context manager)."""
        conn = None
        try:
            conn = self._pool.get(timeout=5)
            with self._lock:
                self._active_connections += 1
            yield conn
        finally:
            if conn:
                self._pool.put(conn)
                with self._lock:
                    self._active_connections -= 1

    def close_all(self):
        """Close all connections in pool."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break


class OptimizedDatabaseManager:
    """Enterprise-grade database manager with connection pooling."""

    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool = DatabaseConnectionPool(db_path, pool_size)
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_lock = threading.Lock()
        self._initialize_database()

    def _initialize_database(self):
        """Initialize database schema."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Downloads table with partitioning support
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    site TEXT,
                    quality TEXT,
                    filepath TEXT,
                    filesize INTEGER DEFAULT 0,
                    duration INTEGER DEFAULT 0,
                    download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completion_time INTEGER DEFAULT 0,
                    average_speed REAL DEFAULT 0,
                    status TEXT DEFAULT 'completed',
                    metadata TEXT
                )
            """)

            # Optimized indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_downloads_date 
                ON downloads(download_date DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_downloads_status 
                ON downloads(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_downloads_site 
                ON downloads(site)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_downloads_url_hash 
                ON downloads(url)
            """)

            # Queue table for batch downloads
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS download_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    quality TEXT DEFAULT 'best',
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    retry_count INTEGER DEFAULT 0,
                    last_error TEXT
                )
            """)

            # Statistics table (pre-aggregated)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS download_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_date DATE UNIQUE,
                    total_downloads INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    total_duration INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def add_download(self, url: str, title: str, site: str, quality: str,
                    filepath: str, filesize: int = 0, duration: int = 0,
                    completion_time: int = 0, average_speed: float = 0,
                    metadata: Optional[dict] = None) -> int:
        """Add download with optimized insert."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            metadata_json = json.dumps(metadata) if metadata else None

            cursor.execute("""
                INSERT INTO downloads (
                    url, title, site, quality, filepath, filesize, duration,
                    completion_time, average_speed, status, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
            """, (url, title, site, quality, filepath, filesize, duration,
                  completion_time, average_speed, metadata_json))

            download_id = cursor.lastrowid

            # Update daily statistics
            today = datetime.now().date().isoformat()
            cursor.execute("""
                INSERT INTO download_statistics (stat_date, total_downloads, total_size, total_duration)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(stat_date) DO UPDATE SET
                    total_downloads = total_downloads + 1,
                    total_size = total_size + ?,
                    total_duration = total_duration + ?,
                    updated_at = CURRENT_TIMESTAMP
            """, (today, filesize, duration, filesize, duration))

            conn.commit()

            # Invalidate cache
            self._invalidate_cache()

            return download_id

    def get_download_history(self, limit: int = 100, offset: int = 0) -> List[sqlite3.Row]:
        """Get download history with pagination."""
        cache_key = f"history_{limit}_{offset}"

        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads
                WHERE status = 'completed'
                ORDER BY download_date DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            results = cursor.fetchall()

            # Cache results
            self._add_to_cache(cache_key, results)

            return results

    def get_statistics(self) -> dict:
        """Get aggregated statistics."""
        cache_key = "statistics"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Use pre-aggregated statistics
            cursor.execute("""
                SELECT
                    SUM(total_downloads) as total_downloads,
                    SUM(total_size) as total_size,
                    SUM(total_duration) as total_duration
                FROM download_statistics
            """)
            total = cursor.fetchone()

            # Today's stats
            today = datetime.now().date().isoformat()
            cursor.execute("""
                SELECT total_downloads, total_size
                FROM download_statistics
                WHERE stat_date = ?
            """, (today,))
            today_stats = cursor.fetchone()

            # Week stats
            week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
            cursor.execute("""
                SELECT SUM(total_downloads), SUM(total_size)
                FROM download_statistics
                WHERE stat_date >= ?
            """, (week_ago,))
            week_stats = cursor.fetchone()

            # Top sites
            cursor.execute("""
                SELECT site, COUNT(*) as count
                FROM downloads
                WHERE status = 'completed' AND site IS NOT NULL
                GROUP BY site
                ORDER BY count DESC
                LIMIT 10
            """)
            sites = cursor.fetchall()

            stats = {
                'total_downloads': total[0] or 0,
                'total_size': total[1] or 0,
                'total_duration': total[2] or 0,
                'today_downloads': today_stats[0] if today_stats else 0,
                'today_size': today_stats[1] if today_stats else 0,
                'week_downloads': week_stats[0] if week_stats else 0,
                'week_size': week_stats[1] if week_stats else 0,
                'top_sites': [{'site': row[0], 'count': row[1]} for row in sites]
            }

            self._add_to_cache(cache_key, stats)
            return stats

    def search_downloads(self, query: str) -> List[sqlite3.Row]:
        """Search downloads by query."""
        search = f'%{query}%'
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads 
                WHERE (title LIKE ? OR url LIKE ? OR site LIKE ?) AND status = 'completed'
                ORDER BY download_date DESC LIMIT 100
            """, (search, search, search))
            return cursor.fetchall()

    def clear_history(self):
        """Clear download history."""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM downloads')
            conn.commit()
        self._invalidate_cache()

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        with self._cache_lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if datetime.now().timestamp() - timestamp < self._cache_ttl:
                    return data
                else:
                    del self._cache[key]
        return None

    def _add_to_cache(self, key: str, data: Any):
        """Add item to cache."""
        with self._cache_lock:
            self._cache[key] = (data, datetime.now().timestamp())

    def _invalidate_cache(self):
        """Invalidate all cache."""
        with self._cache_lock:
            self._cache.clear()

    def close(self):
        """Close database connections."""
        self.pool.close_all()
