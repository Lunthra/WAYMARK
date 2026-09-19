# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent
APP_ROOT = PROJECT_ROOT / "app"

hiddenimports = [
    "app.backend.core.bridge_server",
    "app.backend.core.desktop_api",
    "app.backend.core.waymark_core",
    "app.backend.core.credentials",
    "app.backend.core.runtime_paths",
    "app.backend.services.mal",
    "app.backend.services.serializd",
    "app.backend.services.tmdb",
    "app.backend.services.auth",
    "app.backend.data.notes",
]

try:
    hiddenimports += collect_submodules("playwright")
except Exception:
    pass

a = Analysis(
    [str(APP_ROOT / "backend" / "core" / "bridge_server.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WAYMARK-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
