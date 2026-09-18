# Using NightWire

This guide describes the browser interface and the lifecycle rules in NightWire `1.0.2`.

## Pages

NightWire has three dedicated routes:

| Page | Route | Purpose |
| --- | --- | --- |
| Secure Drop | `/files` | Create expiring file, text, or voice Drops and share private links. |
| Clipboard | `/clipboard` | Share text, unlock protected text, copy entries, and set retention. |
| Clients | `/clients` | View connected devices, LAN addresses, and the connection QR code. |

Opening `/` redirects to `/files`.

## Secure Drop

### Upload a file

1. Open **Secure Drop**.
2. Select a burn time. New Drops default to **1 hour**.
3. Drop one file into the file card or tap the card to choose one.
4. Copy the generated access link or show its QR representation.

After each upload, NightWire displays a complete share URL. Internet-facing mode includes a cryptographically random Access Key; copy that link before leaving because NightWire stores only its non-recoverable verifier. With both trusted-network switches enabled, the active list can reopen a keyless access link and its QR at any time until expiry or deletion.

Uploads stream directly to isolated temporary Core storage while SHA-256 is calculated, then are atomically finalized under an opaque internal object ID. The original filename remains the visible name. NightWire does not set an application-level file-size limit; practical limits are available disk space, browser behavior, and network reliability.

### Share temporary text or voice

The composer places file and voice sharing together on the first row and a larger text area below. Choose one lifetime, then paste or type text and select **Share text**, or select **Start recording**, grant microphone access, and select **Stop & share**. During live capture, the voice card displays an intensity matrix and elapsed time. Both become ordinary expiring Drops through the same Core transfer pipeline.

The result modal can copy the complete share link or display a QR for that exact link. Recipient pages preview text and images and use NightWire's custom voice player. NightWire prefers Safari-compatible MP4 audio where supported and falls back to WebM/Ogg. When iOS or an insecure LAN address does not expose `MediaRecorder`, the same control opens the device audio-capture chooser and uploads the result.

### Password behavior

Password-protected Drops remain supported by the compatibility API, but password setup is not part of the minimal anonymous Secure Drop screen. Passwords are creation-only.

- A password cannot be added, changed, or removed after upload.
- A protected file requires its password to download or delete through NightWire.
- Uploading another file with the same name cannot overwrite an existing protected file.
- Protection applies to the NightWire interface and API; it does not encrypt the server-side file.

Keep the password somewhere safe. NightWire has no password-reset feature.

### Auto-delete behavior

Every Drop has an enforced countdown:

- New Drops always have an explicit creation time and expiration time.
- Drop lifetime may be selected from 1 minute through 365 days on trusted/private installations.
- Anonymous Drops on an `internet-facing` installation have a hard 24-hour maximum.
- The compatibility API can change the countdown; the primary Drop screen keeps creation focused on choosing it once.
- The cleanup worker checks expiration while the server is running, even when no browser is open.

The countdown is a retention convenience, not an authorization boundary.

### Download and deletion

Recipients open the complete `/drop/{filename}?key=...` share URL. NightWire validates the Access Key before showing metadata or allowing a download. Password-protected Drops then request the password as an additional check.

Each Drop shows its persisted security state. `suspicious`, `scan_failed`, and `unscanned` warn that the content is not known clean. A `malicious` Drop is retained, but NightWire does not preview it or send it to risky processors. To retrieve its opaque bytes, hold the download control until confirmation completes; a click or interrupted hold does not authorize the download.

The QR shown after creation encodes the exact complete URL; it is not a pairing code. In fully enabled trusted mode, every active row can reopen its access link and QR and can download without relying on a browser-held key. In internet-facing mode, the active directory is absent and only the one-time creation result exposes the keyed share link.

The active directory is enabled only when trusted/private deployment, key relaxation, and active browsing are all configured. Internet-facing deployments always require complete Access Key URLs and never expose the active-Drop directory.

Files copied directly into the legacy storage root do not have Access Keys and retain their original direct-download behavior until replaced by a new Drop.

Deleting an unprotected file is immediate after interface confirmation. Deleting a protected file requires the password.

## Clipboard

### Share text

1. Open **Clipboard**.
2. Paste or type text into the editor.
3. Select a countdown. New clipboard entries default to **10 minutes**.
4. Optionally set and confirm a password.
5. Choose **Share text**.

Clipboard text is limited to 32,768 characters. The shared history keeps the newest 40 entries.

### Copy and paste detection

NightWire can detect copy or paste activity that occurs inside the page and recommend sharing the detected text. It never broadcasts detected text until the user approves it.

The optional clipboard watcher uses the browser Clipboard API. Browser security may require:

- explicit permission;
- a focused page;
- a secure context such as HTTPS or localhost.

A plain LAN HTTP address may not be allowed to read the operating-system clipboard automatically. Manual paste and page-level paste detection still work in supported browsers.

### Protected clipboard entries

Protected clipboard text is withheld from normal synchronization responses. A client must submit the correct password to retrieve and copy the plaintext.

- The password cannot be changed or removed after sharing.
- Deletion requires the password.
- Countdown changes remain public to connected clients.
- Other clients can see that an entry exists, its length, source, creation time, expiration, and protected status, but not its text.

### Clipboard persistence

Clipboard entries are memory-only. They disappear when:

- their countdown expires;
- a user deletes them;
- an unprotected history is cleared;
- NightWire restarts.

Protected entries must be deleted individually; bulk clear is blocked while protected entries remain.

## Clients

The Clients page shows the NightWire host and browsers that recently sent a heartbeat.

- Browser clients send a heartbeat approximately every 2.5 seconds.
- A client is treated as inactive after roughly 18 seconds without a heartbeat.
- Device and browser names are inferred from the user agent and browser platform hints.
- The server displays one or more detected IPv4 LAN addresses.
- The QR code encodes the selected NightWire HTTP address.

The list is informational. It is not an access-control list, and there is no function to approve, reject, or disconnect a client.

## Retention defaults and limits

| Item type | Default | Minimum timed duration | Maximum timed duration | Unlimited value |
| --- | ---: | ---: | ---: | ---: |
| Drop | 1 hour | 1 minute | 365 days trusted/private; 24 hours internet-facing | Not supported |
| Clipboard text | 10 minutes | 1 minute | 365 days | `0` seconds |

## Recommended workflow

For ordinary trusted-LAN use:

1. Copy each complete Drop share URL immediately; the raw Access Key cannot be recovered later.
2. Keep clipboard retention short.
3. Use passwords for content that should not be opened casually by other clients.
4. Remember that any connected client can change a Drop countdown within the active deployment limit.
5. Delete sensitive items when finished rather than relying solely on countdowns.
