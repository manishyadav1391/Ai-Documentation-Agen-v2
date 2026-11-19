# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DocBot (one-folder build).
# Build from a CLEAN virtual environment (see build.bat) so that only DocBot's
# own dependencies are bundled. Building from a global Python picks up every
# installed package (torch, transformers, OpenCV, ...) and gave a 1.4 GB folder.
#
# Output: dist\DocBot\DocBot.exe + dist\DocBot\_internal\
# Chromium is NOT bundled here; build.bat stages it in dist\DocBot\browsers and
# installer\DocBot.iss ships it, so recording works without a download.
import os

block_cipher = None
APP_VERSION = os.environ.get("DOCBOT_VERSION", "3.1.0")

a = Analysis(
    ['launcher_entry.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('clients', 'clients'),
        ('content', 'content'),
        ('styles', 'styles'),
        ('config.yaml', '.'),
        ('USER_GUIDE.md', '.'),
        ('prompts', 'prompts'),
        ('providers/prompts', 'providers/prompts'),
        ('docbot/recorder/injected.js', 'docbot/recorder'),
        ('assets/docbot.ico', 'assets'),
        ('assets/docbot.png', 'assets'),
    ],
    hiddenimports=[
        'playwright.sync_api',
        'loguru',
        'yaml',
        'docx',
        'httpx',
        'pydantic',
        'dotenv',
        'PIL.ImageTk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Never ship test tooling or optional heavy libraries.
    excludes=['pytest', '_pytest', 'pluggy', 'iniconfig', 'fitz', 'pymupdf', 'pdf2image',
              'numpy', 'torch', 'cv2', 'scipy', 'pandas', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


def _version_info():
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo,
                                                     StringTable, StringStruct, VarFileInfo, VarStruct)
    nums = tuple(int(x) for x in (APP_VERSION.split(".") + ["0", "0", "0"])[:4])
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums, mask=0x3F, flags=0x0, OS=0x40004,
                          fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[StringFileInfo([StringTable('040904B0', [
                  StringStruct('CompanyName', 'Silver Touch Technologies Ltd.'),
                  StringStruct('FileDescription', 'DocBot - user manual generator'),
                  StringStruct('FileVersion', APP_VERSION),
                  StringStruct('InternalName', 'DocBot'),
                  StringStruct('OriginalFilename', 'DocBot.exe'),
                  StringStruct('ProductName', 'DocBot'),
                  StringStruct('ProductVersion', APP_VERSION)])]),
              VarFileInfo([VarStruct('Translation', [1033, 1200])])])


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DocBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-packed DLLs trigger antivirus false positives
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/docbot.ico',
    version=_version_info(),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DocBot',
)
