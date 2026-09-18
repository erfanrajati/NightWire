import asyncio
import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from unittest import mock
from urllib.parse import quote, unquote, urlsplit

import app
from nightwire.core.transfer import TransferDirection, TransferPhase


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _ImmediateAsyncFile:
    """Small synchronous-file adapter that keeps ASGI tests off AnyIO worker threads."""

    def __init__(self, path, mode="r", *args, **kwargs):
        self._file = open(path, mode, *args, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._file.close()

    async def read(self, size=-1):
        return self._file.read(size)

    async def write(self, data):
        return self._file.write(data)

    async def seek(self, offset, whence=0):
        return self._file.seek(offset, whence)

    async def flush(self):
        return self._file.flush()


async def _immediate_open_file(path, mode="r", *args, **kwargs):
    return _ImmediateAsyncFile(path, mode, *args, **kwargs)


async def _immediate_run_sync(function, *args, **kwargs):
    return function(*args)


@dataclass
class _CapturedResponse:
    status: int | None
    headers: dict[str, str]
    body: bytes
    exception: BaseException | None = None

    def json(self):
        return json.loads(self.body.decode("utf-8"))


async def _asgi_request_async(method, target, *, body=b"", headers=None, client=("127.0.0.1", 43000), disconnect=False):
    parsed = urlsplit(target)
    chunks = list(body) if isinstance(body, (list, tuple)) else [body]
    request_messages = []
    for index, chunk in enumerate(chunks):
        request_messages.append(
            {
                "type": "http.request",
                "body": chunk,
                "more_body": disconnect or index < len(chunks) - 1,
            }
        )
    if disconnect:
        request_messages.append({"type": "http.disconnect"})

    raw_headers = {"host": "testserver:8080"}
    raw_headers.update({key.lower(): value for key, value in (headers or {}).items()})
    if not disconnect and "content-length" not in raw_headers:
        raw_headers["content-length"] = str(sum(len(chunk) for chunk in chunks))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": unquote(parsed.path),
        "raw_path": parsed.path.encode("ascii"),
        "query_string": parsed.query.encode("ascii"),
        "root_path": "",
        "headers": [(key.encode("latin-1"), value.encode("latin-1")) for key, value in raw_headers.items()],
        "client": client,
        "server": ("testserver", 8080),
        "extensions": {},
    }

    message_index = 0

    async def receive():
        nonlocal message_index
        if message_index < len(request_messages):
            message = request_messages[message_index]
            message_index += 1
            return message
        return {"type": "http.disconnect"}

    sent = []

    async def send(message):
        sent.append(message)

    caught = None
    with mock.patch.object(app.anyio, "open_file", new=_immediate_open_file), mock.patch.object(
        app.anyio.to_thread, "run_sync", new=_immediate_run_sync
    ):
        try:
            await app.app(scope, receive, send)
        except BaseException as exc:  # ServerErrorMiddleware sends a 500 and then re-raises.
            caught = exc

    start = next((message for message in sent if message["type"] == "http.response.start"), None)
    response_headers = {}
    if start:
        response_headers = {
            key.decode("latin-1").lower(): value.decode("latin-1") for key, value in start.get("headers", [])
        }
    response_body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return _CapturedResponse(start["status"] if start else None, response_headers, response_body, caught)


def asgi_request(method, target, *, body=b"", headers=None, client=("127.0.0.1", 43000), disconnect=False):
    return asyncio.run(
        _asgi_request_async(method, target, body=body, headers=headers, client=client, disconnect=disconnect)
    )


def json_request(method, target, payload=None, *, client=("127.0.0.1", 43000)):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return asgi_request(
        method,
        target,
        body=body,
        headers={"content-type": "application/json"},
        client=client,
    )


