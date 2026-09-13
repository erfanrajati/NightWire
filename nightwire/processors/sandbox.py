"""Deny-by-default sandbox execution contracts for sensitive processors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from nightwire.core.storage import ObjectId, StorageBackend
from nightwire.processors.base import ProcessorIdentity


@dataclass(frozen=True, slots=True)
class SandboxInput:
    """Read-only logical object made available to a sandbox implementation."""

    object_id: ObjectId
    name: str

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip() or "/" in self.name or "\\" in self.name:
            raise ValueError("Sandbox input names must be normalized basenames.")


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    wall_time_seconds: float = 30.0
    memory_bytes: int = 256 * 1024 * 1024
    output_bytes: int = 8 * 1024 * 1024
    process_count: int = 1

    def __post_init__(self) -> None:
        if self.wall_time_seconds <= 0:
            raise ValueError("Sandbox wall-time limit must be positive.")
        if self.memory_bytes < 1 or self.output_bytes < 1 or self.process_count < 1:
            raise ValueError("Sandbox resource limits must be positive.")


@dataclass(frozen=True, slots=True)
class SandboxExecutionRequest:
    processor: ProcessorIdentity
    executable: str
    arguments: tuple[str, ...] = ()
    inputs: tuple[SandboxInput, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    allow_network: bool = False

    def __post_init__(self) -> None:
        if (
            not self.executable
            or self.executable != self.executable.strip()
            or "/" in self.executable
            or "\\" in self.executable
        ):
            raise ValueError("A sandbox executable name, not a host path, is required.")


class SandboxExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    status: SandboxExecutionStatus
    exit_code: int | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    duration_seconds: float = 0.0
    output_truncated: bool = False
    reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is SandboxExecutionStatus.COMPLETED and self.exit_code == 0


class SandboxExecutor(ABC):
    """Resolve logical inputs and execute them inside an implementation-defined sandbox."""

    @abstractmethod
    async def execute(
        self,
        request: SandboxExecutionRequest,
        storage: StorageBackend,
    ) -> SandboxExecutionResult:
        """Run a bounded sandbox request without exposing host filesystem paths."""


class DenySandboxExecutor(SandboxExecutor):
    """Safe default used until an isolated execution implementation is configured."""

    async def execute(
        self,
        request: SandboxExecutionRequest,
        storage: StorageBackend,
    ) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            status=SandboxExecutionStatus.DENIED,
            reason="No sandbox executor is configured.",
        )


__all__ = [
    "DenySandboxExecutor",
    "SandboxExecutionRequest",
    "SandboxExecutionResult",
    "SandboxExecutionStatus",
    "SandboxExecutor",
    "SandboxInput",
    "SandboxLimits",
]
