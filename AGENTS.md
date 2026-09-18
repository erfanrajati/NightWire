# NightWire Project Context

This file is persistent product and implementation guidance for coding agents working in this repository.

## Product source of truth

- The canonical product specification is the Notion page [NightWire Product Proposal](https://app.notion.com/p/3db2babe17108124a724d5e7cb4df937), under [NightWire Progress](https://app.notion.com/p/3da2babe17108158b4dbc17a0cf62755).
- Before implementing any task, fetch and read the current proposal and the task's current entry in NightWire Progress. This local summary was last refreshed from Notion on 2026-09-18 and is a fallback, not a substitute for checking the current pages.
- Precedence is: the user's current task instructions, then the task entry in NightWire Progress where it narrows or updates the proposal, then the current Product Proposal, then repository documentation and existing behavior.
- Preserve existing behavior unless the task explicitly changes it. Inspect the repository before designing, add or update focused tests, keep the existing suite passing, and do not implement unrelated later roadmap work opportunistically.
- Repository documentation describes the implementation as it exists and may lag the product direction. Do not use an older README statement to override the proposal.

## Product definition

NightWire is a private storage, sharing, and file-utility platform that combines:

- **Drop:** lightweight anonymous temporary file, text, and voice sharing. Keep its experience simple: upload, share, download, disappear.
- **Library:** authenticated persistent personal and Workspace storage with recursive folders, Trash, quotas, history, versions, search, and controlled external sharing.
- **Core:** the common trusted data plane for transfer, physical storage, object identity, security inspection, lifecycle, quotas, the general toolkit, and public processing/extension contracts.
- **Text:** a shared capability for plain text, Markdown, and code, usable from Drop and Library. It is not a full office-document editor.

Evolve the existing Starlette application incrementally as a modular monolith. Do not rewrite working behavior from scratch or introduce microservices, internal HTTP calls, service discovery, per-module databases, or message brokers unless a future approved specification changes that direction.

## Public Community scope and paid boundary

This repository is **NightWire Community**, the independently deployable public/open-source foundation. It must run on LANs, private or air-gapped networks, VPSs, and cloud servers without a private repository or NightWire-operated service.

The governing boundary is:

> Community manages files. Paid NightWire understands file types.

Community owns general, format-agnostic capabilities: transfer and storage, security status and rescanning, Drop and Library fundamentals, authentication, Personal Library, supported Workspaces and shares, lifecycle and quotas, versions, Trash, file operations, checksums, generic compression and estimation, safe generic Clean Copy behavior, safe previews, and the public processor/toolkit/extension contracts.

File-type-specific processing belongs in the separate private `nightwire-enterprise` extension repository. Do not add proprietary processors, licensing or activation, paid UI placeholders, or scattered `is_enterprise` checks here. Examples outside Community include image crop/resize/conversion and EXIF tools, document extraction or document-specific sanitation, audio/video transcoding, speech-to-text, advanced media metadata, and advanced archive inspection/extraction. Paid modules must eventually register through stable public contracts rather than reach arbitrarily into Community internals.

Safe recognition or browser preview of a content type is not the same as specialized processing and may remain in Community.

## Required domain semantics

### Drop

- Anonymous Drop does not require an account.
- Default lifetime is one hour. Anonymous internet-facing Drop lifetime is capped at one day.
- Expiration removes access, metadata, and the actual stored bytes.
- Access Keys are reusable for repeated and concurrent access until the share expires or is revoked. They are not single-use credentials. A QR code is only a representation of the URL/key; it is not device pairing.
- Trusted-network deployments may explicitly relax selected Drop restrictions. Public deployments must never inherit those relaxations silently.

### Library and Workspaces

- Library is persistent and authenticated. Each user has a private recursive Personal Library.
- Community permits at most **one Workspace association per user**, whether the user created or joined it. Enforce this server-side through a policy/capability boundary that a future paid module can replace; do not implement the paid override here.
- Personal deletions go to personal Trash. Workspace deletions go to that Workspace's Trash. Permanent deletion removes relevant stored versions according to retention policy.
- Versions represent states of the same file and enable inspection, restoration, and reversible transformations.
- A transformation producing a different content type creates a derived object with source and operation provenance.
- Do not silently deduplicate. Warn on relevant checksum or filename matches and let the user choose whether to proceed.
- Initial search is fuzzy recursive filename search scoped to the user's available Personal Library or Workspace storage; full document-content indexing is not initially required.

### Sharing

- A Library share is a read-only Share Grant to an existing Library object, not a duplicate or temporary relocation.
- Expiring or revoking a Library share removes access only; it does not delete the Library object.
- Library share Access Keys are reusable until expiration or revocation. Workspaces, not public share links, provide collaborative mutation.
- Drop and Library lifecycles are deliberately different. Drop is not "Library with a TTL."

## Core storage, transfer, security, and capacity rules

- Core alone owns physical storage. Modules use logical objects and stable internal IDs, never user filenames as physical identifiers and never arbitrary filesystem paths.
- Stream large uploads and downloads; use isolated temporary uploads, checksums, controlled/atomic finalization, and bounded resource use. Failed work must not appear finalized.
- One configured storage root/backend is the initial model. SQLite is the default Library database, while large content remains in storage rather than database blobs.
- Every uploaded object is untrusted. Derive content identity from stored bytes; client-declared MIME is not authoritative.
- Preserve the verdict vocabulary: `clean`, `suspicious`, `malicious`, `scan_failed`, and `unscanned`.
- A malicious verdict does not auto-delete an object. Opaque storage may continue; deliberate confirmation is required to download it, and risky processing is centrally denied.
- Files are data, not executable content. Uploaded content and processors must not gain application secrets, unrelated storage, application-code mutation, uncontrolled processes, or network access.
- Internet-facing security-sensitive processing must use constrained workers or equivalent sandboxes with explicit filesystem, network, CPU, memory, time, process, file-count, and output limits. Do not silently fall back to unsafe in-process parsing.
- Capacity policy may include installation, Library, Workspace, Drop, object-size, and minimum-free-disk limits. Drop must never consume the host's final available disk space.

## Toolkit and extension behavior

- Discover applicable actions from public registries; do not hard-code every edition capability into routes or the frontend.
- Community actions are present when supported. Unsupported paid actions are absent, not fake locked controls or upsell placeholders.
- Use version results when an operation creates another state of the same file. Use derived objects when it creates a different content type.
- Generic Community Clean Copy is non-destructive and must report exactly what it sanitized. Never imply that embedded format-specific metadata was removed when Community did not parse it.
- Archive creation can be Community functionality, but advanced archive exploration/extraction is paid. Any extraction implementation must defend against traversal, absolute paths, links, special files, decompression bombs, excessive nesting/file counts, and resource exhaustion.

## Deployment and UI direction

- Core is always installed; supported Community packaging may enable Drop only, Library only, or both. Disabled modules must not expose routes or navigation.
- Internet-facing deployments use explicit hardened/containerized policy. Trusted-network conveniences are opt-in and remain distinct. Community normal operation must not require an external NightWire service.
- Keep one cohesive browser-first, responsive, installable PWA shell. It should discover installed modules/capabilities and must not imply offline filesystem synchronization.
- Preserve Drop's minimal UX. Library's primary surfaces include My Library, Workspaces, folder browsing, filename search, file details, versions, shares, Trash, and storage usage.
- File detail may expose Preview, Properties/Metadata, Security, Versions, Derived Outputs, Toolkit, and Sharing according to installed capabilities.

## Current non-goals and undecided policy

Do not assume or opportunistically implement desktop/offline synchronization, office-suite editing, professional media editing, Community backup orchestration, microservices, multiple simultaneous storage roots, automatic OCR fallback, or mandatory external cloud services.

The proposal intentionally leaves several policies undecided, including detailed Workspace roles, registration defaults, Trash/version retention defaults, exact hosted limits, supported external databases, processor implementations, and future organization identity/admin/audit features. When a task depends materially on one of these, follow an explicit task decision or ask rather than inventing product policy.
