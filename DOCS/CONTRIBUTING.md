# Contributing to NightWire

Thank you for improving NightWire. Contributions should preserve its core qualities: simple local deployment, fast LAN transfers, a small dependency footprint, clear security behavior, and responsive browser performance.

## Before contributing

The repository currently has no explicit license file or contributor agreement. Maintainers should define contribution and licensing terms before accepting third-party code for redistribution.

For security-sensitive findings, follow [SECURITY.md](SECURITY.md) and report privately rather than opening a public exploit report.

## Development setup

Requirements:

- Python 3.11 or newer;
- `uv`;
- a modern browser;
- optionally Node.js for JavaScript syntax checking.

Prepare the environment:

```bash
git clone <repository-url>
cd NightWire
uv sync --locked
```

Run the development server:

```bash
uv run python app.py
```

Use a separate files directory during development when you do not want test uploads mixed with the repository:

```bash
NIGHTWIRE_FILES_DIR=/tmp/nightwire-dev-files PORT=8080 uv run python app.py
```

## Branch and commit guidance

- Create a focused branch for one feature or fix.
- Keep commits reviewable and logically grouped.
- Use imperative commit subjects, for example `Fix mobile viewport overflow`.
- Avoid mixing broad formatting changes with behavior changes.
- Do not commit uploaded files, `.venv`, caches, secrets, or local environment files.

## Code organization

### Backend

The root `app.py` is a compatibility alias and executable launcher for `nightwire.app.runtime`. Configuration, object storage, transfers/progress, lifecycle decisions, capacity policy, and security inspection belong in `nightwire/core`; Drop domain behavior, metadata persistence, route-facing services, clipboard compatibility, and client visibility belong in `nightwire/drop`; content processing contracts belong in `nightwire/processors`; Starlette construction, registration contracts, configured middleware, and runtime composition belong in `nightwire/app`. New behavior should be placed in the relevant package. Backend work should:

- validate all client input at the boundary;
- address stored content through Core object/upload IDs instead of passing arbitrary filesystem paths across boundaries;
- use locks for shared state touched by requests and the cleanup thread;
- preserve atomic metadata writes;
- remove temporary upload files on failure;
- keep active transfer IDs out of orphan cleanup and preserve bounded progress state;
- treat declared MIME as evidence only and detect content from stored bytes;
- persist normalized security results without treating `unscanned` as `clean`;
- implement malware engines through `MalwareScannerAdapter`, not direct Core imports;
- register optional post-storage work through `ProcessorRegistry`;
- give processors a stable name/version identity and return typed execution results rather than ad hoc dictionaries;
- describe derived content with `DerivedObject` references after storing it through Core;
- route security-sensitive external tools through `SandboxExecutor`; never treat `DenySandboxExecutor` as successful execution;
- keep `drop`, `library`, and `text` from importing one another's internal implementation modules; use Core or an explicitly public package API;
- maintain no-store and security headers;
- avoid putting passwords or sensitive plaintext in URLs or logs;
- never persist raw Drop Access Keys; use the Drop access policy and keep complete bearer URLs out of logs;
- preserve creation-only, immutable password protection unless a reviewed security redesign replaces it;
- remember that countdown changes are intentionally public to LAN clients in the current model.

Keep `release-manifest.txt` synchronized when adding package files required by source-tree or installed execution.

### Frontend

The frontend uses plain HTML, CSS, and JavaScript. Preserve that approach unless a major version explicitly adopts a build system.

Frontend changes should:

- remain usable with keyboard and touch input;
- provide labels and accessible names for controls;
- keep dialogs focusable and understandable;
- avoid injecting untrusted strings through `innerHTML`;
- keep decorative layers inside the viewport;
- avoid expensive full-screen blur, backdrop-filter, and continuous animation;
- update only active page views during polling;
- preserve reduced-motion support;
- test iPhone widths and desktop layouts;
- avoid disabling browser zoom.

### Documentation

