import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from nightwire.core.capacity import (
    AllowAllCapacityPolicy,
    CapacityMeter,
    CapacityPolicy,
    CapacityRequest,
    CapacitySnapshot,
    CapacityExceededError,
    CommunityCapacityManager,
    UsageScope,
)
from nightwire.core.lifecycle import CoreLifecycleService, LifecycleItem, LifecycleService
from nightwire.core.security import (
    CoreSecurityPipeline,
    CoreSecurityPolicy,
    MalwareScanResult,
    MalwareScannerAdapter,
    SecurityAction,
    SecurityPipeline,
    SecurityVerdict,
    compare_mime_evidence,
    detect_mime_signature,
)
from nightwire.core.storage import LocalFilesystemStorage
from nightwire.processors import ContentProcessor, ProcessorContext, ProcessorExecutionResult, ProcessorRegistry


class _ImmediateAsyncFile:
    def __init__(self, path, mode="rb"):
        self._file = open(path, mode)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._file.close()

    async def read(self, size=-1):
        return self._file.read(size)


async def _immediate_open_file(path, mode="rb", *args, **kwargs):
    return _ImmediateAsyncFile(path, mode)


class CoreLifecycleTests(unittest.TestCase):
    def test_lifecycle_contract_and_expiration_classification(self):
        with self.assertRaises(TypeError):
            LifecycleService()
        service = CoreLifecycleService()

        sweep = service.sweep(
            [
                LifecycleItem("expired", expires_at=99, present=True),
                LifecycleItem("missing", expires_at=None, present=False),
                LifecycleItem("live", expires_at=101, present=True),
            ],
            now=100,
        )

        self.assertEqual(sweep.expired_ids, ("expired",))
        self.assertEqual(sweep.missing_ids, ("missing",))
        self.assertTrue(sweep.changed)

    def test_orphan_cleanup_removes_only_old_inactive_temporary_uploads(self):
        with tempfile.TemporaryDirectory() as temporary:
            storage = LocalFilesystemStorage(temporary)
            old = storage.allocate_temporary_upload()
            active = storage.allocate_temporary_upload()
            recent = storage.allocate_temporary_upload()
            old_time = 1_000.0
            os.utime(storage.temporary_upload_reference(old), (old_time, old_time))
            os.utime(storage.temporary_upload_reference(active), (old_time, old_time))

            removed = CoreLifecycleService().cleanup_orphaned_uploads(
                storage,
                older_than_seconds=100,
                active_upload_ids=[active],
                now=1_200,
            )

            self.assertEqual(removed, (old,))
            self.assertFalse(storage.temporary_upload_exists(old))
            self.assertTrue(storage.temporary_upload_exists(active))
            self.assertTrue(storage.temporary_upload_exists(recent))


