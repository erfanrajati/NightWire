"""Application composition package with cycle-safe lazy compatibility exports."""

from __future__ import annotations


_REGISTRATION_EXPORTS = {"ApplicationModule", "ApplicationRegistry", "ModuleBinding", "ModuleContext"}


def __getattr__(name: str):
    if name in {"build_application", "configured_modules"}:
        from nightwire.app import bootstrap

        return getattr(bootstrap, name)
    if name in _REGISTRATION_EXPORTS:
        from nightwire.app import registration

        return getattr(registration, name)
    raise AttributeError(name)


__all__ = [
    "ApplicationModule",
    "ApplicationRegistry",
    "ModuleBinding",
    "ModuleContext",
    "build_application",
    "configured_modules",
]
