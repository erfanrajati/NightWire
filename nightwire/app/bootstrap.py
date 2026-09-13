"""Starlette application bootstrap and module composition."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from inspect import isawaitable

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from nightwire.app.registration import (
    ApplicationRegistry,
    ApplicationHandler,
    HttpMiddleware,
    ModuleBinding,
    ModuleContext,
)
from nightwire.core.config import ApplicationConfig
from nightwire.drop.registration import DropModule
from nightwire.library.registration import LibraryModule


def configured_modules(settings: ApplicationConfig) -> tuple[ModuleBinding, ...]:
    """Return built-in modules paired with their resolved enabled state."""

    return (
        ModuleBinding(DropModule(), settings.installed_modules.drop),
        ModuleBinding(LibraryModule(), settings.installed_modules.library),
    )


def build_application(
    settings: ApplicationConfig,
    handlers: Mapping[str, ApplicationHandler],
    *,
    modules: Sequence[ModuleBinding] | None = None,
    http_middleware: Sequence[HttpMiddleware] = (),
) -> Starlette:
    """Build a Starlette application from enabled module registrations."""

    registry = ApplicationRegistry()
    context = ModuleContext(settings=settings, handlers=handlers)
    bindings = configured_modules(settings) if modules is None else tuple(modules)

    for binding in bindings:
        if not binding.enabled:
            continue
        registry.registered_modules.append(binding.module.name)
        binding.module.register(registry, context)

    @asynccontextmanager
    async def lifespan(application: Starlette):
        for hook in registry.startup_hooks:
            result = hook()
            if isawaitable(result):
                await result
        try:
            yield
        finally:
            for hook in registry.shutdown_hooks:
                result = hook()
                if isawaitable(result):
                    await result

    application = Starlette(
        debug=False,
        routes=registry.routes,
        middleware=[Middleware(BaseHTTPMiddleware, dispatch=middleware) for middleware in http_middleware],
        lifespan=lifespan,
    )
    application.state.registered_modules = tuple(registry.registered_modules)
    application.state.startup_hooks = tuple(registry.startup_hooks)
    application.state.shutdown_hooks = tuple(registry.shutdown_hooks)
    return application


__all__ = ["build_application", "configured_modules"]
