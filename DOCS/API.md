# HTTP API Reference

The NightWire browser uses a small JSON and streaming HTTP API. This API is currently an internal interface and does not carry a formal backward-compatibility guarantee.

All paths are relative to the NightWire origin. Dynamic responses use no-store caching.

## Page and static routes

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Redirects to `/files`. |
| `GET` | `/files` | Serves the primary Secure Drop composer. |
| `GET` | `/clipboard` | Serves the browser application on the Clipboard page. |
| `GET` | `/clients` | Serves the browser application on the Clients page. |
| `GET` | `/drop/{filename}?key=ACCESS_KEY` | Validates a Drop Access Key and serves the recipient page. |
| `GET` | `/static/*` | Serves frontend assets. |

## Server information

### `GET /api/info`

Returns version, host information, limits, configured files directory, and detected LAN addresses.

Important fields include:

```json
{
  "version": "1.0.2",
  "hostname": "host-name",
  "directory": "/srv/nightwire/files",
  "chunk_hint": 1048576,
  "client_ttl_seconds": 18,
  "clipboard_max_text_length": 32768,
  "clipboard_history_limit": 40,
  "clipboard_default_expiry_seconds": 600,
  "file_default_expiry_seconds": 3600,
  "drop_max_expiry_seconds": 31536000,
  "drop_access_key_required": true,
  "active_drop_browsing": true,
  "item_min_expiry_seconds": 60,
  "item_max_expiry_seconds": 31536000,
  "password_max_characters": 256,
  "installed_modules": {"drop": true, "library": true},
  "deployment_profile": "trusted-private",
  "network_urls": ["http://192.168.1.29:8080"],
  "primary_network_url": "http://192.168.1.29:8080"
}
```

Drop's enabled state controls whether its route surface is registered at application bootstrap. Library has no routes yet. The deployment profile controls Drop lifetime and visibility policy: `internet-facing` caps anonymous Drops at 86,400 seconds, always enforces Access Keys, and disables active-Drop browsing, but does not itself add TLS, user accounts, or proxy/firewall configuration.

## Drop creation and browsing

### `PUT /api/drops/files?filename=NAME`

The canonical anonymous file-upload endpoint. It accepts the same raw streamed body and creation headers as the compatibility `PUT /api/upload` endpoint. Browser-recorded audio also uses this endpoint with `X-NightWire-Drop-Kind: voice`; all other uploads default to `file`.

### `POST /api/drops/text`

Creates an expiring UTF-8 text Drop through the same Core transfer, checksum, storage, security, and lifecycle pipeline:

```json
{"text": "Temporary text", "expires_in_seconds": 3600, "password": "optional password"}
```

The server assigns a collision-resistant `.txt` logical name. Success is `201 Created` with the same one-time `access_key`, complete `share_url`, public record, checksum, and transfer fields as file upload.

### `GET /api/drops`

Returns active Drops and storage usage only when effective deployment policy permits browsing. Browsing is available only for a `trusted-private` profile with both `NIGHTWIRE_TRUSTED_ACTIVE_DROP_BROWSING=true` and `NIGHTWIRE_TRUSTED_RELAX_ACCESS_KEYS=true`; otherwise this endpoint returns `403`.

Permitted active records include persistent keyless `share_url` and `download_url` values. Raw Access Keys remain non-recoverable, which is why browsing is not exposed while key enforcement is active.

## Files

### `GET /api/files`

Returns the current file list and filesystem usage.

```json
{
  "files": [
    {
      "name": "report.pdf",
      "size": 1024,
      "modified": "2026-07-26T20:00:00+00:00",
      "created_at": "2026-07-26T20:00:00+00:00",
      "expires_at": "2026-07-26T21:00:00+00:00",
      "content_kind": "file",
      "access_key_required": true,
      "password_protected": false,
      "checksum_sha256": "c21f...64 lowercase hexadecimal characters...",
      "security": {
        "verdict": "unscanned",
        "detected_mime": "application/pdf",
        "scanner": null,
        "scanner_version": null,
        "signature_metadata": {},
        "findings": [],
        "inspected_at": 1789416000.0
      },
      "security_verdict": "unscanned",
      "detected_mime": "application/pdf",
      "download_confirmation_required": false,
      "download_url": "/download/report.pdf"
    }
  ],
  "storage": {
    "total": 0,
    "used": 0,
    "free": 0
  }
}
```

