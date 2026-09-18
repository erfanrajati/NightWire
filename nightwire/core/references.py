"""Reference-safe Core object deletion contracts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from nightwire.core.storage import ObjectId


class ObjectReferenceSource(Protocol):
    def __call__(self, object_id: ObjectId) -> bool:
        """Return whether this source still references the object."""


class ObjectReferenceChecker:
    """Aggregate logical reference sources before physical object deletion."""

    def __init__(self, sources: Iterable[ObjectReferenceSource] = ()) -> None:
        self._sources = list(sources)

    def add_source(self, source: Callable[[ObjectId], bool]) -> None:
        if source not in self._sources:
            self._sources.append(source)

    def is_referenced(self, object_id: ObjectId) -> bool:
        return any(source(object_id) for source in tuple(self._sources))


__all__ = ["ObjectReferenceChecker", "ObjectReferenceSource"]
