# Security Model

## Intended deployment

NightWire is intended for devices on a **trusted local network**. It does not include user accounts, server-wide login, per-client permissions, approval queues, or client blocking.

Do not expose NightWire directly to the public internet.

## Trust boundaries

A device that can reach the NightWire port can generally:

- list shared files and their metadata;
- upload unprotected or protected files;
- share clipboard entries;
- view connected-device information;
- change the auto-delete countdown of any file or clipboard entry;
- download or delete unprotected items;
- attempt to unlock or delete protected items.

Access Keys limit new Drop downloads, and optional passwords add a second check. They do not turn an untrusted network into a fully isolated multi-user system.

## Drop Access Keys

Every new Drop receives a 256-bit random URL-safe bearer key. The raw key is returned once in the complete `/drop/{filename}?key=...` share URL. NightWire persists only a randomly salted, domain-separated SHA-256 verifier and uses constant-time comparison during validation.

The complete URL grants access until the Drop expires or is deleted. Treat it like a secret: it can appear in browser history, copied messages, proxy logs, or screenshots. NightWire sends `Referrer-Policy: no-referrer`, disables its Uvicorn access log, and does not persist the raw key in server metadata or browser storage.

Access Key validation protects recipient metadata and downloads. The existing manager list, countdown update, and deletion surfaces remain installation-level controls rather than per-user authorization.

On explicitly trusted/private deployments, `NIGHTWIRE_TRUSTED_RELAX_ACCESS_KEYS=true` permits keyless recipient metadata and downloads. This intentionally reduces authorization: anyone who can reach the service and determine a logical Drop name can access it. A raw key is still issued for share-link compatibility. Internet-facing policy ignores this relaxation and always enforces keys.

Active-Drop discovery is configured by `NIGHTWIRE_TRUSTED_ACTIVE_DROP_BROWSING`, but becomes effective only alongside trusted key relaxation. This guarantees that every visible active row has a durable, actionable keyless link and download. The active `/api/drops` API and compatibility file listing return `403` otherwise. Internet-facing installations cannot enable either relaxation through configuration.

Share QR codes contain the exact bearer share URL. They are another representation of the credential, not device pairing or approval. Protect screenshots and printed codes like the copied URL.

## Password protection

Passwords are optional and must be selected when a file is uploaded or clipboard text is shared.

Password length, digest creation, verification, and authorization are centralized in configured application policy. Upload-header decoding runs in middleware; Drop routes receive normalized creation context and delegate authorization to `DropService`. This changes ownership without changing v1.0.2 password semantics.

After creation, the public API permits only countdown changes. It does not permit a password to be added, changed, or removed.

### Stored password data

NightWire stores a password verifier containing:

- a random 16-byte salt;
- a 32-byte digest generated with `scrypt`;
- parameters `N=2^14`, `r=8`, and `p=1`.

The plaintext password is not written to the file metadata. Verification uses constant-time comparison.

### Protection scope

For files, the password is required to download or delete the item through NightWire. The file itself remains readable in the server's shared directory by operating-system users with filesystem access.

For clipboard entries, protected plaintext is omitted from list/synchronization responses. The password is required to retrieve the text or delete the entry.

Password protection is not encryption at rest and is not end-to-end encryption.

## Transport security

NightWire serves HTTP by default. On an unencrypted LAN connection:

- file contents can be observed by an attacker able to intercept traffic;
- clipboard contents can be observed while sharing or unlocking;
- passwords can be observed in request traffic;
- device and filename metadata can be observed.

Base64 used for the upload password header is transport encoding, not encryption.

Use a trusted network. When traffic confidentiality is required, place NightWire behind a correctly configured HTTPS reverse proxy and restrict access at the network or proxy layer.

## Retention controls

Any connected client may change an item's countdown without its password. A new Drop must retain a positive expiry and cannot exceed its deployment-profile limit.

Therefore:

- auto-delete is not an access-control mechanism;
- a password does not protect the countdown setting;
- users should manually delete sensitive content when finished;
- operators should not assume a short initial countdown cannot be extended within the configured limit.

Protected deletion still requires the password.

## File handling protections

NightWire implements several file-safety measures:

