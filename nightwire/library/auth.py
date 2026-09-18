"""Library registration policy, authentication, and session services."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from nightwire.core.config import RegistrationPolicy
from nightwire.library.domain import User, UserStatus
from nightwire.library.passwords import PasswordHasher
from nightwire.library.repository import LibraryRepository


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthenticationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user: User
    session_token: str | None


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    session_token: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class LibraryAuthService:
    def __init__(
        self,
        repository: LibraryRepository,
        registration_policy: RegistrationPolicy,
        *,
        session_ttl_seconds: int,
        password_min_characters: int,
        password_max_characters: int = 256,
    ) -> None:
        self.repository = repository
        self.registration_policy = registration_policy
        self.session_ttl_seconds = session_ttl_seconds
        self.password_min_characters = password_min_characters
        self.password_max_characters = password_max_characters
        self.passwords = PasswordHasher()
        self._registration_lock = threading.RLock()
        self._dummy_password_hash = self.passwords.hash(secrets.token_urlsafe(24))

    @staticmethod
    def normalize_email(value: object) -> str:
        if not isinstance(value, str):
            raise AuthenticationError("A valid email address is required.")
        email = value.strip().casefold()
        if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
            raise AuthenticationError("A valid email address is required.")
        return email

    @staticmethod
    def normalize_display_name(value: object) -> str:
        if not isinstance(value, str):
            raise AuthenticationError("A display name is required.")
        display_name = " ".join(value.replace("\x00", "").split())
        if not 2 <= len(display_name) <= 80:
            raise AuthenticationError("Display name must be between 2 and 80 characters.")
        return display_name

    def normalize_password(self, value: object) -> str:
        if not isinstance(value, str):
            raise AuthenticationError("A password is required.")
        if len(value) < self.password_min_characters:
            raise AuthenticationError(
                f"Password must be at least {self.password_min_characters} characters."
            )
        if len(value) > self.password_max_characters:
            raise AuthenticationError(
                f"Password cannot exceed {self.password_max_characters} characters."
            )
        return value

    def register(
        self,
        *,
        email: object,
        display_name: object,
        password: object,
        invitation_token: object = None,
    ) -> RegistrationResult:
        normalized_email = self.normalize_email(email)
        normalized_name = self.normalize_display_name(display_name)
        normalized_password = self.normalize_password(password)
        now = _now()

        with self._registration_lock:
            if self.repository.find_user_by_email(normalized_email) is not None:
                raise AuthenticationError("An account with that email already exists.", 409)
            first_account = self.repository.user_count() == 0
            invitation = None
            if not first_account and self.registration_policy is RegistrationPolicy.INVITATION_ONLY:
                if not isinstance(invitation_token, str) or not invitation_token:
                    raise AuthenticationError("A valid invitation is required.", 403)
                invitation = self.repository.valid_invitation(
                    _token_hash(invitation_token), normalized_email, now
                )
                if invitation is None:
                    raise AuthenticationError("That invitation is invalid or has expired.", 403)

            active = (
                first_account
                or self.registration_policy is RegistrationPolicy.OPEN
                or self.registration_policy is RegistrationPolicy.INVITATION_ONLY
            )
            user = User(
                id=uuid.uuid4().hex,
                email=normalized_email,
                display_name=normalized_name,
                password_hash=self.passwords.hash(normalized_password),
                status=UserStatus.ACTIVE if active else UserStatus.PENDING,
                is_administrator=first_account,
                created_at=now,
                approved_at=now if active else None,
            )
            try:
                if invitation is None:
                    self.repository.create_user(user)
                else:
                    self.repository.create_invited_user(user, str(invitation["id"]), now)
            except ValueError as exc:
                raise AuthenticationError("That invitation has already been used.", 409) from exc
            except Exception as exc:
                if self.repository.find_user_by_email(normalized_email) is not None:
                    raise AuthenticationError("An account with that email already exists.", 409) from exc
                raise

        token = self._create_session(user, now) if active else None
        return RegistrationResult(user=user, session_token=token)

    def login(self, email: object, password: object) -> LoginResult:
        normalized_email = self.normalize_email(email)
        supplied = password if isinstance(password, str) else ""
        user = self.repository.find_user_by_email(normalized_email)
        encoded = user.password_hash if user else self._dummy_password_hash
        valid = self.passwords.verify(supplied, encoded)
        if not valid or user is None or user.status is not UserStatus.ACTIVE:
            raise AuthenticationError("Email, password, or account status is invalid.", 401)
        return LoginResult(user=user, session_token=self._create_session(user, _now()))

    def _create_session(self, user: User, now: datetime) -> str:
        token = secrets.token_urlsafe(32)
        self.repository.create_session(
            uuid.uuid4().hex,
            user.id,
            _token_hash(token),
            now,
            now + timedelta(seconds=self.session_ttl_seconds),
        )
        return token

    def current_user(self, session_token: str | None) -> User | None:
        if not session_token:
            return None
        try:
            token_hash = _token_hash(session_token)
        except UnicodeEncodeError:
            return None
        return self.repository.user_for_session(token_hash, _now())

    def logout(self, session_token: str | None) -> None:
        if session_token:
            try:
                self.repository.revoke_session(_token_hash(session_token), _now())
            except UnicodeEncodeError:
                pass

    @staticmethod
    def require_administrator(user: User | None) -> User:
        if user is None:
            raise AuthenticationError("Library authentication is required.", 401)
        if not user.is_administrator:
            raise AuthenticationError("Administrator access is required.", 403)
        return user

    def create_invitation(self, administrator: User | None, email: object) -> str:
        admin = self.require_administrator(administrator)
        normalized_email = self.normalize_email(email)
        if self.repository.find_user_by_email(normalized_email):
            raise AuthenticationError("An account with that email already exists.", 409)
        now = _now()
        token = secrets.token_urlsafe(32)
        self.repository.create_invitation(
            uuid.uuid4().hex,
            normalized_email,
            _token_hash(token),
            admin.id,
            now,
            now + timedelta(days=7),
        )
        return token

    def pending_users(self, administrator: User | None) -> list[User]:
        self.require_administrator(administrator)
        return self.repository.pending_users()

    def decide_pending_user(
        self, administrator: User | None, user_id: str, *, approve: bool
    ) -> User:
        self.require_administrator(administrator)
        status = UserStatus.ACTIVE if approve else UserStatus.REJECTED
        user = self.repository.set_user_status(user_id, status, _now())
        if user is None:
            raise AuthenticationError("Pending account was not found.", 404)
        if not approve:
            self.repository.revoke_user_sessions(user.id, _now())
        return user


__all__ = [
    "AuthenticationError",
    "LibraryAuthService",
    "LoginResult",
    "RegistrationResult",
]
