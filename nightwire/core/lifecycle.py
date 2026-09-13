"""Core lifecycle decisions and temporary-upload housekeeping."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from nightwire.core.storage import StorageBackend, TemporaryUploadId


DEFAULT_ORPHANED_UPLOAD_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class LifecycleItem:
    """Backend-neutral lifecycle facts for one logical item."""

    item_id: str
    expires_at: float | None
    present: bool = True


@dataclass(frozen=True, slots=True)
class LifecycleSweep:
    """Classification returned by a lifecycle sweep."""

    expired_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.expired_ids or self.missing_ids)


class LifecycleService(ABC):
    """Decide item expiration and reclaim abandoned temporary uploads."""

    @abstractmethod
    def sweep(self, items: Iterable[LifecycleItem], now: float | None = None) -> LifecycleSweep:
        """Classify expired and physically missing logical items."""

    @abstractmethod
    def cleanup_orphaned_uploads(
        self,
        storage: StorageBackend,
        *,
        older_than_seconds: int = DEFAULT_ORPHANED_UPLOAD_AGE_SECONDS,
        active_upload_ids: Iterable[TemporaryUploadId] = (),
        now: float | None = None,
    ) -> tuple[TemporaryUploadId, ...]:
        """Discard inactive temporary uploads older than the configured threshold."""


class CoreLifecycleService(LifecycleService):
    def sweep(self, items: Iterable[LifecycleItem], now: float | None = None) -> LifecycleSweep:
        current = time.time() if now is None else now
        expired = []
        missing = []
        for item in items:
            if not item.present:
                missing.append(item.item_id)
            elif item.expires_at is not None and item.expires_at <= current:
                expired.append(item.item_id)
        return LifecycleSweep(expired_ids=tuple(expired), missing_ids=tuple(missing))

    def cleanup_orphaned_uploads(
        self,
        storage: StorageBackend,
        *,
        older_than_seconds: int = DEFAULT_ORPHANED_UPLOAD_AGE_SECONDS,
        active_upload_ids: Iterable[TemporaryUploadId] = (),
        now: float | None = None,
    ) -> tuple[TemporaryUploadId, ...]:
        if older_than_seconds < 0:
            raise ValueError("Orphaned-upload age cannot be negative.")
        current = time.time() if now is None else now
        active = set(active_upload_ids)
        removed = []
        for upload in storage.list_temporary_uploads():
            if upload.upload_id in active or current - upload.modified_at < older_than_seconds:
                continue
            storage.discard_temporary_upload(upload.upload_id)
            removed.append(upload.upload_id)
        return tuple(removed)


__all__ = [
    "CoreLifecycleService",
    "DEFAULT_ORPHANED_UPLOAD_AGE_SECONDS",
    "LifecycleItem",
    "LifecycleService",
    "LifecycleSweep",
]
