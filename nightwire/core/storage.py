"""Logical object storage contracts and the local-filesystem backend."""

from __future__ import annotations

import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio


_IDENTIFIER_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OBJECTS_DIRECTORY_NAME = ".nightwire-objects"
OBJECT_METADATA_DIRECTORY_NAME = ".nightwire-object-metadata"
TEMPORARY_UPLOADS_DIRECTORY_NAME = ".nightwire-uploads"


@dataclass(frozen=True, slots=True)
class ObjectId:
    """Stable logical identity for one permanently stored object."""

    value: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.value):
            raise ValueError("Object IDs must contain exactly 32 lowercase hexadecimal characters.")

    @classmethod
    def new(cls) -> ObjectId:
        return cls(uuid.uuid4().hex)

    @classmethod
    def parse(cls, value: object) -> ObjectId:
        if not isinstance(value, str):
            raise ValueError("A valid object ID is required.")
        return cls(value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TemporaryUploadId:
    """Logical identity for an isolated, not-yet-finalized upload."""

    value: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.value):
            raise ValueError("Temporary upload IDs must contain exactly 32 lowercase hexadecimal characters.")

    @classmethod
    def new(cls) -> TemporaryUploadId:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Backend-neutral facts returned after an object is finalized."""

    object_id: ObjectId
    size: int


@dataclass(frozen=True, slots=True)
class TemporaryUpload:
    """Backend-neutral facts about one unfinished upload."""

    upload_id: TemporaryUploadId
    size: int
    modified_at: float


class StorageBackend(ABC):
    """Storage operations addressed only by logical object/upload IDs."""

    @abstractmethod
    def allocate_temporary_upload(self) -> TemporaryUploadId:
        """Reserve an isolated temporary upload and return its logical ID."""

    @abstractmethod
    async def open_temporary_upload(self, upload_id: TemporaryUploadId, mode: str = "wb") -> Any:
        """Open a previously allocated temporary upload."""

    @abstractmethod
    def temporary_upload_exists(self, upload_id: TemporaryUploadId) -> bool:
        """Return whether a temporary upload currently exists."""

    @abstractmethod
    def discard_temporary_upload(self, upload_id: TemporaryUploadId) -> None:
        """Remove a temporary upload if it exists."""

    @abstractmethod
    def list_temporary_uploads(self) -> tuple[TemporaryUpload, ...]:
        """Return unfinished uploads available for orphan cleanup."""

    @abstractmethod
    def finalize_temporary_upload(
        self,
        upload_id: TemporaryUploadId,
        object_id: ObjectId | None = None,
    ) -> StoredObject:
        """Atomically promote a temporary upload to permanent object storage."""

    @abstractmethod
    def object_exists(self, object_id: ObjectId) -> bool:
        """Return whether an object currently exists."""

    @abstractmethod
    async def open_object(self, object_id: ObjectId, mode: str = "rb") -> Any:
        """Open a permanent object by logical ID."""

    @abstractmethod
    def object_size(self, object_id: ObjectId) -> int:
        """Return an object's current byte length."""

    @abstractmethod
    def object_modified_at(self, object_id: ObjectId) -> float:
        """Return an object's modification timestamp."""

    @abstractmethod
    def delete_object(self, object_id: ObjectId) -> None:
        """Remove an object if it exists."""

    @abstractmethod
    def save_object_metadata(self, object_id: ObjectId, metadata: dict[str, Any]) -> None:
        """Atomically persist JSON-compatible metadata for an object."""

    @abstractmethod
    def load_object_metadata(self, object_id: ObjectId) -> dict[str, Any] | None:
        """Load an object's persisted metadata when present."""