- logical filenames are validated as single basenames, while permanent content is stored under random opaque object IDs;
- object and temporary IDs accept only fixed-length lowercase hexadecimal values and are mapped inside dedicated storage roots;
- path traversal, internal directory names, and the internal metadata filename are rejected;
- uploads use isolated files under `.nightwire-uploads/`;
- successful uploads are committed into `.nightwire-objects/` with an atomic rename after the stream completes;
- SHA-256 is calculated during streaming and persisted as integrity metadata;
- MIME is detected from stored signatures/content rather than trusted from the browser;
- extension, browser-declared MIME, and detected MIME disagreements produce a persisted `suspicious` verdict;
- configured scanners run after finalization and persist their identity, engine version, signature-set metadata, findings, and inspection time;
- per-object security results are stored under `.nightwire-object-metadata/` and mirrored into logical file metadata;
- incomplete temporary uploads are removed after client disconnects or errors;
- inactive temporary uploads older than 24 hours are reclaimed unless the transfer service still marks them active;
- protected existing files cannot be overwritten by another upload with the same name;
- downloads use `application/octet-stream` and `X-Content-Type-Options: nosniff`.

An unprotected existing file may be replaced by a new upload with the same name. Treat shared filenames as mutable unless they are protected.

The normalized model supports `clean`, `suspicious`, `malicious`, `scan_failed`, and `unscanned`. Scanner absence remains `unscanned`, and scanner errors become `scan_failed`; neither is reported as clean. NightWire does not ship a scanner, but a configured `MalwareScannerAdapter` is invoked for every finalized Drop object.

Security enforcement lives in Core policy. All verdicts may remain in opaque storage. Every non-clean state is visibly warned in manager and recipient views. A malicious object cannot enter a risky processor, is never previewed automatically, and can be downloaded only after the recipient deliberately holds the confirmation control; the server independently requires that confirmation. A malicious verdict alone never deletes or rejects the stored bytes.

Security-sensitive content processors must use the sandbox-execution abstraction rather than assuming access to host paths or subprocesses. Sandbox requests use logical object IDs, basename-only input labels, positive resource limits, and no network access by default. The built-in executor is deny-only; no sandboxed program execution is currently enabled.

## Clipboard protections and limitations

- Clipboard history is bounded and memory-only.
- Protected plaintext is not included in public snapshots.
- Clipboard IDs are random UUID-derived values, but they are identifiers rather than secrets.
- Restarting NightWire clears all clipboard entries.
- Clipboard text already viewed by a client cannot be revoked from that client.

## Community Library identity

Library account passwords use salted scrypt hashes; plaintext passwords are never persisted. Session and invitation bearer tokens are generated from cryptographic randomness and only SHA-256 token digests are stored. Session cookies are HttpOnly and SameSite=Strict, and become Secure automatically under the `internet-facing` deployment profile.

The internet-facing registration default is `administrator-approved`; trusted-private defaults to `open`. The first account bootstraps the administrator role. Invitation-only codes are bound to a normalized email, expire after seven days, and can be used once. Logging out revokes the server-side session, so retaining an old cookie does not restore access.

Library cookies do not gate or grant access to Drop. Drop remains an anonymous, access-key-oriented feature with its own protection boundary.

Deploy internet-facing Library installations behind HTTPS. A Secure cookie will not be returned over plain HTTP.

## HTTP response headers

The application sets or defaults these headers:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `X-Frame-Options: DENY`
- a same-origin Content Security Policy with framing disabled
- no-store caching for dynamic API responses and static application assets

These headers reduce common browser risks but do not replace authentication or HTTPS.

## Server and filesystem access

Anyone with operating-system access to the NightWire host may be able to:

- read shared files directly;
- delete or modify files;
- inspect or edit file metadata;
- stop the process and clear clipboard state;
- replace the application code.

Run NightWire under an appropriately restricted account and protect the host itself.

## Deployment recommendations

- Bind access to a trusted private network through firewall rules.
- Avoid guest Wi-Fi and networks with unknown clients.
- Do not port-forward the NightWire port from a router.
- Use a dedicated service account for long-running installations.
- Restrict filesystem permissions on the shared directory.
- Use HTTPS through a trusted reverse proxy when passwords or sensitive content cross a network you do not fully control.
- Back up persistent files independently when they matter.
- Remember that automatic expiration intentionally deletes data and is not a backup strategy.

## Lost passwords

NightWire has no password recovery or reset workflow.

- A protected file remains directly present on the server disk because it is not encrypted. A server operator with filesystem access can retrieve it outside NightWire.
- A protected clipboard entry cannot be unlocked through NightWire without the password. It will disappear when deleted, expired, or when the server restarts.

## Reporting a vulnerability

Do not publish active exploit details in a public issue. Contact the project maintainer privately with:

- the affected version;
- reproduction steps;
- impact and expected behavior;
- logs or a minimal proof of concept that does not expose unrelated private data.

A repository-specific private reporting address or security-advisory process should be added before accepting public security reports.
