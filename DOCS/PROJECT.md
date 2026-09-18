# Project Architecture

## Goals

NightWire is built to provide fast, low-friction sharing between devices on the same trusted local network. Its design favors:

- a small dependency set;
- direct file streaming;
- browser-based clients with no app installation;
- predictable local persistence;
- a responsive interface on desktop and mobile;
- simple deployment through `uv` and cross-platform installers.

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
                         ├── Core transfer service
                         ├── clipboard service
                         ├── client heartbeat registry
                         ├── QR generator
                         └── cleanup worker
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
          Core object storage            Process memory
          + metadata JSON                clipboard entries
```

The application is a single process. Shared mutable state is guarded by thread locks because the cleanup worker runs in a separate daemon thread while requests are handled by the ASGI server.

## Repository layout

```text
NightWire/
├── app.py                    # 15-line compatibility alias and executable launcher
├── nightwire/
│   ├── core/config.py        # Central paths, limits, module flags, and deployment profile
│   ├── core/capacity.py      # Capacity-meter and quota-policy contracts
│   ├── core/lifecycle.py     # Expiration decisions and orphan-upload cleanup
│   ├── core/security.py      # MIME evidence, verdicts, pipeline, and scanner contract
│   ├── core/storage.py       # Logical object-ID storage contract and local backend
│   ├── core/transfer.py      # Upload/download streaming, progress, and finalization
│   ├── drop/
│   │   ├── access.py         # Access Key generation and digest verification
│   │   ├── domain.py         # Route-independent Drop entities
│   │   ├── repository.py     # Metadata contract and local JSON repository
│   │   ├── service.py        # File use cases composed over Core contracts
│   │   ├── compatibility.py  # Clipboard facade and client-visibility service
│   │   └── registration.py   # Current route/static/lifecycle registration
│   ├── library/registration.py # Empty initial Library registration
│   ├── text/                 # Shared-text package boundary (skeleton)
│   ├── processors/
│   │   ├── base.py           # Versioned results, derived objects, contract, and registry
│   │   └── sandbox.py        # Deny-by-default isolated-execution abstraction
│   └── app/
│       ├── bootstrap.py      # Starlette construction and conditional composition
│       ├── passwords.py      # Configured password policy and request middleware
│       ├── registration.py   # Module, registry, context, and binding contracts
│       └── runtime.py        # HTTP adapters, compatibility helpers, and runtime
├── static/
│   ├── index.html            # Three-page browser shell
│   ├── app.js                # Shared ES-module application bootstrap
│   ├── drop.js               # Drop-owned v1.0.2 UI behavior
│   ├── drop-share.html       # Recipient Drop page
│   ├── drop-share.js         # Access-Key recipient flow
│   └── styles.css            # Responsive aurora interface
├── files/
│   └── .gitkeep              # Default shared-file directory placeholder
├── tests/                    # Unit, characterization, architecture, and installer tests
├── install.sh                # Linux and macOS installer/upgrader
├── install.ps1               # Windows installer/upgrader
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

The root `app.py` is only a compatibility alias and executable launcher. On import it resolves to `nightwire.app.runtime`, preserving legacy attribute mutation and monkeypatch behavior without retaining implementation at the repository root. Core owns infrastructure contracts; Drop owns its domain, repository, file use cases, clipboard compatibility facade, client visibility, and route registration; the application package owns composition, configured password middleware, and HTTP adaptation.

`DropItem` is independent of Starlette requests and response dictionaries. `DropRepository` owns metadata access, with `LocalDropRepository` retaining the lightweight filename-keyed `.nightwire-metadata.json` format so existing installations migrate without a database or one-time conversion. The compatibility `_FILE_METADATA` mapping is the local repository's backing map during this transition.

## Application bootstrap and module registration

`nightwire.app.bootstrap.build_application()` creates a registration context and registry, invokes each enabled module in order, then builds the Starlette application from the collected routes and startup/shutdown hooks. Global HTTP middleware is supplied to the same bootstrap function.

Modules implement a small registration contract: a stable `name` plus `register(registry, context)`. The registry accepts HTTP routes, mounted ASGI applications, startup hooks, and shutdown hooks. The context exposes resolved settings and the legacy handler mapping during migration.

Drop is the initial compatibility module and registers every v1.0.2 route, `/static`, and the cleanup worker hooks. Library is independently conditional but currently registers no functionality. Registered module names are exposed as `app.state.registered_modules` for diagnostics and tests.

File, text, and voice route handlers validate transport input, invoke `DropService`, and translate domain exceptions to status codes. `DropService` composes the Drop repository with Core storage, transfer, lifecycle, and security contracts. `DropItem.content_kind` identifies `file`, `text`, or `voice` without changing the physical transfer path. Password creation and verification are injected as configured policy; the upload password header is decoded by application middleware. Clipboard routes pass through `DropClipboardService` pending the Text migration. Client TTL, mutation, sorting, and projection live in `DropClientVisibilityService`.

## Browser routing

The three public page paths serve the same `static/index.html`. The frontend reads the current path, displays the matching page section, and updates browser history without loading a separate HTML document.

- `/files`
- `/clipboard`
- `/clients`

Static assets are served under `/static` with no-store caching headers.

## File lifecycle

