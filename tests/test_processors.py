import asyncio
import tempfile
import unittest

from nightwire.core.storage import LocalFilesystemStorage, ObjectId
from nightwire.processors import (
    DenySandboxExecutor,
    DerivedObject,
    ProcessorExecutionResult,
    ProcessorExecutionStatus,
    ProcessorIdentity,
    SandboxExecutionRequest,
    SandboxExecutionStatus,
    SandboxExecutor,
    SandboxInput,
    SandboxLimits,
)


class ProcessorExecutionResultTests(unittest.TestCase):
    def test_versioned_success_can_describe_derived_objects(self):
        identity = ProcessorIdentity("thumbnail", "2.1.0")
        derived = DerivedObject(
            object_id=ObjectId("a" * 32),
            relationship="thumbnail",
            filename="preview.webp",
            mime_type="image/webp",
            size=512,
            metadata={"width": 320},
        )

        result = ProcessorExecutionResult.success(
            identity,
            metadata={"source_pages": 3},
            derived_objects=[derived],
            started_at=100.0,
            duration_seconds=0.25,
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(result.processor, "thumbnail")
        self.assertEqual(result.processor_version, "2.1.0")
        self.assertEqual(result.derived_objects, (derived,))
        self.assertEqual(result.to_dict()["derived_objects"][0]["object_id"], "a" * 32)

    def test_failure_and_skip_are_distinct_terminal_results(self):
        identity = ProcessorIdentity("extract", "2026.09")

        failed = ProcessorExecutionResult.failure(identity, "SandboxTimedOut")
        skipped = ProcessorExecutionResult.skipped(identity, "unsupported MIME")

        self.assertEqual(failed.status, ProcessorExecutionStatus.FAILED)
        self.assertEqual(skipped.status, ProcessorExecutionStatus.SKIPPED)
        self.assertFalse(failed.succeeded)
        self.assertFalse(skipped.succeeded)

    def test_result_types_validate_identity_derived_size_and_success_error(self):
        with self.assertRaises(ValueError):
            ProcessorIdentity(" processor", "1")
        with self.assertRaises(ValueError):
            DerivedObject(ObjectId("b" * 32), "preview", size=-1)
        with self.assertRaises(ValueError):
            ProcessorExecutionResult(
                ProcessorIdentity("processor", "1"),
                ProcessorExecutionStatus.SUCCEEDED,
                error="impossible",
            )


class SandboxExecutionContractTests(unittest.TestCase):
    def test_sandbox_executor_is_abstract_and_default_executor_denies(self):
        with self.assertRaises(TypeError):
            SandboxExecutor()
        request = SandboxExecutionRequest(
            processor=ProcessorIdentity("archive-inspector", "1.0"),
            executable="inspect-archive",
            arguments=("--json",),
            inputs=(SandboxInput(ObjectId("c" * 32), "payload.zip"),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            storage = LocalFilesystemStorage(temporary)
            result = asyncio.run(DenySandboxExecutor().execute(request, storage))

        self.assertEqual(result.status, SandboxExecutionStatus.DENIED)
        self.assertFalse(result.succeeded)
        self.assertIn("No sandbox", result.reason)

    def test_sandbox_inputs_and_limits_reject_paths_or_unbounded_values(self):
        with self.assertRaises(ValueError):
            SandboxInput(ObjectId("d" * 32), "../payload")
        with self.assertRaises(ValueError):
            SandboxLimits(wall_time_seconds=0)
        with self.assertRaises(ValueError):
            SandboxExecutionRequest(
                processor=ProcessorIdentity("processor", "1"),
                executable="/usr/bin/unsafe-host-path",
            )


if __name__ == "__main__":
    unittest.main()
