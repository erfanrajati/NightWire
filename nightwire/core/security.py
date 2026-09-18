"""Content-type evidence, security verdicts, and scanner-neutral inspection."""

from __future__ import annotations

import mimetypes
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from nightwire.core.storage import ObjectId, StorageBackend


class SecurityVerdict(StrEnum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"
    SCAN_FAILED = "scan_failed"
    UNSCANNED = "unscanned"


class SecurityAction(StrEnum):
    """Actions whose safety depends on a persisted security verdict."""

    OPAQUE_STORAGE = "opaque_storage"
    DOWNLOAD = "download"
    RISKY_PROCESSING = "risky_processing"


@dataclass(frozen=True, slots=True)
class SecurityPolicyDecision:
    allowed: bool
    reason: str | None = None
    confirmation_required: bool = False


class CoreSecurityPolicy:
    """Central enforcement for actions performed on stored content.

    A malicious verdict is evidence that must be retained, not a reason to
    destroy the object. It may still be downloaded after an explicit
    confirmation, but it must never be passed to a risky processor.
    """

    @staticmethod
    def _verdict(value: SecurityVerdict | str | None) -> SecurityVerdict:
        try:
            return SecurityVerdict(value)
        except (TypeError, ValueError):
            return SecurityVerdict.UNSCANNED

    def evaluate(
        self,
        verdict: SecurityVerdict | str | None,
        action: SecurityAction,
        *,
        confirmed: bool = False,
        risky: bool = True,
    ) -> SecurityPolicyDecision:
        normalized = self._verdict(verdict)
        if action is SecurityAction.OPAQUE_STORAGE:
            return SecurityPolicyDecision(True)
        if action is SecurityAction.DOWNLOAD and normalized is SecurityVerdict.MALICIOUS:
            if confirmed:
                return SecurityPolicyDecision(True)
            return SecurityPolicyDecision(
                False,
                "This Drop was reported as malicious. Deliberate confirmation is required to download it.",
                confirmation_required=True,
            )
        if (
            action is SecurityAction.RISKY_PROCESSING
            and risky
            and normalized is SecurityVerdict.MALICIOUS
        ):
            return SecurityPolicyDecision(
                False,
                "Risky processing is blocked for content reported as malicious.",
            )
        return SecurityPolicyDecision(True)


@dataclass(frozen=True, slots=True)
class PasswordDigest:
    """Backend-neutral password verifier data; plaintext is never retained."""

    salt: str
    digest: str

    def to_dict(self) -> dict[str, str]:
        return {"salt": self.salt, "digest": self.digest}


@dataclass(frozen=True, slots=True)
class MimeDetection:
    mime_type: str
    basis: str
    confidence: str


@dataclass(frozen=True, slots=True)
class MimeComparison:
    filename_extension_mime: str | None
    declared_mime: str | None
    detected_mime: str
    extension_matches_detected: bool | None
    declared_matches_detected: bool | None
    mismatches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MalwareScanResult:
    verdict: SecurityVerdict
    scanner: str
    details: str | None = None
    scanner_version: str | None = None
    signature_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SecurityResult:
    verdict: SecurityVerdict
    detection: MimeDetection
    comparison: MimeComparison
    scanner: str | None
    scanner_version: str | None
    signature_metadata: Mapping[str, Any]
    findings: tuple[str, ...]
    inspected_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "detected_mime": self.detection.mime_type,
            "detection_basis": self.detection.basis,
            "detection_confidence": self.detection.confidence,
            "filename_extension_mime": self.comparison.filename_extension_mime,
            "declared_mime": self.comparison.declared_mime,
            "extension_matches_detected": self.comparison.extension_matches_detected,
            "declared_matches_detected": self.comparison.declared_matches_detected,
            "mismatches": list(self.comparison.mismatches),
            "scanner": self.scanner,
            "scanner_version": self.scanner_version,
            "signature_metadata": dict(self.signature_metadata),
            "findings": list(self.findings),
            "inspected_at": self.inspected_at,
        }


