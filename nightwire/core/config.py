"""Central application configuration for NightWire.

The legacy ``app.py`` entry point imports this module while behavior is gradually
moved into the package. Environment parsing belongs here so future modules share
one configuration contract.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


DEFAULT_PORT = 8080
DEFAULT_BASE_DIR = Path(__file__).resolve().parents[2]


class DeploymentProfile(str, Enum):
    """Declared trust boundary for an installation.

    Profiles are descriptive in the current release foundation. Enforcement is
    added by the modules that consume them.
    """

    TRUSTED_PRIVATE = "trusted-private"
    INTERNET_FACING = "internet-facing"


class RegistrationPolicy(str, Enum):
    """Who may create a Community Library account."""

    OPEN = "open"
    INVITATION_ONLY = "invitation-only"
    ADMINISTRATOR_APPROVED = "administrator-approved"


@dataclass(frozen=True, slots=True)
class InstalledModules:
    """Feature modules installed for this application instance."""

    drop: bool = True
    library: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {"drop": self.drop, "library": self.library}


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Resolved paths, limits, installed modules, and deployment profile."""

    base_dir: Path
    files_dir: Path
    static_dir: Path
    version_file: Path
    version: str
    installed_modules: InstalledModules
    deployment_profile: DeploymentProfile
    database_url: str
    library_registration_policy: RegistrationPolicy
    library_session_ttl_seconds: int = 30 * 24 * 60 * 60
    library_password_min_characters: int = 12
    library_trash_retention_seconds: int = 30 * 24 * 60 * 60
    library_version_retention: int = 100
    installation_max_bytes: int = 0
    personal_library_quota_bytes: int = 0
    workspace_quota_bytes: int = 0
    drop_quota_bytes: int = 0
    maximum_object_bytes: int = 0
    minimum_host_free_bytes: int = 0
    chunk_hint: int = 1024 * 1024
    client_ttl_seconds: int = 18
    clipboard_max_text_length: int = 32_768
    clipboard_history_limit: int = 40
    clipboard_payload_limit: int = 160_000
    clipboard_default_expiry_seconds: int = 10 * 60
    file_default_expiry_seconds: int = 60 * 60
    item_min_expiry_seconds: int = 60
    item_max_expiry_seconds: int = 365 * 24 * 60 * 60
    anonymous_internet_drop_max_expiry_seconds: int = 24 * 60 * 60
    trusted_network_relaxed_access: bool = False
    trusted_network_active_drop_browsing: bool = True
    password_max_characters: int = 256
    file_metadata_filename: str = ".nightwire-metadata.json"


def _parse_enabled(environment: Mapping[str, str], name: str, default: bool = True) -> bool:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disabled"}:
        return False
    raise ValueError(f"{name} must be an enabled/disabled boolean value.")


def _parse_deployment_profile(environment: Mapping[str, str]) -> DeploymentProfile:
    raw_value = environment.get("NIGHTWIRE_DEPLOYMENT_PROFILE", DeploymentProfile.TRUSTED_PRIVATE.value)
    value = raw_value.strip().lower().replace("_", "-")
    aliases = {
        "trusted": DeploymentProfile.TRUSTED_PRIVATE,
        "private": DeploymentProfile.TRUSTED_PRIVATE,
        "trusted/private": DeploymentProfile.TRUSTED_PRIVATE,
        DeploymentProfile.TRUSTED_PRIVATE.value: DeploymentProfile.TRUSTED_PRIVATE,
        "internet": DeploymentProfile.INTERNET_FACING,
        DeploymentProfile.INTERNET_FACING.value: DeploymentProfile.INTERNET_FACING,
    }
    try:
        return aliases[value]
    except KeyError as exc:
        allowed = ", ".join(profile.value for profile in DeploymentProfile)
        raise ValueError(f"NIGHTWIRE_DEPLOYMENT_PROFILE must be one of: {allowed}.") from exc


def _parse_registration_policy(
    environment: Mapping[str, str], deployment_profile: DeploymentProfile
) -> RegistrationPolicy:
    default = (
        RegistrationPolicy.ADMINISTRATOR_APPROVED
        if deployment_profile is DeploymentProfile.INTERNET_FACING
        else RegistrationPolicy.OPEN
    )
    raw_value = environment.get("NIGHTWIRE_LIBRARY_REGISTRATION_POLICY", default.value)
    value = raw_value.strip().lower().replace("_", "-")
    try:
        return RegistrationPolicy(value)
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in RegistrationPolicy)
        raise ValueError(
            f"NIGHTWIRE_LIBRARY_REGISTRATION_POLICY must be one of: {allowed}."
        ) from exc


