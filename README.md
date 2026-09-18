<p align="center">
  <img src="./static/assets/logo.svg" width="560" alt="NightWire — local sharing node">
</p>

<p align="center">
  <strong>Fast file transfer, shared clipboard, and client visibility across your local network.</strong>
</p>

<p align="center">
  <img alt="Release 1.0.2" src="https://img.shields.io/badge/release-1.0.2-9B7BFF?style=for-the-badge">
  <img alt="Python 3.11 or newer" src="https://img.shields.io/badge/python-3.11%2B-65B5FF?style=for-the-badge&logo=python&logoColor=07111F">
  <img alt="Starlette" src="https://img.shields.io/badge/Starlette-0.48%2B-5FFBF1?style=for-the-badge">
  <img alt="Linux, macOS, and Windows" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-68F7C2?style=for-the-badge">
  <img alt="LAN first" src="https://img.shields.io/badge/network-LAN--first-FF7BCB?style=for-the-badge">
  <img alt="Contributions welcome" src="https://img.shields.io/badge/contributions-welcome-B07BFF?style=for-the-badge">
</p>

<p align="center">
  <a href="#-features">Features</a> ·
  <a href="#-installation">Installation</a> ·
  <a href="#-using-nightwire">Usage</a> ·
  <a href="#-security-model">Security</a> ·
  <a href="#-documentation">Documentation</a> ·
  <a href="#-contributing">Contributing</a>
</p>

> [!IMPORTANT]
> NightWire is designed for trusted home, studio, lab, and office networks. It has no user-account system and should not be exposed directly to the public internet.

## ✨ Overview

NightWire is a lightweight local-network sharing server that runs on one computer and opens in any modern browser on the same LAN. It keeps everyday transfers simple: no cloud upload, no account, and no companion app required.

The interface is divided into three focused pages:

| Page | Purpose |
| --- | --- |
| **Files** | Upload, browse, download, protect, and automatically expire shared files. |
| **Clipboard** | Share text across connected browsers with optional protection and retention controls. |
| **Clients** | See active devices, view LAN addresses, and open NightWire from a QR code. |

## ⚡ Features

<table>
<tr>
<td width="50%" valign="top">

### 📁 LAN-speed file sharing

Files, pasted text, and browser-recorded voice messages use the same streamed Core storage pipeline. Every new Drop gets a copyable share link and exact-link QR, and defaults to a one-hour lifetime.

</td>
<td width="50%" valign="top">

### 📋 Shared clipboard

Share links, commands, notes, and code snippets between connected browsers. Text defaults to a 10-minute lifetime.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔐 Private share access

New Drops use cryptographically random Access Keys stored only as salted digests. An optional password can add a second check; trusted/private operators may explicitly relax key checks.

</td>
<td width="50%" valign="top">

### ⏳ Lifecycle controls

Each item can expire automatically. Connected clients may edit the countdown, and the server enforces expiration even with no browser open.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📱 Browser-native clients

Use NightWire from desktop or mobile Safari, Chrome, Firefox, and other modern browsers without installing a client application.

</td>
<td width="50%" valign="top">

### 🪶 Lightweight core

Built with Python, Starlette, Uvicorn, and a dependency-light frontend. File metadata persists locally; clipboard content stays memory-only.

</td>
</tr>
</table>

## 📦 Requirements

