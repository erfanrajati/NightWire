# Using NightWire

This guide describes the browser interface and the lifecycle rules in NightWire `1.0.2`.

## Pages

NightWire has three dedicated routes:

| Page | Route | Purpose |
| --- | --- | --- |
| Files | `/files` | Upload, browse, download, delete, and set file retention. |
| Clipboard | `/clipboard` | Share text, unlock protected text, copy entries, and set retention. |
| Clients | `/clients` | View connected devices, LAN addresses, and the connection QR code. |

Opening `/` redirects to `/files`.

## Files

### Upload a file

1. Open **Files**.
2. Select an auto-delete duration. New files default to **Unlimited / never**.
3. Optionally enter and confirm a password.
4. Drop one or more files into the upload area or choose **browse your device**.

Uploads stream directly to a temporary file and are atomically moved into the shared directory when complete. NightWire does not set an application-level file-size limit; practical limits are available disk space, browser behavior, and network reliability.

### Password behavior

File passwords are optional and creation-only.

- A password cannot be added, changed, or removed after upload.
- A protected file requires its password to download or delete through NightWire.
- Uploading another file with the same name cannot overwrite an existing protected file.
- Protection applies to the NightWire interface and API; it does not encrypt the server-side file.

Keep the password somewhere safe. NightWire has no password-reset feature.

### Auto-delete behavior

Every file has an editable countdown:

- `Unlimited` means no automatic deletion.
- Timed retention may be set from 1 minute through 365 days.
- Any connected client may change the countdown, including for a password-protected file.
- Changing the countdown does not require the item password.
- The cleanup worker checks expiration while the server is running, even when no browser is open.

The countdown is a retention convenience, not an authorization boundary.

### Download and deletion

Unprotected files download directly. Protected files open a password prompt before NightWire sends the file.

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
| File | Unlimited | 1 minute | 365 days | `0` seconds |
| Clipboard text | 10 minutes | 1 minute | 365 days | `0` seconds |

## Recommended workflow

For ordinary trusted-LAN use:

1. Use unlimited retention only for files that should remain on the host.
2. Keep clipboard retention short.
3. Use passwords for content that should not be opened casually by other clients.
4. Remember that any connected client can extend or disable auto-delete.
5. Delete sensitive items when finished rather than relying solely on countdowns.