class LocalFilesystemStorage(StorageBackend):
    """Object-ID storage rooted inside the existing NightWire files directory."""

    def __init__(self, storage_root: Path | str):
        self.storage_root = Path(storage_root).expanduser().resolve()
        self.objects_root = (self.storage_root / OBJECTS_DIRECTORY_NAME).resolve()
        self.object_metadata_root = (self.storage_root / OBJECT_METADATA_DIRECTORY_NAME).resolve()
        self.temporary_uploads_root = (self.storage_root / TEMPORARY_UPLOADS_DIRECTORY_NAME).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.object_metadata_root.mkdir(parents=True, exist_ok=True)
        self.temporary_uploads_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _contained_reference(parent: Path, name: str) -> Path:
        reference = (parent / name).resolve()
        if reference.parent != parent:
            raise ValueError("Storage reference escaped its configured root.")
        return reference

    def object_reference(self, object_id: ObjectId) -> Path:
        """Map a validated object ID to its opaque physical reference."""

        return self._contained_reference(self.objects_root, object_id.value)

    def temporary_upload_reference(self, upload_id: TemporaryUploadId) -> Path:
        """Map a validated upload ID to its isolated physical reference."""

        return self._contained_reference(self.temporary_uploads_root, f"{upload_id.value}.part")

    def object_metadata_reference(self, object_id: ObjectId) -> Path:
        """Map a validated object ID to its internal metadata sidecar."""

        return self._contained_reference(self.object_metadata_root, f"{object_id.value}.json")

    def allocate_temporary_upload(self) -> TemporaryUploadId:
        while True:
            upload_id = TemporaryUploadId.new()
            reference = self.temporary_upload_reference(upload_id)
            try:
                reference.touch(exist_ok=False)
            except FileExistsError:
                continue
            return upload_id

    async def open_temporary_upload(self, upload_id: TemporaryUploadId, mode: str = "wb") -> Any:
        if mode not in {"wb", "ab", "rb"}:
            raise ValueError("Temporary uploads support only binary read/write modes.")
        return await anyio.open_file(self.temporary_upload_reference(upload_id), mode)

    def temporary_upload_exists(self, upload_id: TemporaryUploadId) -> bool:
        return self.temporary_upload_reference(upload_id).is_file()

    def discard_temporary_upload(self, upload_id: TemporaryUploadId) -> None:
        self.temporary_upload_reference(upload_id).unlink(missing_ok=True)

    def list_temporary_uploads(self) -> tuple[TemporaryUpload, ...]:
        uploads = []
        for reference in self.temporary_uploads_root.iterdir():
            match = re.fullmatch(r"([0-9a-f]{32})\.part", reference.name)
            if match is None:
                continue
            try:
                stat = reference.stat()
            except FileNotFoundError:
                continue
            if not reference.is_file():
                continue
            uploads.append(
                TemporaryUpload(
                    upload_id=TemporaryUploadId(match.group(1)),
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )
        return tuple(sorted(uploads, key=lambda upload: upload.modified_at))

    def finalize_temporary_upload(
        self,
        upload_id: TemporaryUploadId,
        object_id: ObjectId | None = None,
    ) -> StoredObject:
        source = self.temporary_upload_reference(upload_id)
        if not source.is_file():
            raise FileNotFoundError("Temporary upload not found.")
        resolved_object_id = object_id or ObjectId.new()
        destination = self.object_reference(resolved_object_id)
        if destination.exists():
            raise FileExistsError("The target object ID already exists.")
        os.replace(source, destination)
        return StoredObject(object_id=resolved_object_id, size=destination.stat().st_size)

    def object_exists(self, object_id: ObjectId) -> bool:
        return self.object_reference(object_id).is_file()

    async def open_object(self, object_id: ObjectId, mode: str = "rb") -> Any:
        if mode != "rb":
            raise ValueError("Permanent objects can only be opened for binary reading.")
        return await anyio.open_file(self.object_reference(object_id), mode)

    def object_size(self, object_id: ObjectId) -> int:
        return self.object_reference(object_id).stat().st_size

    def object_modified_at(self, object_id: ObjectId) -> float:
        return self.object_reference(object_id).stat().st_mtime

    def delete_object(self, object_id: ObjectId) -> None:
        self.object_reference(object_id).unlink(missing_ok=True)
        self.object_metadata_reference(object_id).unlink(missing_ok=True)

    def save_object_metadata(self, object_id: ObjectId, metadata: dict[str, Any]) -> None:
        if not self.object_exists(object_id):
            raise FileNotFoundError("Stored object not found.")
        destination = self.object_metadata_reference(object_id)
        temporary = self._contained_reference(
            self.object_metadata_root,
            f".{object_id.value}.{uuid.uuid4().hex}.tmp",
        )
        payload = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            temporary.write_text(payload + "\n", encoding="utf-8")
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def load_object_metadata(self, object_id: ObjectId) -> dict[str, Any] | None:
        reference = self.object_metadata_reference(object_id)
        if not reference.is_file():
            return None
        try:
            payload = json.loads(reference.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None


__all__ = [
    "LocalFilesystemStorage",
    "OBJECT_METADATA_DIRECTORY_NAME",
    "OBJECTS_DIRECTORY_NAME",
    "ObjectId",
    "StorageBackend",
    "StoredObject",
    "TEMPORARY_UPLOADS_DIRECTORY_NAME",
    "TemporaryUploadId",
    "TemporaryUpload",
]
