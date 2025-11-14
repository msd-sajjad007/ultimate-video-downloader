import os
import sys
import subprocess
import threading
from pathlib import Path
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import yt_dlp
from datetime import datetime, timedelta
import json
import platform
import pyperclip
import time
import sqlite3
import re
# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE LOGIC MOVED TO MAIN ENTRY POINT (see bottom of file)
# ═══════════════════════════════════════════════════════════════════════════════

# === Browser capture imports ===
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    sync_playwright = None  # Will lazy-install if missing

# Configure
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ═══════════════════════════════════════════════════════════════════════════════
# MODERN THEME CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class Theme:
    """Ultra-modern color scheme and styling"""
    
    # Background colors - Deep space theme
    BG_PRIMARY = "#0a0e27"       # Deep dark blue
    BG_SECONDARY = "#151a2e"      # Card background
    BG_TERTIARY = "#1e2640"       # Elevated cards
    BG_INPUT = "#252b4a"          # Input fields
    
    # Accent colors
    ACCENT_PRIMARY = "#00d4ff"    # Bright cyan
    ACCENT_SECONDARY = "#667eea"  # Purple
    ACCENT_TERTIARY = "#f093fb"   # Pink
    
    # Status colors
    SUCCESS = "#10b981"           # Green
    ERROR = "#ef4444"             # Red  
    WARNING = "#f59e0b"           # Orange
    INFO = "#3b82f6"              # Blue
    
    # Text colors
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"
    
    # UI elements
    BORDER = "#334155"
    HOVER = "#00b8e6"
    SHADOW = "#000000"
    
    # Fonts
    FONT_TITLE = ("Segoe UI", 28, "bold")
    FONT_SUBTITLE = ("Segoe UI", 16, "bold")
    FONT_BODY = ("Segoe UI", 12)
    FONT_SMALL = ("Segoe UI", 10)
    FONT_BUTTON = ("Segoe UI", 13, "bold")
    
    # Spacing
    PADDING_XLARGE = 30
    PADDING_LARGE = 20
    PADDING_MEDIUM = 15
    PADDING_SMALL = 10
    PADDING_TINY = 5
    
    # Border radius
    RADIUS_LARGE = 20
    RADIUS_MEDIUM = 15
    RADIUS_SMALL = 10
    
    # Sizes
    BUTTON_HEIGHT = 45
    INPUT_HEIGHT = 45
    HEADER_HEIGHT = 80

# ═══════════════════════════════════════════════════════════════════════════════
# BROWSER CAPTURE ENGINE - ENTERPRISE-GRADE (VIDEO-ONLY)
# ═══════════════════════════════════════════════════════════════════════════════

