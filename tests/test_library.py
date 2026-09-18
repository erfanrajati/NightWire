import asyncio
import concurrent.futures
import json
import threading
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from unittest import mock

from nightwire.app.bootstrap import build_application
from nightwire.app.registration import ModuleBinding
from nightwire.core.config import RegistrationPolicy, load_application_config
from nightwire.core.storage import ObjectId
from nightwire.library.database import SQLiteDatabase
from nightwire.library.registration import LibraryModule


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ImmediateAsyncFile:
    def __init__(self, path, mode):
        self.file = open(path, mode)

    async def __aenter__(self): return self
    async def __aexit__(self, *_): self.file.close()
    async def read(self, size=-1): return self.file.read(size)
    async def write(self, data): return self.file.write(data)
    async def flush(self): return self.file.flush()


async def immediate_open_file(path, mode="r"):
    return ImmediateAsyncFile(path, mode)


@dataclass
class CapturedResponse:
    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def json(self):
        return json.loads(self.body)

    def header(self, name):
        return next((value for key, value in self.headers if key.lower() == name.lower()), None)


class AsgiClient:
    def __init__(self, application):
        self.application = application
        self.cookies = {}

    def request(self, method, target, payload=None, *, body=None, headers=None):
        return asyncio.run(self._request(method, target, payload, body=body, extra_headers=headers))

    async def _request(self, method, target, payload, *, body=None, extra_headers=None):
        parsed = urlsplit(target)
        body = body if body is not None else (json.dumps(payload).encode() if payload is not None else b"")
        headers = [(b"host", b"testserver"), (b"content-length", str(len(body)).encode())]
        if payload is not None:
            headers.append((b"content-type", b"application/json"))
        for key, value in (extra_headers or {}).items():
            headers.append((key.lower().encode(), value.encode()))
        if self.cookies:
            value = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
            headers.append((b"cookie", value.encode("ascii")))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": parsed.path,
            "raw_path": parsed.path.encode(),
            "query_string": parsed.query.encode(),
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 40000),
            "server": ("testserver", 80),
            "extensions": {},
        }
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        messages = []

        async def send(message):
            messages.append(message)

        await self.application(scope, receive, send)
        start = next(message for message in messages if message["type"] == "http.response.start")
        response_headers = [
            (key.decode("latin-1"), value.decode("latin-1"))
            for key, value in start.get("headers", [])
        ]
        for key, value in response_headers:
            if key.lower() != "set-cookie":
                continue
            pair = value.split(";", 1)[0]
            name, cookie_value = pair.split("=", 1)
            if cookie_value:
                self.cookies[name] = cookie_value
            else:
                self.cookies.pop(name, None)
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return CapturedResponse(start["status"], response_headers, response_body)


class LibraryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.file_patch = mock.patch("nightwire.core.storage.anyio.open_file", new=immediate_open_file)
        self.file_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.temporary.cleanup()

    def application(self, policy, profile="trusted-private", extra_environment=None):
        database_path = Path(self.temporary.name) / f"{policy.value}.db"
        environment = {
                "NIGHTWIRE_DATABASE_URL": f"sqlite:///{database_path}",
                "NIGHTWIRE_FILES_DIR": str(Path(self.temporary.name) / "files"),
                "NIGHTWIRE_LIBRARY_REGISTRATION_POLICY": policy.value,
                "NIGHTWIRE_DEPLOYMENT_PROFILE": profile,
            }
        environment.update(extra_environment or {})
        settings = load_application_config(
            environment,
            base_dir=PROJECT_ROOT,
            create_files_directory=False,
        )
        module = LibraryModule()
        application = build_application(
            settings, {}, modules=[ModuleBinding(module, enabled=True)]
        )
        application.state.library_database.migrate()
        return application

    def test_personal_quota_usage_api_and_permanent_delete_accounting(self):
        application = self.application(
            RegistrationPolicy.OPEN,
            extra_environment={"NIGHTWIRE_PERSONAL_LIBRARY_QUOTA_BYTES": "5"},
        )
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("quota@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        item = client.request("PUT", f"/api/library/folders/{root['id']}/upload?name=five.bin",
                              body=b"12345", headers={"content-type": "application/octet-stream"}).json()["file"]
        denied = client.request("PUT", f"/api/library/folders/{root['id']}/upload?name=one.bin",
                                body=b"1", headers={"content-type": "application/octet-stream"})
        usage = client.request("GET", "/api/library/usage").json()
        self.assertEqual((denied.status, denied.json()["code"]), (413, "capacity_exceeded"))
        self.assertEqual((usage["used_bytes"], usage["limit_bytes"], usage["available_bytes"]), (5, 5, 0))
        self.assertEqual(list(application.state.personal_library.storage.temporary_uploads_root.iterdir()), [])
        client.request("DELETE", f"/api/library/files/{item['id']}")
        client.request("DELETE", f"/api/library/trash/files/{item['id']}")
        self.assertEqual(client.request("GET", "/api/library/usage").json()["used_bytes"], 0)

    @staticmethod
    def registration(email, name="Test User"):
        return {
            "email": email,
            "display_name": name,
            "password": "correct horse battery",
        }

    def test_fresh_sqlite_migration_is_idempotent(self):
        database = SQLiteDatabase(Path(self.temporary.name) / "fresh.db")
        database.migrate()
        database.migrate()

        with database.transaction() as transaction:
            versions = transaction.fetch_all("SELECT version FROM library_schema_migrations")
            tables = transaction.fetch_all(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'library_%'"
            )

        self.assertEqual([row["version"] for row in versions], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(
            {row["name"] for row in tables},
            {
                "library_schema_migrations",
                "library_users",
                "library_sessions",
                "library_invitations",
                "library_folders",
                "library_files",
                "library_workspaces",
                "library_workspace_memberships",
                "library_object_references",
                "library_file_versions",
                "library_derived_objects",
                "library_share_grants",
                "library_text_objects",
                "library_text_share_grants",
            },
        )

    def test_file_versions_restore_and_generic_derived_promotion(self):
        application = self.application(
            RegistrationPolicy.OPEN,
            extra_environment={"NIGHTWIRE_LIBRARY_VERSION_RETENTION": "10"},
        )
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("versions@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        item = client.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=story.txt",
            body=b"first", headers={"content-type": "text/plain"},
        ).json()["file"]

        initial = client.request("GET", f"/api/library/files/{item['id']}").json()["versions"][0]
        second = client.request(
            "PUT", f"/api/library/files/{item['id']}/versions",
            body=b"second", headers={"content-type": "text/plain"},
        )
        history = client.request("GET", f"/api/library/files/{item['id']}/versions").json()["versions"]
        historical = client.request(
            "GET", f"/api/library/files/{item['id']}/versions/{initial['id']}/download"
        )
        restored = client.request(
            "POST", f"/api/library/files/{item['id']}/versions/{initial['id']}/restore"
        )

        self.assertEqual(second.status, 201)
        self.assertEqual([version["version"] for version in history], [2, 1])
        self.assertEqual(historical.body, b"first")
        self.assertEqual(restored.json()["version"]["version"], 3)
        self.assertEqual(client.request("GET", f"/api/library/files/{item['id']}/download").body, b"first")

        current = client.request("GET", f"/api/library/files/{item['id']}").json()["versions"][0]
        attached = client.request(
            "PUT", f"/api/library/files/{item['id']}/derived-outputs",
            body=b"generic result",
            headers={
                "content-type": "application/x-test-result",
                "x-source-version-id": current["id"],
                "x-operation": "fixture.generic",
                "x-provenance": json.dumps({"processor": "test-fixture", "run": 7}),
            },
        )
        output = attached.json()["derived_output"]
        promoted = client.request(
            "POST", f"/api/library/files/{item['id']}/derived-outputs/{output['id']}/promote"
        )
        details = client.request("GET", f"/api/library/files/{item['id']}").json()

        self.assertEqual(attached.status, 201)
        self.assertEqual(output["provenance"], {"processor": "test-fixture", "run": 7})
        self.assertEqual(promoted.status, 201)
        self.assertEqual(promoted.json()["version"]["source_kind"], "derived")
        self.assertEqual(client.request("GET", f"/api/library/files/{item['id']}/download").body,
                         b"generic result")
        self.assertEqual(details["derived_outputs"][0]["promoted_version_id"],
                         promoted.json()["version"]["id"])

    def test_version_retention_preserves_derived_sources_and_reclaims_only_unreferenced_objects(self):
        application = self.application(
            RegistrationPolicy.OPEN,
            extra_environment={"NIGHTWIRE_LIBRARY_VERSION_RETENTION": "1"},
        )
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("retained-source@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        item = client.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=model.bin",
            body=b"source", headers={"content-type": "application/octet-stream"},
        ).json()["file"]
        source = client.request("GET", f"/api/library/files/{item['id']}").json()["versions"][0]
        derived = client.request(
            "PUT", f"/api/library/files/{item['id']}/derived-outputs",
            body=b"result", headers={"content-type": "application/octet-stream",
                                     "x-source-version-id": source["id"],
                                     "x-operation": "fixture.pin-source"},
        ).json()["derived_output"]
        second = client.request(
            "PUT", f"/api/library/files/{item['id']}/versions",
            body=b"temporary-current", headers={"content-type": "application/octet-stream"},
        ).json()["version"]
        with application.state.library_database.transaction() as transaction:
            second_row = transaction.fetch_one(
                "SELECT object_id FROM library_file_versions WHERE id = :id", {"id": second["id"]}
            )
        second_object_id = ObjectId.parse(second_row["object_id"])
        promoted = client.request(
            "POST", f"/api/library/files/{item['id']}/derived-outputs/{derived['id']}/promote"
        )
        versions = client.request("GET", f"/api/library/files/{item['id']}/versions").json()["versions"]

        self.assertEqual(promoted.status, 201)
        self.assertEqual([version["version"] for version in versions], [3, 1])
        self.assertFalse(application.state.personal_library.storage.object_exists(second_object_id))
        self.assertEqual(client.request(
            "GET", f"/api/library/files/{item['id']}/versions/{source['id']}/download"
        ).body, b"source")

    def test_duplicate_warnings_are_structured_scoped_and_explicitly_confirmable(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("dupes@example.com"))
        root = owner.request("GET", "/api/library").json()["folder"]
        nested = owner.request(
            "POST", "/api/library/folders", {"parent_id": root["id"], "path": "Projects/Deep"}
        ).json()["folder"]
        owner.request(
            "PUT", f"/api/library/folders/{nested['id']}/upload?name=report.txt",
            body=b"same bytes", headers={"content-type": "text/plain"},
        )

        warning = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=copy.txt",
            body=b"same bytes", headers={"content-type": "text/plain"},
        )
        self.assertEqual((warning.status, warning.json()["code"]), (409, "duplicate_warning"))
        self.assertEqual(warning.json()["warnings"][0]["kind"], "checksum_match")
        self.assertEqual(warning.json()["warnings"][0]["candidates"][0]["path"],
                         "/Projects/Deep/report.txt")
        self.assertEqual(owner.request("GET", "/api/library").json()["files"], [])

        confirmed = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=copy.txt&confirm_duplicates=true",
            body=b"same bytes", headers={"content-type": "text/plain"},
        )
        same_folder_warning = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=copy.txt",
            body=b"different", headers={"content-type": "text/plain"},
        )
        same_folder_confirmed = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=copy.txt&confirm_duplicates=true",
            body=b"different", headers={"content-type": "text/plain"},
        )
        self.assertEqual(confirmed.status, 201)
        self.assertEqual(same_folder_warning.json()["warnings"][0]["kind"], "same_name")
        self.assertEqual(same_folder_confirmed.json()["file"]["name"], "copy copy.txt")

        outsider = AsgiClient(application)
        outsider.request("POST", "/api/library/auth/register", self.registration("dupe-outsider@example.com"))
        outsider_root = outsider.request("GET", "/api/library").json()["folder"]
        isolated = outsider.request(
            "PUT", f"/api/library/folders/{outsider_root['id']}/upload?name=report.txt",
            body=b"same bytes", headers={"content-type": "text/plain"},
        )
        self.assertEqual(isolated.status, 201)

    def test_recursive_fuzzy_search_global_scope_metadata_and_authorization(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("search-owner@example.com"))
        root = owner.request("GET", "/api/library").json()["folder"]
        personal_folder = owner.request(
            "POST", "/api/library/folders", {"parent_id": root["id"], "path": "Plans/2027"}
        ).json()["folder"]
        owner.request(
            "PUT", f"/api/library/folders/{personal_folder['id']}/upload?name=Quarterly-Roadmap.pdf",
            body=b"personal search target", headers={"content-type": "application/pdf"},
        )
        workspace = owner.request("POST", "/api/workspaces", {"name": "Visible Team"}).json()["workspace"]
        workspace_root = owner.request("GET", f"/api/workspaces/{workspace['id']}").json()["folder"]
        workspace_folder = owner.request(
            "POST", f"/api/workspaces/{workspace['id']}/folders",
            {"parent_id": workspace_root["id"], "path": "Design/Nested"},
        ).json()["folder"]
        owner.request(
            "PUT", f"/api/workspaces/{workspace['id']}/folders/{workspace_folder['id']}/upload?name=Launch-Wireframes.fig",
            body=b"workspace search target", headers={"content-type": "application/octet-stream"},
        )

        fuzzy = owner.request("GET", "/api/library/search?q=qtrly%20roadmap&scope=personal").json()
        global_results = owner.request("GET", "/api/library/search?q=launch%20wireframe&scope=global").json()
        self.assertEqual(fuzzy["results"][0]["name"], "Quarterly-Roadmap.pdf")
        self.assertEqual(fuzzy["results"][0]["path"], "/Plans/2027/Quarterly-Roadmap.pdf")
        self.assertEqual(global_results["results"][0]["scope"], {
            "kind": "workspace", "id": workspace["id"], "name": "Visible Team",
            "filter": "workspace",
        })

        outsider = AsgiClient(application)
        outsider.request("POST", "/api/library/auth/register", self.registration("search-outsider@example.com"))
        leaked_personal = outsider.request(
            "GET", "/api/library/search?q=Quarterly-Roadmap&scope=global"
        ).json()["results"]
        leaked_workspace = outsider.request(
            "GET", "/api/library/search?q=Launch-Wireframes&scope=global"
        ).json()["results"]
        body_only = owner.request(
            "GET", "/api/library/search?q=workspace%20search%20target&scope=global"
        ).json()["results"]
        self.assertEqual(leaked_personal, [])
        self.assertEqual(leaked_workspace, [])
        self.assertEqual(body_only, [])

    def test_library_shares_are_reusable_read_only_and_pin_immutable_source_versions(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("shares@example.com"))
        root = owner.request("GET", "/api/library").json()["folder"]
        item = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=public-plan.txt",
            body=b"original shared bytes", headers={"content-type": "text/plain"},
        ).json()["file"]

        unprotected = owner.request(
            "POST", f"/api/library/files/{item['id']}/shares",
            {"expires_in_seconds": 0, "access_key_protected": False},
        )
        share = unprotected.json()["share"]
        parsed = urlsplit(share["share_url"])
        target = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
        token = parsed.path.rsplit("/", 1)[-1]
        info_target = f"/api/public/shares/{token}"
        download_target = f"{info_target}/download"

        self.assertEqual(unprotected.status, 201)
        self.assertIsNone(share["expires_at"])
        self.assertEqual(AsgiClient(application).request("GET", target).status, 200)
        self.assertEqual(AsgiClient(application).request("POST", info_target).status, 405)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            repeated = list(pool.map(
                lambda _: AsgiClient(application).request("GET", download_target).body,
                range(6),
            ))
        self.assertEqual(repeated, [b"original shared bytes"] * 6)

        owner.request(
            "PUT", f"/api/library/files/{item['id']}/versions",
            body=b"new current bytes", headers={"content-type": "text/plain"},
        )
        self.assertEqual(AsgiClient(application).request("GET", download_target).body,
                         b"original shared bytes")

        qr = AsgiClient(application).request("GET", f"{info_target}/qr")
        self.assertEqual(qr.status, 200)
        self.assertEqual(qr.header("content-type"), "image/svg+xml")
        self.assertIn(b"<svg", qr.body)

    def test_protected_share_expiry_revocation_security_and_source_survival(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("protected-shares@example.com"))
        root = owner.request("GET", "/api/library").json()["folder"]
        item = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=held.bin",
            body=b"held source bytes", headers={"content-type": "application/octet-stream"},
        ).json()["file"]
        with application.state.library_database.transaction() as transaction:
            object_value = transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": item["id"]}
            )["object_id"]
        object_id = ObjectId.parse(object_value)
        application.state.personal_library.storage.save_object_metadata(object_id, {
            "security": {"verdict": "malicious", "detected_mime": "application/octet-stream"}
        })

        created = owner.request(
            "POST", f"/api/library/files/{item['id']}/shares",
            {"expires_in_seconds": 3600, "access_key_protected": True},
        )
        payload = created.json()
        key = payload["access_key"]
        parsed = urlsplit(payload["share"]["share_url"])
        token = parsed.path.rsplit("/", 1)[-1]
        info = f"/api/public/shares/{token}"
        keyed = f"{info}?{parsed.query}"
        download = f"{info}/download?{parsed.query}"

        self.assertEqual(created.status, 201)
        self.assertRegex(key, r"^[A-Za-z0-9_-]{43}$")
        with application.state.library_database.transaction() as transaction:
            stored = transaction.fetch_one(
                "SELECT * FROM library_share_grants WHERE public_token = :token", {"token": token}
            )
        self.assertNotIn(key, json.dumps(dict(stored)))
        self.assertEqual(AsgiClient(application).request("GET", info).status, 403)
        self.assertEqual(AsgiClient(application).request("GET", keyed).json()["share"]["security_verdict"],
                         "malicious")
        held = AsgiClient(application).request("GET", download)
        confirmed = AsgiClient(application).request("GET", f"{download}&confirm_malicious=true")
        self.assertEqual((held.status, held.json()["confirmation_required"]), (409, True))
        self.assertEqual(confirmed.body, b"held source bytes")
        self.assertEqual(AsgiClient(application).request("GET", download).status, 409)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            protected_repeats = list(pool.map(
                lambda _: AsgiClient(application).request(
                    "GET", f"{download}&confirm_malicious=true"
                ).body,
                range(6),
            ))
        self.assertEqual(protected_repeats, [b"held source bytes"] * 6)

        outsider = AsgiClient(application)
        outsider.request("POST", "/api/library/auth/register", self.registration("share-outsider@example.com"))
        self.assertEqual(outsider.request(
            "POST", f"/api/library/files/{item['id']}/shares",
            {"expires_in_seconds": 0, "access_key_protected": False},
        ).status, 404)
        self.assertEqual(outsider.request(
            "DELETE", f"/api/library/shares/{payload['share']['id']}"
        ).status, 404)

        revoked = owner.request("DELETE", f"/api/library/shares/{payload['share']['id']}")
        self.assertEqual(revoked.status, 204)
        self.assertEqual(AsgiClient(application).request("GET", keyed).status, 404)
        self.assertTrue(application.state.personal_library.storage.object_exists(object_id))
        self.assertEqual(owner.request("GET", f"/api/library/files/{item['id']}/download").body,
                         b"held source bytes")

        expiring = owner.request(
            "POST", f"/api/library/files/{item['id']}/shares",
            {"expires_in_seconds": 60, "access_key_protected": False},
        ).json()["share"]
        expiring_token = urlsplit(expiring["share_url"]).path.rsplit("/", 1)[-1]
        with application.state.library_database.transaction() as transaction:
            transaction.execute(
                "UPDATE library_share_grants SET expires_at = :past WHERE id = :id",
                {"id": expiring["id"], "past": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
            )
        self.assertEqual(AsgiClient(application).request(
            "GET", f"/api/public/shares/{expiring_token}"
        ).status, 410)
        self.assertTrue(application.state.personal_library.storage.object_exists(object_id))

    def test_open_registration_session_identity_and_logout_revocation(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)

        self.assertEqual(client.request("GET", "/api/library").status, 401)
        registered = client.request(
            "POST", "/api/library/auth/register", self.registration("User@Example.com")
        )
        identity = client.request("GET", "/api/library/auth/me")
        session_cookie = client.cookies["nightwire_library_session"]
        logged_out = client.request("POST", "/api/library/auth/logout")

        self.assertEqual(registered.status, 201)
        self.assertTrue(registered.json()["authenticated"])
        self.assertIn("HttpOnly", registered.header("set-cookie"))
        self.assertIn("SameSite=strict", registered.header("set-cookie"))
        self.assertEqual(identity.json()["user"]["email"], "user@example.com")
        self.assertEqual(logged_out.status, 204)
        client.cookies["nightwire_library_session"] = session_cookie
        self.assertEqual(client.request("GET", "/api/library/auth/me").status, 401)

        with application.state.library_database.transaction() as transaction:
            user = transaction.fetch_one("SELECT password_hash FROM library_users")
            session = transaction.fetch_one("SELECT token_hash, revoked_at FROM library_sessions")
        self.assertNotIn("correct horse", user["password_hash"])
        self.assertNotEqual(session["token_hash"], session_cookie)
        self.assertIsNotNone(session["revoked_at"])

    def test_invitation_only_enforces_email_bound_single_use_invitations(self):
        client = AsgiClient(self.application(RegistrationPolicy.INVITATION_ONLY))
        admin = client.request(
            "POST", "/api/library/auth/register", self.registration("admin@example.com", "Admin")
        )
        denied = AsgiClient(client.application).request(
            "POST", "/api/library/auth/register", self.registration("member@example.com")
        )
        invitation = client.request(
            "POST", "/api/library/admin/invitations", {"email": "member@example.com"}
        )
        token = invitation.json()["invitation_token"]
        wrong_email_payload = self.registration("someone@example.com") | {"invitation_token": token}
        wrong_email = AsgiClient(client.application).request(
            "POST", "/api/library/auth/register", wrong_email_payload
        )
        invited_payload = self.registration("member@example.com") | {"invitation_token": token}
        invited = AsgiClient(client.application).request(
            "POST", "/api/library/auth/register", invited_payload
        )

        self.assertEqual(admin.status, 201)
        self.assertEqual(denied.status, 403)
        self.assertEqual(invitation.status, 201)
        self.assertEqual(wrong_email.status, 403)
        self.assertEqual(invited.status, 201)

    def test_administrator_approval_blocks_login_until_approved(self):
        client = AsgiClient(self.application(RegistrationPolicy.ADMINISTRATOR_APPROVED))
        client.request(
            "POST", "/api/library/auth/register", self.registration("admin@example.com", "Admin")
        )
        applicant = AsgiClient(client.application)
        pending = applicant.request(
            "POST", "/api/library/auth/register", self.registration("pending@example.com")
        )
        blocked = applicant.request(
            "POST",
            "/api/library/auth/login",
            {"email": "pending@example.com", "password": "correct horse battery"},
        )
        pending_users = client.request("GET", "/api/library/admin/pending-users")
        user_id = pending_users.json()["users"][0]["id"]
        approved = client.request(
            "POST", f"/api/library/admin/pending-users/{user_id}/approve"
        )
        logged_in = applicant.request(
            "POST",
            "/api/library/auth/login",
            {"email": "pending@example.com", "password": "correct horse battery"},
        )

        self.assertEqual(pending.status, 202)
        self.assertFalse(pending.json()["authenticated"])
        self.assertEqual(blocked.status, 401)
        self.assertEqual(approved.json()["user"]["status"], "active")
        self.assertEqual(logged_in.status, 200)

    def test_auth_pages_are_usable_and_internet_cookie_is_secure(self):
        client = AsgiClient(
            self.application(RegistrationPolicy.ADMINISTRATOR_APPROVED, "internet-facing")
        )
        page = (PROJECT_ROOT / "static" / "library-auth.html").read_bytes()
        registered = client.request(
            "POST", "/api/library/auth/register", self.registration("admin@example.com", "Admin")
        )

        self.assertIn(b'id="loginForm"', page)
        self.assertIn(b'id="signupForm"', page)
        self.assertIn(b"Library identity is separate from anonymous Drop", page)
        self.assertIn("Secure", registered.header("set-cookie"))

    def test_personal_tree_operations_use_opaque_objects_and_enforce_ownership(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("owner@example.com"))
        other = AsgiClient(application)
        other.request("POST", "/api/library/auth/register", self.registration("other@example.com"))

        root = owner.request("GET", "/api/library").json()["folder"]
        nested = owner.request(
            "POST", "/api/library/folders", {"parent_id": root["id"], "path": "Projects/2026"}
        )
        destination = owner.request(
            "POST", "/api/library/folders", {"parent_id": root["id"], "name": "Archive"}
        ).json()["folder"]
        folder_id = nested.json()["folder"]["id"]
        upload = owner.request(
            "PUT", f"/api/library/folders/{folder_id}/upload?name=roadmap.txt",
            body=b"private roadmap", headers={"content-type": "text/plain"},
        )
        file_id = upload.json()["file"]["id"]

        with application.state.library_database.transaction() as transaction:
            before = transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": file_id}
            )["object_id"]
        changed = owner.request(
            "PATCH", f"/api/library/files/{file_id}",
            {"name": "plans.txt", "parent_id": destination["id"]},
        )
        with application.state.library_database.transaction() as transaction:
            after = transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": file_id}
            )["object_id"]

        downloaded = owner.request("GET", f"/api/library/files/{file_id}/download")
        self.assertEqual(nested.status, 201)
        self.assertEqual(changed.json()["file"]["name"], "plans.txt")
        self.assertEqual(before, after)
        self.assertEqual(downloaded.body, b"private roadmap")
        self.assertEqual(other.request("GET", f"/api/library/folders/{folder_id}").status, 404)
        self.assertEqual(other.request("GET", f"/api/library/files/{file_id}/download").status, 404)
        self.assertEqual(other.request("PATCH", f"/api/library/files/{file_id}", {"name": "stolen.txt"}).status, 404)
        self.assertEqual(other.request("DELETE", f"/api/library/folders/{folder_id}").status, 404)

        projects_id = owner.request("GET", f"/api/library/folders/{folder_id}").json()["breadcrumbs"][-2]["id"]
        invalid_move = owner.request(
            "PATCH", f"/api/library/folders/{projects_id}", {"parent_id": folder_id}
        )
        self.assertEqual(invalid_move.status, 409)

        nested_upload = owner.request(
            "PUT", f"/api/library/folders/{folder_id}/upload?name=nested.bin",
            body=b"nested bytes", headers={"content-type": "application/octet-stream"},
        ).json()["file"]
        duplicated_tree = owner.request(
            "POST", f"/api/library/folders/{projects_id}/duplicate", {"parent_id": root["id"]}
        ).json()["folder"]
        copied_year = owner.request(
            "GET", f"/api/library/folders/{duplicated_tree['id']}"
        ).json()["folders"][0]
        copied_nested = owner.request(
            "GET", f"/api/library/folders/{copied_year['id']}"
        ).json()["files"][0]
        with application.state.library_database.transaction() as transaction:
            original_object = transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": nested_upload["id"]}
            )["object_id"]
            tree_copy_object = transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": copied_nested["id"]}
            )["object_id"]
        self.assertNotEqual(original_object, tree_copy_object)
        self.assertEqual(
            owner.request("GET", f"/api/library/files/{copied_nested['id']}/download").body,
            b"nested bytes",
        )
        self.assertEqual(owner.request("GET", "/api/library/tree").status, 200)

        logical_copy = owner.request(
            "POST", f"/api/library/files/{file_id}/copy", {"parent_id": destination["id"]}
        ).json()["file"]
        physical_copy = owner.request(
            "POST", f"/api/library/files/{file_id}/duplicate", {"parent_id": destination["id"]}
        ).json()["file"]
        with application.state.library_database.transaction() as transaction:
            copied = transaction.fetch_one("SELECT object_id FROM library_files WHERE id = :id", {"id": logical_copy["id"]})
            duplicated = transaction.fetch_one("SELECT object_id FROM library_files WHERE id = :id", {"id": physical_copy["id"]})
        self.assertEqual(copied["object_id"], before)
        self.assertNotEqual(duplicated["object_id"], before)
        self.assertEqual(owner.request("GET", f"/api/library/files/{physical_copy['id']}/download").body, b"private roadmap")

        self.assertEqual(owner.request("DELETE", f"/api/library/files/{file_id}").status, 204)
        self.assertEqual(owner.request("GET", f"/api/library/files/{file_id}/download").status, 404)

    def test_workspace_collaboration_scope_limit_and_membership_release(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        member = AsgiClient(application)
        outsider = AsgiClient(application)
        owner_user = owner.request("POST", "/api/library/auth/register", self.registration("owner@workspace.test", "Owner")).json()["user"]
        member_user = member.request("POST", "/api/library/auth/register", self.registration("member@workspace.test", "Member")).json()["user"]
        outsider_user = outsider.request("POST", "/api/library/auth/register", self.registration("outsider@workspace.test", "Outsider")).json()["user"]

        created = owner.request("POST", "/api/workspaces", {"name": "Community Docs"})
        workspace = created.json()["workspace"]
        added = owner.request(
            "POST", f"/api/workspaces/{workspace['id']}/members",
            {"email": "member@workspace.test"},
        )
        detail = member.request("GET", f"/api/workspaces/{workspace['id']}")
        root = detail.json()["folder"]
        folder = member.request(
            "POST", f"/api/workspaces/{workspace['id']}/folders",
            {"parent_id": root["id"], "name": "Shared"},
        ).json()["folder"]
        shared_file = member.request(
            "PUT", f"/api/workspaces/{workspace['id']}/folders/{folder['id']}/upload?name=notes.txt",
            body=b"member contribution", headers={"content-type": "text/plain"},
        ).json()["file"]

        self.assertEqual(created.status, 201)
        self.assertEqual(created.json()["policy"]["maximum_associations_per_user"], 1)
        self.assertEqual(added.status, 201)
        self.assertEqual(owner.request(
            "GET", f"/api/workspaces/{workspace['id']}/files/{shared_file['id']}/download"
        ).body, b"member contribution")
        self.assertEqual(outsider.request("GET", f"/api/workspaces/{workspace['id']}").status, 404)
        self.assertEqual(member.request("GET", f"/api/workspaces/{workspace['id']}/usage").status, 200)
        self.assertEqual(outsider.request("GET", f"/api/workspaces/{workspace['id']}/usage").status, 404)
        self.assertEqual(outsider.request(
            "PATCH", f"/api/workspaces/{workspace['id']}/files/{shared_file['id']}", {"name": "nope.txt"}
        ).status, 404)

        personal_root = owner.request("GET", "/api/library").json()["folder"]
        self.assertEqual(owner.request(
            "GET", f"/api/workspaces/{workspace['id']}/folders/{personal_root['id']}"
        ).status, 404)
        self.assertEqual(owner.request("GET", f"/api/library/folders/{root['id']}").status, 404)
        self.assertEqual(owner.request("POST", "/api/workspaces", {"name": "Second"}).status, 409)
        self.assertEqual(member.request("POST", "/api/workspaces", {"name": "Second"}).status, 409)
        self.assertEqual(owner.request(
            "POST", f"/api/workspaces/{workspace['id']}/members",
            {"email": member_user["email"]},
        ).status, 409)

        owner.request(
            "POST", f"/api/workspaces/{workspace['id']}/members",
            {"email": outsider_user["email"]},
        )
        self.assertEqual(owner.request(
            "DELETE", f"/api/workspaces/{workspace['id']}/members/{outsider_user['id']}"
        ).status, 204)
        outsider_workspace = outsider.request("POST", "/api/workspaces", {"name": "Freed User Space"})
        self.assertEqual(outsider_workspace.status, 201)

        left = owner.request("DELETE", f"/api/workspaces/{workspace['id']}/members/me")
        self.assertEqual(left.json()["new_owner_user_id"], member_user["id"])
        self.assertEqual(owner.request("GET", f"/api/workspaces/{workspace['id']}").status, 404)
        self.assertEqual(member.request("GET", f"/api/workspaces/{workspace['id']}").status, 200)
        self.assertEqual(member.request(
            "DELETE", f"/api/workspaces/{workspace['id']}/members/me"
        ).status, 409)
        self.assertEqual(owner.request("POST", "/api/workspaces", {"name": "Owner Is Free"}).status, 201)

    def test_personal_trash_recursively_hides_and_restores_a_tree(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("trash@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        top = client.request(
            "POST", "/api/library/folders", {"parent_id": root["id"], "name": "Projects"}
        ).json()["folder"]
        child = client.request(
            "POST", "/api/library/folders", {"parent_id": top["id"], "name": "Current"}
        ).json()["folder"]
        item = client.request(
            "PUT", f"/api/library/folders/{child['id']}/upload?name=plan.txt",
            body=b"recover me", headers={"content-type": "text/plain"},
        ).json()["file"]

        self.assertEqual(client.request("DELETE", f"/api/library/folders/{top['id']}").status, 204)
        self.assertEqual(client.request("GET", f"/api/library/folders/{top['id']}").status, 404)
        self.assertEqual(client.request("GET", f"/api/library/files/{item['id']}/download").status, 404)
        trash = client.request("GET", "/api/library/trash").json()
        self.assertEqual([folder["id"] for folder in trash["folders"]], [top["id"]])
        self.assertEqual(trash["files"], [])

        restored = client.request(
            "POST", f"/api/library/trash/folders/{top['id']}/restore"
        )
        nested = client.request("GET", f"/api/library/folders/{child['id']}")
        self.assertEqual(restored.status, 200)
        self.assertEqual(nested.status, 200)
        self.assertEqual(nested.json()["files"][0]["id"], item["id"])
        self.assertEqual(client.request("GET", f"/api/library/files/{item['id']}/download").body, b"recover me")
        self.assertEqual(client.request("GET", "/api/library/trash").json()["folders"], [])

    def test_restore_uses_root_and_predictable_copy_name_when_parent_is_missing(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("restore@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        folder = client.request(
            "POST", "/api/library/folders", {"parent_id": root["id"], "name": "Old"}
        ).json()["folder"]
        item = client.request(
            "PUT", f"/api/library/folders/{folder['id']}/upload?name=notes.txt",
            body=b"old", headers={"content-type": "text/plain"},
        ).json()["file"]
        client.request("PUT", f"/api/library/folders/{root['id']}/upload?name=notes.txt&confirm_duplicates=true",
                       body=b"new", headers={"content-type": "text/plain"})
        client.request("DELETE", f"/api/library/files/{item['id']}")
        client.request("DELETE", f"/api/library/folders/{folder['id']}")

        restored = client.request("POST", f"/api/library/trash/files/{item['id']}/restore")
        self.assertEqual(restored.status, 200)
        self.assertEqual(restored.json()["file"]["folder_id"], root["id"])
        self.assertEqual(restored.json()["file"]["name"], "notes copy.txt")

    def test_workspace_trash_is_scope_isolated_and_membership_authorized(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner, member, outsider = AsgiClient(application), AsgiClient(application), AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("trash-owner@example.com"))
        member_user = member.request(
            "POST", "/api/library/auth/register", self.registration("trash-member@example.com")
        ).json()["user"]
        outsider.request("POST", "/api/library/auth/register", self.registration("trash-out@example.com"))
        workspace = owner.request("POST", "/api/workspaces", {"name": "Shared Trash"}).json()["workspace"]
        owner.request("POST", f"/api/workspaces/{workspace['id']}/members", {"email": member_user["email"]})
        root = owner.request("GET", f"/api/workspaces/{workspace['id']}").json()["folder"]
        item = member.request(
            "PUT", f"/api/workspaces/{workspace['id']}/folders/{root['id']}/upload?name=shared.txt",
            body=b"shared", headers={"content-type": "text/plain"},
        ).json()["file"]
        member.request("DELETE", f"/api/workspaces/{workspace['id']}/files/{item['id']}")

        self.assertEqual(owner.request("GET", "/api/library/trash").json()["files"], [])
        workspace_trash = owner.request("GET", f"/api/workspaces/{workspace['id']}/trash")
        self.assertEqual(workspace_trash.json()["files"][0]["id"], item["id"])
        self.assertEqual(outsider.request("GET", f"/api/workspaces/{workspace['id']}/trash").status, 404)
        self.assertEqual(outsider.request(
            "POST", f"/api/workspaces/{workspace['id']}/trash/files/{item['id']}/restore"
        ).status, 404)
        self.assertEqual(member.request(
            "POST", f"/api/workspaces/{workspace['id']}/trash/files/{item['id']}/restore"
        ).status, 200)

    def test_permanent_delete_preserves_shared_and_derived_object_references(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("refs@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        original = client.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=source.bin",
            body=b"shared bytes", headers={"content-type": "application/octet-stream"},
        ).json()["file"]
        logical_copy = client.request(
            "POST", f"/api/library/files/{original['id']}/copy", {"parent_id": root["id"]}
        ).json()["file"]
        with application.state.library_database.transaction() as transaction:
            object_value = transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": original["id"]}
            )["object_id"]
        object_id = ObjectId.parse(object_value)

        client.request("DELETE", f"/api/library/files/{original['id']}")
        first = client.request("DELETE", f"/api/library/trash/files/{original['id']}")
        self.assertFalse(first.json()["physical_object_deleted"])
        self.assertTrue(application.state.personal_library.storage.object_exists(object_id))

        repository = application.state.personal_library.repository
        repository.add_object_reference(object_id, "derived", "preview-1")
        client.request("DELETE", f"/api/library/files/{logical_copy['id']}")
        second = client.request("DELETE", f"/api/library/trash/files/{logical_copy['id']}")
        self.assertFalse(second.json()["physical_object_deleted"])
        self.assertTrue(application.state.personal_library.storage.object_exists(object_id))
        repository.remove_object_reference(object_id, "derived", "preview-1")
        self.assertTrue(application.state.library_trash.reclaim_unreferenced_object(object_id))
        self.assertFalse(application.state.personal_library.storage.object_exists(object_id))

    def test_permanent_folder_delete_recursively_removes_logical_tree_and_bytes(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("purge-tree@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        top = client.request("POST", "/api/library/folders", {
            "parent_id": root["id"], "path": "Discard/Nested"
        }).json()["folder"]
        item = client.request(
            "PUT", f"/api/library/folders/{top['id']}/upload?name=gone.bin",
            body=b"gone", headers={"content-type": "application/octet-stream"},
        ).json()["file"]
        with application.state.library_database.transaction() as transaction:
            object_id = ObjectId.parse(transaction.fetch_one(
                "SELECT object_id FROM library_files WHERE id = :id", {"id": item["id"]}
            )["object_id"])
        parent_id = client.request("GET", f"/api/library/folders/{top['id']}").json()["breadcrumbs"][-2]["id"]
        client.request("DELETE", f"/api/library/folders/{parent_id}")

        purged = client.request("DELETE", f"/api/library/trash/folders/{parent_id}")
        self.assertEqual(purged.json()["physical_objects_deleted"], 1)
        self.assertFalse(application.state.personal_library.storage.object_exists(object_id))
        with application.state.library_database.transaction() as transaction:
            self.assertEqual(transaction.fetch_one(
                "SELECT COUNT(*) AS total FROM library_folders WHERE id IN (:parent, :child)",
                {"parent": parent_id, "child": top["id"]},
            )["total"], 0)

    def test_retention_cleanup_purges_expired_items_only(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("retention@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        old = client.request("PUT", f"/api/library/folders/{root['id']}/upload?name=old.txt",
                             body=b"old", headers={"content-type": "text/plain"}).json()["file"]
        recent = client.request("PUT", f"/api/library/folders/{root['id']}/upload?name=recent.txt",
                                body=b"recent", headers={"content-type": "text/plain"}).json()["file"]
        client.request("DELETE", f"/api/library/files/{old['id']}")
        client.request("DELETE", f"/api/library/files/{recent['id']}")
        now = datetime.now(timezone.utc)
        application.state.library_trash.retention_seconds = 60
        with application.state.library_database.transaction() as transaction:
            transaction.execute(
                "UPDATE library_files SET trashed_at = :at WHERE id = :id",
                {"at": (now - timedelta(seconds=61)).isoformat(), "id": old["id"]},
            )

        result = application.state.library_trash.cleanup_expired(now)
        remaining = client.request("GET", "/api/library/trash").json()["files"]
        self.assertEqual(result["purged_items"], 1)
        self.assertEqual([item["id"] for item in remaining], [recent["id"]])
        self.assertEqual(client.request("DELETE", f"/api/library/trash/files/{old['id']}").status, 404)

    def test_concurrent_workspace_creation_cannot_bypass_community_limit(self):
        application = self.application(RegistrationPolicy.OPEN)
        original = AsgiClient(application)
        original.request("POST", "/api/library/auth/register", self.registration("race@workspace.test", "Racer"))
        first = AsgiClient(application)
        second = AsgiClient(application)
        first.cookies = dict(original.cookies)
        second.cookies = dict(original.cookies)
        barrier = threading.Barrier(2)

        def create(client, name):
            barrier.wait()
            return client.request("POST", "/api/workspaces", {"name": name}).status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(create, first, "Race One"),
                executor.submit(create, second, "Race Two"),
            ]
            statuses = sorted(future.result() for future in futures)

        self.assertEqual(statuses, [201, 409])
        with application.state.library_database.transaction() as transaction:
            memberships = transaction.fetch_one(
                "SELECT COUNT(*) AS total FROM library_workspace_memberships"
            )["total"]
            workspaces = transaction.fetch_one("SELECT COUNT(*) AS total FROM library_workspaces")["total"]
        self.assertEqual((memberships, workspaces), (1, 1))

    def test_concurrent_workspace_joins_allow_only_one_association(self):
        application = self.application(RegistrationPolicy.OPEN)
        first_owner = AsgiClient(application)
        second_owner = AsgiClient(application)
        target = AsgiClient(application)
        first_owner.request("POST", "/api/library/auth/register", self.registration("first@join.test", "First"))
        second_owner.request("POST", "/api/library/auth/register", self.registration("second@join.test", "Second"))
        target_user = target.request("POST", "/api/library/auth/register", self.registration("target@join.test", "Target")).json()["user"]
        first_workspace = first_owner.request("POST", "/api/workspaces", {"name": "First Space"}).json()["workspace"]
        second_workspace = second_owner.request("POST", "/api/workspaces", {"name": "Second Space"}).json()["workspace"]
        barrier = threading.Barrier(2)

        def join(client, workspace_id):
            barrier.wait()
            return client.request(
                "POST", f"/api/workspaces/{workspace_id}/members", {"email": target_user["email"]}
            ).status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(join, first_owner, first_workspace["id"]),
                executor.submit(join, second_owner, second_workspace["id"]),
            ]
            statuses = sorted(future.result() for future in futures)

        self.assertEqual(statuses, [201, 409])
        with application.state.library_database.transaction() as transaction:
            associations = transaction.fetch_one(
                """SELECT COUNT(*) AS total FROM library_workspace_memberships
                   WHERE user_id = :user_id""", {"user_id": target_user["id"]}
            )["total"]
        self.assertEqual(associations, 1)

    def test_first_class_library_text_crud_search_and_trash_lifecycle(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("text@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]

        created = client.request(
            "POST", f"/api/library/folders/{root['id']}/texts",
            {"title": "Deploy Notes", "content": "print('hello')", "mode": "code",
             "language": "python", "source_kind": "manual", "source_id": "draft-1"},
        )
        item = created.json()["text"]
        listing = client.request("GET", "/api/library").json()
        searched = client.request("GET", "/api/library/search?q=deploy%20note&scope=personal").json()

        self.assertEqual(created.status, 201)
        self.assertEqual((item["type"], item["lifecycle"], item["mode"], item["language"]),
                         ("text", "persistent", "code", "python"))
        self.assertEqual(listing["texts"][0]["id"], item["id"])
        self.assertNotIn("content", listing["texts"][0])
        self.assertEqual(searched["results"][0]["type"], "text")

        updated = client.request(
            "PATCH", f"/api/library/texts/{item['id']}",
            {"title": "Deploy Checklist", "content": "one\ntwo", "mode": "plain"},
        ).json()["text"]
        self.assertEqual((updated["title"], updated["content"], updated["mode"], updated["language"]),
                         ("Deploy Checklist", "one\ntwo", "plain", None))

        self.assertEqual(client.request("DELETE", f"/api/library/texts/{item['id']}").status, 204)
        trash = client.request("GET", "/api/library/trash").json()
        self.assertEqual(trash["texts"][0]["id"], item["id"])
        restored = client.request(
            "POST", f"/api/library/trash/texts/{item['id']}/restore"
        ).json()["text"]
        self.assertEqual(restored["title"], "Deploy Checklist")

        client.request("DELETE", f"/api/library/texts/{item['id']}")
        deleted = client.request("DELETE", f"/api/library/trash/texts/{item['id']}")
        self.assertEqual(deleted.json(), {"permanently_deleted": True})
        self.assertEqual(client.request("GET", f"/api/library/texts/{item['id']}").status, 404)

    def test_library_text_shares_are_read_only_reusable_and_do_not_delete_source(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("text-share@example.com"))
        root = owner.request("GET", "/api/library").json()["folder"]
        item = owner.request(
            "POST", "/api/library/texts",
            {"folder_id": root["id"], "title": "Public note", "content": "shared text",
             "mode": "markdown"},
        ).json()["text"]
        created = owner.request(
            "POST", f"/api/library/texts/{item['id']}/shares",
            {"expires_in_seconds": 0, "access_key_protected": True},
        ).json()
        share = created["share"]
        parsed = urlsplit(share["share_url"])
        info_path = parsed.path.replace("/s/", "/api/public/shares/") + f"?{parsed.query}"
        download_path = info_path.replace("?", "/download?")

        first = AsgiClient(application).request("GET", info_path)
        second = AsgiClient(application).request("GET", info_path)
        downloaded = AsgiClient(application).request("GET", download_path)
        recipient_page = AsgiClient(application).request("GET", parsed.path + f"?{parsed.query}")
        self.assertEqual((first.status, second.status, downloaded.status), (200, 200, 200))
        self.assertEqual(first.json()["share"]["content"], "shared text")
        self.assertTrue(first.json()["share"]["read_only"])
        self.assertEqual(downloaded.body, b"shared text")
        self.assertIn(b'Read-only shared Text', recipient_page.body)
        self.assertIn("object-src 'none'", recipient_page.header("content-security-policy"))

        self.assertEqual(owner.request("DELETE", f"/api/library/shares/{share['id']}").status, 204)
        self.assertEqual(AsgiClient(application).request("GET", info_path).status, 404)
        self.assertEqual(
            owner.request("GET", f"/api/library/texts/{item['id']}").json()["text"]["content"],
            "shared text",
        )

    def test_text_editor_page_is_authenticated_csp_restricted_and_saves_large_mode_changes(self):
        application = self.application(RegistrationPolicy.OPEN)
        anonymous = AsgiClient(application)
        self.assertEqual(anonymous.request("GET", "/library/texts/missing").status, 303)

        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("editor@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        item = client.request("POST", f"/api/library/folders/{root['id']}/texts", {
            "title": "Editor test", "content": "# Start", "mode": "markdown",
        }).json()["text"]

        page = client.request("GET", f"/library/texts/{item['id']}")
        self.assertEqual(page.status, 200)
        self.assertIn(b'id="textContent"', page.body)
        self.assertIn("object-src 'none'", page.header("content-security-policy"))

        large_source = "const safe = true;\n" * 1500
        saved = client.request("PATCH", f"/api/library/texts/{item['id']}", {
            "title": "Editor test", "content": large_source, "mode": "code",
            "language": "javascript",
        })
        self.assertEqual(saved.status, 200)
        self.assertEqual(saved.json()["text"]["mode"], "code")
        self.assertEqual(saved.json()["text"]["language"], "javascript")
        self.assertEqual(saved.json()["text"]["content"], large_source)

    def test_unified_file_detail_and_preview_use_stored_bytes_and_restrict_active_content(self):
        application = self.application(RegistrationPolicy.OPEN)
        client = AsgiClient(application)
        client.request("POST", "/api/library/auth/register", self.registration("preview@example.com"))
        root = client.request("GET", "/api/library").json()["folder"]
        image_bytes = b"\x89PNG\r\n\x1a\npreview-fixture"
        image = client.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=sample.bin",
            body=image_bytes, headers={"content-type": "text/html"},
        ).json()["file"]
        active = client.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=attack.png",
            body=b"<!doctype html><script>parent.location='https://evil.test'</script>",
            headers={"content-type": "image/png"},
        ).json()["file"]

        detail = client.request("GET", f"/api/library/files/{image['id']}").json()
        active_detail = client.request("GET", f"/api/library/files/{active['id']}").json()
        preview = client.request("GET", f"/api/library/files/{image['id']}/preview")
        blocked = client.request("GET", f"/api/library/files/{active['id']}/preview")
        page = client.request("GET", f"/library/files/{image['id']}")

        self.assertEqual((detail["content_kind"], detail["preview"]["detected_mime"]),
                         ("image", "image/png"))
        self.assertEqual(detail["preview"]["declared_mime"], "text/html")
        self.assertEqual((active_detail["preview"]["available"], active_detail["preview"]["kind"]),
                         (False, "active"))
        self.assertEqual(preview.body, image_bytes)
        self.assertEqual(preview.header("content-type"), "image/png")
        self.assertEqual(preview.header("content-disposition"), 'inline; filename="nightwire-preview"')
        self.assertEqual(preview.header("x-content-type-options"), "nosniff")
        self.assertIn("sandbox", preview.header("content-security-policy"))
        self.assertEqual(blocked.status, 415)
        self.assertNotIn(b"<script>", blocked.body)
        self.assertEqual(page.status, 200)
        for section in [b"Preview", b"Properties", b"Security", b"Versions",
                        b"Derived Outputs", b"Toolkit", b"Sharing"]:
            self.assertIn(section, page.body)
        self.assertIn("frame-src 'self'", page.header("content-security-policy"))

    def test_public_file_share_exposes_only_the_restricted_preview_endpoint(self):
        application = self.application(RegistrationPolicy.OPEN)
        owner = AsgiClient(application)
        owner.request("POST", "/api/library/auth/register", self.registration("shared-preview@example.com"))
        root = owner.request("GET", "/api/library").json()["folder"]
        item = owner.request(
            "PUT", f"/api/library/folders/{root['id']}/upload?name=notes.md",
            body=b"# Shared\n\nSafe text", headers={"content-type": "text/html"},
        ).json()["file"]
        shared = owner.request(
            "POST", f"/api/library/files/{item['id']}/shares",
            {"expires_in_seconds": 0, "access_key_protected": True},
        ).json()["share"]
        parsed = urlsplit(shared["share_url"])
        info_path = parsed.path.replace("/s/", "/api/public/shares/") + f"?{parsed.query}"
        public = AsgiClient(application)
        info = public.request("GET", info_path).json()["share"]
        preview = public.request("GET", info["preview_url"])

        self.assertEqual((info["preview"]["available"], info["preview"]["kind"]),
                         (True, "markdown"))
        self.assertEqual(preview.body, b"# Shared\n\nSafe text")
        self.assertTrue(preview.header("content-type").startswith("text/plain"))
        self.assertEqual(preview.header("x-content-type-options"), "nosniff")
        self.assertNotIn("notes.md", preview.header("content-disposition"))


if __name__ == "__main__":
    unittest.main()