class IsolatedApplicationState(unittest.TestCase):
    def setUp(self):
        self._old_files_dir = app.FILES_DIR
        self._old_file_metadata = copy.deepcopy(app._FILE_METADATA)
        with app._CLIPBOARD_LOCK:
            self._old_clipboard_entries = copy.deepcopy(app._CLIPBOARD_ENTRIES)
            self._old_clipboard_revision = app._CLIPBOARD_REVISION
            app._CLIPBOARD_ENTRIES.clear()
            app._CLIPBOARD_REVISION = 0
        with app._CLIENTS_LOCK:
            self._old_active_clients = copy.deepcopy(app._ACTIVE_CLIENTS)
            app._ACTIVE_CLIENTS.clear()

        self._temporary_directory = tempfile.TemporaryDirectory()
        app.FILES_DIR = Path(self._temporary_directory.name).resolve()
        app._FILE_METADATA.clear()

    def tearDown(self):
        app.FILES_DIR = self._old_files_dir
        app._FILE_METADATA.clear()
        app._FILE_METADATA.update(self._old_file_metadata)
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES[:] = self._old_clipboard_entries
            app._CLIPBOARD_REVISION = self._old_clipboard_revision
        with app._CLIENTS_LOCK:
            app._ACTIVE_CLIENTS.clear()
            app._ACTIVE_CLIENTS.update(self._old_active_clients)
        self._temporary_directory.cleanup()

    def create_file(self, name, data, *, password=None, expires_at=None):
        path = app.FILES_DIR / name
        path.write_bytes(data)
        app._FILE_METADATA[name] = {
            "created_at": app.utc_iso(),
            "expires_at": expires_at,
            "password": app.create_password_record(password) if password else None,
        }
        app._save_file_metadata_locked()
        return path


