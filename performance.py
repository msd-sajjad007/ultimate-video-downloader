"""
performance.py - Performance Optimization Layer
"""
import functools
import hashlib
import pickle
import time
from typing import Any, Callable, Optional
from pathlib import Path
import threading

class MemoryCache:
    """Thread-safe in-memory cache with LRU eviction."""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self._cache = {}
        self._access_times = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        with self._lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    self._access_times[key] = time.time()
                    return data
                else:
                    del self._cache[key]
                    del self._access_times[key]
        return None

    def set(self, key: str, value: Any):
        """Set item in cache."""
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_size:
                # Remove least recently used
                lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]
                del self._cache[lru_key]
                del self._access_times[lru_key]

            self._cache[key] = (value, time.time())
            self._access_times[key] = time.time()

    def clear(self):
        """Clear cache."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()


def memoize(ttl: int = 3600):
    """Memoization decorator with TTL."""
    cache = MemoryCache(ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from arguments
            key_data = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(key_data.encode()).hexdigest()

            # Check cache
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result

        return wrapper
    return decorator


class DownloadQueue:
    """Thread-safe download queue with priority support."""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self._queue = []
        self._active = set()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def add(self, url: str, priority: int = 0, **kwargs):
        """Add download to queue."""
        with self._lock:
            self._queue.append({
                'url': url,
                'priority': priority,
                'metadata': kwargs
            })
            # Sort by priority
            self._queue.sort(key=lambda x: x['priority'], reverse=True)
            self._condition.notify()

    def get_next(self, timeout: Optional[float] = None) -> Optional[dict]:
        """Get next download from queue."""
        with self._condition:
            while len(self._active) >= self.max_concurrent or not self._queue:
                if not self._condition.wait(timeout):
                    return None

            if self._queue:
                item = self._queue.pop(0)
                self._active.add(item['url'])
                return item
            return None

    def complete(self, url: str):
        """Mark download as complete."""
        with self._condition:
            self._active.discard(url)
            self._condition.notify()
