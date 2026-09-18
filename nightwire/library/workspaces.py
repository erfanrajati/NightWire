"""Community Workspace policy and collaborative storage service."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from nightwire.library.domain import Folder, LibraryScope, User, Workspace
from nightwire.library.repository import LibraryRepository
from nightwire.library.service import LibraryOperationError, PersonalLibraryService


class WorkspacePolicy(ABC):
    """Public commercial-capability boundary for Workspace associations."""

    @property
    @abstractmethod
    def maximum_associations_per_user(self) -> int: ...

    @abstractmethod
    def assert_can_associate(self, current_associations: int) -> None: ...

    def public_dict(self) -> dict[str, object]:
        return {"maximum_associations_per_user": self.maximum_associations_per_user}


@dataclass(frozen=True, slots=True)
class CommunityWorkspacePolicy(WorkspacePolicy):
    maximum_associations_per_user: int = 1

    def assert_can_associate(self, current_associations: int) -> None:
        if current_associations >= self.maximum_associations_per_user:
            raise LibraryOperationError(
                "Community edition allows each user to own or belong to one Workspace total.", 409
            )


class WorkspaceService:
    def __init__(
        self,
        repository: LibraryRepository,
        storage: PersonalLibraryService,
        policy: WorkspacePolicy | None = None,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.policy = policy or CommunityWorkspacePolicy()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def current(self, user: User) -> Workspace | None:
        return self.repository.workspace_for_user(user.id)

    def create(self, user: User, name: object) -> Workspace:
        clean = self.storage._name(name)
        self.policy.assert_can_associate(1 if self.current(user) else 0)
        now = self._now()
        workspace_id = uuid.uuid4().hex
        root_id = uuid.uuid4().hex
        workspace = Workspace(workspace_id, clean, user.id, root_id, now, now)
        root = Folder(root_id, user.id, None, clean, True, now, now, workspace_id=workspace_id)
        try:
            self.repository.create_workspace(workspace, root, now)
        except Exception as exc:
            if self.current(user) is None:
                raise
            raise LibraryOperationError(
                "Community edition allows each user to own or belong to one Workspace total.", 409
            ) from exc
        return workspace

    def require_member(self, user: User, workspace_id: object) -> tuple[Workspace, LibraryScope]:
        workspace = self.repository.workspace_for_member(str(workspace_id), user.id)
        if workspace is None:
            raise LibraryOperationError("Workspace not found or membership is required.", 404)
        return workspace, LibraryScope.workspace(workspace.id, user.id)

    def describe(self, user: User, workspace_id: object | None = None) -> dict[str, object]:
        workspace = self.current(user) if workspace_id is None else self.require_member(user, workspace_id)[0]
        if workspace is None:
            return {"workspace": None, "members": [], "policy": self.policy.public_dict()}
        members = self.repository.workspace_members(workspace.id)
        return {
            "workspace": workspace.public_dict(),
            "members": [member.public_dict() | {"is_owner": member.id == workspace.owner_user_id}
                        for member in members],
            "policy": self.policy.public_dict(),
        }

    def add_member(self, user: User, workspace_id: object, email: object) -> User:
        workspace, _ = self.require_member(user, workspace_id)
        if workspace.owner_user_id != user.id:
            raise LibraryOperationError("Only the Workspace owner can add members.", 403)
        if not isinstance(email, str) or not email.strip():
            raise LibraryOperationError("An existing Library user's email is required.")
        normalized = email.strip().lower()
        candidate = self.repository.find_user_by_email(normalized)
        if candidate is None or candidate.status.value != "active":
            raise LibraryOperationError("Active Library user not found.", 404)
        self.policy.assert_can_associate(1 if self.current(candidate) else 0)
        try:
            member = self.repository.add_workspace_member(workspace.id, normalized, self._now())
        except Exception as exc:
            if self.current(candidate) is None:
                raise
            raise LibraryOperationError(
                "That user already owns or belongs to a Workspace; Community allows one total.", 409
            ) from exc
        if member is None:
            raise LibraryOperationError("Active Library user not found.", 404)
        return member

    def leave(self, user: User, workspace_id: object) -> str | None:
        workspace, _ = self.require_member(user, workspace_id)
        try:
            result = self.repository.leave_workspace(workspace.id, user.id, self._now())
        except ValueError as exc:
            raise LibraryOperationError(str(exc), 409) from exc
        if result is None:
            raise LibraryOperationError("Workspace membership not found.", 404)
        return result or None

    def remove_member(self, user: User, workspace_id: object, member_id: object) -> None:
        workspace, _ = self.require_member(user, workspace_id)
        try:
            removed = self.repository.remove_workspace_member(workspace.id, user.id, str(member_id))
        except ValueError as exc:
            raise LibraryOperationError(str(exc), 409) from exc
        if not removed:
            if workspace.owner_user_id != user.id:
                raise LibraryOperationError("Only the Workspace owner can remove members.", 403)
            raise LibraryOperationError("Workspace member not found.", 404)


__all__ = ["CommunityWorkspacePolicy", "WorkspacePolicy", "WorkspaceService"]