class MalwareScannerAdapter(ABC):
    """Scanner contract addressed by object identity, never a caller path."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable scanner implementation name."""

    @property
    def version(self) -> str | None:
        """Scanner engine/adapter version captured with each scan."""

        return None

    @property
    def signature_metadata(self) -> Mapping[str, Any]:
        """Current signature-set identifiers, versions, or update timestamps."""

        return {}

    @abstractmethod
    async def scan(
        self,
        object_id: ObjectId,
        storage: StorageBackend,
        detected_mime: str,
    ) -> MalwareScanResult:
        """Inspect a stored object and return a normalized scanner result."""


class SecurityPipeline(ABC):
    @abstractmethod
    async def inspect(
        self,
        object_id: ObjectId,
        *,
        filename: str,
        declared_mime: str | None = None,
    ) -> SecurityResult:
        """Detect, compare, scan, and persist one stored object's security result."""


_MIME_ALIASES = {
    "application/x-gzip": "application/gzip",
    "application/x-zip-compressed": "application/zip",
    "image/jpg": "image/jpeg",
    "text/xml": "application/xml",
}


def normalize_mime(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.split(";", 1)[0].strip().lower()
    if not normalized or "/" not in normalized:
        return None
    return _MIME_ALIASES.get(normalized, normalized)


def detect_mime_signature(content: bytes) -> MimeDetection:
    """Detect content type from stored bytes without filename or client MIME input."""

    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png", "png-signature"),
        (b"\xff\xd8\xff", "image/jpeg", "jpeg-signature"),
        (b"GIF87a", "image/gif", "gif-signature"),
        (b"GIF89a", "image/gif", "gif-signature"),
        (b"%PDF-", "application/pdf", "pdf-signature"),
        (b"PK\x03\x04", "application/zip", "zip-signature"),
        (b"PK\x05\x06", "application/zip", "zip-empty-signature"),
        (b"\x1f\x8b\x08", "application/gzip", "gzip-signature"),
        (b"BZh", "application/x-bzip2", "bzip2-signature"),
        (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed", "7zip-signature"),
        (b"Rar!\x1a\x07", "application/vnd.rar", "rar-signature"),
        (b"\x7fELF", "application/x-elf", "elf-signature"),
        (b"MZ", "application/vnd.microsoft.portable-executable", "pe-signature"),
        (b"SQLite format 3\x00", "application/vnd.sqlite3", "sqlite-signature"),
        (b"\x00asm", "application/wasm", "wasm-signature"),
        (b"ID3", "audio/mpeg", "id3-signature"),
        (b"BM", "image/bmp", "bmp-signature"),
    )
    for signature, mime_type, basis in signatures:
        if content.startswith(signature):
            return MimeDetection(mime_type=mime_type, basis=basis, confidence="high")
    if len(content) >= 12 and content[4:8] == b"ftyp":
        # MediaRecorder on Safari emits ISO-BMFF audio. The generic ftyp marker
        # alone does not distinguish audio from video, but M4A/M4B brands and an
        # audio handler in the inspected prefix do.
        brand = content[8:12]
        audio_container = brand in {b"M4A ", b"M4B ", b"M4P "} or (
            b"hdlr" in content and b"soun" in content
        )
        return MimeDetection(
            mime_type="audio/mp4" if audio_container else "video/mp4",
            basis="iso-base-media-audio-signature" if audio_container else "iso-base-media-signature",
            confidence="high",
        )
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return MimeDetection(mime_type="image/webp", basis="webp-signature", confidence="high")
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return MimeDetection(mime_type="image/tiff", basis="tiff-signature", confidence="high")

    sample = content[:65536]
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        decoded = ""
    if decoded and "\x00" not in decoded:
        printable = sum(character.isprintable() or character in "\r\n\t" for character in decoded)
        if printable / len(decoded) >= 0.95:
            leading = decoded.lstrip().lower()
            if leading.startswith("<!doctype html") or leading.startswith("<html"):
                return MimeDetection("text/html", "utf8-html-structure", "medium")
            if leading.startswith("<?xml"):
                return MimeDetection("application/xml", "utf8-xml-declaration", "medium")
            if leading.startswith(("{", "[")):
                return MimeDetection("application/json", "utf8-json-structure", "medium")
            return MimeDetection("text/plain", "utf8-text-content", "medium")
    return MimeDetection("application/octet-stream", "unknown-binary", "low")


def compare_mime_evidence(filename: str, declared_mime: str | None, detected_mime: str) -> MimeComparison:
    extension_mime = normalize_mime(mimetypes.guess_type(filename, strict=False)[0])
    declared = normalize_mime(declared_mime)
    detected = normalize_mime(detected_mime) or "application/octet-stream"
    extension_matches = None if extension_mime is None else extension_mime == detected
    declared_matches = None if declared is None else declared == detected
    mismatches = []
    if extension_matches is False:
        mismatches.append("filename_extension")
    if declared_matches is False:
        mismatches.append("declared_mime")
    return MimeComparison(
        filename_extension_mime=extension_mime,
        declared_mime=declared,
        detected_mime=detected,
        extension_matches_detected=extension_matches,
        declared_matches_detected=declared_matches,
        mismatches=tuple(mismatches),
    )


class CoreSecurityPipeline(SecurityPipeline):
    def __init__(self, storage: StorageBackend, scanner: MalwareScannerAdapter | None = None):
        self.storage = storage
        self.scanner = scanner

    async def inspect(
        self,
        object_id: ObjectId,
        *,
        filename: str,
        declared_mime: str | None = None,
    ) -> SecurityResult:
        async with await self.storage.open_object(object_id, "rb") as source:
            prefix = await source.read(65536)
        detection = detect_mime_signature(prefix)
        comparison = compare_mime_evidence(filename, declared_mime, detection.mime_type)
        findings = [f"mime_mismatch:{source}" for source in comparison.mismatches]
        scanner_name = None
        scanner_version = None
        signature_metadata: Mapping[str, Any] = {}
        scanner_verdict = SecurityVerdict.UNSCANNED
        if self.scanner is not None:
            try:
                scanner_name = self.scanner.name
                scanner_version = self.scanner.version
                signature_metadata = dict(self.scanner.signature_metadata)
                scan = await self.scanner.scan(object_id, self.storage, detection.mime_type)
                scanner_name = scan.scanner
                scanner_version = scan.scanner_version or scanner_version
                signature_metadata = dict(scan.signature_metadata or signature_metadata)
                scanner_verdict = SecurityVerdict(scan.verdict)
                if scan.details:
                    findings.append(scan.details)
            except Exception as exc:
                scanner_verdict = SecurityVerdict.SCAN_FAILED
                if scanner_name is None:
                    scanner_name = type(self.scanner).__name__
                findings.append(f"scanner_error:{type(exc).__name__}")

        if scanner_verdict is SecurityVerdict.MALICIOUS:
            verdict = SecurityVerdict.MALICIOUS
        elif scanner_verdict is SecurityVerdict.SCAN_FAILED:
            verdict = SecurityVerdict.SCAN_FAILED
        elif comparison.mismatches or scanner_verdict is SecurityVerdict.SUSPICIOUS:
            verdict = SecurityVerdict.SUSPICIOUS
        elif scanner_verdict is SecurityVerdict.CLEAN:
            verdict = SecurityVerdict.CLEAN
        else:
            verdict = SecurityVerdict.UNSCANNED

        result = SecurityResult(
            verdict=verdict,
            detection=detection,
            comparison=comparison,
            scanner=scanner_name,
            scanner_version=scanner_version,
            signature_metadata=signature_metadata,
            findings=tuple(findings),
            inspected_at=time.time(),
        )
        persisted = self.storage.load_object_metadata(object_id) or {}
        persisted["security"] = result.to_dict()
        self.storage.save_object_metadata(object_id, persisted)
        return result


__all__ = [
    "CoreSecurityPipeline",
    "CoreSecurityPolicy",
    "MalwareScanResult",
    "MalwareScannerAdapter",
    "MimeComparison",
    "MimeDetection",
    "PasswordDigest",
    "SecurityPipeline",
    "SecurityAction",
    "SecurityPolicyDecision",
    "SecurityResult",
    "SecurityVerdict",
    "compare_mime_evidence",
    "detect_mime_signature",
    "normalize_mime",
]
