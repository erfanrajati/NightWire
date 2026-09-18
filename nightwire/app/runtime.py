"""NightWire application runtime composed from Core and Drop services."""

from __future__ import annotations

import base64
import ipaddress
import io
import json
import os
import re
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
from starlette.requests import ClientDisconnect, Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from nightwire.app.bootstrap import build_application
from nightwire.app.passwords import PasswordProtection
from nightwire.core.config import SETTINGS, load_port
from nightwire.core.capacity import CapacityExceededError, CommunityCapacityManager, UsageScope
from nightwire.core.storage import (
    OBJECT_METADATA_DIRECTORY_NAME,
    OBJECTS_DIRECTORY_NAME,
    TEMPORARY_UPLOADS_DIRECTORY_NAME,
    LocalFilesystemStorage,
    ObjectId,
)
from nightwire.core.lifecycle import CoreLifecycleService, LifecycleItem
from nightwire.core.security import CoreSecurityPipeline, PasswordDigest
from nightwire.core.transfer import CoreTransferService, TransferProgressStore
from nightwire.drop.access import DropAccessKeyPolicy
from nightwire.drop.compatibility import DropClientVisibilityService, DropClipboardService
from nightwire.drop.repository import LocalDropRepository
from nightwire.drop.service import (
    DropAccessDeniedError,
    DropService,
    MaliciousDropConfirmationRequiredError,
    ProtectedDropItemError,
    ProtectedDropOverwriteError,
)
from nightwire.text import TextLifecycle, TextObjectService, TextScopeKind, TextValidationError

BASE_DIR = SETTINGS.base_dir
FILES_DIR = SETTINGS.files_dir
STATIC_DIR = SETTINGS.static_dir
VERSION_FILE = SETTINGS.version_file
APP_VERSION = SETTINGS.version

CHUNK_HINT = SETTINGS.chunk_hint
CLIENT_TTL_SECONDS = SETTINGS.client_ttl_seconds
CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
CLIPBOARD_MAX_TEXT_LENGTH = SETTINGS.clipboard_max_text_length
CLIPBOARD_HISTORY_LIMIT = SETTINGS.clipboard_history_limit
CLIPBOARD_PAYLOAD_LIMIT = SETTINGS.clipboard_payload_limit
CLIPBOARD_DEFAULT_EXPIRY_SECONDS = SETTINGS.clipboard_default_expiry_seconds
FILE_DEFAULT_EXPIRY_SECONDS = SETTINGS.file_default_expiry_seconds
ITEM_MIN_EXPIRY_SECONDS = SETTINGS.item_min_expiry_seconds
ITEM_MAX_EXPIRY_SECONDS = SETTINGS.item_max_expiry_seconds
ANONYMOUS_INTERNET_DROP_MAX_EXPIRY_SECONDS = SETTINGS.anonymous_internet_drop_max_expiry_seconds
PASSWORD_MAX_CHARACTERS = SETTINGS.password_max_characters
CLIPBOARD_ENTRY_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
FILE_METADATA_FILENAME = SETTINGS.file_metadata_filename
STARTED_AT = datetime.now(timezone.utc)

STORAGE_BACKEND = LocalFilesystemStorage(FILES_DIR)
TRANSFER_PROGRESS = TransferProgressStore()
TRANSFER_SERVICE = CoreTransferService(STORAGE_BACKEND, progress_store=TRANSFER_PROGRESS)
CAPACITY_MANAGER = CommunityCapacityManager(
    FILES_DIR, installation_limit=SETTINGS.installation_max_bytes,
    personal_limit=SETTINGS.personal_library_quota_bytes,
    workspace_limit=SETTINGS.workspace_quota_bytes, drop_limit=SETTINGS.drop_quota_bytes,
    object_limit=SETTINGS.maximum_object_bytes, minimum_free=SETTINGS.minimum_host_free_bytes,
)
TRANSFER_SERVICE.set_capacity_manager(CAPACITY_MANAGER)
LIFECYCLE_SERVICE = CoreLifecycleService()
SECURITY_PIPELINE = CoreSecurityPipeline(STORAGE_BACKEND)
PASSWORD_PROTECTION = PasswordProtection(PASSWORD_MAX_CHARACTERS)
DROP_ACCESS_KEYS = DropAccessKeyPolicy()
TEXT_OBJECTS = TextObjectService()

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
    if name in {
        ".gitkeep",
        FILE_METADATA_FILENAME,
        OBJECT_METADATA_DIRECTORY_NAME,
        OBJECTS_DIRECTORY_NAME,
        TEMPORARY_UPLOADS_DIRECTORY_NAME,
    } or name.startswith(".uploading-") or name.startswith(f".{FILE_METADATA_FILENAME}."):
        raise ValueError("That filename is reserved by NightWire.")

    candidate = (FILES_DIR / name).resolve()
    if candidate.parent != FILES_DIR:
        raise ValueError("Invalid file path.")
    return candidate


