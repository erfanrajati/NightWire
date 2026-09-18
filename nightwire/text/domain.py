"""Shared Community Text domain objects, independent of Drop and Library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class TextMode(StrEnum):
    PLAIN = "plain"
    MARKDOWN = "markdown"
    CODE = "code"


class TextLifecycle(StrEnum):
    TEMPORARY = "temporary"
    PERSISTENT = "persistent"


class TextScopeKind(StrEnum):
    DROP = "drop"
    PERSONAL = "personal"
    WORKSPACE = "workspace"


@dataclass(frozen=True, slots=True)
class TextProvenance:
    source_kind: str
    source_id: str

    def to_dict(self) -> dict[str, str]:
        return {"source_kind": self.source_kind, "source_id": self.source_id}


@dataclass(frozen=True, slots=True)
class TextObject:
    """A logical Text object shared by temporary and persistent products."""

    id: str
    title: str
    content: str
    mode: TextMode
    language: str | None
    scope_kind: TextScopeKind
    scope_id: str
    lifecycle: TextLifecycle
    created_at: datetime
    updated_at: datetime
    folder_id: str | None = None
    expires_at: datetime | None = None
    trashed_at: datetime | None = None
    provenance: TextProvenance | None = None

    @property
    def name(self) -> str:
        """Folder/search compatibility without pretending Text is a file."""
        return self.title

    def public_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.id,
            "type": "text",
            "title": self.title,
            "name": self.title,
            "mode": self.mode.value,
            "language": self.language,
            "scope": {"kind": self.scope_kind.value, "id": self.scope_id},
            "lifecycle": self.lifecycle.value,
            "folder_id": self.folder_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "trashed_at": self.trashed_at.isoformat() if self.trashed_at else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }
        if include_content:
            record["content"] = self.content
        return record

    def to_record(self, *, include_content: bool = True) -> dict[str, Any]:
        return self.public_dict(include_content=include_content)

    @classmethod
    def from_record(cls, raw: object) -> TextObject | None:
        if not isinstance(raw, dict):
            return None
        try:
            provenance_raw = raw.get("provenance")
            provenance = None
            if isinstance(provenance_raw, dict):
                provenance = TextProvenance(
                    source_kind=str(provenance_raw["source_kind"]),
                    source_id=str(provenance_raw["source_id"]),
                )
            return cls(
                id=str(raw["id"]),
                title=str(raw["title"]),
                content=str(raw.get("content", "")),
                mode=TextMode(str(raw["mode"])),
                language=str(raw["language"]) if raw.get("language") else None,
                scope_kind=TextScopeKind(str(raw["scope"]["kind"])),
                scope_id=str(raw["scope"]["id"]),
                lifecycle=TextLifecycle(str(raw["lifecycle"])),
                created_at=datetime.fromisoformat(str(raw["created_at"])),
                updated_at=datetime.fromisoformat(str(raw["updated_at"])),
                folder_id=str(raw["folder_id"]) if raw.get("folder_id") else None,
                expires_at=(datetime.fromisoformat(str(raw["expires_at"]))
                            if raw.get("expires_at") else None),
                trashed_at=(datetime.fromisoformat(str(raw["trashed_at"]))
                            if raw.get("trashed_at") else None),
                provenance=provenance,
            )
        except (KeyError, TypeError, ValueError):
            return None


__all__ = [
    "TextLifecycle", "TextMode", "TextObject", "TextProvenance", "TextScopeKind",
]
