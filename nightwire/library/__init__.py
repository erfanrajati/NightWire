"""Community Library public identity and registration surface."""

from nightwire.library.auth import AuthenticationError, LibraryAuthService
from nightwire.library.domain import (
    DerivedObject, FileVersion, Folder, LibraryFile, LibraryScope, ShareGrant, TextShareGrant,
    User, UserStatus, Workspace,
)
from nightwire.library.registration import LibraryModule
from nightwire.library.service import DuplicateWarningError, LibraryOperationError, PersonalLibraryService
from nightwire.library.shares import LibraryShareService, ShareAccessError
from nightwire.library.trash import TrashService
from nightwire.library.texts import LibraryTextService
from nightwire.library.workspaces import CommunityWorkspacePolicy, WorkspacePolicy, WorkspaceService

__all__ = [
    "AuthenticationError",
    "LibraryAuthService",
    "LibraryFile",
    "FileVersion",
    "DerivedObject",
    "LibraryModule",
    "LibraryOperationError",
    "DuplicateWarningError",
    "LibraryScope",
    "LibraryShareService",
    "ShareAccessError",
    "ShareGrant",
    "TextShareGrant",
    "LibraryTextService",
    "PersonalLibraryService",
    "TrashService",
    "Folder",
    "CommunityWorkspacePolicy",
    "User",
    "UserStatus",
    "Workspace",
    "WorkspacePolicy",
    "WorkspaceService",
]
