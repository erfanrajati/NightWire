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
        ]
        actual = [
            (route.path, set(route.methods) if hasattr(route, "methods") else None)
            for route in app.app.routes
        ]

        self.assertEqual(actual, expected)
        self.assertEqual(app.app.state.registered_modules, ("drop", "library"))

    def test_drop_owns_existing_lifecycle_hooks(self):
        self.assertEqual(app.app.state.startup_hooks, (app.start_cleanup_worker,))
        self.assertEqual(app.app.state.shutdown_hooks, (app.stop_cleanup_worker,))

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
        self.assertEqual(application.routes, [])
        self.assertEqual(application.state.startup_hooks, ())
        self.assertEqual(application.state.shutdown_hooks, ())

    def test_disabled_library_leaves_drop_route_surface_unchanged(self):
        application = build_application(
            self.settings_with_modules(drop=True, library=False),
            app.ROUTE_HANDLERS,
            http_middleware=[app.security_headers],
        )

        self.assertEqual(application.state.registered_modules, ("drop",))
        self.assertEqual(
            [(route.path, getattr(route, "methods", None)) for route in application.routes],
            [(route.path, getattr(route, "methods", None)) for route in app.app.routes],
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
