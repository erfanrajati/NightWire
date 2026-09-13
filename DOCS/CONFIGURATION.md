# Configuration Reference

NightWire is configured primarily through environment variables and launcher arguments. There is no required configuration file.

## Runtime variables

| Variable | Default | Used by | Description |
| --- | --- | --- | --- |
| `PORT` | `8080` | `nightwire.core.config`, launchers | TCP port used by Uvicorn. |
| `NIGHTWIRE_PORT` | unset | `run.sh`, `run.bat`, installed launcher | Preferred launcher-level port override. It is copied into `PORT`. |
| `NIGHTWIRE_FILES_DIR` | `<project>/files` | `nightwire.core.config` | Core storage root containing metadata, objects, temporary uploads, and compatible legacy files. |
| `NIGHTWIRE_DROP_ENABLED` | `true` | `nightwire.core.config` | Declares whether the Drop module is installed/enabled. |
| `NIGHTWIRE_LIBRARY_ENABLED` | `true` | `nightwire.core.config` | Declares whether the Library module is installed/enabled. |
| `NIGHTWIRE_DEPLOYMENT_PROFILE` | `trusted-private` | `nightwire.core.config` | Declares the installation trust boundary. |

Examples:

```bash
PORT=9000 uv run --locked python app.py
```

```bash
NIGHTWIRE_PORT=9000 ./run.sh
```

```bash
NIGHTWIRE_FILES_DIR=/mnt/shared/nightwire-files ./run.sh
```

The files directory is resolved to an absolute path and created automatically when possible. The account running NightWire must have read, write, rename, and delete permission there.

## Installed modules

Drop and Library are independently configurable. Accepted enabled values are `1`, `true`, `yes`, `on`, and `enabled`; accepted disabled values are `0`, `false`, `no`, `off`, and `disabled` (case-insensitive).

```bash
NIGHTWIRE_DROP_ENABLED=false NIGHTWIRE_LIBRARY_ENABLED=true ./run.sh
```

Both modules default to enabled, preserving v1.0.2 behavior. At bootstrap, only enabled modules receive the opportunity to register routes and lifecycle hooks. Drop currently owns the complete legacy route surface, static mount, and cleanup hooks, so disabling Drop leaves the Starlette application with no registered routes. Library participates independently in registration but does not contribute functionality yet.

## Deployment profiles

`NIGHTWIRE_DEPLOYMENT_PROFILE` accepts these canonical values:

| Value | Meaning |
| --- | --- |
| `trusted-private` | A trusted home, studio, lab, or office network. This is the default. |
| `internet-facing` | An installation intended to sit behind internet-facing security controls. |

`trusted`, `private`, and `trusted/private` are accepted aliases for `trusted-private`; `internet` is an alias for `internet-facing`. The profile is currently descriptive and is returned by `/api/info`. Selecting `internet-facing` does not itself add TLS, authentication, proxy configuration, or firewall rules.

## Installed launcher

The Linux, macOS, and Windows installers create a `nightwire` command with these options:

```text
Usage: nightwire [--port PORT]

Options:
  -p, --port PORT   Listen on this port (default: 8080)
  -h, --help        Show help
```

Examples:

```bash
nightwire
nightwire --port 9000
NIGHTWIRE_PORT=9000 nightwire
```

The command-line `--port` value takes precedence over environment defaults.

## Installer variables

| Variable | Default | Description |
| --- | --- | --- |
| `NIGHTWIRE_INSTALL_DIR` | Linux: `/srv/nightwire`; macOS: `/usr/local/share/nightwire`; Windows: `%LOCALAPPDATA%\NightWire` | Installed application directory. |
| `NIGHTWIRE_BIN_DIR` | Unix: `/usr/local/bin`; Windows: `%LOCALAPPDATA%\Programs\NightWire` | Directory receiving the `nightwire` launcher. |
| `NIGHTWIRE_PYTHON` | `3.11` | Python version or executable requested when `uv` creates or syncs the environment. |

