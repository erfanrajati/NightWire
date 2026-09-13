"""Drop domain, services, repository, and lazy registration export."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "DropModule":
        from nightwire.drop.registration import DropModule

        return DropModule
    raise AttributeError(name)


__all__ = ["DropModule"]
