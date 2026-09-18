"""Identity and personal-storage domain objects for the Community Library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from nightwire.drop import AccessKeyDigest
from nightwire.text import TextObject


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"


class LibraryScopeKind(StrEnum):
    PERSONAL = "personal"
    WORKSPACE = "workspace"


@dataclass(frozen=True, slots=True)
class LibraryScope:
    kind: LibraryScopeKind
    id: str
    actor_id: str

    @classmethod
    def personal(cls, user_id: str) -> LibraryScope:
        return cls(LibraryScopeKind.PERSONAL, user_id, user_id)

    @classmethod
    def workspace(cls, workspace_id: str, actor_id: str) -> LibraryScope:
        return cls(LibraryScopeKind.WORKSPACE, workspace_id, actor_id)

    @property
    def workspace_id(self) -> str | None:
        return self.id if self.kind is LibraryScopeKind.WORKSPACE else None


@dataclass(frozen=True, slots=True)
class Folder:
    id: str
    owner_id: str
    parent_id: str | None
    name: str
    is_root: bool
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    workspace_id: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": "folder",
            "parent_id": self.parent_id,
            "name": self.name,
            "is_root": self.is_root,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def trash_dict(self) -> dict[str, object]:
        return self.public_dict() | {
            "trashed_at": self.trashed_at.isoformat() if self.trashed_at else None
        }


@dataclass(frozen=True, slots=True)
class LibraryFile:
    id: str
    owner_id: str
    folder_id: str
    object_id: str
    name: str
    size: int
    checksum_sha256: str
    content_type: str
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    workspace_id: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": "file",
            "folder_id": self.folder_id,
            "name": self.name,
            "size": self.size,
            "content_type": self.content_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def trash_dict(self) -> dict[str, object]:
        return self.public_dict() | {
            "trashed_at": self.trashed_at.isoformat() if self.trashed_at else None
        }


@dataclass(frozen=True, slots=True)
class FileVersion:
    id: str
    file_id: str
    version_number: int
    object_id: str
    size: int
    checksum_sha256: str
    content_type: str
    created_at: datetime
    created_by_user_id: str
    source_kind: str = "upload"
    source_id: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "file_id": self.file_id,
            "version": self.version_number,
            "size": self.size,
            "checksum_sha256": self.checksum_sha256,
            "content_type": self.content_type,
            "created_at": self.created_at.isoformat(),
            "created_by_user_id": self.created_by_user_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class DerivedObject:
    id: str
    file_id: str
    source_version_id: str
    operation: str
    created_at: datetime
    created_by_user_id: str
    output_object_id: str
    size: int
    checksum_sha256: str
    content_type: str
    provenance: dict[str, Any]
    promoted_version_id: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "file_id": self.file_id,
            "source_version_id": self.source_version_id,
            "operation": self.operation,
            "created_at": self.created_at.isoformat(),
            "created_by_user_id": self.created_by_user_id,
            "size": self.size,
            "checksum_sha256": self.checksum_sha256,
            "content_type": self.content_type,
            "provenance": self.provenance,
            "promoted_version_id": self.promoted_version_id,
        }


@dataclass(frozen=True, slots=True)
class ShareGrant:
    id: str
    public_token: str
    file_id: str
    source_version_id: str
    source_name: str
    created_by_user_id: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    access_key_digest: AccessKeyDigest | None
    workspace_id: str | None = None

    @property
    def access_key_required(self) -> bool:
        return self.access_key_digest is not None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "file_id": self.file_id,
            "source_version_id": self.source_version_id,
            "name": self.source_name,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "access_key_required": self.access_key_required,
            "scope": {
                "kind": "workspace" if self.workspace_id else "personal",
                "id": self.workspace_id or self.created_by_user_id,
            },
        }


@dataclass(frozen=True, slots=True)
class TextShareGrant:
    id: str
    public_token: str
    text_id: str
    source_title: str
    created_by_user_id: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    access_key_digest: AccessKeyDigest | None
    workspace_id: str | None = None

    @property
    def access_key_required(self) -> bool:
        return self.access_key_digest is not None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "text_id": self.text_id,
            "item_type": "text",
            "name": self.source_title,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "access_key_required": self.access_key_required,
            "scope": {
                "kind": "workspace" if self.workspace_id else "personal",
                "id": self.workspace_id or self.created_by_user_id,
            },
        }


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    owner_user_id: str
    root_folder_id: str
    created_at: datetime
    updated_at: datetime

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "owner_user_id": self.owner_user_id,
            "root_folder_id": self.root_folder_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

@dataclass(frozen=True, slots=True)
class User:
    id: str
    email: str
    display_name: str
    password_hash: str
    status: UserStatus
    is_administrator: bool
    created_at: datetime
    approved_at: datetime | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "status": self.status.value,
            "is_administrator": self.is_administrator,
            "created_at": self.created_at.isoformat(),
        }


__all__ = [
    "DerivedObject", "FileVersion", "Folder", "LibraryFile", "LibraryScope", "LibraryScopeKind", "ShareGrant",
    "TextObject", "TextShareGrant", "User", "UserStatus", "Workspace",
]
