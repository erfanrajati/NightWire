"""Conservative, format-agnostic preview decisions for Community Library files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from nightwire.core.security import SecurityVerdict, detect_mime_signature, normalize_mime
from nightwire.core.storage import ObjectId, StorageBackend


_ACTIVE_EXTENSIONS = {".html", ".htm", ".xhtml", ".svg", ".xml", ".xsl", ".xslt"}
_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}
_CODE_LANGUAGES = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cs": "csharp", ".css": "css",
    ".go": "go", ".h": "c", ".hpp": "cpp", ".java": "java", ".js": "javascript",
    ".jsx": "javascript", ".json": "json", ".kt": "kotlin", ".php": "php",
    ".py": "python", ".rb": "ruby", ".rs": "rust", ".sh": "shell", ".sql": "sql",
    ".swift": "swift", ".toml": "toml", ".ts": "typescript", ".tsx": "typescript",
    ".yaml": "yaml", ".yml": "yaml",
}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/webm", "audio/flac"}
_VIDEO_TYPES = {"video/mp4", "video/webm", "video/ogg", "video/quicktime"}


@dataclass(frozen=True, slots=True)
class PreviewDecision:
    available: bool
    kind: str
    detected_mime: str
    detection_basis: str
    declared_mime: str | None
    language: str | None = None
    reason: str | None = None
    response_mime: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "kind": self.kind,
            "detected_mime": self.detected_mime,
            "detection_basis": self.detection_basis,
            "declared_mime": self.declared_mime,
            "language": self.language,
            "reason": self.reason,
        }


class CommunityPreviewService:
    """Recognize only browser-safe previews; never parse or transform content."""

    prefix_bytes = 65_536
    tail_bytes = 65_536
    maximum_text_preview_bytes = 2 * 1024 * 1024

    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    @staticmethod
    def security(storage: StorageBackend, object_id: ObjectId) -> dict[str, object]:
        metadata = storage.load_object_metadata(object_id) or {}
        security = metadata.get("security")
        if isinstance(security, dict) and security.get("verdict") in {
            verdict.value for verdict in SecurityVerdict
        }:
            return dict(security)
        return {"verdict": SecurityVerdict.UNSCANNED.value}

    async def describe(
        self, object_id: ObjectId, *, name: str, declared_mime: str | None,
        security: dict[str, object] | None = None,
    ) -> PreviewDecision:
        size = self.storage.object_size(object_id)
        async with await self.storage.open_object(object_id, "rb") as source:
            prefix = await source.read(self.prefix_bytes)
            tail = b""
            if size > self.prefix_bytes:
                await source.seek(max(0, size - self.tail_bytes))
                tail = await source.read(self.tail_bytes)
        declared = normalize_mime(declared_mime)
        detection = detect_mime_signature(prefix)
        detected = detection.mime_type
        basis = detection.basis
        extension = PurePath(name).suffix.lower()
        leading = prefix.lstrip().lower()
        security_record = security or self.security(self.storage, object_id)
        verdict = security_record.get("verdict", SecurityVerdict.UNSCANNED.value)

        if verdict in {SecurityVerdict.MALICIOUS.value, SecurityVerdict.SUSPICIOUS.value}:
            return PreviewDecision(False, "blocked", detected, basis, declared,
                                   reason=f"Preview is disabled for {verdict} content.")
        if extension in _ACTIVE_EXTENSIONS or leading.startswith(
            (b"<!doctype html", b"<html", b"<svg", b"<?xml")
        ):
            return PreviewDecision(
                False, "active", detected, basis, declared,
                reason="Active HTML, SVG, and XML content is download-only for safety.",
            )
        if detected == "application/pdf":
            if b"/encrypt" in prefix.lower() or b"/encrypt" in tail.lower():
                return PreviewDecision(
                    False, "encrypted", detected, basis, declared,
                    reason="Encrypted PDFs are download-only.",
                )
            return PreviewDecision(True, "pdf", detected, basis, declared,
                                   response_mime="application/pdf")
        if detected in _IMAGE_TYPES:
            return PreviewDecision(True, "image", detected, basis, declared,
                                   response_mime=detected)

        signature_media = self._media_signature(prefix, extension, declared)
        if signature_media in _AUDIO_TYPES:
            return PreviewDecision(True, "audio", signature_media, "media-signature", declared,
                                   response_mime=signature_media)
        if signature_media in _VIDEO_TYPES:
            return PreviewDecision(True, "video", signature_media, "media-signature", declared,
                                   response_mime=signature_media)

        text_like = detected in {"text/plain", "application/json"}
        if text_like:
            if size > self.maximum_text_preview_bytes:
                return PreviewDecision(
                    False, "text", detected, basis, declared,
                    reason="This text file is too large for an inline preview.",
                )
            if extension in _MARKDOWN_EXTENSIONS:
                return PreviewDecision(True, "markdown", detected, basis, declared,
                                       response_mime="text/plain; charset=utf-8")
            language = _CODE_LANGUAGES.get(extension)
            if language or declared in {
                "application/javascript", "application/json", "application/sql",
            }:
                return PreviewDecision(True, "code", detected, basis, declared,
                                       language=language or "plain",
                                       response_mime="text/plain; charset=utf-8")
            return PreviewDecision(True, "text", detected, basis, declared,
                                   response_mime="text/plain; charset=utf-8")

        return PreviewDecision(
            False, "unsupported", detected, basis, declared,
            reason="No safe browser preview is available for this content.",
        )

    @staticmethod
    def _media_signature(prefix: bytes, extension: str, declared: str | None) -> str | None:
        if prefix.startswith(b"ID3") or (len(prefix) > 1 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0):
            return "audio/mpeg"
        if prefix.startswith(b"fLaC"):
            return "audio/flac"
        if len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WAVE":
            return "audio/wav"
        if prefix.startswith(b"OggS"):
            return "video/ogg" if extension == ".ogv" or declared == "video/ogg" else "audio/ogg"
        if prefix.startswith(b"\x1aE\xdf\xa3"):
            return "audio/webm" if declared == "audio/webm" or extension in {".weba", ".oga"} else "video/webm"
        if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
            brand = prefix[8:12]
            if brand == b"qt  ":
                return "video/quicktime"
            if brand in {b"M4A ", b"M4B ", b"M4P "} or declared == "audio/mp4":
                return "audio/mp4"
            return "video/mp4"
        return None


__all__ = ["CommunityPreviewService", "PreviewDecision"]
