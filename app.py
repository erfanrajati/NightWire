from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import io
import json
import os
import re
import secrets
import shutil
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import anyio
import qrcode
import qrcode.image.svg
import uvicorn
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
FILES_DIR = Path(os.environ.get("NIGHTWIRE_FILES_DIR", BASE_DIR / "files")).expanduser().resolve()
STATIC_DIR = BASE_DIR / "static"
VERSION_FILE = BASE_DIR / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.is_file() else "development"
FILES_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_HINT = 1024 * 1024
CLIENT_TTL_SECONDS = 18
CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
CLIPBOARD_MAX_TEXT_LENGTH = 32_768
CLIPBOARD_HISTORY_LIMIT = 40
CLIPBOARD_PAYLOAD_LIMIT = 160_000
CLIPBOARD_DEFAULT_EXPIRY_SECONDS = 10 * 60
FILE_DEFAULT_EXPIRY_SECONDS = 0
ITEM_MIN_EXPIRY_SECONDS = 60
ITEM_MAX_EXPIRY_SECONDS = 365 * 24 * 60 * 60
PASSWORD_MAX_CHARACTERS = 256
CLIPBOARD_ENTRY_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
FILE_METADATA_FILENAME = ".nightwire-metadata.json"
STARTED_AT = datetime.now(timezone.utc)

_ACTIVE_CLIENTS: dict[str, dict[str, Any]] = {}
_CLIENTS_LOCK = threading.RLock()
_CLIPBOARD_ENTRIES: list[dict[str, Any]] = []
_CLIPBOARD_REVISION = 0
_CLIPBOARD_LOCK = threading.RLock()
_FILE_METADATA: dict[str, dict[str, Any]] = {}
_FILES_LOCK = threading.RLock()
_CLEANUP_STOP = threading.Event()
_CLEANUP_THREAD: threading.Thread | None = None


def utc_iso(timestamp: float | None = None) -> str:
    value = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp is not None else datetime.now(timezone.utc)
    return value.isoformat()


def parse_iso_timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def safe_file_path(name: str) -> Path:
    """Resolve a user-provided filename and prevent path traversal."""
    if not name or name in {".", ".."}:
        raise ValueError("A valid filename is required.")
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("Folders and path separators are not allowed.")
    if name in {".gitkeep", FILE_METADATA_FILENAME} or name.startswith(".uploading-") or name.startswith(f".{FILE_METADATA_FILENAME}."):
        raise ValueError("That filename is reserved by NightWire.")

    candidate = (FILES_DIR / name).resolve()
    if candidate.parent != FILES_DIR:
        raise ValueError("Invalid file path.")
    return candidate


def metadata_path() -> Path:
    return FILES_DIR / FILE_METADATA_FILENAME


