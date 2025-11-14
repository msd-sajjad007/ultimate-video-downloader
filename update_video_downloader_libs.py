#!/usr/bin/env python3
"""
Video Downloader Library Updater
Standalone tool to update all dependencies used by UltimateVideoDownloader
"""

import subprocess
import sys
import os
from pathlib import Path
import time
from datetime import datetime

class LibraryUpdater:
    """Updates all libraries used by the video downloader"""
    
    # All libraries used in the video downloader
    REQUIRED_LIBRARIES = [
        'yt-dlp',           # Video downloading
        'playwright',       # Browser automation
        'customtkinter',    # Modern GUI framework
        'Pillow',           # Image processing
        'requests',         # HTTP library
        'pyperclip',        # Clipboard operations
        'urllib3',          # HTTP client
        'certifi',          # SSL certificates
        'charset-normalizer', # Character encoding
        'idna',             # Domain name handling
        'websockets',       # WebSocket support
        'greenlet',         # Async support
        'pyee',             # Event emitters
    ]
    
    def __init__(self):
        self.log_file = Path.home() / "video_downloader_update.log"
        self.success_count = 0
        self.fail_count = 0
        self.skipped_count = 0
    
    def log(self, message):
        """Log to console and file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_msg + "\n")
        except Exception:
            pass
    
    def check_pip(self):
        """Verify pip is available"""
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.log(f"✅ pip found: {result.stdout.strip()}")
                return True
            else:
                self.log("❌ pip not working properly")
                return False
        except Exception as e:
            self.log(f"❌ pip check failed: {e}")
            return False
    
    def upgrade_pip(self):
        """Upgrade pip itself"""
        self.log("="*80)
        self.log("🔄 Upgrading pip...")
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                self.log("✅ pip upgraded successfully")
                return True
            else:
                self.log(f"⚠️ pip upgrade had issues: {result.stderr[:200]}")
                return False
        except Exception as e:
            self.log(f"❌ pip upgrade failed: {e}")
            return False
    
    def update_library(self, library_name):
        """Update a single library"""
        self.log("="*80)
        self.log(f"🔄 Updating {library_name}...")
        
        try:
            # Run pip install --upgrade
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', library_name],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes max per library
            )
            
            if result.returncode == 0:
                # Check if actually updated or already satisfied
                output = result.stdout.lower()
                
                if 'successfully installed' in output or 'successfully upgraded' in output:
                    # Extract version if possible
                    for line in result.stdout.split('\n'):
                        if library_name.lower() in line.lower():
                            self.log(f"✅ {library_name} updated: {line.strip()}")
                            break
                    else:
                        self.log(f"✅ {library_name} updated successfully")
                    self.success_count += 1
                    return True
                
                elif 'requirement already satisfied' in output or 'already up-to-date' in output:
                    self.log(f"ℹ️ {library_name} already up-to-date")
                    self.skipped_count += 1
                    return True
                
                else:
                    self.log(f"✅ {library_name} processed")
                    self.success_count += 1
                    return True
            
            else:
                error_msg = result.stderr[:300] if result.stderr else "Unknown error"
                self.log(f"❌ {library_name} failed: {error_msg}")
                self.fail_count += 1
                return False
        
        except subprocess.TimeoutExpired:
            self.log(f"⏱️ {library_name} update timed out (5 min limit)")
            self.fail_count += 1
            return False
        
        except Exception as e:
            self.log(f"❌ {library_name} error: {str(e)[:200]}")
            self.fail_count += 1
            return False
    
    def install_playwright_browsers(self):
        """Install Playwright browsers after updating playwright"""
        self.log("="*80)
        self.log("🌐 Installing Playwright browsers (Chromium)...")
        
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'playwright', 'install', 'chromium'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes for browser download
            )
            
            if result.returncode == 0:
                self.log("✅ Playwright Chromium browser installed")
                return True
            else:
                self.log(f"⚠️ Playwright browser install had issues: {result.stderr[:200]}")
                return False
        
        except subprocess.TimeoutExpired:
            self.log("⏱️ Playwright browser install timed out")
            return False
        
        except Exception as e:
            self.log(f"❌ Playwright browser install failed: {e}")
            return False
    
    def run_full_update(self):
        """Run complete update process"""
        start_time = time.time()
        
        self.log("="*80)
        self.log("🚀 VIDEO DOWNLOADER LIBRARY UPDATER")
        self.log("="*80)
        self.log(f"Python: {sys.version}")
        self.log(f"Executable: {sys.executable}")
        self.log(f"Log file: {self.log_file}")
        self.log("")
        
        # Step 1: Check pip
        if not self.check_pip():
            self.log("\n❌ FATAL: pip not available. Cannot continue.")
            return False
        
        # Step 2: Upgrade pip
        self.upgrade_pip()
        time.sleep(1)
        
        # Step 3: Update all libraries
        self.log("\n" + "="*80)
        self.log(f"📦 Updating {len(self.REQUIRED_LIBRARIES)} libraries...")
        self.log("="*80)
        
        for i, library in enumerate(self.REQUIRED_LIBRARIES, 1):
            self.log(f"\n[{i}/{len(self.REQUIRED_LIBRARIES)}] Processing: {library}")
            self.update_library(library)
            time.sleep(0.5)  # Small delay between updates
        
        # Step 4: Install Playwright browsers
        if 'playwright' in self.REQUIRED_LIBRARIES:
            self.install_playwright_browsers()
        
        # Final summary
        elapsed = time.time() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        
        self.log("\n" + "="*80)
        self.log("📊 UPDATE SUMMARY")
        self.log("="*80)
        self.log(f"✅ Successfully updated: {self.success_count}")
        self.log(f"ℹ️ Already up-to-date: {self.skipped_count}")
        self.log(f"❌ Failed: {self.fail_count}")
        self.log(f"⏱️ Total time: {minutes}m {seconds}s")
        self.log(f"📝 Full log: {self.log_file}")
        self.log("="*80)
        
        if self.fail_count == 0:
            self.log("\n🎉 All libraries updated successfully!")
            return True
        else:
            self.log(f"\n⚠️ {self.fail_count} libraries had issues. Check log for details.")
            return False


def main():
    """Main entry point"""
    try:
        updater = LibraryUpdater()
        success = updater.run_full_update()
        
        # Wait for user input before closing
        print("\n" + "="*80)
        input("Press ENTER to exit...")
        
        sys.exit(0 if success else 1)
    
    except KeyboardInterrupt:
        print("\n\n🛑 Update cancelled by user")
        input("Press ENTER to exit...")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {e}")
        input("Press ENTER to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
