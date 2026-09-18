import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
from nightwire.core.config import (
    DeploymentProfile,
    InstalledModules,
    RegistrationPolicy,
    load_application_config,
    load_port,
)


class ApplicationConfigTests(unittest.TestCase):
    def test_default_paths_version_limits_modules_and_profile_match_existing_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            base_dir = Path(temporary)
            (base_dir / "VERSION").write_text("1.0.2\n", encoding="utf-8")

            settings = load_application_config({}, base_dir=base_dir)

            self.assertEqual(settings.base_dir, base_dir.resolve())
            self.assertEqual(settings.files_dir, (base_dir / "files").resolve())
            self.assertTrue(settings.files_dir.is_dir())
            self.assertEqual(settings.static_dir, base_dir / "static")
            self.assertEqual(settings.version_file, base_dir / "VERSION")
            self.assertEqual(settings.version, "1.0.2")
            self.assertEqual(settings.installed_modules, InstalledModules(drop=True, library=True))
            self.assertEqual(settings.deployment_profile, DeploymentProfile.TRUSTED_PRIVATE)
            self.assertEqual(settings.database_url, f"sqlite:///{base_dir.resolve()}/data/nightwire-library.db")
            self.assertEqual(settings.library_registration_policy, RegistrationPolicy.OPEN)
            self.assertEqual(settings.chunk_hint, 1024 * 1024)
            self.assertEqual(settings.clipboard_default_expiry_seconds, 600)
            self.assertEqual(settings.file_default_expiry_seconds, 3600)
            self.assertEqual(settings.anonymous_internet_drop_max_expiry_seconds, 86400)
            self.assertFalse(settings.trusted_network_relaxed_access)
            self.assertTrue(settings.trusted_network_active_drop_browsing)
            self.assertEqual(settings.installation_max_bytes, 0)
            self.assertEqual(settings.maximum_object_bytes, 0)

    def test_storage_limits_are_independently_configurable(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = load_application_config({
                "NIGHTWIRE_INSTALLATION_MAX_BYTES": "100",
                "NIGHTWIRE_PERSONAL_LIBRARY_QUOTA_BYTES": "101",
                "NIGHTWIRE_WORKSPACE_QUOTA_BYTES": "102",
                "NIGHTWIRE_DROP_QUOTA_BYTES": "103",
                "NIGHTWIRE_MAXIMUM_OBJECT_BYTES": "104",
                "NIGHTWIRE_MINIMUM_HOST_FREE_BYTES": "105",
            }, base_dir=temporary, create_files_directory=False)
        self.assertEqual((settings.installation_max_bytes, settings.personal_library_quota_bytes,
                          settings.workspace_quota_bytes, settings.drop_quota_bytes,
                          settings.maximum_object_bytes, settings.minimum_host_free_bytes),
                         (100, 101, 102, 103, 104, 105))

    def test_missing_version_keeps_development_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = load_application_config(
                {}, base_dir=temporary, create_files_directory=False
            )

        self.assertEqual(settings.version, "development")

    def test_files_directory_override_is_expanded_resolved_and_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            base_dir = Path(temporary) / "application"
            files_dir = Path(temporary) / "external" / "shared"

            settings = load_application_config(
                {"NIGHTWIRE_FILES_DIR": str(files_dir)}, base_dir=base_dir
            )

            self.assertEqual(settings.files_dir, files_dir.resolve())
            self.assertTrue(files_dir.is_dir())

    def test_drop_and_library_can_be_disabled_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            drop_disabled = load_application_config(
                {"NIGHTWIRE_DROP_ENABLED": "off", "NIGHTWIRE_LIBRARY_ENABLED": "yes"},
                base_dir=temporary,
                create_files_directory=False,
            )
            library_disabled = load_application_config(
                {"NIGHTWIRE_DROP_ENABLED": "enabled", "NIGHTWIRE_LIBRARY_ENABLED": "0"},
                base_dir=temporary,
                create_files_directory=False,
            )

        self.assertEqual(drop_disabled.installed_modules.as_dict(), {"drop": False, "library": True})
        self.assertEqual(library_disabled.installed_modules.as_dict(), {"drop": True, "library": False})

    def test_invalid_module_toggle_fails_during_configuration_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "NIGHTWIRE_DROP_ENABLED"):
                load_application_config(
                    {"NIGHTWIRE_DROP_ENABLED": "sometimes"},
                    base_dir=temporary,
                    create_files_directory=False,
                )

    def test_trusted_network_policy_switches_are_independently_configurable(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = load_application_config(
                {
                    "NIGHTWIRE_TRUSTED_RELAX_ACCESS_KEYS": "yes",
                    "NIGHTWIRE_TRUSTED_ACTIVE_DROP_BROWSING": "off",
                },
                base_dir=temporary,
                create_files_directory=False,
            )

        self.assertTrue(settings.trusted_network_relaxed_access)
        self.assertFalse(settings.trusted_network_active_drop_browsing)

    def test_invalid_trusted_network_policy_switch_fails_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "NIGHTWIRE_TRUSTED_RELAX_ACCESS_KEYS"):
                load_application_config(
                    {"NIGHTWIRE_TRUSTED_RELAX_ACCESS_KEYS": "maybe"},
                    base_dir=temporary,
                    create_files_directory=False,
                )

    def test_deployment_profile_distinguishes_private_and_internet_facing(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = load_application_config(
                {"NIGHTWIRE_DEPLOYMENT_PROFILE": "private"},
                base_dir=temporary,
                create_files_directory=False,
            )
            internet = load_application_config(
                {"NIGHTWIRE_DEPLOYMENT_PROFILE": "internet-facing"},
                base_dir=temporary,
                create_files_directory=False,
            )

        self.assertEqual(trusted.deployment_profile, DeploymentProfile.TRUSTED_PRIVATE)
        self.assertEqual(internet.deployment_profile, DeploymentProfile.INTERNET_FACING)

    def test_invalid_deployment_profile_fails_during_configuration_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "NIGHTWIRE_DEPLOYMENT_PROFILE"):
                load_application_config(
                    {"NIGHTWIRE_DEPLOYMENT_PROFILE": "public-ish"},
                    base_dir=temporary,
                    create_files_directory=False,
                )

    def test_internet_profile_defaults_to_approval_and_policy_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as temporary:
            restrictive = load_application_config(
                {"NIGHTWIRE_DEPLOYMENT_PROFILE": "internet-facing"},
                base_dir=temporary,
                create_files_directory=False,
            )
            invitation = load_application_config(
                {
                    "NIGHTWIRE_DEPLOYMENT_PROFILE": "internet-facing",
                    "NIGHTWIRE_LIBRARY_REGISTRATION_POLICY": "invitation_only",
                    "NIGHTWIRE_DATABASE_URL": "sqlite:///:memory:",
                },
                base_dir=temporary,
                create_files_directory=False,
            )

        self.assertEqual(
            restrictive.library_registration_policy,
            RegistrationPolicy.ADMINISTRATOR_APPROVED,
        )
        self.assertEqual(invitation.library_registration_policy, RegistrationPolicy.INVITATION_ONLY)
        self.assertEqual(invitation.database_url, "sqlite:///:memory:")

    def test_port_loading_preserves_integer_conversion_and_call_time_default(self):
        self.assertEqual(load_port({}, default=9000), 9000)
        self.assertEqual(load_port({"PORT": "8123"}), 8123)
        with self.assertRaises(ValueError):
            load_port({"PORT": "not-a-port"})

    def test_legacy_app_constants_are_sourced_from_central_settings(self):
        self.assertEqual(app.BASE_DIR, app.SETTINGS.base_dir)
        self.assertEqual(app.FILES_DIR, app.SETTINGS.files_dir)
        self.assertEqual(app.STATIC_DIR, app.SETTINGS.static_dir)
        self.assertEqual(app.APP_VERSION, app.SETTINGS.version)
        self.assertEqual(app.CLIPBOARD_HISTORY_LIMIT, app.SETTINGS.clipboard_history_limit)
        self.assertEqual(app.FILE_METADATA_FILENAME, app.SETTINGS.file_metadata_filename)


class ConfigurationInfoResponseTests(unittest.TestCase):
    def test_info_response_exposes_installed_modules_and_deployment_profile(self):
        scope = {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/api/info",
            "raw_path": b"/api/info",
            "query_string": b"",
            "headers": [(b"host", b"testserver:8080")],
            "client": ("127.0.0.1", 43000),
            "server": ("testserver", 8080),
        }
        request = app.Request(scope)

        with mock.patch.object(app, "local_addresses", return_value=[]):
            response = asyncio.run(app.server_info(request))
        payload = json.loads(response.body)

        self.assertEqual(payload["installed_modules"], {"drop": True, "library": True})
        self.assertEqual(payload["deployment_profile"], "trusted-private")
        self.assertEqual(payload["file_default_expiry_seconds"], 3600)
        self.assertEqual(payload["drop_max_expiry_seconds"], 31_536_000)
        self.assertTrue(payload["drop_access_key_required"])
        self.assertFalse(payload["active_drop_browsing"])


if __name__ == "__main__":
    unittest.main()
