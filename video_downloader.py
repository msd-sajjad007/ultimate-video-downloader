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
# ENTERPRISE-GRADE UPGRADE IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════
from config import ConfigManager
from logger import LoggerFactory, monitor_performance
from error_handling import (
    ErrorHandler, retry_on_error, CircuitBreaker,
    NetworkError, RateLimitError, ValidationError, FileSystemError
)
from performance import DownloadQueue, memoize, MemoryCache
from security import SecurityValidator

# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE LOGIC MOVED TO MAIN ENTRY POINT (see bottom of file)
# ═══════════════════════════════════════════════════════════════════════════════

# === Browser capture imports ===
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    sync_playwright = None  # Will lazy-install if missing

# ═══════════════════════════════════════════════════════════════════════════════
# GREENLET THREADING COMPATIBILITY FIX
# ═══════════════════════════════════════════════════════════════════════════════
import warnings
import asyncio
import logging

# Suppress greenlet threading warnings - Playwright handles these internally
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*greenlet.*')
logging.getLogger('asyncio').setLevel(logging.ERROR)

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
    FIXED: Enterprise-Grade Video Stream Capture Engine
    Now captures ALL video types properly!
    """

    # ENHANCED: More comprehensive patterns
    VIDEO_URL_PATTERNS = [
        # HLS (most common streaming)
        r'\.m3u8',
        r'/hls/',
        r'master\.m3u8',
        r'playlist\.m3u8',
        r'index\.m3u8',

        # DASH
        r'\.mpd',
        r'/dash/',
        r'manifest\.mpd',

        # Direct video files
        r'\.mp4',
        r'\.webm',
        r'\.m4v',
        r'\.mov',
        r'\.avi',
        r'\.mkv',
        r'\.flv',
        r'\.ts',
        r'\.m4s',

        # Common paths
        r'/video',
        r'/stream',
        r'/media',
        r'/content',
        r'/player',
        r'/live',
    ]

    VIDEO_CONTENT_TYPES = [
        'video/mp4',
        'video/webm',
        'video/x-m4v',
        'video/ogg',
        'video/x-msvideo',
        'application/x-mpegurl',
        'application/vnd.apple.mpegurl',
        'application/dash+xml',
        'video/mp2t',
        'video/mpeg',
        'video/quicktime',
        'video/x-flv',
    ]

    # FIXED: Less restrictive exclude patterns
    EXCLUDE_PATTERNS = [
        r'\.(jpg|jpeg|png|gif|webp|svg|ico)$',  # Images only
        r'\.(js|css|woff|ttf|eot)$',  # Assets only
        r'/ad[s]?/',  # Ads
        r'/analytics/',  # Analytics
        r'/thumbnail',  # Thumbnails
        r'/poster',  # Posters
    ]

    def __init__(self, log_fn, on_found):
        self.log = log_fn
        self.on_video_found = on_found
        self._stop = False
        self._stopping = False
        self._is_running = False
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None

        self.captured_videos = set()
        self._video_elements = set()

        # NEW: Tracking
        self.response_count = 0
        self.video_check_count = 0

    def _is_video_url(self, url: str, content_type: str, headers: dict) -> bool:
        """
        FIXED: Much more lenient video URL detection.
        """
        if not url:
            return False

        url_lower = url.lower()

        # FIRST: Check exclude patterns (must be strict)
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, url_lower):
                return False

        # SECOND: Check content type (if available)
        if content_type:
            for vtype in self.VIDEO_CONTENT_TYPES:
                if vtype in content_type.lower():
                    self.log(f"✅ Video detected by content-type: {content_type}")
                    return True

        # THIRD: Check URL patterns (be generous)
        for pattern in self.VIDEO_URL_PATTERNS:
            if re.search(pattern, url_lower):
                self.log(f"✅ Video detected by URL pattern: {pattern}")
                return True

        # FOURTH: Check for range requests (video streams often use these)
        if headers:
            range_header = headers.get('range', '').lower()
            if 'bytes' in range_header:
                self.log(f"✅ Video detected by range request")
                return True

        # FIFTH: Check content length (LOWERED threshold)
        if headers:
            try:
                content_length = int(headers.get('content-length', 0))
                # FIXED: Lower threshold to 100KB instead of 1MB
                if content_length > 100000:  # 100KB
                    # Also check if URL looks video-like
                    if any(hint in url_lower for hint in ['video', 'stream', 'media', 'mp4', 'webm', 'm3u8']):
                        self.log(f"✅ Video detected by size + URL hint: {content_length} bytes")
                        return True
            except:
                pass

        return False

    def extract_title_from_page(self):
        """Extract title from multiple sources with priority."""
        try:
            # Try video title attribute
            video_title = self.page.evaluate("""
                () => {
                    const video = document.querySelector('video');
                    return video ? video.title || video.getAttribute('data-title') : null;
                }
            """)
            if video_title:
                self.log(f"📌 Video title: {video_title}")
                return video_title.strip()

            # Try Open Graph title
            og_title = self.page.evaluate("""
                () => {
                    const og = document.querySelector('meta[property="og:title"]');
                    return og ? og.content : null;
                }
            """)
            if og_title:
                return og_title.strip()

            # Try page title
            page_title = self.page.title()
            if page_title:
                return page_title.strip()

            # Fallback to URL
            from urllib.parse import urlparse
            domain = urlparse(self.page.url).netloc.replace('www.', '')
            return f"Video from {domain}"

        except Exception as e:
            self.log(f"Title extraction error: {e}")
            return "Video"

    def _extract_video_sources(self):
        """Extract video sources from <video> elements on the page."""
        try:
            videos = self.page.query_selector_all('video')
            current_title = self.extract_title_from_page()

            videos = self.page.query_selector_all('video')

            for video in videos:
                src = video.get_attribute('src')

                if src and src not in self._video_elements:
                    self._video_elements.add(src)

                    if self._is_video_url(src, '', {}):
                        # Get video-specific title or use page title
                        video_title = (video.get_attribute('title') or 
                                     video.get_attribute('data-title') or 
                                     current_title)

                        self.log(f"📹 Extracted: {video_title[:50]}")

                        if src not in self.captured_videos:
                            self.captured_videos.add(src)
                            page_url = self.page.url
                            self.on_video_found(src, video_title, page_url)

                # Check source children
                sources = video.query_selector_all('source')
                for source in sources:
                    src = source.get_attribute('src')
                    if src and src not in self._video_elements:
                        self._video_elements.add(src)

                        if self._is_video_url(src, '', {}):
                            source_title = (source.get_attribute('title') or 
                                          current_title)

                            if src not in self.captured_videos:
                                self.captured_videos.add(src)
                                self.on_video_found(src, source_title, self.page.url)

        except Exception as e:
            self.log(f"Video extraction error: {e}")

    def detect_video_quality(self, url):
        """Detect video quality from URL."""
        import re

        url_lower = url.lower()
        resolution = 'Unknown'
        format_type = 'Unknown'

        # Look for resolution in URL
        res_match = re.search(r'(\d{3,4})p', url)
        if res_match:
            resolution = f"{res_match.group(1)}p"

        # Look for dimensions
        dim_match = re.search(r'(\d{3,4})x(\d{3,4})', url)
        if dim_match:
            resolution = dim_match.group(0)

        # Detect format
        if '.m3u8' in url_lower:
            format_type = 'HLS'
        elif '.mpd' in url_lower:
            format_type = 'DASH'
        elif '1080' in url_lower and resolution == 'Unknown':
            resolution = '1080p'
        elif '720' in url_lower and resolution == 'Unknown':
            resolution = '720p'
        elif '480' in url_lower and resolution == 'Unknown':
            resolution = '480p'

        return {'resolution': resolution, 'format': format_type, 'quality': resolution if resolution != 'Unknown' else format_type}

    def parse_hls_manifest(self, manifest_url):
        """
        Parse HLS manifest to extract quality variants.

        Returns: list of variant streams with quality info
        """
        try:
            import requests
            response = requests.get(manifest_url, timeout=10)
            content = response.text

            variants = []
            lines = content.split('\n')

            current_variant = {}
            for i, line in enumerate(lines):
                line = line.strip()

                if line.startswith('#EXT-X-STREAM-INF:'):
                    # Parse stream info
                    import re

                    bandwidth_match = re.search(r'BANDWIDTH=(\d+)', line)
                    resolution_match = re.search(r'RESOLUTION=(\d+x\d+)', line)
                    codecs_match = re.search(r'CODECS="([^"]+)"', line)

                    current_variant = {
                        'bandwidth': int(bandwidth_match.group(1)) if bandwidth_match else None,
                        'resolution': resolution_match.group(1) if resolution_match else None,
                        'codecs': codecs_match.group(1) if codecs_match else None,
                    }

                    # Next line should be the URL
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line and not next_line.startswith('#'):
                            current_variant['url'] = next_line
                            variants.append(current_variant)
                            current_variant = {}

            # Sort by quality (highest first)
            variants.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)

            return variants

        except Exception as e:
            self.log(f"HLS manifest parsing error: {e}")
            return []

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

                    is_video = self._is_video_url(url, content_type, headers)
                    
                    # hard gate: only real video / streaming types
                    ctype = (content_type or "").lower()
                    is_real_video = (
                        ctype.startswith("video/") or
                        "application/x-mpegurl" in ctype or
                        "application/vnd.apple.mpegurl" in ctype or
                        "application/dash+xml" in ctype
                    )

                    if is_video and is_real_video:
                        # STRICT deduplication - only process if truly new
                        if url not in self.captured_videos:
                            self.captured_videos.add(url)
                            self.log(f"📊 New video detected ({len(self.captured_videos)} total)")
                            
                            try:
                                # Enhanced title extraction
                                title = self.extract_title_from_page()
                            except Exception as title_err:
                                title = "Video"
                                self.log(f"⚠️ Title extraction failed: {title_err}")
                            
                            # Detect quality from response
                            try:
                                quality_info = self.detect_video_quality(url)
                            except Exception as quality_err:
                                quality_info = {'resolution': 'Unknown', 'format': 'Unknown'}
                                self.log(f"⚠️ Quality detection failed: {quality_err}")
                            
                            page_url = self.page.url
                            content_length = headers.get('content-length', 'Unknown')
                            
                            # Enhanced logging with quality info
                            self.log(f"🎬 CAPTURED VIDEO STREAM:")
                            self.log(f"   Title: {title[:60]}")
                            self.log(f"   URL: {url[:80]}")
                            self.log(f"   Type: {content_type}")
                            self.log(f"   Size: {content_length} bytes")
                            if quality_info and isinstance(quality_info, dict):
                                if quality_info.get('resolution') and quality_info.get('resolution') != 'Unknown':
                                    self.log(f"   Quality: {quality_info['resolution']}")
                            
                            # Thread-safe callback
                            try:
                                self.log(f"🔗 Calling on_video_found callback with URL: {url[:60]}...")
                                self.on_video_found(url, title, page_url)
                                self.log(f"✅ Callback successful - URL should appear in entry field")
                            except Exception as callback_err:
                                import traceback
                                self.log(f"⚠️ Callback error: {callback_err}")
                                self.log(f"⚠️ Callback traceback: {traceback.format_exc()[:300]}")

                    if len(self.captured_videos) == 0:
                        try:
                            self._extract_video_sources()
                        except Exception as extract_err:
                            self.log(f"⚠️ Video extraction error: {extract_err}")
                except Exception as e:
                    import traceback
                    self.log(f"⚠️ Response handler error: {e}")
                    self.log(f"⚠️ Traceback: {traceback.format_exc()[:200]}")

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
# NEW: DOWNLOAD QUEUE MANAGER SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadItem:
    """Represents a single download with progress tracking"""
    def __init__(self, download_id, url, title, quality, output_path):
        self.id = download_id
        self.url = url
        self.title = title or "Untitled"
        self.quality = quality
        self.output_path = output_path
        self.status = "queued"  # queued, downloading, processing, completed, failed, cancelled
        self.progress = 0.0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.speed = 0
        self.eta = 0
        self.error_message = ""
        self.file_path = ""
        self.start_time = None
        self.end_time = None
        self.thread = None
        self.thumbnail = None

    def update_progress(self, data: dict):
        """Update download progress from normalized callback data"""
        # status: 'downloading', 'processing', 'finished'
        status = data.get("status")
        if status:
            if status == "finished":
                self.status = "completed"
                self.progress = 100.0
            else:
                self.status = status

        # numeric fields
        if "percent" in data and data["percent"] is not None:
            self.progress = float(data["percent"])

        if "downloaded" in data and data["downloaded"] is not None:
            self.downloaded_bytes = int(data["downloaded"])

        if "total" in data and data["total"] is not None:
            self.total_bytes = int(data["total"])

        if "speed" in data and data["speed"] is not None:
            self.speed = float(data["speed"])

        if "eta" in data and data["eta"] is not None:
            self.eta = int(data["eta"])

class ActiveDownloadsManager:
    """Manages multiple simultaneous downloads"""
    def __init__(self):
        self.downloads = {}  # download_id -> DownloadItem
        self.next_id = 1
        self.lock = threading.Lock()

    def add_download(self, url, title, quality, output_path):
        """Add a new download to the queue"""
        with self.lock:
            download_id = self.next_id
            self.next_id += 1
            item = DownloadItem(download_id, url, title, quality, output_path)
            self.downloads[download_id] = item
            return download_id

    def get_download(self, download_id):
        """Get download by ID"""
        with self.lock:
            return self.downloads.get(download_id)

    def get_all_active(self):
        """Get all active (not completed/failed) downloads"""
        with self.lock:
            return [d for d in self.downloads.values() 
                    if d.status in ['queued', 'downloading', 'processing']]

    def get_all_completed(self):
        """Get all completed downloads from manager cache"""
        with self.lock:
            return [d for d in self.downloads.values() 
                    if d.status in ['completed', 'failed', 'cancelled']]

    def remove_download(self, download_id):
        """Remove download from manager"""
        with self.lock:
            if download_id in self.downloads:
                # Cancel thread if still running
                item = self.downloads[download_id]
                if item.thread and item.thread.is_alive():
                    # Set cancellation flag
                    item.status = "cancelled"
                del self.downloads[download_id]

    def update_status(self, download_id, status, error_message="", file_path=""):
        """Update download status"""
        with self.lock:
            if download_id in self.downloads:
                self.downloads[download_id].status = status
                if error_message:
                    self.downloads[download_id].error_message = error_message
                if file_path:
                    self.downloads[download_id].file_path = file_path

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
    """Enhanced download manager with enterprise features"""
    
    def __init__(self, progress_callback=None, log_callback=None, config=None, logger=None, security=None, error_handler=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.config = config
        self.logger = logger
        self.security = security
        self.error_handler = error_handler
        self.is_cancelled = False
        self.start_time = None
    
    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def extract_title_from_info(self, info):
        """
        Extract best possible title from yt-dlp info dict.

        Priority:
        1. info['title'] - Primary title
        2. info['alt_title'] - Alternative title
        3. info['track'] - Music track name
        4. info['fulltitle'] - Full title
        5. info['webpage_url_basename'] - URL based
        6. Fallback to 'video'
        """
        if not isinstance(info, dict):
            return 'video'

        # Try various title fields in priority order
        title = (info.get('title') or 
                info.get('alt_title') or 
                info.get('track') or 
                info.get('fulltitle') or 
                info.get('webpage_url_basename') or 
                'video')

        return str(title).strip()

    def build_output_template(self, output_path, title, quality, is_audio=False):
        """
        Build yt-dlp output template with proper filename.

        Returns: Complete path with template
        """
        import os

        # Sanitize title
        safe_title = self._sanitize_title(title)

        # Add quality suffix if not audio
        if not is_audio and quality and quality != 'best':
            safe_title = f"{safe_title}_{quality}"

        # Extension
        ext = '.mp3' if is_audio else '.mp4'

        # Full template
        template = os.path.join(output_path, f"{safe_title}{ext}")

        return template

    def _format_for_quality(self, quality: str) -> str:
        """
        Map GUI quality selection to yt-dlp format string.
        Priority: exact match -> downgrade -> upgrade if nothing below exists
        """
        if not quality or quality == "best":
            return "bv*+ba/best"
        
        if quality == "audio":
            return "bestaudio/best"
        
        if quality.endswith("p"):
            try:
                height = int(quality[:-1])
                # Priority chain:
                # 1. Try exact height with best audio
                # 2. Try within ±10% tolerance with best audio
                # 3. Try anything at or below requested height
                # 4. If nothing below exists, fallback to best (upgrade)
                return f"bv*[height={height}]+ba/bv*[height<={int(height*1.1)}][height>={int(height*0.9)}]+ba/bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/best"
            except (ValueError, IndexError):
                self.log(f"Invalid quality format: {quality}, using best")
                return "bv*+ba/best"
        
        return "bv*+ba/best"


    # ✅ Allow UI to cancel an in-flight download
    def cancel(self):
        """Cancel the current download."""
        self.is_cancelled = True
        self.log("🛑 Download cancelled by user")
    
    def progress_hook(self, d):
        """
        Process yt-dlp progress data.
        FIXED: Properly calculates percent even when total_bytes is missing by using _percent_str fallback
        """
        if self.is_cancelled:
            raise Exception("Download cancelled by user")

        status = d.get("status")
        if status == "downloading":
            try:
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0

                # 🔴 CRITICAL FIX: Calculate percent with fallback to _percent_str
                percent = 0.0
                if total > 0:
                    percent = (downloaded / total * 100.0)
                else:
                    # Fallback: Parse yt-dlp's pre-calculated string (e.g. " 15.4%")
                    pct_str = d.get("_percent_str", "0%").strip().replace("%", "").strip()
                    try:
                        percent = float(pct_str)
                    except (ValueError, AttributeError, TypeError):
                        percent = 0.0

                # DEBUG: Log when progress_hook is called
                if int(percent) % 10 == 0 and percent > 0:
                    print(f"[PROGRESS_HOOK] Raw: percent={percent:.1f}% speed={speed} eta={eta} | Has callback: {self.progress_callback is not None}")

                if self.progress_callback:
                    self.progress_callback({
                        "status": "downloading",
                        "percent": percent,
                        "downloaded": downloaded,
                        "total": total,
                        "speed": speed,
                        "eta": eta,
                    })
            except Exception as e:
                print(f"[progress_hook error] {e}")

        elif status == "finished":
            if self.progress_callback:
                self.progress_callback({
                    "status": "finished",
                    "percent": 100.0,
                    "downloaded": d.get("downloaded_bytes") or 0,
                    "total": d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                    "speed": d.get("speed") or 0,
                    "eta": 0,
                })
    
    def download(self, url, quality="best", output_path=None, preferred_title=None, referer=None):
        """Download video. Handles both yt-dlp URLs and captured stream URLs (blob:// or direct streams)."""
        self.is_cancelled = False
        self.start_time = time.time()
        
        # ═══════════════════════════════════════════════════════════════════════
        # ENTERPRISE: URL VALIDATION & SECURITY CHECK
        # ═══════════════════════════════════════════════════════════════════════
        if self.security:
            is_valid, error_msg = self.security.validate_url(url)
            if not is_valid:
                self.log(f"🚫 Security check failed: {error_msg}")
                if self.logger:
                    self.logger.error(f"URL validation failed: {error_msg}", url=url)
                return {"success": False, "error": f"Invalid URL: {error_msg}"}
        
        # Log download start with enterprise logging
        if self.logger:
            self.logger.download_started(url, quality=quality)
        
        if not output_path:
            output_path = str(Path.home() / "Downloads")
        is_audio = (quality == "audio")
        
        # DETECT CAPTURED STREAM URLs (from browser capture)
        is_captured_stream = any(marker in url.lower() for marker in 
                                 ['blob:', 'data:', 'dua.', 'stream', '/get_file/', '.m3u8', '.mpd'])
        
        if is_captured_stream:
            # Use binary download for captured streams
            self.log(f"🎬 Detected captured stream URL - using binary download")
            downloaded_file = self._binary_download(url, output_path, preferred_title)
            if downloaded_file and os.path.exists(downloaded_file):
                size_bytes = os.path.getsize(downloaded_file)
                elapsed = max(1, int(time.time() - self.start_time))
                avg_speed = size_bytes / elapsed if size_bytes else 0
                return {
                    "success": True,
                    "info": {"title": preferred_title or "captured_video"},
                    "filesize": size_bytes,
                    "duration": 0,
                    "completion_time": elapsed,
                    "average_speed": avg_speed,
                    "final_path": downloaded_file
                }
            else:
                return {"success": False, "error": "Binary download failed"}
        
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
                if self.logger:
                    self.logger.download_failed(url, "User cancelled")
                return {"success": False, "error": "Download cancelled by user"}
            self.log(f"❌ yt-dlp failed: {emsg[:200]}")
            # Enterprise error handling
            if self.error_handler:
                self.error_handler.handle_error(e, {'url': url, 'quality': quality})
            if self.logger:
                self.logger.download_failed(url, emsg, context={'quality': quality})
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
        
        # ═══════════════════════════════════════════════════════════════════════
        # ENTERPRISE: LOG DOWNLOAD COMPLETION
        # ═══════════════════════════════════════════════════════════════════════
        if self.logger and size_bytes:
            self.logger.download_completed(
                url,
                downloaded_file,
                size_bytes,
                elapsed,
                quality=quality,
                is_audio=is_audio
            )
        
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
    
    def _binary_download(self, url, output_path, preferred_title=None):
        """Download video as binary blob (for captured stream URLs)."""
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            # Resilient session with retries
            session = requests.Session()
            retry = Retry(connect=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            # Headers to avoid blocks
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': url.split('?')[0] if '?' in url else url,
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate'
            }
            
            self.log(f"📥 Starting binary download: {url[:60]}...")
            response = session.get(url, headers=headers, stream=True, timeout=30, verify=False)
            response.raise_for_status()
            
            # Get content length
            total_size = int(response.headers.get('content-length', 0))
            if total_size:
                self.log(f"📦 Content size: {total_size/1024/1024:.1f} MB")
            
            # Detect extension from content-type or URL
            content_type = response.headers.get('content-type', '').lower()
            ext = '.mp4'
            if 'audio' in content_type or 'mp3' in content_type:
                ext = '.mp3'
            elif 'video' in content_type or 'mp4' in content_type:
                ext = '.mp4'
            elif 'webm' in content_type:
                ext = '.webm'
            elif '.m3u8' in url.lower():
                ext = '.m3u8'
            elif '.mpd' in url.lower():
                ext = '.mpd'
            
            # Generate filename
            title = self._sanitize_title(preferred_title or 'captured_video')
            filename = f"{title}{ext}"
            filepath = os.path.join(output_path, filename)
            
            # Avoid overwrite
            counter = 1
            base_name = f"{title}_"
            while os.path.exists(filepath):
                filepath = os.path.join(output_path, f"{base_name}{counter}{ext}")
                counter += 1
            
            # Download with progress
            downloaded = 0
            start_time = time.time()
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.is_cancelled:
                        os.remove(filepath)
                        return None
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            pct = (downloaded / total_size) * 100
                            elapsed_so_far = time.time() - start_time
                            speed = downloaded / elapsed_so_far if elapsed_so_far > 0 else 0
                            eta = (total_size - downloaded) / speed if speed > 0 else 0
                            
                            # Update progress bar via callback
                            if self.progress_callback:
                                self.progress_callback({
                                    'status': 'downloading',
                                    'percent': pct,
                                    'downloaded': downloaded,
                                    'total': total_size,
                                    'speed': speed,
                                    'eta': eta
                                })
                            
                            self.log(f"⬇️ {pct:.0f}% ({downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB) | Speed: {speed/1024/1024:.1f}MB/s")
            
            elapsed = time.time() - start_time
            file_size = os.path.getsize(filepath)
            
            # Final progress update
            if self.progress_callback:
                self.progress_callback({
                    'status': 'finished',
                    'percent': 100,
                    'downloaded': file_size,
                    'total': file_size,
                    'speed': file_size / elapsed if elapsed > 0 else 0,
                    'eta': 0
                })
            
            self.log(f"✅ Binary download complete: {os.path.basename(filepath)} ({file_size/1024/1024:.1f} MB in {elapsed:.0f}s)")
            
            return filepath
            
        except Exception as e:
            self.log(f"❌ Binary download failed: {e}")
            return None
    
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
                start_time = time.time()
                
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
                            
                            # Update progress bar with speed and ETA
                            if self.progress_callback and total_size > 0:
                                percent = (downloaded / total_size) * 100
                                elapsed_so_far = time.time() - start_time
                                speed = downloaded / elapsed_so_far if elapsed_so_far > 0 else 0
                                eta = (total_size - downloaded) / speed if speed > 0 else 0
                                
                                self.progress_callback({
                                    "status": "downloading",
                                    "percent": percent,
                                    "downloaded": downloaded,
                                    "total": total_size,
                                    "speed": speed,
                                    "eta": eta
                                })
                            
                            # Log every 10MB
                            if downloaded % (10 * 1024 * 1024) < (1024 * 1024):
                                if total_size > 0:
                                    pct = (downloaded / total_size) * 100
                                    self.log(f"📥 {pct:.0f}% - Downloaded {downloaded / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB")
                                else:
                                    self.log(f"📥 Downloaded {downloaded / (1024 * 1024):.1f} MB...")
                
                # Atomically move into place
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                os.replace(tmp, dest_path)
                
                # Final progress update
                final_elapsed = time.time() - start_time
                final_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                if self.progress_callback:
                    self.progress_callback({
                        "status": "finished",
                        "percent": 100,
                        "downloaded": final_size,
                        "total": final_size,
                        "speed": final_size / final_elapsed if final_elapsed > 0 else 0,
                        "eta": 0
                    })
                
                self.log(f"✅ HTTP download complete: {final_size / (1024 * 1024):.1f} MB in {final_elapsed:.0f}s")

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
        """Enhanced sanitization for cross-platform filenames."""
        if not name:
            return "video"

        import re

        # Remove HTML entities
        name = name.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

        # Remove control characters
        name = ''.join(ch for ch in name if ord(ch) >= 32 or ch in '\t\n\r')

        # Replace invalid characters
        invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        name = re.sub(invalid_chars, '_', name)

        # Collapse whitespace
        name = ' '.join(name.split())

        # Remove trailing dots/spaces
        name = name.strip(' .')

        # Check reserved names
        reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 
                   'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                   'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 
                   'LPT7', 'LPT8', 'LPT9'}

        if name.upper() in reserved:
            name = f"_{name}"

        # Limit length
        if len(name) > 200:
            name = name[:200].strip(' .')

        return name or 'video'

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
        
        # ═══════════════════════════════════════════════════════════════════════════
        # ENTERPRISE-GRADE INITIALIZATION
        # ═══════════════════════════════════════════════════════════════════════════
        
        # Load enterprise configuration
        self.config = ConfigManager.get_config()
        
        # Setup enterprise logging
        self.logger = LoggerFactory.get_logger(
            'downloader',
            config=self.config.logging.to_dict()
        )
        
        # Setup error handler
        self.error_handler = ErrorHandler(self.logger)
        
        # Setup security validator
        self.security = SecurityValidator(self.config.security.to_dict())
        
        # Setup database manager
        self.db = DatabaseManager(
            str(Path.home() / ".ultimate_downloader_v9.db")
        )
        
        # Setup downloads manager for queue-based system
        self.downloads_manager = ActiveDownloadsManager()
        
        # Setup download queue
        self.download_queue = DownloadQueue(
            max_concurrent=self.config.download.max_concurrent_downloads
        )
        
        # Setup circuit breaker for network resilience
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60
        )
        
        # Setup memory cache
        self.cache = MemoryCache(
            max_size=1000,
            ttl=self.config.performance.cache_ttl
        )
        
        self.capture_engine = None
        
        # ✅ FIRST: build the UI (this defines update_progress, creates widgets, etc.)
        self.setup_ui()
        
        # ✅ THEN: Per-download DownloadManager instances are created in start_download()
        # Do NOT create shared download_manager here - each download gets its own
        
        # Log startup
        self.logger.info("🚀 Application started", version=self.config.version, environment=self.config.environment)
        
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
        """Create main content area with new tab structure"""
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

        # Tabs container
        tabs_container = ctk.CTkFrame(
            scrollable_frame,
            fg_color="transparent"
        )
        tabs_container.pack(fill="both", expand=False, pady=(0, 10))

        # NEW TABS STRUCTURE - 3 tabs only
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
            height=500
        )
        self.tabview.pack(fill="both", expand=True)

        # Add new tabs
        self.tab_download = self.tabview.add("📥 Download")
        self.tab_in_progress = self.tabview.add("⏳ In Progress")
        self.tab_downloaded = self.tabview.add("✅ Downloaded")

        # Setup tabs
        self.setup_download_tab()
        self.setup_in_progress_tab()
        self.setup_downloaded_tab()

        # Activity log below tabs
        self.create_shared_log(scrollable_frame)

        # Start UI update loop for progress tracking
        self.update_download_displays()

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
        
        # NO PROGRESS BAR SECTION HERE - Moved to "In Progress" tab

        # Action Buttons
        button_section = ctk.CTkFrame(card, fg_color="transparent")
        button_section.pack(fill="x", padx=30, pady=(20, 30))

        # Download button (main CTA)
        self.download_btn = ctk.CTkButton(
            button_section,
            text="⬇️ Start Download",
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
        analyze_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

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
    
    def setup_in_progress_tab(self):
        """Create the In Progress tab showing all active downloads"""
        # Main container
        self.in_progress_container = ctk.CTkScrollableFrame(
            self.tab_in_progress,
            fg_color=Theme.BG_TERTIARY,
            corner_radius=Theme.RADIUS_MEDIUM
        )
        self.in_progress_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        header = ctk.CTkFrame(self.in_progress_container, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="⏳ Active Downloads",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")

        self.active_count_label = ctk.CTkLabel(
            header,
            text="0 downloads",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        self.active_count_label.pack(side="right")

        # Downloads list frame (will be populated dynamically)
        self.in_progress_list = ctk.CTkFrame(
            self.in_progress_container,
            fg_color="transparent"
        )
        self.in_progress_list.pack(fill="both", expand=True, padx=20, pady=10)

        # Empty state message
        self.empty_progress_label = ctk.CTkLabel(
            self.in_progress_list,
            text="No active downloads\n\nStart a download to see it here",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED
        )
        self.empty_progress_label.pack(expand=True, pady=50)

    def setup_downloaded_tab(self):
        """Create the Downloaded tab showing completed downloads"""
        # Main container
        self.downloaded_container = ctk.CTkScrollableFrame(
            self.tab_downloaded,
            fg_color=Theme.BG_TERTIARY,
            corner_radius=Theme.RADIUS_MEDIUM
        )
        self.downloaded_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header with clear button
        header = ctk.CTkFrame(self.downloaded_container, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="✅ Downloaded Files",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")

        clear_completed_btn = ctk.CTkButton(
            header,
            text="🗑️ Clear List",
            width=100,
            height=30,
            fg_color=Theme.ERROR,
            hover_color="#dc2626",
            corner_radius=8,
            font=Theme.FONT_SMALL,
            command=self.clear_completed_downloads
        )
        clear_completed_btn.pack(side="right")

        # Downloads list frame
        self.downloaded_list = ctk.CTkFrame(
            self.downloaded_container,
            fg_color="transparent"
        )
        self.downloaded_list.pack(fill="both", expand=True, padx=20, pady=10)

        # Empty state
        self.empty_downloaded_label = ctk.CTkLabel(
            self.downloaded_list,
            text="No completed downloads yet\n\nCompleted downloads will appear here",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED
        )
        self.empty_downloaded_label.pack(expand=True, pady=50)

    def create_download_card(self, parent, download_item, is_active=True):
        """Create a card showing download progress or completed status"""
        card = ctk.CTkFrame(
            parent,
            fg_color=Theme.BG_INPUT,
            corner_radius=Theme.RADIUS_SMALL,
            border_width=2,
            border_color=Theme.BORDER
        )
        card.pack(fill="x", pady=8)

        # Store reference for updates
        card.download_id = download_item.id

        # Content frame
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=15, pady=15)

        # Top row: Icon + Title + Status
        top_row = ctk.CTkFrame(content, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 10))

        # Icon
        icon_text = "⏳" if is_active else ("✅" if download_item.status == "completed" else "❌")
        icon_label = ctk.CTkLabel(
            top_row,
            text=icon_text,
            font=("Segoe UI", 24),
            width=40
        )
        icon_label.pack(side="left", padx=(0, 10))

        # Title and URL
        text_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True)

        title_label = ctk.CTkLabel(
            text_frame,
            text=download_item.title[:60] + ("..." if len(download_item.title) > 60 else ""),
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_PRIMARY,
            anchor="w"
        )
        title_label.pack(anchor="w")

        url_label = ctk.CTkLabel(
            text_frame,
            text=download_item.url[:50] + "...",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="w"
        )
        url_label.pack(anchor="w")

        if is_active:
            # ACTIVE DOWNLOAD CARD
            # Progress bar
            progress_bar = ctk.CTkProgressBar(
                content,
                height=15,
                progress_color=Theme.ACCENT_PRIMARY,
                fg_color=Theme.BG_SECONDARY,
                corner_radius=8
            )
            progress_bar.pack(fill="x", pady=(10, 5))
            progress_bar.set(download_item.progress / 100)
            card.progress_bar = progress_bar

            # Stats row
            stats_row = ctk.CTkFrame(content, fg_color="transparent")
            stats_row.pack(fill="x")

            # Progress percentage
            progress_label = ctk.CTkLabel(
                stats_row,
                text=f"{download_item.progress:.1f}%",
                font=Theme.FONT_SMALL,
                text_color=Theme.ACCENT_PRIMARY
            )
            progress_label.pack(side="left")
            card.progress_label = progress_label

            # Speed
            speed_mb = download_item.speed / (1024 * 1024) if download_item.speed else 0
            speed_label = ctk.CTkLabel(
                stats_row,
                text=f"⚡ {speed_mb:.2f} MB/s",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_SECONDARY
            )
            speed_label.pack(side="left", padx=15)
            card.speed_label = speed_label

            # ETA
            if download_item.eta:
                minutes, seconds = divmod(int(download_item.eta), 60)
                eta_text = f"⏱️ {minutes:02d}:{seconds:02d}"
            else:
                eta_text = "⏱️ --:--"
            eta_label = ctk.CTkLabel(
                stats_row,
                text=eta_text,
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_SECONDARY
            )
            eta_label.pack(side="left")
            card.eta_label = eta_label

            # Cancel button
            cancel_btn = ctk.CTkButton(
                stats_row,
                text="❌ Cancel",
                width=80,
                height=25,
                fg_color=Theme.ERROR,
                hover_color="#dc2626",
                corner_radius=6,
                font=Theme.FONT_SMALL,
                command=lambda: self.cancel_specific_download(download_item.id)
            )
            cancel_btn.pack(side="right")

        else:
            # COMPLETED DOWNLOAD CARD
            # File info row
            info_row = ctk.CTkFrame(content, fg_color="transparent")
            info_row.pack(fill="x", pady=(10, 5))

            # File size
            if download_item.total_bytes:
                size_mb = download_item.total_bytes / (1024 * 1024)
                size_text = f"💾 {size_mb:.1f} MB"
            else:
                size_text = "💾 Unknown size"

            size_label = ctk.CTkLabel(
                info_row,
                text=size_text,
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_SECONDARY
            )
            size_label.pack(side="left")

            # Quality
            quality_label = ctk.CTkLabel(
                info_row,
                text=f"🎯 {download_item.quality}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_SECONDARY
            )
            quality_label.pack(side="left", padx=15)

            # Status indicator
            if download_item.status == "completed":
                status_color = Theme.SUCCESS
                status_icon = "✅"
                status_text = "Completed"
            elif download_item.status == "failed":
                status_color = Theme.ERROR
                status_icon = "❌"
                status_text = f"Failed: {download_item.error_message[:30]}"
            else:
                status_color = Theme.WARNING
                status_icon = "⏹️"
                status_text = "Cancelled"

            status_label = ctk.CTkLabel(
                info_row,
                text=f"{status_icon} {status_text}",
                font=Theme.FONT_SMALL,
                text_color=status_color
            )
            status_label.pack(side="right")

            # Action buttons
            buttons_row = ctk.CTkFrame(content, fg_color="transparent")
            buttons_row.pack(fill="x", pady=(10, 0))

            # Open file button
            open_btn = ctk.CTkButton(
                buttons_row,
                text="📂 Open File",
                width=100,
                height=30,
                fg_color=Theme.SUCCESS,
                hover_color="#059669",
                corner_radius=6,
                font=Theme.FONT_SMALL,
                command=lambda: self.open_downloaded_file(download_item)
            )
            open_btn.pack(side="left", padx=(0, 5))

            # Open folder button
            folder_btn = ctk.CTkButton(
                buttons_row,
                text="📁 Open Folder",
                width=100,
                height=30,
                fg_color=Theme.INFO,
                hover_color="#2563eb",
                corner_radius=6,
                font=Theme.FONT_SMALL,
                command=lambda: self.open_file_location(download_item)
            )
            folder_btn.pack(side="left", padx=5)

            # Remove from list button
            remove_btn = ctk.CTkButton(
                buttons_row,
                text="🗑️ Remove",
                width=80,
                height=30,
                fg_color=Theme.ERROR,
                hover_color="#dc2626",
                corner_radius=6,
                font=Theme.FONT_SMALL,
                command=lambda: self.remove_from_completed(download_item.id)
            )
            remove_btn.pack(side="right")

        return card

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

        # Quality selection
        quality_section = ctk.CTkFrame(card, fg_color="transparent")
        quality_section.pack(fill="x", padx=30, pady=20)

        quality_label = ctk.CTkLabel(
            quality_section,
            text="Quality",
            font=Theme.FONT_SUBTITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        quality_label.pack(anchor="w", pady=(0, 10))

        self.batch_quality_buttons_frame = ctk.CTkFrame(
            quality_section,
            fg_color="transparent"
        )
        self.batch_quality_buttons_frame.pack(fill="x")

        if not hasattr(self, "batch_quality_var"):
            self.batch_quality_var = tk.StringVar(value="best")

        batch_qualities = [
            ("Best", "best"),
            ("1080p", "1080p"),
            ("720p", "720p"),
            ("480p", "480p"),
            ("Audio", "audio")
        ]

        for label, value in batch_qualities:
            btn = ctk.CTkRadioButton(
                self.batch_quality_buttons_frame,
                text=label,
                variable=self.batch_quality_var,
                value=value,
                font=Theme.FONT_BODY,
                fg_color=Theme.ACCENT_PRIMARY,
                hover_color=Theme.HOVER,
                border_color=Theme.BORDER,
                text_color=Theme.TEXT_PRIMARY
            )
            btn.pack(side="left", padx=10, pady=5)
        
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
            
            # Update stat cards (with null checks for widgets that may not exist yet)
            total = stats.get('total_downloads', 0)
            size_gb = stats.get('total_size', 0) / (1024**3) if stats.get('total_size') else 0
            
            # Calculate average time from completion_time
            try:
                self.db.cursor.execute('SELECT AVG(completion_time) FROM downloads WHERE status = "completed" AND completion_time > 0')
                avg_time_result = self.db.cursor.fetchone()
                avg_time = int(avg_time_result[0]) if avg_time_result and avg_time_result[0] else 0
            except:
                avg_time = 0
            
            # Safely update labels (may not exist during initialization)
            if hasattr(self, 'total_downloads_label'):
                try:
                    self.total_downloads_label.configure(text=str(total))
                except:
                    pass
            
            if hasattr(self, 'total_size_label'):
                try:
                    self.total_size_label.configure(text=f"{size_gb:.2f} GB")
                except:
                    pass
            
            if hasattr(self, 'avg_time_label'):
                try:
                    self.avg_time_label.configure(text=f"{avg_time}s")
                except:
                    pass
            
            # Load history
            self.load_history()
            
        except Exception as e:
            self.log(f"⚠️ Failed to load stats: {e}")
    
    def load_history(self):
        """Load download history"""
        try:
            # Defensive check: history_textbox may not exist during early initialization
            if not hasattr(self, 'history_textbox'):
                return
            
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
        """Thread-safe progress update from DownloadManager callbacks"""

        def _do_update():
            try:
                percent = data.get('percent', 0)
                speed = data.get('speed', 0)
                eta = data.get('eta', 0)

                # Progress bar
                self.progress_bar.set(percent / 100)

                # Status
                if percent >= 100:
                    self.status_label.configure(
                        text="Finishing...",
                        text_color=Theme.SUCCESS,
                    )
                else:
                    self.status_label.configure(
                        text=f"Downloading... {percent:.1f}%",
                        text_color=Theme.ACCENT_PRIMARY,
                    )

                # Speed
                if speed:
                    speed_mb = speed / (1024 * 1024)
                    self.speed_label.configure(text=f"Speed: {speed_mb:.2f} MB/s")

                # ETA
                if eta:
                    minutes, seconds = divmod(int(eta), 60)
                    self.eta_label.configure(text=f"ETA: {minutes:02d}:{seconds:02d}")
            except Exception as e:
                print(f"Progress update error: {e}")

        # Always marshal to Tk main thread
        self.after(0, _do_update)

    # ═══════════════════════════════════════════════════════════════════════════
    # DOWNLOAD QUEUE HELPER METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def update_download_displays(self):
        """FIX #3: Smart UI update - only update values, don't rebuild cards"""
        try:
            # Check if window still exists
            if not self.winfo_exists():
                return
            
            # Initialize card tracking on first run
            if not hasattr(self, '_card_widgets'):
                self._card_widgets = {}  # {download_id: card_frame}
            
            # Get active downloads
            active_downloads = self.downloads_manager.get_all_active()
            active_ids = {d.id for d in active_downloads}
            
            # Remove cards for completed downloads
            completed_ids = set(self._card_widgets.keys()) - active_ids
            for download_id in completed_ids:
                try:
                    card = self._card_widgets[download_id]
                    if card.winfo_exists():
                        card.destroy()
                except:
                    pass
                del self._card_widgets[download_id]
            
            # Update or create cards for active downloads
            try:
                if self.in_progress_list.winfo_exists():
                    for download in active_downloads:
                        if download.id in self._card_widgets:
                            # SMART UPDATE: Update existing card values
                            card = self._card_widgets[download.id]
                            if card.winfo_exists():
                                self.update_download_card(card, download)
                        else:
                            # Create new card and track it
                            card = self.create_download_card(self.in_progress_list, download, is_active=True)
                            self._card_widgets[download.id] = card
            except:
                pass
            
            # Update empty/count labels
            try:
                if active_downloads:
                    self.empty_progress_label.pack_forget()
                    self.active_count_label.configure(text=f"{len(active_downloads)} download(s)")
                else:
                    self.empty_progress_label.pack(expand=True, pady=50)
                    self.active_count_label.configure(text="No active downloads")
            except:
                pass
            
            # Update completed downloads (only when count changes)
            completed_downloads = self.downloads_manager.get_all_completed()
            if hasattr(self, '_last_completed_count'):
                if len(completed_downloads) != self._last_completed_count:
                    try:
                        self.refresh_completed_tab()
                    except:
                        pass
            else:
                try:
                    self.refresh_completed_tab()
                except:
                    pass
            self._last_completed_count = len(completed_downloads)

        except Exception as e:
            pass  # Silently handle errors
        finally:
            # Schedule next update (every 500ms) only if window exists
            try:
                if self.winfo_exists():
                    self.after(500, self.update_download_displays)
            except:
                pass

    def update_download_card(self, card, download_item):
        """Update an existing active-download card from DownloadItem state."""
        try:
            # ✅ UPDATE PROGRESS BAR - This is critical!
            if hasattr(card, "progress_bar"):
                try:
                    # Always clamp to 0-1 range for CTkProgressBar
                    progress_pct = float(download_item.progress or 0)
                    bar_value = max(0.0, min(1.0, progress_pct / 100.0))
                    
                    # Force update
                    card.progress_bar.set(bar_value)
                    
                    # DEBUG every 10%
                    if int(progress_pct) % 10 == 0 and progress_pct > 0:
                        print(f"[CARD UPDATE {download_item.id}] Progress: {progress_pct:.1f}% → Bar: {bar_value:.2f}")
                        
                except Exception as e:
                    print(f"[ERROR] progress_bar.set() failed: {e}")
                    import traceback
                    traceback.print_exc()

            # percentage label
            if hasattr(card, "progress_label"):
                try:
                    pct = float(download_item.progress or 0)
                    card.progress_label.configure(text=f"{pct:.1f}%")
                except Exception:
                    pass

            # speed label
            if hasattr(card, "speed_label"):
                try:
                    if download_item.speed and download_item.speed > 0:
                        mbps = download_item.speed / (1024 * 1024)
                        text = f"⚡ {mbps:.2f} MB/s"
                    else:
                        text = "⚡ 0.00 MB/s"
                    card.speed_label.configure(text=text)
                except Exception:
                    pass

            # ETA label
            if hasattr(card, "eta_label"):
                try:
                    if download_item.eta and download_item.eta > 0:
                        m, s = divmod(int(download_item.eta), 60)
                        eta_text = f"⏱️ {m:02d}:{s:02d}"
                    else:
                        eta_text = "⏱️ --:--"
                    card.eta_label.configure(text=eta_text)
                except Exception:
                    pass

        except Exception as e:
            print(f"[ERROR] update_download_card overall: {e}")
            import traceback
            traceback.print_exc()

    def refresh_completed_tab(self):
        """Refresh the Downloaded tab display"""
        try:
            # Check if window exists first
            if not self.winfo_exists():
                return
            
            # Clear existing cards with error handling
            try:
                if self.downloaded_list.winfo_exists():
                    for widget in self.downloaded_list.winfo_children():
                        try:
                            widget.destroy()
                        except:
                            pass
            except:
                return

            # Get completed downloads from manager + database
            completed_from_manager = self.downloads_manager.get_all_completed()

            # Also load from database (for persistence across app restarts)
            try:
                db_history = self.db.get_download_history(20)  # Last 20 downloads
            except:
                db_history = []

            # Combine both sources (avoid duplicates by URL)
            all_completed = {}

            # Add from manager first (most recent session)
            for download in completed_from_manager:
                all_completed[download.url] = download

            # Add from database (for historical data)
            for db_entry in db_history:
                try:
                    url = db_entry[1] if isinstance(db_entry, tuple) else db_entry.get('url')
                    if url not in all_completed:
                        # Convert DB entry to DownloadItem for consistent display
                        title = db_entry[2] if isinstance(db_entry, tuple) else db_entry.get('title')
                        quality = db_entry[4] if isinstance(db_entry, tuple) else db_entry.get('quality')
                        filepath = db_entry[5] if isinstance(db_entry, tuple) else db_entry.get('file_path')
                        filesize = db_entry[6] if isinstance(db_entry, tuple) else db_entry.get('file_size')

                        # Create DownloadItem from DB data
                        item = DownloadItem(0, url, title, quality, os.path.dirname(filepath) if filepath else "")
                        item.status = "completed"
                        item.file_path = filepath
                        item.total_bytes = filesize
                        all_completed[url] = item
                except:
                    pass

            # Display all completed downloads
            try:
                if all_completed:
                    self.empty_downloaded_label.pack_forget()
                    for download in all_completed.values():
                        try:
                            self.create_download_card(self.downloaded_list, download, is_active=False)
                        except:
                            pass
                else:
                    self.empty_downloaded_label.pack(expand=True, pady=50)
            except:
                pass

        except Exception as e:
            pass  # Silently handle errors

    def cancel_specific_download(self, download_id):
        """Cancel a specific download - PROPERLY STOPS THE DOWNLOAD"""
        try:
            download = self.downloads_manager.get_download(download_id)
            if download:
                # ✅ Mark as cancelled in item
                download.status = "cancelled"
                
                # ✅ Signal the download manager to abort
                # Each download has a download_manager_instance (added during download_worker)
                if hasattr(download, 'download_manager_instance'):
                    try:
                        download.download_manager_instance.cancel()
                    except Exception as e:
                        print(f"[cancel manager error] {e}")
                
                # ✅ Update manager status
                self.downloads_manager.update_status(download_id, "cancelled")
                
                self.log(f"🛑 Cancelled: {download.title}")
        except Exception as e:
            self.log(f"❌ Cancel error: {e}")

    def open_downloaded_file(self, download_item):
        """Open downloaded file - with file existence check"""
        try:
            if not download_item.file_path or not os.path.exists(download_item.file_path):
                messagebox.showwarning(
                    "File Not Found",
                    f"The file no longer exists:\n{download_item.file_path}\n\nIt may have been moved or deleted."
                )
                self.log(f"⚠️ File not found: {download_item.file_path}")
                return

            # Open file with default application
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', download_item.file_path])
            elif platform.system() == 'Windows':
                os.startfile(download_item.file_path)
            else:  # Linux
                subprocess.run(['xdg-open', download_item.file_path])

            self.log(f"📂 Opened: {download_item.title}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n{e}")
            self.log(f"❌ Open file error: {e}")

    def open_file_location(self, download_item):
        """Open folder containing the downloaded file"""
        try:
            if not download_item.file_path:
                messagebox.showwarning("Error", "File path not available")
                return

            folder = os.path.dirname(download_item.file_path)

            if not os.path.exists(folder):
                messagebox.showwarning(
                    "Folder Not Found",
                    f"The folder no longer exists:\n{folder}"
                )
                return

            # Open folder
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', folder])
            elif platform.system() == 'Windows':
                subprocess.run(['explorer', folder])
            else:  # Linux
                subprocess.run(['xdg-open', folder])

            self.log(f"📁 Opened folder: {folder}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder:\n{e}")
            self.log(f"❌ Open folder error: {e}")

    def remove_from_completed(self, download_id):
        """Remove download from completed list"""
        try:
            self.downloads_manager.remove_download(download_id)
            self.refresh_completed_tab()
            self.log("🗑️ Removed from list")
        except Exception as e:
            self.log(f"❌ Remove error: {e}")

    def clear_completed_downloads(self):
        """Clear all completed downloads from the list"""
        if messagebox.askyesno("Confirm", "Clear all completed downloads from the list?"):
            try:
                completed = self.downloads_manager.get_all_completed()
                for download in completed:
                    self.downloads_manager.remove_download(download.id)
                self.refresh_completed_tab()
                self.log("🗑️ Cleared completed downloads list")
            except Exception as e:
                self.log(f"❌ Clear error: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # DOWNLOAD METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def start_download(self):
        """Start download and add to queue - FIXED VERSION"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a video URL!")
            return

        quality = self.quality_var.get()
        output_path = self.path_entry.get().strip() or str(Path.home() / "Downloads")

        # Extract unique title first
        title = getattr(self, '_analyzed_title', None)

        if not title:
            self.log("🔍 Extracting video title...")
            try:
                opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', f'video_{int(time.time())}')
            except:
                title = f'video_{int(time.time())}'

        # Add to downloads manager
        download_id = self.downloads_manager.add_download(url, title, quality, output_path)

        self.log(f"⬇️ Added to queue: {title[:50]}")

        # Switch to "In Progress" tab
        self.tabview.set("⏳ In Progress")

        # ✅ FIX: Start download in background thread with PROPER callback
        def download_worker():
            download_item = None
            try:
                download_item = self.downloads_manager.get_download(download_id)
                if not download_item:
                    return

                download_item.start_time = time.time()
                download_item.status = "downloading"

                # ✅ CRITICAL FIX: Define callback FIRST, THEN create manager
                def progress_callback(d: dict):
                    """Progress callback - data is already normalized from progress_hook()"""
                    try:
                        if d.get("status") not in ("downloading", "finished"):
                            return

                        # Data is ALREADY normalized by progress_hook()
                        # Don't recalculate, just pass it through!
                        percent = d.get("percent", 0.0)
                        speed = d.get("speed", 0)
                        eta = d.get("eta", 0)
                        
                        # DEBUG: Log when callback is called with progress
                        if int(percent) % 10 == 0 and percent > 0:
                            print(f"[PROGRESS_CALLBACK {download_id}] Percent: {percent:.1f}% | Speed: {speed/1024/1024 if speed else 0:.2f}MB/s | ETA: {eta}s")
                        
                        # This updates download_item.progress
                        download_item.update_progress(d)
                        
                        if int(percent) % 10 == 0 and percent > 0:
                            print(f"[AFTER_UPDATE {download_id}] Item progress now: {download_item.progress}%")

                    except Exception as e:
                        print(f"[progress_callback error] {e}")
                        import traceback
                        traceback.print_exc()

                # ✅ NOW create manager with the defined callback
                download_manager = DownloadManager(
                    progress_callback=progress_callback,  # ✅ Direct reference, not lambda!
                    log_callback=self.log,
                    config=self.config,
                    logger=self.logger,
                    security=self.security,
                    error_handler=self.error_handler
                )

                # ✅ Store reference so cancel_specific_download can access it
                download_item.download_manager_instance = download_manager

                # Get capture data
                referer = getattr(self, "_last_capture_referer", None) if getattr(self, "_url_from_capture", False) else None
                preferred_title = getattr(self, "_last_capture_title", None) if getattr(self, "_url_from_capture", False) else None

                # Perform download
                result = download_manager.download(
                    url,
                    quality,
                    output_path,
                    preferred_title=preferred_title or title,
                    referer=referer
                )

                # Update status
                if result['success']:
                    download_item.status = "completed"
                    download_item.file_path = result.get('final_path', '')
                    download_item.total_bytes = result.get('filesize', 0)
                    download_item.end_time = time.time()
                    download_item.progress = 100

                    # Save to database
                    info = result.get('info', {})
                    self.db.add_download(
                        url=url,
                        title=download_item.title,
                        site=info.get('extractor', 'Unknown'),
                        quality=quality,
                        file_path=download_item.file_path,  # ✅ FIXED parameter name
                        file_size=download_item.total_bytes,
                        duration=info.get('duration', 0),
                        completion_time=result.get('completion_time', 0),
                        avg_speed=result.get('average_speed', 0)
                    )

                    self.after(0, lambda: self.log(f"✅ Completed: {download_item.title}"))
                else:
                    error = result.get('error', 'Unknown error')
                    download_item.status = "failed"
                    download_item.error_message = error
                    self.after(0, lambda: self.log(f"❌ Failed: {error[:100]}"))

            except Exception as e:
                if download_item:
                    download_item.status = "failed"
                    download_item.error_message = str(e)
                self.after(0, lambda: self.log(f"❌ Error: {str(e)[:100]}"))

        # Start thread
        thread = threading.Thread(target=download_worker, daemon=True)
        thread.start()

        # Store thread reference
        download_item = self.downloads_manager.get_download(download_id)
        if download_item:
            download_item.thread = thread

        # Clear URL field
        self.url_entry.delete(0, "end")
        self._analyzed_title = None
    
    def download_thread(self, url, quality, output_path):
        """Background download thread"""
        try:
            referer = None
            preferred_title = None

            if getattr(self, "_url_from_capture", False):
                referer = getattr(self, "_last_capture_referer", None)
                preferred_title = getattr(self, "_last_capture_title", None)

            result = self.download_manager.download(
                url,
                quality,
                output_path,
                preferred_title=preferred_title,
                referer=referer,
            )

            # once used, clear the flag so normal URLs don't reuse this referer
            self._url_from_capture = False
            
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
                    filepath=filepath,          # FIXED
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
            error_msg = str(e)              # capture NOW
            self.after(0, lambda msg=error_msg: self.download_complete(False, msg))

    
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
        """Cancel current download - cancels all active downloads"""
        # With the new queue system, we cancel all active downloads
        active = self.downloads_manager.get_all_active()
        if active:
            for download in active:
                self.cancel_specific_download(download.id)
            self.log("⏹️ Cancelled all active downloads")
    
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

        # init capture tracking
        if not hasattr(self, "_captured_urls"):
            self._captured_urls = set()
        self._capture_notified = False

        def on_video_found(video_url, title, page_url):
            """Callback when video is captured - debounced with referer tracking"""
            def _handle():
                # init set if needed
                if not hasattr(self, "_captured_urls"):
                    self._captured_urls = set()

                # ignore exact duplicates
                if video_url in self._captured_urls:
                    # just update field + log, no popup
                    self.url_entry.delete(0, "end")
                    self.url_entry.insert(0, video_url)
                    self.log(f"🎬 Captured (duplicate): {video_url[:60]}...")
                    return

                # remember this URL, title and its referer (page URL) for Download button
                self._captured_urls.add(video_url)
                self._last_capture_referer = page_url
                self._last_capture_title = title  # NEW: keep human title
                self._url_from_capture = True

                # update URL box and log
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, video_url)
                self.log(f"🎬 Captured: {video_url[:60]}...")

                # show popup ONLY on first capture
                if not getattr(self, "_capture_notified", False):
                    self._capture_notified = True
                    messagebox.showinfo("Captured!", f"Video stream captured!\n\n{title}")


            self.after(0, _handle)

        def capture_thread():
            try:
                engine = BrowserCaptureEngine(
                    log_fn=lambda msg: self.after(0, lambda: self.log(msg)),
                    on_found=on_video_found
                )
                self.capture_engine = engine
                engine.start(url, headless=False, timeout_sec=300)
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.log(f"❌ Capture error: {error_msg}"))
                self.after(0, lambda: messagebox.showerror("Error", f"Browser capture failed:\n{error_msg}"))
        
        threading.Thread(target=capture_thread, daemon=True).start()
    
    def start_batch_download(self):
        """Start batch download - uses queue system like single download"""
        urls_text = self.batch_textbox.get("1.0", "end").strip()
        
        if not urls_text:
            messagebox.showwarning("Warning", "Please enter URLs (one per line)!")
            return
        
        urls = [line.strip() for line in urls_text.split('\n') if line.strip() and 'http' in line]
        
        if not urls:
            messagebox.showwarning("Warning", "No valid URLs found!")
            return
        
        self.log(f"📋 Starting batch download: {len(urls)} videos")
        
        quality = self.batch_quality_var.get() if hasattr(self, "batch_quality_var") else self.quality_var.get()
        output_path = self.path_entry.get().strip() or str(Path.home() / "Downloads")
        
        # Add all URLs to queue (this will start downloads automatically)
        for url in urls:
            try:
                # Extract title for each URL
                title = f'batch_video_{int(time.time())}'
                try:
                    opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', title)
                except:
                    pass
                
                # Add to downloads manager
                download_id = self.downloads_manager.add_download(url, title, quality, output_path)
                
                # Start download in background
                def batch_download_worker(url_to_download=url, title_to_use=title, download_id_to_use=download_id):
                    download_item = None
                    try:
                        download_item = self.downloads_manager.get_download(download_id_to_use)
                        if not download_item:
                            return
                        
                        download_item.start_time = time.time()
                        download_item.status = "downloading"
                        
                        # Define callback first
                        def batch_progress_callback(data):
                            """Progress callback for batch downloads"""
                            try:
                                downloaded = data.get('downloaded', 0) or data.get('downloaded_bytes', 0) or 0
                                total = data.get('total', 0) or data.get('total_bytes', 0) or data.get('total_bytes_estimate', 0) or 0
                                speed = data.get('speed', 0) or data.get('_speed', 0) or 0
                                eta = data.get('eta', 0) or data.get('_eta', 0) or 0
                                status = data.get('status', 'downloading')
                                
                                if total > 0 and downloaded >= 0:
                                    percent = min(100.0, (downloaded / total * 100))
                                else:
                                    percent = 0.0
                                
                                normalized = {
                                    'status': status,
                                    'percent': percent,
                                    'downloaded': downloaded,
                                    'total': total,
                                    'speed': speed,
                                    'eta': eta
                                }
                                download_item.update_progress(normalized)
                            except Exception as e:
                                print(f"[BATCH PROGRESS ERROR] {e}")
                        
                        # Create manager for this download
                        batch_manager = DownloadManager(
                            progress_callback=batch_progress_callback,
                            log_callback=self.log,
                            config=self.config,
                            logger=self.logger,
                            security=self.security,
                            error_handler=self.error_handler
                        )
                        
                        result = batch_manager.download(
                            url_to_download,
                            quality,
                            output_path,
                            preferred_title=title_to_use
                        )
                        
                        if result['success']:
                            download_item.status = "completed"
                            download_item.file_path = result.get('final_path', '')
                            download_item.total_bytes = result.get('filesize', 0)
                            download_item.end_time = time.time()
                            download_item.progress = 100
                            
                            info = result.get('info', {})
                            self.db.add_download(
                                url=url_to_download,
                                title=download_item.title,
                                site=info.get('extractor', 'Unknown'),
                                quality=quality,
                                file_path=download_item.file_path,
                                file_size=download_item.total_bytes,
                                duration=info.get('duration', 0),
                                completion_time=result.get('completion_time', 0),
                                avg_speed=result.get('average_speed', 0)
                            )
                            self.after(0, lambda: self.log(f"✅ Batch item success: {title_to_use[:50]}"))
                        else:
                            error = result.get('error', 'Unknown error')
                            download_item.status = "failed"
                            download_item.error_message = error
                            self.after(0, lambda: self.log(f"❌ Batch item failed: {error[:100]}"))
                    
                    except Exception as e:
                        if download_item:
                            download_item.status = "failed"
                            download_item.error_message = str(e)
                        self.after(0, lambda: self.log(f"❌ Batch error: {str(e)[:100]}"))
                
                thread = threading.Thread(target=batch_download_worker, daemon=True)
                thread.start()
                
                download_item = self.downloads_manager.get_download(download_id)
                if download_item:
                    download_item.thread = thread
                    
            except Exception as e:
                self.log(f"❌ Error adding to batch: {e}")
        
        # Switch to In Progress tab
        self.tabview.set("⏳ In Progress")
        self.log(f"📊 Queued all {len(urls)} downloads")
    
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
        # Cancel all active downloads gracefully
        active = self.downloads_manager.get_all_active()
        if active:
            if messagebox.askyesno("Confirm Exit", f"{len(active)} download(s) in progress. Cancel and exit?"):
                for download in active:
                    self.cancel_specific_download(download.id)
                if self.capture_engine:
                    try:
                        self.capture_engine.stop()
                    except:
                        pass
                self.db.close()
                self.destroy()
            # else: User cancelled exit
        else:
            if self.capture_engine:
                try:
                    self.capture_engine.stop()
                except:
                    pass
            # ═══════════════════════════════════════════════════════════════════════
            # ENTERPRISE: GRACEFUL SHUTDOWN
            # ═══════════════════════════════════════════════════════════════════════
            try:
                self.db.close()
                if self.logger:
                    self.logger.info("🛑 Application closed")
            except:
                pass
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
    
    # Launch the application
    app = UltimateDownloaderModern()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