def metadata_path() -> Path:
    return FILES_DIR / FILE_METADATA_FILENAME


DROP_REPOSITORY = LocalDropRepository(
    metadata_path,
    records=_FILE_METADATA,
    validate_name=safe_file_path,
)


def _physical_usage(scope: UsageScope) -> int:
    if scope.kind != "installation":
        return 0
    storage = current_storage_backend()
    objects = sum(path.stat().st_size for path in storage.objects_root.iterdir() if path.is_file())
    legacy = sum(path.stat().st_size for path in storage.storage_root.iterdir()
                 if path.is_file() and path.name != FILE_METADATA_FILENAME)
    return objects + legacy


def _drop_usage(scope: UsageScope) -> int:
    if scope.kind != "drop":
        return 0
    return sum(item.size or 0 for item in DROP_REPOSITORY.list())


CAPACITY_MANAGER.add_usage_source(_physical_usage)
CAPACITY_MANAGER.add_usage_source(_drop_usage)


def current_storage_backend() -> LocalFilesystemStorage:
    """Return the configured backend, adapting when tests replace FILES_DIR."""

    if STORAGE_BACKEND.storage_root == FILES_DIR:
        return STORAGE_BACKEND
    return LocalFilesystemStorage(FILES_DIR)


def current_transfer_service(storage: LocalFilesystemStorage | None = None) -> CoreTransferService:
    resolved_storage = storage or current_storage_backend()
    if TRANSFER_SERVICE.storage is resolved_storage:
        return TRANSFER_SERVICE
    transfer = CoreTransferService(resolved_storage, progress_store=TRANSFER_PROGRESS)
    capacity = CAPACITY_MANAGER if resolved_storage.storage_root == FILES_DIR else CommunityCapacityManager(resolved_storage.storage_root)
    transfer.set_capacity_manager(capacity)
    return transfer


def current_capacity_manager() -> CommunityCapacityManager:
    return CAPACITY_MANAGER


def current_security_pipeline(storage: LocalFilesystemStorage | None = None) -> CoreSecurityPipeline:
    resolved_storage = storage or current_storage_backend()
    if SECURITY_PIPELINE.storage is resolved_storage:
        return SECURITY_PIPELINE
    return CoreSecurityPipeline(resolved_storage, scanner=SECURITY_PIPELINE.scanner)


def current_drop_service() -> DropService:
    storage = current_storage_backend()
    return DropService(
        repository=DROP_REPOSITORY,
        storage=storage,
        legacy_root=FILES_DIR,
        transfer=current_transfer_service(storage),
        lifecycle=LIFECYCLE_SERVICE,
        security=current_security_pipeline(storage),
        passwords=PASSWORD_PROTECTION,
        access_keys=DROP_ACCESS_KEYS,
        validate_name=safe_file_path,
        lock=_FILES_LOCK,
        metadata_filename=FILE_METADATA_FILENAME,
        default_expiry_seconds=FILE_DEFAULT_EXPIRY_SECONDS,
        minimum_expiry_seconds=ITEM_MIN_EXPIRY_SECONDS,
        maximum_expiry_seconds=ITEM_MAX_EXPIRY_SECONDS,
        deployment_profile=SETTINGS.deployment_profile,
        anonymous_internet_maximum_expiry_seconds=ANONYMOUS_INTERNET_DROP_MAX_EXPIRY_SECONDS,
        trusted_network_relaxed_access=SETTINGS.trusted_network_relaxed_access,
        trusted_network_active_drop_browsing=SETTINGS.trusted_network_active_drop_browsing,
    )