### `PUT /api/upload?filename=NAME`

Compatibility alias for raw file upload. New clients should use `PUT /api/drops/files?filename=NAME`.

Optional request headers:

| Header | Meaning |
| --- | --- |
| `X-NightWire-Expires-In-Seconds` | 60 through 31,536,000 seconds. Defaults to 3,600. Internet-facing Drops are capped at 86,400. |
| `X-NightWire-Password-B64` | UTF-8 password encoded as Base64. Empty or absent means unprotected. |

The Base64 header is encoding only and does not provide transport encryption.

Success status: `201 Created`. The response includes a `transfer_id`, the public `file` record, `bytes_written`, the streamed content's `checksum_sha256`, elapsed seconds, average byte rate, a one-time raw `access_key`, and the complete `share_url`. The key is not stored raw and cannot be recovered later.

```json
{
  "access_key": "43-character URL-safe bearer key",
  "share_url": "http://host:8080/drop/report.pdf?key=..."
}
```

The request `Content-Type` is retained only as declared MIME evidence. Core detects MIME from stored content, compares detected, declared, and filename-extension evidence, invokes the configured scanner adapter when present, and persists the result. Scanner identity/version/signature metadata is retained for later audit or rescanning. With no scanner, consistent content is `unscanned`; adapter errors are `scan_failed`; a MIME mismatch is `suspicious`. No verdict causes upload rejection or deletion.

Original filenames remain the logical API and download names. Newly uploaded content is physically stored under an opaque internal object ID that is not exposed by this API.

A protected existing file with the same name returns `409 Conflict`. An unprotected file with the same name may be replaced.

### `PATCH /api/files/{filename}`

Changes only the auto-delete countdown.

```json
{
  "expires_in_seconds": 3600
}
```

Drop lifetimes must remain positive. Password and Access Key fields are rejected.

### `GET /api/drops/{filename}?key=ACCESS_KEY`

Returns recipient-safe Drop metadata after validating the Access Key. Credential digests and object IDs are never returned.

### `GET /download/{filename}`

For newly created Drops, `key=ACCESS_KEY` is required. A password-protected Drop returns `401` after the Access Key succeeds and must use the protected download endpoint. Object-backed GET responses stream through Core and include `X-NightWire-Transfer-ID`. Compatible legacy root files without Access Keys retain their existing direct response path.

For a `malicious` Drop, an unconfirmed request returns `409` with `"confirmation_required": true`. After a deliberate hold in the UI, the client repeats the request with `confirm_malicious=true`. This server-side precondition applies independently of frontend behavior.

### `POST /api/files/{filename}/download?key=ACCESS_KEY`

Downloads a password-protected Drop using a JSON body containing `password`. Malicious protected Drops additionally require the boolean field `"confirm_malicious": true`, supplied only after the same hold interaction.

Downloads a Drop after Access Key and password verification.

```json
{
  "password": "example"
}
```

This endpoint also works for an unprotected file, although the direct route is simpler.

### `DELETE /api/files/{filename}`

Deletes a file. The JSON body may be empty for an unprotected item.

```json
{
  "password": "example"
}
```

Wrong passwords return `403 Forbidden`.

## Clipboard

### `GET /api/clipboard?since_revision=REVISION`

Returns clipboard entries when the supplied revision differs from the server revision.

```json
{
  "revision": 12,
  "changed": true,
  "entries": [],
  "max_text_length": 32768,
  "history_limit": 40
}
```

When `changed` is `false`, `entries` is an empty array. Clients should retain their current local snapshot.

Protected entry records contain `"text": null` and provide `text_length` instead.

### `POST /api/clipboard`

Creates a clipboard entry.

```json
{
  "client_id": "valid-client-id",
  "text": "Shared text",
  "expires_in_seconds": 600,
  "password": "optional password"
}
```

Rules:

- `client_id` must be 8 to 128 characters and match the accepted alphanumeric/punctuation pattern.
- `text` must contain 1 through 32,768 characters after normalization.
- expiration defaults to 600 seconds when omitted;
- an empty or omitted password creates an unprotected entry.

Success status: `201 Created`.

### `PATCH /api/clipboard/{entry_id}`

