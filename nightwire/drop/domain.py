"""Drop domain types independent of HTTP routes and legacy dictionaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nightwire.core.security import PasswordDigest
from nightwire.core.storage import ObjectId


@dataclass(frozen=True, slots=True)
class DropItem:
    """One logical ephemeral file shared through Drop."""

    name: str
    created_at: str | None
    expires_at: str | None
    password: PasswordDigest | None = None
    object_id: ObjectId | None = None
    checksum_sha256: str | None = None
    size: int | None = None
    security: dict[str, Any] | None = None

    @property
    def password_protected(self) -> bool:
        return self.password is not None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "created_at": self.created_at,
            "expires_at": self.expires_at,
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
        return record


@dataclass(frozen=True, slots=True)
class DropUpload:
    item: DropItem
    transfer_id: str
    bytes_written: int
    checksum_sha256: str
    seconds: float


@dataclass(frozen=True, slots=True)
class DropDownload:
    item: DropItem
    size: int
    legacy_path: str | None = None


__all__ = ["DropDownload", "DropItem", "DropUpload", "PasswordDigest"]
