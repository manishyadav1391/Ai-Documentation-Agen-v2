# -*- mode: python ; coding: utf-8 -*-
import os
import setuptools

setuptools_dir = os.path.dirname(setuptools.__file__)
lorem_path = os.path.join(setuptools_dir, '_vendor', 'jaraco', 'text', 'Lorem ipsum.txt')

block_cipher = None

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
        (lorem_path, 'setuptools/_vendor/jaraco/text'),
        ('docbot/recorder/injected.js', 'docbot/recorder'),
    ],
    hiddenimports=[
        'playwright.sync_api',
        'loguru',
        'yaml',
        'docx',
        'jinja2',
        'httpx',
        'pydantic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DocBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DocBot',
)
