"""Contracts used by NightWire modules during application composition."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Mount, Route

from nightwire.core.config import ApplicationConfig


RequestHandler = Callable[[Request], Awaitable[Response]]
LifecycleHook = Callable[[], Awaitable[None] | None]
HttpMiddleware = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]
ApplicationHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ModuleContext:
    """Configuration and legacy handlers available during registration."""

    settings: ApplicationConfig
    handlers: Mapping[str, ApplicationHandler]

    def handler(self, name: str) -> ApplicationHandler:
        try:
            return self.handlers[name]
        except KeyError as exc:
            raise KeyError(f"The {name!r} application handler is not available.") from exc

    def request_handler(self, name: str) -> RequestHandler:
        return cast(RequestHandler, self.handler(name))

    def lifecycle_hook(self, name: str) -> LifecycleHook:
        return cast(LifecycleHook, self.handler(name))


@dataclass(slots=True)
class ApplicationRegistry:
    """Mutable route and lifecycle collection populated by enabled modules."""

    routes: list[BaseRoute] = field(default_factory=list)
    startup_hooks: list[LifecycleHook] = field(default_factory=list)
    shutdown_hooks: list[LifecycleHook] = field(default_factory=list)
    registered_modules: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def add_route(
        self,
        path: str,
        endpoint: RequestHandler,
        *,
        methods: Sequence[str],
        name: str | None = None,
    ) -> None:
        self.routes.append(Route(path, endpoint, methods=list(methods), name=name))

    def add_mount(self, path: str, application: Any, *, name: str | None = None) -> None:
        self.routes.append(Mount(path, app=application, name=name))

    def add_startup_hook(self, hook: LifecycleHook) -> None:
        self.startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: LifecycleHook) -> None:
        self.shutdown_hooks.append(hook)

    def set_state(self, name: str, value: Any) -> None:
        self.state[name] = value


class ApplicationModule(Protocol):
    """A module capable of contributing routes and lifecycle hooks."""

    name: str

    def register(self, registry: ApplicationRegistry, context: ModuleContext) -> None: ...


@dataclass(frozen=True, slots=True)
class ModuleBinding:
    """An application module paired with its resolved enabled state."""

    module: ApplicationModule
    enabled: bool


__all__ = [
    "ApplicationModule",
    "ApplicationHandler",
    "ApplicationRegistry",
    "HttpMiddleware",
    "LifecycleHook",
    "ModuleBinding",
    "ModuleContext",
    "RequestHandler",
]
