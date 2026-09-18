import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import app
from app import (
    CLIPBOARD_DEFAULT_EXPIRY_SECONDS,
    CLIPBOARD_HISTORY_LIMIT,
    FILE_DEFAULT_EXPIRY_SECONDS,
    add_clipboard_entry,
    clipboard_snapshot,
    create_password_record,
    delete_clipboard_entry,
    delete_file_record,
    human_file_record,
    normalize_clipboard_expiry,
    normalize_clipboard_text,
    parse_user_agent,
    safe_file_path,
    unlock_clipboard_entry,
    update_clipboard_settings,
    update_file_settings,
    verify_password,
)


async def immediate_run_sync(function, *args, **kwargs):
    """Run the cleanup join inline so Python 3.14 does not retain an AnyIO worker."""
    return function(*args)


class UserAgentTests(unittest.TestCase):
    def test_iphone_safari(self):
        result = parse_user_agent(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
        )
        self.assertEqual(result["device"], "iPhone")
        self.assertEqual(result["browser"], "Safari")
        self.assertEqual(result["browser_version"], "17.5")

    def test_windows_edge(self):
        result = parse_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 "
            "Safari/537.36 Edg/126.0.0.0"
        )
        self.assertEqual(result["device"], "Windows PC")
        self.assertEqual(result["browser"], "Edge")


class PathTests(unittest.TestCase):
    def setUp(self):
        self.old_files_dir = app.FILES_DIR
        self.temp = tempfile.TemporaryDirectory()
        app.FILES_DIR = Path(self.temp.name).resolve()

    def tearDown(self):
        app.FILES_DIR = self.old_files_dir
        self.temp.cleanup()

    def test_filename_is_kept_inside_files_directory(self):
        self.assertEqual(safe_file_path("report.pdf").name, "report.pdf")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_file_path("../secret.txt")

    def test_internal_metadata_filename_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_file_path(app.FILE_METADATA_FILENAME)


class PasswordTests(unittest.TestCase):
    def test_password_record_verifies_without_storing_plaintext(self):
        record = create_password_record("correct horse battery staple")
        self.assertNotIn("correct horse", json.dumps(record))
        self.assertTrue(verify_password("correct horse battery staple", record))
        self.assertFalse(verify_password("wrong", record))


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES.clear()
            app._CLIPBOARD_REVISION = 0

    def test_clipboard_text_preserves_lines_and_normalizes_endings(self):
        self.assertEqual(normalize_clipboard_text("  first\r\nsecond\r  "), "first\nsecond")

    def test_empty_clipboard_text_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_clipboard_text(" \n\t ")

    def test_clipboard_history_is_bounded_and_newest_first(self):
        for index in range(CLIPBOARD_HISTORY_LIMIT + 3):
            add_clipboard_entry(f"clip {index}", "client-12345678", "Test browser", "127.0.0.1")
        revision, entries = clipboard_snapshot()
        self.assertEqual(revision, CLIPBOARD_HISTORY_LIMIT + 3)
        self.assertEqual(len(entries), CLIPBOARD_HISTORY_LIMIT)
        self.assertEqual(entries[0]["text"], f"clip {CLIPBOARD_HISTORY_LIMIT + 2}")
        self.assertEqual(entries[-1]["text"], "clip 3")

    def test_clipboard_expiry_defaults_to_ten_minutes(self):
        self.assertEqual(normalize_clipboard_expiry(None), CLIPBOARD_DEFAULT_EXPIRY_SECONDS)
        _, entry = add_clipboard_entry("temporary", "client-12345678", "Test browser", "127.0.0.1")
        created = app.datetime.fromisoformat(entry["created_at"])
        expires = app.datetime.fromisoformat(entry["expires_at"])
        self.assertAlmostEqual((expires - created).total_seconds(), 10 * 60, delta=1)
        self.assertEqual((entry["text_object_id"], entry["mode"], entry["lifecycle"]),
                         (entry["id"], "plain", "temporary"))
        self.assertEqual(app._CLIPBOARD_ENTRIES[0]["text_object"]["content"], "temporary")

    def test_protected_clipboard_text_is_withheld_and_unlockable(self):
        revision, protected = add_clipboard_entry(
            "top secret", "client-12345678", "Test browser", "127.0.0.1", password="secret-pass"
        )
        self.assertEqual(revision, 1)
        self.assertTrue(protected["password_protected"])
        self.assertIsNone(protected["text"])
        self.assertEqual(protected["text_length"], len("top secret"))
        with self.assertRaises(PermissionError):
            unlock_clipboard_entry(protected["id"], "wrong")
        self.assertEqual(unlock_clipboard_entry(protected["id"], "secret-pass"), "top secret")

    def test_protected_clipboard_countdown_is_public_but_password_is_immutable(self):
        _, entry = add_clipboard_entry(
            "protected", "client-12345678", "Test browser", "127.0.0.1", password="first"
        )
        _, updated = update_clipboard_settings(entry["id"], {"expires_in_seconds": 3600})
        self.assertIsNotNone(updated["expires_at"])
        self.assertTrue(updated["password_protected"])
        with self.assertRaises(ValueError):
            update_clipboard_settings(entry["id"], {"password_action": "remove", "expires_in_seconds": 600})

    def test_protected_clipboard_delete_requires_password(self):
        _, entry = add_clipboard_entry(
            "delete me", "client-12345678", "Test browser", "127.0.0.1", password="delete-pass"
        )
        with self.assertRaises(PermissionError):
            delete_clipboard_entry(entry["id"], "wrong")
        revision, deleted = delete_clipboard_entry(entry["id"], "delete-pass")
        self.assertTrue(deleted)
        self.assertEqual(revision, 2)

    def test_expired_clipboard_entries_are_purged(self):
        add_clipboard_entry("expired", "client-12345678", "Test browser", "127.0.0.1", 60)
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES[0]["expires_at"] = app.utc_iso(app.time.time() - 1)
        revision, entries = clipboard_snapshot()
        self.assertEqual(entries, [])
        self.assertEqual(revision, 2)


class FileLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.old_files_dir = app.FILES_DIR
        self.old_metadata = dict(app._FILE_METADATA)
        self.temp = tempfile.TemporaryDirectory()
        app.FILES_DIR = Path(self.temp.name).resolve()
        app._FILE_METADATA.clear()
        self.file_path = app.FILES_DIR / "report.txt"
        self.file_path.write_text("hello", encoding="utf-8")

    def tearDown(self):
        app.FILES_DIR = self.old_files_dir
        app._FILE_METADATA.clear()
        app._FILE_METADATA.update(self.old_metadata)
        self.temp.cleanup()

    def test_legacy_file_remains_unlimited_while_new_drops_default_to_one_hour(self):
        record = human_file_record(self.file_path)
        self.assertEqual(FILE_DEFAULT_EXPIRY_SECONDS, 3600)
        self.assertIsNone(record["expires_at"])
        self.assertFalse(record["password_protected"])

    def test_file_countdown_can_be_changed_without_password(self):
        app._FILE_METADATA["report.txt"] = {
            "created_at": app.utc_iso(),
            "expires_at": None,
            "password": create_password_record("file-pass"),
        }
        record = update_file_settings("report.txt", {"expires_in_seconds": 3600})
        self.assertTrue(record["password_protected"])
        self.assertIsNotNone(record["expires_at"])
        metadata_text = app.metadata_path().read_text(encoding="utf-8")
        self.assertNotIn("file-pass", metadata_text)

    def test_file_password_is_immutable_and_delete_still_requires_it(self):
        app._FILE_METADATA["report.txt"] = {
            "created_at": app.utc_iso(),
            "expires_at": None,
            "password": create_password_record("file-pass"),
        }
        with self.assertRaises(ValueError):
            update_file_settings("report.txt", {"password_action": "remove", "expires_in_seconds": 600})
        with self.assertRaises(PermissionError):
            delete_file_record("report.txt", "wrong")
        delete_file_record("report.txt", "file-pass")
        self.assertFalse(self.file_path.exists())

    def test_expired_file_is_removed(self):
        update_file_settings("report.txt", {"expires_in_seconds": 60})
        app._FILE_METADATA["report.txt"]["expires_at"] = app.utc_iso(app.time.time() - 1)
        with app._FILES_LOCK:
            changed = app._purge_expired_files_locked()
        self.assertTrue(changed)
        self.assertFalse(self.file_path.exists())


class CleanupWorkerTests(unittest.TestCase):
    def setUp(self):
        self.old_files_dir = app.FILES_DIR
        self.old_metadata = dict(app._FILE_METADATA)
        self.temp = tempfile.TemporaryDirectory()
        app.FILES_DIR = Path(self.temp.name).resolve()
        app._FILE_METADATA.clear()
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES.clear()
            app._CLIPBOARD_REVISION = 0

    def tearDown(self):
        try:
            asyncio.run(app.stop_cleanup_worker())
        except RuntimeError:
            pass
        app.FILES_DIR = self.old_files_dir
        app._FILE_METADATA.clear()
        app._FILE_METADATA.update(self.old_metadata)
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES.clear()
            app._CLIPBOARD_REVISION = 0
        self.temp.cleanup()

    def test_cleanup_worker_enforces_expiry_without_polling(self):
        path = app.FILES_DIR / "temporary.txt"
        path.write_text("temporary", encoding="utf-8")
        app._FILE_METADATA[path.name] = {
            "created_at": app.utc_iso(),
            "expires_at": app.utc_iso(app.time.time() - 1),
            "password": None,
        }
        add_clipboard_entry("temporary text", "client-12345678", "Test browser", "127.0.0.1", 60)
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES[0]["expires_at"] = app.utc_iso(app.time.time() - 1)

        asyncio.run(app.start_cleanup_worker())
        deadline = time.time() + 2.5
        while time.time() < deadline and (path.exists() or clipboard_snapshot()[1]):
            time.sleep(0.05)
        with mock.patch.object(app.anyio.to_thread, "run_sync", new=immediate_run_sync):
            asyncio.run(app.stop_cleanup_worker())

        self.assertFalse(path.exists())
        self.assertEqual(clipboard_snapshot()[1], [])


if __name__ == "__main__":
    unittest.main()
