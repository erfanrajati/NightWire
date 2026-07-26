# HTTP API Reference

The NightWire browser uses a small JSON and streaming HTTP API. This API is currently an internal interface and does not carry a formal backward-compatibility guarantee.

All paths are relative to the NightWire origin. Dynamic responses use no-store caching.

## Page and static routes

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Redirects to `/files`. |
| `GET` | `/files` | Serves the browser application on the Files page. |
| `GET` | `/clipboard` | Serves the browser application on the Clipboard page. |
| `GET` | `/clients` | Serves the browser application on the Clients page. |
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
  "file_default_expiry_seconds": 0,
  "item_min_expiry_seconds": 60,
  "item_max_expiry_seconds": 31536000,
  "password_max_characters": 256,
  "network_urls": ["http://192.168.1.29:8080"],
  "primary_network_url": "http://192.168.1.29:8080"
}
```

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
      "expires_at": null,
      "password_protected": false,
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

Streams the raw request body into a file.

Optional request headers:

| Header | Meaning |
| --- | --- |
| `X-NightWire-Expires-In-Seconds` | `0` for unlimited, otherwise 60 through 31,536,000 seconds. Defaults to `0`. |
| `X-NightWire-Password-B64` | UTF-8 password encoded as Base64. Empty or absent means unprotected. |

The Base64 header is encoding only and does not provide transport encryption.

Success status: `201 Created`.

A protected existing file with the same name returns `409 Conflict`. An unprotected file with the same name may be replaced.

### `PATCH /api/files/{filename}`

Changes only the auto-delete countdown.

```json
{
  "expires_in_seconds": 3600
}
```

Use `0` for unlimited. Password-related fields are rejected.

### `GET /download/{filename}`

Downloads an unprotected file. A protected file returns `401` and must use the protected download endpoint.

### `POST /api/files/{filename}/download`

Downloads a file after password verification.

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
| `403` | Incorrect password for protected access or deletion. |
| `404` | Item not found or already expired. |
| `409` | Protected overwrite attempt or bulk clipboard clear blocked. |
| `413` | JSON request payload exceeds the endpoint limit. |
| `499` | Upload client disconnected before completion. |
