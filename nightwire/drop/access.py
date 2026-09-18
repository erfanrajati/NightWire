"""Generation and verification of bearer Access Keys for Drop shares."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from nightwire.drop.domain import AccessKeyDigest


_ACCESS_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_DOMAIN_SEPARATOR = b"nightwire-drop-access-key-v1\x00"


class DropAccessKeyPolicy:
    """Create high-entropy URL-safe keys while persisting only salted digests."""

    algorithm = "sha256-v1"

    def issue(self) -> tuple[str, AccessKeyDigest]:
        raw_key = secrets.token_urlsafe(32)
        salt = secrets.token_bytes(16)
        digest = self._digest(raw_key, salt)
        return raw_key, AccessKeyDigest(
            algorithm=self.algorithm,
            salt=base64.b64encode(salt).decode("ascii"),
            digest=base64.b64encode(digest).decode("ascii"),
        )

    @staticmethod
    def _digest(raw_key: str, salt: bytes) -> bytes:
        return hashlib.sha256(_DOMAIN_SEPARATOR + salt + raw_key.encode("ascii")).digest()

    def verify(self, supplied: object, record: AccessKeyDigest | None) -> bool:
        if record is None or not isinstance(supplied, str) or not _ACCESS_KEY_PATTERN.fullmatch(supplied):
            return False
        if record.algorithm != self.algorithm:
            return False
        try:
            salt = base64.b64decode(record.salt, validate=True)
            expected = base64.b64decode(record.digest, validate=True)
        except (ValueError, TypeError):
            return False
        if len(salt) != 16 or len(expected) != 32:
            return False
        return hmac.compare_digest(self._digest(supplied, salt), expected)

    def require(self, supplied: object, record: AccessKeyDigest | None) -> None:
        if record is not None and not self.verify(supplied, record):
            raise PermissionError("The Drop Access Key is missing or invalid.")


__all__ = ["DropAccessKeyPolicy"]
