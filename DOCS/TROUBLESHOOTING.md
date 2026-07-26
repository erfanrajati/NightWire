# Troubleshooting

## `uv` is missing

The source launchers and installer require `uv` in `PATH`.

Check:

```bash
uv --version
```

After installing `uv`, reopen the terminal or update `PATH`, then run `./run.sh` or `./install.sh` again.

## Python version errors

NightWire requires Python 3.11 or newer.

```bash
python3 --version
```

For the system installer, select a specific interpreter:

```bash
NIGHTWIRE_PYTHON=python3.12 ./install.sh
```

## Port already in use

Symptoms include an address-in-use error or immediate server shutdown.

Choose another port:

```bash
PORT=9000 ./run.sh
```

or:

```bash
nightwire --port 9000
```

## Another device cannot connect

Confirm all of the following:

1. NightWire is still running.
2. The client uses a LAN address printed by NightWire, not `127.0.0.1`.
3. Both devices are on the same reachable network.
4. The host firewall allows inbound TCP traffic on the NightWire port.
5. The router does not enable AP isolation, client isolation, or guest-device separation.
6. A VPN is not forcing traffic through a different route.

Try opening the address from another browser on the host first, then from the second device.

## The Clients page shows stale or missing devices

Browser clients must keep sending heartbeats. A client disappears about 18 seconds after heartbeats stop.

A device may be absent when:

- its page is suspended by the mobile operating system;
- the browser tab is closed;
- the network changed;
- the client cannot reach the server;
- aggressive power saving paused browser timers.

Return to the NightWire tab and wait a few seconds.

## Upload fails immediately

Check write permission and free space for the shared directory:

```bash
ls -ld /srv/nightwire/files
df -h /srv/nightwire/files
```

For a custom source-tree directory, inspect the path set by `NIGHTWIRE_FILES_DIR`.

Also verify that the filename is not trying to overwrite an existing password-protected file. Protected files cannot be overwritten under the same name.

## A partial `.uploading-*` file appears

NightWire normally removes temporary upload files when a client disconnects or an upload fails. After an abnormal process termination, a hidden temporary file may remain.

Stop NightWire, confirm no upload is active, then remove only clearly stale `.uploading-*` files from the configured shared directory.

## Countdown did not delete an item

Check:

- NightWire is running;
- the host clock is correct;
- the item countdown was not changed by another connected client;
- the process account can delete from the files directory;
- the item did not have its retention changed to unlimited.

The cleanup worker runs approximately once per second, so a small delay is normal.

## A password was forgotten

Passwords cannot be changed or removed through NightWire.

For a protected file, the server operator can access the underlying file directly from the shared directory because NightWire protection is not disk encryption.

For protected clipboard text, there is no recovery path through NightWire. The entry disappears when it expires, is deleted with the correct password, or the server restarts.

## Clipboard watching is unavailable

Automatic clipboard reads depend on browser permissions and secure-context rules.

Try:

- granting clipboard permission when prompted;
- focusing the NightWire tab;
- using manual paste;
- using HTTPS through a trusted reverse proxy;
- testing on localhost when using the host device.

NightWire can still detect paste events inside the page on many browsers even when background clipboard watching is blocked.

## Clipboard items disappeared after restart

This is expected. Clipboard history is stored only in process memory. Shared files and file metadata are persistent; clipboard entries are not.

## iPhone page becomes tiny when zooming out

Version `1.0.2` contains the iPhone viewport-width fix. Confirm the footer shows `1.0.2` or newer, then reload without an old cached page.

On Safari, close and reopen the tab or clear website data for the NightWire address when a normal reload keeps old styling.

## Installer cannot use `sudo`

The current Linux system installer requires root privileges or a working `sudo` command, including when custom target paths are selected.

When neither is available, run NightWire directly from the source tree instead:

```bash
chmod +x run.sh
./run.sh
```

An administrator can later run `./install.sh`, or install into the desired system locations on your behalf.

## Installed version did not change

Verify the source and installed versions:

```bash
cat /path/to/source/NightWire/VERSION
cat /srv/nightwire/VERSION
```

Run the installer from the newly updated source tree, stop any older process, and launch NightWire again. A previously running Python process continues serving the old code until restarted.

## File metadata problems

Persistent file settings live in:

```text
<files directory>/.nightwire-metadata.json
```

Before manual repair:

1. stop NightWire;
2. back up the file and shared directory;
3. validate that the JSON is well formed;
4. avoid changing password records unless you understand the format.

Deleting the metadata entry for a file causes NightWire to rediscover that file as unprotected with unlimited retention. This is an administrative filesystem action and bypasses application-level protection.