Changes only the auto-delete countdown:

```json
{
  "expires_in_seconds": 0
}
```

The item password is not required. Password changes are rejected.

### `POST /api/clipboard/{entry_id}/unlock`

Returns protected plaintext after verification:

```json
{
  "password": "example"
}
```

Success response:

```json
{
  "ok": true,
  "text": "Shared secret"
}
```

### `DELETE /api/clipboard/{entry_id}`

Deletes one clipboard entry. Protected entries require a password in the optional JSON body.

```json
{
  "password": "example"
}
```

### `DELETE /api/clipboard`

Clears all clipboard entries only when none are protected. If protected entries exist, the endpoint returns `409 Conflict` and those items must be deleted individually.

## Clients

### `POST /api/clients/heartbeat`

Registers or refreshes a browser client.

```json
{
  "client_id": "valid-client-id",
  "platform": "iOS",
  "mobile": true
}
```

The response includes the active device list and inactivity TTL. Browser metadata is inferred from the request user agent and optional platform hints.

### `GET /api/devices`

Returns the NightWire server record followed by active browser clients.

Clients with no heartbeat for more than approximately 18 seconds are removed.

## QR codes

### `GET /api/qr?url=URL`

Returns an SVG QR code for a valid HTTP or HTTPS URL. The URL must be no longer than 2,048 characters.

## Community Library authentication