def _metadata_object_id(record: object) -> ObjectId | None:
    if not isinstance(record, dict) or record.get("object_id") is None:
        return None
    try:
        return ObjectId.parse(record.get("object_id"))
    except ValueError:
        return None


def _stored_file_path_locked(name: str, record: dict[str, Any] | None = None) -> Path:
    legacy_path = safe_file_path(name)
    resolved_record = _FILE_METADATA.get(name) if record is None else record
    object_id = _metadata_object_id(resolved_record)
    if object_id is not None:
        return current_storage_backend().object_reference(object_id)
    return legacy_path


def _delete_stored_file_locked(name: str, record: dict[str, Any], path: Path) -> None:
    object_id = _metadata_object_id(record)
    if object_id is not None:
        current_storage_backend().delete_object(object_id)
    else:
        path.unlink(missing_ok=True)


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
    DROP_REPOSITORY.load()


def _save_file_metadata_locked() -> None:
    DROP_REPOSITORY.save()


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
    return PASSWORD_PROTECTION.normalize_optional(value)


def decode_optional_password_header(value: str | None) -> str | None:
    """Decode a UTF-8 password transported in a base64 request header."""
    return PASSWORD_PROTECTION.decode_creation_header(value)


def create_password_record(password: str) -> dict[str, str]:
    return PASSWORD_PROTECTION.create(password).to_dict()


def verify_password(password: object, record: object) -> bool:
    valid_record = _sanitize_password_record(record)
    digest = PasswordDigest(**valid_record) if valid_record is not None else None
    return PASSWORD_PROTECTION.verify(password, digest)


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


def _file_metadata_locked(path: Path, logical_name: str | None = None) -> dict[str, Any]:
    name = logical_name or path.name
    record = _FILE_METADATA.get(name)
    if not isinstance(record, dict):
        record = _default_file_metadata(path)
        _FILE_METADATA[name] = record
    return record


def _purge_expired_files_locked(now: float | None = None) -> bool:
    return current_drop_service().purge_expired(now)


def human_file_record(
    path: Path,
    *,
    logical_name: str | None = None,
    metadata_record: dict[str, Any] | None = None,
) -> dict[str, object]:
    name = logical_name or path.name
    stat = path.stat()
    with _FILES_LOCK:
        metadata = metadata_record or _file_metadata_locked(path, name)
        password_protected = metadata.get("password") is not None
        expires_at = metadata.get("expires_at")
    return {
        "name": name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "created_at": metadata.get("created_at") or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "expires_at": expires_at,
        "password_protected": password_protected,
        "checksum_sha256": metadata.get("checksum_sha256"),
        "security_verdict": (
            metadata.get("security", {}).get("verdict") if isinstance(metadata.get("security"), dict) else None
        ),
        "detected_mime": (
            metadata.get("security", {}).get("detected_mime")
            if isinstance(metadata.get("security"), dict)
            else None
        ),
        "download_url": f"/download/{quote(name)}",
    }


def update_file_settings(name: str, payload: dict[str, Any]) -> dict[str, object]:
    service = current_drop_service()
    return service.public_record(service.update_expiry(name, payload))


def delete_file_record(name: str, password: object = None) -> None:
    current_drop_service().delete(name, password)


def _public_clipboard_entry(entry: dict[str, Any]) -> dict[str, Any]:
    protected = entry.get("password") is not None
    text_object = entry.get("text_object") if isinstance(entry.get("text_object"), dict) else {}
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
        "text_object_id": text_object.get("id", entry["id"]),
        "title": text_object.get("title", "Shared clipboard text"),
        "mode": text_object.get("mode", "plain"),
        "language": text_object.get("language"),
        "lifecycle": "temporary",
    }


