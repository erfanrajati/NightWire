# Graph Report - NightWire  (2026-09-14)

## Corpus Check
- 56 files · ~40,404 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 3, .zip 1, .bat 1)

## Summary
- 1055 nodes · 2256 edges · 61 communities (51 shown, 8 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 216 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d225b577`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Request
- Configuration Reference
- README.md
- Any
- Files
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
- test_drop.py
- LocalDropRepository
- LocalFilesystemStorageTests
- CoreTransferService
- TemporaryUploadId
- ObjectId
- test_app.py
- test_core_services.py
- StorageBackend
- runtime.py
- share_clipboard
- _ImmediateAsyncFile
- test_dependency_boundaries.py
- TemporaryUpload
- processors/__init__.py
- TransferService
- DropItem
- drop-share.js
- ProcessorExecutionResult
- CoreTransferServiceTests
- DropServiceTests
- transfer.py
- LifecycleItem
- DropRepository
- _ImmediateAsyncFile
- DropService
- ProtectedDropOverwriteError
- ApplicationRegistry
- LinuxInstallUpdateSmokeTests
- ModuleContext
- base.py
- BootstrapRouteParityTests
- build_application
- load_port
- ModuleBinding

## God Nodes (most connected - your core abstractions)
1. `ObjectId` - 70 edges
2. `StorageBackend` - 44 edges
3. `LocalFilesystemStorage` - 44 edges
4. `DropService` - 37 edges
5. `DropItem` - 32 edges
6. `TemporaryUploadId` - 31 edges
7. `bindEvents()` - 26 edges
8. `CoreTransferService` - 25 edges
9. `asgi_request()` - 25 edges
10. `LocalDropRepository` - 24 edges

## Surprising Connections (you probably didn't know these)
- `ModuleRegistrationContractTests` --uses--> `ApplicationRegistry`  [INFERRED]
  tests/test_bootstrap.py → nightwire/app/registration.py
- `ModuleRegistrationContractTests` --uses--> `ModuleBinding`  [INFERRED]
  tests/test_bootstrap.py → nightwire/app/registration.py
- `DropServiceTests` --uses--> `DeploymentProfile`  [INFERRED]
  tests/test_drop.py → nightwire/core/config.py
- `ConditionalBuiltInModuleTests` --uses--> `InstalledModules`  [INFERRED]
  tests/test_bootstrap.py → nightwire/core/config.py
- `CoreLifecycleTests` --uses--> `LifecycleItem`  [INFERRED]
  tests/test_core_services.py → nightwire/core/lifecycle.py

## Import Cycles
- None detected.

## Communities (61 total, 8 thin omitted)

### Community 0 - "Request"
Cohesion: 0.13
Nodes (25): JSONResponse, clear_clipboard(), delete_clipboard(), delete_file(), delete_file_record(), download_file(), _download_headers(), download_protected_file() (+17 more)

### Community 1 - "Configuration Reference"
Cohesion: 0.17
Nodes (12): Configuration Reference, Deployment profiles, Fixed application limits, Installed launcher, Installed modules, Installer variables, Network behavior, Preserved paths during update (+4 more)

### Community 2 - "README.md"
Cohesion: 0.13
Nodes (13): Documentation conventions, Guides, NightWire Documentation, 🤝 Contributing, 🛠 Development, 📚 Documentation, 📄 License, ✨ Overview (+5 more)

### Community 3 - "Any"
Cohesion: 0.12
Nodes (27): active_device_records(), add_clipboard_entry(), _apply_item_settings(), _clipboard_entry_locked(), clipboard_snapshot(), _default_file_metadata(), delete_clipboard_entry(), _delete_stored_file_locked() (+19 more)

### Community 5 - "Files"
Cohesion: 0.08
Nodes (25): Clients, Clipboard, Common error shape, `DELETE /api/clipboard`, `DELETE /api/clipboard/{entry_id}`, `DELETE /api/files/{filename}`, Files, `GET /api/clipboard?since_revision=REVISION` (+17 more)

### Community 6 - "Contributing to NightWire"
Cohesion: 0.11
Nodes (18): Backend, Before contributing, Branch and commit guidance, Clients, Clipboard, Code organization, Contributing to NightWire, Dependency changes (+10 more)

### Community 7 - "NightWire v1.0.2 Architecture Inventory"
Cohesion: 0.08
Nodes (24): Backend entry point, Cleanup jobs, Client presence state, Clipboard, Clipboard state, Configuration inventory, Expired items worker, File lifecycle metadata (+16 more)

### Community 8 - "Using NightWire"
Cohesion: 0.13
Nodes (15): Auto-delete behavior, Clients, Clipboard, Clipboard persistence, Copy and paste detection, Download and deletion, Files, Pages (+7 more)

### Community 9 - "Security Model"
Cohesion: 0.12
Nodes (16): Clipboard protections and limitations, Deployment recommendations, Drop Access Keys, File handling protections, HTTP response headers, Intended deployment, Lost passwords, Password protection (+8 more)

### Community 10 - "install.sh"
Cohesion: 0.43
Nodes (5): as_admin(), as_install_user(), install.sh script, fail(), find_uv()

### Community 11 - "config.py"
Cohesion: 0.12
Nodes (14): DeploymentProfile, InstalledModules, load_application_config(), _parse_deployment_profile(), _parse_enabled(), Path, Central application configuration for NightWire. The legacy ``app.py`` entry…, Resolve application configuration from an environment mapping. (+6 more)

### Community 12 - "update-existing.sh"
Cohesion: 0.53
Nodes (4): as_root(), fail(), update-existing.sh script, usage()

### Community 13 - "safe_file_path"
Cohesion: 0.32
Nodes (3): Resolve a user-provided filename and prevent path traversal., safe_file_path(), PathTests

### Community 15 - "asgi_request"
Cohesion: 0.10
Nodes (9): asgi_request(), ClientVisibilityCharacterizationTests, ClipboardCharacterizationTests, FileDownloadCharacterizationTests, FileUploadCharacterizationTests, json_request(), LifecycleCharacterizationTests, PasswordProtectionCharacterizationTests (+1 more)

### Community 18 - "Troubleshooting"
Cohesion: 0.12
Nodes (17): A Drop share link was lost, A partial upload file appears, A password was forgotten, Another device cannot connect, Clipboard items disappeared after restart, Clipboard watching is unavailable, Countdown did not delete an item, File metadata problems (+9 more)

### Community 19 - "drop.js"
Cohesion: 0.09
Nodes (67): actionButton(), api(), askPassword(), bindEvents(), clipboardPreview(), clipboardShareSettings(), closePasswordModal(), closeSettings() (+59 more)

### Community 20 - "bootstrap.py"
Cohesion: 0.16
Nodes (12): configured_modules(), Starlette application bootstrap and module composition., Return built-in modules paired with their resolved enabled state., Application composition package with cycle-safe lazy compatibility exports., Contracts used by NightWire modules during application composition., ApplicationConfig, Resolved paths, limits, installed modules, and deployment profile., __getattr__() (+4 more)

### Community 21 - "Project Architecture"
Cohesion: 0.12
Nodes (16): Application bootstrap and module registration, Browser routing, Cleanup worker, Client presence, Clipboard lifecycle, File lifecycle, Frontend update model, Goals (+8 more)

### Community 22 - "⚡ Features"
Cohesion: 0.29
Nodes (7): 📱 Browser-native clients, ⚡ Features, 📁 LAN-speed file sharing, ⏳ Lifecycle controls, 🪶 Lightweight core, 🔐 Private share access, 📋 Shared clipboard

### Community 23 - "ContentProcessor"
Cohesion: 0.11
Nodes (9): ContentProcessor, ProcessorContext, ProcessorRegistry, Optional post-storage transformation or analysis contract., Stable registry name., Implementation version persisted with every execution result., Return whether this processor accepts the stored content., Process content without assuming a local filesystem path. (+1 more)

### Community 25 - "🚀 Installation"
Cohesion: 0.50
Nodes (4): Install on Fedora, Ubuntu, or macOS, Install on Windows, 🚀 Installation, Run from the source tree

### Community 26 - "test_drop.py"
Cohesion: 0.16
Nodes (10): DropAccessKeyPolicy, Generation and verification of bearer Access Keys for Drop shares., Create high-entropy URL-safe keys while persisting only salted digests., AccessKeyDigest, DropDownload, DropUpload, Drop domain types independent of HTTP routes and legacy dictionaries., Non-recoverable verifier for a Drop bearer Access Key. (+2 more)

### Community 27 - "LocalDropRepository"
Cohesion: 0.19
Nodes (4): LocalDropRepository, Any, Path, Filename-keyed JSON metadata retained for upgrade compatibility.

### Community 29 - "CoreTransferService"
Cohesion: 0.13
Nodes (9): CompletedUpload, CoreTransferService, chunks(), PendingUpload, Final transfer facts associated with a stable object ID., Promote one pending upload into permanent storage., Core streaming implementation backed by a logical StorageBackend., A fully streamed upload that has not entered permanent storage. (+1 more)

### Community 30 - "TemporaryUploadId"
Cohesion: 0.12
Nodes (9): Atomically promote a temporary upload to permanent object storage., Logical identity for an isolated, not-yet-finalized upload., Backend-neutral facts returned after an object is finalized., Reserve an isolated temporary upload and return its logical ID., Open a previously allocated temporary upload., Return whether a temporary upload currently exists., Remove a temporary upload if it exists., StoredObject (+1 more)

### Community 31 - "ObjectId"
Cohesion: 0.12
Nodes (12): LocalFilesystemStorage, ObjectId, Any, Path, Open a permanent object by logical ID., Atomically persist JSON-compatible metadata for an object., Load an object's persisted metadata when present., Object-ID storage rooted inside the existing NightWire files directory. (+4 more)

### Community 32 - "test_app.py"
Cohesion: 0.12
Nodes (10): create_password_record(), _password_required(), _sanitize_password_record(), update_file_settings(), verify_password(), CleanupWorkerTests, FileLifecycleTests, immediate_run_sync() (+2 more)

### Community 33 - "test_core_services.py"
Cohesion: 0.06
Nodes (34): AllowAllCapacityPolicy, CapacityDecision, CapacityMeter, CapacityPolicy, CapacityRequest, CapacitySnapshot, ABC, Capacity and quota policy contracts for storage-backed modules. (+26 more)

### Community 34 - "StorageBackend"
Cohesion: 0.09
Nodes (21): Shared configuration, lifecycle, and infrastructure primitives., CoreLifecycleService, LifecycleService, ABC, Core lifecycle decisions and temporary-upload housekeeping., Decide item expiration and reclaim abandoned temporary uploads., Discard inactive temporary uploads older than the configured threshold., Detect, compare, scan, and persist one stored object's security result. (+13 more)

### Community 35 - "runtime.py"
Cohesion: 0.18
Nodes (18): cleanup_expired_items(), _cleanup_worker(), current_drop_service(), current_security_pipeline(), current_storage_backend(), current_transfer_service(), _drop_download_url(), drop_share_info() (+10 more)

### Community 36 - "share_clipboard"
Cohesion: 0.10
Nodes (16): clean_text(), client_heartbeat(), normalize_client_ip(), normalize_clipboard_text(), normalize_optional_password(), parse_user_agent(), Return an optional creation-time password; empty values mean unprotected., Validate shared clipboard text while preserving useful formatting. (+8 more)

### Community 37 - "_ImmediateAsyncFile"
Cohesion: 0.12
Nodes (6): _asgi_request_async(), _CapturedResponse, _immediate_open_file(), _immediate_run_sync(), _ImmediateAsyncFile, Small synchronous-file adapter that keeps ASGI tests off AnyIO worker threads.

### Community 38 - "test_dependency_boundaries.py"
Cohesion: 0.60
Nodes (3): FeatureDependencyBoundaryTests, _internal_module_names(), _resolved_import()

### Community 39 - "TemporaryUpload"
Cohesion: 0.40
Nodes (3): Return unfinished uploads available for orphan cleanup., Backend-neutral facts about one unfinished upload., TemporaryUpload

### Community 40 - "processors/__init__.py"
Cohesion: 0.15
Nodes (16): Versioned processor and sandbox execution contracts., DenySandboxExecutor, ABC, StrEnum, Deny-by-default sandbox execution contracts for sensitive processors., Read-only logical object made available to a sandbox implementation., Resolve logical inputs and execute them inside an implementation-defined…, Run a bounded sandbox request without exposing host filesystem paths. (+8 more)

### Community 41 - "TransferService"
Cohesion: 0.15
Nodes (9): DownloadTransfer, ABC, Prepared object download with observable progress and streamed chunks., Stream uploads/downloads and finalize content without filesystem paths., Stream chunks into isolated temporary storage and calculate integrity., Discard one pending upload without finalizing it., Prepare a lazily streamed permanent-object download., TransferService (+1 more)

### Community 42 - "DropItem"
Cohesion: 0.20
Nodes (5): DropItem, Any, One logical ephemeral file shared through Drop., Return all persisted Drop items., DropDomainRepositoryTests

### Community 43 - "drop-share.js"
Cohesion: 0.36
Nodes (8): downloadDrop(), elements, filename, formatBytes(), formatDate(), loadDrop(), saveBlob(), updateExpiry()

### Community 44 - "ProcessorExecutionResult"
Cohesion: 0.16
Nodes (7): DerivedObject, ProcessorExecutionResult, ProcessorIdentity, Any, A stored object produced from another object by a processor., Compatibility projection for callers that previously read a name string., ProcessorExecutionResultTests

### Community 46 - "DropServiceTests"
Cohesion: 0.08
Nodes (11): PasswordProtection, Request, Configured password protection and HTTP creation-password middleware., decode_optional_password_header(), Decode a UTF-8 password transported in a base64 request header., PasswordDigest, Backend-neutral password verifier data; plaintext is never retained., PasswordProtectionContract (+3 more)

### Community 47 - "transfer.py"
Cohesion: 0.12
Nodes (11): Compatibility import and executable entry point for NightWire., StrEnum, Streaming transfer contracts, progress state, and the Core implementation., Immutable progress event suitable for modules or a future API projection., Thread-safe bounded state containing the latest event per transfer., TransferDirection, TransferPhase, TransferProgress (+3 more)

### Community 48 - "LifecycleItem"
Cohesion: 0.29
Nodes (5): LifecycleItem, LifecycleSweep, Backend-neutral lifecycle facts for one logical item., Classification returned by a lifecycle sweep., Classify expired and physically missing logical items.

### Community 49 - "DropRepository"
Cohesion: 0.12
Nodes (12): _load_file_metadata(), _save_file_metadata_locked(), StrEnum, SecurityVerdict, DropRepository, ABC, Drop metadata repository contract and lightweight local JSON backend., Load durable Drop metadata into the repository. (+4 more)

### Community 51 - "DropService"
Cohesion: 0.25
Nodes (3): DropService, Path, Commit byte/credential/metadata removal as one locked Drop transition.

### Community 52 - "ProtectedDropOverwriteError"
Cohesion: 0.33
Nodes (6): clear_clipboard_entries(), ProtectedDropItemError, ProtectedDropOverwriteError, Direct download attempted for an item requiring password verification., Upload attempted to replace a protected logical name., PermissionError

### Community 53 - "ApplicationRegistry"
Cohesion: 0.17
Nodes (8): LifecycleHook, ApplicationRegistry, Any, Mutable route and lifecycle collection populated by enabled modules., Library module package for future stored-file behavior., LibraryModule, Registration boundary for the not-yet-implemented Library module., Participate in composition without contributing functionality yet.

### Community 55 - "ModuleContext"
Cohesion: 0.17
Nodes (8): ApplicationModule, ModuleContext, ApplicationHandler, Protocol, Configuration and legacy handlers available during registration., A module capable of contributing routes and lifecycle hooks., RequestHandler, ModuleRegistrationContractTests

### Community 56 - "base.py"
Cohesion: 0.33
Nodes (5): Enum, ProcessorExecutionStatus, ABC, StrEnum, Versioned content-processor contracts and deterministic execution results.

### Community 58 - "build_application"
Cohesion: 0.27
Nodes (6): HttpMiddleware, build_application(), ApplicationHandler, Build a Starlette application from enabled module registrations., Starlette, ConditionalBuiltInModuleTests

### Community 59 - "load_port"
Cohesion: 0.22
Nodes (9): list_devices(), local_addresses(), local_ipv4_addresses(), main(), Return usable IPv4 addresses, with the most likely LAN address first., request_port(), server_info(), load_port() (+1 more)

### Community 60 - "ModuleBinding"
Cohesion: 0.27
Nodes (6): ModuleBinding, An application module paired with its resolved enabled state., endpoint(), register(), shutdown(), startup()

## Knowledge Gaps
- **150 isolated node(s):** `nightwire`, `run.sh script`, `PORT`, `elements`, `filename` (+145 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 394 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ObjectId` connect `ObjectId` to `Request`, `Any`, `ContentProcessor`, `test_drop.py`, `LocalDropRepository`, `LocalFilesystemStorageTests`, `CoreTransferService`, `TemporaryUploadId`, `test_core_services.py`, `StorageBackend`, `runtime.py`, `processors/__init__.py`, `TransferService`, `DropItem`, `ProcessorExecutionResult`, `CoreTransferServiceTests`, `transfer.py`, `DropRepository`, `base.py`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **Why does `LocalFilesystemStorage` connect `ObjectId` to `test_core_services.py`, `StorageBackend`, `runtime.py`, `TemporaryUpload`, `processors/__init__.py`, `CoreTransferServiceTests`, `DropServiceTests`, `transfer.py`, `ContentProcessor`, `test_drop.py`, `LocalFilesystemStorageTests`, `CoreTransferService`, `TemporaryUploadId`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `StorageBackend` connect `StorageBackend` to `test_core_services.py`, `TemporaryUpload`, `processors/__init__.py`, `TransferService`, `transfer.py`, `DropService`, `ContentProcessor`, `base.py`, `CoreTransferService`, `TemporaryUploadId`, `ObjectId`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `ObjectId` (e.g. with `_metadata_object_id()` and `_object_download_response()`) actually correct?**
  _`ObjectId` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `StorageBackend` (e.g. with `CoreLifecycleService` and `LifecycleService`) actually correct?**
  _`StorageBackend` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `LocalFilesystemStorage` (e.g. with `current_security_pipeline()` and `current_transfer_service()`) actually correct?**
  _`LocalFilesystemStorage` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `DropService` (e.g. with `DeploymentProfile` and `LifecycleItem`) actually correct?**
  _`DropService` has 11 INFERRED edges - model-reasoned connections that need verification._