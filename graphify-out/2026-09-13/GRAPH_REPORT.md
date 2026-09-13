# Graph Report - NightWire  (2026-09-13)

## Corpus Check
- 45 files · ~34,976 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 3, .zip 1, .bat 1)

## Summary
- 865 nodes · 1834 edges · 51 communities (43 shown, 7 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 130 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7cfaa33a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Request
- Configuration Reference
- README.md
- Any
- app.js
- HTTP API Reference
- Contributing to NightWire
- NightWire v1.0.2 Architecture Inventory
- Using NightWire
- Security Model
- install.sh
- config.py
- update-existing.sh
- PathTests
- run.sh
- asgi_request
- nightwire
- Troubleshooting
- upload_file
- ModuleContext
- Project Architecture
- ⚡ Features
- ContentProcessor
- text/__init__.py
- 🚀 Installation
- NightWire Documentation
- app.py
- ObjectId
- CoreTransferService
- TemporaryUploadId
- LocalFilesystemStorage
- test_app.py
- test_core_services.py
- core/__init__.py
- normalize_optional_password
- share_clipboard
- Files
- test_dependency_boundaries.py
- StorageBackend
- processors/__init__.py
- transfer.py
- security.py
- CoreSecurityTests
- ProcessorIdentity
- CoreTransferServiceTests
- ProcessorExecutionResult
- TransferProgressStore
- _Scanner
- _ImmediateAsyncFile
- _ImmediateAsyncFile

## God Nodes (most connected - your core abstractions)
1. `ObjectId` - 65 edges
2. `StorageBackend` - 40 edges
3. `LocalFilesystemStorage` - 40 edges
4. `TemporaryUploadId` - 31 edges
5. `bindEvents()` - 24 edges
6. `CoreTransferService` - 22 edges
7. `asgi_request()` - 20 edges
8. `ModuleContext` - 19 edges
9. `upload_file()` - 18 edges
10. `build_application()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `current_transfer_service()` --uses--> `LocalFilesystemStorage`  [INFERRED]
  app.py → nightwire/core/storage.py
- `current_security_pipeline()` --uses--> `LocalFilesystemStorage`  [INFERRED]
  app.py → nightwire/core/storage.py
- `_metadata_object_id()` --uses--> `ObjectId`  [INFERRED]
  app.py → nightwire/core/storage.py
- `_load_file_metadata()` --uses--> `SecurityVerdict`  [INFERRED]
  app.py → nightwire/core/security.py
- `_load_file_metadata()` --uses--> `ObjectId`  [INFERRED]
  app.py → nightwire/core/storage.py

## Import Cycles
- None detected.

## Communities (51 total, 7 thin omitted)

### Community 0 - "Request"
Cohesion: 0.21
Nodes (19): clear_clipboard(), clear_clipboard_entries(), delete_clipboard(), delete_file(), list_clipboard(), list_devices(), page(), patch_clipboard() (+11 more)

### Community 1 - "Configuration Reference"
Cohesion: 0.17
Nodes (12): Configuration Reference, Deployment profiles, Fixed application limits, Installed launcher, Installed modules, Installer variables, Network behavior, Preserved paths during update (+4 more)

### Community 2 - "README.md"
Cohesion: 0.16
Nodes (10): 🤝 Contributing, 🛠 Development, 📚 Documentation, 📄 License, ✨ Overview, 🧱 Project structure, 📦 Requirements, 🔒 Security model (+2 more)

### Community 3 - "Any"
Cohesion: 0.17
Nodes (13): add_clipboard_entry(), _clipboard_entry_locked(), clipboard_snapshot(), delete_clipboard_entry(), normalize_clipboard_text(), _password_required(), _public_clipboard_entry(), _purge_expired_clipboard_entries_locked() (+5 more)

### Community 4 - "app.js"
Cohesion: 0.10
Nodes (61): actionButton(), api(), askPassword(), bindEvents(), clipboardPreview(), clipboardShareSettings(), closePasswordModal(), closeSettings() (+53 more)

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
Nodes (17): Enum, DeploymentProfile, InstalledModules, load_application_config(), load_port(), _parse_deployment_profile(), _parse_enabled(), Path (+9 more)

### Community 12 - "update-existing.sh"
Cohesion: 0.53
Nodes (4): as_root(), fail(), update-existing.sh script, usage()

### Community 15 - "asgi_request"
Cohesion: 0.06
Nodes (16): asgi_request(), _asgi_request_async(), _CapturedResponse, ClientVisibilityCharacterizationTests, ClipboardCharacterizationTests, FileDownloadCharacterizationTests, FileUploadCharacterizationTests, _immediate_open_file() (+8 more)

### Community 18 - "Troubleshooting"
Cohesion: 0.12
Nodes (16): A partial upload file appears, A password was forgotten, Another device cannot connect, Clipboard items disappeared after restart, Clipboard watching is unavailable, Countdown did not delete an item, File metadata problems, Installed version did not change (+8 more)

### Community 19 - "upload_file"
Cohesion: 0.25
Nodes (20): _default_file_metadata(), delete_file_record(), _delete_stored_file_locked(), download_file(), download_protected_file(), _file_metadata_locked(), human_file_record(), list_files() (+12 more)

### Community 20 - "ModuleContext"
Cohesion: 0.06
Nodes (40): HttpMiddleware, LifecycleHook, build_application(), configured_modules(), ApplicationHandler, Starlette application bootstrap and module composition., Return built-in modules paired with their resolved enabled state., Build a Starlette application from enabled module registrations. (+32 more)

### Community 21 - "Project Architecture"
Cohesion: 0.12
Nodes (16): Application bootstrap and module registration, Browser routing, Cleanup worker, Client presence, Clipboard lifecycle, File lifecycle, Frontend update model, Goals (+8 more)

### Community 22 - "⚡ Features"
Cohesion: 0.29
Nodes (7): 📱 Browser-native clients, ⚡ Features, 📁 LAN-speed file sharing, ⏳ Lifecycle controls, 🪶 Lightweight core, 🔐 Optional protection, 📋 Shared clipboard

### Community 23 - "ContentProcessor"
Cohesion: 0.12
Nodes (10): ContentProcessor, ProcessorContext, ProcessorRegistry, ABC, Versioned content-processor contracts and deterministic execution results., Optional post-storage transformation or analysis contract., Stable registry name., Implementation version persisted with every execution result. (+2 more)

### Community 25 - "🚀 Installation"
Cohesion: 0.50
Nodes (4): Install on Fedora, Ubuntu, or macOS, Install on Windows, 🚀 Installation, Run from the source tree

### Community 26 - "NightWire Documentation"
Cohesion: 0.67
Nodes (3): Documentation conventions, Guides, NightWire Documentation

### Community 27 - "app.py"
Cohesion: 0.13
Nodes (23): _apply_item_settings(), cleanup_expired_items(), _cleanup_worker(), current_security_pipeline(), current_storage_backend(), current_transfer_service(), _download_headers(), _expires_at_from_seconds() (+15 more)

### Community 28 - "ObjectId"
Cohesion: 0.12
Nodes (6): ObjectId, Open a permanent object by logical ID., Atomically persist JSON-compatible metadata for an object., Load an object's persisted metadata when present., Stable logical identity for one permanently stored object., LocalFilesystemStorageTests

### Community 29 - "CoreTransferService"
Cohesion: 0.15
Nodes (9): CompletedUpload, CoreTransferService, chunks(), PendingUpload, Final transfer facts associated with a stable object ID., Promote one pending upload into permanent storage., Core streaming implementation backed by a logical StorageBackend., A fully streamed upload that has not entered permanent storage. (+1 more)

### Community 30 - "TemporaryUploadId"
Cohesion: 0.13
Nodes (7): Atomically promote a temporary upload to permanent object storage., Map a validated upload ID to its isolated physical reference., Logical identity for an isolated, not-yet-finalized upload., Backend-neutral facts returned after an object is finalized., Open a previously allocated temporary upload., StoredObject, TemporaryUploadId

### Community 31 - "LocalFilesystemStorage"
Cohesion: 0.24
Nodes (6): LocalFilesystemStorage, Any, Path, Object-ID storage rooted inside the existing NightWire files directory., Map a validated object ID to its opaque physical reference., Map a validated object ID to its internal metadata sidecar.

### Community 32 - "test_app.py"
Cohesion: 0.15
Nodes (7): create_password_record(), verify_password(), CleanupWorkerTests, FileLifecycleTests, immediate_run_sync(), PasswordTests, Run the cleanup join inline so Python 3.14 does not retain an AnyIO worker.

### Community 33 - "test_core_services.py"
Cohesion: 0.21
Nodes (15): AllowAllCapacityPolicy, CapacityDecision, CapacityMeter, CapacityPolicy, CapacityRequest, CapacitySnapshot, ABC, Capacity and quota policy contracts for storage-backed modules. (+7 more)

### Community 34 - "core/__init__.py"
Cohesion: 0.19
Nodes (12): Shared configuration, lifecycle, and infrastructure primitives., CoreLifecycleService, LifecycleItem, LifecycleService, LifecycleSweep, ABC, Core lifecycle decisions and temporary-upload housekeeping., Backend-neutral lifecycle facts for one logical item. (+4 more)

### Community 35 - "normalize_optional_password"
Cohesion: 0.40
Nodes (5): decode_optional_password_header(), normalize_optional_password(), normalize_password(), Return an optional creation-time password; empty values mean unprotected., Decode a UTF-8 password transported in a base64 request header.

### Community 36 - "share_clipboard"
Cohesion: 0.26
Nodes (10): active_device_records(), clean_text(), client_heartbeat(), normalize_client_ip(), parse_user_agent(), purge_inactive_clients(), Return a compact device/browser summary without adding a parser dependency., share_clipboard() (+2 more)

### Community 37 - "Files"
Cohesion: 0.40
Nodes (5): Auto-delete behavior, Download and deletion, Files, Password behavior, Upload a file

### Community 38 - "test_dependency_boundaries.py"
Cohesion: 0.60
Nodes (3): FeatureDependencyBoundaryTests, _internal_module_names(), _resolved_import()

### Community 39 - "StorageBackend"
Cohesion: 0.09
Nodes (14): Discard inactive temporary uploads older than the configured threshold., ABC, Logical object storage contracts and the local-filesystem backend., Return unfinished uploads available for orphan cleanup., Return whether an object currently exists., Return an object's current byte length., Remove an object if it exists., Backend-neutral facts about one unfinished upload. (+6 more)

### Community 40 - "processors/__init__.py"
Cohesion: 0.13
Nodes (18): ProcessorExecutionStatus, StrEnum, Versioned processor and sandbox execution contracts., DenySandboxExecutor, ABC, StrEnum, Deny-by-default sandbox execution contracts for sensitive processors., Read-only logical object made available to a sandbox implementation. (+10 more)

### Community 41 - "transfer.py"
Cohesion: 0.14
Nodes (13): DownloadTransfer, ABC, StrEnum, Streaming transfer contracts, progress state, and the Core implementation., Prepared object download with observable progress and streamed chunks., Stream uploads/downloads and finalize content without filesystem paths., Stream chunks into isolated temporary storage and calculate integrity., Discard one pending upload without finalizing it. (+5 more)

### Community 42 - "security.py"
Cohesion: 0.17
Nodes (12): compare_mime_evidence(), detect_mime_signature(), MimeComparison, MimeDetection, normalize_mime(), Any, StrEnum, Content-type evidence, security verdicts, and scanner-neutral inspection. (+4 more)

### Community 43 - "CoreSecurityTests"
Cohesion: 0.22
Nodes (7): CoreSecurityPipeline, MalwareScannerAdapter, ABC, Scanner contract addressed by object identity, never a caller path., Stable scanner implementation name., SecurityPipeline, CoreSecurityTests

### Community 44 - "ProcessorIdentity"
Cohesion: 0.22
Nodes (4): DerivedObject, ProcessorIdentity, A stored object produced from another object by a processor., ProcessorExecutionResultTests

### Community 46 - "ProcessorExecutionResult"
Cohesion: 0.20
Nodes (4): ProcessorExecutionResult, Any, Process content without assuming a local filesystem path., Compatibility projection for callers that previously read a name string.

### Community 47 - "TransferProgressStore"
Cohesion: 0.28
Nodes (4): Immutable progress event suitable for modules or a future API projection., Thread-safe bounded state containing the latest event per transfer., TransferProgress, TransferProgressStore

### Community 48 - "_Scanner"
Cohesion: 0.33
Nodes (3): MalwareScanResult, Inspect a stored object and return a normalized scanner result., _Scanner

## Knowledge Gaps
- **145 isolated node(s):** `nightwire`, `run.sh script`, `PORT`, `state`, `elements` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 339 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ObjectId` connect `ObjectId` to `core/__init__.py`, `StorageBackend`, `processors/__init__.py`, `transfer.py`, `security.py`, `CoreSecurityTests`, `ProcessorIdentity`, `CoreTransferServiceTests`, `TransferProgressStore`, `_Scanner`, `upload_file`, `ContentProcessor`, `app.py`, `CoreTransferService`, `TemporaryUploadId`, `LocalFilesystemStorage`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **Why does `LocalFilesystemStorage` connect `LocalFilesystemStorage` to `test_core_services.py`, `core/__init__.py`, `StorageBackend`, `processors/__init__.py`, `transfer.py`, `CoreSecurityTests`, `CoreTransferServiceTests`, `ContentProcessor`, `app.py`, `ObjectId`, `CoreTransferService`, `TemporaryUploadId`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `StorageBackend` connect `StorageBackend` to `core/__init__.py`, `processors/__init__.py`, `transfer.py`, `security.py`, `CoreSecurityTests`, `_Scanner`, `ContentProcessor`, `ObjectId`, `CoreTransferService`, `TemporaryUploadId`, `LocalFilesystemStorage`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `ObjectId` (e.g. with `_load_file_metadata()` and `_metadata_object_id()`) actually correct?**
  _`ObjectId` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `StorageBackend` (e.g. with `CoreLifecycleService` and `LifecycleService`) actually correct?**
  _`StorageBackend` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `LocalFilesystemStorage` (e.g. with `current_security_pipeline()` and `current_transfer_service()`) actually correct?**
  _`LocalFilesystemStorage` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `TemporaryUploadId` (e.g. with `CoreLifecycleService` and `LifecycleService`) actually correct?**
  _`TemporaryUploadId` has 6 INFERRED edges - model-reasoned connections that need verification._