class FileUploadCharacterizationTests(IsolatedApplicationState):
    def test_successful_upload_preserves_filename_bytes_and_metadata(self):
        filename = "report final.bin"
        payload = [b"\x00\xffNight", b"Wire\r\n\x10"]

        response = asgi_request(
            "PUT",
            f"/api/upload?filename={quote(filename)}",
            body=payload,
            headers={"x-nightwire-expires-in-seconds": "600"},
        )

        self.assertIsNone(response.exception)
        self.assertEqual(response.status, 201)
        result = response.json()
        self.assertEqual(result["file"]["name"], filename)
        self.assertEqual(len(result["transfer_id"]), 32)
        self.assertEqual(result["bytes_written"], len(b"".join(payload)))
        self.assertFalse(result["file"]["password_protected"])
        self.assertTrue(result["file"]["access_key_required"])
        self.assertRegex(result["access_key"], r"^[A-Za-z0-9_-]{43}$")
        self.assertIn(f"/drop/{quote(filename)}?key=", result["share_url"])
        self.assertEqual(len(result["checksum_sha256"]), 64)

        metadata = json.loads(app.metadata_path().read_text(encoding="utf-8"))
        self.assertEqual(set(metadata), {filename})
        self.assertIsNone(metadata[filename]["password"])
        self.assertNotIn(result["access_key"], json.dumps(metadata))
        self.assertEqual(metadata[filename]["access_key_digest"]["algorithm"], "sha256-v1")
        object_id = app.ObjectId.parse(metadata[filename]["object_id"])
        self.assertEqual(
            app.current_storage_backend().object_reference(object_id).read_bytes(),
            b"".join(payload),
        )
        self.assertFalse((app.FILES_DIR / filename).exists())
        self.assertEqual(metadata[filename]["checksum_sha256"], result["checksum_sha256"])
        self.assertEqual(metadata[filename]["security"]["verdict"], "unscanned")
        self.assertEqual(metadata[filename]["security"]["detected_mime"], "application/octet-stream")
        self.assertEqual(
            app.current_storage_backend().load_object_metadata(object_id)["security"],
            metadata[filename]["security"],
        )
        self.assertEqual(list(app.current_storage_backend().temporary_uploads_root.iterdir()), [])
        created = app.parse_iso_timestamp(metadata[filename]["created_at"])
        expires = app.parse_iso_timestamp(metadata[filename]["expires_at"])
        self.assertAlmostEqual(expires - created, 600, delta=1)

    def test_object_id_and_checksum_survive_metadata_reload(self):
        filename = "persistent name.bin"
        payload = b"stable object identity\x00\xff"

        response = asgi_request("PUT", f"/api/upload?filename={quote(filename)}", body=payload)
        self.assertEqual(response.status, 201)
        original_record = dict(app._FILE_METADATA[filename])

        app._FILE_METADATA.clear()
        app._load_file_metadata()

        self.assertEqual(app._FILE_METADATA[filename]["object_id"], original_record["object_id"])
        self.assertEqual(app._FILE_METADATA[filename]["checksum_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(app._FILE_METADATA[filename]["security"]["verdict"], "unscanned")
        access_key = response.json()["access_key"]
        download = asgi_request(
            "GET", f"/download/{quote(filename)}?key={quote(access_key)}"
        )
        self.assertEqual(download.status, 200)
        self.assertEqual(download.body, payload)
        self.assertIn("persistent%20name.bin", download.headers["content-disposition"])
        transfer_id = download.headers["x-nightwire-transfer-id"]
        progress = app.TRANSFER_PROGRESS.get(transfer_id)
        self.assertEqual(progress.direction, TransferDirection.DOWNLOAD)
        self.assertEqual(progress.phase, TransferPhase.COMPLETED)
        self.assertEqual(progress.bytes_transferred, len(payload))

    def test_upload_persists_mime_mismatch_as_suspicious_security_evidence(self):
        payload = b"\x89PNG\r\n\x1a\n" + b"image bytes"

        response = asgi_request(
            "PUT",
            "/api/upload?filename=disguised.txt",
            body=payload,
            headers={"content-type": "image/jpeg"},
        )

        self.assertEqual(response.status, 201)
        security = app._FILE_METADATA["disguised.txt"]["security"]
        self.assertEqual(security["verdict"], "suspicious")
        self.assertEqual(security["detected_mime"], "image/png")
        self.assertEqual(security["mismatches"], ["filename_extension", "declared_mime"])

    def test_unprotected_existing_file_is_replaced(self):
        self.create_file("replace.bin", b"old")

        response = asgi_request("PUT", "/api/upload?filename=replace.bin", body=b"new bytes")

        self.assertEqual(response.status, 201)
        object_id = app.ObjectId.parse(app._FILE_METADATA["replace.bin"]["object_id"])
        self.assertEqual(app.current_storage_backend().object_reference(object_id).read_bytes(), b"new bytes")
        self.assertFalse((app.FILES_DIR / "replace.bin").exists())
        self.assertIsNone(app._FILE_METADATA["replace.bin"]["password"])

    def test_disconnected_upload_removes_temporary_file(self):
        response = asgi_request(
            "PUT",
            "/api/upload?filename=partial.bin",
            body=[b"partial"],
            disconnect=True,
        )

        self.assertEqual(response.status, 499)
        self.assertEqual(response.json(), {"ok": False, "cancelled": True})
        self.assertFalse((app.FILES_DIR / "partial.bin").exists())
        self.assertEqual(list(app.FILES_DIR.glob(".uploading-*")), [])
        self.assertEqual(list(app.current_storage_backend().temporary_uploads_root.iterdir()), [])

    def test_invalid_upload_inputs_return_400_without_writing(self):
        cases = [
            ("/api/upload", {}),
            ("/api/upload?filename=..%2Fescape.bin", {}),
            ("/api/upload?filename=.nightwire-metadata.json", {}),
            ("/api/upload?filename=file.bin", {"x-nightwire-expires-in-seconds": "59"}),
            ("/api/upload?filename=file.bin", {"x-nightwire-password-b64": "not-base64"}),
        ]

        for target, headers in cases:
            with self.subTest(target=target, headers=headers):
                response = asgi_request("PUT", target, body=b"data", headers=headers)
                self.assertEqual(response.status, 400)

        self.assertEqual(list(app.FILES_DIR.iterdir()), [])


class FileDownloadCharacterizationTests(IsolatedApplicationState):
    def test_download_returns_exact_binary_and_response_headers(self):
        data = bytes(range(256)) + b"\x00\xff\x80NightWire"
        self.create_file("payload.bin", data)

        response = asgi_request("GET", "/download/payload.bin")

        self.assertIsNone(response.exception)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, data)
        self.assertEqual(response.headers["content-type"], "application/octet-stream")
        self.assertEqual(response.headers["content-length"], str(len(data)))
        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="payload.bin"')
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["accept-ranges"], "bytes")

    def test_head_returns_download_headers_without_a_body(self):
        data = b"header-only"
        self.create_file("head.bin", data)

        response = asgi_request("HEAD", "/download/head.bin")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.headers["content-length"], str(len(data)))

    def test_missing_file_returns_json_404(self):
        response = asgi_request("GET", "/download/missing.bin")

        self.assertEqual(response.status, 404)
        self.assertEqual(response.json(), {"error": "File not found."})


