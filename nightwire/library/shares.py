"""Read-only Library share grants over immutable Core objects."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from nightwire.core.security import CoreSecurityPolicy, SecurityAction, SecurityVerdict
from nightwire.core.storage import ObjectId, StorageBackend
from nightwire.drop import DropAccessKeyPolicy
from nightwire.library.domain import (
    FileVersion, LibraryFile, LibraryScope, ShareGrant, TextShareGrant, User,
)
from nightwire.library.repository import LibraryRepository
from nightwire.library.service import LibraryOperationError, PersonalLibraryService


class ShareAccessError(LibraryOperationError):
    pass


@dataclass(frozen=True, slots=True)
class CreatedShare:
    grant: ShareGrant | TextShareGrant
    access_key: str | None


@dataclass(frozen=True, slots=True)
class ResolvedShare:
    grant: ShareGrant | TextShareGrant
    file: LibraryFile | None
    version: FileVersion | None
    security: dict[str, object]
    text: object | None = None


class LibraryShareService:
    maximum_expiry_seconds = 365 * 24 * 60 * 60

    def __init__(
        self, repository: LibraryRepository, library: PersonalLibraryService,
        storage: StorageBackend,
    ) -> None:
        self.repository = repository
        self.library = library
        self.storage = storage
        self.access_keys = DropAccessKeyPolicy()
        self.security_policy = CoreSecurityPolicy()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _scope(principal: User | LibraryScope) -> LibraryScope:
        return principal if isinstance(principal, LibraryScope) else LibraryScope.personal(principal.id)

    def _expiry(self, value: object, now: datetime) -> datetime | None:
        if value is None or value == 0 or value == "0" or value == "":
            return None
        if isinstance(value, bool):
            raise LibraryOperationError("Share expiry must be a number of seconds.")
        try:
            seconds = int(value)
        except (TypeError, ValueError) as exc:
            raise LibraryOperationError("Share expiry must be a number of seconds.") from exc
        if seconds < 1 or seconds > self.maximum_expiry_seconds:
            raise LibraryOperationError("Share expiry must be between 1 second and 365 days, or zero for no expiry.")
        return now + timedelta(seconds=seconds)

    def create(
        self, principal: User | LibraryScope, file_id: object, *,
        expires_in_seconds: object = None, access_key_protected: object = False,
    ) -> CreatedShare:
        if not isinstance(access_key_protected, bool):
            raise LibraryOperationError("access_key_protected must be true or false.")
        scope = self._scope(principal)
        item = self.library.get_file(principal, file_id)
        versions = self.repository.versions(scope, item.id)
        if not versions:
            raise LibraryOperationError("The file has no shareable version.", 409)
        raw_key, digest = self.access_keys.issue() if access_key_protected else (None, None)
        now = self._now()
        grant = ShareGrant(
            id=uuid.uuid4().hex, public_token=secrets.token_urlsafe(24),
            file_id=item.id, source_version_id=versions[0].id, source_name=item.name,
            created_by_user_id=scope.actor_id, created_at=now,
            expires_at=self._expiry(expires_in_seconds, now), revoked_at=None,
            access_key_digest=digest, workspace_id=scope.workspace_id,
        )
        try:
            self.repository.create_share_grant(scope, grant)
        except ValueError as exc:
            raise LibraryOperationError(str(exc), 404) from exc
        return CreatedShare(grant, raw_key)

    def list_for_file(self, principal: User | LibraryScope, file_id: object) -> list[ShareGrant]:
        scope = self._scope(principal)
        item = self.library.get_file(principal, file_id)
        return self.repository.share_grants_for_file(scope, item.id, scope.actor_id)

    def list_created(self, user: User) -> list[ShareGrant]:
        grants = [
            *self.repository.share_grants_created_by(user.id),
            *self.repository.text_share_grants_created_by(user.id),
        ]
        return sorted(grants, key=lambda grant: grant.created_at, reverse=True)

    def create_text(
        self, principal: User | LibraryScope, text_id: object, *,
        expires_in_seconds: object = None, access_key_protected: object = False,
    ) -> CreatedShare:
        if not isinstance(access_key_protected, bool):
            raise LibraryOperationError("access_key_protected must be true or false.")
        scope = self._scope(principal)
        item = self.repository.text(scope, str(text_id))
        if item is None:
            raise LibraryOperationError("Text not found.", 404)
        raw_key, digest = self.access_keys.issue() if access_key_protected else (None, None)
        now = self._now()
        grant = TextShareGrant(
            id=uuid.uuid4().hex, public_token=secrets.token_urlsafe(24),
            text_id=item.id, source_title=item.title,
            created_by_user_id=scope.actor_id, created_at=now,
            expires_at=self._expiry(expires_in_seconds, now), revoked_at=None,
            access_key_digest=digest, workspace_id=scope.workspace_id,
        )
        try:
            self.repository.create_text_share_grant(scope, grant)
        except ValueError as exc:
            raise LibraryOperationError(str(exc), 404) from exc
        return CreatedShare(grant, raw_key)

    def list_for_text(
        self, principal: User | LibraryScope, text_id: object,
    ) -> list[TextShareGrant]:
        scope = self._scope(principal)
        if self.repository.text(scope, str(text_id)) is None:
            raise LibraryOperationError("Text not found.", 404)
        return self.repository.text_share_grants_for_text(scope, str(text_id), scope.actor_id)

    def revoke(self, user: User, grant_id: object) -> None:
        now = self._now()
        if not (
            self.repository.revoke_share_grant(user.id, str(grant_id), now)
            or self.repository.revoke_text_share_grant(user.id, str(grant_id), now)
        ):
            raise LibraryOperationError("Active share not found.", 404)

    def _security(self, object_id: str) -> dict[str, object]:
        metadata = self.storage.load_object_metadata(ObjectId.parse(object_id)) or {}
        security = metadata.get("security")
        if isinstance(security, dict) and security.get("verdict") in {
            verdict.value for verdict in SecurityVerdict
        }:
            return dict(security)
        return {"verdict": SecurityVerdict.UNSCANNED.value}

    def resolve(self, public_token: object, supplied_key: object = None) -> ResolvedShare:
        if not isinstance(public_token, str) or len(public_token) > 128:
            raise ShareAccessError("Share not found.", 404)
        grant = self.repository.share_grant_by_token(public_token)
        text_grant = None if grant is not None else self.repository.text_share_grant_by_token(public_token)
        grant = grant or text_grant
        now = self._now()
        if grant is None or grant.revoked_at is not None:
            raise ShareAccessError("Share not found.", 404)
        if grant.expires_at is not None and grant.expires_at <= now:
            raise ShareAccessError("This share has expired.", 410)
        if grant.access_key_digest is not None and not self.access_keys.verify(
            supplied_key, grant.access_key_digest
        ):
            raise ShareAccessError("The Share Access Key is missing or invalid.", 403)
        if isinstance(grant, TextShareGrant):
            text = self.repository.text_share_source(grant)
            if text is None:
                raise ShareAccessError("Shared content is no longer available.", 404)
            return ResolvedShare(
                grant, None, None, {"verdict": SecurityVerdict.UNSCANNED.value}, text
            )
        source = self.repository.share_source(grant)
        if source is None:
            raise ShareAccessError("Shared content is no longer available.", 404)
        item, version = source
        return ResolvedShare(grant, item, version, self._security(version.object_id))

    def recipient_record(self, public_token: object, supplied_key: object = None) -> dict[str, object]:
        resolved = self.resolve(public_token, supplied_key)
        if resolved.text is not None:
            record = resolved.text.public_dict()
            return record | {
                "item_type": "text",
                "name": resolved.grant.source_title,
                "size": len(resolved.text.content.encode("utf-8")),
                "content_type": "text/plain; charset=utf-8",
                "created_at": resolved.grant.created_at.isoformat(),
                "expires_at": (resolved.grant.expires_at.isoformat()
                               if resolved.grant.expires_at else None),
                "access_key_required": resolved.grant.access_key_required,
                "security": {"verdict": SecurityVerdict.UNSCANNED.value},
                "security_verdict": SecurityVerdict.UNSCANNED.value,
                "read_only": True,
            }
        assert resolved.version is not None
        return {
            "item_type": "file",
            "name": resolved.grant.source_name,
            "size": resolved.version.size,
            "content_type": resolved.version.content_type,
            "created_at": resolved.grant.created_at.isoformat(),
            "expires_at": resolved.grant.expires_at.isoformat() if resolved.grant.expires_at else None,
            "access_key_required": resolved.grant.access_key_required,
            "security": resolved.security,
            "security_verdict": resolved.security.get("verdict", SecurityVerdict.UNSCANNED.value),
            "read_only": True,
        }

    def download(
        self, public_token: object, supplied_key: object = None, *,
        confirmed_malicious: bool = False,
    ) -> ResolvedShare:
        resolved = self.resolve(public_token, supplied_key)
        if resolved.text is not None:
            return resolved
        decision = self.security_policy.evaluate(
            resolved.security.get("verdict"), SecurityAction.DOWNLOAD,
            confirmed=confirmed_malicious,
        )
        if not decision.allowed:
            raise ShareAccessError(decision.reason or "Download is blocked.", 409)
        return resolved


__all__ = [
    "CreatedShare", "LibraryShareService", "ResolvedShare", "ShareAccessError",
]
