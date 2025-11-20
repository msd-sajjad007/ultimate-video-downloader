#!/bin/bash
# ============================================================================
# Build Script for Ultimate Video Downloader - Enterprise Edition (Linux/Mac)
# ============================================================================

echo ""
echo "========================================================================"
echo "Building Ultimate Video Downloader - Enterprise Edition"
echo "========================================================================"
echo ""

# Check if PyInstaller is installed
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "ERROR: PyInstaller not found!"
    echo ""
    echo "Installing PyInstaller..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install PyInstaller"
        exit 1
    fi
fi

# Clean previous builds
if [ -d "build" ]; then
    echo "Cleaning previous build..."
    rm -rf build
fi
if [ -d "dist" ]; then
    echo "Cleaning previous dist..."
    rm -rf dist
fi

# Build the executable
echo ""
echo "Building executable..."
echo ""
pyinstaller video_downloader_ENTERPRISE.spec

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================================================"
    echo "BUILD FAILED!"
    echo "========================================================================"
    exit 1
fi

echo ""
echo "========================================================================"
echo "BUILD SUCCESSFUL!"
echo "========================================================================"
echo ""
echo "Executable location: dist/UltimateVideoDownloader"
echo ""
echo "You can now run: ./dist/UltimateVideoDownloader"
echo ""

# Make executable
chmod +x dist/UltimateVideoDownloader

# Optional: Copy config files
if [ -f "config.json" ]; then
    echo "Copying config.json to dist folder..."
    cp config.json dist/
fi

echo "Done!"
