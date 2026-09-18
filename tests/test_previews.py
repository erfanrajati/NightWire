import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nightwire.core.storage import LocalFilesystemStorage, ObjectId
from nightwire.library.previews import CommunityPreviewService


class ImmediateAsyncFile:
    def __init__(self, path, mode):
        self.file = open(path, mode)

    async def __aenter__(self): return self
    async def __aexit__(self, *_): self.file.close()
    async def read(self, size=-1): return self.file.read(size)
    async def seek(self, offset, whence=0): return self.file.seek(offset, whence)


async def immediate_open_file(path, mode="r"):
    return ImmediateAsyncFile(path, mode)


class CommunityPreviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = LocalFilesystemStorage(Path(self.temporary.name))
        self.previews = CommunityPreviewService(self.storage)
        self.file_patch = mock.patch("nightwire.core.storage.anyio.open_file", new=immediate_open_file)
        self.file_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.temporary.cleanup()

    def store(self, content):
        upload = self.storage.allocate_temporary_upload()
        self.storage.temporary_upload_reference(upload).write_bytes(content)
        return self.storage.finalize_temporary_upload(upload).object_id

    def describe(self, content, name, declared="application/octet-stream", security=None):
        object_id = self.store(content)
        decision = asyncio.run(self.previews.describe(
            object_id, name=name, declared_mime=declared, security=security,
        ))
        return decision, object_id

    def test_stored_bytes_override_spoofed_declared_type(self):
        decision, _ = self.describe(
            b"\x89PNG\r\n\x1a\nnot-a-complete-image", "picture.bin", "text/html",
        )

        self.assertTrue(decision.available)
        self.assertEqual((decision.kind, decision.detected_mime), ("image", "image/png"))

    def test_active_html_and_svg_are_download_only_even_when_spoofed(self):
        html, _ = self.describe(
            b"<!doctype html><script>top.location='https://evil.test'</script>",
            "photo.png", "image/png",
        )
        svg, _ = self.describe(
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            "drawing.svg", "image/svg+xml",
        )

        self.assertFalse(html.available)
        self.assertEqual(html.kind, "active")
        self.assertFalse(svg.available)
        self.assertEqual(svg.kind, "active")

    def test_text_markdown_code_and_binary_fallback_are_classified_without_processing(self):
        markdown, _ = self.describe(b"# Safe\n\nHello", "readme.md", "text/markdown")
        code, _ = self.describe(b"const answer = 42;", "answer.js", "application/javascript")
        binary, _ = self.describe(b"\x00\x01\x02\x03", "unknown.bin")

        self.assertEqual((markdown.available, markdown.kind), (True, "markdown"))
        self.assertEqual((code.available, code.kind, code.language), (True, "code", "javascript"))
        self.assertEqual((binary.available, binary.kind), (False, "unsupported"))

    def test_encrypted_pdf_and_suspicious_content_do_not_preview(self):
        encrypted, _ = self.describe(
            b"%PDF-1.7\n1 0 obj\n<< /Encrypt 2 0 R >>\n", "secret.pdf", "application/pdf",
        )
        suspicious, _ = self.describe(
            b"\x89PNG\r\n\x1a\nimage", "flagged.png", "image/png",
            {"verdict": "suspicious"},
        )

        self.assertEqual((encrypted.available, encrypted.kind), (False, "encrypted"))
        self.assertEqual((suspicious.available, suspicious.kind), (False, "blocked"))


class UnifiedFileDetailFrontendTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def asset(self, name):
        return (self.root / "static" / name).read_text(encoding="utf-8")

    def test_shell_exposes_every_community_file_detail_section(self):
        page = self.asset("file-detail.html")
        for section in ["Preview", "Properties", "Security", "Versions", "Derived Outputs",
                        "Toolkit", "Sharing"]:
            self.assertIn(section, page)
        self.assertIn("object-src 'none'", page)
        self.assertIn("frame-src 'self'", page)

    def test_frontend_uses_sandboxed_pdf_and_dom_safe_text_rendering(self):
        script = self.asset("file-detail.js")

        self.assertIn('frame.setAttribute("sandbox","")', script)
        self.assertIn('renderText(container', script)
        self.assertIn('/preview`', script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn('document.createElement("object")', script)
        self.assertNotIn('document.createElement("embed")', script)


if __name__ == "__main__":
    unittest.main()
