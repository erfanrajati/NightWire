"""Scope-aware Trash lifecycle and reference-safe physical deletion."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from nightwire.core.references import ObjectReferenceChecker
from nightwire.core.storage import ObjectId, StorageBackend
from nightwire.library.domain import Folder, LibraryFile, LibraryScope, User
from nightwire.library.repository import LibraryRepository
from nightwire.library.service import LibraryOperationError, PersonalLibraryService


class TrashService:
    def __init__(
        self,
        repository: LibraryRepository,
        library: PersonalLibraryService,
        storage: StorageBackend,
        references: ObjectReferenceChecker,
        retention_seconds: int,
        *,
        cleanup_interval_seconds: int = 60,
    ) -> None:
        if retention_seconds < 1:
            raise ValueError("Trash retention must be positive.")
        self.repository = repository
        self.library = library
        self.storage = storage
        self.references = references
        self.retention_seconds = retention_seconds
        self.cleanup_interval_seconds = max(cleanup_interval_seconds, 1)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _scope(principal: User | LibraryScope) -> LibraryScope:
        return principal if isinstance(principal, LibraryScope) else LibraryScope.personal(principal.id)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def list(self, principal: User | LibraryScope) -> dict[str, object]:
        scope = self._scope(principal)
        folders, files = self.repository.trash_items(scope)
        return {
            "folders": [folder.trash_dict() for folder in folders],
            "files": [item.trash_dict() for item in files],
            "texts": [item.public_dict(include_content=False)
                      for item in self.repository.trashed_texts(scope)],
            "retention_seconds": self.retention_seconds,
        }

    def restore_file(self, principal: User | LibraryScope, file_id: object) -> LibraryFile:
        scope = self._scope(principal)
        item = self.repository.trashed_file(scope, str(file_id))
        if item is None:
            raise LibraryOperationError("Trashed file not found.", 404)
        parent = self.repository.folder(scope, item.folder_id) or self.library.root(scope)
        name = self.library._available(scope, parent.id, item.name)
        self.repository.restore_file(scope, item.id, parent.id, name, self._now())
        restored = self.repository.file(scope, item.id)
        if restored is None:
            raise LibraryOperationError("The file could not be restored.", 409)
        return restored

    def restore_folder(self, principal: User | LibraryScope, folder_id: object) -> Folder:
        scope = self._scope(principal)
        folder = self.repository.trashed_folder(scope, str(folder_id))
        if folder is None:
            raise LibraryOperationError("Trashed folder not found.", 404)
        parent = self.repository.folder(scope, folder.parent_id) if folder.parent_id else None
        parent = parent or self.library.root(scope)
        name = self.library._available(scope, parent.id, folder.name)
        self.repository.restore_folder_tree(scope, folder.id, parent.id, name, self._now())
        restored = self.repository.folder(scope, folder.id)
        if restored is None:
            raise LibraryOperationError("The folder could not be restored.", 409)
        return restored

    def restore_text(self, principal: User | LibraryScope, text_id: object):
        scope = self._scope(principal)
        item = self.repository.text(scope, str(text_id), trashed=True)
        if item is None:
            raise LibraryOperationError("Trashed Text not found.", 404)
        parent = self.repository.folder(scope, item.folder_id or "") or self.library.root(scope)
        title = self.library._available(scope, parent.id, item.title)
        self.repository.restore_text(scope, item.id, parent.id, title, self._now())
        restored = self.repository.text(scope, item.id)
        if restored is None:
            raise LibraryOperationError("The Text could not be restored.", 409)
        return restored

    def _delete_object_if_unreferenced(self, value: str) -> bool:
        object_id = ObjectId.parse(value)
        if self.references.is_referenced(object_id):
            return False
        self.storage.delete_object(object_id)
        return True

    def reclaim_unreferenced_object(self, object_id: ObjectId | str) -> bool:
        """Delete bytes after a version/derived reference has been removed."""
        return self._delete_object_if_unreferenced(str(object_id))

    def permanently_delete_file(self, principal: User | LibraryScope, file_id: object) -> bool:
        scope = self._scope(principal)
        object_ids = self.repository.permanently_delete_file(scope, str(file_id))
        if object_ids is None:
            raise LibraryOperationError("Trashed file not found.", 404)
        return bool(sum(self._delete_object_if_unreferenced(value) for value in set(object_ids)))

    def permanently_delete_folder(self, principal: User | LibraryScope, folder_id: object) -> int:
        scope = self._scope(principal)
        object_ids = self.repository.permanently_delete_folder_tree(scope, str(folder_id))
        if object_ids is None:
            raise LibraryOperationError("Trashed folder not found.", 404)
        return sum(self._delete_object_if_unreferenced(value) for value in set(object_ids))

    def permanently_delete_text(self, principal: User | LibraryScope, text_id: object) -> None:
        scope = self._scope(principal)
        if not self.repository.permanently_delete_text(scope, str(text_id)):
            raise LibraryOperationError("Trashed Text not found.", 404)

    def cleanup_expired(self, now: datetime | None = None) -> dict[str, int]:
        current = now or self._now()
        cutoff = current - timedelta(seconds=self.retention_seconds)
        scopes = {
            (scope.kind.value, scope.id): scope
            for scope in self.repository.expired_trash_scopes(cutoff)
        }
        purged_items = 0
        deleted_objects = 0
        for scope in scopes.values():
            folders, files = self.repository.trash_items(scope)
            for folder in folders:
                if folder.trashed_at and folder.trashed_at <= cutoff:
                    deleted_objects += self.permanently_delete_folder(scope, folder.id)
                    purged_items += 1
            for item in files:
                if item.trashed_at and item.trashed_at <= cutoff:
                    deleted_objects += int(self.permanently_delete_file(scope, item.id))
                    purged_items += 1
            for item in self.repository.trashed_texts(scope):
                if item.trashed_at and item.trashed_at <= cutoff:
                    self.permanently_delete_text(scope, item.id)
                    purged_items += 1
        return {"purged_items": purged_items, "deleted_objects": deleted_objects}

    def start_cleanup(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def run() -> None:
            while not self._stop.wait(self.cleanup_interval_seconds):
                try:
                    self.cleanup_expired()
                except Exception:
                    continue

        self.cleanup_expired()
        self._thread = threading.Thread(target=run, name="nightwire-library-trash", daemon=True)
        self._thread.start()

    def stop_cleanup(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None


__all__ = ["TrashService"]