def _parse_positive_integer(
    environment: Mapping[str, str], name: str, default: int
) -> int:
    try:
        value = int(environment.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _parse_byte_limit(environment: Mapping[str, str], name: str) -> int:
    try:
        value = int(environment.get(name, "0"))
    except ValueError as exc:
        raise ValueError(f"{name} must be zero or a positive integer.") from exc
    if value < 0:
        raise ValueError(f"{name} must be zero or a positive integer.")
    return value


def load_port(environment: Mapping[str, str] | None = None, *, default: int = DEFAULT_PORT) -> int:
    """Read ``PORT`` with the same integer conversion semantics as v1.0.2."""

    source = os.environ if environment is None else environment
    return int(source.get("PORT", str(default)))


def load_application_config(
    environment: Mapping[str, str] | None = None,
    *,
    base_dir: Path | str | None = None,
    create_files_directory: bool = True,
) -> ApplicationConfig:
    """Resolve application configuration from an environment mapping."""

    source = os.environ if environment is None else environment
    resolved_base = Path(base_dir if base_dir is not None else DEFAULT_BASE_DIR).resolve()
    files_dir = Path(source.get("NIGHTWIRE_FILES_DIR", str(resolved_base / "files"))).expanduser().resolve()
    static_dir = resolved_base / "static"
    version_file = resolved_base / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "development"
    deployment_profile = _parse_deployment_profile(source)
    default_database_path = resolved_base / "data" / "nightwire-library.db"
    database_url = source.get(
        "NIGHTWIRE_DATABASE_URL", f"sqlite:///{default_database_path}"
    ).strip()
    if not database_url:
        raise ValueError("NIGHTWIRE_DATABASE_URL cannot be empty.")

    if create_files_directory:
        files_dir.mkdir(parents=True, exist_ok=True)

    return ApplicationConfig(
        base_dir=resolved_base,
        files_dir=files_dir,
        static_dir=static_dir,
        version_file=version_file,
        version=version,
        installed_modules=InstalledModules(
            drop=_parse_enabled(source, "NIGHTWIRE_DROP_ENABLED"),
            library=_parse_enabled(source, "NIGHTWIRE_LIBRARY_ENABLED"),
        ),
        deployment_profile=deployment_profile,
        database_url=database_url,
        library_registration_policy=_parse_registration_policy(source, deployment_profile),
        library_session_ttl_seconds=_parse_positive_integer(
            source, "NIGHTWIRE_LIBRARY_SESSION_TTL_SECONDS", 30 * 24 * 60 * 60
        ),
        library_password_min_characters=_parse_positive_integer(
            source, "NIGHTWIRE_LIBRARY_PASSWORD_MIN_CHARACTERS", 12
        ),
        library_trash_retention_seconds=_parse_positive_integer(
            source, "NIGHTWIRE_LIBRARY_TRASH_RETENTION_SECONDS", 30 * 24 * 60 * 60
        ),
        library_version_retention=_parse_positive_integer(
            source, "NIGHTWIRE_LIBRARY_VERSION_RETENTION", 100
        ),
        installation_max_bytes=_parse_byte_limit(source, "NIGHTWIRE_INSTALLATION_MAX_BYTES"),
        personal_library_quota_bytes=_parse_byte_limit(source, "NIGHTWIRE_PERSONAL_LIBRARY_QUOTA_BYTES"),
        workspace_quota_bytes=_parse_byte_limit(source, "NIGHTWIRE_WORKSPACE_QUOTA_BYTES"),
        drop_quota_bytes=_parse_byte_limit(source, "NIGHTWIRE_DROP_QUOTA_BYTES"),
        maximum_object_bytes=_parse_byte_limit(source, "NIGHTWIRE_MAXIMUM_OBJECT_BYTES"),
        minimum_host_free_bytes=_parse_byte_limit(source, "NIGHTWIRE_MINIMUM_HOST_FREE_BYTES"),
        trusted_network_relaxed_access=_parse_enabled(
            source, "NIGHTWIRE_TRUSTED_RELAX_ACCESS_KEYS", default=False
        ),
        trusted_network_active_drop_browsing=_parse_enabled(
            source, "NIGHTWIRE_TRUSTED_ACTIVE_DROP_BROWSING", default=True
        ),
    )


SETTINGS = load_application_config()


__all__ = [
    "ApplicationConfig",
    "DEFAULT_BASE_DIR",
    "DEFAULT_PORT",
    "DeploymentProfile",
    "InstalledModules",
    "RegistrationPolicy",
    "SETTINGS",
    "load_application_config",
    "load_port",
]