Update `README.md` when installation, requirements, routes, defaults, or the security summary changes. Update the relevant file in `DOCS/` for detailed behavior.

Keep examples aligned with the actual release version and scripts.

## Validation

Run the unit test suite:

```bash
uv run python -m unittest discover -s tests -v
```

Compile-check the Python entry point:

```bash
uv run python -m py_compile app.py
```

Validate JavaScript when Node.js is available:

```bash
node --check static/app.js
node --check static/drop.js
node --check static/drop-share.js
```

Validate shell scripts:

```bash
bash -n run.sh install.sh update-existing.sh
```

When PowerShell is available, also parse-check the Windows installer:

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile("$PWD/install.ps1", [ref]$null, [ref]$errors) > $null
if ($errors) { $errors | Format-List; exit 1 }
```

Confirm the locked environment is consistent:

```bash
uv lock --check
uv sync --locked
```

## Manual test matrix

At minimum, test these workflows in a real browser:

### Files

- upload one and multiple files;
- upload with the default and selected Drop lifetimes;
- enforce the internet-facing 24-hour Drop maximum;
- validate missing, wrong, and correct Access Keys through a complete share URL;
- upload with and without a password;
- confirm protected files cannot be overwritten;
- download and delete protected and unprotected files;
- edit countdowns from another client;
- verify expiration removes the disk file and metadata.

### Clipboard

- share normal and multiline text;
- share protected and unprotected text;
- verify protected plaintext is absent from list responses;
- unlock, copy, and delete protected text;
- edit countdowns from another client;
- verify history bounding and server-restart clearing;
- test manual paste and optional clipboard watching.

### Clients

- connect desktop and mobile browsers;
- verify device labels and LAN addresses;
- verify a closed client disappears after the TTL;
- scan the QR code from a second device.

### Responsive and performance

Test at least these viewport widths:

```text
320, 360, 375, 390, 414, 430, 768, 1024, 1440 pixels
```

Check that:

- `document.documentElement.scrollWidth` does not exceed the viewport at mobile widths;
- page changes are immediate;
- scrolling stays smooth;
- no hidden decorative element creates horizontal space;
- pinch zoom remains available;
- browser console errors do not appear.

## Tests for backend changes

Add or update `unittest` coverage for:

- validation failures;
- authorization/password boundaries;
- path traversal and internal filenames;
- expiration and cleanup behavior;
- persistence and restart behavior;
- immutable password rules;
- public countdown changes;
- regression cases from the reported bug.

Run the dependency-boundary test whenever feature packages change. New internal modules are discovered from the package tree, so direct absolute and relative cross-feature imports fail the suite.

Tests that alter global state must restore `FILES_DIR`, metadata, clipboard entries, locks, and cleanup-worker state in teardown.

## Dependency changes

NightWire deliberately has few dependencies. Before adding one:

1. explain why the standard library or current stack is insufficient;
2. consider installation size and offline reproducibility;
3. pin an appropriate compatible range in `pyproject.toml`;
4. regenerate `uv.lock`;
5. run the full validation set.

Do not hand-edit `uv.lock`.

## Release changes

When preparing a release:

1. update `VERSION`;
2. update the version in `pyproject.toml`;
3. update the frontend-visible version and cache-busting references where applicable;
4. update `README.md` and relevant `DOCS/` files;
5. update `release-manifest.txt` when release files are added or removed;
6. run automated and manual validation;
7. verify a clean extraction and installation over an existing tree;
8. create and verify the release archive checksum.

## Pull-request checklist

- [ ] The change has one clear purpose.
- [ ] Security assumptions are documented.
- [ ] Password and countdown behavior remains intentional.
- [ ] Unit tests pass.
- [ ] Python, JavaScript, and shell syntax checks pass where applicable.
- [ ] Mobile and desktop workflows were tested.
- [ ] No secrets, uploads, caches, or generated environments are included.
- [ ] Documentation and version references are updated.
- [ ] New release files are represented in the release manifest when required.
