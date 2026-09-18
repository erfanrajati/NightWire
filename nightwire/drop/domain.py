"""Drop domain types independent of HTTP routes and legacy dictionaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nightwire.core.security import PasswordDigest
from nightwire.core.storage import ObjectId
from nightwire.text import TextObject


@dataclass(frozen=True, slots=True)
class AccessKeyDigest:
    """Non-recoverable verifier for a Drop bearer Access Key."""

    algorithm: str
    salt: str
    digest: str

    def to_dict(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "salt": self.salt, "digest": self.digest}


@dataclass(frozen=True, slots=True)
class DropItem:
    """One logical ephemeral file shared through Drop."""

    name: str
    created_at: str | None
    expires_at: str | None
    content_kind: str = "file"
    access_key_digest: AccessKeyDigest | None = None
    password: PasswordDigest | None = None
    object_id: ObjectId | None = None
    checksum_sha256: str | None = None
    size: int | None = None
    security: dict[str, Any] | None = None
    text_object: TextObject | None = None

    @property
    def password_protected(self) -> bool:
        return self.password is not None

    @property
    def access_key_required(self) -> bool:
        return self.access_key_digest is not None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "content_kind": self.content_kind,
            "access_key_digest": self.access_key_digest.to_dict() if self.access_key_digest else None,
            "password": self.password.to_dict() if self.password else None,
        }
        if self.object_id is not None:
            record["object_id"] = str(self.object_id)
        if self.checksum_sha256 is not None:
            record["checksum_sha256"] = self.checksum_sha256
        if self.size is not None:
            record["size"] = self.size
        if self.security is not None:
            record["security"] = dict(self.security)
        if self.text_object is not None:
            record["text_object"] = self.text_object.to_record(include_content=False)
        return record


@dataclass(frozen=True, slots=True)
class DropUpload:
    item: DropItem
    access_key: str
    transfer_id: str
    bytes_written: int
    checksum_sha256: str
    seconds: float


@dataclass(frozen=True, slots=True)
class DropDownload:
    item: DropItem
    size: int
    legacy_path: str | None = None


__all__ = ["AccessKeyDigest", "DropDownload", "DropItem", "DropUpload", "PasswordDigest"]