def _sanitize_password_record(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    salt = value.get("salt")
    digest = value.get("digest")
    if not isinstance(salt, str) or not isinstance(digest, str):
        return None
    try:
        base64.b64decode(salt, validate=True)
        base64.b64decode(digest, validate=True)
    except (ValueError, TypeError):
        return None
    return {"salt": salt, "digest": digest}


def _load_file_metadata() -> None:
    path = metadata_path()
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return
    if not isinstance(payload, dict):
        return

    cleaned: dict[str, dict[str, Any]] = {}
    for name, raw in payload.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            continue
        try:
            safe_file_path(name)
        except ValueError:
            continue
        cleaned[name] = {
            "created_at": raw.get("created_at") if isinstance(raw.get("created_at"), str) else None,
            "expires_at": raw.get("expires_at") if isinstance(raw.get("expires_at"), str) else None,
            "password": _sanitize_password_record(raw.get("password")),
        }
    _FILE_METADATA.clear()
    _FILE_METADATA.update(cleaned)


def _save_file_metadata_locked() -> None:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    path = metadata_path()
    temp = FILES_DIR / f".{FILE_METADATA_FILENAME}.{uuid.uuid4().hex}.tmp"
    payload = json.dumps(_FILE_METADATA, ensure_ascii=False, indent=2, sort_keys=True)
    temp.write_text(payload + "\n", encoding="utf-8")
    os.replace(temp, path)


def normalize_password(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("A password is required.")
    password = value.replace("\x00", "")
    if not password and not allow_empty:
        raise ValueError("Password cannot be empty.")
    if len(password) > PASSWORD_MAX_CHARACTERS:
        raise ValueError(f"Password cannot exceed {PASSWORD_MAX_CHARACTERS} characters.")
    return password


def normalize_optional_password(value: object) -> str | None:
    """Return an optional creation-time password; empty values mean unprotected."""
    if value is None or value == "":
        return None
    return normalize_password(value)


def decode_optional_password_header(value: str | None) -> str | None:
    """Decode a UTF-8 password transported in a base64 request header."""
    if value is None or value == "":
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("The upload password header is invalid.") from exc
    return normalize_optional_password(decoded)


def create_password_record(password: str) -> dict[str, str]:
    normalized = normalize_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(normalized.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "digest": base64.b64encode(digest).decode("ascii"),
    }


def verify_password(password: object, record: object) -> bool:
    valid_record = _sanitize_password_record(record)
    if valid_record is None or not isinstance(password, str):
        return False
    try:
        salt = base64.b64decode(valid_record["salt"], validate=True)
        expected = base64.b64decode(valid_record["digest"], validate=True)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


def clean_text(value: object, maximum: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    value = " ".join(value.replace("\x00", "").split())
    return value[:maximum]


def normalize_client_ip(value: str) -> str:
    if value.startswith("::ffff:"):
        value = value[7:]
    return value or "unknown"


def normalize_clipboard_text(value: object) -> str:
    """Validate shared clipboard text while preserving useful formatting."""
    if not isinstance(value, str):
        raise ValueError("Clipboard text is required.")
    text = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Clipboard text cannot be empty.")
    if len(text) > CLIPBOARD_MAX_TEXT_LENGTH:
        raise ValueError(f"Clipboard text cannot exceed {CLIPBOARD_MAX_TEXT_LENGTH:,} characters.")
    return text


def normalize_expiry(value: object, default_seconds: int) -> int:
    """Return a validated auto-delete duration in seconds; zero means unlimited."""
    if value is None:
        return default_seconds
    if isinstance(value, bool):
        raise ValueError("Auto-delete duration must be a number of seconds.")
    try:
        seconds = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Auto-delete duration must be a number of seconds.") from exc
    if seconds == 0:
        return 0
    if seconds < ITEM_MIN_EXPIRY_SECONDS:
        raise ValueError("Auto-delete must be at least 1 minute, or zero for unlimited.")
    if seconds > ITEM_MAX_EXPIRY_SECONDS:
        raise ValueError("Auto-delete cannot exceed 365 days.")
    return seconds


def normalize_clipboard_expiry(value: object) -> int:
    return normalize_expiry(value, CLIPBOARD_DEFAULT_EXPIRY_SECONDS)


def normalize_file_expiry(value: object) -> int:
    return normalize_expiry(value, FILE_DEFAULT_EXPIRY_SECONDS)


def _expires_at_from_seconds(seconds: int, now: float | None = None) -> str | None:
    if seconds == 0:
        return None
    current = time.time() if now is None else now
    return utc_iso(current + seconds)


def _password_required(record: dict[str, Any], supplied: object) -> bool:
    password_record = record.get("password")
    return password_record is not None and not verify_password(supplied, password_record)


def _apply_item_settings(record: dict[str, Any], payload: dict[str, Any], *, default_expiry: int) -> None:
    """Apply the only mutable item setting: its auto-delete countdown.

    Password protection is intentionally creation-only and immutable. Retention is
    public to connected LAN clients, including for protected items.
    """
    forbidden = set(payload) - {"expires_in_seconds"}
    if forbidden:
        raise ValueError("Password protection is immutable; only the countdown can be changed.")
    if "expires_in_seconds" not in payload:
        raise ValueError("An auto-delete duration is required.")
    seconds = normalize_expiry(payload.get("expires_in_seconds"), default_expiry)
    record["expires_at"] = _expires_at_from_seconds(seconds)


def _default_file_metadata(path: Path) -> dict[str, Any]:
    return {
        "created_at": utc_iso(path.stat().st_mtime),
        "expires_at": None,
        "password": None,
    }


def _file_metadata_locked(path: Path) -> dict[str, Any]:
    record = _FILE_METADATA.get(path.name)
    if not isinstance(record, dict):
        record = _default_file_metadata(path)
        _FILE_METADATA[path.name] = record
    return record


def _purge_expired_files_locked(now: float | None = None) -> bool:
    current = time.time() if now is None else now
    changed = False

    for name in list(_FILE_METADATA):
        try:
            path = safe_file_path(name)
        except ValueError:
            _FILE_METADATA.pop(name, None)
            changed = True
            continue
        if not path.is_file():
            _FILE_METADATA.pop(name, None)
            changed = True
            continue
        expires_at = parse_iso_timestamp(_FILE_METADATA[name].get("expires_at"))
        if expires_at is not None and expires_at <= current:
            path.unlink(missing_ok=True)
            _FILE_METADATA.pop(name, None)
            changed = True

    if changed:
        _save_file_metadata_locked()
    return changed


def human_file_record(path: Path) -> dict[str, object]:
    stat = path.stat()
    with _FILES_LOCK:
        metadata = _file_metadata_locked(path)
        password_protected = metadata.get("password") is not None
        expires_at = metadata.get("expires_at")
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "created_at": metadata.get("created_at") or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "expires_at": expires_at,
        "password_protected": password_protected,
        "download_url": f"/download/{quote(path.name)}",
    }


def update_file_settings(name: str, payload: dict[str, Any]) -> dict[str, object]:
    path = safe_file_path(name)
    with _FILES_LOCK:
        _purge_expired_files_locked()
        if not path.is_file() or path.name == ".gitkeep":
            raise FileNotFoundError("File not found.")
        record = _file_metadata_locked(path)
        _apply_item_settings(record, payload, default_expiry=FILE_DEFAULT_EXPIRY_SECONDS)
        _save_file_metadata_locked()
    return human_file_record(path)


def delete_file_record(name: str, password: object = None) -> None:
    path = safe_file_path(name)
    with _FILES_LOCK:
        _purge_expired_files_locked()
        if not path.is_file() or path.name == ".gitkeep":
            raise FileNotFoundError("File not found.")
        record = _file_metadata_locked(path)
        if _password_required(record, password):
            raise PermissionError("The file password is incorrect.")
        path.unlink()
        _FILE_METADATA.pop(path.name, None)
        _save_file_metadata_locked()


def _public_clipboard_entry(entry: dict[str, Any]) -> dict[str, Any]:
    protected = entry.get("password") is not None
    return {
        "id": entry["id"],
        "text": None if protected else entry["text"],
        "text_length": len(entry["text"]),
        "client_id": entry["client_id"],
        "source": entry["source"],
        "ip_address": entry["ip_address"],
        "created_at": entry["created_at"],
        "expires_at": entry.get("expires_at"),
        "password_protected": protected,
    }


def _purge_expired_clipboard_entries_locked(now: float | None = None) -> bool:
    global _CLIPBOARD_REVISION
    current = time.time() if now is None else now
    retained = [
        entry
        for entry in _CLIPBOARD_ENTRIES
        if parse_iso_timestamp(entry.get("expires_at")) is None or parse_iso_timestamp(entry.get("expires_at")) > current
    ]
    if len(retained) == len(_CLIPBOARD_ENTRIES):
        return False
    _CLIPBOARD_ENTRIES[:] = retained
    _CLIPBOARD_REVISION += 1
    return True


def clipboard_snapshot() -> tuple[int, list[dict[str, Any]]]:
    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked()
        return _CLIPBOARD_REVISION, [_public_clipboard_entry(entry) for entry in _CLIPBOARD_ENTRIES]


def add_clipboard_entry(
    text: str,
    client_id: str,
    source: str,
    ip_address: str,
    expires_in_seconds: int = CLIPBOARD_DEFAULT_EXPIRY_SECONDS,
    password: str | None = None,
) -> tuple[int, dict[str, Any]]:
    global _CLIPBOARD_REVISION
    created = time.time()
    entry = {
        "id": uuid.uuid4().hex,
        "text": text,
        "client_id": client_id,
        "source": source,
        "ip_address": ip_address,
        "created_at": utc_iso(created),
        "expires_at": _expires_at_from_seconds(expires_in_seconds, created),
        "password": create_password_record(password) if password else None,
    }

    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked(created)
        _CLIPBOARD_ENTRIES.insert(0, entry)
        del _CLIPBOARD_ENTRIES[CLIPBOARD_HISTORY_LIMIT:]
        _CLIPBOARD_REVISION += 1
        revision = _CLIPBOARD_REVISION
    return revision, _public_clipboard_entry(entry)


def _clipboard_entry_locked(entry_id: str) -> dict[str, Any] | None:
    for entry in _CLIPBOARD_ENTRIES:
        if entry["id"] == entry_id:
            return entry
    return None


def update_clipboard_settings(entry_id: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    global _CLIPBOARD_REVISION
    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked()
        entry = _clipboard_entry_locked(entry_id)
        if entry is None:
            raise FileNotFoundError("Shared clipboard entry not found.")
        _apply_item_settings(entry, payload, default_expiry=CLIPBOARD_DEFAULT_EXPIRY_SECONDS)
        _CLIPBOARD_REVISION += 1
        return _CLIPBOARD_REVISION, _public_clipboard_entry(entry)


def unlock_clipboard_entry(entry_id: str, password: object) -> str:
    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked()
        entry = _clipboard_entry_locked(entry_id)
        if entry is None:
            raise FileNotFoundError("Shared clipboard entry not found.")
        if _password_required(entry, password):
            raise PermissionError("The clipboard password is incorrect.")
        return entry["text"]


def delete_clipboard_entry(entry_id: str, password: object = None) -> tuple[int, bool]:
    global _CLIPBOARD_REVISION
    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked()
        for index, entry in enumerate(_CLIPBOARD_ENTRIES):
            if entry["id"] == entry_id:
                if _password_required(entry, password):
                    raise PermissionError("The clipboard password is incorrect.")
                del _CLIPBOARD_ENTRIES[index]
                _CLIPBOARD_REVISION += 1
                return _CLIPBOARD_REVISION, True
        return _CLIPBOARD_REVISION, False


def clear_clipboard_entries() -> int:
    global _CLIPBOARD_REVISION
    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked()
        if any(entry.get("password") is not None for entry in _CLIPBOARD_ENTRIES):
            raise PermissionError("Protected clipboard entries must be deleted individually.")
        _CLIPBOARD_ENTRIES.clear()
        _CLIPBOARD_REVISION += 1
        return _CLIPBOARD_REVISION


def local_ipv4_addresses() -> list[str]:
    """Return usable IPv4 addresses, with the most likely LAN address first."""
    addresses: set[str] = set()
    preferred: str | None = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            preferred = probe.getsockname()[0]
            addresses.add(preferred)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass

    usable: list[str] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.is_loopback or address.is_unspecified:
            continue
        usable.append(value)

    private_ranges = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )

    def rank(value: str) -> tuple[int, int, str]:
        address = ipaddress.ip_address(value)
        if any(address in network for network in private_ranges):
            scope_rank = 0
        elif address.is_link_local:
            scope_rank = 1
        else:
            scope_rank = 2
        return (0 if value == preferred else 1, scope_rank, value)

    return sorted(set(usable), key=rank)


def local_addresses(port: int) -> list[str]:
    return [f"http://{ip}:{port}" for ip in local_ipv4_addresses()]


def _version_from_agent(user_agent: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, user_agent, flags=re.IGNORECASE)
        if match:
            return match.group(1).replace("_", ".")
    return None


def parse_user_agent(user_agent: str, metadata: dict[str, Any] | None = None) -> dict[str, str | bool | None]:
    """Return a compact device/browser summary without adding a parser dependency."""
    metadata = metadata or {}
    ua = clean_text(user_agent, 512)
    ua_lower = ua.lower()
    hinted_platform = clean_text(metadata.get("platform"), 80)
    is_mobile_hint = bool(metadata.get("mobile"))

    if "iphone" in ua_lower:
        device, device_kind, operating_system = "iPhone", "phone", "iOS"
    elif "ipad" in ua_lower:
        device, device_kind, operating_system = "iPad", "tablet", "iPadOS"
    elif "android" in ua_lower:
        model_match = re.search(r"Android[^;)]*;\s*([^;)]+?)(?:\s+Build|[;)])", ua, flags=re.IGNORECASE)
        model = clean_text(model_match.group(1), 64) if model_match else ""
        mobile = "mobile" in ua_lower or is_mobile_hint
        device = model if model and model.lower() not in {"wv", "k"} else ("Android phone" if mobile else "Android tablet")
        device_kind, operating_system = ("phone" if mobile else "tablet"), "Android"
    elif "cros" in ua_lower:
        device, device_kind, operating_system = "Chromebook", "computer", "ChromeOS"
    elif "windows" in ua_lower:
        device, device_kind, operating_system = "Windows PC", "computer", "Windows"
    elif "macintosh" in ua_lower or hinted_platform.lower() == "macos":
        device, device_kind, operating_system = "Mac", "computer", "macOS"
    elif "linux" in ua_lower:
        device, device_kind, operating_system = "Linux device", "computer", "Linux"
    elif hinted_platform:
        device, device_kind, operating_system = hinted_platform, ("phone" if is_mobile_hint else "computer"), hinted_platform
    else:
        device, device_kind, operating_system = "Unknown device", "device", "Unknown OS"

    browser_patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Samsung Internet", (r"SamsungBrowser/([\d.]+)",)),
        ("Edge", (r"EdgA?/([\d.]+)", r"EdgiOS/([\d.]+)")),
        ("Opera", (r"OPR/([\d.]+)", r"Opera/([\d.]+)")),
        ("Chrome", (r"CriOS/([\d.]+)", r"Chrome/([\d.]+)")),
        ("Firefox", (r"FxiOS/([\d.]+)", r"Firefox/([\d.]+)")),
        ("Safari", (r"Version/([\d.]+).*Safari/",)),
    )
    browser, browser_version = "Unknown browser", None
    for candidate, patterns in browser_patterns:
        version = _version_from_agent(ua, patterns)
        if version:
            browser, browser_version = candidate, version
            break

    return {
        "device": device,
        "device_kind": device_kind,
        "operating_system": operating_system,
        "browser": browser,
        "browser_version": browser_version,
        "agent_label": f"{device} · {browser}{f' {browser_version}' if browser_version else ''}",
        "user_agent": ua,
    }


def purge_inactive_clients(now: float | None = None) -> None:
    current = now if now is not None else time.time()
    stale = [client_id for client_id, record in _ACTIVE_CLIENTS.items() if current - record["last_seen_epoch"] > CLIENT_TTL_SECONDS]
    for client_id in stale:
        _ACTIVE_CLIENTS.pop(client_id, None)


def server_device_record(port: int) -> dict[str, Any]:
    addresses = local_ipv4_addresses()
    return {
        "id": "server",
        "role": "server",
        "name": socket.gethostname(),
        "status": "online",
        "ip_addresses": addresses,
        "primary_ip": addresses[0] if addresses else "127.0.0.1",
        "network_urls": [f"http://{address}:{port}" for address in addresses],
        "connected_at": STARTED_AT.isoformat(),
        "last_seen": utc_iso(),
        "device": "NightWire server",
        "device_kind": "server",
        "operating_system": os.name,
        "browser": None,
        "browser_version": None,
        "agent_label": "NightWire server",
        "user_agent": None,
    }


def active_device_records(port: int) -> list[dict[str, Any]]:
    with _CLIENTS_LOCK:
        purge_inactive_clients()
        clients = [dict(record) for record in _ACTIVE_CLIENTS.values()]
    clients.sort(key=lambda record: (record["connected_at"], record["ip_address"], record["id"]))
    for record in clients:
        record.pop("last_seen_epoch", None)
    return [server_device_record(port), *clients]


def request_port(request: Request) -> int:
    return int(os.environ.get("PORT", str(request.url.port or 8080)))


def cleanup_expired_items() -> None:
    with _FILES_LOCK:
        _purge_expired_files_locked()
    with _CLIPBOARD_LOCK:
        _purge_expired_clipboard_entries_locked()


def _cleanup_worker() -> None:
    while not _CLEANUP_STOP.wait(1.0):
        try:
            cleanup_expired_items()
        except Exception as exc:
            print(f"NightWire cleanup warning: {exc}")


async def start_cleanup_worker() -> None:
    global _CLEANUP_THREAD
    if _CLEANUP_THREAD is not None and _CLEANUP_THREAD.is_alive():
        return
    _CLEANUP_STOP.clear()
    _CLEANUP_THREAD = threading.Thread(target=_cleanup_worker, name="nightwire-cleanup", daemon=True)
    _CLEANUP_THREAD.start()


async def stop_cleanup_worker() -> None:
    global _CLEANUP_THREAD
    _CLEANUP_STOP.set()
    thread = _CLEANUP_THREAD
    if thread is not None and thread.is_alive():
        await anyio.to_thread.run_sync(thread.join, 2.0)
    _CLEANUP_THREAD = None


async def read_json_payload(request: Request, *, maximum: int = 32_768, allow_empty: bool = False) -> dict[str, Any]:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > maximum:
        raise OverflowError("Request payload is too large.")
    if allow_empty and (not content_length or content_length == "0"):
        return {}
    try:
        payload = await request.json()
    except (ValueError, TypeError):
        if allow_empty:
            return {}
        raise ValueError("A valid JSON payload is required.")
    if not isinstance(payload, dict):
        raise ValueError("A valid JSON payload is required.")
    return payload


async def root(_: Request) -> Response:
    return RedirectResponse("/files", status_code=307)


async def page(_: Request) -> Response:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        return HTMLResponse("NightWire frontend assets are missing.", status_code=500)
    return FileResponse(index_path, media_type="text/html", headers={"Cache-Control": "no-store"})


async def list_files(_: Request) -> JSONResponse:
    with _FILES_LOCK:
        _purge_expired_files_locked()
        files = [
            human_file_record(path)
            for path in FILES_DIR.iterdir()
            if path.is_file()
            and not path.name.startswith(".uploading-")
            and not path.name.startswith(f".{FILE_METADATA_FILENAME}.")
            and path.name not in {".gitkeep", FILE_METADATA_FILENAME}
        ]
    files.sort(key=lambda item: item["modified"], reverse=True)
    usage = shutil.disk_usage(FILES_DIR)
    return JSONResponse(
        {"files": files, "storage": {"total": usage.total, "used": usage.used, "free": usage.free}},
        headers={"Cache-Control": "no-store"},
    )


async def server_info(request: Request) -> JSONResponse:
    port = request_port(request)
    network_urls = local_addresses(port)
    return JSONResponse(
        {
            "version": APP_VERSION,
            "hostname": socket.gethostname(),
            "directory": str(FILES_DIR),
            "chunk_hint": CHUNK_HINT,
            "client_ttl_seconds": CLIENT_TTL_SECONDS,
            "clipboard_max_text_length": CLIPBOARD_MAX_TEXT_LENGTH,
            "clipboard_history_limit": CLIPBOARD_HISTORY_LIMIT,
            "clipboard_default_expiry_seconds": CLIPBOARD_DEFAULT_EXPIRY_SECONDS,
            "file_default_expiry_seconds": FILE_DEFAULT_EXPIRY_SECONDS,
            "item_min_expiry_seconds": ITEM_MIN_EXPIRY_SECONDS,
            "item_max_expiry_seconds": ITEM_MAX_EXPIRY_SECONDS,
            "password_max_characters": PASSWORD_MAX_CHARACTERS,
            "network_urls": network_urls,
            "primary_network_url": network_urls[0] if network_urls else f"http://127.0.0.1:{port}",
        },
        headers={"Cache-Control": "no-store"},
    )


async def list_devices(request: Request) -> JSONResponse:
    return JSONResponse(
        {"devices": active_device_records(request_port(request)), "client_ttl_seconds": CLIENT_TTL_SECONDS},
        headers={"Cache-Control": "no-store"},
    )


async def client_heartbeat(request: Request) -> JSONResponse:
    try:
        payload = await read_json_payload(request, maximum=8192)
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    client_id = clean_text(payload.get("client_id"), 128)
    if not CLIENT_ID_PATTERN.fullmatch(client_id):
        return JSONResponse({"error": "A valid client ID is required."}, status_code=400)

    client_host = normalize_client_ip(request.client.host if request.client else "unknown")
    agent = parse_user_agent(request.headers.get("user-agent", ""), payload)
    now = time.time()
    with _CLIENTS_LOCK:
        purge_inactive_clients(now)
        previous = _ACTIVE_CLIENTS.get(client_id)
        connected_at = previous["connected_at"] if previous else utc_iso(now)
        _ACTIVE_CLIENTS[client_id] = {
            "id": client_id,
            "role": "client",
            "name": agent["device"],
            "status": "online",
            "ip_address": client_host,
            "ip_addresses": [client_host],
            "primary_ip": client_host,
            "connected_at": connected_at,
            "last_seen": utc_iso(now),
            "last_seen_epoch": now,
            **agent,
        }

    return JSONResponse(
        {"ok": True, "devices": active_device_records(request_port(request)), "client_ttl_seconds": CLIENT_TTL_SECONDS},
        headers={"Cache-Control": "no-store"},
    )


async def list_clipboard(request: Request) -> JSONResponse:
    raw_revision = request.query_params.get("since_revision", "-1")
    try:
        since_revision = int(raw_revision)
    except ValueError:
        return JSONResponse({"error": "since_revision must be an integer."}, status_code=400)
    revision, entries = clipboard_snapshot()
    changed = since_revision != revision
    return JSONResponse(
        {
            "revision": revision,
            "changed": changed,
            "entries": entries if changed else [],
            "max_text_length": CLIPBOARD_MAX_TEXT_LENGTH,
            "history_limit": CLIPBOARD_HISTORY_LIMIT,
        },
        headers={"Cache-Control": "no-store"},
    )


async def share_clipboard(request: Request) -> JSONResponse:
    try:
        payload = await read_json_payload(request, maximum=CLIPBOARD_PAYLOAD_LIMIT)
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    client_id = clean_text(payload.get("client_id"), 128)
    if not CLIENT_ID_PATTERN.fullmatch(client_id):
        return JSONResponse({"error": "A valid client ID is required."}, status_code=400)
    try:
        text = normalize_clipboard_text(payload.get("text"))
        expires_in_seconds = normalize_clipboard_expiry(payload.get("expires_in_seconds"))
        password = normalize_optional_password(payload.get("password"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    client_host = normalize_client_ip(request.client.host if request.client else "unknown")
    with _CLIENTS_LOCK:
        purge_inactive_clients()
        known_client = _ACTIVE_CLIENTS.get(client_id)
        source = clean_text(known_client.get("agent_label"), 160) if known_client else ""
    if not source:
        source = clean_text(parse_user_agent(request.headers.get("user-agent", "")).get("agent_label"), 160) or "Connected device"

    revision, entry = add_clipboard_entry(text, client_id, source, client_host, expires_in_seconds, password)
    return JSONResponse(
        {"ok": True, "revision": revision, "entry": entry},
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


async def patch_clipboard(request: Request) -> JSONResponse:
    entry_id = request.path_params.get("entry_id", "")
    if not CLIPBOARD_ENTRY_ID_PATTERN.fullmatch(entry_id):
        return JSONResponse({"error": "A valid clipboard entry ID is required."}, status_code=400)
    try:
        payload = await read_json_payload(request)
        revision, entry = update_clipboard_settings(entry_id, payload)
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True, "revision": revision, "entry": entry}, headers={"Cache-Control": "no-store"})


async def unlock_clipboard(request: Request) -> JSONResponse:
    entry_id = request.path_params.get("entry_id", "")
    if not CLIPBOARD_ENTRY_ID_PATTERN.fullmatch(entry_id):
        return JSONResponse({"error": "A valid clipboard entry ID is required."}, status_code=400)
    try:
        payload = await read_json_payload(request)
        text = unlock_clipboard_entry(entry_id, payload.get("password"))
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True, "text": text}, headers={"Cache-Control": "no-store"})


