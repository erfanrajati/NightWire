"""Community Library route and lifecycle registration."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import qrcode
import qrcode.image.svg

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from nightwire.app.registration import ApplicationRegistry, ModuleContext
from nightwire.core.config import DeploymentProfile
from nightwire.core.references import ObjectReferenceChecker
from nightwire.core.storage import LocalFilesystemStorage, ObjectId, StorageBackend
from nightwire.core.transfer import CoreTransferService, TransferService
from nightwire.core.capacity import CapacityExceededError, CommunityCapacityManager, UsageScope
from nightwire.library.auth import AuthenticationError, LibraryAuthService
from nightwire.library.database import Database, database_from_url
from nightwire.library.domain import LibraryScope, User
from nightwire.library.previews import CommunityPreviewService, PreviewDecision
from nightwire.library.repository import LibraryRepository
from nightwire.library.service import DuplicateWarningError, LibraryOperationError, PersonalLibraryService
from nightwire.library.shares import LibraryShareService, ShareAccessError
from nightwire.library.trash import TrashService
from nightwire.library.texts import LibraryTextService
from nightwire.library.workspaces import CommunityWorkspacePolicy, WorkspaceService


SESSION_COOKIE = "nightwire_library_session"
TEXT_EDITOR_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; object-src 'none'; frame-src 'none'; "
    "base-uri 'none'; form-action 'self'"
)
FILE_DETAIL_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
    "style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; "
    "frame-src 'self'; base-uri 'none'; form-action 'self'"
)
PREVIEW_RESOURCE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Content-Disposition": 'inline; filename="nightwire-preview"',
    "Content-Security-Policy": "sandbox; default-src 'none'; script-src 'none'; object-src 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
}


class LibraryModule:
    """Own Library identity routes without changing anonymous Drop access."""

    name = "library"

    def __init__(
        self,
        database: Database | None = None,
        storage: StorageBackend | None = None,
        transfer: TransferService | None = None,
    ) -> None:
        self.database = database
        self.storage = storage
        self.transfer = transfer
        self.auth: LibraryAuthService | None = None
        self.library: PersonalLibraryService | None = None
        self.workspaces: WorkspaceService | None = None
        self.trash: TrashService | None = None
        self.shares: LibraryShareService | None = None
        self.texts: LibraryTextService | None = None
        self.previews: CommunityPreviewService | None = None
        self.capacity: CommunityCapacityManager | None = None
        self.static_dir: Path | None = None
        self.secure_cookies = False

    def register(self, registry: ApplicationRegistry, context: ModuleContext) -> None:
        self.database = self.database or database_from_url(context.settings.database_url)
        self.static_dir = context.settings.static_dir
        self.secure_cookies = (
            context.settings.deployment_profile is DeploymentProfile.INTERNET_FACING
        )
        repository = LibraryRepository(self.database)
        self.storage = self.storage or LocalFilesystemStorage(context.settings.files_dir)
        self.transfer = self.transfer or CoreTransferService(self.storage)
        capacity_factory = context.handlers.get("capacity_manager")
        capacity = capacity_factory() if capacity_factory else CommunityCapacityManager(
            context.settings.files_dir,
            installation_limit=context.settings.installation_max_bytes,
            personal_limit=context.settings.personal_library_quota_bytes,
            workspace_limit=context.settings.workspace_quota_bytes,
            drop_limit=context.settings.drop_quota_bytes,
            object_limit=context.settings.maximum_object_bytes,
            minimum_free=context.settings.minimum_host_free_bytes,
        )
        if capacity_factory is None:
            capacity.add_usage_source(
                lambda scope: sum(path.stat().st_size for path in self.storage.objects_root.iterdir()
                                  if path.is_file()) if scope.kind == "installation" else 0
            )
        self.capacity = capacity
        if isinstance(self.transfer, CoreTransferService):
            self.transfer.set_capacity_manager(capacity)
        capacity.add_usage_source(
            lambda scope: repository.usage_bytes(
                LibraryScope.workspace(scope.id, scope.id)
                if scope.kind == "workspace" else LibraryScope.personal(scope.id)
            ) if scope.kind in {"personal", "workspace"} else 0
        )
        self.auth = LibraryAuthService(
            repository,
            context.settings.library_registration_policy,
            session_ttl_seconds=context.settings.library_session_ttl_seconds,
            password_min_characters=context.settings.library_password_min_characters,
            password_max_characters=context.settings.password_max_characters,
        )
        references = ObjectReferenceChecker([repository.object_is_referenced])
        external_references = context.handlers.get("object_is_referenced")
        if external_references is not None:
            references.add_source(external_references)
        self.library = PersonalLibraryService(
            repository, self.transfer, self.storage,
            version_retention=context.settings.library_version_retention,
            references=references,
        )
        self.workspaces = WorkspaceService(repository, self.library, CommunityWorkspacePolicy())
        self.shares = LibraryShareService(repository, self.library, self.storage)
        self.texts = LibraryTextService(repository, self.library)
        self.previews = CommunityPreviewService(self.storage)
        self.trash = TrashService(
            repository, self.library, self.storage, references,
            context.settings.library_trash_retention_seconds,
        )
        registry.set_state("library_auth", self.auth)
        registry.set_state("personal_library", self.library)
        registry.set_state("workspace_service", self.workspaces)
        registry.set_state("library_trash", self.trash)
        registry.set_state("library_shares", self.shares)
        registry.set_state("library_texts", self.texts)
        registry.set_state("library_previews", self.previews)
        registry.set_state("library_database", self.database)
        registry.set_state("capacity_manager", capacity)
        registry.add_startup_hook(self.database.migrate)
        registry.add_startup_hook(self.trash.start_cleanup)
        registry.add_shutdown_hook(self.trash.stop_cleanup)

        registry.add_route("/library", self.library_page, methods=["GET"])
        registry.add_route("/library/files/{file_id:str}", self.file_detail_page, methods=["GET"])
        registry.add_route("/library/texts/{text_id:str}", self.text_editor_page, methods=["GET"])
        registry.add_route("/workspaces", self.workspace_page, methods=["GET"])
        registry.add_route(
            "/workspaces/{workspace_id:str}/files/{file_id:str}",
            self.file_detail_page,
            methods=["GET"],
        )
        registry.add_route(
            "/workspaces/{workspace_id:str}/texts/{text_id:str}",
            self.text_editor_page,
            methods=["GET"],
        )
        registry.add_route("/library/trash", self.trash_page, methods=["GET"])
        registry.add_route("/library/shares", self.shares_page, methods=["GET"])
        registry.add_route("/workspaces/trash", self.trash_page, methods=["GET"])
        registry.add_route("/library/login", self.auth_page, methods=["GET"])
        registry.add_route("/library/signup", self.auth_page, methods=["GET"])
        registry.add_route("/library/assets/auth.js", self.auth_script, methods=["GET"])
        registry.add_route("/library/assets/auth.css", self.auth_styles, methods=["GET"])
        registry.add_route("/library/assets/browser.js", self.browser_script, methods=["GET"])
        registry.add_route("/library/assets/browser.css", self.browser_styles, methods=["GET"])
        registry.add_route("/library/assets/text-ui.js", self.text_ui_script, methods=["GET"])
        registry.add_route("/library/assets/text-editor.js", self.text_editor_script, methods=["GET"])
        registry.add_route("/library/assets/text-editor.css", self.text_editor_styles, methods=["GET"])
        registry.add_route("/library/assets/file-detail.js", self.file_detail_script, methods=["GET"])
        registry.add_route("/library/assets/file-detail.css", self.file_detail_styles, methods=["GET"])
        registry.add_route("/library/assets/trash.js", self.trash_script, methods=["GET"])
        registry.add_route("/library/assets/shares.js", self.shares_script, methods=["GET"])
        registry.add_route("/library/assets/share-recipient.js", self.share_recipient_script, methods=["GET"])
        registry.add_route("/library/assets/shell.css", self.shell_styles, methods=["GET"])
        registry.add_route("/api/library", self.library_api, methods=["GET"])
        registry.add_route("/api/library/usage", self.personal_usage, methods=["GET"])
        registry.add_route("/api/library/search", self.search, methods=["GET"])
        registry.add_route("/api/library/folders", self.folders, methods=["GET", "POST"])
        registry.add_route("/api/library/tree", self.tree, methods=["GET"])
        registry.add_route("/api/library/folders/{folder_id:str}", self.folder, methods=["GET", "PATCH", "DELETE"])
        registry.add_route("/api/library/folders/{folder_id:str}/upload", self.upload_file, methods=["PUT"])
        registry.add_route("/api/library/folders/{folder_id:str}/texts", self.personal_texts, methods=["POST"])
        registry.add_route("/api/library/folders/{folder_id:str}/copy", self.copy_folder, methods=["POST"])
        registry.add_route("/api/library/folders/{folder_id:str}/duplicate", self.duplicate_folder, methods=["POST"])
        registry.add_route("/api/library/files/{file_id:str}", self.file, methods=["GET", "PATCH", "DELETE"])
        registry.add_route("/api/library/files/{file_id:str}/preview", self.preview_file, methods=["GET"])
        registry.add_route("/api/library/files/{file_id:str}/download", self.download_file, methods=["GET"])
        registry.add_route("/api/library/files/{file_id:str}/versions", self.file_versions, methods=["GET", "PUT"])
        registry.add_route("/api/library/files/{file_id:str}/versions/{version_id:str}/download", self.download_version, methods=["GET"])
        registry.add_route("/api/library/files/{file_id:str}/versions/{version_id:str}/restore", self.restore_version, methods=["POST"])
        registry.add_route("/api/library/files/{file_id:str}/derived-outputs", self.derived_outputs, methods=["GET", "PUT"])
        registry.add_route("/api/library/files/{file_id:str}/derived-outputs/{derived_id:str}/promote", self.promote_derived, methods=["POST"])
        registry.add_route("/api/library/files/{file_id:str}/shares", self.file_shares, methods=["GET", "POST"])
        registry.add_route("/api/library/files/{file_id:str}/copy", self.copy_file, methods=["POST"])
        registry.add_route("/api/library/files/{file_id:str}/duplicate", self.duplicate_file, methods=["POST"])
        registry.add_route("/api/library/texts", self.personal_texts, methods=["POST"])
        registry.add_route("/api/library/texts/{text_id:str}", self.personal_text, methods=["GET", "PATCH", "DELETE"])
        registry.add_route("/api/library/texts/{text_id:str}/shares", self.personal_text_shares, methods=["GET", "POST"])
        registry.add_route("/api/library/trash", self.personal_trash, methods=["GET"])
        registry.add_route("/api/library/trash/files/{file_id:str}/restore", self.restore_personal_file, methods=["POST"])
        registry.add_route("/api/library/trash/files/{file_id:str}", self.delete_personal_file, methods=["DELETE"])
        registry.add_route("/api/library/trash/folders/{folder_id:str}/restore", self.restore_personal_folder, methods=["POST"])
        registry.add_route("/api/library/trash/folders/{folder_id:str}", self.delete_personal_folder, methods=["DELETE"])
        registry.add_route("/api/library/trash/texts/{text_id:str}/restore", self.restore_personal_text, methods=["POST"])
        registry.add_route("/api/library/trash/texts/{text_id:str}", self.delete_personal_text, methods=["DELETE"])
        registry.add_route("/api/library/shares", self.share_collection, methods=["GET"])
        registry.add_route("/api/library/shares/{share_id:str}", self.revoke_share, methods=["DELETE"])
        registry.add_route("/api/workspaces", self.workspace_collection, methods=["GET", "POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}", self.workspace_detail, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/usage", self.workspace_usage, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/members", self.workspace_members, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/members/me", self.leave_workspace, methods=["DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/members/{member_id:str}", self.remove_workspace_member, methods=["DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/folders", self.workspace_folders, methods=["GET", "POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/tree", self.workspace_tree, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}", self.workspace_folder, methods=["GET", "PATCH", "DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/upload", self.workspace_upload, methods=["PUT"])
        registry.add_route("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/texts", self.workspace_texts, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/copy", self.workspace_copy_folder, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/duplicate", self.workspace_duplicate_folder, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}", self.workspace_file, methods=["GET", "PATCH", "DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/preview", self.workspace_preview, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/download", self.workspace_download, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/versions", self.workspace_file_versions, methods=["GET", "PUT"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/versions/{version_id:str}/download", self.workspace_download_version, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/versions/{version_id:str}/restore", self.workspace_restore_version, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/derived-outputs", self.workspace_derived_outputs, methods=["GET", "PUT"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/derived-outputs/{derived_id:str}/promote", self.workspace_promote_derived, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/shares", self.workspace_file_shares, methods=["GET", "POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/copy", self.workspace_copy_file, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/files/{file_id:str}/duplicate", self.workspace_duplicate_file, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/texts", self.workspace_texts, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/texts/{text_id:str}", self.workspace_text, methods=["GET", "PATCH", "DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/texts/{text_id:str}/shares", self.workspace_text_shares, methods=["GET", "POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash", self.workspace_trash, methods=["GET"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash/files/{file_id:str}/restore", self.restore_workspace_file, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash/files/{file_id:str}", self.delete_workspace_file, methods=["DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash/folders/{folder_id:str}/restore", self.restore_workspace_folder, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash/folders/{folder_id:str}", self.delete_workspace_folder, methods=["DELETE"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash/texts/{text_id:str}/restore", self.restore_workspace_text, methods=["POST"])
        registry.add_route("/api/workspaces/{workspace_id:str}/trash/texts/{text_id:str}", self.delete_workspace_text, methods=["DELETE"])
        registry.add_route("/api/library/auth/config", self.auth_config, methods=["GET"])
        registry.add_route("/api/library/auth/register", self.register_user, methods=["POST"])
        registry.add_route("/api/library/auth/login", self.login, methods=["POST"])
        registry.add_route("/api/library/auth/logout", self.logout, methods=["POST"])
        registry.add_route("/api/library/auth/me", self.current_identity, methods=["GET"])
        registry.add_route(
            "/api/library/admin/invitations", self.create_invitation, methods=["POST"]
        )
        registry.add_route(
            "/api/library/admin/pending-users", self.pending_users, methods=["GET"]
        )
        registry.add_route(
            "/api/library/admin/pending-users/{user_id:str}/approve",
            self.approve_user,
            methods=["POST"],
        )
        registry.add_route(
            "/api/library/admin/pending-users/{user_id:str}/reject",
            self.reject_user,
            methods=["POST"],
        )
        registry.add_route("/s/{share_token:str}", self.public_share_page, methods=["GET"])
        registry.add_route("/api/public/shares/{share_token:str}", self.public_share_info, methods=["GET"])
        registry.add_route("/api/public/shares/{share_token:str}/preview", self.public_share_preview, methods=["GET"])
        registry.add_route("/api/public/shares/{share_token:str}/download", self.public_share_download, methods=["GET"])
        registry.add_route("/api/public/shares/{share_token:str}/qr", self.public_share_qr, methods=["GET"])

    def _service(self) -> LibraryAuthService:
        if self.auth is None:
            raise RuntimeError("Library module is not registered.")
        return self.auth

    def _library(self) -> PersonalLibraryService:
        if self.library is None:
            raise RuntimeError("Library module is not registered.")
        return self.library

    def _workspaces(self) -> WorkspaceService:
        if self.workspaces is None:
            raise RuntimeError("Library module is not registered.")
        return self.workspaces

    def _trash(self) -> TrashService:
        if self.trash is None:
            raise RuntimeError("Library module is not registered.")
        return self.trash

    def _shares(self) -> LibraryShareService:
        if self.shares is None:
            raise RuntimeError("Library module is not registered.")
        return self.shares

    def _texts(self) -> LibraryTextService:
        if self.texts is None:
            raise RuntimeError("Library module is not registered.")
        return self.texts

    def _previews(self) -> CommunityPreviewService:
        if self.previews is None:
            raise RuntimeError("Library module is not registered.")
        return self.previews

    def _asset(self, filename: str) -> Path:
        if self.static_dir is None:
            raise RuntimeError("Library module is not registered.")
        return self.static_dir / filename

    async def _payload(self, request: Request, *, maximum_bytes: int = 16_384) -> dict[str, Any]:
        content_length = request.headers.get("content-length", "0")
        if content_length.isdigit() and int(content_length) > maximum_bytes:
            raise AuthenticationError("Request payload is too large.", 413)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise AuthenticationError("A valid JSON payload is required.") from exc
        if not isinstance(payload, dict):
            raise AuthenticationError("A valid JSON payload is required.")
        return payload

    def _user(self, request: Request) -> User | None:
        return self._service().current_user(request.cookies.get(SESSION_COOKIE))

    def _require_user(self, request: Request) -> User:
        user = self._user(request)
        if user is None:
            raise AuthenticationError("Library authentication is required.", 401)
        return user

    @staticmethod
    def _error(exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            {"error": str(exc)}, status_code=exc.status_code, headers={"Cache-Control": "no-store"}
        )

    def _set_session_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=self._service().session_ttl_seconds,
            httponly=True,
            secure=self.secure_cookies,
            samesite="strict",
            path="/",
        )

    async def auth_page(self, _: Request) -> Response:
        path = self._asset("library-auth.html")
        if not path.is_file():
            return JSONResponse({"error": "Library frontend assets are missing."}, status_code=500)
        return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})

    async def auth_script(self, _: Request) -> Response:
        return FileResponse(
            self._asset("library-auth.js"),
            media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def auth_styles(self, _: Request) -> Response:
        return FileResponse(
            self._asset("library-auth.css"),
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    async def browser_script(self, _: Request) -> Response:
        return FileResponse(self._asset("library-browser.js"), media_type="text/javascript")

    async def browser_styles(self, _: Request) -> Response:
        return FileResponse(self._asset("library-browser.css"), media_type="text/css")

    async def text_ui_script(self, _: Request) -> Response:
        return FileResponse(
            self._asset("text-ui.js"), media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def text_editor_script(self, _: Request) -> Response:
        return FileResponse(
            self._asset("text-editor.js"), media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def text_editor_styles(self, _: Request) -> Response:
        return FileResponse(
            self._asset("text-editor.css"), media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    async def file_detail_script(self, _: Request) -> Response:
        return FileResponse(
            self._asset("file-detail.js"), media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def file_detail_styles(self, _: Request) -> Response:
        return FileResponse(
            self._asset("file-detail.css"), media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    async def trash_script(self, _: Request) -> Response:
        return FileResponse(self._asset("library-trash.js"), media_type="text/javascript")

    async def shares_script(self, _: Request) -> Response:
        return FileResponse(self._asset("library-shares.js"), media_type="text/javascript")

    async def share_recipient_script(self, _: Request) -> Response:
        return FileResponse(self._asset("library-share.js"), media_type="text/javascript")

    async def shell_styles(self, _: Request) -> Response:
        return FileResponse(
            self._asset("styles.css"),
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    async def library_page(self, request: Request) -> Response:
        if self._user(request) is None:
            return RedirectResponse("/library/login", status_code=303)
        path = self._asset("library-browser.html")
        if not path.is_file():
            return JSONResponse({"error": "Library frontend assets are missing."}, status_code=500)
        return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})

    async def text_editor_page(self, request: Request) -> Response:
        try:
            if request.path_params.get("workspace_id"):
                self._workspace_context(request)
            else:
                self._require_user(request)
        except (AuthenticationError, LibraryOperationError):
            return RedirectResponse("/library/login", status_code=303)
        path = self._asset("text-editor.html")
        if not path.is_file():
            return JSONResponse({"error": "Text editor assets are missing."}, status_code=500)
        return HTMLResponse(
            path.read_text(encoding="utf-8"), media_type="text/html",
            headers={"Cache-Control": "no-store", "Content-Security-Policy": TEXT_EDITOR_CSP},
        )

    async def file_detail_page(self, request: Request) -> Response:
        try:
            if request.path_params.get("workspace_id"):
                self._workspace_context(request)
            else:
                self._require_user(request)
        except (AuthenticationError, LibraryOperationError):
            return RedirectResponse("/library/login", status_code=303)
        path = self._asset("file-detail.html")
        if not path.is_file():
            return JSONResponse({"error": "File detail assets are missing."}, status_code=500)
        return HTMLResponse(
            path.read_text(encoding="utf-8"), media_type="text/html",
            headers={"Cache-Control": "no-store", "Content-Security-Policy": FILE_DETAIL_CSP},
        )

    async def workspace_page(self, request: Request) -> Response:
        if self._user(request) is None:
            return RedirectResponse("/library/login", status_code=303)
        path = self._asset("workspace-browser.html")
        if not path.is_file():
            return JSONResponse({"error": "Workspace frontend assets are missing."}, status_code=500)
        return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})

    async def trash_page(self, request: Request) -> Response:
        if self._user(request) is None:
            return RedirectResponse("/library/login", status_code=303)
        return FileResponse(
            self._asset("library-trash.html"), media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    async def shares_page(self, request: Request) -> Response:
        if self._user(request) is None:
            return RedirectResponse("/library/login", status_code=303)
        return FileResponse(
            self._asset("library-shares.html"), media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    async def auth_config(self, _: Request) -> JSONResponse:
        service = self._service()
        return JSONResponse(
            {
                "registration_policy": service.registration_policy.value,
                "password_min_characters": service.password_min_characters,
                "first_account": service.repository.user_count() == 0,
            },
            headers={"Cache-Control": "no-store"},
        )

    async def register_user(self, request: Request) -> JSONResponse:
        try:
            payload = await self._payload(request)
            result = self._service().register(
                email=payload.get("email"),
                display_name=payload.get("display_name"),
                password=payload.get("password"),
                invitation_token=payload.get("invitation_token"),
            )
            self._library().root(result.user)
        except AuthenticationError as exc:
            return self._error(exc)
        active = result.session_token is not None
        response = JSONResponse(
            {"user": result.user.public_dict(), "authenticated": active},
            status_code=201 if active else 202,
            headers={"Cache-Control": "no-store"},
        )
        if result.session_token:
            self._set_session_cookie(response, result.session_token)
        return response

    async def login(self, request: Request) -> JSONResponse:
        try:
            payload = await self._payload(request)
            result = self._service().login(payload.get("email"), payload.get("password"))
        except AuthenticationError as exc:
            return self._error(exc)
        response = JSONResponse(
            {"user": result.user.public_dict()}, headers={"Cache-Control": "no-store"}
        )
        self._set_session_cookie(response, result.session_token)
        return response

    async def logout(self, request: Request) -> Response:
        self._service().logout(request.cookies.get(SESSION_COOKIE))
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(SESSION_COOKIE, path="/", secure=self.secure_cookies, samesite="strict")
        return response

    async def current_identity(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._error(exc)
        return JSONResponse({"user": user.public_dict()}, headers={"Cache-Control": "no-store"})

    async def library_api(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            listing = self._library().list_folder(user, request.query_params.get("folder_id"))
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return JSONResponse({"user": user.public_dict(), **listing}, headers={"Cache-Control": "no-store"})

    async def personal_usage(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            usage = self.capacity.report(UsageScope("personal", user.id))
            return JSONResponse({"scope": "personal", **usage,
                                 "installation": self.capacity.installation_report()},
                                headers={"Cache-Control": "no-store"})
        except AuthenticationError as exc:
            return self._operation_error(exc)

    @staticmethod
    def _operation_error(exc: AuthenticationError | LibraryOperationError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code,
                            headers={"Cache-Control": "no-store"})

    @staticmethod
    def _duplicate_warning(exc: DuplicateWarningError) -> JSONResponse:
        return JSONResponse(
            {"error": str(exc), "code": "duplicate_warning", "warnings": exc.warnings,
             "confirmation": {"parameter": "confirm_duplicates", "value": "true"}},
            status_code=409, headers={"Cache-Control": "no-store"},
        )

    async def search(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            selected = request.query_params.get("scope", "global")
            if selected not in {"personal", "workspace", "global"}:
                raise LibraryOperationError("Search scope must be personal, workspace, or global.")
            query = request.query_params.get("q", "")
            personal = LibraryScope.personal(user.id)
            workspace = self._workspaces().current(user)
            available = [{"filter": "personal", "kind": "personal", "id": user.id,
                          "name": "My Library"}]
            targets: list[tuple[LibraryScope, str, str]] = []
            if selected in {"personal", "global"}:
                targets.append((personal, "personal", "My Library"))
            if workspace is not None:
                available.append({"filter": "workspace", "kind": "workspace",
                                  "id": workspace.id, "name": workspace.name})
                if selected in {"workspace", "global"}:
                    targets.append((LibraryScope.workspace(workspace.id, user.id),
                                    "workspace", workspace.name))
            results = [
                result
                for scope, scope_name, label in targets
                for result in self._library().search(
                    scope, query, scope_name=scope_name, scope_label=label, limit=100
                )
            ]
            results.sort(key=lambda item: (-float(item["score"]), str(item["name"]).casefold(),
                                           str(item["path"]).casefold()))
            return JSONResponse(
                {"query": query, "scope": selected, "available_scopes": available,
                 "results": results[:50]}, headers={"Cache-Control": "no-store"},
            )
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    @staticmethod
    def _share_status(grant) -> str:
        if grant.revoked_at is not None:
            return "revoked"
        if grant.expires_at is not None and grant.expires_at <= datetime.now(timezone.utc):
            return "expired"
        return "active"

    def _share_record(self, request: Request, grant, access_key: str | None = None) -> dict[str, object]:
        root = str(request.base_url).rstrip("/")
        base_url = f"{root}/s/{quote(grant.public_token, safe='')}"
        share_url = base_url
        if grant.access_key_required:
            share_url = f"{base_url}?key={quote(access_key, safe='')}" if access_key else None
        qr_url = None
        if share_url is not None:
            key_query = f"?key={quote(access_key, safe='')}" if access_key else ""
            qr_url = f"{root}/api/public/shares/{quote(grant.public_token, safe='')}/qr{key_query}"
        return grant.public_dict() | {
            "status": self._share_status(grant), "share_url": share_url,
            "qr_url": qr_url,
        }

    async def _file_shares(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            file_id = request.path_params["file_id"]
            if request.method == "GET":
                grants = self._shares().list_for_file(principal, file_id)
                return JSONResponse(
                    {"shares": [self._share_record(request, grant) for grant in grants]},
                    headers={"Cache-Control": "no-store"},
                )
            payload = await self._payload(request)
            created = self._shares().create(
                principal, file_id,
                expires_in_seconds=payload.get("expires_in_seconds"),
                access_key_protected=payload.get("access_key_protected", False),
            )
            return JSONResponse(
                {"share": self._share_record(request, created.grant, created.access_key),
                 "access_key": created.access_key},
                status_code=201, headers={"Cache-Control": "no-store"},
            )
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def file_shares(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._file_shares(request, user)

    async def workspace_file_shares(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._file_shares(request, scope)

    async def _text_shares(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            text_id = request.path_params["text_id"]
            if request.method == "GET":
                grants = self._shares().list_for_text(principal, text_id)
                return JSONResponse(
                    {"shares": [self._share_record(request, grant) for grant in grants]},
                    headers={"Cache-Control": "no-store"},
                )
            payload = await self._payload(request)
            created = self._shares().create_text(
                principal, text_id,
                expires_in_seconds=payload.get("expires_in_seconds"),
                access_key_protected=payload.get("access_key_protected", False),
            )
            return JSONResponse(
                {"share": self._share_record(request, created.grant, created.access_key),
                 "access_key": created.access_key},
                status_code=201, headers={"Cache-Control": "no-store"},
            )
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def personal_text_shares(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._text_shares(request, user)

    async def workspace_text_shares(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._text_shares(request, scope)

    async def _create_text(self, request: Request, principal: User | LibraryScope) -> JSONResponse:
        try:
            payload = await self._payload(request, maximum_bytes=1_100_000)
            item = self._texts().create(
                principal,
                folder_id=request.path_params.get("folder_id") or payload.get("folder_id"),
                title=payload.get("title"), content=payload.get("content"),
                mode=payload.get("mode", "plain"), language=payload.get("language"),
                source_kind=payload.get("source_kind"), source_id=payload.get("source_id"),
            )
            return JSONResponse({"text": item.public_dict()}, status_code=201,
                                headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def personal_texts(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._create_text(request, user)

    async def workspace_texts(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._create_text(request, scope)

    async def _text_item(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            text_id = request.path_params["text_id"]
            if request.method == "GET":
                return JSONResponse({"text": self._texts().get(principal, text_id).public_dict()},
                                    headers={"Cache-Control": "no-store"})
            if request.method == "DELETE":
                self._texts().trash(principal, text_id)
                return Response(status_code=204)
            payload = await self._payload(request, maximum_bytes=1_100_000)
            item = self._texts().update(
                principal, text_id,
                title=payload.get("title") if "title" in payload else None,
                content=payload.get("content") if "content" in payload else None,
                mode=payload.get("mode") if "mode" in payload else None,
                language=payload.get("language"), language_supplied="language" in payload,
                parent_id=payload.get("parent_id") if "parent_id" in payload else None,
            )
            return JSONResponse({"text": item.public_dict()}, headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def personal_text(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._text_item(request, user)

    async def workspace_text(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._text_item(request, scope)

    async def share_collection(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            grants = self._shares().list_created(user)
            return JSONResponse(
                {"shares": [self._share_record(request, grant) for grant in grants]},
                headers={"Cache-Control": "no-store"},
            )
        except AuthenticationError as exc:
            return self._operation_error(exc)

    async def revoke_share(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
            self._shares().revoke(user, request.path_params["share_id"])
            return Response(status_code=204, headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def folders(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            if request.method == "GET":
                return JSONResponse(
                    self._library().list_folder(user, request.query_params.get("parent_id")),
                    headers={"Cache-Control": "no-store"},
                )
            payload = await self._payload(request)
            if "path" in payload:
                folder = self._library().create_path(user, payload.get("parent_id"), payload["path"])
            else:
                folder = self._library().create_folder(user, payload.get("parent_id"), payload.get("name"))
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return JSONResponse({"folder": folder.public_dict()}, status_code=201)

    async def tree(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            return JSONResponse({"root": self._library().tree(user)}, headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def folder(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
            folder_id = request.path_params["folder_id"]
            if request.method == "GET":
                return JSONResponse(self._library().list_folder(user, folder_id), headers={"Cache-Control": "no-store"})
            if request.method == "DELETE":
                self._library().trash_folder(user, folder_id)
                return Response(status_code=204)
            payload = await self._payload(request)
            folder = self._library().rename_move_folder(
                user, folder_id, name=payload.get("name"),
                parent_id=payload["parent_id"] if "parent_id" in payload else None,
            )
            return JSONResponse({"folder": folder.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def _file_detail_record(
        self, principal: User | LibraryScope, file_id: object,
    ) -> dict[str, object]:
        details = self._library().file_details(principal, file_id)
        item = self._library().get_file(principal, file_id)
        object_id = ObjectId.parse(item.object_id)
        security = self._previews().security(self.storage, object_id)
        preview = await self._previews().describe(
            object_id, name=item.name, declared_mime=item.content_type, security=security,
        )
        details["security"] = security
        details["preview"] = preview.public_dict()
        details["content_kind"] = preview.kind
        return details

    def _preview_response(self, object_id: ObjectId, decision: PreviewDecision) -> Response:
        if not decision.available or decision.response_mime is None:
            return JSONResponse(
                {"error": decision.reason or "Preview unavailable.", "preview": decision.public_dict()},
                status_code=415, headers={"Cache-Control": "no-store"},
            )
        try:
            transfer = self.transfer.prepare_download(object_id)
        except FileNotFoundError:
            return JSONResponse({"error": "Stored content not found."}, status_code=404)
        return StreamingResponse(
            transfer.chunks, media_type=decision.response_mime,
            headers={**PREVIEW_RESOURCE_HEADERS, "Content-Length": str(transfer.total_bytes)},
        )

    async def _preview_for(
        self, principal: User | LibraryScope, file_id: object,
    ) -> Response:
        try:
            item = self._library().get_file(principal, file_id)
            object_id = ObjectId.parse(item.object_id)
            security = self._previews().security(self.storage, object_id)
            decision = await self._previews().describe(
                object_id, name=item.name, declared_mime=item.content_type, security=security,
            )
            return self._preview_response(object_id, decision)
        except (AuthenticationError, LibraryOperationError, FileNotFoundError, ValueError) as exc:
            if isinstance(exc, FileNotFoundError):
                exc = LibraryOperationError("Stored content not found.", 404)
            if isinstance(exc, ValueError):
                exc = LibraryOperationError("Stored content reference is invalid.", 409)
            return self._operation_error(exc)

    async def file(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
            file_id = request.path_params["file_id"]
            if request.method == "GET":
                return JSONResponse(await self._file_detail_record(user, file_id),
                                    headers={"Cache-Control": "no-store"})
            if request.method == "DELETE":
                self._library().trash_file(user, file_id)
                return Response(status_code=204)
            payload = await self._payload(request)
            item = self._library().rename_move_file(
                user, file_id, name=payload.get("name"),
                parent_id=payload["parent_id"] if "parent_id" in payload else None,
            )
            return JSONResponse({"file": item.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def preview_file(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._preview_for(user, request.path_params["file_id"])

    async def upload_file(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            name = request.query_params.get("name") or request.headers.get("x-file-name")
            item, transfer_id = await self._library().upload(
                user, request.path_params["folder_id"], name,
                request.headers.get("content-type"), request.stream(),
                int(request.headers["content-length"]) if request.headers.get("content-length") else None,
                confirm_duplicates=request.query_params.get("confirm_duplicates") == "true",
            )
        except CapacityExceededError as exc:
            return JSONResponse({"error": str(exc), "code": "capacity_exceeded"}, status_code=413)
        except DuplicateWarningError as exc:
            return self._duplicate_warning(exc)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return JSONResponse({"file": item.public_dict(), "transfer_id": transfer_id}, status_code=201)

    async def download_file(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
            item = self._library().get_file(user, request.path_params["file_id"])
            transfer = self.transfer.prepare_download(ObjectId.parse(item.object_id))
        except (AuthenticationError, LibraryOperationError, FileNotFoundError) as exc:
            if isinstance(exc, FileNotFoundError):
                exc = LibraryOperationError("Stored content not found.", 404)
            return self._operation_error(exc)
        ascii_name = "".join(character if 32 <= ord(character) < 127 and character not in {'"', '\\'} else "_" for character in item.name)
        disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(item.name)}'
        return StreamingResponse(
            transfer.chunks, media_type=item.content_type,
            headers={"Content-Length": str(transfer.total_bytes), "Content-Disposition": disposition,
                     "Cache-Control": "private, no-store", "X-Transfer-Id": transfer.transfer_id},
        )

    def _version_download_response(self, item, version) -> Response:
        transfer = self.transfer.prepare_download(ObjectId.parse(version.object_id))
        ascii_name = "".join(
            character if 32 <= ord(character) < 127 and character not in {'"', '\\'} else "_"
            for character in item.name
        )
        return StreamingResponse(
            transfer.chunks, media_type=version.content_type,
            headers={"Content-Length": str(transfer.total_bytes),
                     "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(item.name)}',
                     "Cache-Control": "private, no-store", "X-Transfer-Id": transfer.transfer_id,
                     "X-File-Version": str(version.version_number)},
        )

    async def _versions(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            file_id = request.path_params["file_id"]
            if request.method == "GET":
                details = self._library().file_details(principal, file_id)
                return JSONResponse({"versions": details["versions"],
                                     "version_retention": details["version_retention"]},
                                    headers={"Cache-Control": "no-store"})
            version, transfer_id = await self._library().add_version(
                principal, file_id, request.headers.get("content-type"), request.stream(),
                int(request.headers["content-length"]) if request.headers.get("content-length") else None,
            )
            return JSONResponse({"version": version.public_dict(), "transfer_id": transfer_id},
                                status_code=201)
        except CapacityExceededError as exc:
            return JSONResponse({"error": str(exc), "code": "capacity_exceeded"}, status_code=413)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def file_versions(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._versions(request, user)

    async def _download_version(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            item = self._library().get_file(principal, request.path_params["file_id"])
            version = self._library().get_version(
                principal, item.id, request.path_params["version_id"]
            )
            return self._version_download_response(item, version)
        except (AuthenticationError, LibraryOperationError, FileNotFoundError) as exc:
            if isinstance(exc, FileNotFoundError):
                exc = LibraryOperationError("Stored content not found.", 404)
            return self._operation_error(exc)

    async def download_version(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._download_version(request, user)

    async def _restore_version(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            version = self._library().restore_version(
                principal, request.path_params["file_id"], request.path_params["version_id"]
            )
            return JSONResponse({"version": version.public_dict()}, status_code=201)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_version(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._restore_version(request, user)

    async def _derived_outputs(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            file_id = request.path_params["file_id"]
            if request.method == "GET":
                details = self._library().file_details(principal, file_id)
                return JSONResponse({"derived_outputs": details["derived_outputs"]},
                                    headers={"Cache-Control": "no-store"})
            provenance_raw = request.headers.get("x-provenance", "{}")
            try:
                provenance = json.loads(provenance_raw)
            except json.JSONDecodeError as exc:
                raise LibraryOperationError("X-Provenance must contain a JSON object.") from exc
            output, transfer_id = await self._library().upload_derived_output(
                principal, file_id,
                source_version_id=request.headers.get("x-source-version-id", ""),
                operation=request.headers.get("x-operation", ""),
                content_type=request.headers.get("content-type"), provenance=provenance,
                chunks=request.stream(),
                expected_bytes=(int(request.headers["content-length"])
                                if request.headers.get("content-length") else None),
            )
            return JSONResponse({"derived_output": output.public_dict(),
                                 "transfer_id": transfer_id}, status_code=201)
        except CapacityExceededError as exc:
            return JSONResponse({"error": str(exc), "code": "capacity_exceeded"}, status_code=413)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def derived_outputs(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._derived_outputs(request, user)

    async def _promote_derived(self, request: Request, principal: User | LibraryScope) -> Response:
        try:
            version = self._library().promote_derived_output(
                principal, request.path_params["file_id"], request.path_params["derived_id"]
            )
            return JSONResponse({"version": version.public_dict()}, status_code=201)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def promote_derived(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
        except AuthenticationError as exc:
            return self._operation_error(exc)
        return await self._promote_derived(request, user)

    async def _copy(self, request: Request, *, folder: bool, physical: bool) -> JSONResponse:
        try:
            user = self._require_user(request)
            payload = await self._payload(request)
            item_id = request.path_params["folder_id" if folder else "file_id"]
            if folder:
                item = await self._library().copy_folder(user, item_id, payload.get("parent_id"), payload.get("name"), physical=physical)
                return JSONResponse({"folder": item.public_dict()}, status_code=201)
            item = await self._library().copy_file(user, item_id, payload.get("parent_id"), payload.get("name"), physical=physical)
            return JSONResponse({"file": item.public_dict()}, status_code=201)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def copy_folder(self, request: Request) -> JSONResponse:
        return await self._copy(request, folder=True, physical=False)

    async def duplicate_folder(self, request: Request) -> JSONResponse:
        return await self._copy(request, folder=True, physical=True)

    async def copy_file(self, request: Request) -> JSONResponse:
        return await self._copy(request, folder=False, physical=False)

    async def duplicate_file(self, request: Request) -> JSONResponse:
        return await self._copy(request, folder=False, physical=True)

    async def personal_trash(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            return JSONResponse(self._trash().list(user), headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_personal_file(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            item = self._trash().restore_file(user, request.path_params["file_id"])
            return JSONResponse({"file": item.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_personal_folder(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            folder = self._trash().restore_folder(user, request.path_params["folder_id"])
            return JSONResponse({"folder": folder.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def delete_personal_file(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            deleted = self._trash().permanently_delete_file(user, request.path_params["file_id"])
            return JSONResponse({"permanently_deleted": True, "physical_object_deleted": deleted})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def delete_personal_folder(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            deleted = self._trash().permanently_delete_folder(user, request.path_params["folder_id"])
            return JSONResponse({"permanently_deleted": True, "physical_objects_deleted": deleted})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_personal_text(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            item = self._trash().restore_text(user, request.path_params["text_id"])
            return JSONResponse({"text": item.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def delete_personal_text(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            self._trash().permanently_delete_text(user, request.path_params["text_id"])
            return JSONResponse({"permanently_deleted": True})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    def _workspace_context(self, request: Request):
        user = self._require_user(request)
        workspace, scope = self._workspaces().require_member(
            user, request.path_params["workspace_id"]
        )
        return user, workspace, scope

    async def workspace_collection(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            if request.method == "GET":
                return JSONResponse(
                    {"user": user.public_dict(), **self._workspaces().describe(user)},
                    headers={"Cache-Control": "no-store"},
                )
            payload = await self._payload(request)
            workspace = self._workspaces().create(user, payload.get("name"))
            return JSONResponse(
                {"workspace": workspace.public_dict(),
                 "policy": self._workspaces().policy.public_dict()}, status_code=201
            )
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_detail(self, request: Request) -> JSONResponse:
        try:
            user, workspace, scope = self._workspace_context(request)
            listing = self._library().list_folder(scope, request.query_params.get("folder_id"))
            return JSONResponse(
                {"user": user.public_dict(), **self._workspaces().describe(user, workspace.id),
                 **listing}, headers={"Cache-Control": "no-store"}
            )
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_usage(self, request: Request) -> JSONResponse:
        try:
            _, workspace, scope = self._workspace_context(request)
            usage = self.capacity.report(UsageScope("workspace", scope.id))
            return JSONResponse({"scope": "workspace", "workspace": workspace.public_dict(),
                                 **usage, "installation": self.capacity.installation_report()},
                                headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_members(self, request: Request) -> JSONResponse:
        try:
            user = self._require_user(request)
            payload = await self._payload(request)
            member = self._workspaces().add_member(
                user, request.path_params["workspace_id"], payload.get("email")
            )
            return JSONResponse({"member": member.public_dict()}, status_code=201)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def leave_workspace(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
            new_owner_id = self._workspaces().leave(user, request.path_params["workspace_id"])
            return JSONResponse({"new_owner_user_id": new_owner_id})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def remove_workspace_member(self, request: Request) -> Response:
        try:
            user = self._require_user(request)
            self._workspaces().remove_member(
                user, request.path_params["workspace_id"], request.path_params["member_id"]
            )
            return Response(status_code=204)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_folders(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            if request.method == "GET":
                return JSONResponse(
                    self._library().list_folder(scope, request.query_params.get("parent_id")),
                    headers={"Cache-Control": "no-store"},
                )
            payload = await self._payload(request)
            if "path" in payload:
                folder = self._library().create_path(scope, payload.get("parent_id"), payload["path"])
            else:
                folder = self._library().create_folder(scope, payload.get("parent_id"), payload.get("name"))
            return JSONResponse({"folder": folder.public_dict()}, status_code=201)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_tree(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            return JSONResponse({"root": self._library().tree(scope)},
                                headers={"Cache-Control": "no-store"})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_folder(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
            folder_id = request.path_params["folder_id"]
            if request.method == "GET":
                return JSONResponse(self._library().list_folder(scope, folder_id),
                                    headers={"Cache-Control": "no-store"})
            if request.method == "DELETE":
                self._library().trash_folder(scope, folder_id)
                return Response(status_code=204)
            payload = await self._payload(request)
            folder = self._library().rename_move_folder(
                scope, folder_id, name=payload.get("name"),
                parent_id=payload["parent_id"] if "parent_id" in payload else None,
            )
            return JSONResponse({"folder": folder.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_file(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
            file_id = request.path_params["file_id"]
            if request.method == "GET":
                return JSONResponse(await self._file_detail_record(scope, file_id),
                                    headers={"Cache-Control": "no-store"})
            if request.method == "DELETE":
                self._library().trash_file(scope, file_id)
                return Response(status_code=204)
            payload = await self._payload(request)
            item = self._library().rename_move_file(
                scope, file_id, name=payload.get("name"),
                parent_id=payload["parent_id"] if "parent_id" in payload else None,
            )
            return JSONResponse({"file": item.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_preview(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._preview_for(scope, request.path_params["file_id"])

    async def workspace_upload(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            name = request.query_params.get("name") or request.headers.get("x-file-name")
            item, transfer_id = await self._library().upload(
                scope, request.path_params["folder_id"], name,
                request.headers.get("content-type"), request.stream(),
                int(request.headers["content-length"]) if request.headers.get("content-length") else None,
                confirm_duplicates=request.query_params.get("confirm_duplicates") == "true",
            )
            return JSONResponse({"file": item.public_dict(), "transfer_id": transfer_id},
                                status_code=201)
        except CapacityExceededError as exc:
            return JSONResponse({"error": str(exc), "code": "capacity_exceeded"}, status_code=413)
        except DuplicateWarningError as exc:
            return self._duplicate_warning(exc)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_download(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
            item = self._library().get_file(scope, request.path_params["file_id"])
            transfer = self.transfer.prepare_download(ObjectId.parse(item.object_id))
        except (AuthenticationError, LibraryOperationError, FileNotFoundError) as exc:
            if isinstance(exc, FileNotFoundError):
                exc = LibraryOperationError("Stored content not found.", 404)
            return self._operation_error(exc)
        ascii_name = "".join(
            character if 32 <= ord(character) < 127 and character not in {'"', '\\'} else "_"
            for character in item.name
        )
        return StreamingResponse(
            transfer.chunks, media_type=item.content_type,
            headers={"Content-Length": str(transfer.total_bytes),
                     "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(item.name)}',
                     "Cache-Control": "private, no-store", "X-Transfer-Id": transfer.transfer_id},
        )

    async def workspace_file_versions(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._versions(request, scope)

    async def workspace_download_version(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._download_version(request, scope)

    async def workspace_restore_version(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._restore_version(request, scope)

    async def workspace_derived_outputs(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._derived_outputs(request, scope)

    async def workspace_promote_derived(self, request: Request) -> Response:
        try:
            _, _, scope = self._workspace_context(request)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)
        return await self._promote_derived(request, scope)

    async def _workspace_copy(self, request: Request, *, folder: bool, physical: bool) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            payload = await self._payload(request)
            item_id = request.path_params["folder_id" if folder else "file_id"]
            if folder:
                item = await self._library().copy_folder(
                    scope, item_id, payload.get("parent_id"), payload.get("name"), physical=physical
                )
                return JSONResponse({"folder": item.public_dict()}, status_code=201)
            item = await self._library().copy_file(
                scope, item_id, payload.get("parent_id"), payload.get("name"), physical=physical
            )
            return JSONResponse({"file": item.public_dict()}, status_code=201)
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def workspace_copy_folder(self, request: Request) -> JSONResponse:
        return await self._workspace_copy(request, folder=True, physical=False)

    async def workspace_duplicate_folder(self, request: Request) -> JSONResponse:
        return await self._workspace_copy(request, folder=True, physical=True)

    async def workspace_copy_file(self, request: Request) -> JSONResponse:
        return await self._workspace_copy(request, folder=False, physical=False)

    async def workspace_duplicate_file(self, request: Request) -> JSONResponse:
        return await self._workspace_copy(request, folder=False, physical=True)

    async def workspace_trash(self, request: Request) -> JSONResponse:
        try:
            user, workspace, scope = self._workspace_context(request)
            return JSONResponse(
                {"user": user.public_dict(), "workspace": workspace.public_dict(),
                 **self._trash().list(scope)}, headers={"Cache-Control": "no-store"},
            )
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_workspace_file(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            item = self._trash().restore_file(scope, request.path_params["file_id"])
            return JSONResponse({"file": item.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_workspace_folder(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            folder = self._trash().restore_folder(scope, request.path_params["folder_id"])
            return JSONResponse({"folder": folder.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def delete_workspace_file(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            deleted = self._trash().permanently_delete_file(scope, request.path_params["file_id"])
            return JSONResponse({"permanently_deleted": True, "physical_object_deleted": deleted})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def delete_workspace_folder(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            deleted = self._trash().permanently_delete_folder(scope, request.path_params["folder_id"])
            return JSONResponse({"permanently_deleted": True, "physical_objects_deleted": deleted})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def restore_workspace_text(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            item = self._trash().restore_text(scope, request.path_params["text_id"])
            return JSONResponse({"text": item.public_dict()})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    async def delete_workspace_text(self, request: Request) -> JSONResponse:
        try:
            _, _, scope = self._workspace_context(request)
            self._trash().permanently_delete_text(scope, request.path_params["text_id"])
            return JSONResponse({"permanently_deleted": True})
        except (AuthenticationError, LibraryOperationError) as exc:
            return self._operation_error(exc)

    @staticmethod
    def _public_share_error(exc: ShareAccessError) -> JSONResponse:
        payload: dict[str, object] = {"error": str(exc)}
        if exc.status_code == 409:
            payload |= {"security_verdict": "malicious", "confirmation_required": True}
        return JSONResponse(payload, status_code=exc.status_code,
                            headers={"Cache-Control": "no-store"})

    async def public_share_page(self, request: Request) -> Response:
        try:
            self._shares().resolve(
                request.path_params["share_token"], request.query_params.get("key")
            )
        except ShareAccessError as exc:
            return Response(str(exc), status_code=exc.status_code, media_type="text/plain",
                            headers={"Cache-Control": "no-store"})
        path = self._asset("library-share.html")
        if not path.is_file():
            return JSONResponse({"error": "Library share assets are missing."}, status_code=500)
        return HTMLResponse(
            path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store", "Content-Security-Policy": FILE_DETAIL_CSP},
        )

    async def public_share_info(self, request: Request) -> JSONResponse:
        token = request.path_params["share_token"]
        key = request.query_params.get("key")
        try:
            record = self._shares().recipient_record(token, key)
            resolved = self._shares().resolve(token, key)
        except ShareAccessError as exc:
            return self._public_share_error(exc)
        query = f"?key={quote(key, safe='')}" if key else ""
        root = str(request.base_url).rstrip("/")
        record["download_url"] = f"/api/public/shares/{quote(token, safe='')}/download{query}"
        if resolved.version is not None:
            object_id = ObjectId.parse(resolved.version.object_id)
            preview = await self._previews().describe(
                object_id, name=resolved.grant.source_name,
                declared_mime=resolved.version.content_type, security=resolved.security,
            )
            record["preview"] = preview.public_dict()
            record["preview_url"] = f"/api/public/shares/{quote(token, safe='')}/preview{query}"
        return JSONResponse(
            {"share": record, "share_url": f"{root}/s/{quote(token, safe='')}{query}"},
            headers={"Cache-Control": "no-store"},
        )

    async def public_share_preview(self, request: Request) -> Response:
        try:
            resolved = self._shares().resolve(
                request.path_params["share_token"], request.query_params.get("key")
            )
            if resolved.version is None:
                return JSONResponse({"error": "This share is not a file preview."}, status_code=415)
            object_id = ObjectId.parse(resolved.version.object_id)
            decision = await self._previews().describe(
                object_id, name=resolved.grant.source_name,
                declared_mime=resolved.version.content_type, security=resolved.security,
            )
            return self._preview_response(object_id, decision)
        except ShareAccessError as exc:
            return self._public_share_error(exc)

    async def public_share_download(self, request: Request) -> Response:
        try:
            resolved = self._shares().download(
                request.path_params["share_token"], request.query_params.get("key"),
                confirmed_malicious=request.query_params.get("confirm_malicious") == "true",
            )
            if resolved.text is not None:
                extension = ".md" if resolved.text.mode.value == "markdown" else ".txt"
                name = resolved.grant.source_title
                if not name.lower().endswith(extension):
                    name += extension
                ascii_name = "".join(
                    character if 32 <= ord(character) < 127 and character not in {'"', '\\'} else "_"
                    for character in name
                )
                return Response(
                    resolved.text.content.encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={
                        "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}',
                        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                    },
                )
            assert resolved.version is not None
            transfer = self.transfer.prepare_download(ObjectId.parse(resolved.version.object_id))
        except ShareAccessError as exc:
            return self._public_share_error(exc)
        except FileNotFoundError:
            return JSONResponse({"error": "Shared content is no longer available."}, status_code=404)
        name = resolved.grant.source_name
        ascii_name = "".join(
            character if 32 <= ord(character) < 127 and character not in {'"', '\\'} else "_"
            for character in name
        )
        return StreamingResponse(
            transfer.chunks, media_type=resolved.version.content_type,
            headers={"Content-Length": str(transfer.total_bytes),
                     "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}',
                     "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                     "X-Transfer-Id": transfer.transfer_id},
        )

    async def public_share_qr(self, request: Request) -> Response:
        token = request.path_params["share_token"]
        key = request.query_params.get("key")
        try:
            self._shares().resolve(token, key)
        except ShareAccessError as exc:
            return self._public_share_error(exc)
        query = f"?key={quote(key, safe='')}" if key else ""
        target = f"{str(request.base_url).rstrip('/')}/s/{quote(token, safe='')}{query}"
        qr = qrcode.QRCode(
            version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10, border=4,
        )
        qr.add_data(target)
        qr.make(fit=True)
        image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        output = io.BytesIO()
        image.save(output)
        return Response(
            output.getvalue(), media_type="image/svg+xml",
            headers={"Cache-Control": "no-store",
                     "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                     "X-Content-Type-Options": "nosniff"},
        )

    async def create_invitation(self, request: Request) -> JSONResponse:
        try:
            payload = await self._payload(request)
            token = self._service().create_invitation(self._user(request), payload.get("email"))
        except AuthenticationError as exc:
            return self._error(exc)
        return JSONResponse(
            {"invitation_token": token, "expires_in_seconds": 7 * 24 * 60 * 60},
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )

    async def pending_users(self, request: Request) -> JSONResponse:
        try:
            users = self._service().pending_users(self._user(request))
        except AuthenticationError as exc:
            return self._error(exc)
        return JSONResponse(
            {"users": [user.public_dict() for user in users]},
            headers={"Cache-Control": "no-store"},
        )

    async def approve_user(self, request: Request) -> JSONResponse:
        return self._decide_user(request, approve=True)

    async def reject_user(self, request: Request) -> JSONResponse:
        return self._decide_user(request, approve=False)

    def _decide_user(self, request: Request, *, approve: bool) -> JSONResponse:
        try:
            user = self._service().decide_pending_user(
                self._user(request), request.path_params["user_id"], approve=approve
            )
        except AuthenticationError as exc:
            return self._error(exc)
        return JSONResponse({"user": user.public_dict()}, headers={"Cache-Control": "no-store"})


__all__ = ["LibraryModule", "SESSION_COOKIE"]