class LifecycleCharacterizationTests(IsolatedApplicationState):
    def test_application_cleanup_reclaims_orphaned_core_temporary_upload(self):
        storage = app.current_storage_backend()
        upload_id = storage.allocate_temporary_upload()
        reference = storage.temporary_upload_reference(upload_id)
        old = time.time() - (25 * 60 * 60)
        os.utime(reference, (old, old))

        app.cleanup_expired_items()

        self.assertFalse(reference.exists())

    def test_file_listing_removes_expired_file_and_its_current_metadata(self):
        expired_path = self.create_file("expired.bin", b"expired", expires_at=app.utc_iso(time.time() - 1))
        survivor_path = self.create_file("survivor.bin", b"survivor", expires_at=None)
        app._FILE_METADATA["orphan.bin"] = {
            "created_at": app.utc_iso(),
            "expires_at": None,
            "password": None,
        }
        app._save_file_metadata_locked()

        trusted_manager = replace(
            app.SETTINGS,
            trusted_network_relaxed_access=True,
            trusted_network_active_drop_browsing=True,
        )
        with mock.patch.object(app, "SETTINGS", trusted_manager):
            response = asgi_request("GET", "/api/files")

        self.assertEqual(response.status, 200)
        self.assertFalse(expired_path.exists())
        self.assertTrue(survivor_path.exists())
        self.assertEqual([item["name"] for item in response.json()["files"]], ["survivor.bin"])
        self.assertEqual(set(app._FILE_METADATA), {"survivor.bin"})
        on_disk = json.loads(app.metadata_path().read_text(encoding="utf-8"))
        self.assertEqual(on_disk, {"survivor.bin": app._FILE_METADATA["survivor.bin"]})

    def test_expired_file_download_is_404_after_removing_file_and_metadata(self):
        expired_path = self.create_file("gone.bin", b"gone", expires_at=app.utc_iso(time.time() - 1))

        response = asgi_request("GET", "/download/gone.bin")

        self.assertEqual(response.status, 404)
        self.assertFalse(expired_path.exists())
        self.assertNotIn("gone.bin", app._FILE_METADATA)
        self.assertEqual(json.loads(app.metadata_path().read_text(encoding="utf-8")), {})


class ClipboardCharacterizationTests(IsolatedApplicationState):
    def test_share_list_revision_update_and_delete_flow(self):
        created = json_request(
            "POST",
            "/api/clipboard",
            {
                "client_id": "client-12345678",
                "text": "  first\r\nsecond  ",
                "expires_in_seconds": 600,
            },
        )

        self.assertEqual(created.status, 201)
        entry = created.json()["entry"]
        self.assertEqual(entry["text"], "first\nsecond")
        self.assertEqual(entry["ip_address"], "127.0.0.1")
        self.assertEqual(created.json()["revision"], 1)

        unchanged = asgi_request("GET", "/api/clipboard?since_revision=1")
        self.assertEqual(unchanged.json()["changed"], False)
        self.assertEqual(unchanged.json()["entries"], [])

        listed = asgi_request("GET", "/api/clipboard?since_revision=0")
        self.assertEqual(listed.json()["entries"], [entry])

        updated = json_request("PATCH", f"/api/clipboard/{entry['id']}", {"expires_in_seconds": 0})
        self.assertEqual(updated.status, 200)
        self.assertEqual(updated.json()["revision"], 2)
        self.assertIsNone(updated.json()["entry"]["expires_at"])

        deleted = json_request("DELETE", f"/api/clipboard/{entry['id']}")
        self.assertEqual(deleted.status, 200)
        self.assertEqual(deleted.json()["revision"], 3)
        self.assertEqual(asgi_request("GET", "/api/clipboard?since_revision=-1").json()["entries"], [])

    def test_expired_clipboard_entry_is_removed_and_advances_revision_once(self):
        app.add_clipboard_entry("expired", "client-12345678", "Test browser", "127.0.0.1", 60)
        with app._CLIPBOARD_LOCK:
            app._CLIPBOARD_ENTRIES[0]["expires_at"] = app.utc_iso(time.time() - 1)

        response = asgi_request("GET", "/api/clipboard?since_revision=1")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["revision"], 2)
        self.assertTrue(response.json()["changed"])
        self.assertEqual(response.json()["entries"], [])

    def test_clear_refuses_mixed_history_when_any_entry_is_protected(self):
        app.add_clipboard_entry("public", "client-12345678", "Test", "127.0.0.1")
        app.add_clipboard_entry("secret", "client-12345678", "Test", "127.0.0.1", password="password")

        response = asgi_request("DELETE", "/api/clipboard")

        self.assertEqual(response.status, 409)
        self.assertEqual(len(app._CLIPBOARD_ENTRIES), 2)