class BrowserCaptureEngine:
    """
    Enterprise-Grade Video Stream Capture Engine
    Captures ONLY video streams (HLS, DASH, MP4, WebM) from browser network traffic.
    Filters out non-video assets aggressively for precision.
    """

    # Video-specific regex patterns
    VIDEO_URL_PATTERNS = [
        r'\.m3u8(?:[?#].*)?$',      # HLS manifests
        r'\.mpd(?:[?#].*)?$',       # DASH manifests
        r'\.mp4(?:[?#].*)?$',       # MP4 videos
        r'\.webm(?:[?#].*)?$',      # WebM videos
        r'\.ts(?:[?#].*)?$',        # MPEG-TS segments
        r'/video/[^\s]*',           # /video/ paths
        r'/stream/[^\s]*',          # /stream/ paths
        r'/hls/[^\s]*',             # HLS paths
        r'/dash/[^\s]*',            # DASH paths
        r'\.m4v(?:[?#].*)?$',       # M4V
        r'\.m4s(?:[?#].*)?$',       # Segments
    ]

    # Valid video content types
    VIDEO_CONTENT_TYPES = [
        'video/mp4', 'video/webm', 'video/x-m4v', 'video/ogg', 'video/x-msvideo',
        'application/x-mpegurl', 'application/vnd.apple.mpegurl',  # HLS
        'application/dash+xml',  # DASH
        'video/mpeg', 'video/quicktime', 'video/x-flv',
    ]

    # Exclude patterns (non-video assets)
    EXCLUDE_PATTERNS = [
        r'\.(jpg|jpeg|png|gif|webp|svg|ico)$',  # Images
        r'\.(js|css|woff|ttf|eot|json|xml)$',   # Scripts, styles, fonts
        r'/api/', r'/ads/', r'/analytics/',    # API calls
        r'blob:',                               # Blob URLs handled separately
        r'/thumbnail/', r'/poster/',
    ]

    def __init__(self, log_fn, on_found):
        self.log = log_fn
        self.on_video_found = on_found  # keep compatibility with existing call sites
        self._stop = False
        self._stopping = False
        self._is_running = False
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self.captured_videos = set()    # Only videos
        self._request_interceptor = None
        self._response_handler = None
        self._video_elements = set()    # Track extracted video srcs

    def _is_video_url(self, url: str, content_type: str, headers: dict) -> bool:
        """Strict video validation using multiple criteria."""
        url_lower = (url or "").lower()

        # Exclude non-video first
        for exclude in self.EXCLUDE_PATTERNS:
            if re.search(exclude, url_lower):
                return False

        # Check URL patterns
        if any(re.search(pattern, url_lower) for pattern in self.VIDEO_URL_PATTERNS):
            return True

        # Check content type
        if any(vt in (content_type or "").lower() for vt in self.VIDEO_CONTENT_TYPES):
            return True

        # Check for range requests (common in video streaming)
        if (headers.get('range') or '').startswith('bytes='):
            return True

        # Size check: Video files are typically >1MB
        try:
            content_length = int(headers.get('content-length', '0'))
            if content_length > 1_000_000:
                return True
        except Exception:
            pass

        return False

    def _extract_video_sources(self):
        """Extract video sources from <video> elements on the page."""
        try:
            videos = self.page.query_selector_all('video')
            for video in videos:
                src = video.get_attribute('src')
                if src and src not in self._video_elements:
                    self._video_elements.add(src)
                    if self._is_video_url(src, '', {}):
                        self.log(f"📹 Extracted from <video> tag: {src[:80]}...")
                        if src not in self.captured_videos:
                            self.captured_videos.add(src)
                            title = self.page.title() or ""
                            current_url = self.page.url
                            self.on_video_found(src, title, current_url)

                # Check <source> children
                sources = video.query_selector_all('source')
                for source in sources:
                    src = source.get_attribute('src')
                    if src and src not in self._video_elements:
                        self._video_elements.add(src)
                        if self._is_video_url(src, '', {}):
                            self.log(f"📹 Extracted from <source> tag: {src[:80]}...")
                            if src not in self.captured_videos:
                                self.captured_videos.add(src)
                                title = self.page.title() or ""
                                current_url = self.page.url
                                self.on_video_found(src, title, current_url)
        except Exception as e:
            self.log(f"⚠️ Video element extraction failed: {e}")

    def _setup_blob_monitor(self):
        """Monitor Blob and MediaSource creation for blob: URLs."""
        try:
            self.page.add_init_script("""
                const originalCreateObjectURL = URL.createObjectURL;
                URL.createObjectURL = function(blob) {
                    try {
                        if (blob && (blob.type || '').startsWith('video/') || (blob.type || '').startsWith('audio/')) {
                            window.__capturedBlobs = window.__capturedBlobs || [];
                            const u = originalCreateObjectURL.call(this, blob);
                            window.__capturedBlobs.push({ url: u, type: blob.type || '', size: blob.size || 0 });
                            return u;
                        }
                    } catch (e) {}
                    return originalCreateObjectURL.apply(this, arguments);
                };

                const originalAddSourceBuffer = MediaSource.prototype.addSourceBuffer;
                MediaSource.prototype.addSourceBuffer = function(type) {
                    try {
                        if ((type || '').startsWith('video/') || (type || '').startsWith('audio/')) {
                            window.__mediaSources = window.__mediaSources || [];
                            window.__mediaSources.push({ type: type });
                        }
                    } catch (e) {}
                    return originalAddSourceBuffer.apply(this, arguments);
                };
            """)

            # Poll for captured blobs periodically
            def poll_blobs():
                try:
                    blobs = self.page.evaluate("window.__capturedBlobs || []")
                    for blob_info in blobs:
                        url = blob_info.get('url') or ''
                        if url and url not in self.captured_videos:
                            self.log(f"🎥 Resolved blob video: {url[:80]} (type: {blob_info.get('type','')})")
                            self.captured_videos.add(url)
                            title = self.page.title() or ""
                            current_url = self.page.url
                            self.on_video_found(url, title, current_url)
                    # Clear to avoid duplicates
                    self.page.evaluate("window.__capturedBlobs = [];")
                except Exception:
                    pass

            import threading as _th
            def blob_poller():
                while not self._stop:
                    poll_blobs()
                    _th.Event().wait(2)

            _th.Thread(target=blob_poller, daemon=True).start()

        except Exception as e:
            self.log(f"⚠️ Blob monitoring setup failed: {e}")

    def _ensure_playwright(self) -> bool:
        """Ensure Playwright is available and configured."""
        global sync_playwright
        if sync_playwright is not None:
            return True

        try:
            from playwright.sync_api import sync_playwright as sp
            sync_playwright = sp
        except ImportError:
            self.log("❌ Playwright module not found. Install with: pip install playwright")
            self.log("💡 Browser capture disabled. Use yt-dlp for downloads.")
            return False

        # Configure for frozen EXE
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.getcwd()
            playwright_driver = os.path.join(base_path, 'playwright', 'driver')
            if os.path.exists(playwright_driver):
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = playwright_driver
                self.log(f"📁 Configured bundled Playwright: {playwright_driver}")
            else:
                self.log("⚠️ Bundled Playwright not found - capture may fail")

        return True

    def start(self, url: str, headless: bool = False, timeout_sec: int = 300) -> bool:
        """Start enterprise video capture session."""
        if self._is_running:
            self.log("⚠️ Capture session already active.")
            return False

        self._is_running = True
        self._stop = False
        self._stopping = False
        self.captured_videos.clear()
        self._video_elements.clear()

        try:
            if not self._ensure_playwright():
                return False

            self._pw = sync_playwright().start()

            # Launch browser with enterprise-grade stealth
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',
                '--no-first-run',
                '--no-service-autorun',
                '--password-store=basic',
            ]

            browser = None
            for channel in ['chrome', 'msedge']:
                try:
                    self.log(f"🚀 Launching via {channel} channel...")
                    browser = self._pw.chromium.launch(
                        headless=headless,
                        channel=channel,
                        args=launch_args,
                    )
                    break
                except Exception:
                    continue

            if not browser:
                self.log("🔄 Falling back to bundled Chromium...")
                browser = self._pw.chromium.launch(headless=headless, args=launch_args)

            self.browser = browser

            # Create stealth context
            self.context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
                locale='en-US',
                timezone_id='America/Los_Angeles',
                ignore_https_errors=True,
                permissions=['clipboard-read', 'clipboard-write'],
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
            )

            # Anti-detection scripts
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters)
                );
            """)

            self.page = self.context.new_page()

            # Event handlers for graceful shutdown
            self.page.on('close', lambda: self._cleanup('page_closed'))
            self.context.on('page', lambda page: page.on('close', lambda: self._cleanup('context_page_closed')))

            # Request interception for proactive video detection
            def request_interceptor(route):
                req_url = (route.request.url or '').lower()
                try:
                    if any(re.search(p, req_url) for p in self.VIDEO_URL_PATTERNS):
                        self.log(f"🔍 Intercepted potential video request: {req_url[:80]}...")
                except Exception:
                    pass
                route.continue_()

            self.page.route('**/*', request_interceptor)

            # Enhanced response handler - ONLY videos
            def response_handler(response):
                if self._stop:
                    return
                try:
                    url = response.url or ''
                    headers = dict(response.headers or {})
                    content_type = headers.get('content-type', '') or ''

                    if self._is_video_url(url, content_type, headers):
                        if url not in self.captured_videos:
                            self.captured_videos.add(url)
                            title = (self.page.title() or "")[:100] or "Untitled Video"
                            page_url = self.page.url
                            self.log(f"🎬 CAPTURED VIDEO STREAM:\nURL: {url}\nType: {content_type}\nSize: {headers.get('content-length', 'Unknown')} bytes")
                            self.on_video_found(url, title, page_url)

                    if len(self.captured_videos) == 0:
                        self._extract_video_sources()
                except Exception as e:
                    self.log(f"⚠️ Response handler error: {e}")

            self._response_handler = response_handler
            self.page.on('response', response_handler)

            # Setup blob monitoring
            self._setup_blob_monitor()

            # Navigate to URL
            self.log("🌐 Navigating to capture target...")
            navigation_success = False
            for strategy in ['networkidle', 'domcontentloaded', 'load']:
                try:
                    self.page.goto(url, wait_until=strategy, timeout=30000)
                    navigation_success = True
                    self.log(f"✅ Navigation complete ({strategy} strategy)")
                    break
                except Exception as e:
                    self.log(f"⚠️ {strategy} strategy failed: {e}")
                    continue

            if not navigation_success:
                self.log("⚠️ All navigation strategies failed - proceeding anyway")
                self.page.goto(url, timeout=10000)

            # Auto-interact to trigger video playback
            try:
                self.page.wait_for_timeout(2000)
                self.page.evaluate("""
                    document.querySelectorAll('video').forEach(v => {
                        try { v.muted = true; v.play().catch(()=>{}); } catch(e) {}
                    });
                    const btn = document.querySelector('[data-testid="play-button"], .play-button, #play');
                    if (btn) { try { btn.click(); } catch(e) {} }
                """)
                self.log("▶️ Auto-play triggered for video elements")
            except Exception as e:
                self.log(f"⚠️ Auto-interaction failed: {e}")

            # Initial video source extraction
            self._extract_video_sources()

            self.log("🚀 Enterprise Capture Engine Active - Play videos to capture streams")
            self.log("💡 Tip: Interact with page normally; videos will be auto-detected")

            import time as _t
            t0 = _t.time()
            while not self._stop and (_t.time() - t0) < timeout_sec:
                try:
                    if self.browser and not self.browser.is_connected():
                        self._stop = True
                        break
                except Exception:
                    pass
                if (_t.time() - t0) % 5 < 0.2:
                    self._extract_video_sources()
                _t.sleep(0.2)

            return True

        except Exception as e:
            self.log(f"❌ Capture engine startup failed: {e}")
            self._cleanup('startup_error')
            return False

        finally:
            self._cleanup('normal_shutdown')

    def stop(self):
        """Graceful shutdown of capture session."""
        self._stopping = True
        self._stop = True
        self.log("🛑 Shutting down capture engine...")
        self._cleanup('user_stop')

    def _cleanup(self, reason: str):
        """Comprehensive cleanup."""
        try:
            if self._request_interceptor:
                self.page.route('**/*', lambda route: route.continue_())
            if self._response_handler:
                try:
                    self.page.remove_listener('response', self._response_handler)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if self.page:
                self.page.close()
        except Exception:
            pass

        try:
            if self.context:
                self.context.close()
        except Exception:
            pass

        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass

        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

        self._is_running = False
        try:
            self.log(f"🔒 Cleanup complete ({reason}) - Captured {len(self.captured_videos)} videos")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE (NO CHANGES)
# ═══════════════════════════════════════════════════════════════════════════════

class DatabaseManager:
    """Optimized database manager"""
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path.home() / ".ultimate_downloader_v9.db"
        
        self.db_path = db_path
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
        
        # Optimize
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA cache_size = -64000")
        
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.create_indexes()
    
    def create_tables(self):
        """Create tables"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                site TEXT,
                quality TEXT,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                duration INTEGER DEFAULT 0,
                download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completion_time INTEGER DEFAULT 0,
                average_speed REAL DEFAULT 0,
                status TEXT DEFAULT 'completed'
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                quality TEXT DEFAULT 'best',
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def create_indexes(self):
        """Create indexes"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_downloads_date ON downloads(download_date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_downloads_site ON downloads(site)",
        ]
        for idx in indexes:
            try:
                self.cursor.execute(idx)
            except:
                pass
        self.conn.commit()
    
    def add_download(self, url, title, site, quality, file_path, file_size=0, duration=0, completion_time=0, avg_speed=0):
        """Add download with debug output"""
        try:
            # Debug output
            print(f"[DB SAVE] Title: {title[:30]} | Size: {file_size/(1024**2):.1f}MB | Duration: {duration}s | Speed: {avg_speed/(1024**2):.1f}MB/s")
            
            self.cursor.execute('''
                INSERT INTO downloads (url, title, site, quality, file_path, file_size, duration, completion_time, average_speed, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, title, site, quality, file_path, file_size, duration, completion_time, avg_speed, 'completed'))
            self.conn.commit()
            
            print(f"[DB SAVE] ✅ Successfully saved to database (ID: {self.cursor.lastrowid})")
            return self.cursor.lastrowid
        except Exception as e:
            print(f"[DB ERROR] ❌ {e}")
            return None

    
    def get_download_history(self, limit=100):
        """Get history"""
        self.cursor.execute('SELECT * FROM downloads WHERE status = "completed" ORDER BY download_date DESC LIMIT ?', (limit,))
        return self.cursor.fetchall()
    
    def search_downloads(self, query):
        """Search"""
        search = f'%{query}%'
        self.cursor.execute('''
            SELECT * FROM downloads 
            WHERE (title LIKE ? OR url LIKE ? OR site LIKE ?) AND status = "completed"
            ORDER BY download_date DESC LIMIT 100
        ''', (search, search, search))
        return self.cursor.fetchall()
    
    def get_statistics(self):
        """Get statistics with PROPER calculations"""
        # Total stats
        self.cursor.execute('''
            SELECT 
                COUNT(*) as total,
                COALESCE(SUM(file_size), 0) as size,
                COALESCE(SUM(duration), 0) as duration,
                COALESCE(SUM(average_speed), 0) as total_speed,
                COUNT(CASE WHEN average_speed > 0 THEN 1 END) as speed_count
            FROM downloads WHERE status = 'completed'
        ''')
        total = self.cursor.fetchone()
        
        # Today
        today = datetime.now().date().isoformat()
        self.cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(file_size), 0)
            FROM downloads WHERE DATE(download_date) = ? AND status = 'completed'
        ''', (today,))
        today_stats = self.cursor.fetchone()
        
        # Week
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        self.cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(file_size), 0)
            FROM downloads WHERE DATE(download_date) >= ? AND status = 'completed'
        ''', (week_ago,))
        week_stats = self.cursor.fetchone()
        
        # Sites
        self.cursor.execute('''
            SELECT site, COUNT(*) as count
            FROM downloads WHERE status = 'completed' AND site IS NOT NULL
            GROUP BY site ORDER BY count DESC LIMIT 10
        ''')
        sites = self.cursor.fetchall()
        
        # Calculate average speed
        avg_speed = (total[3] / total[4]) if total[4] > 0 else 0
        
        return {
            'total_downloads': total[0] or 0,
            'total_size': total[1] or 0,
            'total_duration': total[2] or 0,
            'average_speed': avg_speed,
            'today_downloads': today_stats[0] or 0,
            'today_size': today_stats[1] or 0,
            'week_downloads': week_stats[0] or 0,
            'week_size': week_stats[1] or 0,
            'sites': sites
        }
    
    def add_to_queue(self, url, quality='best', priority=0):
        """Add to queue"""
        try:
            self.cursor.execute('INSERT INTO queue (url, quality, priority) VALUES (?, ?, ?)', (url, quality, priority))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
    
    def get_queue(self):
        """Get queue"""
        self.cursor.execute('SELECT * FROM queue WHERE status = "pending" ORDER BY priority DESC, added_date ASC')
        return self.cursor.fetchall()
    
    def clear_history(self):
        """Clear history"""
        self.cursor.execute('DELETE FROM downloads')
        self.conn.commit()
    
    def get_database_size(self):
        """Get DB size"""
        try:
            return os.path.getsize(self.db_path) / (1024 * 1024)
        except:
            return 0
    
    def close(self):
        """Close"""
        try:
            self.conn.close()
        except:
            pass

# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD MANAGER (NO CHANGES)
# ═══════════════════════════════════════════════════════════════════════════════

class _YDLLogger:
    """Custom yt-dlp logger that handles unusual extension messages"""
    def __init__(self, log_fn):
        self.log = log_fn

    def debug(self, msg):
        # Optional: forward to verbose log
        try:
            txt = str(msg)
            if txt.strip():
                pass  # or: self.log(txt)
        except:
            pass

    def warning(self, msg):
        try:
            self.log(str(msg))
        except:
            pass

    def error(self, msg):
        # Downgrade the "unusual extension" line so it doesn't trigger error popups
        txt = str(msg)
        if "extracted extension" in txt and "unusual" in txt:
            try:
                self.log(f"Note: {txt}")
            except:
                pass
        else:
            try:
                self.log(f"ERROR: {txt}")
            except:
                pass

class DownloadManager:
    """Enhanced download manager"""
    
    def __init__(self, progress_callback=None, log_callback=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.is_cancelled = False
        self.start_time = None
    
    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
    
    def _format_for_quality(self, quality: str) -> str:
        """
        Map GUI quality selection to yt-dlp format string.
        Ensures exact quality matching for user selection.
        """
        if not quality or quality == "best":
            # Best available video + best available audio
            return "bv*+ba/best"
        
        if quality == "audio":
            # Best audio only
            return "bestaudio/best"
        
        # Handle specific quality selection (e.g., "720p", "1080p", "144p")
        if quality.endswith("p"):
            try:
                height = int(quality[:-1])  # Remove 'p' and convert to int
                
                # Format string breakdown:
                # 1. Try exact height with best audio
                # 2. Try height within ±10% tolerance with best audio
                # 3. Fallback to best video near that height
                # 4. Final fallback to best available
                
                # For better quality matching, especially for lower resolutions like 144p
                return f"bv*[height={height}]+ba/bv*[height<={int(height*1.1)}][height>={int(height*0.9)}]+ba/b[height<={int(height*1.1)}]/best"
                
            except (ValueError, IndexError):
                self.log(f"Invalid quality format: {quality}, using best")
                return "bv*+ba/best"
        
        # Default fallback
        return "bv*+ba/best"

    # ✅ Allow UI to cancel an in-flight download
    def cancel(self):
        """Cancel the current download."""
        self.is_cancelled = True
        self.log("🛑 Download cancelled by user")
    
    def progress_hook(self, d):
        if self.is_cancelled:
            raise Exception("Download cancelled by user")
        
        if d['status'] == 'downloading':
            try:
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                percent = (downloaded / total * 100) if total > 0 else 0
                
                if self.progress_callback:
                    self.progress_callback({
                        'status': 'downloading',
                        'percent': percent,
                        'downloaded': downloaded,
                        'total': total,
                        'speed': speed,
                        'eta': eta
                    })
            except:
                pass
        elif d['status'] == 'finished':
            if self.progress_callback:
                self.progress_callback({'status': 'processing', 'percent': 98})
    
    def download(self, url, quality="best", output_path=None, preferred_title=None, referer=None):
        """Download to fixed .mp4/.mp3 with robust cancellation.
        For .php/.asp gateways, use direct HTTP; otherwise yt-dlp."""
        self.is_cancelled = False
        self.start_time = time.time()
        if not output_path:
            output_path = str(Path.home() / "Downloads")
        is_audio = (quality == "audio")
        # Early cancellation guard
        if self.is_cancelled:
            return {"success": False, "error": "Download cancelled"}
        # Early detection: if URL has gateway extensions (.php, .asp, etc), skip yt-dlp entirely
        gateway_extensions = ['.php', '.asp', '.aspx', '.jsp', '.cgi']
        is_gateway = any(ext in url.lower() for ext in gateway_extensions)
        if is_gateway:
            self.log("🌐 Detected gateway URL; using direct HTTP download...")
            chosen_title = self._sanitize_title(preferred_title or self._fallback_title_from_url(url))
            target_ext = ".mp3" if is_audio else ".mp4"
            final_target = os.path.join(output_path, f"{chosen_title}{target_ext}")
            downloaded_file = self._http_download_fallback(url, final_target, referer=referer)
            # Cancellation after HTTP transfer
            if self.is_cancelled:
                self.log("🛑 Download cancelled during HTTP transfer")
                return {"success": False, "error": "Download cancelled"}
            if not downloaded_file or not os.path.exists(downloaded_file):
                self.log("❌ Failed: HTTP download did not produce a file")
                return {"success": False, "error": "HTTP download failed"}
            # Stats and return
            size_bytes = os.path.getsize(downloaded_file)
            elapsed = max(1, int(time.time() - self.start_time))
            avg_speed = size_bytes / elapsed if size_bytes else 0
            self.log(f"✅ Download complete! File: {os.path.basename(downloaded_file)} ({size_bytes/1024/1024:.1f} MB)")
            return {
                "success": True,
                "info": {"title": chosen_title},
                "filesize": size_bytes,
                "duration": 0,
                "completion_time": elapsed,
                "average_speed": avg_speed,
                "final_path": downloaded_file
            }
        # Normal yt-dlp path for non-gateway URLs
        ydl_opts = self._build_ydl_opts(url, quality, output_path, is_audio=is_audio,
                                        preferred_title=preferred_title, referer=referer)
        info = {}
        try:
            # Cancellation before metadata extraction
            if self.is_cancelled:
                return {"success": False, "error": "Download cancelled"}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get("title", "Unknown")
                duration = info.get("duration", 0)
                est_size = info.get("filesize") or info.get("filesize_approx") or 0
                self.log(f"📝 {title[:60]}...")
                if duration:
                    m, s = divmod(int(duration), 60)
                    self.log(f"⏱️ Duration: {m}m {s}s")
                if est_size:
                    self.log(f"📦 Estimated Size: {est_size/1024/1024:.1f} MB")
                # Cancellation before actual download
                if self.is_cancelled:
                    return {"success": False, "error": "Download cancelled"}
                self.log("⬇️ Starting download...")
                result = ydl.extract_info(url, download=True)
            # Post-download cancellation guard
            if self.is_cancelled:
                self.log("🛑 Download cancelled after completion - cleaning up")
                return {"success": False, "error": "Download cancelled"}
            # Resolve path
            downloaded_file = None
            if isinstance(result, dict):
                rdl = result.get("requested_downloads") or []
                if rdl and isinstance(rdl, list):
                    downloaded_file = rdl[0].get("filepath")
            if not downloaded_file:
                downloaded_file = result.get("filepath")
            if not downloaded_file:
                now = time.time()
                recent = []
                try:
                    for fn in os.listdir(output_path):
                        fp = os.path.join(output_path, fn)
                        if os.path.isfile(fp) and now - os.path.getmtime(fp) < 120:
                            recent.append((fp, os.path.getsize(fp)))
                    if recent:
                        downloaded_file, _ = max(recent, key=lambda x: x[1])
                except Exception:
                    pass
        except Exception as e:
            emsg = str(e)
            if self.is_cancelled or "cancel" in emsg.lower():
                self.log("🛑 Download cancelled")
                return {"success": False, "error": "Download cancelled by user"}
            self.log(f"❌ yt-dlp failed: {emsg[:200]}")
            return {"success": False, "error": emsg}
        # Finalize (rename to .mp4/.mp3 if needed)
        try:
            if downloaded_file and os.path.exists(downloaded_file):
                chosen_title = self._sanitize_title(preferred_title or info.get("title") or self._fallback_title_from_url(url))
                finalized = self.finalize_media(downloaded_file, output_path, chosen_title, is_audio=is_audio)
                if finalized:
                    downloaded_file = finalized
        except Exception as fe:
            self.log(f"⚠️ Finalize exception: {fe}")
        # Stats
        size_bytes = os.path.getsize(downloaded_file) if downloaded_file and os.path.exists(downloaded_file) else 0
        if size_bytes:
            self.log(f"✅ Download complete! File: {os.path.basename(downloaded_file)} ({size_bytes/1024/1024:.1f} MB)")
        else:
            self.log("⚠️ File not found after download")
        elapsed = max(1, int(time.time() - self.start_time))
        avg_speed = size_bytes / elapsed if size_bytes else 0
        return {
            "success": bool(size_bytes),
            "info": info,
            "filesize": size_bytes,
            "duration": info.get("duration", 0) if isinstance(info, dict) else 0,
            "completion_time": elapsed,
            "average_speed": avg_speed,
            "final_path": downloaded_file
        }


    def download_for_batch(self, url, quality="best", output_path=None, batch_progress_callback=None, preferred_title=None, referer=None):
        """Download for batch with safe extension handling"""
        self.is_cancelled = False
        self.start_time = time.time()
        if not output_path:
            output_path = str(Path.home() / "Downloads")

        is_audio = (quality == "audio")

        def batch_hook(d):
            if self.is_cancelled:
                raise Exception("Cancelled")
            if d.get("status") == "downloading" and batch_progress_callback:
                try:
                    downloaded = d.get("downloaded_bytes", 0)
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    percent = downloaded / total * 100 if total else 0
                    batch_progress_callback(percent)
                except:
                    pass

        ydl_opts = self._build_ydl_opts(url, quality, output_path, is_audio=is_audio, preferred_title=preferred_title, referer=referer)
        # Override some options for batch mode
        ydl_opts["progress_hooks"] = [batch_hook]
        ydl_opts["quiet"] = True
        ydl_opts["nowarnings"] = True
        if self._looks_unusual_url(url):
            print(f"[BATCH] Note: URL has unusual suffix; forcing .mp4 output")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=True)

            title = None
            duration = 0
            if isinstance(result, dict):
                title = result.get("title", "Unknown")
                duration = result.get("duration", 0)

            downloaded_file = None
            if isinstance(result, dict):
                rdl = result.get("requested_downloads") or []
                if rdl and isinstance(rdl, list):
                    downloaded_file = rdl[0].get("filepath")
                if not downloaded_file:
                    downloaded_file = result.get("filepath")

            actual_filesize = 0
            # Finalize to guaranteed mp4/mp3 with sanitized title
            try:
                chosen_title = preferred_title or title or self._fallback_title_from_url(url)
                chosen_title = self._sanitize_title(chosen_title)
                finalized = self.finalize_media(downloaded_file, output_path, chosen_title, is_audio=is_audio)
                if finalized:
                    downloaded_file = finalized
            except Exception:
                pass

            if downloaded_file and os.path.exists(downloaded_file):
                actual_filesize = os.path.getsize(downloaded_file)
                print(f"[BATCH] Found: {title} {actual_filesize/1024/1024:.1f} MB")
                # Cleanup any unusual leftovers (e.g., .php with same base)
                try:
                    self._cleanup_unusual_leftovers(downloaded_file)
                except Exception:
                    pass
            else:
                # Fallback: recent files in last 2 minutes
                current_time = time.time()
                recent = []
                for fname in os.listdir(output_path):
                    fpath = os.path.join(output_path, fname)
                    if os.path.isfile(fpath) and current_time - os.path.getmtime(fpath) < 120:
                        recent.append((fpath, os.path.getsize(fpath)))
                if recent:
                    downloaded_file, actual_filesize = max(recent, key=lambda x: x[1])

            completion_time = int(time.time() - self.start_time)
            avg_speed = (actual_filesize / completion_time) if completion_time and actual_filesize else 0

            return {
                "success": True,
                "info": result,
                "title": title,
                "filesize": actual_filesize,
                "duration": duration,
                "completion_time": completion_time,
                "average_speed": avg_speed,
                "final_path": downloaded_file,
            }
        except Exception as e:
            msg = str(e)
            if "Invalid argument" in msg and not is_audio:
                # Try salvage remux in batch mode as well
                print("[BATCH] ⚠️ Postprocessing failed, attempting safe remux to MP4...")
                ok, newf = self._salvage_remux_to_mp4(output_path)
                if ok:
                    try:
                        actual_filesize = os.path.getsize(newf)
                    except:
                        actual_filesize = 0
                    # Cleanup any unusual leftovers (e.g., .php with same base)
                    self._cleanup_unusual_leftovers(newf)
                    completion_time = int(time.time() - self.start_time)
                    avg_speed = (actual_filesize / completion_time) if completion_time and actual_filesize else 0
                    return {
                        "success": True,
                        "info": {"filepath": newf},
                        "title": os.path.splitext(os.path.basename(newf))[0],
                        "filesize": actual_filesize,
                        "duration": 0,
                        "completion_time": completion_time,
                        "average_speed": avg_speed,
                    }
            return {"success": False, "error": msg}
    
    
    def _http_download_fallback(self, url: str, dest_path: str, referer: str | None = None) -> str:
        """Stream the file directly when yt-dlp refuses 'unsafe' extension."""
        try:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            # Build headers
            headers = {
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/120.0.0.0 Safari/537.36")
            }
            if referer:
                headers["Referer"] = referer

            import requests
            with requests.get(url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                
                # Get file size if available
                total_size = int(r.headers.get('content-length', 0))
                
                tmp = dest_path + ".part"
                downloaded = 0
                
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                        # Cancellation during HTTP transfer
                        if self.is_cancelled:
                            self.log("🛑 HTTP download cancelled")
                            try:
                                f.close()
                            except Exception:
                                pass
                            try:
                                if os.path.exists(tmp):
                                    os.remove(tmp)
                            except Exception:
                                pass
                            return ""
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # Update progress bar
                            if self.progress_callback and total_size > 0:
                                percent = (downloaded / total_size) * 100
                                speed = 0  # We could calculate this if needed
                                self.progress_callback({
                                    "status": "downloading",
                                    "percent": percent,
                                    "downloaded": downloaded,
                                    "total": total_size,
                                    "speed": speed,
                                    "eta": 0
                                })
                            # Log every 10MB
                            if downloaded % (10 * 1024 * 1024) < (1024 * 1024):
                                self.log(f"📥 Downloaded {downloaded / (1024 * 1024):.1f} MB...")
                
                # Atomically move into place
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                os.replace(tmp, dest_path)
                
                # Final progress update
                if self.progress_callback:
                    self.progress_callback({
                        "status": "finished",
                        "percent": 100
                    })

            return dest_path if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0 else ""
        except Exception as e:
            self.log(f"❌ HTTP fallback failed: {e}")
            return ""



    
    def _looks_unusual_url(self, url: str) -> bool:
        """Check if URL has unusual extensions that might cause problems"""
        u = (url or "").lower()
        return u.endswith((".php", ".asp", ".aspx", ".jsp", ".cgi"))

    def _safe_outtmpl(self, outputpath: str, is_audio: bool, force_mp4: bool) -> str:
        """Create a safe output template that avoids Windows filename issues.
        Keep %(ext)s; yt-dlp will enforce the final extension via final_ext."""
        # Use site's title as filename; yt-dlp will trim via trim_file_name
        return os.path.join(outputpath, "%(title)s.%(ext)s")

    def _get_format_string(self, quality):
        """Get format string"""
        if quality == "audio":
            return 'bestaudio/best'
        elif quality == "best":
            return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        else:
            height = quality.replace('p', '')
            return f'bestvideo[height<={height}][ext=mp4]+bestaudio/bestvideo[height<={height}]+bestaudio/best'
    
    def _fallback_title_from_url(self, url: str) -> str:
        """Derive a reasonable filename stem from a direct media URL."""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            u = urlparse(url)
            q = parse_qs(u.query or "")
            candidate = None
            if "file" in q and q["file"]:
                candidate = os.path.basename(unquote(q["file"][0]))
            if not candidate:
                candidate = os.path.basename(unquote(u.path or "")) or "video"
            name, ext = os.path.splitext(candidate)
            if not name and ext:
                name = ext.lstrip(".")
            return (name or "video").strip()
        except Exception:
            return "video"

    def _sanitize_title(self, name: str) -> str:
        """Sanitize title for Windows-safe filenames and stable FFmpeg processing."""
        if not name:
            return "video"
        # Remove control characters and collapse whitespace
        name = "".join(ch for ch in name if ch >= " ")
        name = " ".join(name.split())
        # Strip trailing dots/spaces not allowed on Windows
        name = name.rstrip(" .")
        # Replace invalid characters
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "_")
        # Avoid reserved device names
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
        }
        if name.upper() in reserved:
            name = f"{name}_"
        # Ensure non-empty and limit length
        return (name or "video")[:150]

    def _build_ydl_opts(self, url, quality, output_path, is_audio=False, preferred_title=None, referer=None):
        """Build yt-dlp options - optimized to avoid FFmpeg merge errors"""
        chosen_title = self._sanitize_title(preferred_title or self._fallback_title_from_url(url))
        target_ext = ".mp3" if is_audio else ".mp4"
        outtmpl = os.path.join(output_path, f"{chosen_title}{target_ext}")

        # Use the new format mapper that respects GUI quality selection
        fmt = self._format_for_quality(quality)

        opts = {
            "logger": _YDLLogger(self.log),
            "outtmpl": outtmpl,
            "format": fmt,
            "quiet": False,
            "nocolor": True,
            "progress_hooks": [self.progress_hook],
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 30,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "force_overwrites": True,
            "nopart": True,
            "compat_opts": ["allow-unsafe-ext"],
            # Force MP4 container to avoid codec issues
            "merge_output_format": "mp4",
            "postprocessor_args": [
                "-c", "copy",  # Copy streams without re-encoding (faster, no quality loss)
                "-movflags", "+faststart"  # Web-optimized
            ],
        }
        
        # Optional cookie file
        cookie_file = Path.home() / "yt_dlp_cookies.txt"
        if cookie_file.exists():
            opts["cookiefile"] = str(cookie_file)
        
        if referer:
            opts["http_headers"] = {"Referer": referer}
        
        return opts




    
    def _is_volatile_direct(self, url: str) -> bool:
        """Detect expiring/gateway direct links prone to 416."""
        u = (url or "").lower()
        return ("rnd=" in u) or ("remote_control.php" in u) or u.endswith(".php") or any(x in u for x in (".asp", ".aspx", ".jsp", ".cgi"))
    
    def _salvage_remux_to_mp4(self, folder: str):
        """
        Attempt remuxing the most recent file in folder to .mp4 with ffmpeg -c copy.
        Returns (success, new_file_path)
        """
        try:
            latest = None
            latest_mtime = -1
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath):
                    mt = os.path.getmtime(fpath)
                    if mt > latest_mtime:
                        latest, latest_mtime = fpath, mt
            if not latest:
                return (False, "")
            base, _ = os.path.splitext(latest)
            out_mp4 = base + ".mp4"
            cmd = ["ffmpeg", "-y", "-i", latest, "-c", "copy", "-movflags", "+faststart", out_mp4]
            p = subprocess.run(cmd, capture_output=True)
            if p.returncode == 0 and os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 0:
                return (True, out_mp4)
            return (False, "")
        except Exception:
            return (False, "")

    def _cleanup_unusual_leftovers(self, final_path: str):
        """Remove gateway leftovers (.php, .asp, etc.) created during this session."""
        try:
            if not final_path:
                return
            folder = os.path.dirname(final_path) or "."
            base, _ = os.path.splitext(final_path)
            exts = (".php", ".asp", ".aspx", ".jsp", ".cgi", ".htm", ".html")
            # Same-base quick cleanup
            for ext in exts:
                candidate = base + ext
                if candidate != final_path and os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                        self.log(f"🧹 Removed leftover: {os.path.basename(candidate)}")
                    except Exception as e:
                        self.log(f"⚠️ Could not remove leftover {os.path.basename(candidate)}: {e}")
            # Session-window cleanup (files created recently)
            cutoff = (self.start_time or time.time()) - 600  # last 10 minutes
            for fname in os.listdir(folder):
                if not fname.lower().endswith(exts):
                    continue
                fpath = os.path.join(folder, fname)
                try:
                    if os.path.isfile(fpath) and os.path.getmtime(fpath) >= cutoff and fpath != final_path:
                        os.remove(fpath)
                        self.log(f"🧹 Removed leftover: {fname}")
                except Exception as e:
                    self.log(f"⚠️ Could not remove leftover {fname}: {e}")
        except Exception:
            pass

    def _uniq_path(self, path: str) -> str:
        """Return a unique file path by adding (n) if needed."""
        try:
            base, ext = os.path.splitext(path)
            i = 1
            final_path = path
            while os.path.exists(final_path):
                final_path = f"{base} ({i}){ext}"
                i += 1
            return final_path
        except Exception:
            return path

def finalize_media(self, input_path: str, output_dir: str, chosen_title: str, is_audio: bool) -> str:
    """Simple rename to Title.mp4/mp3 if the server used a gateway suffix (.php, .asp, ...)."""
    try:
        if not input_path or not os.path.exists(input_path):
            return ""
        cur_dir, cur_name = os.path.dirname(input_path), os.path.basename(input_path)
        base, ext = os.path.splitext(cur_name)
        target_ext = ".mp3" if is_audio else ".mp4"

        # Already correct
        if ext.lower() == target_ext:
            self.log(f"✅ Already correct extension: {cur_name}")
            return input_path

        chosen_title = self._sanitize_title(chosen_title or base or "video")
        new_name = f"{chosen_title}{target_ext}"
        new_path = os.path.join(cur_dir, new_name)

        # Ensure unique
        i = 1
        while os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(input_path):
            new_name = f"{chosen_title} ({i}){target_ext}"
            new_path = os.path.join(cur_dir, new_name)
            i += 1

        os.rename(input_path, new_path)
        self.log(f"✅ Renamed: {cur_name} → {new_name}")
        return new_path
    except Exception as e:
        self.log(f"❌ Rename failed: {e}")
        return input_path


# ═══════════════════════════════════════════════════════════════════════════════
# MODERN GUI CLASS - ULTRA-MODERN EDITION
# ═══════════════════════════════════════════════════════════════════════════════

class UltimateDownloaderModern(ctk.CTk):
    """Ultra-modern video downloader interface"""
    
    def __init__(self):
        super().__init__()
        
        # Window configuration
        self.title("🎬 Ultimate Video Downloader Pro")
        self.geometry("1400x900")
        self.minsize(1300, 850)
        self.configure(fg_color=Theme.BG_PRIMARY)
        
        # State management
        self.is_downloading = False
        self.download_path = str(Path.home() / "Downloads")
        self._log_buffer = []  # Buffer for early log messages
        
        # Managers created later
        self.db = DatabaseManager()
        self.capture_engine = None
        
        # ✅ FIRST: build the UI (this defines update_progress, creates widgets, etc.)
        self.setup_ui()
        
        # ✅ THEN: create DownloadManager
        self.download_manager = DownloadManager(
            progress_callback=self.update_progress,
            log_callback=self.log
        )
        
        # Load stats
        self.load_stats()
     
    def setup_ui(self):
        """Create the ultra-modern interface"""
        
        # Main container
        self.main_container = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        self.main_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Header
        self.create_header()
        
        # Content area (includes tabs AND log)
        self.create_content()

    
    def create_header(self):
        """Create stunning gradient header"""
        
        # Header frame with gradient effect
        header = ctk.CTkFrame(
            self.main_container,
            height=100,
            fg_color=Theme.BG_SECONDARY,
            corner_radius=0
        )
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        # Left side - Logo and title
        left_section = ctk.CTkFrame(header, fg_color="transparent")
        left_section.pack(side="left", fill="y", padx=30)
        
        # Title with gradient effect (simulated with colors)
        title = ctk.CTkLabel(
            left_section,
            text="🎬 Ultimate Video Downloader",
            font=Theme.FONT_TITLE,
            text_color=Theme.ACCENT_PRIMARY
        )
        title.pack(side="left", pady=20)
        
        # Version badge
        version = ctk.CTkLabel(
            left_section,
            text="v2.0 PRO",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY,
            fg_color=Theme.BG_TERTIARY,
            corner_radius=10,
            padx=15,
            pady=5
        )
        version.pack(side="left", padx=15, pady=20)
        
        # Right side - Quick actions
        right_section = ctk.CTkFrame(header, fg_color="transparent")
        right_section.pack(side="right", fill="y", padx=30)
        
        # Settings button
        settings_btn = ctk.CTkButton(
            right_section,
            text="⚙️ Settings",
            width=120,
            height=40,
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            command=self.open_settings
        )
        settings_btn.pack(side="right", padx=5, pady=20)
        
        # Help button
        help_btn = ctk.CTkButton(
            right_section,
            text="❓ Help",
            width=120,
            height=40,
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            command=self.show_help
        )
        help_btn.pack(side="right", padx=5, pady=20)


    def create_content(self):
        """Create main content area with tabs and shared activity log - WITH SCROLLING"""
        
        # Main content frame (container for everything)
        content_frame = ctk.CTkFrame(
            self.main_container,
            fg_color="transparent"
        )
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # ✅ CREATE SCROLLABLE FRAME
        scrollable_frame = ctk.CTkScrollableFrame(
            content_frame,
            fg_color="transparent",
            scrollbar_button_color=Theme.BG_TERTIARY,
            scrollbar_button_hover_color=Theme.HOVER
        )
        scrollable_frame.pack(fill="both", expand=True)
        
        # Tabs container inside scrollable frame
        tabs_container = ctk.CTkFrame(
            scrollable_frame,
            fg_color="transparent"
        )
        tabs_container.pack(fill="both", expand=False, pady=(0, 10))
        
        # Tabview with fixed height
        self.tabview = ctk.CTkTabview(
            tabs_container,
            fg_color=Theme.BG_SECONDARY,
            segmented_button_fg_color=Theme.BG_TERTIARY,
            segmented_button_selected_color=Theme.ACCENT_PRIMARY,
            segmented_button_selected_hover_color=Theme.HOVER,
            segmented_button_unselected_color=Theme.BG_TERTIARY,
            segmented_button_unselected_hover_color=Theme.BG_INPUT,
            corner_radius=Theme.RADIUS_LARGE,
            border_width=0,
            height=500  # Fixed height for tabs
        )
        self.tabview.pack(fill="both", expand=True)
        
        # Add tabs
        self.tab_download = self.tabview.add("📥 Download")
        self.tab_batch = self.tabview.add("📋 Batch")
        self.tab_history = self.tabview.add("📊 History")
        
        # Setup tabs
        self.setup_download_tab()
        self.setup_batch_tab()
        self.setup_history_tab()
        
        # Activity log below tabs (also inside scrollable frame)
        self.create_shared_log(scrollable_frame)

    def create_shared_log(self, parent):
        """Create shared activity log visible on ALL tabs - SCROLLABLE VERSION"""
        
        # Activity log container with increased height
        log_container = ctk.CTkFrame(
            parent,
            fg_color=Theme.BG_SECONDARY,
            corner_radius=Theme.RADIUS_MEDIUM,
            height=200  # Increased to 200px
        )
        log_container.pack(fill="x", pady=(10, 0))
        log_container.pack_propagate(False)
        
        # Header (compact)
        log_header = ctk.CTkFrame(log_container, fg_color="transparent")
        log_header.pack(fill="x", padx=20, pady=(10, 5))
        
        ctk.CTkLabel(
            log_header,
            text="📝 Activity Log",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")
        
        ctk.CTkButton(
            log_header,
            text="🗑️ Clear",
            width=80,
            height=28,
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            corner_radius=6,
            font=Theme.FONT_SMALL,
            command=self.clear_log
        ).pack(side="right")
        
        # Log textbox (scrollable built-in)
        self.log_textbox = ctk.CTkTextbox(
            log_container,
            fg_color=Theme.BG_INPUT,
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY,
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        
        # Enable text widget
        self.log_textbox.configure(state="normal")
        
        # Flush buffer
        if hasattr(self, '_log_buffer'):
            for msg in self._log_buffer:
                try:
                    self.log_textbox.insert("end", msg + "\n")
                except:
                    pass
            self._log_buffer.clear()
        
        # Initial message
        self.log("✅ Ready to download!")
        self.log_textbox.see("end")


    def setup_download_tab(self):
        """Create the main download interface"""
        
        # Main card
        card = ctk.CTkFrame(
            self.tab_download,
            fg_color=Theme.BG_TERTIARY,
            corner_radius=Theme.RADIUS_MEDIUM
        )
        card.pack(fill="both", expand=True, padx=20, pady=20)
        
        # URL Input Section
        url_section = ctk.CTkFrame(card, fg_color="transparent")
        url_section.pack(fill="x", padx=30, pady=(30, 20))
        
        url_label = ctk.CTkLabel(
            url_section,
            text="📎 Video URL",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        url_label.pack(anchor="w", pady=(0, 10))
        
        # URL input with paste button
        url_input_frame = ctk.CTkFrame(url_section, fg_color="transparent")
        url_input_frame.pack(fill="x")
        
        self.url_entry = ctk.CTkEntry(
            url_input_frame,
            height=Theme.INPUT_HEIGHT,
            placeholder_text="https://www.youtube.com/watch?v=...",
            fg_color=Theme.BG_INPUT,
            border_width=2,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_PRIMARY,
            placeholder_text_color=Theme.TEXT_MUTED
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        paste_btn = ctk.CTkButton(
            url_input_frame,
            text="📋 Paste",
            width=100,
            height=Theme.INPUT_HEIGHT,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_SECONDARY,
            border_width=2,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            command=self.paste_url
        )
        paste_btn.pack(side="right")
        
        # Quality Selection
        quality_section = ctk.CTkFrame(card, fg_color="transparent")
        quality_section.pack(fill="x", padx=30, pady=20)
        
        quality_label = ctk.CTkLabel(
            quality_section,
            text="🎯 Quality",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        quality_label.pack(anchor="w", pady=(0, 10))
        
        # Quality buttons in a row - MUST be instance variable for analyze to update
        self.quality_buttons_frame = ctk.CTkFrame(quality_section, fg_color="transparent")
        self.quality_buttons_frame.pack(fill="x")
        
        self.quality_var = tk.StringVar(value="best")
        
        qualities = [
            ("🏆 Best", "best"),
            ("📺 1080p", "1080p"),
            ("🎬 720p", "720p"),
            ("📱 480p", "480p"),
            ("🎵 Audio", "audio")
        ]
        
        for i, (label, value) in enumerate(qualities):
            btn = ctk.CTkRadioButton(
                self.quality_buttons_frame,
                text=label,
                variable=self.quality_var,
                value=value,
                font=Theme.FONT_BODY,
                fg_color=Theme.ACCENT_PRIMARY,
                hover_color=Theme.HOVER,
                border_color=Theme.BORDER,
                text_color=Theme.TEXT_PRIMARY
            )
            btn.pack(side="left", padx=10, pady=5)
        
        # Output Path
        path_section = ctk.CTkFrame(card, fg_color="transparent")
        path_section.pack(fill="x", padx=30, pady=20)
        
        path_label = ctk.CTkLabel(
            path_section,
            text="📁 Save Location",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        path_label.pack(anchor="w", pady=(0, 10))
        
        path_input_frame = ctk.CTkFrame(path_section, fg_color="transparent")
        path_input_frame.pack(fill="x")
        
        self.path_entry = ctk.CTkEntry(
            path_input_frame,
            height=Theme.INPUT_HEIGHT,
            fg_color=Theme.BG_INPUT,
            border_width=2,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_PRIMARY
        )
        self.path_entry.insert(0, str(Path.home() / "Downloads"))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        browse_btn = ctk.CTkButton(
            path_input_frame,
            text="🔍 Browse",
            width=120,
            height=Theme.INPUT_HEIGHT,
            fg_color=Theme.BG_INPUT,
            hover_color=Theme.BG_SECONDARY,
            border_width=2,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            command=self.browse_folder
        )
        browse_btn.pack(side="right")
        
        # Progress Section
        progress_section = ctk.CTkFrame(card, fg_color=Theme.BG_INPUT, corner_radius=Theme.RADIUS_MEDIUM)
        progress_section.pack(fill="x", padx=30, pady=20)
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            progress_section,
            height=20,
            progress_color=Theme.ACCENT_PRIMARY,
            fg_color=Theme.BG_SECONDARY,
            corner_radius=10
        )
        self.progress_bar.pack(fill="x", padx=20, pady=(20, 10))
        self.progress_bar.set(0)
        
        # Status text
        self.status_label = ctk.CTkLabel(
            progress_section,
            text="Ready to download",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY
        )
        self.status_label.pack(pady=(0, 10))
        
        # Speed and ETA
        stats_frame = ctk.CTkFrame(progress_section, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        self.speed_label = ctk.CTkLabel(
            stats_frame,
            text="Speed: 0 MB/s",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        self.speed_label.pack(side="left", padx=10)
        
        self.eta_label = ctk.CTkLabel(
            stats_frame,
            text="ETA: --:--",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        self.eta_label.pack(side="right", padx=10)
        
        # Action Buttons
        button_section = ctk.CTkFrame(card, fg_color="transparent")
        button_section.pack(fill="x", padx=30, pady=(0, 30))
        
        # Download button (main CTA)
        self.download_btn = ctk.CTkButton(
            button_section,
            text="⬇️ Download Video",
            height=55,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color=Theme.HOVER,
            border_width=0,
            corner_radius=Theme.RADIUS_MEDIUM,
            font=Theme.FONT_BUTTON,
            text_color=Theme.TEXT_PRIMARY,
            command=self.start_download
        )
        self.download_btn.pack(fill="x", pady=5)
        
        # Secondary buttons row
        secondary_buttons = ctk.CTkFrame(button_section, fg_color="transparent")
        secondary_buttons.pack(fill="x", pady=5)
        
        self.cancel_btn = ctk.CTkButton(
            secondary_buttons,
            text="⏹️ Cancel",
            height=45,
            fg_color=Theme.ERROR,
            hover_color="#dc2626",
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            state="disabled",
            command=self.cancel_download
        )
        self.cancel_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        analyze_btn = ctk.CTkButton(
            secondary_buttons,
            text="🔍 Analyze",
            height=45,
            fg_color=Theme.INFO,
            hover_color="#2563eb",
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            command=self.analyze_url
        )
        analyze_btn.pack(side="left", fill="x", expand=True, padx=5)
        
        capture_btn = ctk.CTkButton(
            secondary_buttons,
            text="🌐 Browser Capture",
            height=45,
            fg_color=Theme.ACCENT_SECONDARY,
            hover_color="#5568d3",
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            command=self.browser_capture
        )
        capture_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def setup_batch_tab(self):
        """Create batch download interface"""
        
        card = ctk.CTkFrame(
            self.tab_batch,
            fg_color=Theme.BG_TERTIARY,
            corner_radius=Theme.RADIUS_MEDIUM
        )
        card.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title = ctk.CTkLabel(
            card,
            text="📋 Batch Download",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        title.pack(pady=20)
        
        # URL list
        self.batch_textbox = ctk.CTkTextbox(
            card,
            height=300,
            fg_color=Theme.BG_INPUT,
            border_width=2,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_PRIMARY
        )
        self.batch_textbox.pack(fill="both", expand=True, padx=30, pady=20)
        
        # Batch controls
        batch_btn = ctk.CTkButton(
            card,
            text="⬇️ Start Batch Download",
            height=50,
            fg_color=Theme.ACCENT_PRIMARY,
            hover_color=Theme.HOVER,
            corner_radius=Theme.RADIUS_MEDIUM,
            font=Theme.FONT_BUTTON,
            command=self.start_batch_download
        )
        batch_btn.pack(fill="x", padx=30, pady=(0, 30))
    
    def setup_history_tab(self):
        """Create download history interface"""
        
        card = ctk.CTkFrame(
            self.tab_history,
            fg_color=Theme.BG_TERTIARY,
            corner_radius=Theme.RADIUS_MEDIUM
        )
        card.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Stats cards at top
        stats_container = ctk.CTkFrame(card, fg_color="transparent")
        stats_container.pack(fill="x", padx=20, pady=20)
        
        # Total downloads
        self.total_downloads_card = self.create_stat_card(
            stats_container,
            "📊 Total Downloads",
            "0",
            Theme.SUCCESS
        )
        self.total_downloads_card.pack(side="left", fill="x", expand=True, padx=5)
        self.total_downloads_label = self.total_downloads_card.value_label
        
        # Total size
        self.total_size_card = self.create_stat_card(
            stats_container,
            "💾 Total Size",
            "0 GB",
            Theme.INFO
        )
        self.total_size_card.pack(side="left", fill="x", expand=True, padx=5)
        self.total_size_label = self.total_size_card.value_label
        
        # Avg time
        self.avg_time_card = self.create_stat_card(
            stats_container,
            "⏱️ Avg Time",
            "0s",
            Theme.WARNING
        )
        self.avg_time_card.pack(side="left", fill="x", expand=True, padx=5)
        self.avg_time_label = self.avg_time_card.value_label
        
        # History list
        self.history_textbox = ctk.CTkTextbox(
            card,
            fg_color=Theme.BG_INPUT,
            border_width=2,
            border_color=Theme.BORDER,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_PRIMARY
        )
        self.history_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    
    def create_stat_card(self, parent, title, value, color):
        """Create a stat card widget"""
        card = ctk.CTkFrame(
            parent,
            fg_color=Theme.BG_INPUT,
            corner_radius=Theme.RADIUS_SMALL
        )
        
        title_label = ctk.CTkLabel(
            card,
            text=title,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        title_label.pack(pady=(15, 5))
        
        value_label = ctk.CTkLabel(
            card,
            text=value,
            font=("Segoe UI", 20, "bold"),
            text_color=color
        )
        value_label.pack(pady=(0, 15))
        
        # Store reference to card for packing
        card.value_label = value_label
        return card
    
    def create_log_section(self, parent):
        """Create shared activity log visible on ALL tabs"""
        
        # Log container with fixed height
        log_container = ctk.CTkFrame(
            parent,
            fg_color=Theme.BG_SECONDARY,
            corner_radius=Theme.RADIUS_MEDIUM,
            height=140
        )
        log_container.pack(fill="x", pady=(10, 0))
        log_container.pack_propagate(False)
        
        # Header with title and clear button
        log_header = ctk.CTkFrame(log_container, fg_color="transparent", height=40)
        log_header.pack(fill="x", padx=20, pady=(12, 0))
        log_header.pack_propagate(False)
        
        # Title
        log_title = ctk.CTkLabel(
            log_header,
            text="📝 Activity Log",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        log_title.pack(side="left", anchor="w")
        
        # Clear button
        clear_btn = ctk.CTkButton(
            log_header,
            text="🗑️ Clear",
            width=90,
            height=30,
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            corner_radius=8,
            font=Theme.FONT_SMALL,
            command=self.clear_log
        )
        clear_btn.pack(side="right")
        
        # The actual log textbox (shared across all tabs)
        self.log_textbox = ctk.CTkTextbox(
            log_container,
            fg_color=Theme.BG_INPUT,
            border_width=0,
            corner_radius=Theme.RADIUS_SMALL,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY,
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=20, pady=(8, 12))
        
        # Flush buffered logs
        if hasattr(self, '_log_buffer'):
            for msg in self._log_buffer:
                try:
                    self.log_textbox.insert("end", msg)
                except:
                    pass
            self._log_buffer.clear()
        
        # Initial welcome message
        self.log("✅ Application ready! Paste a URL to start.")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def log(self, message):
        """Thread-safe activity logging"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        if hasattr(self, 'log_textbox'):
            try:
                self.log_textbox.configure(state="normal")  # Enable editing
                self.log_textbox.insert("end", log_entry)
                self.log_textbox.see("end")  # Auto-scroll to bottom
            except:
                # Buffer if textbox not ready
                if not hasattr(self, '_log_buffer'):
                    self._log_buffer = []
                self._log_buffer.append(log_entry)
        else:
            # Buffer logs before textbox is created
            if not hasattr(self, '_log_buffer'):
                self._log_buffer = []
            self._log_buffer.append(log_entry)


    def clear_log(self):
        """Clear the activity log"""
        if hasattr(self, 'log_textbox'):
            try:
                self.log_textbox.delete("1.0", "end")
                self.log("📝 Activity log cleared")
            except:
                pass
    
    def paste_url(self):
        """Paste URL from clipboard"""
        try:
            url = pyperclip.paste()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, url)
            self.log("📋 URL pasted from clipboard")
        except Exception as e:
            self.log(f"❌ Failed to paste: {e}")
    
    def browse_folder(self):
        """Browse for output folder"""
        folder = filedialog.askdirectory(initialdir=self.download_path)
        if folder:
            self.download_path = folder
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.log(f"📁 Output folder: {folder}")
    
    def load_stats(self):
        """Load download statistics"""
        try:
            stats = self.db.get_statistics()
            
            # Update stat cards
            total = stats.get('total_downloads', 0)
            size_gb = stats.get('total_size', 0) / (1024**3) if stats.get('total_size') else 0
            
            # Calculate average time from completion_time
            try:
                self.db.cursor.execute('SELECT AVG(completion_time) FROM downloads WHERE status = "completed" AND completion_time > 0')
                avg_time_result = self.db.cursor.fetchone()
                avg_time = int(avg_time_result[0]) if avg_time_result and avg_time_result[0] else 0
            except:
                avg_time = 0
            
            self.total_downloads_label.configure(text=str(total))
            self.total_size_label.configure(text=f"{size_gb:.2f} GB")
            self.avg_time_label.configure(text=f"{avg_time}s")
            
            # Load history
            self.load_history()
            
        except Exception as e:
            self.log(f"⚠️ Failed to load stats: {e}")
    
    def load_history(self):
        """Load download history"""
        try:
            self.history_textbox.delete("1.0", "end")
            
            downloads = self.db.get_download_history(50)
            
            if not downloads:
                self.history_textbox.insert("end", "No download history yet\n")
                return
            
            for dl in downloads:
                # Handle both tuple and dict formats
                if isinstance(dl, tuple):
                    id_, url, title, site, quality, filepath, filesize, duration, date, comp_time, speed, status = dl
                else:
                    id_ = dl.get('id', 0)
                    url = dl.get('url', '')
                    title = dl.get('title', 'Unknown')
                    site = dl.get('site', '')
                    quality = dl.get('quality', '')
                    filepath = dl.get('file_path', '')
                    filesize = dl.get('file_size', 0)
                    duration = dl.get('duration', 0)
                    date = dl.get('download_date', '')
                    comp_time = dl.get('completion_time', 0)
                    speed = dl.get('average_speed', 0)
                    status = dl.get('status', 'completed')
                
                size_mb = filesize / (1024*1024) if filesize else 0
                date_str = str(date).split()[0] if date else "Unknown"
                
                entry = f"📥 {title[:50] if title else 'Unknown'}\n"
                entry += f"   🔗 {url[:60]}...\n"
                entry += f"   📊 {quality} | 💾 {size_mb:.1f}MB | 📅 {date_str}\n\n"
                
                self.history_textbox.insert("end", entry)
        
        except Exception as e:
            self.log(f"⚠️ Failed to load history: {e}")
    
    def update_progress(self, data):
        """Update progress bar and stats"""
        try:
            percent = data.get('percent', 0)
            speed = data.get('speed', 0)
            eta = data.get('eta', 0)
            
            # Update progress bar
            self.progress_bar.set(percent / 100)
            
            # Update status
            self.status_label.configure(
                text=f"Downloading... {percent:.1f}%",
                text_color=Theme.ACCENT_PRIMARY
            )
            
            # Update speed
            if speed:
                speed_mb = speed / (1024 * 1024)
                self.speed_label.configure(text=f"Speed: {speed_mb:.2f} MB/s")
            
            # Update ETA
            if eta:
                minutes, seconds = divmod(int(eta), 60)
                self.eta_label.configure(text=f"ETA: {minutes:02d}:{seconds:02d}")
        
        except Exception as e:
            print(f"Progress update error: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # DOWNLOAD METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def start_download(self):
        """Start single download"""
        if self.is_downloading:
            messagebox.showwarning("Warning", "Download already in progress!")
            return
        
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a video URL!")
            return
        
        quality = self.quality_var.get()
        output_path = self.path_entry.get().strip()
        
        if not output_path:
            output_path = str(Path.home() / "Downloads")
        
        # Reset UI
        self.is_downloading = True
        self.download_btn.configure(state="disabled", fg_color=Theme.TEXT_MUTED)
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        self.status_label.configure(
            text="Starting download...",
            text_color=Theme.INFO
        )
        
        # Reset download manager
        self.download_manager.is_cancelled = False
        
        # Start download thread
        threading.Thread(
            target=self.download_thread,
            args=(url, quality, output_path),
            daemon=True
        ).start()
        
        self.log(f"⬇️ Starting download: {url[:60]}...")
    
    def download_thread(self, url, quality, output_path):
        """Background download thread"""
        try:
            result = self.download_manager.download(url, quality, output_path)
            
            if result['success']:
                info = result.get('info', {})
                title = info.get('title', 'Video')
                site = info.get('extractor', 'Unknown')
                filesize = info.get('filesize', 0) or info.get('file_size', 0)
                duration = info.get('duration', 0)
                comp_time = result.get('completion_time', 0)
                
                # Get file path from result
                filepath = result.get('filepath', output_path)
                if isinstance(info, dict) and 'requested_downloads' in info:
                    if info['requested_downloads']:
                        filepath = info['requested_downloads'][0].get('filepath', output_path)
                
                # Save to database
                self.db.add_download(
                    url=url,
                    title=title,
                    site=site,
                    quality=quality,
                    file_path=filepath,
                    file_size=filesize,
                    duration=duration,
                    completion_time=comp_time,
                    avg_speed=0
                )
                
                # Update UI
                self.after(0, lambda: self.download_complete(True, title))
                self.after(0, self.load_stats)
            
            else:
                error = result.get('error', 'Unknown error')
                self.after(0, lambda: self.download_complete(False, error))
        
        except Exception as e:
            self.after(0, lambda: self.download_complete(False, str(e)))
    
    def download_complete(self, success, message):
        """Handle download completion"""
        self.is_downloading = False
        self.download_btn.configure(state="normal", fg_color=Theme.ACCENT_PRIMARY)
        self.cancel_btn.configure(state="disabled")
        
        if success:
            self.status_label.configure(
                text=f"✅ Downloaded: {message[:40]}",
                text_color=Theme.SUCCESS
            )
            self.progress_bar.set(1.0)
            self.log(f"✅ Download complete: {message}")
            messagebox.showinfo("Success", f"Downloaded successfully!\n{message}")
        else:
            self.status_label.configure(
                text=f"❌ Failed: {message[:40]}",
                text_color=Theme.ERROR
            )
            self.progress_bar.set(0)
            self.log(f"❌ Download failed: {message}")
            
            if "cancelled" not in message.lower():
                messagebox.showerror("Error", f"Download failed:\n{message[:200]}")
    
    def cancel_download(self):
        """Cancel current download"""
        if self.is_downloading:
            self.download_manager.cancel()
            self.status_label.configure(
                text="⏹️ Cancelling...",
                text_color=Theme.WARNING
            )
            self.log("⏹️ Cancelling download...")
    
    def analyze_url(self):
        """Analyze video and update quality buttons"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a URL!")
            return
        
        self.log(f"🔍 Analyzing: {url[:60]}...")
        
        def worker():
            try:
                opts = {'quiet': True, 'no_warnings': True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                
                # Extract heights
                heights = sorted({
                    f.get('height') for f in info.get('formats', [])
                    if f and f.get('vcodec') != 'none' and isinstance(f.get('height'), int)
                }, reverse=True)
                
                # Filter to common resolutions for cleaner UI
                common = [2160, 1440, 1080, 720, 480, 360, 240, 144]
                heights = [h for h in common if h in heights] or heights[:8]
                
                title = info.get('title', 'Unknown')
                duration = info.get('duration') or 0
                m, s = divmod(int(duration), 60)
                
                # ✅ UPDATE GUI ON MAIN THREAD
                self.after(0, lambda: self.create_dynamic_quality_buttons(heights))
                self.after(0, lambda: self.log(f"✅ {title[:60]}"))
                self.after(0, lambda: self.log(f"✅ Detected qualities: {', '.join([f'{h}p' for h in heights[:8]])}"))
                
            except Exception as e:
                msg = str(e)[:200]
                self.after(0, lambda: self.log(f"❌ Analysis failed: {msg}"))
        
        threading.Thread(target=worker, daemon=True).start()

    def create_dynamic_quality_buttons(self, heights):
        """Rebuild quality buttons with detected formats"""
        
        if not hasattr(self, 'quality_buttons_frame'):
            self.log("Quality buttons frame not found")
            return
        
        # Clear existing buttons
        for widget in self.quality_buttons_frame.winfo_children():
            widget.destroy()
        
        if not hasattr(self, 'quality_var'):
            self.quality_var = tk.StringVar(value="best")
        
        # Best option
        ctk.CTkRadioButton(
            self.quality_buttons_frame,
            text="Best",
            variable=self.quality_var,
            value="best",
            font=Theme.FONT_BODY,
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(side="left", padx=10, pady=5)
        
        # Common resolutions - INCLUDE 144p
        common = [2160, 1440, 1080, 720, 480, 360, 240, 144]
        heights = [h for h in common if h in heights] or heights[:10]  # Show up to 10 qualities
        
        # Add detected qualities
        for h in heights:
            ctk.CTkRadioButton(
                self.quality_buttons_frame,
                text=f"{h}p",
                variable=self.quality_var,
                value=f"{h}p",
                font=Theme.FONT_BODY,
                fg_color=Theme.ACCENT_PRIMARY,
                text_color=Theme.TEXT_PRIMARY,
                hover_color=Theme.HOVER
            ).pack(side="left", padx=10, pady=5)
        
        # Audio option
        ctk.CTkRadioButton(
            self.quality_buttons_frame,
            text="Audio",
            variable=self.quality_var,
            value="audio",
            font=Theme.FONT_BODY,
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(side="left", padx=10, pady=5)
        
        self.log(f"Quality buttons updated: {len(heights)} formats detected")

    def browser_capture(self):
        """Start browser capture"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a URL!")
            return
        
        self.log("🌐 Starting browser capture...")
        
        def on_video_found(video_url, title, page_url):
            """Callback when video is captured"""
            self.after(0, lambda: self.url_entry.delete(0, "end"))
            self.after(0, lambda: self.url_entry.insert(0, video_url))
            self.after(0, lambda: self.log(f"🎬 Captured: {video_url[:60]}..."))
            self.after(0, lambda: messagebox.showinfo("Captured!", f"Video stream captured!\n\n{title}"))
        
        def capture_thread():
            try:
                engine = BrowserCaptureEngine(
                    log_fn=lambda msg: self.after(0, lambda: self.log(msg)),
                    on_found=on_video_found
                )
                self.capture_engine = engine
                engine.start(url, headless=False, timeout_sec=300)
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Capture error: {e}"))
                self.after(0, lambda: messagebox.showerror("Error", f"Browser capture failed:\n{str(e)[:200]}"))
        
        threading.Thread(target=capture_thread, daemon=True).start()
    
    def start_batch_download(self):
        """Start batch download"""
        urls_text = self.batch_textbox.get("1.0", "end").strip()
        
        if not urls_text:
            messagebox.showwarning("Warning", "Please enter URLs (one per line)!")
            return
        
        urls = [line.strip() for line in urls_text.split('\n') if line.strip() and 'http' in line]
        
        if not urls:
            messagebox.showwarning("Warning", "No valid URLs found!")
            return
        
        self.log(f"📋 Starting batch download: {len(urls)} videos")
        
        quality = self.quality_var.get()
        output_path = self.path_entry.get().strip() or str(Path.home() / "Downloads")
        
        def batch_thread():
            success_count = 0
            fail_count = 0
            
            for i, url in enumerate(urls, 1):
                if self.download_manager.is_cancelled:
                    break
                
                self.after(0, lambda i=i, total=len(urls): self.log(f"📥 [{i}/{total}] Downloading..."))
                
                try:
                    result = self.download_manager.download(url, quality, output_path)
                    
                    if result['success']:
                        success_count += 1
                        info = result.get('info', {})
                        title = info.get('title', 'Video')
                        filesize = info.get('filesize', 0) or info.get('file_size', 0)
                        duration = info.get('duration', 0)
                        comp_time = result.get('completion_time', 0)
                        
                        filepath = result.get('filepath', output_path)
                        if isinstance(info, dict) and 'requested_downloads' in info:
                            if info['requested_downloads']:
                                filepath = info['requested_downloads'][0].get('filepath', output_path)
                        
                        self.db.add_download(
                            url=url,
                            title=title,
                            site=info.get('extractor', 'Unknown'),
                            quality=quality,
                            file_path=filepath,
                            file_size=filesize,
                            duration=duration,
                            completion_time=comp_time,
                            avg_speed=0
                        )
                        self.after(0, lambda: self.log(f"✅ Success!"))
                    else:
                        fail_count += 1
                        self.after(0, lambda e=result.get('error'): self.log(f"❌ Failed: {e}"))
                
                except Exception as e:
                    fail_count += 1
                    self.after(0, lambda e=e: self.log(f"❌ Error: {e}"))
            
            # Summary
            self.after(0, lambda: self.log(f"\n📊 Batch complete: {success_count} success, {fail_count} failed"))
            self.after(0, lambda: messagebox.showinfo(
                "Batch Complete",
                f"Batch download finished!\n\n✅ Success: {success_count}\n❌ Failed: {fail_count}"
            ))
            self.after(0, self.load_stats)
        
        threading.Thread(target=batch_thread, daemon=True).start()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MENU METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def open_settings(self):
        """Open settings dialog"""
        messagebox.showinfo(
            "Settings",
            "Settings feature coming soon!\n\n"
            "Planned features:\n"
            "- Default quality\n"
            "- Default output path\n"
            "- Theme customization\n"
            "- Advanced options"
        )

    def show_help(self):
        """Show help dialog"""
        help_text = """
    🎬 Ultimate Video Downloader Pro - Help

    📥 Download Tab:
    1. Paste or enter video URL
    2. Select quality
    3. Choose output folder
    4. Click 'Download Video'

    🌐 Browser Capture:
    For sites not supported by yt-dlp:
    1. Enter page URL
    2. Click 'Browser Capture'
    3. Play the video in browser
    4. Stream URL will be captured automatically

    📋 Batch Download:
    1. Go to Batch tab
    2. Enter URLs (one per line)
    3. Click 'Start Batch Download'

    📊 History:
    View all your past downloads and statistics

    ⚙️ Tips:
    - Use 'Analyze' to check video info before downloading
    - Browser Capture works on most video sites
    - Check the log at the bottom for real-time updates
    """
        messagebox.showinfo("Help", help_text)

    def on_closing(self):
        """Handle window close"""
        if self.is_downloading:
            if messagebox.askyesno("Confirm Exit", "Download in progress. Are you sure you want to exit?"):
                self.download_manager.cancel()
                if self.capture_engine:
                    try:
                        self.capture_engine.stop()
                    except:
                        pass
                self.db.close()
                self.destroy()
        else:
            if self.capture_engine:
                try:
                    self.capture_engine.stop()
                except:
                    pass
            self.db.close()
            self.destroy()

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION - WITH STATE SAVING FIX
# ═══════════════════════════════════════════════════════════════════════════════

