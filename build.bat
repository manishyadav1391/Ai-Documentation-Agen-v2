@echo off
setlocal
cd /d "%~dp0"
echo =======================================================
echo             DocBot Production Build
echo =======================================================
echo.
rem Uses Python 3.14 (or the newest "py" launcher Python) only to create the
rem clean build environment .buildenv; everything else runs inside it.
set "PYEXE=python"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3.14 -c "pass" >nul 2>nul && (set "PYEXE=py -3.14") || (set "PYEXE=py -3")
)
echo Using: %PYEXE%
%PYEXE% build_exe.py %*
if errorlevel 1 (
    echo.
    echo BUILD FAILED - see messages above.
    exit /b 1
)
echo.
echo =======================================================
echo  Build complete: dist\DocBot\DocBot.exe
echo  Next: open installer\DocBot.iss in Inno Setup and press Compile.
echo =======================================================
endlocal