- Python `3.11` or newer
- [`uv`](https://docs.astral.sh/uv/) (installed automatically by the installers)
- A modern browser on the host or another device on the same network
- On Debian, Ubuntu, Fedora, or macOS: `bash`, `tar`, `cmp`, and `curl` or `wget` (the Linux installer installs missing prerequisites with `apt-get` or `dnf`)
- On Windows: Windows PowerShell 5.1+ or PowerShell 7+

NightWire listens on all network interfaces and uses port `8080` by default.

## 🚀 Installation

### Run from the source tree

```bash
cd NightWire
chmod +x run.sh
./run.sh
```

Open the address printed by NightWire, usually:

```text
http://192.168.1.29:8080/files
```

Use another port when needed:

```bash
PORT=9000 ./run.sh
```

`NIGHTWIRE_PORT` is also supported:

```bash
NIGHTWIRE_PORT=9000 ./run.sh
```

### Install on Debian, Ubuntu, Fedora, or macOS

The Unix installer stages and verifies the release before replacing the installed application. If `uv` is missing, it downloads the official standalone installer first. Its defaults are:

```text
Debian/Ubuntu/Fedora app: /srv/nightwire
macOS app:          /usr/local/share/nightwire
Command:            /usr/local/bin/nightwire
```

Install and launch:

```bash
cd NightWire
chmod +x install.sh update-existing.sh run.sh
./install.sh
nightwire
```

Choose another port at launch:

```bash
nightwire --port 9000
```

The installer preserves these paths during upgrades:

```text
files/
.venv/
.env
.env.*
```

Custom installation locations are supported:

```bash
NIGHTWIRE_INSTALL_DIR="$HOME/.local/share/nightwire" \
NIGHTWIRE_BIN_DIR="$HOME/.local/bin" \
./install.sh
```

`sudo` is requested only when the selected paths are not writable by the current user.

### Install on Windows

Extract NightWire, open PowerShell in the extracted directory, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The Windows installer uses per-user directories under `%LOCALAPPDATA%`, installs `uv` automatically when necessary, and adds the `nightwire` launcher to the user `PATH`. Open a new terminal after the first install, then run:

```powershell
nightwire
nightwire --port 9000
```

For source-tree development, `run.bat` remains available and uses port `8080` unless `PORT` or `NIGHTWIRE_PORT` is already set.

## 🔄 Updating

From an extracted release, update another NightWire source tree with:

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

To refresh a system-wide installation after replacing the source files:

```bash
cd /path/to/NightWire
./install.sh
```

## 🌐 Using NightWire

1. Start NightWire on the host computer.
2. Keep every device on the same Wi-Fi, Ethernet network, or hotspot.
3. Open the **Clients** page.
4. Scan the QR code or enter the displayed LAN address on another device.
5. Use **Files** for transfers and **Clipboard** for shared text.

Some routers enable client or access-point isolation, preventing devices on the same Wi-Fi from reaching one another. Disable that option or use another trusted network when necessary.

## 🔒 Security model

NightWire is intentionally LAN-first and does not provide user accounts or per-device authorization.

- Passwords are optional and selected when an item is created.
- Every new Drop receives an Access Key; only the complete share URL can download it.
- Raw Access Keys are returned once and are not persisted by NightWire.
- A password cannot later be added, changed, or removed.
- Protected downloads, clipboard reveals, and deletion require the password.
- Any connected client may change an item's auto-delete countdown.
- Passwords protect access through NightWire; they do **not** encrypt files stored on disk.
- Protected clipboard plaintext is withheld from synchronization responses until unlocked.
- File lifecycle, object-ID, size, and SHA-256 metadata is stored in `files/.nightwire-metadata.json`.
- New uploads use opaque permanent objects in `files/.nightwire-objects/` and isolated temporary storage in `files/.nightwire-uploads/`; original filenames remain visible download names.
- New Drops default to one hour and always have an explicit expiry. Internet-facing anonymous Drops are capped at 24 hours.
- The Secure Drop screen starts with one burn-time control, a file/voice row, and a larger text area; file selection needs only a tap or drop, and voice capture includes a live intensity matrix.
- Active-Drop browsing requires trusted/private mode plus both trusted policy switches, keeping persistent link/QR/download actions coherent; internet-facing deployments always enforce keys and hide the active directory.
- Recipient pages preview shared images for mobile gallery saving and use a custom cross-device voice player backed by explicit `blob:` media policy.
- Core detects MIME from stored bytes, invokes an optional scanner, and records normalized security evidence. Non-clean states are visible; malicious content is retained but cannot enter risky processors and requires a deliberate hold before download.
- Processor contracts record implementation versions and future derived objects; security-sensitive execution is deny-by-default until a real sandbox is configured.
- Clipboard entries remain in server memory and disappear when the process restarts.

Read [the complete security guide](DOCS/SECURITY.md) before using NightWire on a shared or sensitive network.

## 🧱 Project structure

```text
NightWire/
├── app.py                    # Compatibility import and executable launcher
├── nightwire/
│   ├── app/                  # Runtime composition, bootstrap, and middleware
│   ├── core/                 # Storage, transfer, lifecycle, and security contracts
│   ├── drop/                 # Drop domain, repository, services, and registration
│   ├── library/              # Independently enabled Library module skeleton
│   ├── processors/           # Processor results, registry, and sandbox contracts
│   └── text/                 # Future Text module skeleton
├── static/
│   ├── index.html            # Files, Clipboard, and Clients views
│   ├── app.js                # Shared browser application shell
│   ├── drop.js               # Drop-owned behavior and synchronization
│   ├── drop-share.html       # Access-Key recipient page
│   ├── drop-share.js         # Recipient metadata and download flow
│   ├── styles.css            # Responsive aurora interface
│   └── assets/logo.svg       # Project logo
├── files/                    # Preserved Core storage root and legacy shared files
├── tests/                    # Unit and integration-oriented tests
├── install.sh / install.ps1  # Verified Unix and Windows installers
├── update-existing.sh        # Source-tree updater
├── run.sh / run.bat          # Development launchers
└── DOCS/                     # Extended project documentation
```

See [PROJECT.md](DOCS/PROJECT.md) for architecture, persistence, background cleanup, and request-flow details.

## 📚 Documentation

| Guide | Contents |
| --- | --- |
| [Documentation index](DOCS/README.md) | Entry point for all extended guides |
| [Usage](DOCS/USAGE.md) | Files, clipboard, clients, passwords, and countdowns |
| [Project internals](DOCS/PROJECT.md) | Architecture, storage, synchronization, and cleanup |
| [Configuration](DOCS/CONFIGURATION.md) | Ports, paths, launchers, environment variables, and installation |
| [Security](DOCS/SECURITY.md) | Trust assumptions, protection boundaries, and deployment advice |
| [HTTP API](DOCS/API.md) | Endpoints, payloads, responses, and lifecycle operations |
| [Troubleshooting](DOCS/TROUBLESHOOTING.md) | Network, browser, installation, and update problems |
| [Contributing](DOCS/CONTRIBUTING.md) | Development setup, standards, tests, and pull requests |

## 🛠 Development

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python app.py
```

The default development server becomes available at:

```text
http://127.0.0.1:8080/files
```

## 🤝 Contributing

Bug reports, focused feature proposals, documentation improvements, and tested pull requests are welcome.

Before opening a pull request:

1. Read [CONTRIBUTING.md](DOCS/CONTRIBUTING.md).
2. Keep changes focused and preserve backward compatibility where practical.
3. Run the complete test suite.
4. Test the Files, Clipboard, and Clients pages at desktop and mobile widths.
5. Document security, API, configuration, or installation changes.

```bash
uv run python -m unittest discover -s tests -v
```

## 📄 License

NightWire does not currently include a license file. Add an explicit license before public redistribution or accepting external contributions under defined terms.

---

<p align="center">
  Built for fast, private-feeling transfers on networks you trust.
</p>

<!--
Optional live repository counters

Once the repository has a final GitHub owner, replace YOUR_GITHUB_USERNAME and
uncomment these badges near the badge row at the top of this file:

[![GitHub stars](https://img.shields.io/github/stars/YOUR_GITHUB_USERNAME/NightWire?style=for-the-badge&logo=github&color=9B7BFF)](https://github.com/YOUR_GITHUB_USERNAME/NightWire/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/YOUR_GITHUB_USERNAME/NightWire?style=for-the-badge&logo=github&color=65B5FF)](https://github.com/YOUR_GITHUB_USERNAME/NightWire/forks)
[![GitHub issues](https://img.shields.io/github/issues/YOUR_GITHUB_USERNAME/NightWire?style=for-the-badge&logo=github&color=FF7BCB)](https://github.com/YOUR_GITHUB_USERNAME/NightWire/issues)
-->
