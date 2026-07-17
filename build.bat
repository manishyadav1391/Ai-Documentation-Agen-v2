@echo off
echo =======================================================
echo             DocBot Production Build Script
echo =======================================================
echo.
echo Cleaning old build directories...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo Installing/upgrading PyInstaller...
pip install -q pyinstaller

echo.
echo Executing PyInstaller compilation...
python -m PyInstaller --clean docbot.spec

echo.
echo =======================================================
echo Build complete! Executable is located in: dist\DocBot
echo =======================================================