async def clear_clipboard(_: Request) -> JSONResponse:
    try:
        revision = clear_clipboard_entries()
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse({"ok": True, "revision": revision}, headers={"Cache-Control": "no-store"})


async def delete_clipboard(request: Request) -> JSONResponse:
    entry_id = request.path_params.get("entry_id", "")
    if not CLIPBOARD_ENTRY_ID_PATTERN.fullmatch(entry_id):
        return JSONResponse({"error": "A valid clipboard entry ID is required."}, status_code=400)
    try:
        payload = await read_json_payload(request, allow_empty=True)
        revision, deleted = delete_clipboard_entry(entry_id, payload.get("password"))
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    if not deleted:
        return JSONResponse({"error": "Shared clipboard entry not found.", "revision": revision}, status_code=404)
    return JSONResponse({"ok": True, "revision": revision}, headers={"Cache-Control": "no-store"})


async def qr_code(request: Request) -> Response:
    target = request.query_params.get("url", "").strip()
    if not target or len(target) > 2048:
        return JSONResponse({"error": "A valid URL is required."}, status_code=400)
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return JSONResponse({"error": "Only HTTP or HTTPS URLs are supported."}, status_code=400)

    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(target)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    return Response(
        output.getvalue(),
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def upload_file(request: Request) -> JSONResponse:
    filename = request.query_params.get("filename", "")
    try:
        destination = safe_file_path(filename)
        expires_in_seconds = normalize_file_expiry(request.headers.get("x-nightwire-expires-in-seconds"))
        password = decode_optional_password_header(request.headers.get("x-nightwire-password-b64"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    with _FILES_LOCK:
        _purge_expired_files_locked()
        if destination.is_file() and _file_metadata_locked(destination).get("password") is not None:
            return JSONResponse({"error": "A password-protected file cannot be overwritten."}, status_code=409)

    temp_path = FILES_DIR / f".uploading-{uuid.uuid4().hex}"
    total_written = 0
    started = time.perf_counter()
    try:
        async with await anyio.open_file(temp_path, "wb") as output:
            async for chunk in request.stream():
                if chunk:
                    await output.write(chunk)
                    total_written += len(chunk)
    except ClientDisconnect:
        temp_path.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "cancelled": True}, status_code=499, headers={"Cache-Control": "no-store"})
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise

    with _FILES_LOCK:
        _purge_expired_files_locked()
        if destination.is_file() and _file_metadata_locked(destination).get("password") is not None:
            temp_path.unlink(missing_ok=True)
            return JSONResponse({"error": "A password-protected file cannot be overwritten."}, status_code=409)
        os.replace(temp_path, destination)
        _FILE_METADATA[destination.name] = {
            "created_at": utc_iso(),
            "expires_at": _expires_at_from_seconds(expires_in_seconds),
            "password": create_password_record(password) if password else None,
        }
        _save_file_metadata_locked()

    elapsed = max(time.perf_counter() - started, 0.001)
    return JSONResponse(
        {
            "ok": True,
            "file": human_file_record(destination),
            "bytes_written": total_written,
            "seconds": round(elapsed, 3),
            "average_bytes_per_second": round(total_written / elapsed),
        },
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


async def patch_file(request: Request) -> JSONResponse:
    filename = request.path_params["filename"]
    try:
        payload = await read_json_payload(request)
        record = update_file_settings(filename, payload)
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True, "file": record}, headers={"Cache-Control": "no-store"})


