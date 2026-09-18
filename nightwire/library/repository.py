"""Persistence repositories for Library identities, sessions, and invitations."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Mapping

from nightwire.core.storage import ObjectId
from nightwire.drop import AccessKeyDigest
from nightwire.library.database import Database
from nightwire.library.domain import (
    DerivedObject, FileVersion, Folder, LibraryFile, LibraryScope, ShareGrant, TextShareGrant,
    User, UserStatus, Workspace,
)
from nightwire.text import (
    TextLifecycle, TextMode, TextObject, TextProvenance, TextScopeKind,
)


def _as_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _user(row: Mapping[str, Any] | None) -> User | None:
    if row is None:
        return None
    return User(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        password_hash=str(row["password_hash"]),
        status=UserStatus(str(row["status"])),
        is_administrator=bool(row["is_administrator"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        approved_at=_as_datetime(row["approved_at"]),
    )


def _folder(row: Mapping[str, Any] | None) -> Folder | None:
    if row is None:
        return None
    return Folder(
        id=str(row["id"]), owner_id=str(row["owner_id"]),
        parent_id=str(row["parent_id"]) if row["parent_id"] else None,
        name=str(row["name"]), is_root=bool(row["is_root"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
        trashed_at=_as_datetime(row["trashed_at"]),
        workspace_id=str(row["workspace_id"]) if "workspace_id" in row.keys() and row["workspace_id"] else None,
    )


def _file(row: Mapping[str, Any] | None) -> LibraryFile | None:
    if row is None:
        return None
    return LibraryFile(
        id=str(row["id"]), owner_id=str(row["owner_id"]), folder_id=str(row["folder_id"]),
        object_id=str(row["object_id"]), name=str(row["name"]), size=int(row["size"]),
        checksum_sha256=str(row["checksum_sha256"]), content_type=str(row["content_type"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
        trashed_at=_as_datetime(row["trashed_at"]),
        workspace_id=str(row["workspace_id"]) if "workspace_id" in row.keys() and row["workspace_id"] else None,
    )


def _workspace(row: Mapping[str, Any] | None) -> Workspace | None:
    if row is None:
        return None
    return Workspace(
        id=str(row["id"]), name=str(row["name"]), owner_user_id=str(row["owner_user_id"]),
        root_folder_id=str(row["root_folder_id"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _version(row: Mapping[str, Any] | None) -> FileVersion | None:
    if row is None:
        return None
    return FileVersion(
        id=str(row["id"]), file_id=str(row["file_id"]),
        version_number=int(row["version_number"]), object_id=str(row["object_id"]),
        size=int(row["size"]), checksum_sha256=str(row["checksum_sha256"]),
        content_type=str(row["content_type"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        created_by_user_id=str(row["created_by_user_id"]),
        source_kind=str(row["source_kind"]),
        source_id=str(row["source_id"]) if row["source_id"] else None,
    )


def _derived(row: Mapping[str, Any] | None) -> DerivedObject | None:
    if row is None:
        return None
    provenance = json.loads(str(row["provenance_json"]))
    return DerivedObject(
        id=str(row["id"]), file_id=str(row["file_id"]),
        source_version_id=str(row["source_version_id"]), operation=str(row["operation"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        created_by_user_id=str(row["created_by_user_id"]),
        output_object_id=str(row["output_object_id"]), size=int(row["size"]),
        checksum_sha256=str(row["checksum_sha256"]), content_type=str(row["content_type"]),
        provenance=provenance if isinstance(provenance, dict) else {},
        promoted_version_id=(str(row["promoted_version_id"])
                             if row["promoted_version_id"] else None),
    )


def _share(row: Mapping[str, Any] | None) -> ShareGrant | None:
    if row is None:
        return None
    digest = None
    if row["access_key_algorithm"] and row["access_key_salt"] and row["access_key_digest"]:
        digest = AccessKeyDigest(
            algorithm=str(row["access_key_algorithm"]), salt=str(row["access_key_salt"]),
            digest=str(row["access_key_digest"]),
        )
    return ShareGrant(
        id=str(row["id"]), public_token=str(row["public_token"]),
        file_id=str(row["file_id"]), source_version_id=str(row["source_version_id"]),
        source_name=str(row["source_name"]), created_by_user_id=str(row["created_by_user_id"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        expires_at=_as_datetime(row["expires_at"]), revoked_at=_as_datetime(row["revoked_at"]),
        access_key_digest=digest,
        workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
    )


def _text(row: Mapping[str, Any] | None) -> TextObject | None:
    if row is None:
        return None
    workspace_id = str(row["workspace_id"]) if row["workspace_id"] else None
    provenance = None
    if row["source_kind"] and row["source_id"]:
        provenance = TextProvenance(str(row["source_kind"]), str(row["source_id"]))
    return TextObject(
        id=str(row["id"]), title=str(row["title"]), content=str(row["content"]),
        mode=TextMode(str(row["mode"])),
        language=str(row["language"]) if row["language"] else None,
        scope_kind=TextScopeKind.WORKSPACE if workspace_id else TextScopeKind.PERSONAL,
        scope_id=workspace_id or str(row["owner_id"]),
        lifecycle=TextLifecycle.PERSISTENT,
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
        folder_id=str(row["folder_id"]), trashed_at=_as_datetime(row["trashed_at"]),
        provenance=provenance,
    )


def _text_share(row: Mapping[str, Any] | None) -> TextShareGrant | None:
    if row is None:
        return None
    digest = None
    if row["access_key_algorithm"] and row["access_key_salt"] and row["access_key_digest"]:
        digest = AccessKeyDigest(
            algorithm=str(row["access_key_algorithm"]), salt=str(row["access_key_salt"]),
            digest=str(row["access_key_digest"]),
        )
    return TextShareGrant(
        id=str(row["id"]), public_token=str(row["public_token"]),
        text_id=str(row["text_id"]), source_title=str(row["source_title"]),
        created_by_user_id=str(row["created_by_user_id"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        expires_at=_as_datetime(row["expires_at"]), revoked_at=_as_datetime(row["revoked_at"]),
        access_key_digest=digest,
        workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
    )


def _storage_scope(value: str | LibraryScope) -> LibraryScope:
    return value if isinstance(value, LibraryScope) else LibraryScope.personal(value)


def _scope_parameters(value: str | LibraryScope) -> dict[str, Any]:
    scope = _storage_scope(value)
    return {"scope_id": scope.id, "workspace_id": scope.workspace_id}


_SCOPE_SQL = "((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id)"
_FILE_SCOPE_SQL = "((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id) OR f.workspace_id = :workspace_id)"


class LibraryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def user_count(self) -> int:
        with self.database.transaction() as tx:
            row = tx.fetch_one("SELECT COUNT(*) AS total FROM library_users")
            return int(row["total"]) if row else 0

    def find_user_by_email(self, email: str) -> User | None:
        with self.database.transaction() as tx:
            return _user(
                tx.fetch_one("SELECT * FROM library_users WHERE email = :email", {"email": email})
            )

    def find_user_by_id(self, user_id: str) -> User | None:
        with self.database.transaction() as tx:
            return _user(
                tx.fetch_one("SELECT * FROM library_users WHERE id = :id", {"id": user_id})
            )

    def create_user(self, user: User) -> None:
        with self.database.transaction() as tx:
            self._insert_user(tx, user)

    @staticmethod
    def _insert_user(tx, user: User) -> None:
        tx.execute(
            """INSERT INTO library_users
               (id, email, display_name, password_hash, status,
                is_administrator, created_at, approved_at)
               VALUES (:id, :email, :display_name, :password_hash, :status,
                       :is_administrator, :created_at, :approved_at)""",
            {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "password_hash": user.password_hash,
                "status": user.status.value,
                "is_administrator": int(user.is_administrator),
                "created_at": user.created_at.isoformat(),
                "approved_at": user.approved_at.isoformat() if user.approved_at else None,
            },
        )

    def create_invited_user(self, user: User, invitation_id: str, used_at: datetime) -> None:
        """Atomically create an account and consume its one-use invitation."""
        with self.database.transaction() as tx:
            self._insert_user(tx, user)
            consumed = tx.execute(
                """UPDATE library_invitations
                   SET used_at = :used_at, used_by_user_id = :user_id
                   WHERE id = :id AND used_at IS NULL AND expires_at > :used_at""",
                {"id": invitation_id, "user_id": user.id, "used_at": used_at.isoformat()},
            )
            if not consumed:
                raise ValueError("Invitation has already been used or expired.")

    def pending_users(self) -> list[User]:
        with self.database.transaction() as tx:
            return [
                user
                for row in tx.fetch_all(
                    "SELECT * FROM library_users WHERE status = :status ORDER BY created_at",
                    {"status": UserStatus.PENDING.value},
                )
                if (user := _user(row)) is not None
            ]

    def set_user_status(self, user_id: str, status: UserStatus, changed_at: datetime) -> User | None:
        with self.database.transaction() as tx:
            changed = tx.execute(
                """UPDATE library_users
                   SET status = :status, approved_at = :approved_at
                   WHERE id = :id AND is_administrator = 0 AND status = :pending""",
                {
                    "id": user_id,
                    "status": status.value,
                    "approved_at": changed_at.isoformat() if status is UserStatus.ACTIVE else None,
                    "pending": UserStatus.PENDING.value,
                },
            )
            if not changed:
                return None
            return _user(tx.fetch_one("SELECT * FROM library_users WHERE id = :id", {"id": user_id}))

    def create_session(
        self, session_id: str, user_id: str, token_hash: str, created_at: datetime, expires_at: datetime
    ) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO library_sessions
                   (id, user_id, token_hash, created_at, expires_at, revoked_at)
                   VALUES (:id, :user_id, :token_hash, :created_at, :expires_at, NULL)""",
                {
                    "id": session_id,
                    "user_id": user_id,
                    "token_hash": token_hash,
                    "created_at": created_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
            )

    def user_for_session(self, token_hash: str, now: datetime) -> User | None:
        with self.database.transaction() as tx:
            return _user(
                tx.fetch_one(
                    """SELECT u.* FROM library_sessions s
                       JOIN library_users u ON u.id = s.user_id
                       WHERE s.token_hash = :token_hash
                         AND s.revoked_at IS NULL
                         AND s.expires_at > :now
                         AND u.status = :active""",
                    {
                        "token_hash": token_hash,
                        "now": now.isoformat(),
                        "active": UserStatus.ACTIVE.value,
                    },
                )
            )

    def revoke_session(self, token_hash: str, revoked_at: datetime) -> bool:
        with self.database.transaction() as tx:
            return bool(
                tx.execute(
                    """UPDATE library_sessions SET revoked_at = :revoked_at
                       WHERE token_hash = :token_hash AND revoked_at IS NULL""",
                    {"token_hash": token_hash, "revoked_at": revoked_at.isoformat()},
                )
            )

    def revoke_user_sessions(self, user_id: str, revoked_at: datetime) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """UPDATE library_sessions SET revoked_at = :revoked_at
                   WHERE user_id = :user_id AND revoked_at IS NULL""",
                {"user_id": user_id, "revoked_at": revoked_at.isoformat()},
            )

    def create_invitation(
        self,
        invitation_id: str,
        email: str,
        token_hash: str,
        administrator_id: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO library_invitations
                   (id, email, token_hash, created_by_user_id, created_at, expires_at,
                    used_at, used_by_user_id)
                   VALUES (:id, :email, :token_hash, :administrator_id, :created_at,
                           :expires_at, NULL, NULL)""",
                {
                    "id": invitation_id,
                    "email": email,
                    "token_hash": token_hash,
                    "administrator_id": administrator_id,
                    "created_at": created_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
            )

    def valid_invitation(self, token_hash: str, email: str, now: datetime) -> Mapping[str, Any] | None:
        with self.database.transaction() as tx:
            return tx.fetch_one(
                """SELECT * FROM library_invitations
                   WHERE token_hash = :token_hash AND email = :email
                     AND used_at IS NULL AND expires_at > :now""",
                {"token_hash": token_hash, "email": email, "now": now.isoformat()},
            )

    def consume_invitation(self, invitation_id: str, user_id: str, used_at: datetime) -> bool:
        with self.database.transaction() as tx:
            return bool(
                tx.execute(
                    """UPDATE library_invitations
                       SET used_at = :used_at, used_by_user_id = :user_id
                       WHERE id = :id AND used_at IS NULL""",
                    {"id": invitation_id, "user_id": user_id, "used_at": used_at.isoformat()},
                )
            )

    # Every storage query includes an explicit personal/workspace scope.
    def root_folder(self, scope: str | LibraryScope) -> Folder | None:
        with self.database.transaction() as tx:
            return _folder(tx.fetch_one(
                f"SELECT * FROM library_folders WHERE {_SCOPE_SQL} AND is_root = 1",
                _scope_parameters(scope),
            ))

    def create_folder(self, folder: Folder) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO library_folders
                   (id, owner_id, parent_id, name, is_root, created_at, updated_at, trashed_at, workspace_id)
                   VALUES (:id, :owner_id, :parent_id, :name, :is_root, :created_at, :updated_at, NULL, :workspace_id)""",
                {"id": folder.id, "owner_id": folder.owner_id, "parent_id": folder.parent_id,
                 "name": folder.name, "is_root": int(folder.is_root),
                 "created_at": folder.created_at.isoformat(), "updated_at": folder.updated_at.isoformat(),
                 "workspace_id": folder.workspace_id},
            )

    def folder(self, scope: str | LibraryScope, folder_id: str) -> Folder | None:
        with self.database.transaction() as tx:
            return _folder(tx.fetch_one(
                f"SELECT * FROM library_folders WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": folder_id, **_scope_parameters(scope)},
            ))

    def file(self, scope: str | LibraryScope, file_id: str) -> LibraryFile | None:
        with self.database.transaction() as tx:
            return _file(tx.fetch_one(
                f"SELECT * FROM library_files WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": file_id, **_scope_parameters(scope)},
            ))

    def children(self, scope: str | LibraryScope, folder_id: str) -> tuple[list[Folder], list[LibraryFile]]:
        parameters = {"parent": folder_id, **_scope_parameters(scope)}
        with self.database.transaction() as tx:
            folders = [_folder(row) for row in tx.fetch_all(
                f"SELECT * FROM library_folders WHERE {_SCOPE_SQL} AND parent_id = :parent AND trashed_at IS NULL ORDER BY lower(name), name",
                parameters,
            )]
            files = [_file(row) for row in tx.fetch_all(
                f"SELECT * FROM library_files WHERE {_SCOPE_SQL} AND folder_id = :parent AND trashed_at IS NULL ORDER BY lower(name), name",
                parameters,
            )]
        return ([item for item in folders if item], [item for item in files if item])

    def scoped_files(self, scope: str | LibraryScope) -> list[tuple[LibraryFile, str]]:
        """Return active files and relative folder paths inside exactly one authorized scope."""
        parameters = _scope_parameters(scope)
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                """WITH RECURSIVE paths(id, path) AS (
                       SELECT id, '' FROM library_folders
                       WHERE ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id)
                              OR workspace_id = :workspace_id)
                         AND is_root = 1 AND trashed_at IS NULL
                       UNION ALL
                       SELECT f.id,
                              CASE WHEN paths.path = '' THEN f.name ELSE paths.path || '/' || f.name END
                       FROM library_folders f JOIN paths ON f.parent_id = paths.id
                       WHERE ((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id)
                              OR f.workspace_id = :workspace_id)
                         AND f.trashed_at IS NULL
                   )
                   SELECT item.*, paths.path AS folder_path
                   FROM library_files item JOIN paths ON paths.id = item.folder_id
                   WHERE ((:workspace_id IS NULL AND item.workspace_id IS NULL AND item.owner_id = :scope_id)
                          OR item.workspace_id = :workspace_id)
                     AND item.trashed_at IS NULL""",
                parameters,
            )
        return [
            (item, str(row["folder_path"]))
            for row in rows if (item := _file(row)) is not None
        ]

    def name_exists(self, scope: str | LibraryScope, folder_id: str, name: str, *, except_id: str | None = None) -> bool:
        parameters = {"parent": folder_id, "name": name, "except_id": except_id or "", **_scope_parameters(scope)}
        with self.database.transaction() as tx:
            folder = tx.fetch_one(
                f"SELECT id FROM library_folders WHERE {_SCOPE_SQL} AND parent_id = :parent AND lower(name) = lower(:name) AND trashed_at IS NULL AND id != :except_id", parameters)
            file = tx.fetch_one(
                f"SELECT id FROM library_files WHERE {_SCOPE_SQL} AND folder_id = :parent AND lower(name) = lower(:name) AND trashed_at IS NULL AND id != :except_id", parameters)
            text = tx.fetch_one(
                f"SELECT id FROM library_text_objects WHERE {_SCOPE_SQL} AND folder_id = :parent AND lower(title) = lower(:name) AND trashed_at IS NULL AND id != :except_id", parameters)
        return folder is not None or file is not None or text is not None

    def create_file(self, item: LibraryFile) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO library_files
                   (id, owner_id, folder_id, object_id, name, size, checksum_sha256,
                    content_type, created_at, updated_at, trashed_at, workspace_id)
                   VALUES (:id, :owner_id, :folder_id, :object_id, :name, :size,
                           :checksum, :content_type, :created_at, :updated_at, NULL, :workspace_id)""",
                {"id": item.id, "owner_id": item.owner_id, "folder_id": item.folder_id,
                 "object_id": item.object_id, "name": item.name, "size": item.size,
                 "checksum": item.checksum_sha256, "content_type": item.content_type,
                 "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
                 "workspace_id": item.workspace_id},
            )
            self._insert_version(tx, FileVersion(
                id=uuid.uuid4().hex, file_id=item.id, version_number=1,
                object_id=item.object_id, size=item.size,
                checksum_sha256=item.checksum_sha256, content_type=item.content_type,
                created_at=item.created_at, created_by_user_id=item.owner_id,
            ))

    @staticmethod
    def _insert_version(tx, version: FileVersion) -> None:
        tx.execute(
            """INSERT INTO library_file_versions
               (id, file_id, version_number, object_id, size, checksum_sha256,
                content_type, created_at, created_by_user_id, source_kind, source_id)
               VALUES (:id, :file_id, :number, :object_id, :size, :checksum,
                       :content_type, :created_at, :created_by, :source_kind, :source_id)""",
            {"id": version.id, "file_id": version.file_id, "number": version.version_number,
             "object_id": version.object_id, "size": version.size,
             "checksum": version.checksum_sha256, "content_type": version.content_type,
             "created_at": version.created_at.isoformat(),
             "created_by": version.created_by_user_id, "source_kind": version.source_kind,
             "source_id": version.source_id},
        )

    def versions(self, scope: str | LibraryScope, file_id: str) -> list[FileVersion]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                f"""SELECT v.* FROM library_file_versions v
                    JOIN library_files f ON f.id = v.file_id
                    WHERE v.file_id = :file_id AND {_FILE_SCOPE_SQL}
                      AND f.trashed_at IS NULL ORDER BY v.version_number DESC""",
                {"file_id": file_id, **_scope_parameters(scope)},
            )
        return [item for row in rows if (item := _version(row)) is not None]

    def version(self, scope: str | LibraryScope, file_id: str, version_id: str) -> FileVersion | None:
        return next((item for item in self.versions(scope, file_id) if item.id == version_id), None)

    def append_version(self, scope: str | LibraryScope, version: FileVersion, updated_at: datetime) -> None:
        """Atomically append history and advance the logical file projection."""
        with self.database.transaction() as tx:
            file_row = tx.fetch_one(
                f"SELECT id FROM library_files WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": version.file_id, **_scope_parameters(scope)},
            )
            if file_row is None:
                raise ValueError("File not found.")
            self._insert_version(tx, version)
            tx.execute(
                """UPDATE library_files SET object_id = :object_id, size = :size,
                   checksum_sha256 = :checksum, content_type = :content_type, updated_at = :updated
                   WHERE id = :id""",
                {"id": version.file_id, "object_id": version.object_id, "size": version.size,
                 "checksum": version.checksum_sha256, "content_type": version.content_type,
                 "updated": updated_at.isoformat()},
            )

    def prune_versions(self, file_id: str, keep: int) -> list[str]:
        """Remove oldest non-current rows and return candidate objects for reclamation."""
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                "SELECT id, object_id FROM library_file_versions WHERE file_id = :file_id ORDER BY version_number DESC",
                {"file_id": file_id},
            )
            removed: list[str] = []
            for row in rows[keep:]:
                changed = tx.execute(
                    """DELETE FROM library_file_versions WHERE id = :id
                       AND NOT EXISTS (
                           SELECT 1 FROM library_derived_objects
                           WHERE source_version_id = :id OR promoted_version_id = :id
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM library_share_grants WHERE source_version_id = :id
                       )""",
                    {"id": row["id"]},
                )
                if changed:
                    removed.append(str(row["object_id"]))
            return removed

    def create_derived_object(self, scope: str | LibraryScope, item: DerivedObject) -> None:
        with self.database.transaction() as tx:
            source = tx.fetch_one(
                f"""SELECT v.id FROM library_file_versions v JOIN library_files f ON f.id = v.file_id
                    WHERE v.id = :source AND v.file_id = :file_id
                      AND {_FILE_SCOPE_SQL}
                      AND f.trashed_at IS NULL""",
                {"source": item.source_version_id, "file_id": item.file_id,
                 **_scope_parameters(scope)},
            )
            if source is None:
                raise ValueError("Source version not found.")
            tx.execute(
                """INSERT INTO library_derived_objects
                   (id, file_id, source_version_id, operation, created_at, created_by_user_id,
                    output_object_id, size, checksum_sha256, content_type, provenance_json,
                    promoted_version_id)
                   VALUES (:id, :file_id, :source, :operation, :created_at, :created_by,
                           :output, :size, :checksum, :content_type, :provenance, NULL)""",
                {"id": item.id, "file_id": item.file_id, "source": item.source_version_id,
                 "operation": item.operation, "created_at": item.created_at.isoformat(),
                 "created_by": item.created_by_user_id, "output": item.output_object_id,
                 "size": item.size, "checksum": item.checksum_sha256,
                 "content_type": item.content_type,
                 "provenance": json.dumps(item.provenance, sort_keys=True, separators=(",", ":"))},
            )

    def derived_objects(self, scope: str | LibraryScope, file_id: str) -> list[DerivedObject]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                f"""SELECT d.* FROM library_derived_objects d JOIN library_files f ON f.id = d.file_id
                    WHERE d.file_id = :file_id
                      AND {_FILE_SCOPE_SQL}
                      AND f.trashed_at IS NULL ORDER BY d.created_at DESC""",
                {"file_id": file_id, **_scope_parameters(scope)},
            )
        return [item for row in rows if (item := _derived(row)) is not None]

    def derived_object(self, scope: str | LibraryScope, file_id: str, derived_id: str) -> DerivedObject | None:
        return next((item for item in self.derived_objects(scope, file_id) if item.id == derived_id), None)

    def mark_derived_promoted(self, derived_id: str, version_id: str) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                "UPDATE library_derived_objects SET promoted_version_id = :version WHERE id = :id AND promoted_version_id IS NULL",
                {"id": derived_id, "version": version_id},
            )

    def create_share_grant(self, scope: str | LibraryScope, grant: ShareGrant) -> None:
        digest = grant.access_key_digest
        with self.database.transaction() as tx:
            source = tx.fetch_one(
                f"""SELECT v.id FROM library_file_versions v JOIN library_files f ON f.id = v.file_id
                    WHERE f.id = :file_id AND v.id = :version AND {_FILE_SCOPE_SQL}
                      AND f.trashed_at IS NULL""",
                {"file_id": grant.file_id, "version": grant.source_version_id,
                 **_scope_parameters(scope)},
            )
            if source is None:
                raise ValueError("Source file version not found.")
            tx.execute(
                """INSERT INTO library_share_grants
                   (id, public_token, file_id, source_version_id, source_name,
                    created_by_user_id, created_at, expires_at, revoked_at,
                    access_key_algorithm, access_key_salt, access_key_digest, workspace_id)
                   VALUES (:id, :token, :file_id, :version, :name, :creator, :created,
                           :expires, NULL, :algorithm, :salt, :digest, :workspace_id)""",
                {"id": grant.id, "token": grant.public_token, "file_id": grant.file_id,
                 "version": grant.source_version_id, "name": grant.source_name,
                 "creator": grant.created_by_user_id, "created": grant.created_at.isoformat(),
                 "expires": grant.expires_at.isoformat() if grant.expires_at else None,
                 "algorithm": digest.algorithm if digest else None,
                 "salt": digest.salt if digest else None, "digest": digest.digest if digest else None,
                 "workspace_id": grant.workspace_id},
            )

    def share_grant_by_token(self, public_token: str) -> ShareGrant | None:
        with self.database.transaction() as tx:
            return _share(tx.fetch_one(
                "SELECT * FROM library_share_grants WHERE public_token = :token",
                {"token": public_token},
            ))

    def share_grants_for_file(
        self, scope: str | LibraryScope, file_id: str, creator_id: str,
    ) -> list[ShareGrant]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                f"""SELECT g.* FROM library_share_grants g JOIN library_files f ON f.id = g.file_id
                    WHERE g.file_id = :file_id AND g.created_by_user_id = :creator
                      AND {_FILE_SCOPE_SQL} ORDER BY g.created_at DESC""",
                {"file_id": file_id, "creator": creator_id, **_scope_parameters(scope)},
            )
        return [grant for row in rows if (grant := _share(row)) is not None]

    def share_grants_created_by(self, creator_id: str) -> list[ShareGrant]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                """SELECT g.* FROM library_share_grants g JOIN library_files f ON f.id = g.file_id
                   WHERE g.created_by_user_id = :creator ORDER BY g.created_at DESC""",
                {"creator": creator_id},
            )
        return [grant for row in rows if (grant := _share(row)) is not None]

    def revoke_share_grant(self, creator_id: str, grant_id: str, revoked_at: datetime) -> bool:
        with self.database.transaction() as tx:
            return bool(tx.execute(
                """UPDATE library_share_grants SET revoked_at = :revoked
                   WHERE id = :id AND created_by_user_id = :creator AND revoked_at IS NULL""",
                {"id": grant_id, "creator": creator_id, "revoked": revoked_at.isoformat()},
            ))

    def share_source(self, grant: ShareGrant) -> tuple[LibraryFile, FileVersion] | None:
        with self.database.transaction() as tx:
            row = tx.fetch_one(
                """SELECT f.* FROM library_files f WHERE f.id = :file_id""",
                {"file_id": grant.file_id},
            )
            version_row = tx.fetch_one(
                """SELECT * FROM library_file_versions
                   WHERE id = :version AND file_id = :file_id""",
                {"version": grant.source_version_id, "file_id": grant.file_id},
            )
        item, version = _file(row), _version(version_row)
        return (item, version) if item is not None and version is not None else None

    # First-class Text persistence. Text content is application data, not a fake file blob.
    def create_text(self, item: TextObject, owner_id: str, workspace_id: str | None) -> None:
        provenance = item.provenance
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO library_text_objects
                   (id, owner_id, folder_id, title, content, mode, language,
                    source_kind, source_id, created_at, updated_at, trashed_at, workspace_id)
                   VALUES (:id, :owner, :folder, :title, :content, :mode, :language,
                           :source_kind, :source_id, :created, :updated, NULL, :workspace)""",
                {"id": item.id, "owner": owner_id, "folder": item.folder_id,
                 "title": item.title, "content": item.content, "mode": item.mode.value,
                 "language": item.language,
                 "source_kind": provenance.source_kind if provenance else None,
                 "source_id": provenance.source_id if provenance else None,
                 "created": item.created_at.isoformat(), "updated": item.updated_at.isoformat(),
                 "workspace": workspace_id},
            )

    def text(self, scope: str | LibraryScope, text_id: str, *, trashed: bool = False) -> TextObject | None:
        state = "IS NOT NULL" if trashed else "IS NULL"
        with self.database.transaction() as tx:
            return _text(tx.fetch_one(
                f"SELECT * FROM library_text_objects WHERE id = :id AND {_SCOPE_SQL} AND trashed_at {state}",
                {"id": text_id, **_scope_parameters(scope)},
            ))

    def texts_in_folder(self, scope: str | LibraryScope, folder_id: str) -> list[TextObject]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                f"""SELECT * FROM library_text_objects WHERE {_SCOPE_SQL}
                    AND folder_id = :folder AND trashed_at IS NULL
                    ORDER BY lower(title), title""",
                {"folder": folder_id, **_scope_parameters(scope)},
            )
        return [item for row in rows if (item := _text(row)) is not None]

    def scoped_texts(self, scope: str | LibraryScope) -> list[tuple[TextObject, str]]:
        parameters = _scope_parameters(scope)
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                """WITH RECURSIVE paths(id, path) AS (
                       SELECT id, '' FROM library_folders
                       WHERE ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id)
                              OR workspace_id = :workspace_id)
                         AND is_root = 1 AND trashed_at IS NULL
                       UNION ALL
                       SELECT f.id,
                              CASE WHEN paths.path = '' THEN f.name ELSE paths.path || '/' || f.name END
                       FROM library_folders f JOIN paths ON f.parent_id = paths.id
                       WHERE ((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id)
                              OR f.workspace_id = :workspace_id)
                         AND f.trashed_at IS NULL
                   )
                   SELECT item.*, paths.path AS folder_path
                   FROM library_text_objects item JOIN paths ON paths.id = item.folder_id
                   WHERE ((:workspace_id IS NULL AND item.workspace_id IS NULL AND item.owner_id = :scope_id)
                          OR item.workspace_id = :workspace_id)
                     AND item.trashed_at IS NULL""",
                parameters,
            )
        return [(item, str(row["folder_path"])) for row in rows
                if (item := _text(row)) is not None]

    def update_text(self, scope: str | LibraryScope, item: TextObject) -> None:
        provenance = item.provenance
        with self.database.transaction() as tx:
            tx.execute(
                f"""UPDATE library_text_objects SET folder_id = :folder, title = :title,
                    content = :content, mode = :mode, language = :language,
                    source_kind = :source_kind, source_id = :source_id, updated_at = :updated
                    WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL""",
                {"id": item.id, "folder": item.folder_id, "title": item.title,
                 "content": item.content, "mode": item.mode.value, "language": item.language,
                 "source_kind": provenance.source_kind if provenance else None,
                 "source_id": provenance.source_id if provenance else None,
                 "updated": item.updated_at.isoformat(), **_scope_parameters(scope)},
            )

    def trash_text(self, scope: str | LibraryScope, text_id: str, trashed_at: datetime) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                f"UPDATE library_text_objects SET trashed_at = :at WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": text_id, "at": trashed_at.isoformat(), **_scope_parameters(scope)},
            )

    def trashed_texts(self, scope: str | LibraryScope) -> list[TextObject]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                f"""SELECT item.* FROM library_text_objects item
                    WHERE ((:workspace_id IS NULL AND item.workspace_id IS NULL AND item.owner_id = :scope_id)
                           OR item.workspace_id = :workspace_id)
                      AND item.trashed_at IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM library_folders parent
                          WHERE parent.id = item.folder_id AND parent.trashed_at IS NOT NULL
                      )
                    ORDER BY item.trashed_at DESC, lower(item.title)""",
                _scope_parameters(scope),
            )
        return [item for row in rows if (item := _text(row)) is not None]

    def restore_text(
        self, scope: str | LibraryScope, text_id: str, folder_id: str,
        title: str, restored_at: datetime,
    ) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                f"""UPDATE library_text_objects SET folder_id = :folder, title = :title,
                    trashed_at = NULL, updated_at = :updated
                    WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL""",
                {"id": text_id, "folder": folder_id, "title": title,
                 "updated": restored_at.isoformat(), **_scope_parameters(scope)},
            )

    def permanently_delete_text(self, scope: str | LibraryScope, text_id: str) -> bool:
        with self.database.transaction() as tx:
            exists = tx.fetch_one(
                f"SELECT id FROM library_text_objects WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL",
                {"id": text_id, **_scope_parameters(scope)},
            )
            if exists is None:
                return False
            tx.execute("DELETE FROM library_text_share_grants WHERE text_id = :id", {"id": text_id})
            tx.execute("DELETE FROM library_text_objects WHERE id = :id", {"id": text_id})
            return True

    def create_text_share_grant(self, scope: str | LibraryScope, grant: TextShareGrant) -> None:
        digest = grant.access_key_digest
        with self.database.transaction() as tx:
            source = tx.fetch_one(
                f"SELECT id FROM library_text_objects WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": grant.text_id, **_scope_parameters(scope)},
            )
            if source is None:
                raise ValueError("Source Text not found.")
            tx.execute(
                """INSERT INTO library_text_share_grants
                   (id, public_token, text_id, source_title, created_by_user_id,
                    created_at, expires_at, revoked_at, access_key_algorithm,
                    access_key_salt, access_key_digest, workspace_id)
                   VALUES (:id, :token, :text_id, :title, :creator, :created, :expires,
                           NULL, :algorithm, :salt, :digest, :workspace)""",
                {"id": grant.id, "token": grant.public_token, "text_id": grant.text_id,
                 "title": grant.source_title, "creator": grant.created_by_user_id,
                 "created": grant.created_at.isoformat(),
                 "expires": grant.expires_at.isoformat() if grant.expires_at else None,
                 "algorithm": digest.algorithm if digest else None,
                 "salt": digest.salt if digest else None, "digest": digest.digest if digest else None,
                 "workspace": grant.workspace_id},
            )

    def text_share_grant_by_token(self, public_token: str) -> TextShareGrant | None:
        with self.database.transaction() as tx:
            return _text_share(tx.fetch_one(
                "SELECT * FROM library_text_share_grants WHERE public_token = :token",
                {"token": public_token},
            ))

    def text_share_grants_for_text(
        self, scope: str | LibraryScope, text_id: str, creator_id: str,
    ) -> list[TextShareGrant]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                f"""SELECT g.* FROM library_text_share_grants g
                    JOIN library_text_objects item ON item.id = g.text_id
                    WHERE g.text_id = :text_id AND g.created_by_user_id = :creator
                      AND ((:workspace_id IS NULL AND item.workspace_id IS NULL AND item.owner_id = :scope_id)
                           OR item.workspace_id = :workspace_id)
                    ORDER BY g.created_at DESC""",
                {"text_id": text_id, "creator": creator_id, **_scope_parameters(scope)},
            )
        return [grant for row in rows if (grant := _text_share(row)) is not None]

    def text_share_grants_created_by(self, creator_id: str) -> list[TextShareGrant]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                "SELECT * FROM library_text_share_grants WHERE created_by_user_id = :creator ORDER BY created_at DESC",
                {"creator": creator_id},
            )
        return [grant for row in rows if (grant := _text_share(row)) is not None]

    def revoke_text_share_grant(self, creator_id: str, grant_id: str, revoked_at: datetime) -> bool:
        with self.database.transaction() as tx:
            return bool(tx.execute(
                """UPDATE library_text_share_grants SET revoked_at = :revoked
                   WHERE id = :id AND created_by_user_id = :creator AND revoked_at IS NULL""",
                {"id": grant_id, "creator": creator_id, "revoked": revoked_at.isoformat()},
            ))

    def text_share_source(self, grant: TextShareGrant) -> TextObject | None:
        with self.database.transaction() as tx:
            return _text(tx.fetch_one(
                "SELECT * FROM library_text_objects WHERE id = :id", {"id": grant.text_id}
            ))

    def update_folder(self, scope: str | LibraryScope, folder_id: str, name: str, parent_id: str, updated_at: datetime) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                f"UPDATE library_folders SET name = :name, parent_id = :parent, updated_at = :updated WHERE id = :id AND {_SCOPE_SQL} AND is_root = 0 AND trashed_at IS NULL",
                {"id": folder_id, **_scope_parameters(scope), "name": name, "parent": parent_id,
                 "updated": updated_at.isoformat()},
            )

    def update_file(self, scope: str | LibraryScope, file_id: str, name: str, folder_id: str, updated_at: datetime) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                f"UPDATE library_files SET name = :name, folder_id = :parent, updated_at = :updated WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": file_id, **_scope_parameters(scope), "name": name, "parent": folder_id,
                 "updated": updated_at.isoformat()},
            )

    def trash_file(self, scope: str | LibraryScope, file_id: str, trashed_at: datetime) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                f"UPDATE library_files SET trashed_at = :at WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NULL",
                {"id": file_id, **_scope_parameters(scope), "at": trashed_at.isoformat()},
            )

    def trash_folder_tree(self, scope: str | LibraryScope, folder_id: str, trashed_at: datetime) -> None:
        parameters = {"id": folder_id, "at": trashed_at.isoformat(), **_scope_parameters(scope)}
        with self.database.transaction() as tx:
            tx.execute(
                """WITH RECURSIVE tree(id) AS (
                       SELECT id FROM library_folders WHERE id = :id AND ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id) AND is_root = 0
                       UNION ALL SELECT f.id FROM library_folders f JOIN tree t ON f.parent_id = t.id WHERE ((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id) OR f.workspace_id = :workspace_id)
                   ) UPDATE library_files SET trashed_at = :at
                     WHERE ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id) AND folder_id IN (SELECT id FROM tree) AND trashed_at IS NULL""", parameters)
            tx.execute(
                """WITH RECURSIVE tree(id) AS (
                       SELECT id FROM library_folders WHERE id = :id AND ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id) AND is_root = 0
                       UNION ALL SELECT f.id FROM library_folders f JOIN tree t ON f.parent_id = t.id WHERE ((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id) OR f.workspace_id = :workspace_id)
                   ) UPDATE library_text_objects SET trashed_at = :at
                     WHERE ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id) AND folder_id IN (SELECT id FROM tree) AND trashed_at IS NULL""", parameters)
            tx.execute(
                """WITH RECURSIVE tree(id) AS (
                       SELECT id FROM library_folders WHERE id = :id AND ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id) AND is_root = 0
                       UNION ALL SELECT f.id FROM library_folders f JOIN tree t ON f.parent_id = t.id WHERE ((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id) OR f.workspace_id = :workspace_id)
                   ) UPDATE library_folders SET trashed_at = :at
                     WHERE ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id) AND id IN (SELECT id FROM tree) AND trashed_at IS NULL""", parameters)

    def trashed_folder(self, scope: str | LibraryScope, folder_id: str) -> Folder | None:
        with self.database.transaction() as tx:
            return _folder(tx.fetch_one(
                f"SELECT * FROM library_folders WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL",
                {"id": folder_id, **_scope_parameters(scope)},
            ))

    def trashed_file(self, scope: str | LibraryScope, file_id: str) -> LibraryFile | None:
        with self.database.transaction() as tx:
            return _file(tx.fetch_one(
                f"SELECT * FROM library_files WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL",
                {"id": file_id, **_scope_parameters(scope)},
            ))

    def trash_items(self, scope: str | LibraryScope) -> tuple[list[Folder], list[LibraryFile]]:
        parameters = _scope_parameters(scope)
        with self.database.transaction() as tx:
            folders = [_folder(row) for row in tx.fetch_all(
                f"""SELECT f.* FROM library_folders f
                    WHERE ((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id)
                           OR f.workspace_id = :workspace_id)
                      AND f.trashed_at IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM library_folders parent
                          WHERE parent.id = f.parent_id AND parent.trashed_at IS NOT NULL
                      )
                    ORDER BY f.trashed_at DESC, lower(f.name)""",
                parameters,
            )]
            files = [_file(row) for row in tx.fetch_all(
                f"""SELECT item.* FROM library_files item
                    WHERE ((:workspace_id IS NULL AND item.workspace_id IS NULL AND item.owner_id = :scope_id)
                           OR item.workspace_id = :workspace_id)
                      AND item.trashed_at IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM library_folders parent
                          WHERE parent.id = item.folder_id AND parent.trashed_at IS NOT NULL
                      )
                    ORDER BY item.trashed_at DESC, lower(item.name)""",
                parameters,
            )]
        return ([item for item in folders if item], [item for item in files if item])

    def restore_file(
        self, scope: str | LibraryScope, file_id: str, folder_id: str, name: str, restored_at: datetime
    ) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                f"""UPDATE library_files SET folder_id = :folder, name = :name,
                    trashed_at = NULL, updated_at = :updated
                    WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL""",
                {"id": file_id, "folder": folder_id, "name": name,
                 "updated": restored_at.isoformat(), **_scope_parameters(scope)},
            )

    def restore_folder_tree(
        self, scope: str | LibraryScope, folder_id: str, parent_id: str, name: str, restored_at: datetime
    ) -> None:
        parameters = {
            "id": folder_id, "parent": parent_id, "name": name,
            "updated": restored_at.isoformat(), **_scope_parameters(scope),
        }
        scope_sql = "((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id)"
        child_scope_sql = "((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id) OR f.workspace_id = :workspace_id)"
        with self.database.transaction() as tx:
            tx.execute(
                f"""UPDATE library_folders SET parent_id = :parent, name = :name,
                    trashed_at = NULL, updated_at = :updated
                    WHERE id = :id AND {scope_sql} AND trashed_at IS NOT NULL""", parameters,
            )
            tx.execute(
                f"""WITH RECURSIVE tree(id) AS (
                       SELECT id FROM library_folders WHERE id = :id AND {scope_sql}
                       UNION ALL SELECT f.id FROM library_folders f JOIN tree t ON f.parent_id = t.id
                       WHERE {child_scope_sql}
                   ) UPDATE library_folders SET trashed_at = NULL, updated_at = :updated
                     WHERE id IN (SELECT id FROM tree)""", parameters,
            )
            tx.execute(
                """WITH RECURSIVE tree(id) AS (
                       SELECT id FROM library_folders WHERE id = :id
                       UNION ALL SELECT f.id FROM library_folders f JOIN tree t ON f.parent_id = t.id
                   ) UPDATE library_files SET trashed_at = NULL, updated_at = :updated
                     WHERE folder_id IN (SELECT id FROM tree)
                       AND ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id)
                            OR workspace_id = :workspace_id)""", parameters,
            )
            tx.execute(
                """WITH RECURSIVE tree(id) AS (
                       SELECT id FROM library_folders WHERE id = :id
                       UNION ALL SELECT f.id FROM library_folders f JOIN tree t ON f.parent_id = t.id
                   ) UPDATE library_text_objects SET trashed_at = NULL, updated_at = :updated
                     WHERE folder_id IN (SELECT id FROM tree)
                       AND ((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id)
                            OR workspace_id = :workspace_id)""", parameters,
            )

    def permanently_delete_file(self, scope: str | LibraryScope, file_id: str) -> list[str] | None:
        with self.database.transaction() as tx:
            row = tx.fetch_one(
                f"SELECT id FROM library_files WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL",
                {"id": file_id, **_scope_parameters(scope)},
            )
            if row is None:
                return None
            objects = tx.fetch_all(
                """SELECT object_id FROM library_file_versions WHERE file_id = :id
                   UNION SELECT output_object_id AS object_id FROM library_derived_objects WHERE file_id = :id
                   UNION SELECT object_id FROM library_files WHERE id = :id""",
                {"id": file_id},
            )
            tx.execute("DELETE FROM library_share_grants WHERE file_id = :id", {"id": file_id})
            tx.execute("DELETE FROM library_derived_objects WHERE file_id = :id", {"id": file_id})
            tx.execute("DELETE FROM library_files WHERE id = :id", {"id": file_id})
            return [str(item["object_id"]) for item in objects]

    def permanently_delete_folder_tree(self, scope: str | LibraryScope, folder_id: str) -> list[str] | None:
        parameters = {"id": folder_id, **_scope_parameters(scope)}
        scope_sql = "((:workspace_id IS NULL AND workspace_id IS NULL AND owner_id = :scope_id) OR workspace_id = :workspace_id)"
        child_scope_sql = "((:workspace_id IS NULL AND f.workspace_id IS NULL AND f.owner_id = :scope_id) OR f.workspace_id = :workspace_id)"
        tree = f"""WITH RECURSIVE tree(id, depth) AS (
            SELECT id, 0 FROM library_folders WHERE id = :id AND {scope_sql} AND trashed_at IS NOT NULL
            UNION ALL SELECT f.id, t.depth + 1 FROM library_folders f JOIN tree t ON f.parent_id = t.id
            WHERE {child_scope_sql}
        )"""
        with self.database.transaction() as tx:
            if tx.fetch_one(
                f"SELECT id FROM library_folders WHERE id = :id AND {_SCOPE_SQL} AND trashed_at IS NOT NULL",
                parameters,
            ) is None:
                return None
            rows = tx.fetch_all(
                tree + """ SELECT object_id FROM library_files WHERE folder_id IN (SELECT id FROM tree)
                    UNION SELECT v.object_id FROM library_file_versions v JOIN library_files f ON f.id = v.file_id
                    WHERE f.folder_id IN (SELECT id FROM tree)
                    UNION SELECT d.output_object_id AS object_id FROM library_derived_objects d
                    JOIN library_files f ON f.id = d.file_id WHERE f.folder_id IN (SELECT id FROM tree)""",
                parameters,
            )
            folders = tx.fetch_all(tree + " SELECT id FROM tree ORDER BY depth DESC", parameters)
            tx.execute(
                tree + """ DELETE FROM library_share_grants WHERE file_id IN (
                    SELECT id FROM library_files WHERE folder_id IN (SELECT id FROM tree)
                )""", parameters,
            )
            tx.execute(
                tree + """ DELETE FROM library_derived_objects WHERE file_id IN (
                    SELECT id FROM library_files WHERE folder_id IN (SELECT id FROM tree)
                )""", parameters,
            )
            tx.execute(
                tree + """ DELETE FROM library_text_share_grants WHERE text_id IN (
                    SELECT id FROM library_text_objects WHERE folder_id IN (SELECT id FROM tree)
                )""", parameters,
            )
            tx.execute(tree + " DELETE FROM library_text_objects WHERE folder_id IN (SELECT id FROM tree)", parameters)
            tx.execute(tree + " DELETE FROM library_files WHERE folder_id IN (SELECT id FROM tree)", parameters)
            for folder in folders:
                tx.execute("DELETE FROM library_folders WHERE id = :id", {"id": folder["id"]})
            return [str(row["object_id"]) for row in rows]

    def expired_trash_scopes(self, cutoff: datetime) -> list[LibraryScope]:
        with self.database.transaction() as tx:
            rows = tx.fetch_all(
                """SELECT DISTINCT owner_id, workspace_id FROM (
                       SELECT owner_id, workspace_id FROM library_folders
                       WHERE trashed_at IS NOT NULL AND trashed_at <= :cutoff
                       UNION ALL
                       SELECT owner_id, workspace_id FROM library_files
                       WHERE trashed_at IS NOT NULL AND trashed_at <= :cutoff
                       UNION ALL
                       SELECT owner_id, workspace_id FROM library_text_objects
                       WHERE trashed_at IS NOT NULL AND trashed_at <= :cutoff
                   )""", {"cutoff": cutoff.isoformat()},
            )
        scopes = []
        for row in rows:
            workspace_id = row["workspace_id"]
            scopes.append(
                LibraryScope.workspace(str(workspace_id), str(row["owner_id"]))
                if workspace_id else LibraryScope.personal(str(row["owner_id"]))
            )
        return scopes

    def object_is_referenced(self, object_id: ObjectId) -> bool:
        with self.database.transaction() as tx:
            return bool(
                tx.fetch_one("SELECT 1 FROM library_files WHERE object_id = :id LIMIT 1", {"id": str(object_id)})
                or tx.fetch_one("SELECT 1 FROM library_file_versions WHERE object_id = :id LIMIT 1", {"id": str(object_id)})
                or tx.fetch_one("SELECT 1 FROM library_derived_objects WHERE output_object_id = :id LIMIT 1", {"id": str(object_id)})
                or tx.fetch_one("SELECT 1 FROM library_object_references WHERE object_id = :id LIMIT 1", {"id": str(object_id)})
            )

    def usage_bytes(self, scope: LibraryScope) -> int:
        """Logical usage counts each distinct object once per logical file."""
        with self.database.transaction() as tx:
            row = tx.fetch_one(
                f"""SELECT COALESCE(SUM(size), 0) AS total FROM (
                    SELECT file_id, object_id, MAX(size) AS size FROM (
                        SELECT v.file_id, v.object_id, v.size
                        FROM library_file_versions v JOIN library_files f ON f.id = v.file_id
                        WHERE {_FILE_SCOPE_SQL}
                        UNION ALL
                        SELECT d.file_id, d.output_object_id AS object_id, d.size
                        FROM library_derived_objects d JOIN library_files f ON f.id = d.file_id
                        WHERE {_FILE_SCOPE_SQL}
                    ) references_by_file GROUP BY file_id, object_id
                )""",
                _scope_parameters(scope),
            )
        return int(row["total"] if row else 0)

    def add_object_reference(self, object_id: ObjectId, kind: str, reference_id: str) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT OR IGNORE INTO library_object_references
                   (object_id, reference_kind, reference_id) VALUES (:object, :kind, :reference)""",
                {"object": str(object_id), "kind": kind, "reference": reference_id},
            )

    def remove_object_reference(self, object_id: ObjectId, kind: str, reference_id: str) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                """DELETE FROM library_object_references
                   WHERE object_id = :object AND reference_kind = :kind AND reference_id = :reference""",
                {"object": str(object_id), "kind": kind, "reference": reference_id},
            )

    def workspace_for_user(self, user_id: str) -> Workspace | None:
        with self.database.transaction() as tx:
            return _workspace(tx.fetch_one(
                """SELECT w.* FROM library_workspaces w
                   JOIN library_workspace_memberships m ON m.workspace_id = w.id
                   WHERE m.user_id = :user_id""",
                {"user_id": user_id},
            ))

    def workspace_for_member(self, workspace_id: str, user_id: str) -> Workspace | None:
        with self.database.transaction() as tx:
            return _workspace(tx.fetch_one(
                """SELECT w.* FROM library_workspaces w
                   JOIN library_workspace_memberships m ON m.workspace_id = w.id
                   WHERE w.id = :workspace_id AND m.user_id = :user_id""",
                {"workspace_id": workspace_id, "user_id": user_id},
            ))

    def create_workspace(self, workspace: Workspace, root: Folder, joined_at: datetime) -> None:
        """Atomically create the workspace, root, and sole initial membership."""
        with self.database.transaction() as tx:
            if tx.fetch_one(
                "SELECT 1 FROM library_workspace_memberships WHERE user_id = :user_id",
                {"user_id": workspace.owner_user_id},
            ):
                raise ValueError("This user already has a Workspace association.")
            tx.execute(
                """INSERT INTO library_workspaces
                   (id, name, owner_user_id, root_folder_id, created_at, updated_at)
                   VALUES (:id, :name, :owner, :root, :created, :updated)""",
                {"id": workspace.id, "name": workspace.name, "owner": workspace.owner_user_id,
                 "root": workspace.root_folder_id, "created": workspace.created_at.isoformat(),
                 "updated": workspace.updated_at.isoformat()},
            )
            tx.execute(
                """INSERT INTO library_folders
                   (id, owner_id, parent_id, name, is_root, created_at, updated_at,
                    trashed_at, workspace_id)
                   VALUES (:id, :owner, NULL, :name, 1, :created, :updated, NULL, :workspace)""",
                {"id": root.id, "owner": root.owner_id, "name": root.name,
                 "created": root.created_at.isoformat(), "updated": root.updated_at.isoformat(),
                 "workspace": workspace.id},
            )
            tx.execute(
                """INSERT INTO library_workspace_memberships(workspace_id, user_id, joined_at)
                   VALUES (:workspace, :user, :joined)""",
                {"workspace": workspace.id, "user": workspace.owner_user_id,
                 "joined": joined_at.isoformat()},
            )

    def add_workspace_member(self, workspace_id: str, email: str, joined_at: datetime) -> User | None:
        """Atomically associate one existing active user; user_id uniqueness is the policy lock."""
        with self.database.transaction() as tx:
            user = _user(tx.fetch_one(
                "SELECT * FROM library_users WHERE email = :email AND status = :active",
                {"email": email, "active": UserStatus.ACTIVE.value},
            ))
            if user is None:
                return None
            if tx.fetch_one(
                "SELECT 1 FROM library_workspace_memberships WHERE user_id = :user_id",
                {"user_id": user.id},
            ):
                raise ValueError("This user already has a Workspace association.")
            tx.execute(
                """INSERT INTO library_workspace_memberships(workspace_id, user_id, joined_at)
                   VALUES (:workspace, :user, :joined)""",
                {"workspace": workspace_id, "user": user.id, "joined": joined_at.isoformat()},
            )
            return user

    def workspace_members(self, workspace_id: str) -> list[User]:
        with self.database.transaction() as tx:
            return [user for row in tx.fetch_all(
                """SELECT u.* FROM library_users u
                   JOIN library_workspace_memberships m ON m.user_id = u.id
                   WHERE m.workspace_id = :workspace ORDER BY m.joined_at, u.id""",
                {"workspace": workspace_id},
            ) if (user := _user(row)) is not None]

    def leave_workspace(self, workspace_id: str, user_id: str, changed_at: datetime) -> str | None:
        """Remove membership, transferring ownership first when other members survive."""
        with self.database.transaction() as tx:
            workspace = _workspace(tx.fetch_one(
                "SELECT * FROM library_workspaces WHERE id = :id", {"id": workspace_id}
            ))
            if workspace is None or not tx.fetch_one(
                """SELECT 1 FROM library_workspace_memberships
                   WHERE workspace_id = :workspace AND user_id = :user""",
                {"workspace": workspace_id, "user": user_id},
            ):
                return None
            successor_id: str | None = None
            if workspace.owner_user_id == user_id:
                successor = tx.fetch_one(
                    """SELECT user_id FROM library_workspace_memberships
                       WHERE workspace_id = :workspace AND user_id != :user
                       ORDER BY joined_at, user_id LIMIT 1""",
                    {"workspace": workspace_id, "user": user_id},
                )
                if successor is None:
                    raise ValueError("A Workspace's sole owner cannot leave it.")
                successor_id = str(successor["user_id"])
                tx.execute(
                    """UPDATE library_workspaces SET owner_user_id = :owner, updated_at = :updated
                       WHERE id = :workspace""",
                    {"owner": successor_id, "updated": changed_at.isoformat(),
                     "workspace": workspace_id},
                )
            tx.execute(
                """DELETE FROM library_workspace_memberships
                   WHERE workspace_id = :workspace AND user_id = :user""",
                {"workspace": workspace_id, "user": user_id},
            )
            return successor_id or ""

    def remove_workspace_member(self, workspace_id: str, owner_id: str, user_id: str) -> bool:
        with self.database.transaction() as tx:
            workspace = tx.fetch_one(
                "SELECT owner_user_id FROM library_workspaces WHERE id = :id",
                {"id": workspace_id},
            )
            if workspace is None or str(workspace["owner_user_id"]) != owner_id:
                return False
            if user_id == owner_id:
                raise ValueError("The Workspace owner must leave to transfer ownership.")
            return bool(tx.execute(
                """DELETE FROM library_workspace_memberships
                   WHERE workspace_id = :workspace AND user_id = :user""",
                {"workspace": workspace_id, "user": user_id},
            ))


__all__ = ["LibraryRepository"]
