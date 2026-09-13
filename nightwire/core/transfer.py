"""Streaming transfer contracts, progress state, and the Core implementation."""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import AsyncIterable, Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from nightwire.core.storage import ObjectId, StorageBackend, TemporaryUploadId


class TransferDirection(StrEnum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


class TransferPhase(StrEnum):
    STARTED = "started"
    TRANSFERRING = "transferring"
    PENDING = "pending"
    FINALIZED = "finalized"
    COMPLETED = "completed"
    DISCARDED = "discarded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TransferProgress:
    """Immutable progress event suitable for modules or a future API projection."""

    transfer_id: str
    direction: TransferDirection
    phase: TransferPhase
    bytes_transferred: int
    total_bytes: int | None
    updated_at: float
    object_id: ObjectId | None = None
    upload_id: TemporaryUploadId | None = None
    error: str | None = None

    @property
    def fraction(self) -> float | None:
        if self.total_bytes is None:
            return None
        if self.total_bytes == 0:
            return 1.0 if self.phase in {TransferPhase.FINALIZED, TransferPhase.COMPLETED} else 0.0
        return min(self.bytes_transferred / self.total_bytes, 1.0)


ProgressHook = Callable[[TransferProgress], None]


class TransferProgressStore:
    """Thread-safe bounded state containing the latest event per transfer."""

    def __init__(self, history_limit: int = 256):
        if history_limit < 1:
            raise ValueError("Progress history must retain at least one transfer.")
        self.history_limit = history_limit
        self._latest: dict[str, TransferProgress] = {}
        self._order: deque[str] = deque()
        self._lock = threading.RLock()

    def record(self, progress: TransferProgress) -> None:
        with self._lock:
            if progress.transfer_id not in self._latest:
                self._order.append(progress.transfer_id)
            self._latest[progress.transfer_id] = progress
            while len(self._order) > self.history_limit:
                self._latest.pop(self._order.popleft(), None)

    def get(self, transfer_id: str) -> TransferProgress | None:
        with self._lock:
            return self._latest.get(transfer_id)

    def snapshot(self) -> tuple[TransferProgress, ...]:
        with self._lock:
            return tuple(self._latest[transfer_id] for transfer_id in self._order if transfer_id in self._latest)


@dataclass(frozen=True, slots=True)
class PendingUpload:
    """A fully streamed upload that has not entered permanent storage."""

    transfer_id: str
    upload_id: TemporaryUploadId
    bytes_written: int
    checksum_sha256: str
    seconds: float


@dataclass(frozen=True, slots=True)
class CompletedUpload:
    """Final transfer facts associated with a stable object ID."""

    transfer_id: str
    object_id: ObjectId
    bytes_written: int
    checksum_sha256: str
    seconds: float


@dataclass(frozen=True, slots=True)
class DownloadTransfer:
    """Prepared object download with observable progress and streamed chunks."""

    transfer_id: str
    object_id: ObjectId
    total_bytes: int
    chunks: AsyncIterable[bytes]


class TransferService(ABC):
    """Stream uploads/downloads and finalize content without filesystem paths."""

    @abstractmethod
    async def receive_upload(self, chunks: AsyncIterable[bytes]) -> PendingUpload:
        """Stream chunks into isolated temporary storage and calculate integrity."""

    @abstractmethod
    def finalize_upload(self, pending: PendingUpload, object_id: ObjectId | None = None) -> CompletedUpload:
        """Promote one pending upload into permanent storage."""

    @abstractmethod
    def discard_upload(self, pending: PendingUpload) -> None:
        """Discard one pending upload without finalizing it."""

    @abstractmethod
    def prepare_download(self, object_id: ObjectId, chunk_size: int = 1024 * 1024) -> DownloadTransfer:
        """Prepare a lazily streamed permanent-object download."""


class CoreTransferService(TransferService):
    """Core streaming implementation backed by a logical StorageBackend."""

    def __init__(
        self,
        storage: StorageBackend,
        *,
        progress_store: TransferProgressStore | None = None,
        progress_hooks: Iterable[ProgressHook] = (),
    ):
        self.storage = storage
        self.progress_store = progress_store or TransferProgressStore()
        self._progress_hooks = [self.progress_store.record, *progress_hooks]
        self._active_uploads: set[TemporaryUploadId] = set()
        self._active_lock = threading.RLock()

    def add_progress_hook(self, hook: ProgressHook) -> None:
        if hook not in self._progress_hooks:
            self._progress_hooks.append(hook)

    def remove_progress_hook(self, hook: ProgressHook) -> None:
        if hook == self.progress_store.record:
            return
        try:
            self._progress_hooks.remove(hook)
        except ValueError:
            pass

    def active_upload_ids(self) -> frozenset[TemporaryUploadId]:
        with self._active_lock:
            return frozenset(self._active_uploads)

    def _emit(
        self,
        transfer_id: str,
        direction: TransferDirection,
        phase: TransferPhase,
        bytes_transferred: int,
        total_bytes: int | None,
        *,
        object_id: ObjectId | None = None,
        upload_id: TemporaryUploadId | None = None,
        error: str | None = None,
    ) -> None:
        progress = TransferProgress(
            transfer_id=transfer_id,
            direction=direction,
            phase=phase,
            bytes_transferred=bytes_transferred,
            total_bytes=total_bytes,
            updated_at=time.time(),
            object_id=object_id,
            upload_id=upload_id,
            error=error,
        )
        for hook in tuple(self._progress_hooks):
            try:
                hook(progress)
            except Exception:
                continue

    async def receive_upload(self, chunks: AsyncIterable[bytes]) -> PendingUpload:
        transfer_id = uuid.uuid4().hex
        upload_id = self.storage.allocate_temporary_upload()
        with self._active_lock:
            self._active_uploads.add(upload_id)
        digest = hashlib.sha256()
        total_written = 0
        started = time.perf_counter()
        self._emit(transfer_id, TransferDirection.UPLOAD, TransferPhase.STARTED, 0, None, upload_id=upload_id)
        try:
            async with await self.storage.open_temporary_upload(upload_id, "wb") as output:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    digest.update(chunk)
                    await output.write(chunk)
                    total_written += len(chunk)
                    self._emit(
                        transfer_id,
                        TransferDirection.UPLOAD,
                        TransferPhase.TRANSFERRING,
                        total_written,
                        None,
                        upload_id=upload_id,
                    )
                await output.flush()
        except BaseException as exc:
            self.storage.discard_temporary_upload(upload_id)
            with self._active_lock:
                self._active_uploads.discard(upload_id)
            self._emit(
                transfer_id,
                TransferDirection.UPLOAD,
                TransferPhase.FAILED,
                total_written,
                None,
                upload_id=upload_id,
                error=type(exc).__name__,
            )
            raise

        elapsed = max(time.perf_counter() - started, 0.001)
        self._emit(
            transfer_id,
            TransferDirection.UPLOAD,
            TransferPhase.PENDING,
            total_written,
            total_written,
            upload_id=upload_id,
        )
        return PendingUpload(
            transfer_id=transfer_id,
            upload_id=upload_id,
            bytes_written=total_written,
            checksum_sha256=digest.hexdigest(),
            seconds=elapsed,
        )

    def finalize_upload(self, pending: PendingUpload, object_id: ObjectId | None = None) -> CompletedUpload:
        try:
            stored = self.storage.finalize_temporary_upload(pending.upload_id, object_id)
            if stored.size != pending.bytes_written:
                self.storage.delete_object(stored.object_id)
                raise OSError("Finalized object size does not match the streamed upload.")
        except BaseException as exc:
            self._emit(
                pending.transfer_id,
                TransferDirection.UPLOAD,
                TransferPhase.FAILED,
                pending.bytes_written,
                pending.bytes_written,
                upload_id=pending.upload_id,
                error=type(exc).__name__,
            )
            raise
        finally:
            with self._active_lock:
                self._active_uploads.discard(pending.upload_id)

        self._emit(
            pending.transfer_id,
            TransferDirection.UPLOAD,
            TransferPhase.FINALIZED,
            pending.bytes_written,
            pending.bytes_written,
            object_id=stored.object_id,
        )
        return CompletedUpload(
            transfer_id=pending.transfer_id,
            object_id=stored.object_id,
            bytes_written=pending.bytes_written,
            checksum_sha256=pending.checksum_sha256,
            seconds=pending.seconds,
        )

    def discard_upload(self, pending: PendingUpload) -> None:
        self.storage.discard_temporary_upload(pending.upload_id)
        with self._active_lock:
            self._active_uploads.discard(pending.upload_id)
        self._emit(
            pending.transfer_id,
            TransferDirection.UPLOAD,
            TransferPhase.DISCARDED,
            pending.bytes_written,
            pending.bytes_written,
            upload_id=pending.upload_id,
        )

    def prepare_download(self, object_id: ObjectId, chunk_size: int = 1024 * 1024) -> DownloadTransfer:
        if chunk_size < 1:
            raise ValueError("Download chunk size must be positive.")
        total_bytes = self.storage.object_size(object_id)
        transfer_id = uuid.uuid4().hex
        self._emit(
            transfer_id,
            TransferDirection.DOWNLOAD,
            TransferPhase.STARTED,
            0,
            total_bytes,
            object_id=object_id,
        )

        async def chunks():
            transferred = 0
            try:
                async with await self.storage.open_object(object_id, "rb") as source:
                    while True:
                        chunk = await source.read(chunk_size)
                        if not chunk:
                            break
                        transferred += len(chunk)
                        self._emit(
                            transfer_id,
                            TransferDirection.DOWNLOAD,
                            TransferPhase.TRANSFERRING,
                            transferred,
                            total_bytes,
                            object_id=object_id,
                        )
                        yield chunk
            except BaseException as exc:
                self._emit(
                    transfer_id,
                    TransferDirection.DOWNLOAD,
                    TransferPhase.FAILED,
                    transferred,
                    total_bytes,
                    object_id=object_id,
                    error=type(exc).__name__,
                )
                raise
            self._emit(
                transfer_id,
                TransferDirection.DOWNLOAD,
                TransferPhase.COMPLETED,
                transferred,
                total_bytes,
                object_id=object_id,
            )

        return DownloadTransfer(
            transfer_id=transfer_id,
            object_id=object_id,
            total_bytes=total_bytes,
            chunks=chunks(),
        )


__all__ = [
    "CompletedUpload",
    "CoreTransferService",
    "DownloadTransfer",
    "PendingUpload",
    "ProgressHook",
    "TransferDirection",
    "TransferPhase",
    "TransferProgress",
    "TransferProgressStore",
    "TransferService",
]