Example user-local installation:

```bash
NIGHTWIRE_INSTALL_DIR="$HOME/.local/share/nightwire" \
NIGHTWIRE_BIN_DIR="$HOME/.local/bin" \
NIGHTWIRE_PYTHON=3.12 \
./install.sh
```

Ensure `$HOME/.local/bin` is in `PATH` when using a user-local binary directory.

The same variables can be set in PowerShell before running `install.ps1`:

```powershell
$env:NIGHTWIRE_INSTALL_DIR = "$HOME\Apps\NightWire"
$env:NIGHTWIRE_PYTHON = "3.12"
.\install.ps1
```

## Updater variable

| Variable | Default | Description |
| --- | --- | --- |
| `NIGHTWIRE_EXISTING_DIR` | `/srv/nightwire` | Target tree used by `update-existing.sh` when no positional path is supplied. |

Examples:

```bash
./update-existing.sh /home/user/Projects/NightWire
```

```bash
NIGHTWIRE_EXISTING_DIR=/opt/nightwire ./update-existing.sh --install
```

## Preserved paths during update

The installer preserves these top-level paths in the installed application:

```text
files/
.venv/
.env
.env.*
```

The recursive updater also preserves `.git/`.

Because metadata and Core object storage live under `files/`, lifecycle records, checksums, password records, and uploaded content survive normal upgrades.

Drop metadata is accessed through `LocalDropRepository`. It intentionally retains the existing `.nightwire-metadata.json` representation, so the service migration requires no migration command and does not change the preserved storage location.

The local backend creates these internal paths under the configured root:

```text
files/
├── .nightwire-metadata.json
├── .nightwire-object-metadata/ # Per-object security and future Core metadata
├── .nightwire-objects/       # Permanent content named by opaque object ID
└── .nightwire-uploads/       # Isolated in-progress uploads (*.part)
```

Existing deployments may also contain legacy files directly under `files/`; NightWire continues to list, download, update, expire, and replace them.

## Network behavior

NightWire binds Uvicorn to `0.0.0.0`, making it reachable through suitable IPv4 interfaces on the host. It prints detected LAN addresses at startup.

A client must be able to reach:

```text
http://HOST_IP:PORT/
```

When clients cannot connect, check:

- host firewall rules for the selected TCP port;
- router client/AP isolation;
- guest-network restrictions;
- VPN routing;
- whether the printed IP belongs to the network used by the client;
- whether another process is already using the port.

## Reverse proxy and HTTPS

NightWire does not configure TLS. A trusted reverse proxy may terminate HTTPS and forward traffic to NightWire when clipboard permissions or local policy require a secure context.

When adding a proxy, preserve request bodies for streamed uploads and set appropriate upload/time limits. Do not expose the proxy publicly without adding a separate authentication and authorization layer.

## Storage planning

NightWire has no configured file quota. Monitor the filesystem containing `NIGHTWIRE_FILES_DIR`.

- Uploads require enough free space for the temporary object. Finalization is an atomic rename within the same storage root and normally does not duplicate content bytes.
- File metadata is small and stored in the same directory.
- Inactive temporary uploads older than 24 hours are treated as orphans and removed by the lifecycle worker; active transfer IDs are excluded.
- Core capacity/quota interfaces exist, but the current compatibility policy does not enforce Drop or Library quotas.
- Clipboard data consumes process memory only and is bounded to 40 entries of at most 32,768 characters each.

## Fixed application limits

These limits are centralized in `nightwire/core/config.py` and are not environment-configurable in version `1.0.2`:

| Setting | Value |
| --- | ---: |
| Clipboard text length | 32,768 characters |
| Clipboard history | 40 entries |
| Password length | 256 characters |
| Minimum timed retention | 60 seconds |
| Maximum timed retention | 365 days |
| Client inactivity timeout | 18 seconds |
| Cleanup interval | approximately 1 second |
