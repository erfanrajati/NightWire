"""Drop application service composed exclusively over Core and Drop contracts."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from nightwire.core.lifecycle import LifecycleItem, LifecycleService
from nightwire.core.security import PasswordDigest, SecurityPipeline
from nightwire.core.storage import StorageBackend
from nightwire.core.transfer import TransferService
from nightwire.drop.domain import DropDownload, DropItem, DropUpload
from nightwire.drop.repository import DropRepository


class ProtectedDropItemError(PermissionError):
    """Direct download attempted for an item requiring password verification."""


class ProtectedDropOverwriteError(PermissionError):
    """Upload attempted to replace a protected logical name."""


class PasswordProtectionContract(Protocol):
    def create(self, password: str) -> PasswordDigest: ...

    def require(self, supplied: object, record: PasswordDigest | None, message: str) -> None: ...


class DropService:
    def __init__(
        self,
        *,
        repository: DropRepository,
        storage: StorageBackend,
        legacy_root: Path,
        transfer: TransferService,
        lifecycle: LifecycleService,
        security: SecurityPipeline,
        passwords: PasswordProtectionContract,
        validate_name,
        lock: threading.RLock,
        metadata_filename: str,
        default_expiry_seconds: int,
        minimum_expiry_seconds: int,
        maximum_expiry_seconds: int,
    ):
        self.repository = repository
        self.storage = storage
        self.legacy_root = legacy_root
        self.transfer = transfer
        self.lifecycle = lifecycle
        self.security = security
        self.passwords = passwords
        self.validate_name = validate_name
        self.lock = lock
        self.metadata_filename = metadata_filename
        self.default_expiry_seconds = default_expiry_seconds
        self.minimum_expiry_seconds = minimum_expiry_seconds
        self.maximum_expiry_seconds = maximum_expiry_seconds

    @staticmethod
    def _parse_timestamp(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return None

    @staticmethod
    def _iso(timestamp: float | None = None) -> str:
        value = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp is not None else datetime.now(timezone.utc)
        return value.isoformat()

    def normalize_expiry(self, value: object) -> int:
        if value is None:
            return self.default_expiry_seconds
        if isinstance(value, bool):
            raise ValueError("Auto-delete duration must be a number of seconds.")
        try:
            seconds = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Auto-delete duration must be a number of seconds.") from exc
        if seconds == 0:
            return 0
        if seconds < self.minimum_expiry_seconds:
            raise ValueError("Auto-delete must be at least 1 minute, or zero for unlimited.")
        if seconds > self.maximum_expiry_seconds:
            raise ValueError("Auto-delete cannot exceed 365 days.")
        return seconds

    def _expires_at(self, seconds: int, now: float | None = None) -> str | None:
        if seconds == 0:
            return None
        return self._iso((time.time() if now is None else now) + seconds)

    def _legacy_path(self, name: str) -> Path:
        return Path(self.validate_name(name))

    def _present(self, item: DropItem) -> bool:
        if item.object_id is not None:
            return self.storage.object_exists(item.object_id)
        return self._legacy_path(item.name).is_file()

    def _default_legacy_item(self, name: str, path: Path) -> DropItem:
        return DropItem(
            name=name,
            created_at=self._iso(path.stat().st_mtime),
            expires_at=None,
        )

    def _find_locked(self, name: str) -> tuple[DropItem | None, Path]:
        self.validate_name(name)
        item = self.repository.get(name)
        if item is not None:
            return item, self._legacy_path(name)
        path = self._legacy_path(name)
        if path.is_file():
            item = self._default_legacy_item(name, path)
            self.repository.put(item)
        return item, path

    def _delete_content(self, item: DropItem, legacy_path: Path) -> None:
        if item.object_id is not None:
            self.storage.delete_object(item.object_id)
        else:
            legacy_path.unlink(missing_ok=True)

    def purge_expired(self, now: float | None = None) -> bool:
        with self.lock:
            items = self.repository.list()
            sweep = self.lifecycle.sweep(
                (
                    LifecycleItem(
                        item_id=item.name,
                        expires_at=self._parse_timestamp(item.expires_at),
                        present=self._present(item),
                    )
                    for item in items
                ),
                now,
            )
            for name in sweep.expired_ids:
                item = self.repository.get(name)
                if item is not None:
                    self._delete_content(item, self._legacy_path(name))
            for name in (*sweep.expired_ids, *sweep.missing_ids):
                self.repository.remove(name)
            if sweep.changed:
                self.repository.save()
            return sweep.changed

    def list_items(self) -> tuple[DropItem, ...]:
        with self.lock:
            self.purge_expired()
            items = list(self.repository.list())
            known = {item.name for item in items}
            for path in self.legacy_root.iterdir():
                if (
                    not path.is_file()
                    or path.name in known
                    or path.name in {".gitkeep", self.metadata_filename}
                    or path.name.startswith(".uploading-")
                    or path.name.startswith(f".{self.metadata_filename}.")
                ):
                    continue
                item = self._default_legacy_item(path.name, path)
                self.repository.put(item)
                items.append(item)
            return tuple(items)

    def public_record(self, item: DropItem) -> dict[str, object]:
        if item.object_id is not None:
            size = self.storage.object_size(item.object_id)
            modified_at = self.storage.object_modified_at(item.object_id)
        else:
            stat = self._legacy_path(item.name).stat()
            size = stat.st_size
            modified_at = stat.st_mtime
        security = item.security or {}
        return {
            "name": item.name,
            "size": size,
            "modified": self._iso(modified_at),
            "created_at": item.created_at or self._iso(modified_at),
            "expires_at": item.expires_at,
            "password_protected": item.password_protected,
            "checksum_sha256": item.checksum_sha256,
            "security_verdict": security.get("verdict"),
            "detected_mime": security.get("detected_mime"),
            "download_url": f"/download/{quote(item.name)}",
        }

    async def upload(
        self,
        *,
        filename: str,
        chunks,
        expires_in_seconds: object,
        password: str | None,
        declared_mime: str | None,
    ) -> DropUpload:
        self.validate_name(filename)
        expiry = self.normalize_expiry(expires_in_seconds)
        with self.lock:
            self.purge_expired()
            existing, existing_path = self._find_locked(filename)
            if existing is not None and self._present(existing) and existing.password_protected:
                raise ProtectedDropOverwriteError("A password-protected file cannot be overwritten.")

        pending = await self.transfer.receive_upload(chunks)
        with self.lock:
            self.purge_expired()
            existing, existing_path = self._find_locked(filename)
            if existing is not None and self._present(existing) and existing.password_protected:
                self.transfer.discard_upload(pending)
                raise ProtectedDropOverwriteError("A password-protected file cannot be overwritten.")

            completed = self.transfer.finalize_upload(pending)
            try:
                security = await self.security.inspect(
                    completed.object_id,
                    filename=filename,
                    declared_mime=declared_mime,
                )
            except BaseException:
                self.storage.delete_object(completed.object_id)
                raise
            item = DropItem(
                name=filename,
                created_at=self._iso(),
                expires_at=self._expires_at(expiry),
                password=self.passwords.create(password) if password else None,
                object_id=completed.object_id,
                checksum_sha256=completed.checksum_sha256,
                size=completed.bytes_written,
                security=security.to_dict(),
            )
            previous = existing
            self.repository.put(item)
            try:
                self.repository.save()
            except BaseException:
                self.storage.delete_object(completed.object_id)
                if previous is None:
                    self.repository.remove(filename)
                else:
                    self.repository.put(previous)
                raise
            if previous is not None and self._present(previous):
                self._delete_content(previous, existing_path)

        return DropUpload(
            item=item,
            transfer_id=completed.transfer_id,
            bytes_written=completed.bytes_written,
            checksum_sha256=completed.checksum_sha256,
            seconds=completed.seconds,
        )

    def update_expiry(self, name: str, payload: dict[str, object]) -> DropItem:
        forbidden = set(payload) - {"expires_in_seconds"}
        if forbidden:
            raise ValueError("Password protection is immutable; only the countdown can be changed.")
        if "expires_in_seconds" not in payload:
            raise ValueError("An auto-delete duration is required.")
        with self.lock:
            self.purge_expired()
            item, path = self._find_locked(name)
            if item is None or not self._present(item):
                raise FileNotFoundError("File not found.")
            updated = replace(item, expires_at=self._expires_at(self.normalize_expiry(payload["expires_in_seconds"])))
            self.repository.put(updated)
            self.repository.save()
            return updated

    def delete(self, name: str, supplied_password: object = None) -> None:
        with self.lock:
            self.purge_expired()
            item, path = self._find_locked(name)
            if item is None or not self._present(item):
                raise FileNotFoundError("File not found.")
            self.passwords.require(supplied_password, item.password, "The file password is incorrect.")
            self._delete_content(item, path)
            self.repository.remove(name)
            self.repository.save()

    def download(
        self,
        name: str,
        *,
        supplied_password: object = None,
        verify_protected: bool = False,
    ) -> DropDownload:
        with self.lock:
            self.purge_expired()
            item, path = self._find_locked(name)
            if item is None or not self._present(item):
                raise FileNotFoundError("File not found.")
            if item.password_protected and not verify_protected:
                raise ProtectedDropItemError("This file is password protected.")
            if verify_protected:
                self.passwords.require(supplied_password, item.password, "The file password is incorrect.")
            return DropDownload(
                item=item,
                size=(self.storage.object_size(item.object_id) if item.object_id is not None else path.stat().st_size),
                legacy_path=str(path) if item.object_id is None else None,
            )


__all__ = [
    "DropService",
    "ProtectedDropItemError",
    "ProtectedDropOverwriteError",
]
