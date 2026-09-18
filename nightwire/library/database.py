"""Database boundary and versioned migrations for Community Library identity."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ContextManager, Protocol


class DatabaseTransaction(Protocol):
    def execute(self, statement: str, parameters: Mapping[str, Any] | None = None) -> int: ...
    def fetch_one(
        self, statement: str, parameters: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any] | None: ...
    def fetch_all(
        self, statement: str, parameters: Mapping[str, Any] | None = None
    ) -> Sequence[Mapping[str, Any]]: ...


class Database(Protocol):
    def transaction(self) -> ContextManager[DatabaseTransaction]: ...

    def migrate(self) -> None: ...


class _SQLiteTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def execute(self, statement: str, parameters: Mapping[str, Any] | None = None) -> int:
        cursor = self.connection.execute(statement, parameters or {})
        return cursor.rowcount

    def fetch_one(
        self, statement: str, parameters: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any] | None:
        return self.connection.execute(statement, parameters or {}).fetchone()

    def fetch_all(
        self, statement: str, parameters: Mapping[str, Any] | None = None
    ) -> Sequence[Mapping[str, Any]]:
        return self.connection.execute(statement, parameters or {}).fetchall()


_MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            """CREATE TABLE library_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                is_administrator INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                approved_at TEXT
            )""",
            """CREATE TABLE library_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (user_id) REFERENCES library_users(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX library_sessions_user_id_idx ON library_sessions(user_id)",
            "CREATE INDEX library_sessions_expires_at_idx ON library_sessions(expires_at)",
            """CREATE TABLE library_invitations (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                used_by_user_id TEXT,
                FOREIGN KEY (created_by_user_id) REFERENCES library_users(id) ON DELETE CASCADE,
                FOREIGN KEY (used_by_user_id) REFERENCES library_users(id) ON DELETE SET NULL
            )""",
            "CREATE INDEX library_invitations_email_idx ON library_invitations(email)",
        ),
    ),
    (
        2,
        (
            """CREATE TABLE library_folders (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                parent_id TEXT,
                name TEXT NOT NULL,
                is_root INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                trashed_at TEXT,
                FOREIGN KEY (owner_id) REFERENCES library_users(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES library_folders(id) ON DELETE RESTRICT
            )""",
            "CREATE UNIQUE INDEX library_folders_owner_root_idx ON library_folders(owner_id) WHERE is_root = 1",
            "CREATE INDEX library_folders_parent_idx ON library_folders(owner_id, parent_id, trashed_at)",
            """CREATE TABLE library_files (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                folder_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                content_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                trashed_at TEXT,
                FOREIGN KEY (owner_id) REFERENCES library_users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES library_folders(id) ON DELETE RESTRICT
            )""",
            "CREATE INDEX library_files_folder_idx ON library_files(owner_id, folder_id, trashed_at)",
            "CREATE INDEX library_files_object_idx ON library_files(object_id)",
        ),
    ),
    (
        3,
        (
            """CREATE TABLE library_workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner_user_id TEXT NOT NULL,
                root_folder_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (owner_user_id) REFERENCES library_users(id) ON DELETE RESTRICT
            )""",
            """CREATE TABLE library_workspace_memberships (
                workspace_id TEXT NOT NULL,
                user_id TEXT NOT NULL UNIQUE,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (workspace_id, user_id),
                FOREIGN KEY (workspace_id) REFERENCES library_workspaces(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES library_users(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX library_workspace_memberships_workspace_idx ON library_workspace_memberships(workspace_id, joined_at)",
            "ALTER TABLE library_folders ADD COLUMN workspace_id TEXT",
            "ALTER TABLE library_files ADD COLUMN workspace_id TEXT",
            "DROP INDEX library_folders_owner_root_idx",
            "CREATE UNIQUE INDEX library_folders_owner_root_idx ON library_folders(owner_id) WHERE is_root = 1 AND workspace_id IS NULL",
            "CREATE UNIQUE INDEX library_folders_workspace_root_idx ON library_folders(workspace_id) WHERE is_root = 1 AND workspace_id IS NOT NULL",
            "CREATE INDEX library_folders_workspace_parent_idx ON library_folders(workspace_id, parent_id, trashed_at)",
            "CREATE INDEX library_files_workspace_folder_idx ON library_files(workspace_id, folder_id, trashed_at)",
        ),
    ),
    (
        4,
        (
            "CREATE INDEX library_folders_trash_idx ON library_folders(workspace_id, owner_id, trashed_at)",
            "CREATE INDEX library_files_trash_idx ON library_files(workspace_id, owner_id, trashed_at)",
            """CREATE TABLE library_object_references (
                object_id TEXT NOT NULL,
                reference_kind TEXT NOT NULL,
                reference_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (object_id, reference_kind, reference_id)
            )""",
            "CREATE INDEX library_object_references_object_idx ON library_object_references(object_id)",
        ),
    ),
    (
        5,
        (
            """CREATE TABLE library_file_versions (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                object_id TEXT NOT NULL,
                size INTEGER NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                content_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT,
                UNIQUE (file_id, version_number),
                FOREIGN KEY (file_id) REFERENCES library_files(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX library_file_versions_file_idx ON library_file_versions(file_id, version_number DESC)",
            "CREATE INDEX library_file_versions_object_idx ON library_file_versions(object_id)",
            """INSERT INTO library_file_versions
               (id, file_id, version_number, object_id, size, checksum_sha256,
                content_type, created_at, created_by_user_id, source_kind, source_id)
               SELECT 'legacy-' || id, id, 1, object_id, size, checksum_sha256,
                      content_type, created_at, owner_id, 'upload', NULL
               FROM library_files""",
            """CREATE TABLE library_derived_objects (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                source_version_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                output_object_id TEXT NOT NULL,
                size INTEGER NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                content_type TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                promoted_version_id TEXT,
                FOREIGN KEY (file_id) REFERENCES library_files(id) ON DELETE CASCADE,
                FOREIGN KEY (source_version_id) REFERENCES library_file_versions(id) ON DELETE RESTRICT,
                FOREIGN KEY (promoted_version_id) REFERENCES library_file_versions(id) ON DELETE RESTRICT
            )""",
            "CREATE INDEX library_derived_objects_file_idx ON library_derived_objects(file_id, created_at DESC)",
            "CREATE INDEX library_derived_objects_output_idx ON library_derived_objects(output_object_id)",
        ),
    ),
    (
        6,
        (
            """CREATE TABLE library_share_grants (
                id TEXT PRIMARY KEY,
                public_token TEXT NOT NULL UNIQUE,
                file_id TEXT NOT NULL,
                source_version_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked_at TEXT,
                access_key_algorithm TEXT,
                access_key_salt TEXT,
                access_key_digest TEXT,
                workspace_id TEXT,
                FOREIGN KEY (file_id) REFERENCES library_files(id) ON DELETE CASCADE,
                FOREIGN KEY (source_version_id) REFERENCES library_file_versions(id) ON DELETE RESTRICT
            )""",
            "CREATE INDEX library_share_grants_file_idx ON library_share_grants(file_id, created_at DESC)",
            "CREATE INDEX library_share_grants_creator_idx ON library_share_grants(created_by_user_id, created_at DESC)",
            "CREATE INDEX library_share_grants_expiry_idx ON library_share_grants(expires_at, revoked_at)",
        ),
    ),
    (
        7,
        (
            """CREATE TABLE library_text_objects (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                folder_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                mode TEXT NOT NULL,
                language TEXT,
                source_kind TEXT,
                source_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                trashed_at TEXT,
                workspace_id TEXT,
                FOREIGN KEY (owner_id) REFERENCES library_users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES library_folders(id) ON DELETE RESTRICT
            )""",
            "CREATE INDEX library_text_folder_idx ON library_text_objects(owner_id, folder_id, trashed_at)",
            "CREATE INDEX library_text_workspace_folder_idx ON library_text_objects(workspace_id, folder_id, trashed_at)",
            "CREATE INDEX library_text_trash_idx ON library_text_objects(workspace_id, owner_id, trashed_at)",
            """CREATE TABLE library_text_share_grants (
                id TEXT PRIMARY KEY,
                public_token TEXT NOT NULL UNIQUE,
                text_id TEXT NOT NULL,
                source_title TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked_at TEXT,
                access_key_algorithm TEXT,
                access_key_salt TEXT,
                access_key_digest TEXT,
                workspace_id TEXT,
                FOREIGN KEY (text_id) REFERENCES library_text_objects(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX library_text_share_text_idx ON library_text_share_grants(text_id, created_at DESC)",
            "CREATE INDEX library_text_share_creator_idx ON library_text_share_grants(created_by_user_id, created_at DESC)",
            "CREATE INDEX library_text_share_expiry_idx ON library_text_share_grants(expires_at, revoked_at)",
        ),
    ),
)


class SQLiteDatabase:
    """SQLite adapter; Library repositories depend only on ``Database`` above."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._memory_connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self.path == ":memory:" and self._memory_connection is not None:
            return self._memory_connection
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if self.path == ":memory:":
            self._memory_connection = connection
        return connection

    @contextmanager
    def transaction(self) -> Iterator[DatabaseTransaction]:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN")
                yield _SQLiteTransaction(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if self.path != ":memory:":
                    connection.close()

    def migrate(self) -> None:
        with self.transaction() as transaction:
            transaction.execute(
                """CREATE TABLE IF NOT EXISTS library_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            rows = transaction.fetch_all("SELECT version FROM library_schema_migrations")
            applied = {int(row["version"]) for row in rows}
            for version, statements in _MIGRATIONS:
                if version in applied:
                    continue
                for statement in statements:
                    transaction.execute(statement)
                transaction.execute(
                    "INSERT INTO library_schema_migrations(version) VALUES (:version)",
                    {"version": version},
                )


def database_from_url(database_url: str) -> Database:
    """Create a database adapter from a configured URL.

    SQLite ships as the zero-dependency default. Additional adapters can satisfy
    the same protocol without changing repositories or authentication services.
    """

    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        scheme = database_url.split(":", 1)[0] or "unknown"
        raise ValueError(
            f"Unsupported NIGHTWIRE_DATABASE_URL scheme {scheme!r}; this build includes sqlite."
        )
    raw_path = database_url[len(prefix) :]
    if raw_path == ":memory:":
        return SQLiteDatabase(":memory:")
    if not raw_path:
        raise ValueError("SQLite database URL must include a path.")
    path = Path("/" + raw_path) if database_url.startswith("sqlite:////") else Path(raw_path)
    return SQLiteDatabase(path.expanduser().resolve())


__all__ = ["Database", "DatabaseTransaction", "SQLiteDatabase", "database_from_url"]
