import asyncio
import unittest
from dataclasses import replace

import app
from nightwire.app.bootstrap import build_application
from nightwire.app.registration import ApplicationRegistry, ModuleBinding, ModuleContext
from nightwire.core.config import InstalledModules


class BootstrapRouteParityTests(unittest.TestCase):
    def test_default_bootstrap_preserves_every_v1_route_and_method(self):
        expected = [
            ("/", {"GET", "HEAD"}),
            ("/files", {"GET", "HEAD"}),
            ("/clipboard", {"GET", "HEAD"}),
            ("/clients", {"GET", "HEAD"}),
            ("/drop/{filename:str}", {"GET", "HEAD"}),
            ("/api/drops", {"GET", "HEAD"}),
            ("/api/drops/files", {"PUT"}),
            ("/api/drops/text", {"POST"}),
            ("/api/drops/{filename:str}", {"GET", "HEAD"}),
            ("/api/files", {"GET", "HEAD"}),
            ("/api/info", {"GET", "HEAD"}),
            ("/api/devices", {"GET", "HEAD"}),
            ("/api/clients/heartbeat", {"POST"}),
            ("/api/clipboard", {"GET", "HEAD"}),
            ("/api/clipboard", {"POST"}),
            ("/api/clipboard", {"DELETE"}),
            ("/api/clipboard/{entry_id:str}", {"PATCH"}),
            ("/api/clipboard/{entry_id:str}", {"DELETE"}),
            ("/api/clipboard/{entry_id:str}/unlock", {"POST"}),
            ("/api/qr", {"GET", "HEAD"}),
            ("/api/upload", {"PUT"}),
            ("/api/files/{filename:str}", {"PATCH"}),
            ("/api/files/{filename:str}", {"DELETE"}),
            ("/api/files/{filename:str}/download", {"POST"}),
            ("/download/{filename:str}", {"GET", "HEAD"}),
            ("/static", None),
            ("/library", {"GET", "HEAD"}),
            ("/library/files/{file_id:str}", {"GET", "HEAD"}),
            ("/library/texts/{text_id:str}", {"GET", "HEAD"}),
            ("/workspaces", {"GET", "HEAD"}),
            ("/workspaces/{workspace_id:str}/files/{file_id:str}", {"GET", "HEAD"}),
            ("/workspaces/{workspace_id:str}/texts/{text_id:str}", {"GET", "HEAD"}),
            ("/library/trash", {"GET", "HEAD"}),
            ("/library/shares", {"GET", "HEAD"}),
            ("/workspaces/trash", {"GET", "HEAD"}),
            ("/library/login", {"GET", "HEAD"}),
            ("/library/signup", {"GET", "HEAD"}),
            ("/library/assets/auth.js", {"GET", "HEAD"}),
            ("/library/assets/auth.css", {"GET", "HEAD"}),
            ("/library/assets/browser.js", {"GET", "HEAD"}),
            ("/library/assets/browser.css", {"GET", "HEAD"}),
            ("/library/assets/text-ui.js", {"GET", "HEAD"}),
            ("/library/assets/text-editor.js", {"GET", "HEAD"}),
            ("/library/assets/text-editor.css", {"GET", "HEAD"}),
            ("/library/assets/file-detail.js", {"GET", "HEAD"}),
            ("/library/assets/file-detail.css", {"GET", "HEAD"}),
            ("/library/assets/trash.js", {"GET", "HEAD"}),
            ("/library/assets/shares.js", {"GET", "HEAD"}),
            ("/library/assets/share-recipient.js", {"GET", "HEAD"}),
            ("/library/assets/shell.css", {"GET", "HEAD"}),
            ("/api/library", {"GET", "HEAD"}),
            ("/api/library/usage", {"GET", "HEAD"}),
            ("/api/library/search", {"GET", "HEAD"}),
            ("/api/library/folders", {"GET", "HEAD", "POST"}),
            ("/api/library/tree", {"GET", "HEAD"}),
            ("/api/library/folders/{folder_id:str}", {"GET", "HEAD", "PATCH", "DELETE"}),
            ("/api/library/folders/{folder_id:str}/upload", {"PUT"}),
            ("/api/library/folders/{folder_id:str}/texts", {"POST"}),
            ("/api/library/folders/{folder_id:str}/copy", {"POST"}),
            ("/api/library/folders/{folder_id:str}/duplicate", {"POST"}),
            ("/api/library/files/{file_id:str}", {"GET", "HEAD", "PATCH", "DELETE"}),
            ("/api/library/files/{file_id:str}/preview", {"GET", "HEAD"}),
            ("/api/library/files/{file_id:str}/download", {"GET", "HEAD"}),
            ("/api/library/files/{file_id:str}/versions", {"GET", "HEAD", "PUT"}),
            ("/api/library/files/{file_id:str}/versions/{version_id:str}/download", {"GET", "HEAD"}),
            ("/api/library/files/{file_id:str}/versions/{version_id:str}/restore", {"POST"}),
            ("/api/library/files/{file_id:str}/derived-outputs", {"GET", "HEAD", "PUT"}),
            ("/api/library/files/{file_id:str}/derived-outputs/{derived_id:str}/promote", {"POST"}),
            ("/api/library/files/{file_id:str}/shares", {"GET", "HEAD", "POST"}),
            ("/api/library/files/{file_id:str}/copy", {"POST"}),
            ("/api/library/files/{file_id:str}/duplicate", {"POST"}),
            ("/api/library/texts", {"POST"}),
            ("/api/library/texts/{text_id:str}", {"GET", "HEAD", "PATCH", "DELETE"}),
            ("/api/library/texts/{text_id:str}/shares", {"GET", "HEAD", "POST"}),
            ("/api/library/trash", {"GET", "HEAD"}),
            ("/api/library/trash/files/{file_id:str}/restore", {"POST"}),
            ("/api/library/trash/files/{file_id:str}", {"DELETE"}),
            ("/api/library/trash/folders/{folder_id:str}/restore", {"POST"}),
            ("/api/library/trash/folders/{folder_id:str}", {"DELETE"}),
            ("/api/library/trash/texts/{text_id:str}/restore", {"POST"}),
            ("/api/library/trash/texts/{text_id:str}", {"DELETE"}),
            ("/api/library/shares", {"GET", "HEAD"}),
            ("/api/library/shares/{share_id:str}", {"DELETE"}),
            ("/api/workspaces", {"GET", "HEAD", "POST"}),
            ("/api/workspaces/{workspace_id:str}", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/usage", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/members", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/members/me", {"DELETE"}),
            ("/api/workspaces/{workspace_id:str}/members/{member_id:str}", {"DELETE"}),
            ("/api/workspaces/{workspace_id:str}/folders", {"GET", "HEAD", "POST"}),
            ("/api/workspaces/{workspace_id:str}/tree", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}", {"GET", "HEAD", "PATCH", "DELETE"}),
            ("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/upload", {"PUT"}),
            ("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/texts", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/copy", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/folders/{folder_id:str}/duplicate", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}", {"GET", "HEAD", "PATCH", "DELETE"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/preview", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/download", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/versions", {"GET", "HEAD", "PUT"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/versions/{version_id:str}/download", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/versions/{version_id:str}/restore", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/derived-outputs", {"GET", "HEAD", "PUT"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/derived-outputs/{derived_id:str}/promote", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/shares", {"GET", "HEAD", "POST"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/copy", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/files/{file_id:str}/duplicate", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/texts", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/texts/{text_id:str}", {"GET", "HEAD", "PATCH", "DELETE"}),
            ("/api/workspaces/{workspace_id:str}/texts/{text_id:str}/shares", {"GET", "HEAD", "POST"}),
            ("/api/workspaces/{workspace_id:str}/trash", {"GET", "HEAD"}),
            ("/api/workspaces/{workspace_id:str}/trash/files/{file_id:str}/restore", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/trash/files/{file_id:str}", {"DELETE"}),
            ("/api/workspaces/{workspace_id:str}/trash/folders/{folder_id:str}/restore", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/trash/folders/{folder_id:str}", {"DELETE"}),
            ("/api/workspaces/{workspace_id:str}/trash/texts/{text_id:str}/restore", {"POST"}),
            ("/api/workspaces/{workspace_id:str}/trash/texts/{text_id:str}", {"DELETE"}),
            ("/api/library/auth/config", {"GET", "HEAD"}),
            ("/api/library/auth/register", {"POST"}),
            ("/api/library/auth/login", {"POST"}),
            ("/api/library/auth/logout", {"POST"}),
            ("/api/library/auth/me", {"GET", "HEAD"}),
            ("/api/library/admin/invitations", {"POST"}),
            ("/api/library/admin/pending-users", {"GET", "HEAD"}),
            ("/api/library/admin/pending-users/{user_id:str}/approve", {"POST"}),
            ("/api/library/admin/pending-users/{user_id:str}/reject", {"POST"}),
            ("/s/{share_token:str}", {"GET", "HEAD"}),
            ("/api/public/shares/{share_token:str}", {"GET", "HEAD"}),
            ("/api/public/shares/{share_token:str}/preview", {"GET", "HEAD"}),
            ("/api/public/shares/{share_token:str}/download", {"GET", "HEAD"}),
            ("/api/public/shares/{share_token:str}/qr", {"GET", "HEAD"}),
        ]
        actual = [
            (route.path, set(route.methods) if hasattr(route, "methods") else None)
            for route in app.app.routes
        ]

        self.assertEqual(actual, expected)
        self.assertEqual(app.app.state.registered_modules, ("drop", "library"))

    def test_drop_owns_existing_lifecycle_hooks(self):
        self.assertIs(app.app.state.startup_hooks[0], app.start_cleanup_worker)
        self.assertEqual(app.app.state.startup_hooks[1], app.app.state.library_database.migrate)
        self.assertEqual(app.app.state.startup_hooks[2], app.app.state.library_trash.start_cleanup)
        self.assertEqual(
            app.app.state.shutdown_hooks,
            (app.stop_cleanup_worker, app.app.state.library_trash.stop_cleanup),
        )

    def test_security_middleware_is_applied_by_bootstrap(self):
        middleware_classes = [item.cls.__name__ for item in app.app.user_middleware]
        self.assertEqual(middleware_classes, ["BaseHTTPMiddleware"])


class ConditionalBuiltInModuleTests(unittest.TestCase):
    def settings_with_modules(self, *, drop, library):
        return replace(
            app.SETTINGS,
            installed_modules=InstalledModules(drop=drop, library=library),
        )

    def test_disabled_drop_registers_no_legacy_routes_or_lifecycle_hooks(self):
        application = build_application(
            self.settings_with_modules(drop=False, library=True),
            app.ROUTE_HANDLERS,
            http_middleware=[app.security_headers],
        )

        self.assertEqual(application.state.registered_modules, ("library",))
        self.assertEqual(application.routes[0].path, "/library")
        self.assertEqual(application.routes[-1].path, "/api/public/shares/{share_token:str}/qr")
        self.assertEqual(
            application.state.startup_hooks,
            (application.state.library_database.migrate, application.state.library_trash.start_cleanup),
        )
        self.assertEqual(application.state.shutdown_hooks, (application.state.library_trash.stop_cleanup,))

    def test_disabled_library_leaves_drop_route_surface_unchanged(self):
        application = build_application(
            self.settings_with_modules(drop=True, library=False),
            app.ROUTE_HANDLERS,
            http_middleware=[app.security_headers],
        )

        self.assertEqual(application.state.registered_modules, ("drop",))
        self.assertEqual(
            [(route.path, getattr(route, "methods", None)) for route in application.routes],
            [(route.path, getattr(route, "methods", None)) for route in app.app.routes[:26]],
        )
        self.assertEqual(application.state.startup_hooks, (app.start_cleanup_worker,))
        self.assertEqual(application.state.shutdown_hooks, (app.stop_cleanup_worker,))


class ModuleRegistrationContractTests(unittest.TestCase):
    def test_enabled_module_can_register_routes_and_lifecycle_hooks(self):
        calls = []

        async def endpoint(request):
            return app.JSONResponse({"ok": True})

        async def startup():
            calls.append("startup")

        async def shutdown():
            calls.append("shutdown")

        class ProbeModule:
            name = "probe"

            def register(self, registry: ApplicationRegistry, context: ModuleContext):
                self.context = context
                registry.add_route("/probe", endpoint, methods=["GET"])
                registry.add_startup_hook(startup)
                registry.add_shutdown_hook(shutdown)

        probe = ProbeModule()
        application = build_application(
            app.SETTINGS,
            {},
            modules=[ModuleBinding(probe, enabled=True)],
        )

        self.assertEqual(application.state.registered_modules, ("probe",))
        self.assertEqual([route.path for route in application.routes], ["/probe"])
        self.assertEqual(application.state.startup_hooks, (startup,))
        self.assertEqual(application.state.shutdown_hooks, (shutdown,))
        self.assertIs(probe.context.settings, app.SETTINGS)
        self.assertEqual(calls, [])

        async def run_lifespan():
            async with application.router.lifespan_context(application):
                self.assertEqual(calls, ["startup"])

        asyncio.run(run_lifespan())
        self.assertEqual(calls, ["startup", "shutdown"])

    def test_disabled_module_is_not_invoked(self):
        class DisabledModule:
            name = "disabled"

            def register(self, registry: ApplicationRegistry, context: ModuleContext):
                raise AssertionError("disabled module registration must not run")

        application = build_application(
            app.SETTINGS,
            {},
            modules=[ModuleBinding(DisabledModule(), enabled=False)],
        )

        self.assertEqual(application.state.registered_modules, ())
        self.assertEqual(application.routes, [])

    def test_missing_legacy_handler_has_a_specific_registration_error(self):
        context = ModuleContext(settings=app.SETTINGS, handlers={})

        with self.assertRaisesRegex(KeyError, "application handler is not available"):
            context.handler("missing")


if __name__ == "__main__":
    unittest.main()
