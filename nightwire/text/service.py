"""Validation and service contracts for first-class Community Text."""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from nightwire.text.domain import (
    TextLifecycle, TextMode, TextObject, TextProvenance, TextScopeKind,
)


class TextObjectRepository(Protocol):
    def create(self, item: TextObject) -> None: ...
    def get(self, scope_kind: TextScopeKind, scope_id: str, text_id: str) -> TextObject | None: ...
    def update(self, item: TextObject) -> None: ...
    def remove(self, scope_kind: TextScopeKind, scope_id: str, text_id: str) -> bool: ...


class TextValidationError(ValueError):
    pass


class TextObjectService:
    """Creates and updates the common logical model over any persistence adapter."""

    maximum_title_characters = 255
    maximum_content_characters = 1_048_576
    maximum_language_characters = 64

    def __init__(self, repository: TextObjectRepository | None = None) -> None:
        self.repository = repository

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def normalize_title(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TextValidationError("A Text title is required.")
        title = " ".join(value.replace("\x00", "").split())
        if not title:
            raise TextValidationError("A Text title is required.")
        if len(title) > cls.maximum_title_characters:
            raise TextValidationError(
                f"A Text title cannot exceed {cls.maximum_title_characters} characters."
            )
        return title

    @classmethod
    def normalize_content(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TextValidationError("Text content is required.")
        content = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
        if len(content) > cls.maximum_content_characters:
            raise TextValidationError(
                f"Text content cannot exceed {cls.maximum_content_characters:,} characters."
            )
        return content

    @staticmethod
    def normalize_mode(value: object) -> TextMode:
        try:
            return TextMode(str(value or TextMode.PLAIN.value))
        except ValueError as exc:
            raise TextValidationError("Text mode must be plain, markdown, or code.") from exc

    @classmethod
    def normalize_language(cls, value: object, mode: TextMode) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise TextValidationError("Text language must be a string.")
        language = value.strip().lower()
        if len(language) > cls.maximum_language_characters or not re.fullmatch(
            r"[a-z0-9][a-z0-9_+.#-]*", language
        ):
            raise TextValidationError("Text language contains unsupported characters.")
        if mode is not TextMode.CODE:
            raise TextValidationError("A language may only be assigned to code Text.")
        return language

    @staticmethod
    def normalize_provenance(source_kind: object, source_id: object) -> TextProvenance | None:
        if source_kind in (None, "") and source_id in (None, ""):
            return None
        if not isinstance(source_kind, str) or not isinstance(source_id, str):
            raise TextValidationError("Text provenance requires both source_kind and source_id.")
        kind, identifier = source_kind.strip(), source_id.strip()
        if not kind or not identifier or len(kind) > 64 or len(identifier) > 255:
            raise TextValidationError("Text provenance is invalid.")
        return TextProvenance(kind, identifier)

    def build(
        self, *, title: object, content: object, mode: object = TextMode.PLAIN,
        language: object = None, scope_kind: TextScopeKind, scope_id: str,
        lifecycle: TextLifecycle, folder_id: str | None = None,
        expires_at: datetime | None = None, source_kind: object = None,
        source_id: object = None, text_id: str | None = None,
        now: datetime | None = None,
    ) -> TextObject:
        timestamp = now or self._now()
        normalized_mode = self.normalize_mode(mode)
        return TextObject(
            id=text_id or uuid.uuid4().hex,
            title=self.normalize_title(title),
            content=self.normalize_content(content),
            mode=normalized_mode,
            language=self.normalize_language(language, normalized_mode),
            scope_kind=scope_kind,
            scope_id=scope_id,
            lifecycle=lifecycle,
            created_at=timestamp,
            updated_at=timestamp,
            folder_id=folder_id,
            expires_at=expires_at,
            provenance=self.normalize_provenance(source_kind, source_id),
        )

    def create(self, **values) -> TextObject:
        if self.repository is None:
            raise RuntimeError("Text persistence is not configured.")
        item = self.build(**values)
        self.repository.create(item)
        return item

    def revise(
        self, item: TextObject, *, title: object | None = None,
        content: object | None = None, mode: object | None = None,
        language: object = None, folder_id: str | None = None,
        preserve_language: bool = False,
    ) -> TextObject:
        revised_mode = item.mode if mode is None else self.normalize_mode(mode)
        revised_language = item.language if preserve_language else self.normalize_language(
            language, revised_mode
        )
        return replace(
            item,
            title=item.title if title is None else self.normalize_title(title),
            content=item.content if content is None else self.normalize_content(content),
            mode=revised_mode,
            language=revised_language,
            folder_id=item.folder_id if folder_id is None else folder_id,
            updated_at=self._now(),
        )


__all__ = ["TextObjectRepository", "TextObjectService", "TextValidationError"]
