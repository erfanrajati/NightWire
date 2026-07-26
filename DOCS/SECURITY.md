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

Password protection limits content access through NightWire, but it does not turn an untrusted LAN into a fully isolated multi-user system.

## Password protection

Passwords are optional and must be selected when a file is uploaded or clipboard text is shared.

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

Any connected client may change an item's countdown without its password. This includes extending retention or setting it to unlimited.

Therefore:

- auto-delete is not an access-control mechanism;
- a password does not protect the countdown setting;
- users should manually delete sensitive content when finished;
- operators should not assume a short initial countdown cannot be extended.

Protected deletion still requires the password.

## File handling protections

NightWire implements several file-safety measures:

- filenames are resolved and required to remain directly inside the configured files directory;
- path traversal and the internal metadata filename are rejected;
- uploads use hidden temporary files;
- successful uploads are committed with an atomic replace;
- incomplete temporary uploads are removed after client disconnects or errors;
- protected existing files cannot be overwritten by another upload with the same name;
- downloads use `application/octet-stream` and `X-Content-Type-Options: nosniff`.

An unprotected existing file may be replaced by a new upload with the same name. Treat shared filenames as mutable unless they are protected.

## Clipboard protections and limitations

- Clipboard history is bounded and memory-only.
- Protected plaintext is not included in public snapshots.
- Clipboard IDs are random UUID-derived values, but they are identifiers rather than secrets.
- Restarting NightWire clears all clipboard entries.
- Clipboard text already viewed by a client cannot be revoked from that client.

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
