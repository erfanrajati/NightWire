# Graph Report - NightWire  (2026-09-14)

## Corpus Check
- 56 files · ~42,640 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 3, .zip 1, .bat 1)

## Summary
- 1087 nodes · 2342 edges · 66 communities (55 shown, 8 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 223 edges (avg confidence: 0.9)
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
- HTTP API Reference
- Contributing to NightWire
- NightWire v1.0.2 Architecture Inventory
- Using NightWire
- Security Model
- install.sh
- config.py
- update-existing.sh
- Path
- run.sh
- asgi_request
- nightwire
- Troubleshooting
- drop.js
- ApplicationRegistry
- Project Architecture
- ⚡ Features
- ContentProcessor
- text/__init__.py
- 🚀 Installation
- service.py
- DropItem
- LocalFilesystemStorageTests
- CoreTransferService
- TemporaryUploadId
- ObjectId
- test_app.py
- test_core_services.py
- StorageBackend
- runtime.py
- DropClipboardService
- _ImmediateAsyncFile
- test_dependency_boundaries.py
- PasswordDigest
- processors/__init__.py
- security.py
- CoreSecurityPipeline
- drop-share.js
- IsolatedApplicationState
- CoreTransferServiceTests
- test_drop.py
- core/__init__.py
- CoreLifecycleService
- DropRepository
- test_characterization.py
- DropService
- share_clipboard
- json_request
- LinuxInstallUpdateSmokeTests
- ModuleContext
- _Scanner
- test_bootstrap.py
- build_application
- load_port
- .test_enabled_module_can_register_routes_and_lifecycle_hooks
- Files
- _ImmediateAsyncFile
- ClipboardCharacterizationTests
- NightWire Documentation

## God Nodes (most connected - your core abstractions)
1. `ObjectId` - 70 edges
2. `StorageBackend` - 44 edges
3. `LocalFilesystemStorage` - 44 edges
4. `DropService` - 40 edges
5. `DropItem` - 32 edges
6. `TemporaryUploadId` - 31 edges
7. `bindEvents()` - 30 edges
8. `asgi_request()` - 29 edges
9. `CoreTransferService` - 25 edges
10. `LocalDropRepository` - 24 edges

## Surprising Connections (you probably didn't know these)
- `DropServiceTests` --uses--> `PasswordProtection`  [INFERRED]
  tests/test_drop.py → nightwire/app/passwords.py
- `ModuleRegistrationContractTests` --uses--> `ModuleContext`  [INFERRED]
  tests/test_bootstrap.py → nightwire/app/registration.py
- `ModuleRegistrationContractTests` --uses--> `ApplicationRegistry`  [INFERRED]
  tests/test_bootstrap.py → nightwire/app/registration.py
- `DropServiceTests` --uses--> `DeploymentProfile`  [INFERRED]
  tests/test_drop.py → nightwire/core/config.py
- `RefactoredApplicationEndToEndTests` --uses--> `DeploymentProfile`  [INFERRED]
  tests/test_e2e_regression.py → nightwire/core/config.py

## Import Cycles
- None detected.

## Communities (66 total, 8 thin omitted)

### Community 0 - "Request"
Cohesion: 0.14
Nodes (34): JSONResponse, Request, clear_clipboard(), current_drop_service(), delete_clipboard(), delete_file(), delete_file_record(), download_file() (+26 more)

### Community 1 - "Configuration Reference"
Cohesion: 0.17
Nodes (12): Configuration Reference, Deployment profiles, Fixed application limits, Installed launcher, Installed modules, Installer variables, Network behavior, Preserved paths during update (+4 more)

### Community 2 - "README.md"
Cohesion: 0.16
Nodes (10): 🤝 Contributing, 🛠 Development, 📚 Documentation, 📄 License, ✨ Overview, 🧱 Project structure, 📦 Requirements, 🔒 Security model (+2 more)

### Community 3 - "Any"
Cohesion: 0.11
Nodes (22): active_device_records(), add_clipboard_entry(), _apply_item_settings(), _clipboard_entry_locked(), clipboard_snapshot(), _expires_at_from_seconds(), normalize_clipboard_expiry(), normalize_clipboard_text() (+14 more)

### Community 5 - "HTTP API Reference"
Cohesion: 0.07
Nodes (29): Clients, Clipboard, Common error shape, `DELETE /api/clipboard`, `DELETE /api/clipboard/{entry_id}`, `DELETE /api/files/{filename}`, Drop creation and browsing, Files (+21 more)

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
Cohesion: 0.12
Nodes (16): Clipboard protections and limitations, Deployment recommendations, Drop Access Keys, File handling protections, HTTP response headers, Intended deployment, Lost passwords, Password protection (+8 more)

### Community 10 - "install.sh"
Cohesion: 0.43
Nodes (5): as_admin(), as_install_user(), install.sh script, fail(), find_uv()

### Community 11 - "config.py"
Cohesion: 0.10
Nodes (17): Enum, ApplicationConfig, DeploymentProfile, InstalledModules, load_application_config(), _parse_deployment_profile(), _parse_enabled(), Path (+9 more)

### Community 12 - "update-existing.sh"
Cohesion: 0.53
Nodes (4): as_root(), fail(), update-existing.sh script, usage()

### Community 13 - "Path"
Cohesion: 0.17
Nodes (11): _default_file_metadata(), _delete_stored_file_locked(), _file_metadata_locked(), human_file_record(), _metadata_object_id(), metadata_path(), Path, Resolve a user-provided filename and prevent path traversal. (+3 more)

### Community 15 - "asgi_request"
Cohesion: 0.23
Nodes (3): asgi_request(), FileUploadCharacterizationTests, RefactoredApplicationEndToEndTests

### Community 18 - "Troubleshooting"
Cohesion: 0.12
Nodes (17): A Drop share link was lost, A partial upload file appears, A password was forgotten, Another device cannot connect, Clipboard items disappeared after restart, Clipboard watching is unavailable, Countdown did not delete an item, File metadata problems (+9 more)

### Community 19 - "drop.js"
Cohesion: 0.08
Nodes (75): acceptCreatedDrop(), actionButton(), api(), askPassword(), bindEvents(), clipboardPreview(), clipboardShareSettings(), closePasswordModal() (+67 more)

### Community 20 - "ApplicationRegistry"
Cohesion: 0.10
Nodes (18): LifecycleHook, configured_modules(), Starlette application bootstrap and module composition., Return built-in modules paired with their resolved enabled state., Application composition package with cycle-safe lazy compatibility exports., ApplicationRegistry, Any, Contracts used by NightWire modules during application composition. (+10 more)

### Community 21 - "Project Architecture"
Cohesion: 0.12
Nodes (16): Application bootstrap and module registration, Browser routing, Cleanup worker, Client presence, Clipboard lifecycle, File lifecycle, Frontend update model, Goals (+8 more)

### Community 22 - "⚡ Features"
Cohesion: 0.29
Nodes (7): 📱 Browser-native clients, ⚡ Features, 📁 LAN-speed file sharing, ⏳ Lifecycle controls, 🪶 Lightweight core, 🔐 Private share access, 📋 Shared clipboard

### Community 23 - "ContentProcessor"
Cohesion: 0.10
Nodes (11): ContentProcessor, ProcessorContext, ProcessorRegistry, ABC, Optional post-storage transformation or analysis contract., Stable registry name., Implementation version persisted with every execution result., Return whether this processor accepts the stored content. (+3 more)

### Community 25 - "🚀 Installation"
Cohesion: 0.50
Nodes (4): Install on Fedora, Ubuntu, or macOS, Install on Windows, 🚀 Installation, Run from the source tree

### Community 26 - "service.py"
Cohesion: 0.16
Nodes (11): DropAccessKeyPolicy, Generation and verification of bearer Access Keys for Drop shares., Create high-entropy URL-safe keys while persisting only salted digests., AccessKeyDigest, DropDownload, DropUpload, Drop domain types independent of HTTP routes and legacy dictionaries., Non-recoverable verifier for a Drop bearer Access Key. (+3 more)

### Community 27 - "DropItem"
Cohesion: 0.13
Nodes (8): DropItem, Any, One logical ephemeral file shared through Drop., LocalDropRepository, Any, Path, Filename-keyed JSON metadata retained for upgrade compatibility., DropDomainRepositoryTests

### Community 29 - "CoreTransferService"
Cohesion: 0.12
Nodes (11): CompletedUpload, CoreTransferService, chunks(), PendingUpload, Final transfer facts associated with a stable object ID., Stream chunks into isolated temporary storage and calculate integrity., Promote one pending upload into permanent storage., Discard one pending upload without finalizing it. (+3 more)

### Community 30 - "TemporaryUploadId"
Cohesion: 0.09
Nodes (12): Return unfinished uploads available for orphan cleanup., Atomically promote a temporary upload to permanent object storage., Logical identity for an isolated, not-yet-finalized upload., Backend-neutral facts returned after an object is finalized., Backend-neutral facts about one unfinished upload., Reserve an isolated temporary upload and return its logical ID., Open a previously allocated temporary upload., Return whether a temporary upload currently exists. (+4 more)

### Community 31 - "ObjectId"
Cohesion: 0.11
Nodes (12): LocalFilesystemStorage, ObjectId, Any, Path, Open a permanent object by logical ID., Atomically persist JSON-compatible metadata for an object., Load an object's persisted metadata when present., Object-ID storage rooted inside the existing NightWire files directory. (+4 more)

### Community 32 - "test_app.py"
Cohesion: 0.14
Nodes (7): create_password_record(), update_file_settings(), CleanupWorkerTests, FileLifecycleTests, immediate_run_sync(), PasswordTests, Run the cleanup join inline so Python 3.14 does not retain an AnyIO worker.

### Community 33 - "test_core_services.py"
Cohesion: 0.23
Nodes (14): AllowAllCapacityPolicy, CapacityDecision, CapacityMeter, CapacityPolicy, CapacityRequest, CapacitySnapshot, ABC, Capacity and quota policy contracts for storage-backed modules. (+6 more)

### Community 34 - "StorageBackend"
Cohesion: 0.12
Nodes (9): Discard inactive temporary uploads older than the configured threshold., ABC, Return whether an object currently exists., Return an object's current byte length., Return an object's modification timestamp., Remove an object if it exists., Storage operations addressed only by logical object/upload IDs., StorageBackend (+1 more)

### Community 35 - "runtime.py"
Cohesion: 0.12
Nodes (26): cleanup_expired_items(), _cleanup_worker(), clear_clipboard_entries(), current_security_pipeline(), current_storage_backend(), current_transfer_service(), delete_clipboard_entry(), _download_headers() (+18 more)

### Community 36 - "DropClipboardService"
Cohesion: 0.15
Nodes (5): DropClientVisibilityService, DropClipboardService, Any, RLock, Temporary Drop-facing facades for clipboard and client-presence behavior.

### Community 38 - "test_dependency_boundaries.py"
Cohesion: 0.60
Nodes (3): FeatureDependencyBoundaryTests, _internal_module_names(), _resolved_import()

### Community 39 - "PasswordDigest"
Cohesion: 0.17
Nodes (7): PasswordProtection, Configured password protection and HTTP creation-password middleware., decode_optional_password_header(), Decode a UTF-8 password transported in a base64 request header., PasswordDigest, Backend-neutral password verifier data; plaintext is never retained., PasswordProtectionContract

### Community 40 - "processors/__init__.py"
Cohesion: 0.08
Nodes (26): DerivedObject, ProcessorExecutionResult, ProcessorExecutionStatus, ProcessorIdentity, Any, StrEnum, Versioned content-processor contracts and deterministic execution results., A stored object produced from another object by a processor. (+18 more)

### Community 41 - "security.py"
Cohesion: 0.17
Nodes (12): compare_mime_evidence(), detect_mime_signature(), MimeComparison, MimeDetection, normalize_mime(), Any, StrEnum, Content-type evidence, security verdicts, and scanner-neutral inspection. (+4 more)

### Community 42 - "CoreSecurityPipeline"
Cohesion: 0.25
Nodes (7): CoreSecurityPipeline, MalwareScannerAdapter, ABC, Scanner contract addressed by object identity, never a caller path., Stable scanner implementation name., SecurityPipeline, CoreSecurityTests

### Community 43 - "drop-share.js"
Cohesion: 0.36
Nodes (9): downloadDrop(), elements, filename, formatBytes(), formatDate(), loadDrop(), presentDropBlob(), saveBlob() (+1 more)

### Community 44 - "IsolatedApplicationState"
Cohesion: 0.19
Nodes (3): FileDownloadCharacterizationTests, IsolatedApplicationState, LifecycleCharacterizationTests

### Community 45 - "CoreTransferServiceTests"
Cohesion: 0.14
Nodes (3): CoreTransferServiceTests, _immediate_open_file(), _ImmediateAsyncFile

### Community 46 - "test_drop.py"
Cohesion: 0.14
Nodes (3): DropServiceTests, _immediate_open_file(), _ImmediateAsyncFile

### Community 47 - "core/__init__.py"
Cohesion: 0.11
Nodes (17): Shared configuration, lifecycle, and infrastructure primitives., Logical object storage contracts and the local-filesystem backend., DownloadTransfer, ABC, StrEnum, Streaming transfer contracts, progress state, and the Core implementation., Prepared object download with observable progress and streamed chunks., Stream uploads/downloads and finalize content without filesystem paths. (+9 more)

### Community 48 - "CoreLifecycleService"
Cohesion: 0.24
Nodes (8): CoreLifecycleService, LifecycleService, LifecycleSweep, ABC, Core lifecycle decisions and temporary-upload housekeeping., Classification returned by a lifecycle sweep., Decide item expiration and reclaim abandoned temporary uploads., CoreLifecycleTests

### Community 49 - "DropRepository"
Cohesion: 0.11
Nodes (11): _load_file_metadata(), _save_file_metadata_locked(), DropRepository, ABC, Drop metadata repository contract and lightweight local JSON backend., Load durable Drop metadata into the repository., Return one logical Drop item., Return all persisted Drop items. (+3 more)

### Community 50 - "test_characterization.py"
Cohesion: 0.21
Nodes (6): Compatibility import and executable entry point for NightWire., _asgi_request_async(), _CapturedResponse, _immediate_open_file(), _immediate_run_sync(), CompatibilityEntryPointTests

### Community 51 - "DropService"
Cohesion: 0.22
Nodes (3): DropService, Path, Commit byte/credential/metadata removal as one locked Drop transition.

### Community 52 - "share_clipboard"
Cohesion: 0.23
Nodes (10): clean_text(), client_heartbeat(), normalize_client_ip(), normalize_optional_password(), parse_user_agent(), Return an optional creation-time password; empty values mean unprotected., Return a compact device/browser summary without adding a parser dependency., share_clipboard() (+2 more)

### Community 53 - "json_request"
Cohesion: 0.31
Nodes (3): ClientVisibilityCharacterizationTests, json_request(), PasswordProtectionCharacterizationTests

### Community 55 - "ModuleContext"
Cohesion: 0.20
Nodes (7): ApplicationModule, ModuleContext, ApplicationHandler, Protocol, Configuration and legacy handlers available during registration., A module capable of contributing routes and lifecycle hooks., RequestHandler

### Community 56 - "_Scanner"
Cohesion: 0.33
Nodes (3): MalwareScanResult, Inspect a stored object and return a normalized scanner result., _Scanner

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

### Community 61 - "Files"
Cohesion: 0.33
Nodes (6): Auto-delete behavior, Download and deletion, Files, Password behavior, Share temporary text or voice, Upload a file

### Community 65 - "NightWire Documentation"
Cohesion: 0.67
Nodes (3): Documentation conventions, Guides, NightWire Documentation

## Knowledge Gaps
- **154 isolated node(s):** `nightwire`, `run.sh script`, `PORT`, `elements`, `filename` (+149 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 405 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ObjectId` connect `ObjectId` to `StorageBackend`, `runtime.py`, `processors/__init__.py`, `security.py`, `CoreSecurityPipeline`, `Path`, `CoreTransferServiceTests`, `core/__init__.py`, `DropRepository`, `ContentProcessor`, `_Scanner`, `service.py`, `DropItem`, `LocalFilesystemStorageTests`, `CoreTransferService`, `TemporaryUploadId`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Why does `LocalFilesystemStorage` connect `ObjectId` to `test_core_services.py`, `StorageBackend`, `runtime.py`, `PasswordDigest`, `processors/__init__.py`, `CoreSecurityPipeline`, `CoreTransferServiceTests`, `test_drop.py`, `core/__init__.py`, `CoreLifecycleService`, `ContentProcessor`, `LocalFilesystemStorageTests`, `CoreTransferService`, `TemporaryUploadId`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `StorageBackend` connect `StorageBackend` to `processors/__init__.py`, `security.py`, `CoreSecurityPipeline`, `core/__init__.py`, `CoreLifecycleService`, `DropService`, `ContentProcessor`, `_Scanner`, `service.py`, `CoreTransferService`, `TemporaryUploadId`, `ObjectId`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `ObjectId` (e.g. with `_metadata_object_id()` and `_object_download_response()`) actually correct?**
  _`ObjectId` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `StorageBackend` (e.g. with `CoreLifecycleService` and `LifecycleService`) actually correct?**
  _`StorageBackend` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `LocalFilesystemStorage` (e.g. with `current_security_pipeline()` and `current_transfer_service()`) actually correct?**
  _`LocalFilesystemStorage` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `DropService` (e.g. with `_drop_upload_response()` and `DeploymentProfile`) actually correct?**
  _`DropService` has 12 INFERRED edges - model-reasoned connections that need verification._