# Configuration Reference

NightWire is configured primarily through environment variables and launcher arguments. There is no required configuration file.

## Runtime variables

| Variable | Default | Used by | Description |
| --- | --- | --- | --- |
| `PORT` | `8080` | `app.py`, launchers | TCP port used by Uvicorn. |
| `NIGHTWIRE_PORT` | unset | `run.sh`, `run.bat`, installed launcher | Preferred launcher-level port override. It is copied into `PORT`. |
| `NIGHTWIRE_FILES_DIR` | `<project>/files` | `app.py` | Shared file directory and location of `.nightwire-metadata.json`. |

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

## Installed launcher

The Linux installer creates a `nightwire` command with these options:

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
| `NIGHTWIRE_INSTALL_DIR` | `/srv/nightwire` | Installed application directory. |
| `NIGHTWIRE_BIN_DIR` | `/usr/local/bin` | Directory receiving the `nightwire` launcher. |
| `NIGHTWIRE_PYTHON` | `python3` | Python executable requested when `uv` creates or syncs the environment. |

Example user-local installation:

```bash
NIGHTWIRE_INSTALL_DIR="$HOME/.local/share/nightwire" \
NIGHTWIRE_BIN_DIR="$HOME/.local/bin" \
NIGHTWIRE_PYTHON=python3.12 \
./install.sh
```

Ensure `$HOME/.local/bin` is in `PATH` when using a user-local binary directory.

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

Because file metadata lives inside `files/.nightwire-metadata.json`, lifecycle and password records survive normal upgrades.

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

- Uploads require enough free space for the temporary file and final file, although the atomic rename normally keeps them on the same filesystem.
- File metadata is small and stored in the same directory.
- Clipboard data consumes process memory only and is bounded to 40 entries of at most 32,768 characters each.

## Fixed application limits

These limits are constants in `app.py` and are not environment-configurable in version `1.0.2`:

| Setting | Value |
| --- | ---: |
| Clipboard text length | 32,768 characters |
| Clipboard history | 40 entries |
| Password length | 256 characters |
| Minimum timed retention | 60 seconds |
| Maximum timed retention | 365 days |
| Client inactivity timeout | 18 seconds |
| Cleanup interval | approximately 1 second |