class CapacityPolicyTests(unittest.TestCase):
    def test_capacity_contracts_are_abstract_and_default_policy_does_not_enforce_quota(self):
        with self.assertRaises(TypeError):
            CapacityMeter()
        with self.assertRaises(TypeError):
            CapacityPolicy()

        decision = AllowAllCapacityPolicy().evaluate(
            CapacityRequest(module="library", requested_bytes=900, current_module_bytes=10_000),
            CapacitySnapshot(total_bytes=1000, used_bytes=900, free_bytes=100),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.remaining_bytes, 0)

    def test_each_community_limit_and_host_reserve_can_deny_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            usage = {"installation": 7, "personal": 7, "workspace": 7, "drop": 7}
            for field, scope, expected in [
                ("installation_limit", UsageScope("personal", "u"), "Installation"),
                ("personal_limit", UsageScope("personal", "u"), "Personal"),
                ("workspace_limit", UsageScope("workspace", "w"), "Workspace"),
                ("drop_limit", UsageScope("drop"), "Drop"),
                ("object_limit", UsageScope("personal", "u"), "Maximum object"),
            ]:
                manager = CommunityCapacityManager(Path(temporary), **{field: 10})
                manager.add_usage_source(lambda candidate, values=usage: values.get(candidate.kind, 0))
                with self.assertRaisesRegex(CapacityExceededError, expected):
                    manager.reserve(scope, 4 if field != "object_limit" else 11)
            disk = mock.Mock(total=100, used=20, free=80)
            with mock.patch("nightwire.core.capacity.shutil.disk_usage", return_value=disk):
                manager = CommunityCapacityManager(Path(temporary), minimum_free=75)
                with self.assertRaisesRegex(CapacityExceededError, "free-space reserve"):
                    manager.reserve(UsageScope("drop"), 6)

    def test_parallel_reservations_cannot_bypass_scope_quota(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = CommunityCapacityManager(Path(temporary), personal_limit=10)
            barrier, results = threading.Barrier(2), []
            def reserve():
                barrier.wait()
                try:
                    manager.reserve(UsageScope("personal", "same-user"), 6); results.append("allowed")
                except CapacityExceededError:
                    results.append("denied")
            threads = [threading.Thread(target=reserve) for _ in range(2)]
            [thread.start() for thread in threads]; [thread.join() for thread in threads]
            self.assertEqual(sorted(results), ["allowed", "denied"])


class _Scanner(MalwareScannerAdapter):
    def __init__(self, verdict=SecurityVerdict.CLEAN, *, raises=False):
        self.verdict = verdict
        self.raises = raises

    @property
    def name(self):
        return "test-scanner"

    @property
    def version(self):
        return "4.2.0"

    @property
    def signature_metadata(self):
        return {"database": "test-definitions", "version": "2026.09.14"}

    async def scan(self, object_id, storage, detected_mime):
        if self.raises:
            raise RuntimeError("scanner unavailable")
        return MalwareScanResult(self.verdict, self.name, f"scanned:{detected_mime}")


class CoreSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = LocalFilesystemStorage(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def store(self, content):
        upload_id = self.storage.allocate_temporary_upload()
        self.storage.temporary_upload_reference(upload_id).write_bytes(content)
        return self.storage.finalize_temporary_upload(upload_id).object_id

    def inspect(self, pipeline, object_id, **kwargs):
        with mock.patch("nightwire.core.storage.anyio.open_file", new=_immediate_open_file):
            return asyncio.run(pipeline.inspect(object_id, **kwargs))

    def test_security_contracts_and_verdict_vocabulary(self):
        with self.assertRaises(TypeError):
            SecurityPipeline()
        with self.assertRaises(TypeError):
            MalwareScannerAdapter()
        self.assertEqual(
            {verdict.value for verdict in SecurityVerdict},
            {"clean", "suspicious", "malicious", "scan_failed", "unscanned"},
        )

    def test_signature_detection_is_independent_of_filename_and_declared_mime(self):
        detection = detect_mime_signature(b"\x89PNG\r\n\x1a\n" + b"payload")
        comparison = compare_mime_evidence("disguised.txt", "image/jpeg; charset=binary", detection.mime_type)

        self.assertEqual(detection.mime_type, "image/png")
        self.assertEqual(comparison.filename_extension_mime, "text/plain")
        self.assertEqual(comparison.declared_mime, "image/jpeg")
        self.assertEqual(comparison.mismatches, ("filename_extension", "declared_mime"))

    def test_safari_media_recorder_m4a_signature_is_detected_as_audio(self):
        detection = detect_mime_signature(
            b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A isom" + b"audio payload"
        )

        self.assertEqual(detection.mime_type, "audio/mp4")
        self.assertEqual(detection.basis, "iso-base-media-audio-signature")

    def test_pipeline_persists_unscanned_and_suspicious_object_result(self):
        object_id = self.store(b"%PDF-1.7\ncontent")

        result = self.inspect(
            CoreSecurityPipeline(self.storage),
            object_id,
            filename="image.png",
            declared_mime="image/png",
        )

        self.assertEqual(result.verdict, SecurityVerdict.SUSPICIOUS)
        persisted = self.storage.load_object_metadata(object_id)["security"]
        self.assertEqual(persisted["verdict"], "suspicious")
        self.assertEqual(persisted["detected_mime"], "application/pdf")

    def test_scanner_verdicts_are_normalized_without_pipeline_coupling(self):
        object_id = self.store(b"plain text")
        clean = self.inspect(
            CoreSecurityPipeline(self.storage, _Scanner()),
            object_id,
            filename="note.txt",
            declared_mime="text/plain",
        )
        failed = self.inspect(
            CoreSecurityPipeline(self.storage, _Scanner(raises=True)),
            object_id,
            filename="note.txt",
            declared_mime="text/plain",
        )

        self.assertEqual(clean.verdict, SecurityVerdict.CLEAN)
        self.assertEqual(failed.verdict, SecurityVerdict.SCAN_FAILED)
        persisted = self.storage.load_object_metadata(object_id)["security"]
        self.assertEqual(persisted["scanner"], "test-scanner")
        self.assertEqual(persisted["scanner_version"], "4.2.0")
        self.assertEqual(persisted["signature_metadata"]["version"], "2026.09.14")

    def test_pipeline_preserves_all_five_security_states(self):
        cases = (
            (None, SecurityVerdict.UNSCANNED),
            (_Scanner(SecurityVerdict.CLEAN), SecurityVerdict.CLEAN),
            (_Scanner(SecurityVerdict.SUSPICIOUS), SecurityVerdict.SUSPICIOUS),
            (_Scanner(SecurityVerdict.MALICIOUS), SecurityVerdict.MALICIOUS),
            (_Scanner(raises=True), SecurityVerdict.SCAN_FAILED),
        )
        for index, (scanner, expected) in enumerate(cases):
            with self.subTest(verdict=expected):
                object_id = self.store(f"plain text {index}".encode())
                result = self.inspect(
                    CoreSecurityPipeline(self.storage, scanner),
                    object_id,
                    filename="note.txt",
                    declared_mime="text/plain",
                )
                self.assertEqual(result.verdict, expected)
                self.assertEqual(
                    self.storage.load_object_metadata(object_id)["security"]["verdict"],
                    expected.value,
                )

    def test_central_policy_retains_malicious_bytes_but_gates_actions(self):
        policy = CoreSecurityPolicy()
        for verdict in SecurityVerdict:
            with self.subTest(verdict=verdict):
                self.assertTrue(policy.evaluate(verdict, SecurityAction.OPAQUE_STORAGE).allowed)
                download = policy.evaluate(verdict, SecurityAction.DOWNLOAD)
                processing = policy.evaluate(verdict, SecurityAction.RISKY_PROCESSING)
                self.assertEqual(download.allowed, verdict is not SecurityVerdict.MALICIOUS)
                self.assertEqual(processing.allowed, verdict is not SecurityVerdict.MALICIOUS)
        self.assertTrue(
            policy.evaluate(
                SecurityVerdict.MALICIOUS,
                SecurityAction.DOWNLOAD,
                confirmed=True,
            ).allowed
        )
        self.assertTrue(
            policy.evaluate(
                SecurityVerdict.MALICIOUS,
                SecurityAction.RISKY_PROCESSING,
                risky=False,
            ).allowed
        )


class _Processor(ContentProcessor):
    def __init__(self, name, mime="text/plain", *, version="1", raises=False, risky=True):
        self._name = name
        self._version = version
        self.mime = mime
        self.raises = raises
        self._risky = risky
        self.calls = 0

    @property
    def name(self):
        return self._name

    @property
    def version(self):
        return self._version

    @property
    def is_risky(self):
        return self._risky

    def supports(self, context):
        return context.detected_mime == self.mime

    async def process(self, context):
        self.calls += 1
        if self.raises:
            raise RuntimeError("processor failed")
        return ProcessorExecutionResult.success(
            self.identity,
            metadata={"object_id": str(context.object_id)},
        )


class ProcessorRegistryTests(unittest.TestCase):
    def test_processor_contract_registry_selection_and_failure_isolation(self):
        with self.assertRaises(TypeError):
            ContentProcessor()
        with tempfile.TemporaryDirectory() as temporary:
            storage = LocalFilesystemStorage(temporary)
            upload_id = storage.allocate_temporary_upload()
            storage.temporary_upload_reference(upload_id).write_bytes(b"text")
            stored = storage.finalize_temporary_upload(upload_id)
            context = ProcessorContext(stored.object_id, storage, "note.txt", "text/plain", stored.size)
            registry = ProcessorRegistry([_Processor("metadata"), _Processor("broken", raises=True)])

            results = asyncio.run(registry.process(context))

        self.assertEqual([result.processor for result in results], ["metadata", "broken"])
        self.assertEqual([result.processor_version for result in results], ["1", "1"])
        self.assertTrue(results[0].succeeded)
        self.assertFalse(results[1].succeeded)
        self.assertEqual(results[1].error, "RuntimeError")
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(_Processor("metadata"))

    def test_malicious_objects_never_enter_risky_processors(self):
        with tempfile.TemporaryDirectory() as temporary:
            storage = LocalFilesystemStorage(temporary)
            upload_id = storage.allocate_temporary_upload()
            storage.temporary_upload_reference(upload_id).write_bytes(b"malicious")
            stored = storage.finalize_temporary_upload(upload_id)
            context = ProcessorContext(
                stored.object_id,
                storage,
                "payload.txt",
                "text/plain",
                stored.size,
                security_verdict=SecurityVerdict.MALICIOUS,
            )
            risky = _Processor("extract")
            safe = _Processor("opaque-index", risky=False)
            results = asyncio.run(ProcessorRegistry([risky, safe]).process(context))

        self.assertEqual(risky.calls, 0)
        self.assertEqual(safe.calls, 1)
        self.assertEqual(results[0].status.value, "skipped")
        self.assertIn("blocked", results[0].error.lower())
        self.assertTrue(results[1].succeeded)


if __name__ == "__main__":
    unittest.main()
