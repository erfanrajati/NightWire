import unittest
from datetime import datetime, timezone
from pathlib import Path

from nightwire.text import (
    TextLifecycle, TextMode, TextObject, TextObjectService, TextScopeKind,
    TextValidationError,
)


class TextObjectTests(unittest.TestCase):
    def test_shared_model_round_trips_scope_lifecycle_mode_and_provenance(self):
        service = TextObjectService()
        item = service.build(
            text_id="text-1", title="Example", content="line one\r\nline two",
            mode="code", language="Python", scope_kind=TextScopeKind.DROP,
            scope_id="drop-1", lifecycle=TextLifecycle.TEMPORARY,
            source_kind="core_object", source_id="object-1",
            now=datetime(2026, 9, 18, tzinfo=timezone.utc),
        )
        restored = TextObject.from_record(item.to_record())

        self.assertEqual(item.content, "line one\nline two")
        self.assertEqual(item.mode, TextMode.CODE)
        self.assertEqual(item.language, "python")
        self.assertEqual(restored, item)

    def test_language_is_code_only_and_modes_are_closed(self):
        service = TextObjectService()
        with self.assertRaises(TextValidationError):
            service.build(
                title="Invalid", content="text", mode="plain", language="python",
                scope_kind=TextScopeKind.PERSONAL, scope_id="user",
                lifecycle=TextLifecycle.PERSISTENT,
            )
        with self.assertRaises(TextValidationError):
            service.build(
                title="Invalid", content="text", mode="rich-text",
                scope_kind=TextScopeKind.PERSONAL, scope_id="user",
                lifecycle=TextLifecycle.PERSISTENT,
            )


class CommunityTextFrontendTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def asset(self, name):
        return (self.root / "static" / name).read_text(encoding="utf-8")

    def test_markdown_renderer_never_injects_user_html_or_loads_remote_images(self):
        renderer = self.asset("text-ui.js")

        self.assertNotIn("innerHTML", renderer)
        self.assertNotIn("insertAdjacentHTML", renderer)
        self.assertIn('document.createTextNode', renderer)
        self.assertIn('Remote image omitted', renderer)
        self.assertIn('["http:", "https:", "mailto:"]', renderer)
        self.assertNotIn('document.createElement("img")', renderer)

    def test_editor_covers_save_modes_preview_find_copy_and_responsive_layout(self):
        page = self.asset("text-editor.html")
        script = self.asset("text-editor.js")
        styles = self.asset("text-editor.css")

        for marker in ['value="plain"', 'value="markdown"', 'value="code"', 'id="saveTextButton"',
                       'id="previewPane"', 'id="findText"', 'id="copyTextButton"']:
            self.assertIn(marker, page)
        self.assertIn('method: "PATCH"', script)
        self.assertIn('renderText(elements.previewPane', script)
        self.assertIn('setSelectionRange', script)
        self.assertIn('navigator.clipboard.writeText', script)
        self.assertIn('@media (max-width:700px)', styles)

    def test_drop_and_library_recipient_views_are_explicitly_read_only(self):
        drop_page = self.asset("drop-share.html")
        library_page = self.asset("library-share.html")
        drop_script = self.asset("drop-share.js")
        library_script = self.asset("library-share.js")

        self.assertIn('aria-label="Read-only shared Text"', drop_page)
        self.assertIn('aria-label="Read-only shared Text"', library_page)
        self.assertIn('renderText(elements.textPreview', drop_script)
        self.assertIn('renderText(elements.textPreview', library_script)
        self.assertNotIn('contenteditable', drop_page + library_page)


if __name__ == "__main__":
    unittest.main()
