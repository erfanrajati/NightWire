import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nightwire.core.storage import (
    OBJECTS_DIRECTORY_NAME,
    TEMPORARY_UPLOADS_DIRECTORY_NAME,
    LocalFilesystemStorage,
    ObjectId,
    StorageBackend,
    TemporaryUploadId,
)
from nightwire.core.transfer import CoreTransferService, TransferService
from nightwire.core.transfer import TransferDirection, TransferPhase, TransferProgressStore


class _ImmediateAsyncFile:
    def __init__(self, path, mode):
        self._file = open(path, mode)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._file.close()

    async def write(self, data):
        return self._file.write(data)

    async def read(self, size=-1):
        return self._file.read(size)

    async def flush(self):
        return self._file.flush()


async def _immediate_open_file(path, mode="r", *args, **kwargs):
    return _ImmediateAsyncFile(path, mode)


class CoreStorageContractTests(unittest.TestCase):
    def test_storage_and_transfer_contracts_are_abstract_interfaces(self):
        with self.assertRaises(TypeError):
            StorageBackend()
        with self.assertRaises(TypeError):
            TransferService()

    def test_object_ids_are_stable_round_trippable_and_path_injection_safe(self):
        object_id = ObjectId.new()

        self.assertEqual(ObjectId.parse(str(object_id)), object_id)
        self.assertEqual(len(str(object_id)), 32)
        for invalid in ["", "../escape", "a" * 31, "A" * 32, "g" * 32, "/" + "a" * 32]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ObjectId.parse(invalid)

    def test_temporary_ids_reject_arbitrary_filesystem_references(self):
        for invalid in ["../upload", "/tmp/upload", "upload.part", "a" * 33]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                TemporaryUploadId(invalid)


class LocalFilesystemStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = LocalFilesystemStorage(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_backend_uses_hidden_object_and_temporary_roots_inside_existing_storage(self):
        self.assertEqual(self.storage.storage_root, self.root.resolve())
        self.assertEqual(self.storage.objects_root, self.root / OBJECTS_DIRECTORY_NAME)
        self.assertEqual(self.storage.temporary_uploads_root, self.root / TEMPORARY_UPLOADS_DIRECTORY_NAME)
        self.assertTrue(self.storage.objects_root.is_dir())
        self.assertTrue(self.storage.temporary_uploads_root.is_dir())

    def test_object_reference_depends_only_on_validated_object_id(self):
        object_id = ObjectId("0123456789abcdef0123456789abcdef")
        reference = self.storage.object_reference(object_id)

        self.assertEqual(reference, self.storage.objects_root / object_id.value)
        self.assertNotIn("original filename.txt", str(reference))
        self.assertEqual(reference.parent, self.storage.objects_root)

    def test_temporary_upload_is_isolated_and_atomically_finalized(self):
        upload_id = self.storage.allocate_temporary_upload()
        temporary_reference = self.storage.temporary_upload_reference(upload_id)
        temporary_reference.write_bytes(b"temporary payload")
        object_id = ObjectId("fedcba9876543210fedcba9876543210")

        stored = self.storage.finalize_temporary_upload(upload_id, object_id)

        self.assertEqual(stored.object_id, object_id)
        self.assertEqual(stored.size, len(b"temporary payload"))
        self.assertFalse(temporary_reference.exists())
        self.assertEqual(self.storage.object_reference(object_id).read_bytes(), b"temporary payload")
        self.assertGreater(self.storage.object_modified_at(object_id), 0)
        self.assertTrue(self.storage.object_exists(object_id))
        self.assertEqual(self.storage.object_size(object_id), len(b"temporary payload"))

        async def read_object():
            async with await self.storage.open_object(object_id) as source:
                return await source.read()

        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            self.assertEqual(asyncio.run(read_object()), b"temporary payload")
        with self.assertRaises(ValueError):
            asyncio.run(self.storage.open_object(object_id, "wb"))

        self.storage.delete_object(object_id)
        self.assertFalse(self.storage.object_exists(object_id))

    def test_finalization_refuses_to_replace_an_existing_object_id(self):
        object_id = ObjectId("0123456789abcdef0123456789abcdef")
        self.storage.object_reference(object_id).write_bytes(b"existing")
        upload_id = self.storage.allocate_temporary_upload()
        self.storage.temporary_upload_reference(upload_id).write_bytes(b"new")

        with self.assertRaises(FileExistsError):
            self.storage.finalize_temporary_upload(upload_id, object_id)

        self.assertEqual(self.storage.object_reference(object_id).read_bytes(), b"existing")
        self.assertTrue(self.storage.temporary_upload_exists(upload_id))

    def test_object_metadata_is_persisted_atomically_and_deleted_with_content(self):
        upload_id = self.storage.allocate_temporary_upload()
        self.storage.temporary_upload_reference(upload_id).write_bytes(b"object")
        stored = self.storage.finalize_temporary_upload(upload_id)

        self.storage.save_object_metadata(stored.object_id, {"security": {"verdict": "unscanned"}})

        self.assertEqual(
            self.storage.load_object_metadata(stored.object_id),
            {"security": {"verdict": "unscanned"}},
        )
        self.storage.delete_object(stored.object_id)
        self.assertIsNone(self.storage.load_object_metadata(stored.object_id))


class CoreTransferServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = LocalFilesystemStorage(self.temporary.name)
        self.transfer = CoreTransferService(self.storage)

    def tearDown(self):
        self.temporary.cleanup()

    def receive(self, chunks):
        async def stream():
            for chunk in chunks:
                yield chunk

        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            return asyncio.run(self.transfer.receive_upload(stream()))

    def test_streaming_calculates_sha256_before_controlled_finalization(self):
        chunks = [b"first", b"", b"\x00second\xff"]
        content = b"".join(chunks)

        pending = self.receive(chunks)

        self.assertEqual(pending.bytes_written, len(content))
        self.assertEqual(pending.checksum_sha256, hashlib.sha256(content).hexdigest())
        self.assertTrue(self.storage.temporary_upload_exists(pending.upload_id))
        self.assertEqual(list(self.storage.objects_root.iterdir()), [])

        object_id = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        completed = self.transfer.finalize_upload(pending, object_id)

        self.assertEqual(completed.object_id, object_id)
        self.assertEqual(completed.checksum_sha256, hashlib.sha256(content).hexdigest())
        self.assertFalse(self.storage.temporary_upload_exists(pending.upload_id))
        self.assertEqual(self.storage.object_reference(object_id).read_bytes(), content)

    def test_discard_removes_pending_upload_without_creating_an_object(self):
        pending = self.receive([b"discard me"])

        self.transfer.discard_upload(pending)

        self.assertFalse(self.storage.temporary_upload_exists(pending.upload_id))
        self.assertEqual(list(self.storage.objects_root.iterdir()), [])

    def test_stream_failure_removes_allocated_temporary_storage(self):
        async def failing_stream():
            yield b"partial"
            raise RuntimeError("stream failed")

        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            with self.assertRaisesRegex(RuntimeError, "stream failed"):
                asyncio.run(self.transfer.receive_upload(failing_stream()))

        self.assertEqual(list(self.storage.temporary_uploads_root.iterdir()), [])
        self.assertEqual(list(self.storage.objects_root.iterdir()), [])

    def test_download_streams_exact_chunks_and_records_progress(self):
        pending = self.receive([b"abcdefghij"])
        completed = self.transfer.finalize_upload(pending)

        async def collect(chunks):
            return b"".join([chunk async for chunk in chunks])

        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            download = self.transfer.prepare_download(completed.object_id, chunk_size=3)
            content = asyncio.run(collect(download.chunks))

        self.assertEqual(content, b"abcdefghij")
        progress = self.transfer.progress_store.get(download.transfer_id)
        self.assertEqual(progress.direction, TransferDirection.DOWNLOAD)
        self.assertEqual(progress.phase, TransferPhase.COMPLETED)
        self.assertEqual(progress.bytes_transferred, 10)
        self.assertEqual(progress.total_bytes, 10)
        self.assertEqual(progress.fraction, 1.0)

    def test_progress_hooks_and_bounded_state_receive_upload_transitions(self):
        events = []
        progress_store = TransferProgressStore(history_limit=1)
        transfer = CoreTransferService(
            self.storage,
            progress_store=progress_store,
            progress_hooks=[events.append],
        )
        self.transfer = transfer

        pending = self.receive([b"one", b"two"])
        completed = transfer.finalize_upload(pending)

        self.assertEqual([event.phase for event in events], [
            TransferPhase.STARTED,
            TransferPhase.TRANSFERRING,
            TransferPhase.TRANSFERRING,
            TransferPhase.PENDING,
            TransferPhase.FINALIZED,
        ])
        self.assertEqual(progress_store.get(completed.transfer_id).phase, TransferPhase.FINALIZED)
        self.assertEqual(len(progress_store.snapshot()), 1)


if __name__ == "__main__":
    unittest.main()