Library authentication uses an HttpOnly, SameSite=Strict `nightwire_library_session` cookie. It is independent of anonymous Drop credentials.

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /api/library/auth/config` | Public | Returns registration policy, password minimum, and first-account state. |
| `POST /api/library/auth/register` | Public/policy-controlled | Creates an active account or a pending approval request. |
| `POST /api/library/auth/login` | Public | Starts a persistent session for an active account. |
| `POST /api/library/auth/logout` | Session | Revokes the current session and clears its cookie. |
| `GET /api/library/auth/me` | Session | Returns the current identity; otherwise `401`. |
| `GET /api/library` | Session | Returns the private root or the folder selected by `folder_id`, with children and breadcrumbs. |
| `GET /api/library/usage` | Session | Returns personal logical usage/quota, active reservations, and installation/host capacity. |
| `GET /api/library/search?q={query}&scope={personal|workspace|global}` | Session | Fuzzy-searches filenames recursively across only the caller-visible scopes. Results include relative paths, ranking scores, and scope metadata. File contents are not indexed. |
| `GET /api/library/folders?parent_id={id}` | Session | Lists a folder (the private root when omitted). |
| `POST /api/library/folders` | Session | Creates a child using `parent_id` and `name`; a slash-separated `path` creates missing descendants. |
| `GET /api/library/tree` | Session | Returns the complete nested folder/file tree. |
| `GET /api/library/folders/{id}` | Session/owner | Returns one folder, its immediate children, and breadcrumbs. |
| `PATCH /api/library/folders/{id}` | Session/owner | Renames and/or moves a folder using `name` and `parent_id`. |
| `DELETE /api/library/folders/{id}` | Session/owner | Moves a folder tree to the Trash boundary. |
| `PUT /api/library/folders/{id}/upload?name={name}` | Session/owner | Streams the raw request body through Core storage into a folder. Possible same-name or checksum matches return a structured `409 duplicate_warning`; repeat with `confirm_duplicates=true` to upload without deduplication. |
| `POST /api/library/folders/{id}/copy` | Session/owner | Recursively copies the logical tree, sharing immutable Core objects. |
| `POST /api/library/folders/{id}/duplicate` | Session/owner | Recursively duplicates the tree and its Core objects. |
| `GET /api/library/files/{id}` | Session/owner | Returns file details with Versions and Derived Outputs. |
| `PATCH /api/library/files/{id}` | Session/owner | Renames and/or moves a file without changing its Core object identity. |
| `DELETE /api/library/files/{id}` | Session/owner | Moves a file to the Trash boundary. |
| `GET /api/library/files/{id}/download` | Session/owner | Streams the file from Core storage with its logical filename. |
| `GET/PUT /api/library/files/{id}/versions` | Session/owner | Lists history or appends an immutable version from the raw request body. |
| `GET /api/library/files/{id}/versions/{version_id}/download` | Session/owner | Downloads a historical version. |
| `POST /api/library/files/{id}/versions/{version_id}/restore` | Session/owner | Restores old content by appending a new current version. |
| `GET/PUT /api/library/files/{id}/derived-outputs` | Session/owner | Lists outputs or attaches a raw generic output using `X-Source-Version-Id`, `X-Operation`, and optional JSON `X-Provenance` headers. |
| `POST /api/library/files/{id}/derived-outputs/{output_id}/promote` | Session/owner | Promotes an attached output by appending it as the current file version. |
| `GET/POST /api/library/files/{id}/shares` | Session/owner | Lists grants created by the caller or creates a read-only grant using `expires_in_seconds` (`0` means no expiry) and `access_key_protected`. Protected creation returns the raw reusable Access Key exactly once. |
| `POST /api/library/files/{id}/copy` | Session/owner | Creates another logical reference to the immutable Core object. |
| `POST /api/library/files/{id}/duplicate` | Session/owner | Creates an independent Core object and logical file. |
| `GET /api/library/trash` | Session/owner | Lists top-level deleted personal files and folder trees, plus the active retention period. |
| `POST /api/library/trash/files/{id}/restore` | Session/owner | Restores a file to its active parent, or the personal root when that parent is unavailable. |
| `POST /api/library/trash/folders/{id}/restore` | Session/owner | Recursively restores a folder tree, using the personal root when its parent is unavailable. |
| `DELETE /api/library/trash/files/{id}` | Session/owner | Permanently removes the logical file and deletes Core bytes only after all reference sources clear them. |
| `DELETE /api/library/trash/folders/{id}` | Session/owner | Permanently removes a logical folder tree with reference-safe Core cleanup. |
| `GET /api/library/shares` | Session | Lists Personal and Workspace grants created by the caller. Protected URLs cannot be reconstructed after creation. |
| `DELETE /api/library/shares/{share_id}` | Creator | Immediately revokes an active grant without deleting source bytes. |
| `POST /api/library/admin/invitations` | Administrator | Creates a single-use, email-bound invitation. |
| `GET /api/library/admin/pending-users` | Administrator | Lists accounts awaiting approval. |
| `POST /api/library/admin/pending-users/{id}/approve` | Administrator | Activates a pending account. |
| `POST /api/library/admin/pending-users/{id}/reject` | Administrator | Rejects a pending account and revokes its sessions. |

Registration accepts `email`, `display_name`, `password`, and—when required—`invitation_token`. Active registration returns `201`; an administrator-approval request returns `202`. Login accepts `email` and `password`.

## Community Workspaces

Every Workspace route requires Library authentication. Workspace-scoped storage uses the same logical folder/file and Core object services as personal storage, but its IDs are resolved under an explicit Workspace membership scope. A personal folder/file ID therefore returns `404` on a Workspace route, and a Workspace ID returns `404` on a personal route.

Community edition permits one Workspace association per user total, whether the user owns or merely belongs to it. The response from `GET /api/workspaces` exposes this capability as `policy.maximum_associations_per_user`. The server enforces it transactionally; `409` indicates an existing association.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/workspaces` | Returns the current association, members, and Community policy. |
| `POST /api/workspaces` | Creates a Workspace, independent root, and owner membership using `name`. |
| `GET /api/workspaces/{id}` | Returns Workspace metadata, members, and root/folder listing. |
| `GET /api/workspaces/{id}/usage` | Returns member-authorized Workspace logical usage/quota and installation/host capacity. |
| `POST /api/workspaces/{id}/members` | Owner adds an active Library user by `email`. |
| `DELETE /api/workspaces/{id}/members/me` | Leaves; an owner transfers to the oldest remaining member. A sole owner cannot leave. |
| `DELETE /api/workspaces/{id}/members/{user_id}` | Owner removes a non-owner member. |
| `GET/POST /api/workspaces/{id}/folders` | Lists the root/selected parent or creates a folder/path. |
| `GET /api/workspaces/{id}/tree` | Returns the recursive Workspace tree. |
| `GET/PATCH/DELETE /api/workspaces/{id}/folders/{folder_id}` | Lists, renames/moves, or trashes a folder. |
| `PUT /api/workspaces/{id}/folders/{folder_id}/upload?name={name}` | Streams a file through Core storage. Duplicate checks are restricted to that Workspace and use the same explicit confirmation contract as Personal Library uploads. |
| `POST /api/workspaces/{id}/folders/{folder_id}/copy` | Recursively copies logical references. |
| `POST /api/workspaces/{id}/folders/{folder_id}/duplicate` | Recursively duplicates physical Core objects. |
| `GET/PATCH/DELETE /api/workspaces/{id}/files/{file_id}` | Returns details, renames/moves, or trashes a file. |
| `GET /api/workspaces/{id}/files/{file_id}/download` | Downloads a Workspace file. |
| `GET/PUT /api/workspaces/{id}/files/{file_id}/versions` | Lists or appends Workspace file versions. |
| `GET /api/workspaces/{id}/files/{file_id}/versions/{version_id}/download` | Downloads historical Workspace content. |
| `POST /api/workspaces/{id}/files/{file_id}/versions/{version_id}/restore` | Appends a restored historical version. |
| `GET/PUT /api/workspaces/{id}/files/{file_id}/derived-outputs` | Lists or attaches generic Workspace-derived outputs. |
| `POST /api/workspaces/{id}/files/{file_id}/derived-outputs/{output_id}/promote` | Promotes a Workspace-derived output to a new version. |
| `GET/POST /api/workspaces/{id}/files/{file_id}/shares` | Lists or creates caller-owned read-only grants for an authorized Workspace file. |
| `POST /api/workspaces/{id}/files/{file_id}/copy` | Copies a logical file reference. |
| `POST /api/workspaces/{id}/files/{file_id}/duplicate` | Duplicates a Core object and logical file. |
| `GET /api/workspaces/{id}/trash` | Lists only that Workspace's top-level deleted items; membership is required. |
| `POST /api/workspaces/{id}/trash/files/{file_id}/restore` | Restores a Workspace file, falling back to the Workspace root. |
| `POST /api/workspaces/{id}/trash/folders/{folder_id}/restore` | Recursively restores a Workspace folder tree. |
| `DELETE /api/workspaces/{id}/trash/files/{file_id}` | Permanently removes a Workspace logical file with reference-safe Core cleanup. |
| `DELETE /api/workspaces/{id}/trash/folders/{folder_id}` | Permanently removes a Workspace logical folder tree with reference-safe Core cleanup. |