class UltimateDownloaderV9(ctk.CTk):
    """Ultra-Modern Video Downloader - Production Ready"""
    
    def __init__(self):
        super().__init__()
        
        # Window configuration
        self.title("🎬 Ultimate Video Downloader Pro")
        self.geometry("1400x900")
        self.minsize(1300, 850)
        
        # Configure window
        self.configure(fg_color=Theme.BG_PRIMARY)
        
        # State management
        self.is_downloading = False
        self.download_path = str(Path.home() / "Downloads")
        self._log_buffer = []  # Buffer for early log messages
        
        # Initialize database
        self.db = DatabaseManager()
        self.capture_engine = None
        
        # Setup UI (this creates update_progress method at line 2185)
        self.setup_ui()
        
        # NOW create download manager (after update_progress exists)
        self.download_manager = DownloadManager(
            progress_callback=lambda data: self.update_progress(data),
            log_callback=self.log
        )

        
        # Load stats
        self.load_stats()


    def create_interface(self):
        """Create ultra-modern interface"""
        
        # Modern sidebar with gradient effect
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=Theme.BG_SECONDARY)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        # Logo section with modern styling
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(pady=(Theme.PADDING_XLARGE, Theme.PADDING_MEDIUM))
        
        ctk.CTkLabel(logo_frame, text="🎥", font=ctk.CTkFont(size=56)).pack()
        ctk.CTkLabel(logo_frame, text="ULTIMATE", 
                    font=ctk.CTkFont(size=24, weight="bold"),
                    text_color=Theme.ACCENT_PRIMARY).pack(pady=(5, 0))
        ctk.CTkLabel(logo_frame, text="Video Downloader", 
                    font=ctk.CTkFont(size=12),
                    text_color=Theme.TEXT_SECONDARY).pack()
        ctk.CTkLabel(logo_frame, text="Modern Edition", 
                    font=ctk.CTkFont(size=10),
                    text_color=Theme.TEXT_MUTED).pack()
        
        # Navigation with modern buttons
        nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav_frame.pack(fill="both", expand=True, pady=Theme.PADDING_LARGE, padx=Theme.PADDING_MEDIUM)
        
        nav_items = [
            ("📥", "Download", "download", lambda: self.switch_page(self.show_download_page)),
            ("📋", "Batch", "batch", lambda: self.switch_page(self.show_batch_page)),
            ("📊", "Statistics", "stats", lambda: self.switch_page(self.show_stats_page)),
            ("📚", "History", "history", lambda: self.switch_page(self.show_history_page)),
            ("ℹ️", "About", "about", lambda: self.switch_page(self.show_about_page)),
        ]
        
        self.nav_buttons = {}
        for icon, text, key, command in nav_items:
            btn_frame = ctk.CTkFrame(nav_frame, fg_color="transparent", height=50)
            btn_frame.pack(fill="x", pady=Theme.PADDING_TINY)
            
            btn = ctk.CTkButton(
                btn_frame, 
                text=f"{icon}  {text}", 
                command=command, 
                height=48,
                font=ctk.CTkFont(size=14, weight="normal"), 
                anchor="w",
                fg_color="transparent",
                hover_color=Theme.BG_TERTIARY,
                text_color=Theme.TEXT_SECONDARY,
                corner_radius=Theme.RADIUS_SMALL
            )
            btn.pack(fill="x", padx=Theme.PADDING_SMALL)
            self.nav_buttons[key] = btn
        
        # Status section at bottom
        status_frame = ctk.CTkFrame(self.sidebar, fg_color=Theme.BG_TERTIARY, corner_radius=Theme.RADIUS_SMALL)
        status_frame.pack(side="bottom", pady=Theme.PADDING_LARGE, padx=Theme.PADDING_MEDIUM, fill="x")
        
        db_size = self.db.get_database_size()
        self.db_label = ctk.CTkLabel(
            status_frame, 
            text=f"💾 Database: {db_size:.1f} MB",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_SECONDARY
        )
        self.db_label.pack(pady=Theme.PADDING_SMALL)
        
        # Main content area
        self.main_content = ctk.CTkFrame(self, corner_radius=0, fg_color=Theme.BG_PRIMARY)
        self.main_content.pack(side="right", fill="both", expand=True)
        
        # Show initial page
        self.show_download_page()
    
    # ✅ NEW METHODS FOR STATE SAVING
    
    def switch_page(self, page_func):
        """Switch page and save current state"""
        # Save state before switching
        self.save_download_state()
        self.save_batch_state()
        # Switch to new page
        page_func()
    
    def save_download_state(self):
        """Save download page state"""
        try:
            self.saved_url = self.url_entry.get().strip()
            self.saved_detected_info = self.info_frame.winfo_ismapped()
        except:
            pass
    
    def save_batch_state(self):
        """Save batch page state"""
        try:
            self.saved_batch_urls = self.batch_text.get("1.0", "end").strip()
        except:
            pass
    
    # ✅ REST OF THE CODE STAYS THE SAME - Just need to modify show_download_page and show_batch_page slightly
    
    def show_download_page(self):
        """Modern download page with state restoration"""
        self.clear_content()
        self.highlight_nav("download")
        
        # Scrollable container
        scroll = ctk.CTkScrollableFrame(self.main_content, fg_color=Theme.BG_PRIMARY)
        scroll.pack(fill="both", expand=True, padx=Theme.PADDING_LARGE, pady=Theme.PADDING_LARGE)
        
        # Modern header with gradient effect
        header_card = ctk.CTkFrame(scroll, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.RADIUS_LARGE)
        header_card.pack(fill="x", pady=(0, Theme.PADDING_LARGE))
        
        header_content = ctk.CTkFrame(header_card, fg_color="transparent")
        header_content.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=Theme.PADDING_XLARGE)
        
        ctk.CTkLabel(
            header_content, 
            text="📥 Single Video Download", 
            font=ctk.CTkFont(size=34, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            header_content, 
            text="Dynamic quality detection • Auto MP4 format • 1800+ sites supported",
            font=ctk.CTkFont(size=13),
            text_color=Theme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(8, 0))
        
        # Quick actions bar
        quick_actions = ctk.CTkFrame(scroll, fg_color="transparent")
        quick_actions.pack(fill="x", pady=(0, Theme.PADDING_MEDIUM))
        
        ctk.CTkButton(
            quick_actions, 
            text="📋 Paste", 
            command=self.paste_url, 
            width=130, 
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        ).pack(side="left", padx=(0, Theme.PADDING_SMALL))
        
        ctk.CTkButton(
            quick_actions, 
            text="📂 Open Folder", 
            command=self.open_folder, 
            width=150, 
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        ).pack(side="left", padx=(0, Theme.PADDING_SMALL))
        
        ctk.CTkButton(
            quick_actions, 
            text="➕ Add to Queue", 
            command=self.add_to_queue, 
            width=150, 
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.ACCENT_SECONDARY,
            hover_color=Theme.ACCENT_TERTIARY,
            corner_radius=Theme.RADIUS_SMALL
        ).pack(side="left")
        
        # URL Input Card
        url_card = ctk.CTkFrame(scroll, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.RADIUS_MEDIUM)
        url_card.pack(fill="x", pady=(0, Theme.PADDING_MEDIUM))
        
        ctk.CTkLabel(
            url_card, 
            text="📎 Video URL", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=Theme.PADDING_XLARGE, pady=(Theme.PADDING_XLARGE, Theme.PADDING_SMALL))
        
        url_input_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        url_input_frame.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_XLARGE))
        
        self.url_entry = ctk.CTkEntry(
            url_input_frame, 
            placeholder_text="Paste video URL here...", 
            height=Theme.INPUT_HEIGHT, 
            font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, Theme.PADDING_SMALL))
        self.url_entry.bind("<Return>", lambda e: self.detect_video())
        
        # Restore saved URL
        if self.saved_url:
            self.url_entry.insert(0, self.saved_url)

        # Capture via Browser button
        self.capture_btn = ctk.CTkButton(
            url_input_frame,
            text="🕵️ Capture",
            command=self.start_browser_capture,
            width=160, 
            height=Theme.INPUT_HEIGHT,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        )
        self.capture_btn.pack(side="right", padx=(0, Theme.PADDING_SMALL))
        
        # Analyze button
        detect_btn = ctk.CTkButton(
            url_input_frame, 
            text="🔍 Analyze", 
            command=self.detect_video, 
            width=140, 
            height=Theme.INPUT_HEIGHT,
            font=ctk.CTkFont(size=13, weight="bold"), 
            fg_color=Theme.SUCCESS, 
            hover_color="#059669",
            corner_radius=Theme.RADIUS_SMALL
        )
        detect_btn.pack(side="right")
        
        self.site_label = ctk.CTkLabel(
            url_card, 
            text="", 
            font=ctk.CTkFont(size=12), 
            text_color=Theme.TEXT_SECONDARY
        )
        self.site_label.pack(anchor="w", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_MEDIUM))
        
        # Video Info Card
        self.info_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.RADIUS_MEDIUM)
        
        info_content = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        info_content.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=Theme.PADDING_XLARGE)
        
        self.title_label = ctk.CTkLabel(
            info_content, 
            text="", 
            font=ctk.CTkFont(size=13, weight="bold"), 
            anchor="w", 
            wraplength=1000,
            text_color=Theme.TEXT_PRIMARY
        )
        self.title_label.pack(anchor="w", pady=5)
        
        self.duration_label = ctk.CTkLabel(
            info_content, 
            text="", 
            font=ctk.CTkFont(size=12), 
            anchor="w",
            text_color=Theme.TEXT_SECONDARY
        )
        self.duration_label.pack(anchor="w", pady=3)
        
        self.size_label = ctk.CTkLabel(
            info_content, 
            text="", 
            font=ctk.CTkFont(size=12), 
            anchor="w",
            text_color=Theme.TEXT_SECONDARY
        )
        self.size_label.pack(anchor="w", pady=3)
        
        # Quality Selection Card
        quality_card = ctk.CTkFrame(scroll, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.RADIUS_MEDIUM)
        quality_card.pack(fill="x", pady=(0, Theme.PADDING_MEDIUM))
        
        ctk.CTkLabel(
            quality_card, 
            text="🎬 Quality Selection", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=Theme.PADDING_XLARGE, pady=(Theme.PADDING_XLARGE, Theme.PADDING_SMALL))
        
        self.quality_var = ctk.StringVar(value='best')
        self.quality_buttons_frame = ctk.CTkFrame(quality_card, fg_color="transparent")
        self.quality_buttons_frame.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_XLARGE))
        
        self.create_default_quality_buttons()
        
        # Restore detected info if available
        if self.saved_url and self.saved_detected_info and self.video_info:
            self.after(100, lambda: self._update_info_and_qualities(self.video_info))
        
        # Save Location Card
        path_card = ctk.CTkFrame(scroll, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.RADIUS_MEDIUM)
        path_card.pack(fill="x", pady=(0, Theme.PADDING_MEDIUM))
        
        ctk.CTkLabel(
            path_card, 
            text="💾 Save Location", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=Theme.PADDING_XLARGE, pady=(Theme.PADDING_XLARGE, Theme.PADDING_SMALL))
        
        path_inner = ctk.CTkFrame(path_card, fg_color="transparent")
        path_inner.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_XLARGE))
        
        self.path_entry = ctk.CTkEntry(
            path_inner, 
            height=42, 
            font=ctk.CTkFont(size=13),
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, Theme.PADDING_SMALL))
        self.path_entry.insert(0, self.download_path)
        
        ctk.CTkButton(
            path_inner, 
            text="📁 Browse", 
            command=self.browse_folder, 
            width=130, 
            height=42,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        ).pack(side="right")
        
        # Download Button Card
        btn_card = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_card.pack(fill="x", pady=(0, Theme.PADDING_MEDIUM))
        
        self.download_btn = ctk.CTkButton(
            btn_card, 
            text="⬇️ DOWNLOAD NOW", 
            command=self.start_download,
            height=65, 
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=Theme.ACCENT_PRIMARY, 
            hover_color=Theme.HOVER, 
            corner_radius=Theme.RADIUS_MEDIUM,
            text_color=Theme.BG_PRIMARY
        )
        self.download_btn.pack(side="left", fill="x", expand=True, padx=(0, Theme.PADDING_SMALL))
        
        self.cancel_btn = ctk.CTkButton(
            btn_card, 
            text="🛑 Cancel", 
            command=self.cancel_download,
            height=65, 
            width=160, 
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=Theme.ERROR, 
            hover_color="#dc2626", 
            state="disabled",
            corner_radius=Theme.RADIUS_MEDIUM
        )
        self.cancel_btn.pack(side="right")
        
        # Progress Card
        progress_card = ctk.CTkFrame(scroll, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.RADIUS_MEDIUM)
        progress_card.pack(fill="x")
        
        ctk.CTkLabel(
            progress_card, 
            text="📊 Download Progress", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", padx=Theme.PADDING_XLARGE, pady=(Theme.PADDING_XLARGE, Theme.PADDING_MEDIUM))
        
        self.progress_bar = ctk.CTkProgressBar(
            progress_card, 
            height=32, 
            corner_radius=Theme.RADIUS_SMALL,
            fg_color=Theme.BG_INPUT,
            progress_color=Theme.ACCENT_PRIMARY
        )
        self.progress_bar.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_MEDIUM))
        self.progress_bar.set(0)
        
        # Stats
        stats_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        stats_frame.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_MEDIUM))
        
        self.progress_percent = ctk.CTkLabel(
            stats_frame, 
            text="0%", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.ACCENT_PRIMARY
        )
        self.progress_percent.pack(side="left", padx=(0, 30))
        
        self.speed_label = ctk.CTkLabel(
            stats_frame, 
            text="Speed: 0 MB/s", 
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.speed_label.pack(side="left", padx=(0, 30))
        
        self.eta_label = ctk.CTkLabel(
            stats_frame, 
            text="ETA: --:--", 
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.eta_label.pack(side="left", padx=(0, 30))
        
        self.size_progress_label = ctk.CTkLabel(
            stats_frame, 
            text="0 MB / 0 MB", 
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.size_progress_label.pack(side="left")
        
        self.status_label = ctk.CTkLabel(
            progress_card, 
            text="Ready", 
            font=ctk.CTkFont(size=13), 
            text_color=Theme.TEXT_MUTED
        )
        self.status_label.pack(anchor="w", padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_MEDIUM))
        
        # Console Log
        log_header = ctk.CTkFrame(progress_card, fg_color="transparent")
        log_header.pack(fill="x", padx=Theme.PADDING_XLARGE, pady=(Theme.PADDING_SMALL, Theme.PADDING_SMALL))
        
        ctk.CTkLabel(
            log_header, 
            text="📜 Console Log", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")
        
        ctk.CTkButton(
            log_header, 
            text="🗑️ Clear", 
            command=self.clear_log, 
            width=90, 
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=Theme.BG_TERTIARY,
            hover_color=Theme.BG_INPUT,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        ).pack(side="right")
        
        self.log_text = ctk.CTkTextbox(
            progress_card, 
            height=140, 
            font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color=Theme.BG_INPUT,
            text_color=Theme.TEXT_PRIMARY,
            corner_radius=Theme.RADIUS_SMALL
        )
        self.log_text.pack(fill="both", expand=True, padx=Theme.PADDING_XLARGE, pady=(0, Theme.PADDING_XLARGE))
        
        self.log("✅ System ready • v9.0 Final Edition")
        self.log(f"📁 Save location: {self.download_path}")
        if self.saved_url:
            self.log("✅ Previous URL restored")
        else:
            self.log("💡 Paste URL and click Analyze to detect available qualities")
    
    def create_default_quality_buttons(self):
        """Create default quality buttons with modern styling"""
        for widget in self.quality_buttons_frame.winfo_children():
            widget.destroy()
        
        # Ensure quality_var exists
        if not hasattr(self, 'quality_var'):
            self.quality_var = ctk.StringVar(value='best')
        
        ctk.CTkRadioButton(
            self.quality_buttons_frame, 
            text="🏆 Best", 
            variable=self.quality_var, 
            value="best", 
            font=ctk.CTkFont(size=13),
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(anchor="w", pady=6)
        
        ctk.CTkRadioButton(
            self.quality_buttons_frame, 
            text="📺 1080p", 
            variable=self.quality_var, 
            value="1080p", 
            font=ctk.CTkFont(size=13),
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(anchor="w", pady=6)
        
        ctk.CTkRadioButton(
            self.quality_buttons_frame, 
            text="🎬 720p", 
            variable=self.quality_var, 
            value="720p", 
            font=ctk.CTkFont(size=13),
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(anchor="w", pady=6)
        
        ctk.CTkRadioButton(
            self.quality_buttons_frame, 
            text="📱 480p", 
            variable=self.quality_var, 
            value="480p", 
            font=ctk.CTkFont(size=13),
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(anchor="w", pady=6)
        
        ctk.CTkRadioButton(
            self.quality_buttons_frame, 
            text="🎵 Audio", 
            variable=self.quality_var, 
            value="audio", 
            font=ctk.CTkFont(size=13),
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(anchor="w", pady=6)
        
        ctk.CTkLabel(
            self.quality_buttons_frame, 
            text="▶️ Click 'Analyze' to detect available qualities",
            font=ctk.CTkFont(size=11), 
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", pady=(12, 0))
    
    def create_dynamic_quality_buttons(self, heights):
        """Rebuild quality buttons with detected video formats"""
        # Clear old buttons
        for widget in self.quality_buttons_frame.winfo_children():
            widget.destroy()
        
        # Reset variable
        self.quality_var = tk.StringVar(value="best")
        
        # Best option
        ctk.CTkRadioButton(
            self.quality_buttons_frame,
            text="🏆 Best",
            variable=self.quality_var,
            value="best",
            font=Theme.FONT_BODY,
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(side="left", padx=10, pady=5)
        
        # Detected qualities (top 5)
        for h in heights[:5]:
            ctk.CTkRadioButton(
                self.quality_buttons_frame,
                text=f"📺 {h}p",
                variable=self.quality_var,
                value=f"{h}p",
                font=Theme.FONT_BODY,
                fg_color=Theme.ACCENT_PRIMARY,
                text_color=Theme.TEXT_PRIMARY,
                hover_color=Theme.HOVER
            ).pack(side="left", padx=10, pady=5)
        
        # Audio option
        ctk.CTkRadioButton(
            self.quality_buttons_frame,
            text="🎵 Audio",
            variable=self.quality_var,
            value="audio",
            font=Theme.FONT_BODY,
            fg_color=Theme.ACCENT_PRIMARY,
            text_color=Theme.TEXT_PRIMARY,
            hover_color=Theme.HOVER
        ).pack(side="left", padx=10, pady=5)
        
        self.log(f"✅ Updated quality buttons: {len(heights)} formats detected")

    def show_batch_page(self):
        """Batch page - WITH STATE RESTORATION"""
        self.clear_content()
        self.highlight_nav("batch")
        
        scroll = ctk.CTkScrollableFrame(self.main_content)
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(header, text="📋 Batch Download", font=ctk.CTkFont(size=32, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text="Download multiple videos • Real-time progress • Database logging",
                    font=ctk.CTkFont(size=13), text_color="gray").pack(anchor="w", pady=(5, 0))
        
        # URL List
        list_frame = ctk.CTkFrame(scroll)
        list_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        list_header = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_header.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(list_header, text="📝 URL List", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        
        self.url_count_label = ctk.CTkLabel(list_header, text="0 URLs", font=ctk.CTkFont(size=12), text_color="gray")
        self.url_count_label.pack(side="right")
        
        self.batch_text = ctk.CTkTextbox(list_frame, height=300, font=ctk.CTkFont(size=12))
        self.batch_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.batch_text.bind("<KeyRelease>", self.update_url_count)
        
        # ✅ RESTORE saved batch URLs
        if self.saved_batch_urls:
            self.batch_text.insert("1.0", self.saved_batch_urls)
            self.update_url_count()
        
        # Controls
        controls = ctk.CTkFrame(scroll, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 15))
        
        ctk.CTkButton(controls, text="📂 Load File", command=self.load_batch_file, width=140, height=42).pack(side="left", padx=(0, 8))
        ctk.CTkButton(controls, text="📋 Paste", command=self.paste_batch_urls, width=120, height=42).pack(side="left", padx=(0, 8))
        ctk.CTkButton(controls, text="🗑️ Clear", command=lambda: self.batch_text.delete("1.0", "end"), 
                     width=120, height=42, fg_color="#dc2626", hover_color="#991b1b").pack(side="left")
        
        # Quality
        quality_frame = ctk.CTkFrame(scroll)
        quality_frame.pack(fill="x", pady=(0, 15))
        
        quality_inner = ctk.CTkFrame(quality_frame, fg_color="transparent")
        quality_inner.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(quality_inner, text="🎬 Quality:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 15))
        
        self.batch_quality_var = ctk.StringVar(value="best")
        for quality in ["best", "1080p", "720p", "480p", "audio"]:
            ctk.CTkRadioButton(quality_inner, text=quality, variable=self.batch_quality_var, value=quality).pack(side="left", padx=8)
        
        # Download button
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 15))
        
        self.batch_download_btn = ctk.CTkButton(btn_frame, text="⬇️ DOWNLOAD ALL", command=self.start_batch_download,
                                                height=65, font=ctk.CTkFont(size=20, weight="bold"),
                                                fg_color="#2563eb", hover_color="#1d4ed8", corner_radius=12)
        self.batch_download_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.batch_cancel_btn = ctk.CTkButton(btn_frame, text="🛑 Stop", command=self.cancel_batch,
                                              height=65, width=150, font=ctk.CTkFont(size=16, weight="bold"),
                                              fg_color="#dc2626", hover_color="#991b1b", state="disabled")
        self.batch_cancel_btn.pack(side="right")
        
        # Progress section
        progress_frame = ctk.CTkFrame(scroll)
        progress_frame.pack(fill="x", pady=(0, 0))
        
        ctk.CTkLabel(progress_frame, text="📊 Batch Progress", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=20, pady=(20, 12))
        
        self.batch_progress_label = ctk.CTkLabel(progress_frame, text="Ready to download", font=ctk.CTkFont(size=13), text_color="gray")
        self.batch_progress_label.pack(anchor="w", padx=20, pady=(0, 8))
        
        # Current video progress bar
        current_video_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        current_video_frame.pack(fill="x", padx=20, pady=(0, 12))
        
        self.batch_current_label = ctk.CTkLabel(current_video_frame, text="Current video: --", 
                                                font=ctk.CTkFont(size=12), text_color="gray")
        self.batch_current_label.pack(anchor="w", pady=(0, 5))
        
        self.batch_current_progress = ctk.CTkProgressBar(current_video_frame, height=20, corner_radius=10)
        self.batch_current_progress.pack(fill="x", pady=(0, 5))
        self.batch_current_progress.set(0)
        
        self.batch_current_percent = ctk.CTkLabel(current_video_frame, text="0%", font=ctk.CTkFont(size=11))
        self.batch_current_percent.pack(anchor="w")
        
        # Overall batch progress bar
        overall_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        overall_frame.pack(fill="x", padx=20, pady=(0, 12))
        
        ctk.CTkLabel(overall_frame, text="Overall Progress:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 5))
        
        self.batch_overall_progress = ctk.CTkProgressBar(overall_frame, height=25, corner_radius=12)
        self.batch_overall_progress.pack(fill="x", pady=(0, 5))
        self.batch_overall_progress.set(0)
        
        self.batch_overall_label = ctk.CTkLabel(overall_frame, text="0 / 0 videos", font=ctk.CTkFont(size=12))
        self.batch_overall_label.pack(anchor="w")
        
        # Console log
        log_header = ctk.CTkFrame(progress_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=20, pady=(10, 8))
        
        ctk.CTkLabel(log_header, text="📜 Console Log", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(log_header, text="🗑️ Clear", command=self.clear_batch_log, width=80, height=28).pack(side="right")
        
        self.batch_log_text = ctk.CTkTextbox(progress_frame, height=200, font=ctk.CTkFont(size=11, family="Consolas"))
        self.batch_log_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        if self.saved_batch_urls:
            self.batch_log_message("✅ Previous URLs restored")
    
    # ✅ ALL OTHER METHODS STAY EXACTLY THE SAME - no changes needed
    # (Including show_stats_page, show_history_page, show_about_page, all utility methods, etc.)
    # I'm including the rest for completeness:
    
    def show_stats_page(self):
        """Statistics page - FIXED display"""
        self.clear_content()
        self.highlight_nav("stats")
        
        scroll = ctk.CTkScrollableFrame(self.main_content)
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))
        
        ctk.CTkLabel(header, text="📊 Download Statistics", font=ctk.CTkFont(size=32, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text="Smart display: seconds → minutes → hours | bytes → KB → MB → GB",
                    font=ctk.CTkFont(size=13), text_color="gray").pack(anchor="w", pady=(5, 0))
        
        # Get stats
        stats = self.db.get_statistics()
        
        # Debug output
        print(f"\n[STATS DEBUG]")
        print(f"Total downloads: {stats['total_downloads']}")
        print(f"Total size (bytes): {stats['total_size']}")
        print(f"Total duration (seconds): {stats['total_duration']}")
        print(f"Average speed (bytes/s): {stats['average_speed']}\n")
        
        # Cards
        cards = ctk.CTkFrame(scroll, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 25))
        
        # Card 1: Total Downloads
        card1 = ctk.CTkFrame(cards)
        card1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(card1, text="📥", font=ctk.CTkFont(size=50)).pack(pady=(30, 10))
        ctk.CTkLabel(card1, text=str(stats['total_downloads']), font=ctk.CTkFont(size=42, weight="bold")).pack(pady=8)
        ctk.CTkLabel(card1, text="Total Downloads", font=ctk.CTkFont(size=14), text_color="gray").pack(pady=(0, 10))
        ctk.CTkLabel(card1, text=f"📅 Today: {stats['today_downloads']}", font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 20))
        
        # Card 2: Total Size - FIXED with smart display
        card2 = ctk.CTkFrame(cards)
        card2.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        total_bytes = stats['total_size']
        
        # Smart size display
        if total_bytes >= 1024**3:  # >= 1 GB
            size_display = f"{total_bytes / (1024**3):.2f} GB"
            size_font = 36
        elif total_bytes >= 1024**2:  # >= 1 MB
            size_display = f"{total_bytes / (1024**2):.0f} MB"
            size_font = 38
        elif total_bytes >= 1024:  # >= 1 KB
            size_display = f"{total_bytes / 1024:.0f} KB"
            size_font = 40
        else:
            size_display = f"{total_bytes} B" if total_bytes > 0 else "0 B"
            size_font = 42
        
        ctk.CTkLabel(card2, text="💾", font=ctk.CTkFont(size=50)).pack(pady=(30, 10))
        ctk.CTkLabel(card2, text=size_display, font=ctk.CTkFont(size=size_font, weight="bold")).pack(pady=8)
        ctk.CTkLabel(card2, text="Total Size", font=ctk.CTkFont(size=14), text_color="gray").pack(pady=(0, 10))
        
        # Today's size
        today_bytes = stats['today_size']
        if today_bytes >= 1024**3:
            today_display = f"{today_bytes / (1024**3):.2f} GB"
        elif today_bytes >= 1024**2:
            today_display = f"{today_bytes / (1024**2):.0f} MB"
        elif today_bytes >= 1024:
            today_display = f"{today_bytes / 1024:.0f} KB"
        else:
            today_display = f"{today_bytes} B" if today_bytes > 0 else "0 B"
        
        ctk.CTkLabel(card2, text=f"📅 Today: {today_display}", font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 20))
        
        # Card 3: Duration - FIXED with smart display (seconds → minutes → hours)
        card3 = ctk.CTkFrame(cards)
        card3.pack(side="left", fill="both", expand=True)
        
        total_seconds = stats['total_duration']
        
        # Smart duration display
        if total_seconds >= 3600:  # >= 1 hour
            hours = total_seconds / 3600
            duration_display = f"{hours:.1f}h"
            duration_font = 42
        elif total_seconds >= 60:  # >= 1 minute
            minutes = total_seconds / 60
            duration_display = f"{minutes:.0f}m"
            duration_font = 44
        else:  # Seconds
            duration_display = f"{int(total_seconds)}s" if total_seconds > 0 else "0s"
            duration_font = 46
        
        ctk.CTkLabel(card3, text="⏱️", font=ctk.CTkFont(size=50)).pack(pady=(30, 10))
        ctk.CTkLabel(card3, text=duration_display, font=ctk.CTkFont(size=duration_font, weight="bold")).pack(pady=8)
        ctk.CTkLabel(card3, text="Total Duration", font=ctk.CTkFont(size=14), text_color="gray").pack(pady=(0, 10))
        
        # Average speed
        avg_speed_bytes = stats['average_speed']
        if avg_speed_bytes > 0:
            avg_speed_mb = avg_speed_bytes / (1024**2)
            speed_text = f"⚡ Avg Speed: {avg_speed_mb:.1f} MB/s"
        else:
            speed_text = "⚡ Avg Speed: N/A"
        
        ctk.CTkLabel(card3, text=speed_text, font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 20))
        
        # Site Breakdown
        if stats['sites']:
            sites_frame = ctk.CTkFrame(scroll)
            sites_frame.pack(fill="x")
            
            ctk.CTkLabel(sites_frame, text="🌐 Top Sites", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=20, pady=(20, 15))
            
            sites_grid = ctk.CTkFrame(sites_frame, fg_color="transparent")
            sites_grid.pack(fill="x", padx=20, pady=(0, 20))
            
            for site, count in stats['sites'][:5]:
                site_row = ctk.CTkFrame(sites_grid, fg_color="transparent")
                site_row.pack(fill="x", pady=5)
                
                ctk.CTkLabel(site_row, text=f"🌐 {site or 'Unknown'}", font=ctk.CTkFont(size=12)).pack(side="left")
                ctk.CTkLabel(site_row, text=str(count), font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").pack(side="right")
      
    def show_history_page(self):
        """History page"""
        self.clear_content()
        self.highlight_nav("history")
        
        scroll = ctk.CTkScrollableFrame(self.main_content)
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        
        header_left = ctk.CTkFrame(header, fg_color="transparent")
        header_left.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(header_left, text="📚 Download History", font=ctk.CTkFont(size=32, weight="bold")).pack(anchor="w")
        
        ctk.CTkButton(header, text="🗑️ Clear History", command=self.clear_history,
                     width=160, height=42, fg_color="#dc2626", hover_color="#991b1b").pack(side="right")
        
        # Search
        search_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 15))
        
        self.history_search_entry = ctk.CTkEntry(search_frame, placeholder_text="🔍 Search...",
                                                 height=42, font=ctk.CTkFont(size=13))
        self.history_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.history_search_entry.bind("<KeyRelease>", self.search_history)
        
        ctk.CTkButton(search_frame, text="🔍 Search", command=self.search_history, width=120, height=42).pack(side="right")
        
        # History list
        self.history_list_frame = ctk.CTkScrollableFrame(scroll, height=600)
        self.history_list_frame.pack(fill="both", expand=True)
        
        self.refresh_history()
    
    def show_about_page(self):
        """About page"""
        self.clear_content()
        self.highlight_nav("about")
        
        scroll = ctk.CTkScrollableFrame(self.main_content)
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        center = ctk.CTkFrame(scroll, fg_color="transparent")
        center.pack(expand=True, pady=50)
        
        ctk.CTkLabel(center, text="🎥", font=ctk.CTkFont(size=80)).pack(pady=(0, 15))
        ctk.CTkLabel(center, text="Ultimate Video Downloader", font=ctk.CTkFont(size=32, weight="bold")).pack(pady=5)
        ctk.CTkLabel(center, text="Version 9.0 Final Edition", font=ctk.CTkFont(size=16), text_color="gray").pack(pady=5)
        
        features = [
            "✅ Dynamic quality detection (444p, 640p, etc.)",
            "✅ Auto MP4 format",
            "✅ Fixed statistics display",
            "✅ Enhanced batch download with progress bars",
            "✅ Real-time console logging",
            "✅ Database integration",
            "✅ State saving when switching pages",
            "✅ 1800+ websites supported"
        ]
        
        features_frame = ctk.CTkFrame(center)
        features_frame.pack(pady=20)
        
        for feature in features:
            ctk.CTkLabel(features_frame, text=feature, font=ctk.CTkFont(size=13), anchor="w").pack(anchor="w", padx=30, pady=4)
    
    # Background updater
    def _pip_upgrade(self, package: str) -> None:
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", package, "--quiet"]
            subprocess.run(cmd, capture_output=True, check=False)
            self.log(f"⬆️ {package} checked/updated")
        except Exception as e:
            try:
                self.log(f"⚠️ {package} update skipped: {e}")
            except Exception:
                pass
    
    def _install_playwright_browsers(self) -> None:
        try:
            import platform
            is_windows = platform.system().lower().startswith("win")
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            if not is_windows:
                cmd.append("--with-deps")
            subprocess.run(cmd, capture_output=True, check=False)
            self.log("✅ Playwright Chromium available")
        except Exception as e:
            try:
                self.log(f"⚠️ Playwright browser install skipped: {e}")
            except Exception:
                pass
    
    def _background_update_deps(self) -> None:
        """Background updates disabled - updates now run at startup"""
        pass
    # Core Functions
    
    def clear_content(self):
        for widget in self.main_content.winfo_children():
            widget.destroy()
    
    def highlight_nav(self, active):
        """Highlight active navigation button with modern styling"""
        self.current_page = active
        for key, btn in self.nav_buttons.items():
            if key == active:
                btn.configure(
                    fg_color=Theme.BG_TERTIARY,
                    text_color=Theme.ACCENT_PRIMARY,
                    font=ctk.CTkFont(size=14, weight="bold")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=Theme.TEXT_SECONDARY,
                    font=ctk.CTkFont(size=14, weight="normal")
                )
    
    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            self.log_text.insert("end", f"[{timestamp}] {msg}\n")
            self.log_text.see("end")
        except:
            pass
    
    def batch_log_message(self, msg):
        """Log message to batch console"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            self.batch_log_text.insert("end", f"[{timestamp}] {msg}\n")
            self.batch_log_text.see("end")
        except:
            pass
    
    def clear_log(self):
        try:
            self.log_text.delete("1.0", "end")
            self.log("📜 Console cleared")
        except:
            pass
    
    def clear_batch_log(self):
        """Clear batch log"""
        try:
            self.batch_log_text.delete("1.0", "end")
            self.batch_log_message("📜 Console cleared")
        except:
            pass
    
    def update_progress(self, data):
        try:
            status = data.get('status')
            
            if status == 'downloading':
                percent = data.get('percent', 0)
                downloaded = data.get('downloaded', 0)
                total = data.get('total', 0)
                speed = data.get('speed', 0)
                eta = data.get('eta', 0)
                
                self.progress_bar.set(percent / 100)
                self.progress_percent.configure(text=f"{percent:.1f}%")
                
                if total > 0:
                    down_mb = downloaded / (1024**2)
                    total_mb = total / (1024**2)
                    self.size_progress_label.configure(text=f"{down_mb:.1f} MB / {total_mb:.1f} MB")
                
                if speed:
                    speed_mb = speed / (1024**2)
                    self.speed_label.configure(text=f"Speed: {speed_mb:.2f} MB/s")
                
                if eta:
                    mins, secs = divmod(int(eta), 60)
                    self.eta_label.configure(text=f"ETA: {mins:02d}:{secs:02d}")
                
                self.status_label.configure(text="Downloading...")
            
            elif status == 'processing':
                self.progress_bar.set(0.98)
                self.status_label.configure(text="Processing...")
        except:
            pass
    
    def detect_video(self):
        """Detect video"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Enter URL!")
            return
        
        self.log("🔍 Analyzing video and detecting qualities...")
        threading.Thread(target=self._detect_thread, args=(url,), daemon=True).start()
    
    def _detect_thread(self, url):
        """Detection thread"""
        try:
            ydl_opts = {'quiet': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.video_info = info
                self.after(0, lambda: self._update_info_and_qualities(info))
        except Exception as e:
            self.after(0, lambda: self.log(f"⚠️ Detection failed: {str(e)[:60]}"))
            self.after(0, lambda: self.info_frame.pack(fill="x", padx=20, pady=(0, 15)))
    
    def _update_info_and_qualities(self, info):
        """Update info and qualities"""
        title = info.get('title', 'Unknown')
        duration = info.get('duration', 0)
        filesize = info.get('filesize') or info.get('filesize_approx', 0)
        
        self.title_label.configure(text=f"📝 {title[:70]}")
        
        if duration:
            mins, secs = divmod(int(duration), 60)
            self.duration_label.configure(text=f"⏱️ Duration: {mins}m {secs}s")
        
        if filesize:
            self.size_label.configure(text=f"💾 Size: ~{filesize/(1024**2):.1f} MB")
        
        # Extract qualities
        formats = info.get('formats', [])
        available_heights = set()
        
        for fmt in formats:
            height = fmt.get('height')
            if height and fmt.get('vcodec') != 'none':
                available_heights.add(height)
        
        sorted_qualities = sorted(available_heights, reverse=True)
        self.available_qualities = sorted_qualities
        
        if sorted_qualities:
            self.create_dynamic_quality_buttons(sorted_qualities)
            self.log(f"✅ Found qualities: {', '.join(str(q)+'p' for q in sorted_qualities)}")
        else:
            self.log("⚠️ No specific qualities detected, using defaults")
        
        self.info_frame.pack(fill="x", padx=20, pady=(0, 15))
        self.log(f"✅ {title[:50]}")
    
    def start_download(self):
        if self.is_downloading:
            return
        
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Enter URL!")
            return
        
        # ✅ Reset cancel flag for a fresh download
        try:
            self.download_manager.is_cancelled = False
        except Exception:
            pass
        
        self.is_downloading = True
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        
        threading.Thread(target=self._download_thread, daemon=True).start()
    
    def _download_thread(self):
        url = self.url_entry.get().strip()
        quality = self.quality_var.get()
        output_path = self.path_entry.get().strip()
        
        preferred_title = getattr(self, "_preferred_title", None)
        preferred_referer = getattr(self, "_preferred_referer", None)
        result = self.download_manager.download(url, quality, output_path, preferred_title=preferred_title, referer=preferred_referer)
        
        if result['success']:
            info = result['info']
            final_path = result.get('final_path')
            # Prefer captured title; else yt-dlp title; else basename
            raw_title = preferred_title or info.get('title') or self.download_manager._fallback_title_from_url(url)
            title = self.download_manager._sanitize_title(raw_title)
            site = self.detect_site(url)
            file_path = final_path or os.path.join(output_path, f"{title}.mp4")
            self.db.add_download(
                url, title, site, quality, file_path,
                result.get('filesize', 0), result.get('duration', 0),
                result['completion_time'], result['average_speed']
            )
            
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self.log("✅ Download complete!"))
            self.after(0, lambda: messagebox.showinfo("Success", f"Downloaded!\n\n{title}"))
        else:
            err = result.get('error', '') or ''
            if 'cancel' in err.lower():
                self.after(0, lambda: self.log("🛑 Download cancelled"))
                self.after(0, lambda: self.status_label.configure(text="Cancelled"))
            else:
                self.after(0, lambda: self.log(f"❌ Failed: {err[:60]}"))
                self.after(0, lambda: messagebox.showerror("Error", f"Failed:\n\n{err[:150]}"))
        
        self.after(0, self._download_complete)
        # Clear preferred title after use
        self._preferred_title = None
        self._preferred_referer = None
    
    def _download_complete(self):
        self.is_downloading = False
        self.download_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
    
    def cancel_download(self):
        """Cancel the current download"""
        try:
            self.download_manager.cancel()
            self.log("⏹️ Cancelling download...")
            try:
                self.status_label.configure(text="Cancelling...")
            except Exception:
                pass
        except Exception as e:
            try:
                self.log(f"⚠️ Cancel error: {e}")
            except Exception:
                pass
    
    def detect_site(self, url):
        sites = {
            'youtube.com': 'YouTube', 'instagram.com': 'Instagram',
            'tiktok.com': 'TikTok', 'twitter.com': 'Twitter',
            'facebook.com': 'Facebook', 'reddit.com': 'Reddit'
        }
        for domain, name in sites.items():
            if domain in url.lower():
                return name
        return "Other"
    
    def paste_url(self):
        try:
            text = pyperclip.paste()
            if 'http' in text:
                self.url_entry.delete(0, tk.END)
                self.url_entry.insert(0, text)
                self.log("📋 Pasted")
        except:
            pass
    
    def open_folder(self):
        path = self.path_entry.get().strip()
        try:
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':
                subprocess.call(['open', path])
            else:
                subprocess.call(['xdg-open', path])
        except:
            pass
    
    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_path)
        if folder:
            self.download_path = folder
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)
    
    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if url:
            quality = self.quality_var.get()
            if self.db.add_to_queue(url, quality):
                self.log("➕ Added to queue")
                messagebox.showinfo("Success", "Added!")
    
    def update_url_count(self, event=None):
        try:
            content = self.batch_text.get("1.0", "end").strip()
            urls = [line for line in content.split('\n') if 'http' in line]
            self.url_count_label.configure(text=f"{len(urls)} URLs")
        except:
            pass
    
    def load_batch_file(self):
        file = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file:
            try:
                with open(file, 'r') as f:
                    self.batch_text.delete("1.0", "end")
                    self.batch_text.insert("1.0", f.read())
                messagebox.showinfo("Success", "Loaded!")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def paste_batch_urls(self):
        try:
            text = pyperclip.paste()
            if text:
                current = self.batch_text.get("1.0", "end").strip()
                if current:
                    self.batch_text.insert("end", "\n" + text)
                else:
                    self.batch_text.insert("1.0", text)
        except:
            pass
    
    def start_batch_download(self):
        urls_text = self.batch_text.get("1.0", "end").strip()
        if not urls_text:
            messagebox.showwarning("Warning", "Add URLs!")
            return
        
        urls = [line.strip() for line in urls_text.split('\n') if 'http' in line]
        if not urls:
            messagebox.showwarning("Warning", "No valid URLs!")
            return
        
        self.is_batch_downloading = True
        self.batch_download_btn.configure(state="disabled")
        self.batch_cancel_btn.configure(state="normal")
        
        quality = self.batch_quality_var.get()
        output_path = self.download_path
        
        threading.Thread(target=self._batch_thread, args=(urls, quality, output_path), daemon=True).start()
    
    def _batch_thread(self, urls, quality, output):
        """Batch download thread - SAFE VERSION"""
        completed = 0
        failed = 0
        total = len(urls)
        
        self.batch_log_message(f"🚀 Starting batch download of {total} videos")
        self.batch_log_message(f"🎬 Quality: {quality}")
        self.batch_log_message(f"📁 Output: {output}")
        self.batch_log_message("─" * 60)
        
        for i, url in enumerate(urls, 1):
            if not self.is_batch_downloading:
                self.batch_log_message("🛑 Batch download cancelled by user")
                break
            
            # Update progress safely
            try:
                overall_percent = ((i - 1) / total) * 100
                if hasattr(self, 'batch_overall_progress') and self.batch_overall_progress.winfo_exists():
                    self.after(0, lambda p=overall_percent: self.batch_overall_progress.set(p / 100))
                if hasattr(self, 'batch_overall_label') and self.batch_overall_label.winfo_exists():
                    self.after(0, lambda i=i, t=total, c=completed, f=failed: 
                              self.batch_overall_label.configure(text=f"{i-1} / {t} videos (✅ {c} • ❌ {f})"))
                if hasattr(self, 'batch_progress_label') and self.batch_progress_label.winfo_exists():
                    self.after(0, lambda i=i, t=total, c=completed, f=failed: 
                              self.batch_progress_label.configure(text=f"Downloading video {i}/{t} • Completed: {c} • Failed: {f}"))
            except:
                pass
            
            try:
                if hasattr(self, 'batch_current_progress') and self.batch_current_progress.winfo_exists():
                    self.after(0, lambda: self.batch_current_progress.set(0))
                if hasattr(self, 'batch_current_percent') and self.batch_current_percent.winfo_exists():
                    self.after(0, lambda: self.batch_current_percent.configure(text="0%"))
            except:
                pass
            
            self.batch_log_message(f"\n[{i}/{total}] Processing: {url[:70]}")
            
            try:
                if hasattr(self, 'batch_current_label') and self.batch_current_label.winfo_exists():
                    self.after(0, lambda u=url: self.batch_current_label.configure(text=f"Current: {u[:60]}..."))
            except:
                pass
            
            try:
                def update_current_progress(percent):
                    try:
                        if hasattr(self, 'batch_current_progress') and self.batch_current_progress.winfo_exists():
                            self.after(0, lambda p=percent: self.batch_current_progress.set(p / 100))
                        if hasattr(self, 'batch_current_percent') and self.batch_current_percent.winfo_exists():
                            self.after(0, lambda p=percent: self.batch_current_percent.configure(text=f"{p:.1f}%"))
                    except:
                        pass
                
                result = self.download_manager.download_for_batch(
                    url, quality, output, batch_progress_callback=update_current_progress
                )
                
                if result['success']:
                    info = result['info']
                    title = result['title']
                    site = self.detect_site(url)
                    
                    file_path = os.path.join(output, f"{title}.mp4")
                    self.db.add_download(
                        url, title, site, quality, file_path,
                        result.get('filesize', 0), 
                        result.get('duration', 0),
                        result.get('completion_time', 0), 
                        result.get('average_speed', 0)
                    )
                    
                    completed += 1
                    self.batch_log_message(f"  📝 Title: {title[:50]}")
                    self.batch_log_message(f"  ✅ SUCCESS - Saved to database")
                    
                    try:
                        if hasattr(self, 'batch_current_progress') and self.batch_current_progress.winfo_exists():
                            self.after(0, lambda: self.batch_current_progress.set(1.0))
                        if hasattr(self, 'batch_current_percent') and self.batch_current_percent.winfo_exists():
                            self.after(0, lambda: self.batch_current_percent.configure(text="100%"))
                    except:
                        pass
                else:
                    failed += 1
                    error = result.get('error', 'Unknown error')[:60]
                    self.batch_log_message(f"  ❌ FAILED: {error}")
                
            except Exception as e:
                failed += 1
                self.batch_log_message(f"  ❌ EXCEPTION: {str(e)[:60]}")
        
        # Final summary
        self.batch_log_message("\n" + "═" * 60)
        self.batch_log_message(f"✅ BATCH DOWNLOAD COMPLETE!")
        self.batch_log_message(f"📊 Total: {total} videos")
        self.batch_log_message(f"✅ Successful: {completed}")
        self.batch_log_message(f"❌ Failed: {failed}")
        self.batch_log_message(f"📁 Saved to: {output}")
        
        try:
            if hasattr(self, 'batch_overall_progress') and self.batch_overall_progress.winfo_exists():
                self.after(0, lambda: self.batch_overall_progress.set(1.0))
            if hasattr(self, 'batch_overall_label') and self.batch_overall_label.winfo_exists():
                self.after(0, lambda c=completed, t=total, f=failed: 
                          self.batch_overall_label.configure(text=f"{t} / {t} videos (✅ {c} • ❌ {f})"))
            if hasattr(self, 'batch_progress_label') and self.batch_progress_label.winfo_exists():
                self.after(0, lambda c=completed, f=failed: 
                          self.batch_progress_label.configure(text=f"✅ Batch complete! {c} successful, {f} failed"))
            if hasattr(self, 'batch_current_label') and self.batch_current_label.winfo_exists():
                self.after(0, lambda: self.batch_current_label.configure(text="All videos processed"))
        except:
            pass
        
        self.after(0, self._batch_complete)
        self.after(0, lambda c=completed, f=failed: messagebox.showinfo(
            "Batch Complete", 
            f"Batch download finished!\n\n✅ Successful: {c}\n❌ Failed: {f}\n\nAll downloads saved to database and statistics."
        ))
    
    def _batch_complete(self):
        self.is_batch_downloading = False
        self.batch_download_btn.configure(state="normal")
        self.batch_cancel_btn.configure(state="disabled")
    
    def cancel_batch(self):
        self.is_batch_downloading = False
        self.batch_log_message("🛑 Cancelled")
    
    def refresh_history(self):
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()
        
        history = self.db.get_download_history(50)
        
        if not history:
            ctk.CTkLabel(self.history_list_frame, text="No downloads yet!",
                        font=ctk.CTkFont(size=15), text_color="gray").pack(pady=100)
            return
        
        for item in history:
            item_frame = ctk.CTkFrame(self.history_list_frame)
            item_frame.pack(fill="x", pady=5)
            
            title = item[2] or "Unknown"
            date = item[9] if len(item) > 9 else "Unknown"
            
            ctk.CTkLabel(item_frame, text=f"📹 {title[:60]}", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(10, 2))
            ctk.CTkLabel(item_frame, text=f"📅 {date} • 🎬 {item[4]} • 🌐 {item[3]}",
                        font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=15, pady=(0, 10))
    
    def search_history(self, event=None):
        query = self.history_search_entry.get().strip()
        
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()
        
        if not query:
            self.refresh_history()
            return
        
        results = self.db.search_downloads(query)
        
        if not results:
            ctk.CTkLabel(self.history_list_frame, text=f"No results for: {query}",
                        font=ctk.CTkFont(size=14), text_color="gray").pack(pady=50)
            return
        
        for item in results:
            item_frame = ctk.CTkFrame(self.history_list_frame)
            item_frame.pack(fill="x", pady=5)
            
            title = item[2] or "Unknown"
            date = item[9] if len(item) > 9 else "Unknown"
            
            ctk.CTkLabel(item_frame, text=f"📹 {title[:60]}", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(10, 2))
            ctk.CTkLabel(item_frame, text=f"📅 {date} • 🎬 {item[4]} • 🌐 {item[3]}",
                        font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=15, pady=(0, 10))
    
    def clear_history(self):
        if messagebox.askyesno("Confirm", "Clear all history?"):
            self.db.clear_history()
            self.refresh_history()
            messagebox.showinfo("Success", "Cleared!")

    def start_browser_capture(self):
        """Start browser capture for the current URL"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Enter URL first!")
            return

        if getattr(self, "_capture_thread", None) and self._capture_thread.is_alive():
            self.log("♻️ Restarting capture (previous session detected).")
            try:
                self.stop_browser_capture()
            except Exception:
                pass

        self.log("🕵️ Starting browser capture...")
        self.log("⚠️ Do not close the capture browser until the download is finished.")

        def _sanitize_filename(name: str) -> str:
            try:
                if not name:
                    return ""
                bad = '<>:"/\\|?*'
                for ch in bad:
                    name = name.replace(ch, "_")
                return name.strip()[:200]
            except Exception:
                return ""

        def on_found(media_url: str, page_title: str = "", page_url: str = ""):
            # Insert the direct media URL back into the entry and clipboard
            try:
                safe_title = _sanitize_filename(page_title) or None
                self._preferred_title = safe_title
                self._preferred_referer = page_url or None
                self.after(0, lambda: self.url_entry.delete(0, tk.END))
                self.after(0, lambda: self.url_entry.insert(0, media_url))
                try:
                    pyperclip.copy(media_url)
                    self.after(0, lambda: self.log("📋 Direct media URL copied to clipboard"))
                except Exception:
                    pass
                if safe_title:
                    self.after(0, lambda: self.log(f"✅ Media URL captured. Will save as: {safe_title}.mp4"))
                else:
                    self.after(0, lambda: self.log("✅ Media URL captured. You can now Analyze or Download."))
            except Exception:
                pass

        self._browser_engine = BrowserCaptureEngine(self.log, on_found)
        self._capture_thread = threading.Thread(
            target=lambda: self._browser_engine.start(url, headless=False, timeout_sec=300),
            daemon=True
        )
        self._capture_thread.start()
        self._watch_capture()

    def stop_browser_capture(self):
        """Stop browser capture if running"""
        try:
            if getattr(self, "_browser_engine", None):
                self._browser_engine.stop()
                self.log("🛑 Stopping capture...")
            if getattr(self, "_capture_thread", None):
                try:
                    self._capture_thread.join(timeout=2)
                except Exception:
                    pass
                self._capture_thread = None
            self._browser_engine = None
        except Exception:
            pass
    
    def _watch_capture(self):
        """Watcher to clear capture state when thread ends"""
        try:
            th = getattr(self, "_capture_thread", None)
            if th and th.is_alive():
                self.after(500, self._watch_capture)
            else:
                self._capture_thread = None
                self._browser_engine = None
                self.log("🟢 Capture stopped.")
        except Exception:
            pass
    
    def on_closing(self):
        """Clean up and close"""
        try:
            self.stop_browser_capture()
        except Exception:
            pass
        self.db.close()
        self.destroy()

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import multiprocessing
    
    # Required for PyInstaller on Windows
    multiprocessing.freeze_support()
    
    # Set multiprocessing method for Windows compatibility
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set
    
    # Choose GUI version:
    # - UltimateDownloaderV9: Full-featured with sidebar navigation
    # - UltimateDownloaderModern: Ultra-modern tabbed interface (Complete!)
    USE_MODERN_GUI = True  # Set to False to use the classic V9 interface
    
    if USE_MODERN_GUI:
        app = UltimateDownloaderModern()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
    else:
        app = UltimateDownloaderV9()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    app.mainloop()
