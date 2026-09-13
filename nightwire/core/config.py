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
    chunk_hint: int = 1024 * 1024
    client_ttl_seconds: int = 18
    clipboard_max_text_length: int = 32_768
    clipboard_history_limit: int = 40
    clipboard_payload_limit: int = 160_000
    clipboard_default_expiry_seconds: int = 10 * 60
    file_default_expiry_seconds: int = 0
    item_min_expiry_seconds: int = 60
    item_max_expiry_seconds: int = 365 * 24 * 60 * 60
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
        deployment_profile=_parse_deployment_profile(source),
    )


SETTINGS = load_application_config()


__all__ = [
    "ApplicationConfig",
    "DEFAULT_BASE_DIR",
    "DEFAULT_PORT",
    "DeploymentProfile",
    "InstalledModules",
    "SETTINGS",
    "load_application_config",
    "load_port",
]