1. The client sends raw file or recorded-audio bytes to `PUT /api/drops/files?filename=...`, or text to `POST /api/drops/text`; `/api/upload` remains a compatibility alias.
2. The server validates the filename and creation settings.
3. Core allocates an isolated ID under `files/.nightwire-uploads/` and streams the body there while calculating SHA-256.
4. After the complete body is received and overwrite rules are rechecked, Core atomically promotes the temporary upload into `files/.nightwire-objects/` under a stable opaque object ID.
5. Core detects MIME from stored bytes, compares extension/declared/detected evidence, optionally invokes a scanner adapter, and persists a normalized security result beside the stored object.
6. The logical filename, object ID, byte size, checksum, security result, explicit creation/expiry timestamps, salted Access Key digest, and optional password hash are written to `files/.nightwire-metadata.json`.
7. The cleanup worker resolves the object ID and removes both expired physical content and metadata.

The raw 256-bit Access Key is returned only in the upload response and complete recipient URL. It is never persisted. Trusted policy may relax validation or allow active browsing; internet-facing policy always requires keys and denies browsing. New Drops default to one hour, accept a selected positive lifetime, and are capped at 24 hours under the `internet-facing` deployment profile. Expiration runs under the Drop lock and removes the credential record, metadata, object security sidecar, and underlying bytes before access can resume.

The metadata file is written to a temporary path and atomically replaced to reduce the risk of partial writes.

Storage and transfer interfaces accept logical `ObjectId` and `TemporaryUploadId` values rather than caller-supplied paths. The local backend alone maps those validated IDs to physical references. Filenames therefore remain user-facing labels and do not determine where new content is stored.

Legacy files placed directly into the shared directory remain discoverable and receive default metadata: their filesystem modification time becomes the creation time, retention is unlimited, and they are unprotected. They continue to work until replaced by a new upload, which migrates that logical filename to object-backed storage.

Object-backed downloads are prepared and streamed in `CoreTransferService`. Uploads and downloads emit immutable progress events into a bounded, thread-safe latest-state store and optional hooks. Transfer IDs are returned by uploads and in object-download response headers so a future module or frontend endpoint can correlate that state. No progress-listing route is registered yet.

Core owns Community capacity enforcement and a process-wide, thread-safe upload reservation ledger. Drop, Personal Library, and Workspace uploads share installation, object-size, and host-reserve checks while retaining their independent logical quotas. Declared sizes are checked before allocation and every streamed chunk is checked again.

## Security pipeline

`CoreSecurityPipeline` reads object bytes through the storage interface. Signature/structure detection does not use the filename or browser-declared MIME. It then compares detected MIME with the filename extension and normalized declared MIME.

The verdict vocabulary is `clean`, `suspicious`, `malicious`, `scan_failed`, and `unscanned`. With no scanner configured, consistent content is `unscanned`; scanner errors remain `scan_failed`; and mismatched MIME evidence is `suspicious`. `MalwareScannerAdapter` lets configured engines inspect an object ID through Core storage without product-specific coupling. Persisted results include scanner engine and signature-set provenance.

`CoreSecurityPolicy` always permits opaque storage, requires explicit confirmation to download a malicious object, and blocks malicious content from risky processors. `ProcessorRegistry` applies that policy before invoking processor support or execution code. The Drop service applies the same policy at both download entry points, while the browser renders every non-clean state and uses a hold gesture for malicious confirmation.

`ProcessorRegistry` provides ordered, unique-name registration for post-storage processors. A `ProcessorIdentity` combines the stable name with an implementation version, and every execution result records that exact identity plus `succeeded`, `failed`, or `skipped` status. Results can include metadata, timing, an error, and zero or more typed `DerivedObject` references for content a future processor stores through Core. One processor failure is isolated from later processors. No processors are registered by default.

Security-sensitive processors can depend on `SandboxExecutor` instead of invoking host processes directly. Requests contain a processor identity, a sandbox executable name, arguments, read-only logical object inputs, bounded wall-time/memory/output/process limits, an explicit environment, and a network flag that defaults off. Inputs and commands cannot contain host paths. NightWire currently supplies only `DenySandboxExecutor`, so sandbox work cannot accidentally run until a genuinely isolated implementation is configured.

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

An application startup hook creates a daemon thread that asks `CoreLifecycleService` to classify file and clipboard expiration once per second. The same sweep removes inactive temporary uploads older than 24 hours while excluding upload IDs currently owned by the transfer service. The shutdown hook signals and joins the thread.

Request handlers also purge expired items before relevant list, update, unlock, download, or delete operations. This keeps API responses consistent even if cleanup timing is delayed.

## Password model

Passwords are accepted only when an item is created. The server stores:

- a random 16-byte salt;
- a 32-byte `scrypt` digest;
- no plaintext password.

Verification uses constant-time digest comparison. Passwords are immutable through the public API. See [SECURITY.md](SECURITY.md) for the full threat model and limitations.

## Frontend update model

`static/index.html` loads the shared `static/app.js` ES-module shell, which imports and starts Drop-owned `static/drop.js`. The primary Secure Drop view removes the legacy dashboard/navigation treatment and presents one composer: a shared lifetime control plus file, pasted-text, and browser-recorded voice choices. It conditionally renders the policy-governed active directory and retains a newly issued key only in page memory. The creation modal provides a copy action and QR encoding the exact complete URL. `/drop/{filename}?key=...` serves `static/drop-share.html`, whose `drop-share.js` validates effective access policy, previews text or audio, displays recipient-safe metadata and expiration, and performs downloads.

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
