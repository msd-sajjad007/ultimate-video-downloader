# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATIC DEPENDENCY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

# Find customtkinter themes
try:
    import customtkinter
    CUSTOMTKINTER_PATH = Path(customtkinter.__path__[0])
    customtkinter_datas = [(str(CUSTOMTKINTER_PATH / 'assets'), 'customtkinter/assets')]
    print(f"✅ Found customtkinter at: {CUSTOMTKINTER_PATH}")
except ImportError:
    customtkinter_datas = []
    print("⚠️ customtkinter not found")

# Find Playwright browser
try:
    import playwright
    PLAYWRIGHT_PATH = Path(playwright.__file__).parent
    playwright_driver = PLAYWRIGHT_PATH / 'driver'
    
    if playwright_driver.exists():
        playwright_datas = [(str(playwright_driver), 'playwright/driver')]
        print(f"✅ Found Playwright at: {playwright_driver}")
    else:
        playwright_datas = []
        print("⚠️ Playwright driver not found")
        print("   Run: set PLAYWRIGHT_BROWSERS_PATH=0 && playwright install chromium")
except ImportError:
    playwright_datas = []
    print("⚠️ Playwright not installed")

block_cipher = None

a = Analysis(
    ['video_downloader.py'],
    pathex=[],
    binaries=[],
    datas=customtkinter_datas + playwright_datas,
    hiddenimports=[
        # GUI Framework
        'customtkinter',
        'tkinter',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.ttk',
        'tkinter.font',
        'tkinter.scrolledtext',
        
        # Video Downloading
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.extractor.common',
        'yt_dlp.extractor.youtube',
        'yt_dlp.extractor.generic',
        'yt_dlp.downloader',
        'yt_dlp.downloader.http',
        'yt_dlp.downloader.fragment',
        'yt_dlp.postprocessor',
        'yt_dlp.postprocessor.ffmpeg',
        'yt_dlp.postprocessor.common',
        'yt_dlp.utils',
        'yt_dlp.compat',
        
        # Browser Automation
        'playwright',
        'playwright.sync_api',
        'playwright._impl',
        'playwright._impl._driver',
        'playwright._impl._api_structures',
        'playwright._impl._api_types',
        
        # Database
        'sqlite3',
        
        # Utilities
        'pyperclip',
        'PIL',
        'PIL.Image',
        'PIL._tkinter_finder',
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
        'websockets',
        'greenlet',
        'pyee',
        'http.cookiejar',
        'json',
        'datetime',
        'pathlib',
        'threading',
        'queue',
        're',
        'time',
        'platform',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused heavy packages to reduce size
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'pytest',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicates
a.datas = list({tuple(d) for d in a.datas})
a.binaries = list({tuple(b) for b in a.binaries})

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE EXE FILE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='UltimateVideoDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add .ico file path here if you have one
)
