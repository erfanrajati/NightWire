"""Registration of the current v1.0.2 behavior as the initial Drop module."""

from __future__ import annotations

from starlette.staticfiles import StaticFiles

from nightwire.app.registration import ApplicationRegistry, ModuleContext


class DropModule:
    """Register the legacy route surface and cleanup lifecycle."""

    name = "drop"

    def register(self, registry: ApplicationRegistry, context: ModuleContext) -> None:
        handler = context.request_handler
        registry.add_route("/", handler("root"), methods=["GET"])
        registry.add_route("/files", handler("page"), methods=["GET"])
        registry.add_route("/clipboard", handler("page"), methods=["GET"])
        registry.add_route("/clients", handler("page"), methods=["GET"])
        registry.add_route("/api/files", handler("list_files"), methods=["GET"])
        registry.add_route("/api/info", handler("server_info"), methods=["GET"])
        registry.add_route("/api/devices", handler("list_devices"), methods=["GET"])
        registry.add_route("/api/clients/heartbeat", handler("client_heartbeat"), methods=["POST"])
        registry.add_route("/api/clipboard", handler("list_clipboard"), methods=["GET"])
        registry.add_route("/api/clipboard", handler("share_clipboard"), methods=["POST"])
        registry.add_route("/api/clipboard", handler("clear_clipboard"), methods=["DELETE"])
        registry.add_route("/api/clipboard/{entry_id:str}", handler("patch_clipboard"), methods=["PATCH"])
        registry.add_route("/api/clipboard/{entry_id:str}", handler("delete_clipboard"), methods=["DELETE"])
        registry.add_route(
            "/api/clipboard/{entry_id:str}/unlock", handler("unlock_clipboard"), methods=["POST"]
        )
        registry.add_route("/api/qr", handler("qr_code"), methods=["GET"])
        registry.add_route("/api/upload", handler("upload_file"), methods=["PUT"])
        registry.add_route("/api/files/{filename:str}", handler("patch_file"), methods=["PATCH"])
        registry.add_route("/api/files/{filename:str}", handler("delete_file"), methods=["DELETE"])
        registry.add_route(
            "/api/files/{filename:str}/download", handler("download_protected_file"), methods=["POST"]
        )
        registry.add_route("/download/{filename:str}", handler("download_file"), methods=["GET", "HEAD"])
        registry.add_mount(
            "/static",
            StaticFiles(directory=context.settings.static_dir),
            name="static",
        )
        registry.add_startup_hook(context.lifecycle_hook("start_cleanup_worker"))
        registry.add_shutdown_hook(context.lifecycle_hook("stop_cleanup_worker"))


__all__ = ["DropModule"]
