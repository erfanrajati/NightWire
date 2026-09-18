import asyncio
import base64
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock
from urllib.parse import quote, urlsplit

import app
import nightwire.app.runtime as runtime
from nightwire.core.config import DeploymentProfile
from nightwire.core.security import MalwareScanResult, MalwareScannerAdapter, SecurityVerdict

try:
    from .test_characterization import IsolatedApplicationState, _asgi_request_async, asgi_request, json_request
except ImportError:  # unittest discovery imports test modules from the tests directory.
    from test_characterization import IsolatedApplicationState, _asgi_request_async, asgi_request, json_request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _MaliciousScanner(MalwareScannerAdapter):
    @property
    def name(self):
        return "e2e-scanner"

    @property
    def version(self):
        return "7.1"

    @property
    def signature_metadata(self):
        return {"version": "definitions-42"}

    async def scan(self, object_id, storage, detected_mime):
        return MalwareScanResult(SecurityVerdict.MALICIOUS, self.name, "E2E.Test")


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
        access_key = uploaded.json()["access_key"]
        trusted_manager = replace(
            app.SETTINGS,
            trusted_network_relaxed_access=True,
            trusted_network_active_drop_browsing=True,
        )
        with mock.patch.object(app, "SETTINGS", trusted_manager):
            listed = asgi_request("GET", "/api/files")
        direct = asgi_request("GET", "/download/e2e.bin")
        keyed_direct = asgi_request("GET", f"/download/e2e.bin?key={access_key}")
        downloaded = json_request(
            "POST",
            f"/api/files/e2e.bin/download?key={access_key}",
            {"password": password},
        )
        updated = json_request("PATCH", "/api/files/e2e.bin", {"expires_in_seconds": 3600})
        deleted = json_request("DELETE", "/api/files/e2e.bin", {"password": password})

        self.assertEqual(uploaded.status, 201)
        self.assertEqual([item["name"] for item in listed.json()["files"]], ["e2e.bin"])
        self.assertEqual(direct.status, 403)
        self.assertEqual(keyed_direct.status, 401)
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

    def test_complete_access_key_share_url_serves_recipient_page_and_metadata(self):
        uploaded = asgi_request("PUT", "/api/upload?filename=recipient.txt", body=b"recipient")
        share_url = uploaded.json()["share_url"]
        parsed = urlsplit(share_url)
        target = f"{parsed.path}?{parsed.query}"

        page = asgi_request("GET", target)
        info_target = target.replace("/drop/", "/api/drops/")
        info = asgi_request("GET", info_target)
        missing_key = asgi_request("GET", "/api/drops/recipient.txt")
        wrong_key = asgi_request("GET", "/api/drops/recipient.txt?key=" + "x" * 43)
        download = asgi_request("GET", info.json()["drop"]["download_url"])

        self.assertEqual(page.status, 200)
        self.assertIn(b"PRIVATE DROP", page.body)
        self.assertIn(b"/static/drop-share.js?v=1.0.2", page.body)
        self.assertEqual(info.status, 200)
        self.assertEqual(missing_key.status, 403)
        self.assertEqual(wrong_key.status, 403)
        self.assertEqual(download.status, 200)
        self.assertEqual(download.body, b"recipient")
        self.assertEqual(info.json()["drop"]["name"], "recipient.txt")
        self.assertNotIn("access_key_digest", info.json()["drop"])
        self.assertNotIn("salt", json.dumps(info.json()["drop"]))

    def test_share_url_is_reusable_for_repeated_and_concurrent_authorized_access(self):
        content = b"reusable concurrent Drop"
        uploaded = asgi_request(
            "PUT",
            "/api/drops/files?filename=reusable.txt",
            body=content,
            headers={"content-type": "text/plain"},
        )
        parsed = urlsplit(uploaded.json()["share_url"])
        share_target = f"{parsed.path}?{parsed.query}"
        info_target = share_target.replace("/drop/", "/api/drops/")
        download_target = asgi_request("GET", info_target).json()["drop"]["download_url"]

        repeated_pages = [asgi_request("GET", share_target) for _ in range(3)]
        repeated_metadata = [asgi_request("GET", info_target) for _ in range(3)]

        async def concurrent_downloads():
            return await asyncio.gather(
                *(_asgi_request_async("GET", download_target) for _ in range(5))
            )

        downloads = asyncio.run(concurrent_downloads())

        self.assertTrue(all(response.status == 200 for response in repeated_pages))
        self.assertTrue(all(response.status == 200 for response in repeated_metadata))
        self.assertTrue(all(response.status == 200 and response.body == content for response in downloads))
        transfer_ids = {response.headers["x-nightwire-transfer-id"] for response in downloads}
        self.assertEqual(len(transfer_ids), len(downloads))

    def test_expiry_revokes_share_and_physically_deletes_metadata_sidecar_and_bytes(self):
        uploaded = asgi_request(
            "PUT",
            "/api/drops/files?filename=expires.txt",
            body=b"delete all traces",
            headers={"content-type": "text/plain"},
        )
        share_url = urlsplit(uploaded.json()["share_url"])
        info_target = f"/api/drops/expires.txt?{share_url.query}"
        object_id = app.ObjectId.parse(app._FILE_METADATA["expires.txt"]["object_id"])
        object_path = app.current_storage_backend().object_reference(object_id)
        sidecar_path = app.current_storage_backend().object_metadata_reference(object_id)
        app._FILE_METADATA["expires.txt"]["expires_at"] = app.utc_iso(0)
        app._save_file_metadata_locked()

        expired = asgi_request("GET", info_target)

        self.assertEqual(expired.status, 404)
        self.assertNotIn("expires.txt", app._FILE_METADATA)
        self.assertFalse(object_path.exists())
        self.assertFalse(sidecar_path.exists())
        self.assertNotIn("expires.txt", app.metadata_path().read_text(encoding="utf-8"))

    def test_malicious_drop_api_reports_evidence_and_requires_confirmed_download(self):
        with mock.patch.object(app.SECURITY_PIPELINE, "scanner", _MaliciousScanner()):
            uploaded = asgi_request(
                "PUT",
                "/api/drops/files?filename=malicious.txt",
                body=b"retained malicious fixture",
                headers={"content-type": "text/plain"},
            )
        payload = uploaded.json()
        key = payload["access_key"]
        info = asgi_request("GET", f"/api/drops/malicious.txt?key={key}")
        denied = asgi_request("GET", f"/download/malicious.txt?key={key}")
        confirmed = asgi_request(
            "GET",
            f"/download/malicious.txt?key={key}&confirm_malicious=true",
        )

        self.assertEqual(uploaded.status, 201)
        self.assertEqual(payload["file"]["security"]["verdict"], "malicious")
        self.assertEqual(info.json()["drop"]["security"]["scanner"], "e2e-scanner")
        self.assertEqual(info.json()["drop"]["security"]["scanner_version"], "7.1")
        self.assertEqual(denied.status, 409)
        self.assertTrue(denied.json()["confirmation_required"])
        self.assertEqual(confirmed.status, 200)
        self.assertEqual(confirmed.body, b"retained malicious fixture")

    def test_protected_malicious_drop_requires_both_confirmation_and_password(self):
        password = "correct horse"
        encoded = base64.b64encode(password.encode()).decode()
        with mock.patch.object(app.SECURITY_PIPELINE, "scanner", _MaliciousScanner()):
            uploaded = asgi_request(
                "PUT",
                "/api/drops/files?filename=protected-malicious.txt",
                body=b"protected retained fixture",
                headers={
                    "content-type": "text/plain",
                    "x-nightwire-password-b64": encoded,
                },
            )
        key = uploaded.json()["access_key"]
        endpoint = f"/api/files/protected-malicious.txt/download?key={key}"
        unconfirmed = json_request("POST", endpoint, {"password": password})
        wrong_password = json_request(
            "POST",
            endpoint,
            {"password": "wrong", "confirm_malicious": True},
        )
        confirmed = json_request(
            "POST",
            endpoint,
            {"password": password, "confirm_malicious": True},
        )

        self.assertEqual(unconfirmed.status, 409)
        self.assertEqual(wrong_password.status, 403)
        self.assertEqual(confirmed.status, 200)
        self.assertEqual(confirmed.body, b"protected retained fixture")

    def test_new_drop_api_creates_files_text_and_voice_through_core_storage(self):
        file_upload = asgi_request(
            "PUT",
            "/api/drops/files?filename=new-api.bin",
            body=b"\x00binary\xff",
            headers={"content-type": "application/octet-stream"},
        )
        text_upload = json_request(
            "POST",
            "/api/drops/text",
            {"title": "Snippet", "text": "pasted\ntext", "mode": "code",
             "language": "python", "expires_in_seconds": 600},
        )
        voice_upload = asgi_request(
            "PUT",
            "/api/drops/files?filename=voice.webm",
            body=b"webm-audio",
            headers={
                "content-type": "audio/webm",
                "x-nightwire-drop-kind": "voice",
                "x-nightwire-expires-in-seconds": "1800",
            },
        )

        self.assertEqual(file_upload.status, 201)
        self.assertEqual(text_upload.status, 201)
        self.assertEqual(voice_upload.status, 201)
        self.assertEqual(file_upload.json()["file"]["content_kind"], "file")
        self.assertEqual(text_upload.json()["file"]["content_kind"], "text")
        self.assertEqual(text_upload.json()["file"]["text"]["title"], "Snippet")
        self.assertEqual(text_upload.json()["file"]["text"]["mode"], "code")
        self.assertEqual(text_upload.json()["file"]["text"]["lifecycle"], "temporary")
        self.assertEqual(voice_upload.json()["file"]["content_kind"], "voice")
        metadata = json.loads(app.metadata_path().read_text(encoding="utf-8"))
        self.assertEqual({record["content_kind"] for record in metadata.values()}, {"file", "text", "voice"})
        for record in metadata.values():
            self.assertIn("object_id", record)
            self.assertEqual(len(record["checksum_sha256"]), 64)
        text_record = next(record for record in metadata.values() if record["content_kind"] == "text")
        self.assertEqual(text_record["text_object"]["language"], "python")
        self.assertNotIn("content", text_record["text_object"])

    def test_active_drop_api_obeys_profile_and_trusted_key_policy(self):
        uploaded = asgi_request("PUT", "/api/drops/files?filename=active.txt", body=b"active")
        default_list = asgi_request("GET", "/api/drops")
        self.assertEqual(default_list.status, 403)

        relaxed = replace(
            app.SETTINGS,
            trusted_network_relaxed_access=True,
            trusted_network_active_drop_browsing=True,
        )
        with mock.patch.object(app, "SETTINGS", relaxed):
            relaxed_list = asgi_request("GET", "/api/drops")
            keyless = asgi_request("GET", "/download/active.txt")
        self.assertEqual(relaxed_list.status, 200)
        self.assertEqual(relaxed_list.json()["drops"][0]["share_url"], "http://testserver:8080/drop/active.txt")
        self.assertEqual(relaxed_list.json()["drops"][0]["download_url"], "/download/active.txt")
        self.assertEqual(keyless.body, b"active")

        internet = replace(
            relaxed,
            deployment_profile=DeploymentProfile.INTERNET_FACING,
            trusted_network_active_drop_browsing=True,
        )
        with mock.patch.object(app, "SETTINGS", internet):
            denied = asgi_request("GET", "/api/drops")
            still_keyed = asgi_request("GET", "/download/active.txt")
            over_limit = asgi_request(
                "PUT",
                "/api/drops/files?filename=too-long.txt",
                body=b"too long",
                headers={"x-nightwire-expires-in-seconds": "86401"},
            )
        self.assertEqual(denied.status, 403)
        self.assertEqual(still_keyed.status, 403)
        self.assertEqual(over_limit.status, 400)
        self.assertIn("active drop browsing", denied.json()["error"].lower())
        self.assertIn("24 hours", over_limit.json()["error"])
        self.assertRegex(uploaded.json()["access_key"], r"^[A-Za-z0-9_-]{43}$")
        self.assertIn("?key=", uploaded.json()["share_url"])

    def test_qr_endpoint_receives_the_exact_complete_share_url(self):
        target = "http://testserver:8080/drop/report%20final.bin?key=abc_123-XYZ"
        captured = []

        class FakeImage:
            def save(self, output):
                output.write(b"<svg/>")

        class FakeQr:
            def add_data(self, value):
                captured.append(value)

            def make(self, fit):
                self.fit = fit

            def make_image(self, image_factory):
                return FakeImage()

        with mock.patch.object(app.qrcode, "QRCode", return_value=FakeQr()):
            response = asgi_request("GET", f"/api/qr?url={quote(target, safe='')}")

        self.assertEqual(response.status, 200)
        self.assertEqual(captured, [target])

    def test_frontend_exposes_text_voice_expiry_active_browsing_and_exact_share_qr(self):
        page = asgi_request("GET", "/files").body
        script = asgi_request("GET", "/static/drop.js").body

        for marker in [b"dropTextInput", b"recordVoiceButton", b"voiceCaptureInput", b"voiceVisualizer", b"fileExpiryPreset", b"activeDropsPanel", b"shareQrImage"]:
            self.assertIn(marker, page)
        for marker in [b"MediaRecorder", b"getUserMedia", b"audio/mp4", b"recorder.start(250)", b'api("/api/drops/text"', b"/api/drops/files?filename=", b"encodeURIComponent(url)"]:
            self.assertIn(marker, script)
        share_page = asgi_request("GET", "/static/drop-share.html").body
        share_script = asgi_request("GET", "/static/drop-share.js").body
        self.assertIn(b"dropSecurityWarning", share_page)
        self.assertIn(b"dropImagePreview", share_page)
        self.assertIn(b"dropAudioPlayer", share_page)
        self.assertIn(b"Read-only shared Text", share_page)
        self.assertIn(b"renderText(elements.textPreview", share_script)
        self.assertNotIn(b" controls", share_page)
        self.assertIn(b"Hold to download malicious Drop", share_script)
        self.assertIn(b"confirm_malicious", share_script)
        self.assertIn(b"loadInlinePreview", share_script)
        self.assertIn(b"audioPlayButton", share_script)
        for verdict in [b"suspicious", b"malicious", b"scan_failed", b"unscanned"]:
            self.assertIn(verdict, script)
            self.assertIn(verdict, share_script)

    def test_primary_drop_screen_is_centered_on_the_minimal_secure_workflow(self):
        page = asgi_request("GET", "/files").body

        for marker in [
            b"Burn after",
            b"Drop a file here",
            b"Paste text",
            b"Record a message",
            b"Active Drops",
        ]:
            self.assertIn(marker, page)
        self.assertEqual(page.count(b'id="fileExpiryPreset"'), 1)
        self.assertLess(page.index(b"Drop a file here"), page.index(b"Record a message"))
        self.assertLess(page.index(b"Record a message"), page.index(b"Paste text"))
        self.assertNotIn(b"browseButton", page)
        self.assertNotIn(b"Share one thing.", page)
        self.assertNotIn(b"quick-stats", page)
        self.assertNotIn(b"searchInput", page)
        self.assertNotIn(b"filePassword", page)
        self.assertNotIn(b"main-navigation", page)

    def test_security_headers_allow_blob_audio_for_custom_voice_playback(self):
        response = asgi_request("GET", "/drop/missing.txt")

        self.assertIn("media-src 'self' blob:", response.headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