class PasswordProtectionCharacterizationTests(IsolatedApplicationState):
    def test_protected_upload_stores_digest_and_requires_password_for_download_and_delete(self):
        password = "correct horse battery staple"
        encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
        data = b"protected\x00binary\xff"

        uploaded = asgi_request(
            "PUT",
            "/api/upload?filename=protected.bin",
            body=data,
            headers={"x-nightwire-password-b64": encoded},
        )
        self.assertEqual(uploaded.status, 201)
        access_key = uploaded.json()["access_key"]
        metadata_text = app.metadata_path().read_text(encoding="utf-8")
        self.assertNotIn(password, metadata_text)
        self.assertTrue(app.verify_password(password, app._FILE_METADATA["protected.bin"]["password"]))

        missing_key = asgi_request("GET", "/download/protected.bin")
        self.assertEqual(missing_key.status, 403)

        direct = asgi_request("GET", f"/download/protected.bin?key={quote(access_key)}")
        self.assertEqual(direct.status, 401)

        wrong_download = json_request(
            "POST", f"/api/files/protected.bin/download?key={quote(access_key)}", {"password": "wrong"}
        )
        self.assertEqual(wrong_download.status, 403)

        downloaded = json_request(
            "POST", f"/api/files/protected.bin/download?key={quote(access_key)}", {"password": password}
        )
        self.assertEqual(downloaded.status, 200)
        self.assertEqual(downloaded.body, data)

        wrong_delete = json_request("DELETE", "/api/files/protected.bin", {"password": "wrong"})
        self.assertEqual(wrong_delete.status, 403)
        object_id = app.ObjectId.parse(app._FILE_METADATA["protected.bin"]["object_id"])
        object_path = app.current_storage_backend().object_reference(object_id)
        self.assertTrue(object_path.exists())

        deleted = json_request("DELETE", "/api/files/protected.bin", {"password": password})
        self.assertEqual(deleted.status, 200)
        self.assertFalse(object_path.exists())

    def test_protected_existing_file_cannot_be_overwritten(self):
        self.create_file("locked.bin", b"original", password="secret")

        response = asgi_request("PUT", "/api/upload?filename=locked.bin", body=b"replacement")

        self.assertEqual(response.status, 409)
        self.assertEqual((app.FILES_DIR / "locked.bin").read_bytes(), b"original")

    def test_protected_clipboard_redacts_public_text_and_unlocks_with_password(self):
        created = json_request(
            "POST",
            "/api/clipboard",
            {"client_id": "client-12345678", "text": "top secret", "password": "secret"},
        )
        entry = created.json()["entry"]

        self.assertEqual(created.status, 201)
        self.assertTrue(entry["password_protected"])
        self.assertIsNone(entry["text"])
        self.assertEqual(entry["text_length"], len("top secret"))
        self.assertNotIn("secret", json.dumps(entry))

        unlocked = json_request(
            "POST", f"/api/clipboard/{entry['id']}/unlock", {"password": "secret"}
        )
        self.assertEqual(unlocked.status, 200)
        self.assertEqual(unlocked.json()["text"], "top secret")

    def test_wrong_clipboard_password_is_currently_an_unhandled_server_error(self):
        _, entry = app.add_clipboard_entry(
            "top secret", "client-12345678", "Test", "127.0.0.1", password="secret"
        )

        response = json_request(
            "POST", f"/api/clipboard/{entry['id']}/unlock", {"password": "wrong"}
        )

        self.assertEqual(response.status, 500)
        self.assertIsInstance(response.exception, PermissionError)


