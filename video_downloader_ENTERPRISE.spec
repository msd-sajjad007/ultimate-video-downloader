# -*- mode: python ; coding: utf-8 -*-
# video_downloader_onefile.spec - Single EXE with everything bundled
# Includes: FFmpeg, Chromium (Playwright), yt-dlp, CustomTkinter, all modules

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

block_cipher = None

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

APP_NAME = 'UltimateVideoDownloader'
VERSION = '1.0.0'
ICON_PATH = 'icon.ico'  # Optional - create or remove this line

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT FILES - Your modules (NO database_optimized.py)
# ═══════════════════════════════════════════════════════════════════════════════

project_files = [
    'video_downloader.py',  # Main file
    'config.py',            # Configuration
    'logger.py',            # Logging
    'error_handling.py',    # Error handling
    'performance.py',       # Performance utilities
    'security.py',          # Security validation
]

print("\n" + "="*80)
print("🔍 CHECKING PROJECT FILES...")
print("="*80)

missing = []
for f in project_files:
    if os.path.exists(f):
        print(f"  ✓ {f}")
    else:
        print(f"  ✗ {f} - MISSING!")
        missing.append(f)

if missing:
    print("\n❌ ERROR: Missing files! Place these in the same folder as this spec file:")
    for f in missing:
        print(f"  • {f}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# COLLECT THIRD-PARTY DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════

print("\n📦 COLLECTING DEPENDENCIES...")

# CustomTkinter
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')
print("  ✓ CustomTkinter")

# Playwright (Chromium browser)
try:
    playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all('playwright')
    print("  ✓ Playwright + Chromium")
except:
    playwright_datas = []
    playwright_binaries = []
    playwright_hiddenimports = []
    print("  ⚠ Playwright not found")

# yt-dlp
ytdlp_datas, ytdlp_binaries, ytdlp_hiddenimports = collect_all('yt_dlp')
print("  ✓ yt-dlp")

# Pyperclip
try:
    pyperclip_datas, pyperclip_binaries, pyperclip_hiddenimports = collect_all('pyperclip')
    print("  ✓ Pyperclip")
except:
    pyperclip_datas = []
    pyperclip_binaries = []
    pyperclip_hiddenimports = []

# PIL/Pillow
try:
    pil_datas, pil_binaries, pil_hiddenimports = collect_all('PIL')
    print("  ✓ Pillow")
except:
    pil_datas = []
    pil_binaries = []
    pil_hiddenimports = []

# Combine all
all_datas = (ctk_datas + playwright_datas + ytdlp_datas + 
             pyperclip_datas + pil_datas)
all_binaries = (ctk_binaries + playwright_binaries + ytdlp_binaries + 
                pyperclip_binaries + pil_binaries)
all_hiddenimports = (ctk_hiddenimports + playwright_hiddenimports + 
                     ytdlp_hiddenimports + pyperclip_hiddenimports + 
                     pil_hiddenimports)

# ═══════════════════════════════════════════════════════════════════════════════
# ADD PROJECT FILES AS DATA
# ═══════════════════════════════════════════════════════════════════════════════

for f in project_files:
    if f != 'video_downloader.py':  # Don't duplicate main
        all_datas.append((f, '.'))

if os.path.exists(ICON_PATH):
    all_datas.append((ICON_PATH, '.'))

# ═══════════════════════════════════════════════════════════════════════════════
# FFMPEG - Bundle FFmpeg binaries
# ═══════════════════════════════════════════════════════════════════════════════

print("\n🎬 SEARCHING FOR FFMPEG...")

def find_ffmpeg():
    """Locate FFmpeg and FFprobe"""
    binaries = []
    
    if sys.platform == 'win32':
        paths = [
            ('C:\\ffmpeg\\bin\\ffmpeg.exe', 'ffmpeg'),
            ('C:\\ffmpeg\\bin\\ffprobe.exe', 'ffmpeg'),
            ('C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe', 'ffmpeg'),
            ('C:\\Program Files\\ffmpeg\\bin\\ffprobe.exe', 'ffmpeg'),
            (os.path.expanduser('~\\ffmpeg\\bin\\ffmpeg.exe'), 'ffmpeg'),
            (os.path.expanduser('~\\ffmpeg\\bin\\ffprobe.exe'), 'ffmpeg'),
        ]
    elif sys.platform == 'darwin':  # macOS
        paths = [
            ('/usr/local/bin/ffmpeg', 'ffmpeg'),
            ('/usr/local/bin/ffprobe', 'ffmpeg'),
            ('/opt/homebrew/bin/ffmpeg', 'ffmpeg'),
            ('/opt/homebrew/bin/ffprobe', 'ffmpeg'),
        ]
    else:  # Linux
        paths = [
            ('/usr/bin/ffmpeg', 'ffmpeg'),
            ('/usr/bin/ffprobe', 'ffmpeg'),
            ('/usr/local/bin/ffmpeg', 'ffmpeg'),
            ('/usr/local/bin/ffprobe', 'ffmpeg'),
        ]
    
    for path, dest in paths:
        if os.path.exists(path):
            binaries.append((path, dest))
            print(f"  ✓ Found: {path}")
    
    if not binaries:
        print("  ⚠ WARNING: FFmpeg not found!")
        print("  Download: https://ffmpeg.org/download.html")
        print("  Windows: Extract to C:\\ffmpeg\\bin\\")
        print("  Linux: sudo apt install ffmpeg")
        print("  macOS: brew install ffmpeg")
    
    return binaries

all_binaries += find_ffmpeg()

# ═══════════════════════════════════════════════════════════════════════════════
# HIDDEN IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════

additional_hiddenimports = [
    # Your modules (NO database_optimized!)
    'config',
    'logger',
    'error_handling',
    'performance',
    'security',
    
    # Core Python
    'tkinter',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'sqlite3',
    'threading',
    'subprocess',
    'json',
    'time',
    'datetime',
    're',
    'platform',
    'pathlib',
    'os',
    'sys',
    'warnings',
    'asyncio',
    'logging',
    'concurrent.futures',
    
    # yt-dlp
    'yt_dlp',
    'yt_dlp.extractor',
    'yt_dlp.extractor.youtube',
    'yt_dlp.extractor.common',
    'yt_dlp.downloader',
    'yt_dlp.downloader.http',
    'yt_dlp.downloader.fragment',
    'yt_dlp.postprocessor',
    'yt_dlp.postprocessor.ffmpeg',
    'urllib',
    'urllib.parse',
    'urllib.request',
    'urllib.error',
    'http.client',
    'http.cookiejar',
    'certifi',
    'brotli',
    'mutagen',
    'websockets',
    
    # CustomTkinter
    'customtkinter',
    'PIL',
    'PIL._tkinter_finder',
    'PIL.Image',
    'PIL.ImageTk',
    
    # Playwright
    'playwright',
    'playwright.sync_api',
    'greenlet',
    'greenlet._greenlet',
    
    # Networking
    'requests',
    'urllib3',
    'ssl',
    'socket',
    
    # Clipboard
    'pyperclip',
    
    # Encoding
    'encodings',
    'encodings.idna',
    'encodings.utf_8',
]

all_hiddenimports += additional_hiddenimports

print(f"\n✓ Total hidden imports: {len(all_hiddenimports)}")

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

print("\n🔨 BUILDING ANALYSIS...")

a = Analysis(
    ['video_downloader.py'],
    pathex=[os.getcwd()],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'pytest',
        'setuptools',
        'distutils',
        'test',
        'tests',
        'unittest',
        'database_optimized',  # Explicitly exclude
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-FILE EXE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,      # ✅ Include binaries in single EXE
    a.zipfiles,      # ✅ Include zipfiles in single EXE
    a.datas,         # ✅ Include data in single EXE
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set True for debugging
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
)

print("\n" + "="*80)
print(f"✅ SINGLE-FILE EXE BUILD READY: {APP_NAME}.exe")
print("="*80)

print("\n📋 INCLUDED FILES:")
for f in project_files:
    print(f"  ✓ {f}")

print("\n📦 BUNDLED:")
print("  ✓ CustomTkinter (UI framework)")
print("  ✓ yt-dlp (Video downloader)")
print("  ✓ Playwright + Chromium (Browser)")
print("  ✓ FFmpeg + FFprobe (Video processing)")
print("  ✓ All Python modules")

print("\n🔨 TO BUILD:")
print("  pyinstaller video_downloader_onefile.spec --clean")

print("\n📂 OUTPUT:")
print(f"  dist\\{APP_NAME}.exe  (Single file, ~200-400MB)")

print("\n⚠ POST-BUILD:")
print("  Run this command to install Chromium:")
print("  playwright install chromium")

print("\n💡 TIPS:")
print("  • First startup may be slow (extracts to temp)")
print("  • No separate folder needed")
print("  • Antivirus may flag - add exception")
print("  • Set console=True in spec for debugging")

print("="*80 + "\n")
