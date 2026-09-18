"""Configured password protection and HTTP creation-password middleware."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse

from nightwire.core.security import PasswordDigest


@dataclass(frozen=True, slots=True)
class PasswordProtection:
    maximum_characters: int

    def normalize_optional(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("Password must be text.")
        normalized = value.replace("\x00", "")
        if not normalized:
            raise ValueError("Password cannot be empty.")
        if len(normalized) > self.maximum_characters:
            raise ValueError(f"Password cannot exceed {self.maximum_characters} characters.")
        return normalized

    def decode_creation_header(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            password = base64.b64decode(value, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("The upload password header is invalid.") from exc
        return self.normalize_optional(password)

    def create(self, password: str) -> PasswordDigest:
        normalized = self.normalize_optional(password)
        if normalized is None:
            raise ValueError("A password is required.")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(normalized.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return PasswordDigest(
            salt=base64.b64encode(salt).decode("ascii"),
            digest=base64.b64encode(digest).decode("ascii"),
        )

    def verify(self, supplied: object, record: PasswordDigest | None) -> bool:
        if record is None or not isinstance(supplied, str):
            return False
        try:
            salt = base64.b64decode(record.salt, validate=True)
            expected = base64.b64decode(record.digest, validate=True)
        except (ValueError, TypeError):
            return False
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.scrypt(supplied.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)

    def require(self, supplied: object, record: PasswordDigest | None, message: str) -> None:
        if record is not None and not self.verify(supplied, record):
            raise PermissionError(message)

    async def middleware(self, request: Request, call_next):
        if request.method != "PUT" or request.url.path not in {"/api/upload", "/api/drops/files"}:
            return await call_next(request)
        try:
            request.state.drop_creation_password = self.decode_creation_header(
                request.headers.get("x-nightwire-password-b64")
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return await call_next(request)


__all__ = ["PasswordProtection"]
