"""Versioned content-processor contracts and deterministic execution results."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nightwire.core.security import CoreSecurityPolicy, SecurityAction, SecurityVerdict
from nightwire.core.storage import ObjectId, StorageBackend


@dataclass(frozen=True, slots=True)
class ProcessorIdentity:
    name: str
    version: str

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip():
            raise ValueError("A normalized processor name is required.")
        if not self.version or self.version != self.version.strip():
            raise ValueError("A normalized processor version is required.")


class ProcessorExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class DerivedObject:
    """A stored object produced from another object by a processor."""

    object_id: ObjectId
    relationship: str
    filename: str | None = None
    mime_type: str | None = None
    size: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.relationship or self.relationship != self.relationship.strip():
            raise ValueError("A normalized derived-object relationship is required.")
        if self.size is not None and self.size < 0:
            raise ValueError("Derived-object size cannot be negative.")


@dataclass(frozen=True, slots=True)
class ProcessorExecutionResult:
    identity: ProcessorIdentity
    status: ProcessorExecutionStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)
    derived_objects: tuple[DerivedObject, ...] = ()
    error: str | None = None
    started_at: float | None = None
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.status is ProcessorExecutionStatus.SUCCEEDED and self.error is not None:
            raise ValueError("A successful processor result cannot contain an error.")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("Processor duration cannot be negative.")

    @property
    def processor(self) -> str:
        """Compatibility projection for callers that previously read a name string."""

        return self.identity.name

    @property
    def processor_version(self) -> str:
        return self.identity.version

    @property
    def succeeded(self) -> bool:
        return self.status is ProcessorExecutionStatus.SUCCEEDED

    @classmethod
    def success(
        cls,
        identity: ProcessorIdentity,
        *,
        metadata: Mapping[str, Any] | None = None,
        derived_objects: Iterable[DerivedObject] = (),
        started_at: float | None = None,
        duration_seconds: float | None = None,
    ) -> ProcessorExecutionResult:
        return cls(
            identity=identity,
            status=ProcessorExecutionStatus.SUCCEEDED,
            metadata=metadata or {},
            derived_objects=tuple(derived_objects),
            started_at=started_at,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def failure(
        cls,
        identity: ProcessorIdentity,
        error: str,
        *,
        started_at: float | None = None,
        duration_seconds: float | None = None,
    ) -> ProcessorExecutionResult:
        return cls(
            identity=identity,
            status=ProcessorExecutionStatus.FAILED,
            error=error,
            started_at=started_at,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def skipped(cls, identity: ProcessorIdentity, reason: str | None = None) -> ProcessorExecutionResult:
        return cls(identity=identity, status=ProcessorExecutionStatus.SKIPPED, error=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "processor": self.identity.name,
            "processor_version": self.identity.version,
            "status": self.status.value,
            "succeeded": self.succeeded,
            "metadata": dict(self.metadata),
            "derived_objects": [
                {
                    "object_id": str(derived.object_id),
                    "relationship": derived.relationship,
                    "filename": derived.filename,
                    "mime_type": derived.mime_type,
                    "size": derived.size,
                    "metadata": dict(derived.metadata),
                }
                for derived in self.derived_objects
            ],
            "error": self.error,
            "started_at": self.started_at,
            "duration_seconds": self.duration_seconds,
        }


# Compatibility import name retained while callers migrate to ProcessorExecutionResult.
ProcessorResult = ProcessorExecutionResult


@dataclass(frozen=True, slots=True)
class ProcessorContext:
    object_id: ObjectId
    storage: StorageBackend
    filename: str
    detected_mime: str
    size: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
    security_verdict: SecurityVerdict | str | None = SecurityVerdict.UNSCANNED


class ContentProcessor(ABC):
    """Optional post-storage transformation or analysis contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable registry name."""

    @property
    def version(self) -> str:
        """Implementation version persisted with every execution result."""

        return "1"

    @property
    def identity(self) -> ProcessorIdentity:
        return ProcessorIdentity(self.name, self.version)

    @property
    def is_risky(self) -> bool:
        """Whether this processor parses or executes content from the object."""

        return True

    @abstractmethod
    def supports(self, context: ProcessorContext) -> bool:
        """Return whether this processor accepts the stored content."""

    @abstractmethod
    async def process(self, context: ProcessorContext) -> ProcessorExecutionResult:
        """Process content without assuming a local filesystem path."""


class ProcessorRegistry:
    def __init__(
        self,
        processors: Iterable[ContentProcessor] = (),
        *,
        security_policy: CoreSecurityPolicy | None = None,
    ):
        self._processors: dict[str, ContentProcessor] = {}
        self.security_policy = security_policy or CoreSecurityPolicy()
        for processor in processors:
            self.register(processor)

    def register(self, processor: ContentProcessor) -> None:
        identity = processor.identity
        if identity.name in self._processors:
            current = self._processors[identity.name]
            raise ValueError(
                f"Processor '{identity.name}' is already registered at version {current.version}."
            )
        self._processors[identity.name] = processor

    def unregister(self, name: str) -> None:
        self._processors.pop(name, None)

    def get(self, name: str) -> ContentProcessor | None:
        return self._processors.get(name)

    def all(self) -> tuple[ContentProcessor, ...]:
        return tuple(self._processors.values())

    def applicable(self, context: ProcessorContext) -> tuple[ContentProcessor, ...]:
        return tuple(
            processor
            for processor in self._processors.values()
            if self.security_policy.evaluate(
                context.security_verdict,
                SecurityAction.RISKY_PROCESSING,
                risky=processor.is_risky,
            ).allowed
            and processor.supports(context)
        )

    async def process(self, context: ProcessorContext) -> tuple[ProcessorExecutionResult, ...]:
        results = []
        for processor in self._processors.values():
            decision = self.security_policy.evaluate(
                context.security_verdict,
                SecurityAction.RISKY_PROCESSING,
                risky=processor.is_risky,
            )
            if not decision.allowed:
                results.append(ProcessorExecutionResult.skipped(processor.identity, decision.reason))
                continue
            if not processor.supports(context):
                continue
            started_at = time.time()
            started = time.perf_counter()
            try:
                result = await processor.process(context)
            except Exception as exc:
                result = ProcessorExecutionResult.failure(
                    processor.identity,
                    type(exc).__name__,
                    started_at=started_at,
                    duration_seconds=max(time.perf_counter() - started, 0.0),
                )
            if result.identity != processor.identity:
                raise ValueError("Processor results must use their registered name and version.")
            results.append(result)
        return tuple(results)


__all__ = [
    "ContentProcessor",
    "DerivedObject",
    "ProcessorContext",
    "ProcessorExecutionResult",
    "ProcessorExecutionStatus",
    "ProcessorIdentity",
    "ProcessorRegistry",
    "ProcessorResult",
]