class ClientVisibilityCharacterizationTests(IsolatedApplicationState):
    def test_heartbeat_creates_visible_client_and_preserves_connection_time(self):
        with mock.patch.object(app, "local_ipv4_addresses", return_value=["192.168.50.10"]):
            first = json_request(
                "POST",
                "/api/clients/heartbeat",
                {"client_id": "client-12345678", "platform": "Windows", "mobile": False},
                client=("192.168.50.20", 51234),
            )
            connected_at = first.json()["devices"][1]["connected_at"]
            second = json_request(
                "POST",
                "/api/clients/heartbeat",
                {"client_id": "client-12345678", "platform": "Windows", "mobile": False},
                client=("192.168.50.20", 51235),
            )

        self.assertEqual(first.status, 200)
        devices = second.json()["devices"]
        self.assertEqual([device["role"] for device in devices], ["server", "client"])
        self.assertEqual(devices[0]["primary_ip"], "192.168.50.10")
        self.assertEqual(devices[1]["id"], "client-12345678")
        self.assertEqual(devices[1]["ip_address"], "192.168.50.20")
        self.assertEqual(devices[1]["connected_at"], connected_at)
        self.assertNotIn("last_seen_epoch", devices[1])

    def test_device_listing_purges_clients_older_than_ttl(self):
        with app._CLIENTS_LOCK:
            app._ACTIVE_CLIENTS["stale-client"] = {
                "id": "stale-client",
                "role": "client",
                "name": "Old device",
                "status": "online",
                "ip_address": "192.168.1.2",
                "ip_addresses": ["192.168.1.2"],
                "primary_ip": "192.168.1.2",
                "connected_at": app.utc_iso(time.time() - 100),
                "last_seen": app.utc_iso(time.time() - 100),
                "last_seen_epoch": time.time() - app.CLIENT_TTL_SECONDS - 1,
            }

        with mock.patch.object(app, "local_ipv4_addresses", return_value=[]):
            response = asgi_request("GET", "/api/devices")

        self.assertEqual(response.status, 200)
        self.assertEqual([device["id"] for device in response.json()["devices"]], ["server"])
        self.assertNotIn("stale-client", app._ACTIVE_CLIENTS)

    def test_invalid_client_id_is_rejected_without_visibility_state(self):
        response = json_request("POST", "/api/clients/heartbeat", {"client_id": "short"})

        self.assertEqual(response.status, 400)
        self.assertEqual(app._ACTIVE_CLIENTS, {})


