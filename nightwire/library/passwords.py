"""Password hashing for persistent Library accounts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


class PasswordHasher:
    algorithm = "scrypt"
    n = 2**14
    r = 8
    p = 1
    length = 32

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=self.n, r=self.r, p=self.p, dklen=self.length
        )
        return "$".join(
            (
                self.algorithm,
                str(self.n),
                str(self.r),
                str(self.p),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(digest).decode("ascii"),
            )
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_value, digest_value = encoded.split("$")
            if algorithm != self.algorithm:
                return False
            parameters = (int(n), int(r), int(p))
            if parameters != (self.n, self.r, self.p):
                return False
            salt = base64.urlsafe_b64decode(salt_value)
            expected = base64.urlsafe_b64decode(digest_value)
        except (ValueError, TypeError):
            return False
        if len(salt) != 16 or len(expected) != self.length:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=self.n, r=self.r, p=self.p, dklen=self.length
        )
        return hmac.compare_digest(actual, expected)


__all__ = ["PasswordHasher"]
