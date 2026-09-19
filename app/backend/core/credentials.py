"""Small OS-backed credential store for WAYMARK.

Windows uses DPAPI so credentials are encrypted at rest for the current user.
Environment variables remain supported as a development fallback, but are not
written into the store.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

from app.backend.core.runtime_paths import data_dir, get_legacy_file, project_root

STORE_FILENAME = "credentials.dat"


class CredentialStoreError(RuntimeError):
    pass


def _store_path() -> Path:
    path = data_dir() / STORE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("Windows DPAPI is unavailable on this platform.")

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    out = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(blob), "WAYMARK credentials", None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("Windows DPAPI is unavailable on this platform.")

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob), None, None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def load_credentials() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        raw = base64.b64decode(path.read_bytes())
        payload = _dpapi_unprotect(raw)
        data = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise CredentialStoreError(f"Could not open the WAYMARK credential store: {exc}") from exc
    return data if isinstance(data, dict) else {}


def save_credentials(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise TypeError("Credential store data must be a dictionary.")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encrypted = base64.b64encode(_dpapi_protect(payload))
    path = _store_path()
    fd, temp_name = tempfile.mkstemp(prefix="credentials-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def get_credential(service: str, key: str = "access_token", *, env_names: tuple[str, ...] = ()) -> str | None:
    data = load_credentials()
    service_data = data.get(service)
    if isinstance(service_data, dict):
        value = service_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for env_name in env_names:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return None


def set_credential(service: str, key: str, value: str) -> None:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError("Credential value cannot be empty.")
    data = load_credentials()
    service_data = data.setdefault(service, {})
    if not isinstance(service_data, dict):
        service_data = {}
        data[service] = service_data
    service_data[key] = cleaned
    save_credentials(data)


def set_credentials(service: str, values: dict[str, str]) -> None:
    data = load_credentials()
    service_data = data.setdefault(service, {})
    if not isinstance(service_data, dict):
        service_data = {}
        data[service] = service_data
    for key, value in values.items():
        cleaned = str(value or "").strip()
        if cleaned:
            service_data[key] = cleaned
    save_credentials(data)


def migrate_legacy_mal_token() -> bool:
    """Encrypt an existing development token.json into the user store once."""
    candidates = [get_legacy_file("token.json"), project_root() / "token.json"]
    existing = next((path for path in candidates if path.exists()), None)
    if existing is None:
        return False
    try:
        data = load_credentials()
        if isinstance(data.get("mal"), dict) and data["mal"].get("access_token"):
            return False
        payload = json.loads(existing.read_text(encoding="utf-8"))
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            return False
        service = data.setdefault("mal", {})
        service.update({k: v for k, v in payload.items() if isinstance(k, str) and isinstance(v, (str, int, float, bool))})
        save_credentials(data)
        return True
    except Exception:
        return False


def has_service_credentials(service: str, required_keys: tuple[str, ...] = ("access_token",)) -> bool:
    """Return True when the protected store contains all requested service keys."""
    data = load_credentials()
    service_data = data.get(service)
    if not isinstance(service_data, dict):
        return False
    for key in required_keys:
        value = service_data.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def delete_service_credentials(service: str) -> None:
    """Remove all credentials for one service from the protected store."""
    data = load_credentials()
    if service in data:
        data.pop(service, None)
        save_credentials(data)


def get_service_credentials(service: str) -> dict[str, Any]:
    """Return a copy of one service's stored credentials."""
    data = load_credentials()
    service_data = data.get(service)
    return dict(service_data) if isinstance(service_data, dict) else {}
