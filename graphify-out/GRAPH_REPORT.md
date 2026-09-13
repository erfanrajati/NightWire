# Graph Report - NightWire  (2026-09-13)

## Corpus Check
- 54 files · ~37,795 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 3, .zip 1, .bat 1)

## Summary
- 1005 nodes · 2122 edges · 64 communities (55 shown, 7 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 197 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7cfaa33a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Request
- Configuration Reference
- README.md
- add_clipboard_entry
- HTTP API Reference
- Contributing to NightWire
- NightWire v1.0.2 Architecture Inventory
- Using NightWire
- Security Model
- install.sh
- config.py
- update-existing.sh
- safe_file_path
- run.sh
- asgi_request
- nightwire
- Troubleshooting
- drop.js
- bootstrap.py
- Project Architecture
- ⚡ Features
- ContentProcessor
- text/__init__.py
- 🚀 Installation
- NightWire Documentation
- DropItem
- ObjectId
- CoreTransferService
- TemporaryUploadId
- LocalFilesystemStorage
- test_app.py
- test_core_services.py
- core/__init__.py
- runtime.py
- share_clipboard
- Files
- test_dependency_boundaries.py
- TemporaryUpload
- StorageBackend
- TransferService
- security.py
- CoreSecurityPipeline
- ProcessorExecutionResult
- test_core_storage.py
- PasswordDigest
- TransferProgressStore
- _Scanner
- service.py
- _ImmediateAsyncFile
- DropService
- DropServiceTests
- ApplicationRegistry
- Any
- ModuleContext
- test_processors.py
- test_bootstrap.py
- build_application
- load_port
- .test_enabled_module_can_register_routes_and_lifecycle_hooks
- .load
- .save
- .object_size

## God Nodes (most connected - your core abstractions)
1. `ObjectId` - 70 edges
2. `StorageBackend` - 44 edges
3. `LocalFilesystemStorage` - 44 edges
4. `DropService` - 32 edges
5. `TemporaryUploadId` - 31 edges
6. `DropItem` - 30 edges
7. `CoreTransferService` - 25 edges
8. `bindEvents()` - 24 edges
9. `asgi_request()` - 24 edges
10. `LocalDropRepository` - 22 edges

## Surprising Connections (you probably didn't know these)
- `DropServiceTests` --uses--> `PasswordProtection`  [INFERRED]
  tests/test_drop.py → nightwire/app/passwords.py
- `ModuleRegistrationContractTests` --uses--> `ModuleContext`  [INFERRED]
  tests/test_bootstrap.py → nightwire/app/registration.py
- `ModuleRegistrationContractTests` --uses--> `ApplicationRegistry`  [INFERRED]
  tests/test_bootstrap.py → nightwire/app/registration.py
- `ConditionalBuiltInModuleTests` --uses--> `InstalledModules`  [INFERRED]
  tests/test_bootstrap.py → nightwire/core/config.py
- `DropServiceTests` --uses--> `CoreLifecycleService`  [INFERRED]
  tests/test_drop.py → nightwire/core/lifecycle.py

## Import Cycles
- None detected.

## Communities (64 total, 7 thin omitted)

### Community 0 - "Request"
Cohesion: 0.22
Nodes (21): JSONResponse, clear_clipboard(), delete_clipboard(), delete_file(), download_file(), download_protected_file(), list_clipboard(), list_devices() (+13 more)

### Community 1 - "Configuration Reference"
Cohesion: 0.17
Nodes (12): Configuration Reference, Deployment profiles, Fixed application limits, Installed launcher, Installed modules, Installer variables, Network behavior, Preserved paths during update (+4 more)

### Community 2 - "README.md"
Cohesion: 0.16
Nodes (10): 🤝 Contributing, 🛠 Development, 📚 Documentation, 📄 License, ✨ Overview, 🧱 Project structure, 📦 Requirements, 🔒 Security model (+2 more)

### Community 3 - "add_clipboard_entry"
Cohesion: 0.12
Nodes (19): add_clipboard_entry(), clear_clipboard_entries(), _clipboard_entry_locked(), clipboard_snapshot(), delete_clipboard_entry(), _expires_at_from_seconds(), normalize_clipboard_text(), parse_iso_timestamp() (+11 more)

### Community 5 - "HTTP API Reference"
Cohesion: 0.08
Nodes (24): Clients, Clipboard, Common error shape, `DELETE /api/clipboard`, `DELETE /api/clipboard/{entry_id}`, `DELETE /api/files/{filename}`, Files, `GET /api/clipboard?since_revision=REVISION` (+16 more)

### Community 6 - "Contributing to NightWire"
Cohesion: 0.11
Nodes (18): Backend, Before contributing, Branch and commit guidance, Clients, Clipboard, Code organization, Contributing to NightWire, Dependency changes (+10 more)

### Community 7 - "NightWire v1.0.2 Architecture Inventory"
Cohesion: 0.08
Nodes (24): Backend entry point, Cleanup jobs, Client presence state, Clipboard, Clipboard state, Configuration inventory, Expired items worker, File lifecycle metadata (+16 more)

### Community 8 - "Using NightWire"
Cohesion: 0.18
Nodes (10): Clients, Clipboard, Clipboard persistence, Copy and paste detection, Pages, Protected clipboard entries, Recommended workflow, Retention defaults and limits (+2 more)

### Community 9 - "Security Model"
Cohesion: 0.13
Nodes (15): Clipboard protections and limitations, Deployment recommendations, File handling protections, HTTP response headers, Intended deployment, Lost passwords, Password protection, Protection scope (+7 more)

### Community 10 - "install.sh"
Cohesion: 0.43
Nodes (5): as_admin(), as_install_user(), install.sh script, fail(), find_uv()

### Community 11 - "config.py"
Cohesion: 0.11
Nodes (15): Enum, DeploymentProfile, InstalledModules, load_application_config(), _parse_deployment_profile(), _parse_enabled(), Path, Central application configuration for NightWire. The legacy ``app.py`` entry… (+7 more)

### Community 12 - "update-existing.sh"
Cohesion: 0.53
Nodes (4): as_root(), fail(), update-existing.sh script, usage()

### Community 13 - "safe_file_path"
Cohesion: 0.32
Nodes (3): Resolve a user-provided filename and prevent path traversal., safe_file_path(), PathTests

### Community 15 - "asgi_request"
Cohesion: 0.05
Nodes (22): Compatibility import and executable entry point for NightWire., StrEnum, TransferDirection, TransferPhase, asgi_request(), _asgi_request_async(), _CapturedResponse, ClientVisibilityCharacterizationTests (+14 more)

### Community 18 - "Troubleshooting"
Cohesion: 0.12
Nodes (16): A partial upload file appears, A password was forgotten, Another device cannot connect, Clipboard items disappeared after restart, Clipboard watching is unavailable, Countdown did not delete an item, File metadata problems, Installed version did not change (+8 more)

### Community 19 - "drop.js"
Cohesion: 0.10
Nodes (61): actionButton(), api(), askPassword(), bindEvents(), clipboardPreview(), clipboardShareSettings(), closePasswordModal(), closeSettings() (+53 more)

### Community 20 - "bootstrap.py"
Cohesion: 0.15
Nodes (12): configured_modules(), Starlette application bootstrap and module composition., Return built-in modules paired with their resolved enabled state., Application composition package with cycle-safe lazy compatibility exports., Contracts used by NightWire modules during application composition., ApplicationConfig, Resolved paths, limits, installed modules, and deployment profile., __getattr__() (+4 more)

### Community 21 - "Project Architecture"
Cohesion: 0.12
Nodes (16): Application bootstrap and module registration, Browser routing, Cleanup worker, Client presence, Clipboard lifecycle, File lifecycle, Frontend update model, Goals (+8 more)

### Community 22 - "⚡ Features"
Cohesion: 0.29
Nodes (7): 📱 Browser-native clients, ⚡ Features, 📁 LAN-speed file sharing, ⏳ Lifecycle controls, 🪶 Lightweight core, 🔐 Optional protection, 📋 Shared clipboard

### Community 23 - "ContentProcessor"
Cohesion: 0.11
Nodes (10): ContentProcessor, ProcessorContext, ProcessorRegistry, ABC, Versioned content-processor contracts and deterministic execution results., Optional post-storage transformation or analysis contract., Stable registry name., Implementation version persisted with every execution result. (+2 more)

### Community 25 - "🚀 Installation"
Cohesion: 0.50
Nodes (4): Install on Fedora, Ubuntu, or macOS, Install on Windows, 🚀 Installation, Run from the source tree

### Community 26 - "NightWire Documentation"
Cohesion: 0.67
Nodes (3): Documentation conventions, Guides, NightWire Documentation

### Community 27 - "DropItem"
Cohesion: 0.10
Nodes (11): DropItem, Any, One logical ephemeral file shared through Drop., LocalDropRepository, Any, Path, Return one logical Drop item., Return all persisted Drop items. (+3 more)

### Community 28 - "ObjectId"
Cohesion: 0.11
Nodes (6): ObjectId, Open a permanent object by logical ID., Atomically persist JSON-compatible metadata for an object., Load an object's persisted metadata when present., Stable logical identity for one permanently stored object., LocalFilesystemStorageTests

### Community 29 - "CoreTransferService"
Cohesion: 0.15
Nodes (9): CompletedUpload, CoreTransferService, chunks(), PendingUpload, Final transfer facts associated with a stable object ID., Promote one pending upload into permanent storage., Core streaming implementation backed by a logical StorageBackend., A fully streamed upload that has not entered permanent storage. (+1 more)

### Community 30 - "TemporaryUploadId"
Cohesion: 0.15
Nodes (7): Atomically promote a temporary upload to permanent object storage., Map a validated upload ID to its isolated physical reference., Logical identity for an isolated, not-yet-finalized upload., Backend-neutral facts returned after an object is finalized., Open a previously allocated temporary upload., StoredObject, TemporaryUploadId

### Community 31 - "LocalFilesystemStorage"
Cohesion: 0.23
Nodes (6): LocalFilesystemStorage, Any, Path, Object-ID storage rooted inside the existing NightWire files directory., Map a validated object ID to its opaque physical reference., Map a validated object ID to its internal metadata sidecar.

### Community 32 - "test_app.py"
Cohesion: 0.13
Nodes (8): create_password_record(), delete_file_record(), update_file_settings(), CleanupWorkerTests, FileLifecycleTests, immediate_run_sync(), PasswordTests, Run the cleanup join inline so Python 3.14 does not retain an AnyIO worker.

### Community 33 - "test_core_services.py"
Cohesion: 0.21
Nodes (15): AllowAllCapacityPolicy, CapacityDecision, CapacityMeter, CapacityPolicy, CapacityRequest, CapacitySnapshot, ABC, Capacity and quota policy contracts for storage-backed modules. (+7 more)

### Community 34 - "core/__init__.py"
Cohesion: 0.15
Nodes (13): Shared configuration, lifecycle, and infrastructure primitives., CoreLifecycleService, LifecycleItem, LifecycleService, LifecycleSweep, ABC, Core lifecycle decisions and temporary-upload housekeeping., Backend-neutral lifecycle facts for one logical item. (+5 more)

### Community 35 - "runtime.py"
Cohesion: 0.16
Nodes (19): _apply_item_settings(), cleanup_expired_items(), _cleanup_worker(), current_drop_service(), current_security_pipeline(), current_storage_backend(), current_transfer_service(), _download_headers() (+11 more)

### Community 36 - "share_clipboard"
Cohesion: 0.09
Nodes (15): clean_text(), client_heartbeat(), normalize_client_ip(), normalize_optional_password(), parse_user_agent(), Return an optional creation-time password; empty values mean unprotected., Return a compact device/browser summary without adding a parser dependency., share_clipboard() (+7 more)

### Community 37 - "Files"
Cohesion: 0.40
Nodes (5): Auto-delete behavior, Download and deletion, Files, Password behavior, Upload a file

### Community 38 - "test_dependency_boundaries.py"
Cohesion: 0.60
Nodes (3): FeatureDependencyBoundaryTests, _internal_module_names(), _resolved_import()

### Community 39 - "TemporaryUpload"
Cohesion: 0.50
Nodes (3): Return unfinished uploads available for orphan cleanup., Backend-neutral facts about one unfinished upload., TemporaryUpload

### Community 40 - "StorageBackend"
Cohesion: 0.10
Nodes (18): Return whether an object currently exists., Return an object's modification timestamp., Remove an object if it exists., Storage operations addressed only by logical object/upload IDs., Reserve an isolated temporary upload and return its logical ID., Return whether a temporary upload currently exists., Remove a temporary upload if it exists., StorageBackend (+10 more)

### Community 41 - "TransferService"
Cohesion: 0.15
Nodes (9): DownloadTransfer, ABC, Prepared object download with observable progress and streamed chunks., Stream uploads/downloads and finalize content without filesystem paths., Stream chunks into isolated temporary storage and calculate integrity., Discard one pending upload without finalizing it., Prepare a lazily streamed permanent-object download., TransferService (+1 more)

### Community 42 - "security.py"
Cohesion: 0.20
Nodes (11): compare_mime_evidence(), detect_mime_signature(), MimeComparison, MimeDetection, normalize_mime(), Any, StrEnum, Content-type evidence, security verdicts, and scanner-neutral inspection. (+3 more)

### Community 43 - "CoreSecurityPipeline"
Cohesion: 0.17
Nodes (9): CoreSecurityPipeline, MalwareScannerAdapter, ABC, Detect, compare, scan, and persist one stored object's security result., Scanner contract addressed by object identity, never a caller path., Stable scanner implementation name., SecurityPipeline, CoreSecurityTests (+1 more)

### Community 44 - "ProcessorExecutionResult"
Cohesion: 0.13
Nodes (8): DerivedObject, ProcessorExecutionResult, ProcessorIdentity, Any, Process content without assuming a local filesystem path., A stored object produced from another object by a processor., Compatibility projection for callers that previously read a name string., ProcessorExecutionResultTests

### Community 45 - "test_core_storage.py"
Cohesion: 0.14
Nodes (3): CoreTransferServiceTests, _immediate_open_file(), _ImmediateAsyncFile

### Community 46 - "PasswordDigest"
Cohesion: 0.15
Nodes (11): PasswordProtection, Request, Configured password protection and HTTP creation-password middleware., decode_optional_password_header(), Decode a UTF-8 password transported in a base64 request header., _sanitize_password_record(), verify_password(), PasswordDigest (+3 more)

### Community 47 - "TransferProgressStore"
Cohesion: 0.28
Nodes (4): Immutable progress event suitable for modules or a future API projection., Thread-safe bounded state containing the latest event per transfer., TransferProgress, TransferProgressStore

### Community 48 - "_Scanner"
Cohesion: 0.33
Nodes (3): MalwareScanResult, Inspect a stored object and return a normalized scanner result., _Scanner

### Community 49 - "service.py"
Cohesion: 0.17
Nodes (13): ABC, Logical object storage contracts and the local-filesystem backend., Streaming transfer contracts, progress state, and the Core implementation., DropDownload, DropUpload, Drop domain types independent of HTTP routes and legacy dictionaries., DropRepository, ABC (+5 more)

### Community 51 - "DropService"
Cohesion: 0.29
Nodes (3): DropService, Path, RLock

### Community 52 - "DropServiceTests"
Cohesion: 0.14
Nodes (3): DropServiceTests, _immediate_open_file(), _ImmediateAsyncFile

### Community 53 - "ApplicationRegistry"
Cohesion: 0.19
Nodes (8): LifecycleHook, ApplicationRegistry, Any, Mutable route and lifecycle collection populated by enabled modules., Library module package for future stored-file behavior., LibraryModule, Registration boundary for the not-yet-implemented Library module., Participate in composition without contributing functionality yet.

### Community 54 - "Any"
Cohesion: 0.27
Nodes (13): active_device_records(), _default_file_metadata(), _delete_stored_file_locked(), _file_metadata_locked(), human_file_record(), _metadata_object_id(), metadata_path(), purge_inactive_clients() (+5 more)

### Community 55 - "ModuleContext"
Cohesion: 0.20
Nodes (7): ApplicationModule, ModuleContext, ApplicationHandler, Protocol, Configuration and legacy handlers available during registration., A module capable of contributing routes and lifecycle hooks., RequestHandler

### Community 56 - "test_processors.py"
Cohesion: 0.20
Nodes (8): ProcessorExecutionStatus, StrEnum, StrEnum, Read-only logical object made available to a sandbox implementation., SandboxExecutionStatus, SandboxInput, SandboxLimits, SandboxExecutionContractTests

### Community 57 - "test_bootstrap.py"
Cohesion: 0.22
Nodes (4): ModuleBinding, An application module paired with its resolved enabled state., BootstrapRouteParityTests, ModuleRegistrationContractTests

### Community 58 - "build_application"
Cohesion: 0.27
Nodes (6): HttpMiddleware, build_application(), ApplicationHandler, Build a Starlette application from enabled module registrations., Starlette, ConditionalBuiltInModuleTests

### Community 59 - "load_port"
Cohesion: 0.29
Nodes (6): local_addresses(), local_ipv4_addresses(), main(), Return usable IPv4 addresses, with the most likely LAN address first., load_port(), Read ``PORT`` with the same integer conversion semantics as v1.0.2.

### Community 60 - ".test_enabled_module_can_register_routes_and_lifecycle_hooks"
Cohesion: 0.53
Nodes (4): endpoint(), register(), shutdown(), startup()

## Knowledge Gaps
- **145 isolated node(s):** `nightwire`, `run.sh script`, `PORT`, `state`, `elements` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 382 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ObjectId` connect `ObjectId` to `Request`, `ContentProcessor`, `DropItem`, `CoreTransferService`, `TemporaryUploadId`, `LocalFilesystemStorage`, `core/__init__.py`, `runtime.py`, `StorageBackend`, `TransferService`, `security.py`, `CoreSecurityPipeline`, `ProcessorExecutionResult`, `test_core_storage.py`, `TransferProgressStore`, `_Scanner`, `service.py`, `Any`, `test_processors.py`, `.object_size`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Why does `StorageBackend` connect `StorageBackend` to `core/__init__.py`, `TemporaryUpload`, `TransferService`, `security.py`, `CoreSecurityPipeline`, `test_core_storage.py`, `_Scanner`, `service.py`, `CoreTransferService`, `DropService`, `ContentProcessor`, `ObjectId`, `.object_size`, `TemporaryUploadId`, `LocalFilesystemStorage`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `LocalFilesystemStorage` connect `LocalFilesystemStorage` to `test_core_services.py`, `core/__init__.py`, `runtime.py`, `StorageBackend`, `CoreSecurityPipeline`, `test_core_storage.py`, `service.py`, `DropServiceTests`, `ContentProcessor`, `test_processors.py`, `ObjectId`, `CoreTransferService`, `TemporaryUploadId`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `ObjectId` (e.g. with `_metadata_object_id()` and `_object_download_response()`) actually correct?**
  _`ObjectId` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `StorageBackend` (e.g. with `CoreLifecycleService` and `LifecycleService`) actually correct?**
  _`StorageBackend` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `LocalFilesystemStorage` (e.g. with `current_security_pipeline()` and `current_transfer_service()`) actually correct?**
  _`LocalFilesystemStorage` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `DropService` (e.g. with `LifecycleItem` and `LifecycleService`) actually correct?**
  _`DropService` has 10 INFERRED edges - model-reasoned connections that need verification._