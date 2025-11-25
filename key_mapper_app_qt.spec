# -*- mode: python ; coding: utf-8 -*-
import re

# Function to parse metadata from the script
def get_metadata(script_path):
    metadata = {}
    with open(script_path, 'r') as f:
        content = f.read()
        for key in ['__company__', '__product__', '__version__', '__description__', '__copyright__', '__internal_name__']:
            match = re.search(f"^{key}\\s*=\\s*['\"]([^'\"]*)['\"]", content, re.M)
            if match:
                metadata[key] = match.group(1)
    return metadata

script_name = 'key_mapper_app_qt.py'
metadata = get_metadata(script_name)

a = Analysis(
    ['key_mapper_app_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('S-Mapper-logo - 256.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=metadata.get('__internal_name__', 'S-Mapper'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='S-Mapper-logo - 256.png',
    version_info={
        'string': {
            'CompanyName': metadata.get('__company__'),
            'FileDescription': metadata.get('__description__'),
            'InternalName': metadata.get('__internal_name__'),
            'LegalCopyright': metadata.get('__copyright__'),
            'ProductName': metadata.get('__product__'),
            'ProductVersion': metadata.get('__version__')
        },
        'fixed': {
            'product_version': metadata.get('__version__', '0.0.0.0').replace('.', ','),
        }
    }
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=metadata.get('__internal_name__', 'S-Mapper'),
)
