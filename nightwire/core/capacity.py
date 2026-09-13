"""Capacity and quota policy contracts for storage-backed modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    total_bytes: int
    used_bytes: int
    free_bytes: int


@dataclass(frozen=True, slots=True)
class CapacityRequest:
    module: str
    requested_bytes: int
    current_module_bytes: int = 0
    current_module_objects: int = 0


@dataclass(frozen=True, slots=True)
class CapacityDecision:
    allowed: bool
    reason: str | None = None
    remaining_bytes: int | None = None


class CapacityMeter(ABC):
    """Report physical storage capacity without deciding module policy."""

    @abstractmethod
    def snapshot(self) -> CapacitySnapshot:
        """Return the current physical capacity snapshot."""


class CapacityPolicy(ABC):
    """Evaluate a module request without coupling Core to module-specific quotas."""

    @abstractmethod
    def evaluate(self, request: CapacityRequest, capacity: CapacitySnapshot) -> CapacityDecision:
        """Return whether a prospective allocation is allowed."""


class AllowAllCapacityPolicy(CapacityPolicy):
    """Compatibility policy used until a module opts into quota enforcement."""

    def evaluate(self, request: CapacityRequest, capacity: CapacitySnapshot) -> CapacityDecision:
        if request.requested_bytes < 0:
            raise ValueError("Requested capacity cannot be negative.")
        return CapacityDecision(
            allowed=True,
            remaining_bytes=max(capacity.free_bytes - request.requested_bytes, 0),
        )


__all__ = [
    "AllowAllCapacityPolicy",
    "CapacityDecision",
    "CapacityMeter",
    "CapacityPolicy",
    "CapacityRequest",
    "CapacitySnapshot",
]
