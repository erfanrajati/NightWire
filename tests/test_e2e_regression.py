import base64
import json
import unittest
from pathlib import Path

import app
import nightwire.app.runtime as runtime

try:
    from .test_characterization import IsolatedApplicationState, asgi_request, json_request
except ImportError:  # unittest discovery imports test modules from the tests directory.
    from test_characterization import IsolatedApplicationState, asgi_request, json_request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CompatibilityEntryPointTests(unittest.TestCase):
    def test_root_app_module_is_a_small_alias_to_the_package_runtime(self):
        self.assertIs(app, runtime)
        self.assertLessEqual(len((PROJECT_ROOT / "app.py").read_text(encoding="utf-8").splitlines()), 20)


class RefactoredApplicationEndToEndTests(IsolatedApplicationState):
    def test_drop_upload_list_settings_protected_download_and_delete_flow(self):
        password = "correct horse"
        encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
        payload = b"end-to-end\x00Drop\xff"

        uploaded = asgi_request(
            "PUT",
            "/api/upload?filename=e2e.bin",
            body=[payload[:5], payload[5:]],
            headers={"x-nightwire-password-b64": encoded},
        )
        listed = asgi_request("GET", "/api/files")
        direct = asgi_request("GET", "/download/e2e.bin")
        downloaded = json_request(
            "POST",
            "/api/files/e2e.bin/download",
            {"password": password},
        )
        updated = json_request("PATCH", "/api/files/e2e.bin", {"expires_in_seconds": 3600})
        deleted = json_request("DELETE", "/api/files/e2e.bin", {"password": password})

        self.assertEqual(uploaded.status, 201)
        self.assertEqual([item["name"] for item in listed.json()["files"]], ["e2e.bin"])
        self.assertEqual(direct.status, 401)
        self.assertEqual(downloaded.status, 200)
        self.assertEqual(downloaded.body, payload)
        self.assertIsNotNone(updated.json()["file"]["expires_at"])
        self.assertEqual(deleted.status, 200)
        self.assertEqual(json.loads(app.metadata_path().read_text(encoding="utf-8")), {})

    def test_clipboard_and_client_visibility_remain_available_through_drop_facades(self):
        heartbeat = json_request(
            "POST",
            "/api/clients/heartbeat",
            {"client_id": "browser-12345678", "platform": "Linux"},
        )
        shared = json_request(
            "POST",
            "/api/clipboard",
            {"client_id": "browser-12345678", "text": "shared text"},
        )
        snapshot = asgi_request("GET", "/api/clipboard?since_revision=-1")

        self.assertEqual(heartbeat.status, 200)
        self.assertEqual(heartbeat.json()["devices"][1]["id"], "browser-12345678")
        self.assertEqual(shared.status, 201)
        self.assertEqual(snapshot.json()["entries"][0]["text"], "shared text")

    def test_shared_shell_loads_the_drop_owned_frontend_module(self):
        page = asgi_request("GET", "/files")
        shell = asgi_request("GET", "/static/app.js")
        drop = asgi_request("GET", "/static/drop.js")

        self.assertEqual(page.status, 200)
        self.assertIn(b'type="module" src="/static/app.js?v=1.0.2"', page.body)
        self.assertIn(b'import { startDrop }', shell.body)
        self.assertIn(b'export { start as startDrop }', drop.body)


if __name__ == "__main__":
    unittest.main()