async def download_file(request: Request) -> Response:
    filename = request.path_params["filename"]
    try:
        path = safe_file_path(filename)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    with _FILES_LOCK:
        _purge_expired_files_locked()
        if not path.is_file() or path.name == ".gitkeep" or path.name.startswith(".uploading-"):
            return JSONResponse({"error": "File not found."}, status_code=404)
        record = _file_metadata_locked(path)
        if record.get("password") is not None:
            return JSONResponse({"error": "This file is password protected."}, status_code=401)

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def download_protected_file(request: Request) -> Response:
    filename = request.path_params["filename"]
    try:
        path = safe_file_path(filename)
        payload = await read_json_payload(request)
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    with _FILES_LOCK:
        _purge_expired_files_locked()
        if not path.is_file() or path.name == ".gitkeep":
            return JSONResponse({"error": "File not found."}, status_code=404)
        record = _file_metadata_locked(path)
        if _password_required(record, payload.get("password")):
            return JSONResponse({"error": "The file password is incorrect."}, status_code=403)

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def delete_file(request: Request) -> JSONResponse:
    filename = request.path_params["filename"]
    try:
        payload = await read_json_payload(request, allow_empty=True)
        await anyio.to_thread.run_sync(delete_file_record, filename, payload.get("password"))
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


routes = [
    Route("/", root, methods=["GET"]),
    Route("/files", page, methods=["GET"]),
    Route("/clipboard", page, methods=["GET"]),
    Route("/clients", page, methods=["GET"]),
    Route("/api/files", list_files, methods=["GET"]),
    Route("/api/info", server_info, methods=["GET"]),
    Route("/api/devices", list_devices, methods=["GET"]),
    Route("/api/clients/heartbeat", client_heartbeat, methods=["POST"]),
    Route("/api/clipboard", list_clipboard, methods=["GET"]),
    Route("/api/clipboard", share_clipboard, methods=["POST"]),
    Route("/api/clipboard", clear_clipboard, methods=["DELETE"]),
    Route("/api/clipboard/{entry_id:str}", patch_clipboard, methods=["PATCH"]),
    Route("/api/clipboard/{entry_id:str}", delete_clipboard, methods=["DELETE"]),
    Route("/api/clipboard/{entry_id:str}/unlock", unlock_clipboard, methods=["POST"]),
    Route("/api/qr", qr_code, methods=["GET"]),
    Route("/api/upload", upload_file, methods=["PUT"]),
    Route("/api/files/{filename:str}", patch_file, methods=["PATCH"]),
    Route("/api/files/{filename:str}", delete_file, methods=["DELETE"]),
    Route("/api/files/{filename:str}/download", download_protected_file, methods=["POST"]),
    Route("/download/{filename:str}", download_file, methods=["GET", "HEAD"]),
]

app = Starlette(debug=False, routes=routes, on_startup=[start_cleanup_worker], on_shutdown=[stop_cleanup_worker])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
        "style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'",
    )
    return response


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    print(f"\nNightWire {APP_VERSION}")
    print(f"Local     http://127.0.0.1:{port}/files")
    for url in local_addresses(port):
        print(f"Network   {url}/files")
    print(f"Files     {FILES_DIR}\n")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        access_log=False,
        backlog=2048,
        timeout_keep_alive=30,
        server_header=False,
    )


_load_file_metadata()

if __name__ == "__main__":
    main()
