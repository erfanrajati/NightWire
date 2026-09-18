"""Library lifecycle adapter for the shared Community Text model."""

from __future__ import annotations

from datetime import datetime, timezone

from nightwire.library.domain import LibraryScope, User
from nightwire.library.repository import LibraryRepository
from nightwire.library.service import LibraryOperationError, PersonalLibraryService
from nightwire.text import (
    TextLifecycle, TextObject, TextObjectService, TextScopeKind, TextValidationError,
)


class LibraryTextService:
    def __init__(self, repository: LibraryRepository, library: PersonalLibraryService) -> None:
        self.repository = repository
        self.library = library
        self.text = TextObjectService()

    @staticmethod
    def _scope(principal: User | LibraryScope) -> LibraryScope:
        return principal if isinstance(principal, LibraryScope) else LibraryScope.personal(principal.id)

    @staticmethod
    def _scope_kind(scope: LibraryScope) -> TextScopeKind:
        return TextScopeKind.WORKSPACE if scope.workspace_id else TextScopeKind.PERSONAL

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _get(self, principal: User | LibraryScope, text_id: object, *, trashed: bool = False) -> TextObject:
        scope = self._scope(principal)
        item = self.repository.text(scope, str(text_id), trashed=trashed)
        if item is None:
            raise LibraryOperationError("Text not found.", 404)
        return item

    def get(self, principal: User | LibraryScope, text_id: object) -> TextObject:
        return self._get(principal, text_id)

    def create(
        self, principal: User | LibraryScope, *, folder_id: object | None,
        title: object, content: object, mode: object = "plain", language: object = None,
        source_kind: object = None, source_id: object = None,
    ) -> TextObject:
        scope = self._scope(principal)
        folder = self.library._folder(principal, folder_id)
        try:
            normalized_title = self.text.normalize_title(title)
            self.library._assert_name_available(scope, folder.id, normalized_title)
            item = self.text.build(
                title=normalized_title, content=content, mode=mode, language=language,
                scope_kind=self._scope_kind(scope), scope_id=scope.id,
                lifecycle=TextLifecycle.PERSISTENT, folder_id=folder.id,
                source_kind=source_kind, source_id=source_id,
            )
        except TextValidationError as exc:
            raise LibraryOperationError(str(exc)) from exc
        self.repository.create_text(item, scope.actor_id, scope.workspace_id)
        return item

    def update(
        self, principal: User | LibraryScope, text_id: object, *,
        title: object | None = None, content: object | None = None,
        mode: object | None = None, language: object = None,
        language_supplied: bool = False, parent_id: object | None = None,
    ) -> TextObject:
        scope = self._scope(principal)
        item = self._get(principal, text_id)
        folder = self.library._folder(
            principal, item.folder_id if parent_id is None else parent_id
        )
        try:
            normalized_title = item.title if title is None else self.text.normalize_title(title)
            self.library._assert_name_available(
                scope, folder.id, normalized_title, except_id=item.id
            )
            next_mode = item.mode if mode is None else self.text.normalize_mode(mode)
            if language_supplied:
                next_language = self.text.normalize_language(language, next_mode)
            elif mode is not None and next_mode.value != "code":
                next_language = None
            else:
                next_language = item.language
            revised = self.text.revise(
                item, title=normalized_title, content=content, mode=next_mode,
                language=next_language, folder_id=folder.id,
            )
        except TextValidationError as exc:
            raise LibraryOperationError(str(exc)) from exc
        self.repository.update_text(scope, revised)
        return self._get(principal, item.id)

    def trash(self, principal: User | LibraryScope, text_id: object) -> None:
        scope = self._scope(principal)
        item = self._get(principal, text_id)
        self.repository.trash_text(scope, item.id, self._now())

    def restore(self, principal: User | LibraryScope, text_id: object) -> TextObject:
        scope = self._scope(principal)
        item = self._get(principal, text_id, trashed=True)
        parent = self.repository.folder(scope, item.folder_id or "") or self.library.root(scope)
        title = self.library._available(scope, parent.id, item.title)
        self.repository.restore_text(scope, item.id, parent.id, title, self._now())
        return self._get(principal, item.id)

    def permanently_delete(self, principal: User | LibraryScope, text_id: object) -> None:
        scope = self._scope(principal)
        if not self.repository.permanently_delete_text(scope, str(text_id)):
            raise LibraryOperationError("Trashed Text not found.", 404)


__all__ = ["LibraryTextService"]
