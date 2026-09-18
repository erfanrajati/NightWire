"""Drop application service composed exclusively over Core and Drop contracts."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from nightwire.core.config import DeploymentProfile
from nightwire.core.capacity import UsageScope
from nightwire.core.lifecycle import LifecycleItem, LifecycleService
from nightwire.core.security import (
    CoreSecurityPolicy,
    PasswordDigest,
    SecurityAction,
    SecurityPipeline,
    SecurityVerdict,
)
from nightwire.core.storage import StorageBackend
from nightwire.core.transfer import TransferService
from nightwire.drop.domain import AccessKeyDigest, DropDownload, DropItem, DropUpload
from nightwire.drop.repository import DropRepository
from nightwire.text import TextObject, TextProvenance


class ProtectedDropItemError(PermissionError):
    """Direct download attempted for an item requiring password verification."""


class ProtectedDropOverwriteError(PermissionError):
    """Upload attempted to replace a protected logical name."""


class DropAccessDeniedError(PermissionError):
    """A Drop bearer Access Key was missing or invalid."""


class MaliciousDropConfirmationRequiredError(PermissionError):
    """A malicious Drop download was attempted without deliberate confirmation."""


class PasswordProtectionContract(Protocol):
    def create(self, password: str) -> PasswordDigest: ...

    def require(self, supplied: object, record: PasswordDigest | None, message: str) -> None: ...


class AccessKeyPolicyContract(Protocol):
    def issue(self) -> tuple[str, AccessKeyDigest]: ...

    def require(self, supplied: object, record: AccessKeyDigest | None) -> None: ...


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
        access_keys: AccessKeyPolicyContract,
        validate_name,
        lock: threading.RLock,
        metadata_filename: str,
        default_expiry_seconds: int,
        minimum_expiry_seconds: int,
        maximum_expiry_seconds: int,
        deployment_profile: DeploymentProfile,
        anonymous_internet_maximum_expiry_seconds: int,
        trusted_network_relaxed_access: bool = False,
        trusted_network_active_drop_browsing: bool = True,
        security_policy: CoreSecurityPolicy | None = None,
    ):
        self.repository = repository
        self.storage = storage
        self.legacy_root = legacy_root
        self.transfer = transfer
        self.lifecycle = lifecycle
        self.security = security
        self.passwords = passwords
        self.access_keys = access_keys
        self.validate_name = validate_name
        self.lock = lock
        self.metadata_filename = metadata_filename
        self.default_expiry_seconds = default_expiry_seconds
        self.minimum_expiry_seconds = minimum_expiry_seconds
        self.maximum_expiry_seconds = maximum_expiry_seconds
        self.deployment_profile = deployment_profile
        self.anonymous_internet_maximum_expiry_seconds = anonymous_internet_maximum_expiry_seconds
        self.trusted_network_relaxed_access = trusted_network_relaxed_access
        self.trusted_network_active_drop_browsing = trusted_network_active_drop_browsing
        self.security_policy = security_policy or CoreSecurityPolicy()

    @property
    def access_key_enforced(self) -> bool:
        return not (
            self.deployment_profile is DeploymentProfile.TRUSTED_PRIVATE
            and self.trusted_network_relaxed_access
        )

    @property
    def active_drop_browsing_allowed(self) -> bool:
        # An active directory is useful only when its entries remain actionable.
        # Raw Access Keys are intentionally non-recoverable, so a trusted manager
        # can reopen links and downloads only when keyless trusted access is also
        # enabled. Public deployments never satisfy either policy condition.
        return (
            self.deployment_profile is DeploymentProfile.TRUSTED_PRIVATE
            and self.trusted_network_active_drop_browsing
            and not self.access_key_enforced
        )

    @property
    def effective_maximum_expiry_seconds(self) -> int:
        if self.deployment_profile is DeploymentProfile.INTERNET_FACING:
            return min(self.maximum_expiry_seconds, self.anonymous_internet_maximum_expiry_seconds)
        return self.maximum_expiry_seconds

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
            seconds = self.default_expiry_seconds
        elif isinstance(value, bool):
            raise ValueError("Auto-delete duration must be a number of seconds.")
        else:
            try:
                seconds = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Auto-delete duration must be a number of seconds.") from exc
        if seconds < self.minimum_expiry_seconds:
            raise ValueError("A Drop lifetime must be at least 1 minute.")
        if seconds > self.effective_maximum_expiry_seconds:
            if self.deployment_profile is DeploymentProfile.INTERNET_FACING:
                raise ValueError("Anonymous internet-facing Drops cannot live longer than 24 hours.")
            raise ValueError("A Drop lifetime cannot exceed 365 days.")
        return seconds

    def _expires_at(self, seconds: int, now: float | None = None) -> str | None:
        return self._iso((time.time() if now is None else now) + seconds)

    def _require_access(self, item: DropItem, supplied: object) -> None:
        if not self.access_key_enforced:
            return
        try:
            self.access_keys.require(supplied, item.access_key_digest)
        except PermissionError as exc:
            raise DropAccessDeniedError(str(exc)) from exc

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

    def _commit_expiration_locked(
        self,
        expired_ids: tuple[str, ...],
        missing_ids: tuple[str, ...],
    ) -> None:
        """Commit byte/credential/metadata removal as one locked Drop transition."""

        for name in expired_ids:
            item = self.repository.get(name)
            if item is not None:
                # Core deletion also removes the object's security sidecar.
                self._delete_content(item, self._legacy_path(name))
        for name in (*expired_ids, *missing_ids):
            # The Access Key digest is part of this record and disappears in the
            # same atomic metadata-file replacement as the rest of the Drop.
            self.repository.remove(name)
        self.repository.save()

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
            if sweep.changed:
                self._commit_expiration_locked(sweep.expired_ids, sweep.missing_ids)
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
        security = dict(item.security) if item.security else {
            "verdict": SecurityVerdict.UNSCANNED.value,
            "detected_mime": "application/octet-stream",
            "detection_basis": "legacy-uninspected",
            "detection_confidence": "low",
            "filename_extension_mime": None,
            "declared_mime": None,
            "extension_matches_detected": None,
            "declared_matches_detected": None,
            "mismatches": [],
            "scanner": None,
            "scanner_version": None,
            "signature_metadata": {},
            "findings": ["legacy_object_uninspected"],
            "inspected_at": None,
        }
        verdict = security.get("verdict", SecurityVerdict.UNSCANNED.value)
        return {
            "name": item.name,
            "size": size,
            "modified": self._iso(modified_at),
            "created_at": item.created_at or self._iso(modified_at),
            "expires_at": item.expires_at,
            "content_kind": item.content_kind,
            "access_key_required": item.access_key_required and self.access_key_enforced,
            "password_protected": item.password_protected,
            "checksum_sha256": item.checksum_sha256,
            "security": security,
            "security_verdict": verdict,
            "detected_mime": security.get("detected_mime"),
            "download_confirmation_required": verdict == SecurityVerdict.MALICIOUS.value,
            "download_url": f"/download/{quote(item.name)}",
            "text": (item.text_object.public_dict(include_content=False)
                     if item.text_object is not None else None),
        }

    async def upload(
        self,
        *,
        filename: str,
        chunks,
        expires_in_seconds: object,
        password: str | None,
        declared_mime: str | None,
        content_kind: str = "file",
        expected_bytes: int | None = None,
        text_object: TextObject | None = None,
    ) -> DropUpload:
        self.validate_name(filename)
        if content_kind not in {"file", "text", "voice"}:
            raise ValueError("Drop content kind must be file, text, or voice.")
        expiry = self.normalize_expiry(expires_in_seconds)
        with self.lock:
            self.purge_expired()
            existing, existing_path = self._find_locked(filename)
            if existing is not None and self._present(existing) and existing.password_protected:
                raise ProtectedDropOverwriteError("A password-protected file cannot be overwritten.")

        pending = await self.transfer.receive_upload(
            chunks, usage_scope=UsageScope("drop"), expected_bytes=expected_bytes,
            quota_credit=(existing.size or 0) if existing is not None else 0,
        )
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
                if hasattr(self.transfer, "complete_upload"):
                    self.transfer.complete_upload(pending)
                raise
            access_key, access_key_digest = self.access_keys.issue()
            created_at_epoch = time.time()
            expires_at = self._expires_at(expiry, created_at_epoch)
            item = DropItem(
                name=filename,
                created_at=self._iso(created_at_epoch),
                expires_at=expires_at,
                content_kind=content_kind,
                access_key_digest=access_key_digest,
                password=self.passwords.create(password) if password else None,
                object_id=completed.object_id,
                checksum_sha256=completed.checksum_sha256,
                size=completed.bytes_written,
                security=security.to_dict(),
                text_object=(
                    replace(
                        text_object,
                        scope_id=filename,
                        expires_at=(datetime.fromisoformat(expires_at) if expires_at else None),
                        provenance=TextProvenance("core_object", str(completed.object_id)),
                    )
                    if text_object is not None else None
                ),
            )
            previous = existing
            self.repository.put(item)
            try:
                self.repository.save()
            except BaseException:
                self.storage.delete_object(completed.object_id)
                if hasattr(self.transfer, "complete_upload"):
                    self.transfer.complete_upload(pending)
                if previous is None:
                    self.repository.remove(filename)
                else:
                    self.repository.put(previous)
                raise
            if previous is not None and self._present(previous):
                self._delete_content(previous, existing_path)
            if hasattr(self.transfer, "complete_upload"):
                self.transfer.complete_upload(pending)

        return DropUpload(
            item=item,
            access_key=access_key,
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
        access_key: object = None,
        verify_protected: bool = False,
        confirmed_malicious: bool = False,
    ) -> DropDownload:
        with self.lock:
            self.purge_expired()
            item, path = self._find_locked(name)
            if item is None or not self._present(item):
                raise FileNotFoundError("File not found.")
            self._require_access(item, access_key)
            decision = self.security_policy.evaluate(
                (item.security or {}).get("verdict"),
                SecurityAction.DOWNLOAD,
                confirmed=confirmed_malicious is True,
            )
            if not decision.allowed:
                raise MaliciousDropConfirmationRequiredError(decision.reason)
            if item.password_protected and not verify_protected:
                raise ProtectedDropItemError("This file is password protected.")
            if verify_protected:
                self.passwords.require(supplied_password, item.password, "The file password is incorrect.")
            return DropDownload(
                item=item,
                size=(self.storage.object_size(item.object_id) if item.object_id is not None else path.stat().st_size),
                legacy_path=str(path) if item.object_id is None else None,
            )

    def recipient_record(self, name: str, access_key: object) -> dict[str, object]:
        with self.lock:
            self.purge_expired()
            item, _ = self._find_locked(name)
            if item is None or not self._present(item):
                raise FileNotFoundError("Drop not found or expired.")
            self._require_access(item, access_key)
            record = self.public_record(item)
            record.pop("download_url", None)
            return record


__all__ = [
    "DropService",
    "DropAccessDeniedError",
    "MaliciousDropConfirmationRequiredError",
    "ProtectedDropItemError",
    "ProtectedDropOverwriteError",
]