Deleted records are excluded from ordinary folder/tree results. Restore name collisions use deterministic `copy` suffixes. The retention worker purges expired top-level Trash entries; Core bytes survive whenever another Library logical file, registered version/derived result, or external module reference still points to the object ID.

## Public Library shares

Library share URLs use a random public token and optionally carry a reusable Access Key in the `key` query parameter. Only a salted digest of that key is persisted. A share pins the immutable file version that was current at creation, so later Library updates do not change externally shared bytes.

| Endpoint | Purpose |
| --- | --- |
| `GET /s/{token}?key={access_key}` | Anonymous read-only recipient page. |
| `GET /api/public/shares/{token}?key={access_key}` | Anonymous metadata for a valid, unexpired, unrevoked grant. Includes propagated source security state and a download URL. |
| `GET /api/public/shares/{token}/download?key={access_key}` | Streams the pinned Core object. Malicious content requires `confirm_malicious=true`; the recipient UI obtains this only through a continuous hold action. |
| `GET /api/public/shares/{token}/qr?key={access_key}` | Returns an SVG QR representation of the complete validated query-parameter URL. |

These routes expose no mutation methods. Access Keys remain reusable until expiry or revocation. Expiry and revocation invalidate access immediately but do not delete or relocate source bytes.

## Common error shape

Most API errors return JSON:

```json
{
  "error": "Human-readable error message."
}
```

Common status codes:

| Status | Meaning |
| ---: | --- |
| `400` | Invalid filename, payload, duration, ID, or password format. |
| `401` | Direct download attempted for a protected file. |
| `403` | Missing/invalid Drop Access Key or incorrect password for protected access/deletion. |
| `404` | Item or revoked share not found. |
| `409` | Protected overwrite, malicious-download confirmation required, or bulk clipboard clear blocked. |
| `410` | Library share grant has expired. |
| `413` | JSON request payload exceeds the endpoint limit. |
| `499` | Upload client disconnected before completion. |
