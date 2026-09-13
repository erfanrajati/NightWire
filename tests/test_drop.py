import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from nightwire.app.passwords import PasswordProtection
from nightwire.core.lifecycle import CoreLifecycleService
from nightwire.core.security import CoreSecurityPipeline
from nightwire.core.storage import LocalFilesystemStorage
from nightwire.core.transfer import CoreTransferService
from nightwire.drop.domain import DropItem, PasswordDigest
from nightwire.drop.repository import DropRepository, LocalDropRepository
from nightwire.drop.service import DropService, ProtectedDropOverwriteError


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
            validate_name=validate,
            lock=threading.RLock(),
            metadata_filename=".nightwire-metadata.json",
            default_expiry_seconds=0,
            minimum_expiry_seconds=60,
            maximum_expiry_seconds=31_536_000,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def upload(self, name, content, *, password=None):
        async def chunks():
            yield content[:2]
            yield content[2:]

        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            return asyncio.run(
                self.service.upload(
                    filename=name,
                    chunks=chunks(),
                    expires_in_seconds=0,
                    password=password,
                    declared_mime="text/plain",
                )
            )

    def test_service_composes_core_and_repository_for_upload_lifecycle_download_and_delete(self):
        uploaded = self.upload("note.txt", b"hello Drop")

        self.assertEqual(self.repository.get("note.txt"), uploaded.item)
        self.assertEqual(self.service.download("note.txt").item.object_id, uploaded.item.object_id)
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
            self.service.download("protected.txt", supplied_password="wrong", verify_protected=True)
        with self.assertRaises(ProtectedDropOverwriteError):
            self.upload("protected.txt", b"replacement")
        self.service.delete("protected.txt", "correct")


if __name__ == "__main__":
    unittest.main()
