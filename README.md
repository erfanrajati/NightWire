# NightWire

NightWire is a lightweight local-network sharing server for moving files, synchronizing clipboard text, and viewing connected devices from a browser. It is designed for trusted home, studio, lab, and office LANs where fast transfer and minimal setup matter more than account management or cloud storage.

**Documented release:** `1.0.2`

## Highlights

- Direct browser-to-server file uploads and downloads over the local network.
- Shared clipboard history across connected NightWire browsers.
- Optional, creation-time password protection for files and clipboard entries.
- Per-item auto-delete countdowns, enforced by the server even when no browser is open.
- A client page with active-device visibility, LAN addresses, and a connection QR code.
- Responsive, dependency-light frontend with dedicated Files, Clipboard, and Clients routes.
- Persistent file lifecycle metadata and memory-only clipboard storage.

## Requirements

- Python `3.11` or newer.
- [`uv`](https://docs.astral.sh/uv/) available in `PATH`.
- A modern browser on the NightWire host or another device on the same network.
- For the Linux system installer: `bash`, `tar`, `cmp`, and either root access or `sudo`.

NightWire listens on all network interfaces and uses port `8080` by default.

## Installation

### Run from the source tree

Clone or extract NightWire, then run:

```bash
cd NightWire
chmod +x run.sh
./run.sh
```

NightWire prints the local and LAN addresses it detected. Open the `/files` address in a browser, for example:

```text
http://192.168.1.29:8080/files
```

To use another port:

```bash
PORT=9000 ./run.sh
```

`NIGHTWIRE_PORT` may also be used by the supplied launch scripts:

```bash
NIGHTWIRE_PORT=9000 ./run.sh
```

### Install system-wide on Linux

The installer stages and verifies the release before replacing the installed application. By default it installs the application under `/srv/nightwire` and creates `/usr/local/bin/nightwire`.

```bash
cd NightWire
chmod +x install.sh update-existing.sh run.sh
./install.sh
```

Start the installed server:

```bash
nightwire
```

Choose another port when launching:

```bash
nightwire --port 9000
```

The installer preserves the installed `files/` directory, `.venv/`, `.env`, and `.env.*` files during upgrades.

Custom installation locations are supported. The current installer still performs privileged staging and launcher installation, so run it as root or with `sudo` available even when the target paths are user-owned:

```bash
NIGHTWIRE_INSTALL_DIR="$HOME/.local/share/nightwire" \
NIGHTWIRE_BIN_DIR="$HOME/.local/bin" \
./install.sh
```

### Run on Windows

Install Python 3.11 or newer and `uv`, extract NightWire, then run:

```bat
run.bat
```

The Windows launcher uses port `8080` unless `PORT` or `NIGHTWIRE_PORT` is already set.

## Connect another device

1. Start NightWire on the host computer.
2. Keep both devices on the same Wi-Fi, Ethernet network, or hotspot.
3. Open the **Clients** page.
4. Scan the QR code or enter the displayed LAN address on the second device.

Some routers enable client or access-point isolation, which prevents devices on the same Wi-Fi from reaching one another. Disable that feature or use a different trusted network when necessary.

## Updating

From an extracted release, replace an existing tree and optionally update the system installation:

```bash
./update-existing.sh --install /path/to/existing/NightWire
```

The updater preserves:

```text
files/
.venv/
.git/
.env
.env.*
```

## Documentation

- [Documentation index](DOCS/README.md)
- [Using NightWire](DOCS/USAGE.md)
- [Project architecture and internals](DOCS/PROJECT.md)
- [Configuration reference](DOCS/CONFIGURATION.md)
- [Security model](DOCS/SECURITY.md)
- [HTTP API reference](DOCS/API.md)
- [Troubleshooting](DOCS/TROUBLESHOOTING.md)
- [Contributing](DOCS/CONTRIBUTING.md)

## Security summary

NightWire is intended for a **trusted local network**. It has no user-account system and should not be exposed directly to the public internet.

Passwords are optional, immutable after creation, and stored as salted `scrypt` hashes. They protect access through NightWire but do not encrypt files on disk. Any connected client may change an item's auto-delete countdown, including for protected items. See [the security documentation](DOCS/SECURITY.md) before deploying NightWire on a shared or sensitive network.

## Development quick start

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python app.py
```

See [CONTRIBUTING.md](DOCS/CONTRIBUTING.md) for coding standards, validation commands, and pull-request guidance.

## License

This project currently does not include a license file. Add an explicit license before public redistribution or accepting external contributions under defined terms.
