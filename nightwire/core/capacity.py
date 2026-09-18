"""Thread-safe Community quota accounting and upload reservations."""
from __future__ import annotations
import shutil, threading, uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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
    @abstractmethod
    def snapshot(self) -> CapacitySnapshot: ...
class CapacityPolicy(ABC):
    @abstractmethod
    def evaluate(self, request: CapacityRequest, capacity: CapacitySnapshot) -> CapacityDecision: ...
class AllowAllCapacityPolicy(CapacityPolicy):
    def evaluate(self, request: CapacityRequest, capacity: CapacitySnapshot) -> CapacityDecision:
        if request.requested_bytes < 0: raise ValueError("Requested capacity cannot be negative.")
        return CapacityDecision(True, remaining_bytes=max(capacity.free_bytes-request.requested_bytes, 0))
class CapacityExceededError(ValueError):
    """An upload would cross an administrator-defined storage boundary."""
@dataclass(frozen=True, slots=True)
class UsageScope:
    kind: str
    id: str = "installation"
@dataclass(slots=True)
class UploadReservation:
    id: str
    scope: UsageScope
    bytes: int = 0
    closed: bool = False
    physical: bool = True
    quota_credit: int = 0
UsageSource = Callable[[UsageScope], int]

class CommunityCapacityManager:
    """Serializes usage checks so parallel streams cannot bypass quotas."""
    def __init__(self, storage_root: Path, *, installation_limit: int = 0,
                 personal_limit: int = 0, workspace_limit: int = 0,
                 drop_limit: int = 0, object_limit: int = 0, minimum_free: int = 0):
        self.storage_root = Path(storage_root)
        self.limits = {"installation": installation_limit, "personal": personal_limit,
                       "workspace": workspace_limit, "drop": drop_limit}
        self.object_limit, self.minimum_free = object_limit, minimum_free
        self._sources: list[UsageSource] = []
        self._reservations: dict[str, UploadReservation] = {}
        self._lock = threading.RLock()
    def add_usage_source(self, source: UsageSource) -> None:
        with self._lock:
            if source not in self._sources: self._sources.append(source)
    def _usage(self, scope: UsageScope) -> int:
        return sum(max(int(source(scope)), 0) for source in tuple(self._sources))
    def _reserved(self, scope: UsageScope | None = None, *, physical_only: bool = False) -> int:
        return sum(r.bytes for r in self._reservations.values()
                   if not r.closed and (scope is None or r.scope == scope)
                   and (not physical_only or r.physical))
    def _check(self, reservation: UploadReservation, prospective: int) -> None:
        if self.object_limit and prospective > self.object_limit:
            raise CapacityExceededError(f"Maximum object size is {self.object_limit} bytes.")
        scope, other_scope = reservation.scope, self._reserved(reservation.scope)-reservation.bytes
        limit = self.limits.get(scope.kind, 0)
        if limit and max(self._usage(scope)-reservation.quota_credit, 0)+other_scope+prospective > limit:
            raise CapacityExceededError(f"{scope.kind.title()} quota of {limit} bytes would be exceeded.")
        if not reservation.physical:
            return
        other = self._reserved(physical_only=True)-reservation.bytes
        installation_limit = self.limits["installation"]
        if installation_limit and self._usage(UsageScope("installation"))+other+prospective > installation_limit:
            raise CapacityExceededError(f"Installation storage limit of {installation_limit} bytes would be exceeded.")
        free = shutil.disk_usage(self.storage_root).free
        if free-other-prospective < self.minimum_free:
            raise CapacityExceededError(f"Host free-space reserve of {self.minimum_free} bytes must remain available.")
    def reserve(self, scope: UsageScope, expected_bytes: int | None = None, *, physical: bool = True,
                quota_credit: int = 0) -> UploadReservation:
        if expected_bytes is not None and expected_bytes < 0: raise CapacityExceededError("Upload size cannot be negative.")
        with self._lock:
            r = UploadReservation(uuid.uuid4().hex, scope, physical=physical,
                                  quota_credit=max(quota_credit, 0)); self._reservations[r.id] = r
            try:
                if expected_bytes is not None: self._check(r, expected_bytes); r.bytes = expected_bytes
            except BaseException:
                self._reservations.pop(r.id, None); raise
            return r
    def consume(self, reservation: UploadReservation, total_bytes: int) -> None:
        with self._lock:
            if reservation.closed: raise RuntimeError("Upload reservation is closed.")
            self._check(reservation, total_bytes); reservation.bytes = max(reservation.bytes, total_bytes)
    def release(self, reservation: UploadReservation | None) -> None:
        if reservation is None: return
        with self._lock:
            reservation.closed = True; self._reservations.pop(reservation.id, None)
    def report(self, scope: UsageScope) -> dict[str, int | None]:
        with self._lock:
            used, reserved, limit = self._usage(scope), self._reserved(scope), self.limits.get(scope.kind, 0)
            return {"used_bytes": used, "reserved_bytes": reserved, "limit_bytes": limit or None,
                    "available_bytes": max(limit-used-reserved, 0) if limit else None}
    def installation_report(self) -> dict[str, int | None]:
        with self._lock:
            used = self._usage(UsageScope("installation"))
            reserved = self._reserved(physical_only=True)
            limit = self.limits["installation"]
            report = {"used_bytes": used, "reserved_bytes": reserved,
                      "limit_bytes": limit or None,
                      "available_bytes": max(limit-used-reserved, 0) if limit else None}
            disk = shutil.disk_usage(self.storage_root)
            return {**report, "host_total_bytes": disk.total, "host_free_bytes": disk.free,
                    "minimum_host_free_bytes": self.minimum_free}

__all__ = ["AllowAllCapacityPolicy", "CapacityDecision", "CapacityExceededError", "CapacityMeter",
           "CapacityPolicy", "CapacityRequest", "CapacitySnapshot", "CommunityCapacityManager",
           "UploadReservation", "UsageScope"]
