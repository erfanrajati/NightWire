import asyncio
import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from nightwire.app.passwords import PasswordProtection
from nightwire.core.config import DeploymentProfile
from nightwire.core.lifecycle import CoreLifecycleService
from nightwire.core.security import (
    CoreSecurityPipeline,
    MalwareScanResult,
    MalwareScannerAdapter,
    SecurityVerdict,
)
from nightwire.core.storage import LocalFilesystemStorage
from nightwire.core.transfer import CoreTransferService
from nightwire.drop.access import DropAccessKeyPolicy
from nightwire.drop.domain import DropItem, PasswordDigest
from nightwire.drop.repository import DropRepository, LocalDropRepository
from nightwire.drop.service import (
    DropAccessDeniedError,
    DropService,
    MaliciousDropConfirmationRequiredError,
    ProtectedDropOverwriteError,
)


class _MaliciousScanner(MalwareScannerAdapter):
    @property
    def name(self):
        return "test-malware"

    async def scan(self, object_id, storage, detected_mime):
        return MalwareScanResult(SecurityVerdict.MALICIOUS, self.name, "test-signature")


class _ImmediateAsyncFile:
    def __init__(self, path, mode="r"):
        self._file = open(path, mode)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._file.close()

    async def read(self, size=-1):
        return self._file.read(size)

    async def write(self, data):
        return self._file.write(data)

    async def flush(self):
        return self._file.flush()


async def _immediate_open_file(path, mode="r", *args, **kwargs):
    return _ImmediateAsyncFile(path, mode)


class DropDomainRepositoryTests(unittest.TestCase):
    def test_repository_contract_is_abstract(self):
        with self.assertRaises(TypeError):
            DropRepository()

    def test_domain_round_trips_without_legacy_route_or_response_shapes(self):
        item = DropItem(
            name="report.bin",
            created_at="2026-09-13T00:00:00+00:00",
            expires_at=None,
            password=PasswordDigest("c2FsdA==", "ZGlnZXN0"),
            checksum_sha256="a" * 64,
            size=12,
        )

        record = item.to_record()

        self.assertEqual(record["password"], {"salt": "c2FsdA==", "digest": "ZGlnZXN0"})
        self.assertNotIn("download_url", record)
        self.assertNotIn("password_protected", record)

    def test_local_repository_loads_legacy_metadata_and_atomically_persists_domain_items(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".nightwire-metadata.json"
            path.write_text(
                json.dumps(
                    {
                        "legacy.txt": {
                            "created_at": "2026-09-13T00:00:00+00:00",
                            "expires_at": None,
                            "password": None,
                        }
                    }
                ),
                encoding="utf-8",
            )
            repository = LocalDropRepository(path)

            repository.load()
            legacy = repository.get("legacy.txt")
            repository.put(DropItem("new.txt", legacy.created_at, None))
            repository.save()

            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(persisted), {"legacy.txt", "new.txt"})
            self.assertEqual(repository.list()[0].name, "legacy.txt")
            self.assertEqual(list(path.parent.glob("..nightwire-metadata.json.*.tmp")), [])


class DropServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = LocalFilesystemStorage(self.root)
        self.repository = LocalDropRepository(self.root / ".nightwire-metadata.json")
        self.passwords = PasswordProtection(256)
        self.access_keys = DropAccessKeyPolicy()

        def validate(name):
            if not name or Path(name).name != name or "/" in name or "\\" in name:
                raise ValueError("Invalid file path.")
            return self.root / name

        transfer = CoreTransferService(self.storage)
        self.service = DropService(
            repository=self.repository,
            storage=self.storage,
            legacy_root=self.root,
            transfer=transfer,
            lifecycle=CoreLifecycleService(),
            security=CoreSecurityPipeline(self.storage),
            passwords=self.passwords,
            access_keys=self.access_keys,
            validate_name=validate,
            lock=threading.RLock(),
            metadata_filename=".nightwire-metadata.json",
            default_expiry_seconds=3600,
            minimum_expiry_seconds=60,
            maximum_expiry_seconds=31_536_000,
            deployment_profile=DeploymentProfile.TRUSTED_PRIVATE,
            anonymous_internet_maximum_expiry_seconds=86_400,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def upload(self, name, content, *, password=None, expires_in_seconds=None, content_kind="file"):
        async def chunks():
            yield content[:2]
            yield content[2:]

        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            return asyncio.run(
                self.service.upload(
                    filename=name,
                    chunks=chunks(),
                    expires_in_seconds=expires_in_seconds,
                    password=password,
                    declared_mime="text/plain",
                    content_kind=content_kind,
                )
            )

    def test_service_composes_core_and_repository_for_upload_lifecycle_download_and_delete(self):
        uploaded = self.upload("note.txt", b"hello Drop")

        self.assertEqual(self.repository.get("note.txt"), uploaded.item)
        self.assertEqual(
            self.service.download("note.txt", access_key=uploaded.access_key).item.object_id,
            uploaded.item.object_id,
        )
        self.assertEqual(self.service.list_items(), (uploaded.item,))
        updated = self.service.update_expiry("note.txt", {"expires_in_seconds": 60})
        self.assertIsNotNone(updated.expires_at)
        self.service.delete("note.txt")
        self.assertIsNone(self.repository.get("note.txt"))
        self.assertFalse(self.storage.object_exists(uploaded.item.object_id))

    def test_password_policy_is_service_owned_and_protected_items_cannot_be_overwritten(self):
        uploaded = self.upload("protected.txt", b"secret", password="correct")

        self.assertTrue(uploaded.item.password_protected)
        self.assertFalse(self.passwords.verify("correct", PasswordDigest("c2FsdA==", "ZGlnZXN0")))
        with self.assertRaises(PermissionError):
            self.service.download(
                "protected.txt",
                access_key=uploaded.access_key,
                supplied_password="wrong",
                verify_protected=True,
            )
        with self.assertRaises(ProtectedDropOverwriteError):
            self.upload("protected.txt", b"replacement")
        self.service.delete("protected.txt", "correct")

    def test_new_drops_have_explicit_one_hour_timestamps_and_configurable_lifetime(self):
        default = self.upload("default.bin", b"default")
        configured = self.upload("configured.bin", b"configured", expires_in_seconds=21_600)

        default_created = self.service._parse_timestamp(default.item.created_at)
        default_expires = self.service._parse_timestamp(default.item.expires_at)
        configured_created = self.service._parse_timestamp(configured.item.created_at)
        configured_expires = self.service._parse_timestamp(configured.item.expires_at)
        self.assertAlmostEqual(default_expires - default_created, 3600, delta=0.01)
        self.assertAlmostEqual(configured_expires - configured_created, 21_600, delta=0.01)
        with self.assertRaisesRegex(ValueError, "at least 1 minute"):
            self.upload("unlimited.bin", b"not allowed", expires_in_seconds=0)

    def test_internet_facing_anonymous_drops_have_a_hard_24_hour_maximum(self):
        self.service.deployment_profile = DeploymentProfile.INTERNET_FACING

        accepted = self.upload("day.bin", b"day", expires_in_seconds=86_400)
        self.assertIsNotNone(accepted.item.expires_at)
        with self.assertRaisesRegex(ValueError, "24 hours"):
            self.upload("too-long.bin", b"long", expires_in_seconds=86_401)
        with self.assertRaisesRegex(ValueError, "24 hours"):
            self.service.update_expiry("day.bin", {"expires_in_seconds": 86_401})

    def test_access_keys_are_unique_authenticated_and_never_persisted_raw(self):
        first = self.upload("first.bin", b"first")
        second = self.upload("second.bin", b"second")

        self.assertRegex(first.access_key, r"^[A-Za-z0-9_-]{43}$")
        self.assertNotEqual(first.access_key, second.access_key)
        metadata = (self.root / ".nightwire-metadata.json").read_text(encoding="utf-8")
        self.assertNotIn(first.access_key, metadata)
        self.assertIn("access_key_digest", metadata)
        with self.assertRaises(DropAccessDeniedError):
            self.service.download("first.bin")
        with self.assertRaises(DropAccessDeniedError):
            self.service.download("first.bin", access_key=second.access_key)
        self.assertEqual(
            self.service.download("first.bin", access_key=first.access_key).item,
            first.item,
        )

    def test_expiration_atomically_revokes_access_and_removes_metadata_sidecar_and_bytes(self):
        uploaded = self.upload("ephemeral.bin", b"ephemeral")
        object_id = uploaded.item.object_id
        object_path = self.storage.object_reference(object_id)
        sidecar_path = self.storage.object_metadata_reference(object_id)
        expired = replace(uploaded.item, expires_at=self.service._iso(time.time() - 1))
        self.repository.put(expired)
        self.repository.save()

        self.assertTrue(self.service.purge_expired())

        self.assertFalse(object_path.exists())
        self.assertFalse(sidecar_path.exists())
        self.assertIsNone(self.repository.get("ephemeral.bin"))
        self.assertNotIn("ephemeral.bin", (self.root / ".nightwire-metadata.json").read_text(encoding="utf-8"))
        with self.assertRaises(FileNotFoundError):
            self.service.download("ephemeral.bin", access_key=uploaded.access_key)

    def test_content_kind_round_trips_and_rejects_unknown_types(self):
        uploaded = self.upload("message.txt", b"hello", content_kind="text")

        self.assertEqual(uploaded.item.content_kind, "text")
        self.assertEqual(self.repository.get("message.txt").content_kind, "text")
        self.assertEqual(self.service.public_record(uploaded.item)["content_kind"], "text")
        with self.assertRaisesRegex(ValueError, "content kind"):
            self.upload("bad.bin", b"bad", content_kind="archive")

    def test_malicious_drop_is_retained_and_requires_explicit_download_confirmation(self):
        self.service.security = CoreSecurityPipeline(self.storage, _MaliciousScanner())
        uploaded = self.upload("payload.txt", b"retained bytes")

        self.assertTrue(self.storage.object_exists(uploaded.item.object_id))
        self.assertEqual(uploaded.item.security["verdict"], "malicious")
        with self.assertRaises(MaliciousDropConfirmationRequiredError):
            self.service.download("payload.txt", access_key=uploaded.access_key)
        confirmed = self.service.download(
            "payload.txt",
            access_key=uploaded.access_key,
            confirmed_malicious=True,
        )
        self.assertEqual(confirmed.item, uploaded.item)
        public = self.service.public_record(uploaded.item)
        self.assertEqual(public["security"]["verdict"], "malicious")
        self.assertTrue(public["download_confirmation_required"])

    def test_trusted_relaxation_bypasses_keys_but_internet_profile_never_does(self):
        uploaded = self.upload("private.bin", b"private")
        self.service.trusted_network_relaxed_access = True

        self.assertFalse(self.service.access_key_enforced)
        self.assertEqual(self.service.download("private.bin").item, uploaded.item)
        self.assertFalse(self.service.public_record(uploaded.item)["access_key_required"])

        self.service.deployment_profile = DeploymentProfile.INTERNET_FACING
        self.service.trusted_network_active_drop_browsing = True
        self.assertTrue(self.service.access_key_enforced)
        self.assertFalse(self.service.active_drop_browsing_allowed)
        with self.assertRaises(DropAccessDeniedError):
            self.service.download("private.bin")


if __name__ == "__main__":
    unittest.main()
