@echo off
REM ============================================================================
REM Build Script for Ultimate Video Downloader - Enterprise Edition (Windows)
REM ============================================================================

echo.
echo ============================================================================
echo Building Ultimate Video Downloader - Enterprise Edition
echo ============================================================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo ERROR: PyInstaller not found!
    echo.
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Clean previous builds
if exist "build" (
    echo Cleaning previous build...
    rmdir /s /q build
)
if exist "dist" (
    echo Cleaning previous dist...
    rmdir /s /q dist
)

REM Build the executable
echo.
echo Building executable...
echo.
pyinstaller video_downloader_ENTERPRISE.spec

if errorlevel 1 (
    echo.
    echo ============================================================================
    echo BUILD FAILED!
    echo ============================================================================
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo BUILD SUCCESSFUL!
echo ============================================================================
echo.
echo Executable location: dist\UltimateVideoDownloader.exe
echo.
echo You can now run: dist\UltimateVideoDownloader.exe
echo.

REM Optional: Copy config files
if exist "config.json" (
    echo Copying config.json to dist folder...
    copy config.json dist\
)

pause
