# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

project_dir = os.path.abspath(SPECPATH)

a = Analysis(
    ['hikvision_mac_app/main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[],
    hiddenimports=[
        'hikvision_mac_app',
        'hikvision_mac_app.web_server',
        'hikvision_mac_app.core',
        'hikvision_mac_app.core.scanner',
        'hikvision_mac_app.core.sadp_protocol',
        'http.server',
        'urllib.request',
        'urllib.error',
        'ipaddress',
        'concurrent.futures',
        'threading',
        'socket',
        'json',
        'xml.etree.ElementTree',
        'webbrowser',
        'subprocess',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'PIL'],
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
    name='HikvisionManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    upx=False,
    upx_exclude=[],
    name='HikvisionManager',
)

app = BUNDLE(
    coll,
    name='海康威视管理工具.app',
    icon='build_assets/AppIcon.icns',
    bundle_identifier='com.hikvision.mactool',
    info_plist={
        'CFBundleName': '海康威视管理工具',
        'CFBundleDisplayName': '海康威视管理工具',
        'CFBundleIdentifier': 'com.hikvision.mactool',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': '????',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15.0',
        'NSLocalNetworkUsageDescription': '海康威视管理工具需要访问本地网络以搜索和管理局域网摄像头设备',
        'NSHumanReadableCopyright': 'Copyright © 2026 Hikvision Mac Tool. All rights reserved.',
    },
)