def _purge_expired_clipboard_entries_locked(now: float | None = None) -> bool:
    global _CLIPBOARD_REVISION
    sweep = LIFECYCLE_SERVICE.sweep(
        (
            LifecycleItem(
                item_id=entry["id"],
                expires_at=parse_iso_timestamp(entry.get("expires_at")),
            )
            for entry in _CLIPBOARD_ENTRIES
        ),
        now,
    )
    if not sweep.expired_ids:
        return False
    expired_ids = set(sweep.expired_ids)
    _CLIPBOARD_ENTRIES[:] = [entry for entry in _CLIPBOARD_ENTRIES if entry["id"] not in expired_ids]
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
    text_id = uuid.uuid4().hex
    expires_at = _expires_at_from_seconds(expires_in_seconds, created)
    text_object = TEXT_OBJECTS.build(
        text_id=text_id, title="Shared clipboard text", content=text, mode="plain",
        scope_kind=TextScopeKind.DROP, scope_id=client_id,
        lifecycle=TextLifecycle.TEMPORARY,
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
        source_kind="clipboard_client", source_id=client_id,
        now=datetime.fromtimestamp(created, tz=timezone.utc),
    )
    entry = {
        "id": text_id,
        "text": text,
        "client_id": client_id,
        "source": source,
        "ip_address": ip_address,
        "created_at": utc_iso(created),
        "expires_at": expires_at,
        "password": create_password_record(password) if password else None,
        "text_object": text_object.to_record(),
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
        text_object = entry.get("text_object")
        if isinstance(text_object, dict):
            text_object["expires_at"] = entry.get("expires_at")
            text_object["updated_at"] = utc_iso()
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


def record_client_heartbeat(
    client_id: str,
    client_host: str,
    agent: dict[str, Any],
    now: float | None = None,
) -> None:
    current = time.time() if now is None else now
    with _CLIENTS_LOCK:
        purge_inactive_clients(current)
        previous = _ACTIVE_CLIENTS.get(client_id)
        connected_at = previous["connected_at"] if previous else utc_iso(current)
        _ACTIVE_CLIENTS[client_id] = {
            "id": client_id,
            "role": "client",
            "name": agent["device"],
            "status": "online",
            "ip_address": client_host,
            "ip_addresses": [client_host],
            "primary_ip": client_host,
            "connected_at": connected_at,
            "last_seen": utc_iso(current),
            "last_seen_epoch": current,
            **agent,
        }


DROP_CLIPBOARD_SERVICE = DropClipboardService(
    snapshot=clipboard_snapshot,
    share=add_clipboard_entry,
    update=update_clipboard_settings,
    unlock=unlock_clipboard_entry,
    delete=delete_clipboard_entry,
    clear=clear_clipboard_entries,
)
DROP_CLIENT_VISIBILITY_SERVICE = DropClientVisibilityService(
    records=_ACTIVE_CLIENTS,
    lock=_CLIENTS_LOCK,
    ttl_seconds=CLIENT_TTL_SECONDS,
    timestamp=utc_iso,
    server_record=server_device_record,
)


def request_port(request: Request) -> int:
    return load_port(default=request.url.port or 8080)


def cleanup_expired_items() -> None:
    with _FILES_LOCK:
        _purge_expired_files_locked()
        storage = current_storage_backend()
        transfer = current_transfer_service(storage)
        LIFECYCLE_SERVICE.cleanup_orphaned_uploads(
            storage,
            active_upload_ids=transfer.active_upload_ids(),
        )
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


def _drop_share_url(request: Request, filename: str, access_key: str | None) -> str:
    root = str(request.base_url).rstrip("/")
    target = f"{root}/drop/{quote(filename)}"
    return f"{target}?key={quote(access_key, safe='')}" if access_key else target


def _drop_download_url(filename: str, access_key: str | None) -> str:
    target = f"/download/{quote(filename)}"
    return f"{target}?key={quote(access_key, safe='')}" if access_key else target


def _malicious_download_confirmed(request: Request, payload: dict[str, object] | None = None) -> bool:
    """Accept only an explicit confirmation token from the download interaction."""

    return (
        request.query_params.get("confirm_malicious") == "true"
        or request.headers.get("x-nightwire-confirm-malicious") == "true"
        or (payload is not None and payload.get("confirm_malicious") is True)
    )


def _malicious_confirmation_response(exc: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "error": str(exc),
            "security_verdict": "malicious",
            "confirmation_required": True,
        },
        status_code=409,
        headers={"Cache-Control": "no-store"},
    )


async def drop_share_page(request: Request) -> Response:
    filename = request.path_params["filename"]
    try:
        current_drop_service().recipient_record(filename, request.query_params.get("key"))
    except DropAccessDeniedError as exc:
        return HTMLResponse(str(exc), status_code=403, headers={"Cache-Control": "no-store"})
    except (FileNotFoundError, ValueError) as exc:
        return HTMLResponse(str(exc), status_code=404, headers={"Cache-Control": "no-store"})
    share_page = STATIC_DIR / "drop-share.html"
    if not share_page.is_file():
        return HTMLResponse("NightWire Drop share assets are missing.", status_code=500)
    return FileResponse(share_page, media_type="text/html", headers={"Cache-Control": "no-store"})