class LinuxInstallUpdateSmokeTests(unittest.TestCase):
    def write_executable(self, path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def base_environment(self, tool_directory):
        environment = os.environ.copy()
        environment["PATH"] = f"{tool_directory}{os.pathsep}{environment['PATH']}"
        environment.pop("NIGHTWIRE_EXISTING_DIR", None)
        return environment

    def test_linux_installer_preserves_configuration_storage_and_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install_dir = root / "installed"
            bin_dir = root / "bin"
            tools_dir = root / "tools"
            tools_dir.mkdir()
            uv_log = root / "uv.log"
            self.write_executable(
                tools_dir / "uv",
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$NIGHTWIRE_TEST_UV_LOG\"\nexit 0\n",
            )

            (install_dir / "files").mkdir(parents=True)
            (install_dir / "files" / "upload.bin").write_bytes(b"preserve upload")
            (install_dir / "files" / app.FILE_METADATA_FILENAME).write_text('{"upload.bin": {}}\n', encoding="utf-8")
            (install_dir / "data").mkdir()
            (install_dir / "data" / "nightwire-library.db").write_bytes(b"preserve library")
            (install_dir / ".venv").mkdir()
            (install_dir / ".venv" / "sentinel").write_text("preserve venv", encoding="utf-8")
            (install_dir / ".env").write_text("PORT=9000\n", encoding="utf-8")
            (install_dir / ".env.local").write_text("LOCAL=1\n", encoding="utf-8")
            (install_dir / "stale.txt").write_text("remove me", encoding="utf-8")

            environment = self.base_environment(tools_dir)
            environment.update(
                {
                    "NIGHTWIRE_INSTALL_DIR": str(install_dir),
                    "NIGHTWIRE_BIN_DIR": str(bin_dir),
                    "NIGHTWIRE_PYTHON": "3.12",
                    "NIGHTWIRE_TEST_UV_LOG": str(uv_log),
                }
            )
            result = subprocess.run(
                ["bash", str(PROJECT_ROOT / "install.sh")],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((install_dir / "files" / "upload.bin").read_bytes(), b"preserve upload")
            self.assertEqual(
                (install_dir / "files" / app.FILE_METADATA_FILENAME).read_text(encoding="utf-8"),
                '{"upload.bin": {}}\n',
            )
            self.assertEqual(
                (install_dir / "data" / "nightwire-library.db").read_bytes(),
                b"preserve library",
            )
            self.assertEqual((install_dir / ".env").read_text(encoding="utf-8"), "PORT=9000\n")
            self.assertEqual((install_dir / ".env.local").read_text(encoding="utf-8"), "LOCAL=1\n")
            self.assertTrue((install_dir / ".venv" / "sentinel").is_file())
            self.assertFalse((install_dir / "stale.txt").exists())
            self.assertTrue((install_dir / "app.py").is_file())
            self.assertTrue((bin_dir / "nightwire").is_file())
            self.assertIn(f"--project {install_dir} --locked --no-dev --python 3.12", uv_log.read_text(encoding="utf-8"))

    def test_recursive_updater_preserves_source_configuration_and_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release_dir = root / "release"
            target_dir = root / "target"
            tools_dir = root / "tools"
            release_dir.mkdir()
            target_dir.mkdir()
            tools_dir.mkdir()
            self.write_executable(tools_dir / "sudo", "#!/bin/sh\nexec \"$@\"\n")

            manifest = (PROJECT_ROOT / "release-manifest.txt").read_text(encoding="utf-8").splitlines()
            for relative in filter(None, manifest):
                source = PROJECT_ROOT / relative
                destination = release_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            (target_dir / "files").mkdir()
            (target_dir / "files" / "upload.bin").write_bytes(b"preserve upload")
            (target_dir / "files" / app.FILE_METADATA_FILENAME).write_text('{"upload.bin": {}}\n', encoding="utf-8")
            (target_dir / "data").mkdir()
            (target_dir / "data" / "nightwire-library.db").write_bytes(b"preserve library")
            (target_dir / ".venv").mkdir()
            (target_dir / ".venv" / "sentinel").write_text("preserve venv", encoding="utf-8")
            (target_dir / ".git").mkdir()
            (target_dir / ".git" / "config").write_text("preserve git", encoding="utf-8")
            (target_dir / ".env").write_text("PORT=9000\n", encoding="utf-8")
            (target_dir / ".env.local").write_text("LOCAL=1\n", encoding="utf-8")
            (target_dir / "stale.txt").write_text("remove me", encoding="utf-8")

            environment = self.base_environment(tools_dir)
            result = subprocess.run(
                ["bash", str(release_dir / "update-existing.sh"), str(target_dir)],
                cwd=release_dir,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((target_dir / "files" / "upload.bin").read_bytes(), b"preserve upload")
            self.assertEqual(
                (target_dir / "files" / app.FILE_METADATA_FILENAME).read_text(encoding="utf-8"),
                '{"upload.bin": {}}\n',
            )
            self.assertEqual(
                (target_dir / "data" / "nightwire-library.db").read_bytes(),
                b"preserve library",
            )
            self.assertEqual((target_dir / ".env").read_text(encoding="utf-8"), "PORT=9000\n")
            self.assertEqual((target_dir / ".env.local").read_text(encoding="utf-8"), "LOCAL=1\n")
            self.assertTrue((target_dir / ".venv" / "sentinel").is_file())
            self.assertTrue((target_dir / ".git" / "config").is_file())
            self.assertFalse((target_dir / "stale.txt").exists())
            self.assertEqual((target_dir / "app.py").read_bytes(), (release_dir / "app.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
