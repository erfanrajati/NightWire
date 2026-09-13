"""Registration boundary for the not-yet-implemented Library module."""

from __future__ import annotations

from nightwire.app.registration import ApplicationRegistry, ModuleContext


class LibraryModule:
    """Participate in composition without contributing functionality yet."""

    name = "library"

    def register(self, registry: ApplicationRegistry, context: ModuleContext) -> None:
        return None


__all__ = ["LibraryModule"]