async def drop_share_info(request: Request) -> JSONResponse:
    filename = request.path_params["filename"]
    access_key = request.query_params.get("key")
    try:
        record = current_drop_service().recipient_record(filename, access_key)
    except DropAccessDeniedError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    record["download_url"] = _drop_download_url(filename, access_key)
    return JSONResponse(
        {"drop": record, "share_url": _drop_share_url(request, filename, access_key)},
        headers={"Cache-Control": "no-store"},
    )


async def list_files(_: Request) -> JSONResponse:
    service = current_drop_service()
    if not service.active_drop_browsing_allowed:
        return JSONResponse(
            {"error": "Active Drop browsing is disabled by the deployment policy."},
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )
    files = [service.public_record(item) for item in service.list_items()]
    files.sort(key=lambda item: item["modified"], reverse=True)
    usage = shutil.disk_usage(FILES_DIR)
    return JSONResponse(
        {"files": files, "storage": {"total": usage.total, "used": usage.used, "free": usage.free},
         "usage": CAPACITY_MANAGER.report(UsageScope("drop")),
         "installation": CAPACITY_MANAGER.installation_report()},
        headers={"Cache-Control": "no-store"},
    )


async def list_active_drops(request: Request) -> JSONResponse:
    service = current_drop_service()
    if not service.active_drop_browsing_allowed:
        return JSONResponse(
            {"error": "Active Drop browsing is disabled by the deployment policy."},
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )
    drops = []
    for item in service.list_items():
        record = service.public_record(item)
        if service.access_key_enforced and item.access_key_required:
            record["share_url"] = None
        else:
            record["share_url"] = _drop_share_url(request, item.name, None)
            record["download_url"] = _drop_download_url(item.name, None)
        drops.append(record)
    drops.sort(key=lambda item: item["modified"], reverse=True)
    usage = shutil.disk_usage(FILES_DIR)
    return JSONResponse(
        {"drops": drops, "storage": {"total": usage.total, "used": usage.used, "free": usage.free},
         "usage": CAPACITY_MANAGER.report(UsageScope("drop")),
         "installation": CAPACITY_MANAGER.installation_report()},
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
            "drop_max_expiry_seconds": current_drop_service().effective_maximum_expiry_seconds,
            "drop_access_key_required": current_drop_service().access_key_enforced,
            "active_drop_browsing": current_drop_service().active_drop_browsing_allowed,
            "item_min_expiry_seconds": ITEM_MIN_EXPIRY_SECONDS,
            "item_max_expiry_seconds": ITEM_MAX_EXPIRY_SECONDS,
            "password_max_characters": PASSWORD_MAX_CHARACTERS,
            "installed_modules": SETTINGS.installed_modules.as_dict(),
            "deployment_profile": SETTINGS.deployment_profile.value,
            "network_urls": network_urls,
            "primary_network_url": network_urls[0] if network_urls else f"http://127.0.0.1:{port}",
        },
        headers={"Cache-Control": "no-store"},
    )


async def list_devices(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "devices": DROP_CLIENT_VISIBILITY_SERVICE.list_devices(request_port(request)),
            "client_ttl_seconds": CLIENT_TTL_SECONDS,
        },
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
    DROP_CLIENT_VISIBILITY_SERVICE.heartbeat(client_id, client_host, agent)

    return JSONResponse(
        {
            "ok": True,
            "devices": DROP_CLIENT_VISIBILITY_SERVICE.list_devices(request_port(request)),
            "client_ttl_seconds": CLIENT_TTL_SECONDS,
        },
        headers={"Cache-Control": "no-store"},
    )


