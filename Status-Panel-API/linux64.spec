import os
block_cipher = None


raw_datas = [
    ('config.json', '.'),
    ('logs', 'logs') if os.path.exists('logs') else ()  
]

filtered_datas = [item for item in raw_datas if item]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=filtered_datas, 
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


exe_name = 'api_linux'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
