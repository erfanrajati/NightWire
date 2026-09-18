"""Drop metadata repository contract and lightweight local JSON backend."""

from __future__ import annotations

import base64
import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

from nightwire.core.security import SecurityVerdict
from nightwire.core.storage import ObjectId
from nightwire.drop.domain import AccessKeyDigest, DropItem, PasswordDigest
from nightwire.text import TextObject


class DropRepository(ABC):
    @abstractmethod
    def load(self) -> None:
        """Load durable Drop metadata into the repository."""

    @abstractmethod
    def get(self, name: str) -> DropItem | None:
        """Return one logical Drop item."""

    @abstractmethod
    def list(self) -> tuple[DropItem, ...]:
        """Return all persisted Drop items."""

    @abstractmethod
    def put(self, item: DropItem) -> None:
        """Insert or replace one item in memory."""

    @abstractmethod
    def remove(self, name: str) -> None:
        """Remove one item from memory."""

    @abstractmethod
    def save(self) -> None:
        """Atomically persist current repository state."""


class LocalDropRepository(DropRepository):
    """Filename-keyed JSON metadata retained for upgrade compatibility."""

    def __init__(
        self,
        metadata_path: Path | Callable[[], Path],
        *,
        records: MutableMapping[str, dict[str, Any]] | None = None,
        validate_name: Callable[[str], object] | None = None,
    ):
        self._metadata_path = metadata_path
        self.records = records if records is not None else {}
        self.validate_name = validate_name

    @property
    def path(self) -> Path:
        return self._metadata_path() if callable(self._metadata_path) else self._metadata_path

    @staticmethod
    def _password(value: object) -> PasswordDigest | None:
        if not isinstance(value, dict):
            return None
        salt = value.get("salt")
        digest = value.get("digest")
        if not isinstance(salt, str) or not isinstance(digest, str):
            return None
        try:
            base64.b64decode(salt, validate=True)
            base64.b64decode(digest, validate=True)
        except (ValueError, TypeError):
            return None
        return PasswordDigest(salt, digest)

    @staticmethod
    def _access_key_digest(value: object) -> AccessKeyDigest | None:
        if not isinstance(value, dict):
            return None
        algorithm = value.get("algorithm")
        salt = value.get("salt")
        digest = value.get("digest")
        if algorithm != "sha256-v1" or not isinstance(salt, str) or not isinstance(digest, str):
            return None
        try:
            decoded_salt = base64.b64decode(salt, validate=True)
            decoded_digest = base64.b64decode(digest, validate=True)
        except (ValueError, TypeError):
            return None
        if len(decoded_salt) != 16 or len(decoded_digest) != 32:
            return None
        return AccessKeyDigest(algorithm, salt, digest)

    @classmethod
    def _item(cls, name: str, raw: object) -> DropItem | None:
        if not isinstance(raw, dict):
            return None
        try:
            object_id = ObjectId.parse(raw["object_id"]) if raw.get("object_id") is not None else None
        except ValueError:
            object_id = None
        checksum = raw.get("checksum_sha256")
        checksum = checksum if isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum) else None
        size = raw.get("size")
        size = size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None
        security = raw.get("security")
        if not (
            isinstance(security, dict)
            and security.get("verdict") in {verdict.value for verdict in SecurityVerdict}
            and isinstance(security.get("detected_mime"), str)
        ):
            security = None
        content_kind = raw.get("content_kind", "file")
        if content_kind not in {"file", "text", "voice"}:
            content_kind = "file"
        return DropItem(
            name=name,
            created_at=raw.get("created_at") if isinstance(raw.get("created_at"), str) else None,
            expires_at=raw.get("expires_at") if isinstance(raw.get("expires_at"), str) else None,
            content_kind=content_kind,
            access_key_digest=cls._access_key_digest(raw.get("access_key_digest")),
            password=cls._password(raw.get("password")),
            object_id=object_id,
            checksum_sha256=checksum,
            size=size,
            security=dict(security) if security else None,
            text_object=TextObject.from_record(raw.get("text_object")),
        )

    def load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        cleaned = {}
        for name, raw in payload.items():
            if not isinstance(name, str):
                continue
            try:
                if self.validate_name is not None:
                    self.validate_name(name)
            except ValueError:
                continue
            item = self._item(name, raw)
            if item is not None:
                cleaned[name] = item.to_record()
        self.records.clear()
        self.records.update(cleaned)

    def get(self, name: str) -> DropItem | None:
        return self._item(name, self.records.get(name))

    def list(self) -> tuple[DropItem, ...]:
        return tuple(item for name in self.records if (item := self.get(name)) is not None)

    def put(self, item: DropItem) -> None:
        if self.validate_name is not None:
            self.validate_name(item.name)
        self.records[item.name] = item.to_record()

    def remove(self, name: str) -> None:
        self.records.pop(name, None)

    def save(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        payload = json.dumps(self.records, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            temporary.write_text(payload + "\n", encoding="utf-8")
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


__all__ = ["DropRepository", "LocalDropRepository"]