async def list_clipboard(request: Request) -> JSONResponse:
    raw_revision = request.query_params.get("since_revision", "-1")
    try:
        since_revision = int(raw_revision)
    except ValueError:
        return JSONResponse({"error": "since_revision must be an integer."}, status_code=400)
    revision, entries = DROP_CLIPBOARD_SERVICE.snapshot()
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

    revision, entry = DROP_CLIPBOARD_SERVICE.share(
        text, client_id, source, client_host, expires_in_seconds, password
    )
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
        revision, entry = DROP_CLIPBOARD_SERVICE.update(entry_id, payload)
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
        text = DROP_CLIPBOARD_SERVICE.unlock(entry_id, payload.get("password"))
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True, "text": text}, headers={"Cache-Control": "no-store"})


async def clear_clipboard(_: Request) -> JSONResponse:
    try:
        revision = DROP_CLIPBOARD_SERVICE.clear()
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse({"ok": True, "revision": revision}, headers={"Cache-Control": "no-store"})


async def delete_clipboard(request: Request) -> JSONResponse:
    entry_id = request.path_params.get("entry_id", "")
    if not CLIPBOARD_ENTRY_ID_PATTERN.fullmatch(entry_id):
        return JSONResponse({"error": "A valid clipboard entry ID is required."}, status_code=400)
    try:
        payload = await read_json_payload(request, allow_empty=True)
        revision, deleted = DROP_CLIPBOARD_SERVICE.delete(entry_id, payload.get("password"))
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
        # Transport validation stays cheap so rejected requests never initialize storage.
        safe_file_path(filename)
        expires_in_seconds = normalize_file_expiry(
            request.headers.get("x-nightwire-expires-in-seconds")
        )
        service = current_drop_service()
        content_kind = request.headers.get("x-nightwire-drop-kind", "file").strip().lower()
        if content_kind not in {"file", "voice"}:
            raise ValueError("Binary Drop content kind must be file or voice.")
        uploaded = await service.upload(
            filename=filename,
            chunks=request.stream(),
            expires_in_seconds=expires_in_seconds,
            password=getattr(request.state, "drop_creation_password", None),
            declared_mime=request.headers.get("content-type"),
            content_kind=content_kind,
            expected_bytes=int(request.headers["content-length"]) if request.headers.get("content-length") else None,
        )
    except CapacityExceededError as exc:
        return JSONResponse({"error": str(exc), "code": "capacity_exceeded"}, status_code=413)
    except ProtectedDropOverwriteError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except ClientDisconnect:
        return JSONResponse({"ok": False, "cancelled": True}, status_code=499, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return _drop_upload_response(request, service, uploaded)


def _drop_upload_response(request: Request, service: DropService, uploaded) -> JSONResponse:
    file_record = service.public_record(uploaded.item)
    file_record["download_url"] = _drop_download_url(uploaded.item.name, uploaded.access_key)
    return JSONResponse(
        {
            "ok": True,
            "transfer_id": uploaded.transfer_id,
            "file": file_record,
            "access_key": uploaded.access_key,
            "share_url": _drop_share_url(request, uploaded.item.name, uploaded.access_key),
            "bytes_written": uploaded.bytes_written,
            "checksum_sha256": uploaded.checksum_sha256,
            "seconds": round(uploaded.seconds, 3),
            "average_bytes_per_second": round(uploaded.bytes_written / uploaded.seconds),
        },
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


async def share_drop_text(request: Request) -> JSONResponse:
    try:
        payload = await read_json_payload(request, maximum=CLIPBOARD_PAYLOAD_LIMIT)
        text = normalize_clipboard_text(payload.get("text"))
        password = normalize_optional_password(payload.get("password"))
        mode = payload.get("mode", "plain")
        language = payload.get("language")
        title = payload.get("title") or "Shared Text"
        text_id = uuid.uuid4().hex
        filename = f"text-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{text_id[:8]}.txt"
        text_object = TEXT_OBJECTS.build(
            text_id=text_id, title=title, content=text, mode=mode, language=language,
            scope_kind=TextScopeKind.DROP, scope_id=filename,
            lifecycle=TextLifecycle.TEMPORARY,
            source_kind=payload.get("source_kind"), source_id=payload.get("source_id"),
        )

        async def chunks():
            yield text.encode("utf-8")

        service = current_drop_service()
        uploaded = await service.upload(
            filename=filename,
            chunks=chunks(),
            expires_in_seconds=payload.get("expires_in_seconds"),
            password=password,
            declared_mime="text/plain; charset=utf-8",
            content_kind="text",
            expected_bytes=len(text.encode("utf-8")),
            text_object=text_object,
        )
    except CapacityExceededError as exc:
        return JSONResponse({"error": str(exc), "code": "capacity_exceeded"}, status_code=413)
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except (ValueError, TextValidationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return _drop_upload_response(request, service, uploaded)


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


def _download_headers(filename: str, size: int) -> dict[str, str]:
    encoded = quote(filename)
    disposition = (
        f'attachment; filename="{filename}"'
        if encoded == filename
        else f"attachment; filename*=utf-8''{encoded}"
    )
    return {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "Content-Disposition": disposition,
        "Content-Length": str(size),
        "X-Content-Type-Options": "nosniff",
    }


def _object_download_response(request: Request, filename: str, object_id: ObjectId) -> Response:
    if request.method == "HEAD":
        headers = _download_headers(filename, current_storage_backend().object_size(object_id))
        return Response(media_type="application/octet-stream", headers=headers)
    transfer = current_transfer_service()
    prepared = transfer.prepare_download(object_id, CHUNK_HINT)
    headers = _download_headers(filename, prepared.total_bytes)
    headers["X-NightWire-Transfer-ID"] = prepared.transfer_id
    return StreamingResponse(prepared.chunks, media_type="application/octet-stream", headers=headers)


async def download_file(request: Request) -> Response:
    filename = request.path_params["filename"]
    try:
        download = current_drop_service().download(
            filename,
            access_key=request.query_params.get("key"),
            confirmed_malicious=_malicious_download_confirmed(request),
        )
    except DropAccessDeniedError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except MaliciousDropConfirmationRequiredError as exc:
        return _malicious_confirmation_response(exc)
    except ProtectedDropItemError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    if download.item.object_id is not None:
        return _object_download_response(request, filename, download.item.object_id)
    return FileResponse(
        Path(download.legacy_path),
        filename=filename,
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def download_protected_file(request: Request) -> Response:
    filename = request.path_params["filename"]
    try:
        payload = await read_json_payload(request)
        download = current_drop_service().download(
            filename,
            supplied_password=payload.get("password"),
            access_key=request.query_params.get("key"),
            verify_protected=True,
            confirmed_malicious=_malicious_download_confirmed(request, payload),
        )
    except OverflowError as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except DropAccessDeniedError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except MaliciousDropConfirmationRequiredError as exc:
        return _malicious_confirmation_response(exc)
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    if download.item.object_id is not None:
        return _object_download_response(request, filename, download.item.object_id)
    return FileResponse(
        Path(download.legacy_path),
        filename=filename,
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


async def security_headers(request: Request, call_next):
    response = await PASSWORD_PROTECTION.middleware(request, call_next)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
        "media-src 'self' blob:; style-src 'self'; script-src 'self'; "
        "base-uri 'none'; frame-ancestors 'none'",
    )
    return response


def object_is_referenced(object_id: ObjectId) -> bool:
    """Expose Drop references to other modules without coupling their repositories."""
    with _FILES_LOCK:
        return any(item.object_id == object_id for item in DROP_REPOSITORY.list())


ROUTE_HANDLERS = {
    "root": root,
    "page": page,
    "drop_share_page": drop_share_page,
    "drop_share_info": drop_share_info,
    "list_active_drops": list_active_drops,
    "share_drop_text": share_drop_text,
    "list_files": list_files,
    "server_info": server_info,
    "list_devices": list_devices,
    "client_heartbeat": client_heartbeat,
    "list_clipboard": list_clipboard,
    "share_clipboard": share_clipboard,
    "clear_clipboard": clear_clipboard,
    "patch_clipboard": patch_clipboard,
    "delete_clipboard": delete_clipboard,
    "unlock_clipboard": unlock_clipboard,
    "qr_code": qr_code,
    "upload_file": upload_file,
    "patch_file": patch_file,
    "delete_file": delete_file,
    "download_protected_file": download_protected_file,
    "download_file": download_file,
    "start_cleanup_worker": start_cleanup_worker,
    "stop_cleanup_worker": stop_cleanup_worker,
    "object_is_referenced": object_is_referenced,
    "capacity_manager": current_capacity_manager,
}

app = build_application(SETTINGS, ROUTE_HANDLERS, http_middleware=[security_headers])


def main() -> None:
    port = load_port()
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
