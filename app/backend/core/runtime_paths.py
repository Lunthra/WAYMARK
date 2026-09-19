"""WAYMARK runtime paths and first-run migration helpers."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "WAYMARK"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def legacy_data_dir() -> Path:
    configured = os.getenv("WAYMARK_LEGACY_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "app" / "backend" / "data"


def data_dir() -> Path:
    configured = os.getenv("WAYMARK_DATA_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
    elif os.name == "nt":
        root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        path = Path(root) / APP_NAME if root else project_root() / "app" / "backend" / "data"
    else:
        root = os.getenv("XDG_DATA_HOME")
        path = Path(root) / APP_NAME if root else Path.home() / ".local" / "share" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_copy_if_missing(name: str) -> None:
    destination = data_dir() / name
    if destination.exists():
        return
    source = legacy_data_dir() / name
    if source == destination or not source.exists() or not source.is_file():
        return
    try:
        shutil.copy2(source, destination)
    except OSError:
        # Runtime will surface a write/read error if the file is actually needed.
        pass


def get_data_file(name: str, *, migrate: bool = True) -> str:
    """Return a user-writable data path, optionally migrating legacy data once."""
    if not name or Path(name).name != name:
        raise ValueError("Data file name must be a simple file name.")
    if migrate:
        _safe_copy_if_missing(name)
    return str(data_dir() / name)


def get_legacy_file(name: str) -> Path:
    if not name or Path(name).name != name:
        raise ValueError("Legacy file name must be a simple file name.")
    return legacy_data_dir() / name


def ensure_runtime_layout() -> Path:
    root = data_dir()
    (root / "browser" / "edge-profile").mkdir(parents=True, exist_ok=True)
    return root
