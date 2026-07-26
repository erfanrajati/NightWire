# Project Architecture

## Goals

NightWire is built to provide fast, low-friction sharing between devices on the same trusted local network. Its design favors:

- a small dependency set;
- direct file streaming;
- browser-based clients with no app installation;
- predictable local persistence;
- a responsive interface on desktop and mobile;
- simple deployment through `uv` and a Linux installer.

## Non-goals

The current core does not provide:

- user accounts, roles, or per-client authorization;
- end-to-end encryption;
- server-side file encryption;
- internet-facing deployment hardening;
- durable clipboard storage;
- clustering, replication, or multi-server synchronization;
- resumable or chunk-retry upload sessions.

## Technology stack

| Layer | Technology |
| --- | --- |
| Runtime | Python 3.11+ |
| Web framework | Starlette |
| ASGI server | Uvicorn |
| Concurrency helpers | AnyIO |
| QR generation | `qrcode` with SVG output |
| Frontend | Plain HTML, CSS, and JavaScript |
| Dependency management | `uv` and `uv.lock` |
| Tests | Python `unittest` |

## Runtime architecture

```text
Browser clients
    │
    ├── Files UI ───────────────┐
    ├── Clipboard UI ───────────┼── HTTP/JSON and streamed bodies
    └── Clients UI ─────────────┘
                                │
                         Starlette application
                         ├── file service
                         ├── clipboard service
                         ├── client heartbeat registry
                         ├── QR generator
                         └── cleanup worker
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
          Shared file directory          Process memory
          + metadata JSON                clipboard entries
```

The application is a single process. Shared mutable state is guarded by thread locks because the cleanup worker runs in a separate daemon thread while requests are handled by the ASGI server.

## Repository layout

```text
NightWire/
├── app.py                    # Starlette app, API, lifecycle, security, server entry point
├── static/
│   ├── index.html            # Three-page browser shell
│   ├── app.js                # Routing, upload, polling, clipboard, clients, dialogs
│   └── styles.css            # Responsive aurora interface
├── files/
│   └── .gitkeep              # Default shared-file directory placeholder
├── tests/
│   └── test_app.py           # Core unit tests
├── install.sh                # Linux system installer/upgrader
├── update-existing.sh        # Recursive source/installation updater
├── run.sh                    # Unix source-tree launcher
├── run.bat                   # Windows source-tree launcher
├── pyproject.toml            # Package metadata and runtime dependencies
├── uv.lock                   # Locked dependency graph
├── release-manifest.txt      # Files included by the installer/updater
├── VERSION                   # Application version
├── README.md                 # Project overview and installation
└── DOCS/                     # Extended project documentation
```

## Browser routing

The three public page paths serve the same `static/index.html`. The frontend reads the current path, displays the matching page section, and updates browser history without loading a separate HTML document.

- `/files`
- `/clipboard`
- `/clients`

Static assets are served under `/static` with no-store caching headers.

## File lifecycle

1. The client sends raw file bytes to `PUT /api/upload?filename=...`.
2. The server validates the filename and creation settings.
3. Data is streamed to a hidden `.uploading-<id>` temporary file.
4. On success, `os.replace()` atomically moves the temporary file to its final name.
5. Creation time, expiration, and the optional password hash are written to `files/.nightwire-metadata.json`.
6. The cleanup worker removes expired files and their metadata.

The metadata file is written to a temporary path and atomically replaced to reduce the risk of partial writes.

Files placed directly into the shared directory are discovered and receive default metadata: their filesystem modification time becomes the creation time, retention is unlimited, and they are unprotected.

## Clipboard lifecycle

Clipboard entries are stored in a process-local newest-first list.

- Maximum text length: 32,768 characters.
- Maximum history: 40 entries.
- Default retention: 10 minutes.
- Protected plaintext is replaced with `null` in public snapshots.
- A monotonic revision number lets clients avoid re-rendering unchanged history.
- Restarting the process clears all clipboard entries.

## Client presence

Each browser stores a generated client ID in `localStorage` and posts periodic heartbeats. The server keeps an in-memory record containing the IP address, inferred device, operating system, browser, connection time, and last-seen time.

The server itself is always included as the first device record. Browser records expire after 18 seconds without a heartbeat.

## Cleanup worker

An application startup hook creates a daemon thread that checks file and clipboard expiration once per second. The shutdown hook signals and joins the thread.

Request handlers also purge expired items before relevant list, update, unlock, download, or delete operations. This keeps API responses consistent even if cleanup timing is delayed.

## Password model

Passwords are accepted only when an item is created. The server stores:

- a random 16-byte salt;
- a 32-byte `scrypt` digest;
- no plaintext password.

Verification uses constant-time digest comparison. Passwords are immutable through the public API. See [SECURITY.md](SECURITY.md) for the full threat model and limitations.

## Frontend update model

The browser uses lightweight polling:

| Operation | Approximate interval |
| --- | ---: |
| Client heartbeat | 2.5 seconds |
| Clipboard revision poll | 1.2 seconds |
| File list refresh | 4 seconds |
| Visible countdown refresh | 1 second |
| Optional clipboard watch | 1.5 seconds |

Rendering is route-aware so hidden pages do not perform unnecessary visual updates.

## Performance principles

The interface intentionally avoids frontend frameworks and expensive full-viewport animation. When extending the UI:

- keep decorative layers inside the root viewport;
- avoid large animated blur filters and repeated backdrop filters;
- do not create horizontal overflow at mobile widths;
- update only the active page when polling;
- preserve reduced-motion behavior;
- test common iPhone widths as well as desktop layouts.
