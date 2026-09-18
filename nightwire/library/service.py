"""Ownership-enforcing personal Library operations over opaque Core objects."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from nightwire.core.capacity import UsageScope
from nightwire.core.references import ObjectReferenceChecker
from nightwire.core.storage import ObjectId, StorageBackend
from nightwire.core.transfer import TransferService
from nightwire.library.domain import DerivedObject, FileVersion, Folder, LibraryFile, LibraryScope, User
from nightwire.library.repository import LibraryRepository


class LibraryOperationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class DuplicateWarningError(LibraryOperationError):
    def __init__(self, warnings: list[dict[str, object]]) -> None:
        super().__init__("Possible duplicates require explicit confirmation.", 409)
        self.warnings = warnings


class PersonalLibraryService:
    """Manipulate a personal or authorized workspace tree through one implementation."""

    def __init__(
        self, repository: LibraryRepository, transfer: TransferService, storage: StorageBackend,
        *, version_retention: int = 100, references: ObjectReferenceChecker | None = None,
    ):
        if version_retention < 1:
            raise ValueError("Version retention must be positive.")
        self.repository = repository
        self.transfer = transfer
        self.storage = storage
        self.version_retention = version_retention
        self.references = references or ObjectReferenceChecker([repository.object_is_referenced])

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _scope(principal: User | LibraryScope) -> LibraryScope:
        return principal if isinstance(principal, LibraryScope) else LibraryScope.personal(principal.id)

    @staticmethod
    def _name(value: object) -> str:
        if not isinstance(value, str):
            raise LibraryOperationError("A name is required.")
        name = value.replace("\x00", "").strip()
        if not name or name in {".", ".."}:
            raise LibraryOperationError("A valid name is required.")
        if "/" in name or "\\" in name:
            raise LibraryOperationError("Names cannot contain path separators.")
        if len(name) > 255:
            raise LibraryOperationError("Names cannot exceed 255 characters.")
        if any(ord(character) < 32 for character in name):
            raise LibraryOperationError("Names cannot contain control characters.")
        return name

    def root(self, user: User | LibraryScope) -> Folder:
        scope = self._scope(user)
        existing = self.repository.root_folder(scope)
        if existing is not None:
            return existing
        now = self._now()
        name = "Workspace" if scope.workspace_id else "My Library"
        root = Folder(uuid.uuid4().hex, scope.actor_id, None, name, True, now, now,
                      workspace_id=scope.workspace_id)
        try:
            self.repository.create_folder(root)
        except Exception:
            concurrent = self.repository.root_folder(scope)
            if concurrent is None:
                raise
            return concurrent
        return root

    def _folder(self, user: User | LibraryScope, folder_id: object | None) -> Folder:
        scope = self._scope(user)
        resolved_id = self.root(user).id if folder_id in {None, ""} else str(folder_id)
        folder = self.repository.folder(scope, resolved_id)
        if folder is None:
            raise LibraryOperationError("Folder not found.", 404)
        return folder

    def _file(self, user: User | LibraryScope, file_id: object) -> LibraryFile:
        item = self.repository.file(self._scope(user), str(file_id))
        if item is None:
            raise LibraryOperationError("File not found.", 404)
        return item

    def _available(self, scope: LibraryScope, parent_id: str, requested: str, *, except_id: str | None = None) -> str:
        if not self.repository.name_exists(scope, parent_id, requested, except_id=except_id):
            return requested
        stem, dot, extension = requested.rpartition(".")
        base = stem if dot and stem else requested
        suffix = f".{extension}" if dot and stem else ""
        for number in range(1, 10_001):
            label = " copy" if number == 1 else f" copy {number}"
            candidate = f"{base}{label}{suffix}"
            if not self.repository.name_exists(scope, parent_id, candidate):
                return candidate
        raise LibraryOperationError("No available copy name could be created.", 409)

    def _assert_name_available(self, scope: LibraryScope, parent_id: str, name: str, *, except_id: str | None = None) -> None:
        if self.repository.name_exists(scope, parent_id, name, except_id=except_id):
            raise LibraryOperationError("An item with that name already exists in this folder.", 409)

    @staticmethod
    def _candidate_dict(item: LibraryFile, folder_path: str) -> dict[str, object]:
        return {
            "id": item.id, "name": item.name,
            "path": "/" + "/".join(part for part in (folder_path, item.name) if part),
            "size": item.size, "content_type": item.content_type,
            "updated_at": item.updated_at.isoformat(),
        }

    def _duplicate_warnings(
        self, scope: LibraryScope, name: str, checksum_sha256: str,
    ) -> list[dict[str, object]]:
        scoped = self.repository.scoped_files(scope)
        name_matches = [
            self._candidate_dict(item, path)
            for item, path in scoped if item.name.casefold() == name.casefold()
        ]
        checksum_matches = [
            self._candidate_dict(item, path)
            for item, path in scoped if item.checksum_sha256 == checksum_sha256
        ]
        warnings: list[dict[str, object]] = []
        if checksum_matches:
            warnings.append({"kind": "checksum_match", "candidates": checksum_matches})
        if name_matches:
            warnings.append({"kind": "same_name", "candidates": name_matches})
        return warnings

    @staticmethod
    def _fuzzy_score(query: str, name: str) -> float:
        needle, candidate = query.casefold(), name.casefold()
        if candidate == needle:
            return 1.0
        if candidate.startswith(needle):
            return 0.94 - min((len(candidate) - len(needle)) / 1000, 0.08)
        if needle in candidate:
            return 0.88 - min(candidate.index(needle) / 100, 0.12)
        ratio = SequenceMatcher(None, needle, candidate).ratio()
        words = re.findall(r"[a-z0-9]+", candidate)
        token_ratio = max((SequenceMatcher(None, needle, word).ratio() for word in words), default=0)
        positions = iter(candidate)
        subsequence = all(character in positions for character in needle)
        return max(ratio, token_ratio * 0.92, 0.55 if subsequence else 0.0)

    def search(
        self, user: User | LibraryScope, query: object, *, scope_name: str, scope_label: str,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        scope = self._scope(user)
        if not isinstance(query, str):
            raise LibraryOperationError("A search query is required.")
        clean = " ".join(query.replace("\x00", "").split())[:100]
        if not clean:
            return []
        ranked: list[tuple[float, object, str]] = []
        for item, path in self.repository.scoped_files(scope):
            score = self._fuzzy_score(clean, item.name)
            if score >= 0.38:
                ranked.append((score, item, path))
        for item, path in self.repository.scoped_texts(scope):
            score = self._fuzzy_score(clean, item.title)
            if score >= 0.38:
                ranked.append((score, item, path))
        ranked.sort(key=lambda value: (-value[0], value[1].name.casefold(), value[2].casefold()))
        return [
            item.public_dict() | {
                "path": "/" + "/".join(part for part in (path, item.name) if part),
                "folder_path": "/" + path if path else "/",
                "score": round(score, 4),
                "scope": {"kind": scope.kind.value, "id": scope.id,
                          "name": scope_label, "filter": scope_name},
            }
            for score, item, path in ranked[:limit]
        ]

    def create_folder(self, user: User | LibraryScope, parent_id: object | None, name: object) -> Folder:
        scope = self._scope(user)
        parent = self._folder(user, parent_id)
        clean = self._name(name)
        self._assert_name_available(scope, parent.id, clean)
        now = self._now()
        folder = Folder(uuid.uuid4().hex, scope.actor_id, parent.id, clean, False, now, now,
                        workspace_id=scope.workspace_id)
        self.repository.create_folder(folder)
        return folder

    def create_path(self, user: User | LibraryScope, parent_id: object | None, path: object) -> Folder:
        scope = self._scope(user)
        if not isinstance(path, str):
            raise LibraryOperationError("A folder path is required.")
        segments = [self._name(segment) for segment in re.split(r"[/\\]", path) if segment.strip()]
        if not segments:
            raise LibraryOperationError("A folder path is required.")
        parent = self._folder(user, parent_id)
        for segment in segments:
            folders, files = self.repository.children(scope, parent.id)
            existing = next((item for item in folders if item.name.casefold() == segment.casefold()), None)
            if existing:
                parent = existing
                continue
            if any(item.name.casefold() == segment.casefold() for item in files):
                raise LibraryOperationError("A file blocks part of that folder path.", 409)
            parent = self.create_folder(user, parent.id, segment)
        return parent

    def list_folder(self, user: User | LibraryScope, folder_id: object | None) -> dict[str, object]:
        scope = self._scope(user)
        folder = self._folder(user, folder_id)
        folders, files = self.repository.children(scope, folder.id)
        texts = self.repository.texts_in_folder(scope, folder.id)
        breadcrumbs: list[Folder] = []
        cursor: Folder | None = folder
        visited: set[str] = set()
        while cursor is not None:
            if cursor.id in visited:
                raise LibraryOperationError("The folder tree is invalid.", 409)
            visited.add(cursor.id)
            breadcrumbs.append(cursor)
            cursor = self.repository.folder(scope, cursor.parent_id) if cursor.parent_id else None
        breadcrumbs.reverse()
        return {
            "folder": folder.public_dict(),
            "breadcrumbs": [item.public_dict() for item in breadcrumbs],
            "folders": [item.public_dict() for item in folders],
            "files": [item.public_dict() for item in files],
            "texts": [item.public_dict(include_content=False) for item in texts],
        }

    def tree(self, user: User | LibraryScope) -> dict[str, object]:
        scope = self._scope(user)
        def descend(folder: Folder) -> dict[str, object]:
            folders, files = self.repository.children(scope, folder.id)
            texts = self.repository.texts_in_folder(scope, folder.id)
            return {
                **folder.public_dict(),
                "folders": [descend(child) for child in folders],
                "files": [item.public_dict() for item in files],
                "texts": [item.public_dict(include_content=False) for item in texts],
            }

        return descend(self.root(user))

    def get_file(self, user: User | LibraryScope, file_id: object) -> LibraryFile:
        return self._file(user, file_id)

    def file_details(self, user: User | LibraryScope, file_id: object) -> dict[str, object]:
        scope = self._scope(user)
        item = self._file(user, file_id)
        return {
            "file": item.public_dict(),
            "versions": [version.public_dict() for version in self.repository.versions(scope, item.id)],
            "derived_outputs": [output.public_dict() for output in self.repository.derived_objects(scope, item.id)],
            "version_retention": self.version_retention,
        }

    def get_version(self, user: User | LibraryScope, file_id: object, version_id: object) -> FileVersion:
        item = self._file(user, file_id)
        version = self.repository.version(self._scope(user), item.id, str(version_id))
        if version is None:
            raise LibraryOperationError("File version not found.", 404)
        return version

    def _reclaim_candidates(self, object_ids: list[str]) -> None:
        for value in set(object_ids):
            object_id = ObjectId.parse(value)
            if not self.references.is_referenced(object_id):
                self.storage.delete_object(object_id)

    def _append_version(
        self, user: User | LibraryScope, item: LibraryFile, *, object_id: str, size: int,
        checksum_sha256: str, content_type: str, source_kind: str, source_id: str | None,
    ) -> FileVersion:
        scope = self._scope(user)
        history = self.repository.versions(scope, item.id)
        version = FileVersion(
            id=uuid.uuid4().hex, file_id=item.id,
            version_number=(history[0].version_number + 1 if history else 1),
            object_id=object_id, size=size, checksum_sha256=checksum_sha256,
            content_type=content_type, created_at=self._now(),
            created_by_user_id=scope.actor_id, source_kind=source_kind, source_id=source_id,
        )
        self.repository.append_version(scope, version, version.created_at)
        removed = self.repository.prune_versions(item.id, self.version_retention)
        self._reclaim_candidates(removed)
        return version

    async def add_version(
        self, user: User | LibraryScope, file_id: object, content_type: object, chunks,
        expected_bytes: int | None = None,
    ) -> tuple[FileVersion, str]:
        scope = self._scope(user)
        item = self._file(user, file_id)
        pending = await self.transfer.receive_upload(
            chunks, usage_scope=UsageScope(scope.kind.value, scope.id), expected_bytes=expected_bytes
        )
        completed = self.transfer.finalize_upload(pending)
        try:
            version = self._append_version(
                user, item, object_id=str(completed.object_id), size=completed.bytes_written,
                checksum_sha256=completed.checksum_sha256,
                content_type=str(content_type or item.content_type)[:255],
                source_kind="upload", source_id=None,
            )
        except BaseException:
            if not self.references.is_referenced(completed.object_id):
                self.storage.delete_object(completed.object_id)
            if hasattr(self.transfer, "complete_upload"):
                self.transfer.complete_upload(pending)
            raise
        if hasattr(self.transfer, "complete_upload"):
            self.transfer.complete_upload(pending)
        return version, completed.transfer_id

    def restore_version(self, user: User | LibraryScope, file_id: object, version_id: object) -> FileVersion:
        item = self._file(user, file_id)
        source = self.get_version(user, item.id, version_id)
        return self._append_version(
            user, item, object_id=source.object_id, size=source.size,
            checksum_sha256=source.checksum_sha256, content_type=source.content_type,
            source_kind="restore", source_id=source.id,
        )

    def attach_derived_output(
        self, user: User | LibraryScope, file_id: object, *, source_version_id: object,
        operation: object, output_object_id: ObjectId | str, size: int,
        checksum_sha256: object, content_type: object,
        provenance: dict[str, Any] | None = None,
    ) -> DerivedObject:
        scope = self._scope(user)
        item = self._file(user, file_id)
        source = self.get_version(user, item.id, source_version_id)
        operation_name = str(operation).strip()
        if not operation_name or len(operation_name) > 255:
            raise LibraryOperationError("A valid operation is required.")
        try:
            object_id = ObjectId.parse(str(output_object_id))
        except (TypeError, ValueError) as exc:
            raise LibraryOperationError("A valid derived output object reference is required.") from exc
        try:
            actual_size = self.storage.object_size(object_id)
        except FileNotFoundError as exc:
            raise LibraryOperationError("Derived output content not found.", 404) from exc
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or actual_size != size:
            raise LibraryOperationError("Derived output size does not match stored content.")
        checksum = str(checksum_sha256).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise LibraryOperationError("A valid SHA-256 checksum is required.")
        if provenance is not None and not isinstance(provenance, dict):
            raise LibraryOperationError("Provenance must be a JSON object.")
        try:
            json.dumps(provenance or {})
        except (TypeError, ValueError) as exc:
            raise LibraryOperationError("Provenance must be JSON-serializable.") from exc
        output = DerivedObject(
            id=uuid.uuid4().hex, file_id=item.id, source_version_id=source.id,
            operation=operation_name, created_at=self._now(), created_by_user_id=scope.actor_id,
            output_object_id=str(object_id), size=size, checksum_sha256=checksum,
            content_type=str(content_type or "application/octet-stream")[:255],
            provenance=provenance or {},
        )
        try:
            self.repository.create_derived_object(scope, output)
        except ValueError as exc:
            raise LibraryOperationError(str(exc), 404) from exc
        return output

    async def upload_derived_output(
        self, user: User | LibraryScope, file_id: object, *, source_version_id: object,
        operation: object, content_type: object, provenance: dict[str, Any] | None,
        chunks, expected_bytes: int | None = None,
    ) -> tuple[DerivedObject, str]:
        scope = self._scope(user)
        self._file(user, file_id)
        pending = await self.transfer.receive_upload(
            chunks, usage_scope=UsageScope(scope.kind.value, scope.id), expected_bytes=expected_bytes
        )
        completed = self.transfer.finalize_upload(pending)
        try:
            output = self.attach_derived_output(
                user, file_id, source_version_id=source_version_id, operation=operation,
                output_object_id=completed.object_id, size=completed.bytes_written,
                checksum_sha256=completed.checksum_sha256, content_type=content_type,
                provenance=provenance,
            )
        except BaseException:
            if not self.references.is_referenced(completed.object_id):
                self.storage.delete_object(completed.object_id)
            if hasattr(self.transfer, "complete_upload"):
                self.transfer.complete_upload(pending)
            raise
        if hasattr(self.transfer, "complete_upload"):
            self.transfer.complete_upload(pending)
        return output, completed.transfer_id

    def promote_derived_output(
        self, user: User | LibraryScope, file_id: object, derived_id: object,
    ) -> FileVersion:
        scope = self._scope(user)
        item = self._file(user, file_id)
        output = self.repository.derived_object(scope, item.id, str(derived_id))
        if output is None:
            raise LibraryOperationError("Derived output not found.", 404)
        if output.promoted_version_id:
            existing = self.repository.version(scope, item.id, output.promoted_version_id)
            if existing is not None:
                return existing
        version = self._append_version(
            user, item, object_id=output.output_object_id, size=output.size,
            checksum_sha256=output.checksum_sha256, content_type=output.content_type,
            source_kind="derived", source_id=output.id,
        )
        self.repository.mark_derived_promoted(output.id, version.id)
        return version

    async def upload(self, user: User | LibraryScope, folder_id: object | None, name: object, content_type: object, chunks,
                     expected_bytes: int | None = None, *, confirm_duplicates: bool = False) -> tuple[LibraryFile, str]:
        scope = self._scope(user)
        folder = self._folder(user, folder_id)
        clean = self._name(name)
        media_type = str(content_type or "application/octet-stream")[:255]
        pending = await self.transfer.receive_upload(
            chunks, usage_scope=UsageScope(scope.kind.value, scope.id), expected_bytes=expected_bytes
        )
        completed = self.transfer.finalize_upload(pending)
        try:
            warnings = self._duplicate_warnings(scope, clean, completed.checksum_sha256)
            if warnings and not confirm_duplicates:
                raise DuplicateWarningError(warnings)
            if any(
                item.name.casefold() == clean.casefold() and item.folder_id == folder.id
                for item, _ in self.repository.scoped_files(scope)
            ):
                clean = self._available(scope, folder.id, clean)
            self._assert_name_available(scope, folder.id, clean)
            now = self._now()
            item = LibraryFile(
                uuid.uuid4().hex, scope.actor_id, folder.id, str(completed.object_id), clean,
                completed.bytes_written, completed.checksum_sha256, media_type, now, now,
                workspace_id=scope.workspace_id,
            )
            self.repository.create_file(item)
        except BaseException:
            if not self.references.is_referenced(completed.object_id):
                self.storage.delete_object(completed.object_id)
            if hasattr(self.transfer, "complete_upload"):
                self.transfer.complete_upload(pending)
            raise
        if hasattr(self.transfer, "complete_upload"):
            self.transfer.complete_upload(pending)
        return item, completed.transfer_id

    def rename_move_folder(self, user: User | LibraryScope, folder_id: object, *, name: object | None = None, parent_id: object | None = None) -> Folder:
        scope = self._scope(user)
        folder = self._folder(user, folder_id)
        if folder.is_root:
            raise LibraryOperationError("The private root folder cannot be changed.", 409)
        destination = self._folder(user, folder.parent_id if parent_id is None else parent_id)
        cursor: Folder | None = destination
        while cursor is not None:
            if cursor.id == folder.id:
                raise LibraryOperationError("A folder cannot be moved into itself or one of its descendants.", 409)
            cursor = self.repository.folder(scope, cursor.parent_id) if cursor.parent_id else None
        clean = folder.name if name is None else self._name(name)
        self._assert_name_available(scope, destination.id, clean, except_id=folder.id)
        self.repository.update_folder(scope, folder.id, clean, destination.id, self._now())
        return self._folder(user, folder.id)

    def rename_move_file(self, user: User | LibraryScope, file_id: object, *, name: object | None = None, parent_id: object | None = None) -> LibraryFile:
        scope = self._scope(user)
        item = self._file(user, file_id)
        destination = self._folder(user, item.folder_id if parent_id is None else parent_id)
        clean = item.name if name is None else self._name(name)
        self._assert_name_available(scope, destination.id, clean, except_id=item.id)
        self.repository.update_file(scope, item.id, clean, destination.id, self._now())
        return self._file(user, item.id)

    async def _duplicate_file(self, user: User | LibraryScope, source: LibraryFile, parent: Folder, name: str, physical: bool) -> LibraryFile:
        scope = self._scope(user)
        object_id = source.object_id
        transfer_id = ""
        logical_reservation = None
        capacity = getattr(self.transfer, "capacity", None)
        if not physical and capacity:
            logical_reservation = capacity.reserve(
                UsageScope(scope.kind.value, scope.id), source.size, physical=False
            )
        if physical:
            download = self.transfer.prepare_download(ObjectId.parse(source.object_id))
            pending = await self.transfer.receive_upload(
                download.chunks, usage_scope=UsageScope(scope.kind.value, scope.id),
                expected_bytes=source.size,
            )
            completed = self.transfer.finalize_upload(pending)
            object_id = str(completed.object_id)
            transfer_id = completed.transfer_id
        now = self._now()
        copy = LibraryFile(uuid.uuid4().hex, scope.actor_id, parent.id, object_id, name, source.size,
                           source.checksum_sha256, source.content_type, now, now,
                           workspace_id=scope.workspace_id)
        try:
            self.repository.create_file(copy)
        except BaseException:
            if physical:
                self.storage.delete_object(ObjectId.parse(object_id))
            if capacity:
                capacity.release(logical_reservation)
            raise
        if physical and hasattr(self.transfer, "complete_upload"):
            self.transfer.complete_upload(pending)
        if capacity:
            capacity.release(logical_reservation)
        return copy

    async def copy_file(self, user: User | LibraryScope, file_id: object, parent_id: object | None, name: object | None, *, physical: bool) -> LibraryFile:
        scope = self._scope(user)
        source = self._file(user, file_id)
        parent = self._folder(user, source.folder_id if parent_id is None else parent_id)
        clean = self._name(name) if name is not None else self._available(scope, parent.id, source.name)
        self._assert_name_available(scope, parent.id, clean)
        return await self._duplicate_file(user, source, parent, clean, physical)

    async def copy_folder(self, user: User | LibraryScope, folder_id: object, parent_id: object | None, name: object | None, *, physical: bool) -> Folder:
        scope = self._scope(user)
        source = self._folder(user, folder_id)
        if source.is_root:
            raise LibraryOperationError("The private root folder cannot be copied.", 409)
        parent = self._folder(user, source.parent_id if parent_id is None else parent_id)
        cursor: Folder | None = parent
        while cursor is not None:
            if cursor.id == source.id:
                raise LibraryOperationError("A folder cannot be copied into itself or one of its descendants.", 409)
            cursor = self.repository.folder(scope, cursor.parent_id) if cursor.parent_id else None
        clean = self._name(name) if name is not None else self._available(scope, parent.id, source.name)
        self._assert_name_available(scope, parent.id, clean)
        created = self.create_folder(user, parent.id, clean)

        async def recurse(original: Folder, target: Folder) -> None:
            folders, files = self.repository.children(scope, original.id)
            for item in files:
                await self._duplicate_file(user, item, target, item.name, physical)
            for child in folders:
                child_target = self.create_folder(user, target.id, child.name)
                await recurse(child, child_target)

        await recurse(source, created)
        return created

    def trash_file(self, user: User | LibraryScope, file_id: object) -> None:
        item = self._file(user, file_id)
        self.repository.trash_file(self._scope(user), item.id, self._now())

    def trash_folder(self, user: User | LibraryScope, folder_id: object) -> None:
        folder = self._folder(user, folder_id)
        if folder.is_root:
            raise LibraryOperationError("The private root folder cannot be moved to Trash.", 409)
        self.repository.trash_folder_tree(self._scope(user), folder.id, self._now())


__all__ = ["DuplicateWarningError", "LibraryOperationError", "PersonalLibraryService"]
