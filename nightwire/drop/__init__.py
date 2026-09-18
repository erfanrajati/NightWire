"""Drop domain, services, repository, and lazy registration export."""

from __future__ import annotations

from nightwire.drop.access import DropAccessKeyPolicy
from nightwire.drop.domain import AccessKeyDigest


def __getattr__(name: str):
    if name == "DropModule":
        from nightwire.drop.registration import DropModule

        return DropModule
    raise AttributeError(name)


__all__ = ["AccessKeyDigest", "DropAccessKeyPolicy", "DropModule"]
