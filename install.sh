#!/usr/bin/env bash
set -Eeuo pipefail

# NightWire installer / upgrader (Linux and macOS)
#
# Safe for both of these cases:
#   ./install.sh                    # run from an extracted release
#   cd /srv/nightwire && ./install.sh  # upgrade in place (Linux)
#
# Optional overrides:
#   NIGHTWIRE_INSTALL_DIR=/srv/nightwire
#   NIGHTWIRE_BIN_DIR=/usr/local/bin
#   NIGHTWIRE_PYTHON=3.12

APP_NAME="NightWire"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
case "$(uname -s)" in
    Linux) DEFAULT_INSTALL_DIR="/srv/nightwire" ;;
    Darwin) DEFAULT_INSTALL_DIR="/usr/local/share/nightwire" ;;
    *)
        printf 'Error: this installer supports Linux and macOS. On Windows, run install.ps1.\n' >&2
        exit 1
        ;;
esac

INSTALL_DIR="${NIGHTWIRE_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
BIN_DIR="${NIGHTWIRE_BIN_DIR:-/usr/local/bin}"
COMMAND_PATH="$BIN_DIR/nightwire"
PYTHON_REQUEST="${NIGHTWIRE_PYTHON:-3.11}"
TMP_ROOT="$(mktemp -d)"
STAGE_DIR="$TMP_ROOT/release"
LAUNCHER_TMP="$TMP_ROOT/nightwire-launcher"

cleanup() {
    rm -rf -- "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
    printf '\nError: %s\n' "$*" >&2
    exit 1
}

nearest_existing_parent() {
    local candidate="$1"
    while [[ ! -e "$candidate" ]]; do
        candidate="$(dirname -- "$candidate")"
    done
    printf '%s\n' "$candidate"
}

USE_SUDO=0
if [[ "$EUID" -ne 0 ]]; then
    [[ -w "$(nearest_existing_parent "$INSTALL_DIR")" ]] || USE_SUDO=1
    [[ -w "$(nearest_existing_parent "$BIN_DIR")" ]] || USE_SUDO=1
fi

as_admin() {
    if (( USE_SUDO == 0 )); then
        "$@"
    else
        sudo "$@"
    fi
}

install_linux_prerequisites() {
    [[ "$(uname -s)" == "Linux" ]] || return 0

    local -a missing_packages=()
    command -v tar >/dev/null 2>&1 || missing_packages+=(tar)
    command -v cmp >/dev/null 2>&1 || missing_packages+=(diffutils)
    command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || missing_packages+=(ca-certificates curl)
    (( ${#missing_packages[@]} > 0 )) || return 0

    printf 'Installing missing system prerequisites: %s\n' "${missing_packages[*]}"
    local -a admin_command=()
    if [[ "$EUID" -ne 0 ]]; then
        command -v sudo >/dev/null 2>&1 || fail "sudo is required to install missing system prerequisites: ${missing_packages[*]}"
        admin_command=(sudo)
    fi
    if command -v apt-get >/dev/null 2>&1; then
        "${admin_command[@]}" apt-get update
        "${admin_command[@]}" apt-get install -y --no-install-recommends "${missing_packages[@]}"
    elif command -v dnf >/dev/null 2>&1; then
        "${admin_command[@]}" dnf install -y "${missing_packages[@]}"
    else
        fail "Install these prerequisites and run the installer again: ${missing_packages[*]} (supported package managers: apt-get and dnf)."
    fi
}

if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    INSTALL_USER="$SUDO_USER"
else
    INSTALL_USER="$(id -un)"
fi
INSTALL_GROUP="$(id -gn "$INSTALL_USER")"
INSTALL_HOME=""
if command -v getent >/dev/null 2>&1; then
    INSTALL_HOME="$(getent passwd "$INSTALL_USER" 2>/dev/null | cut -d: -f6 || true)"
elif command -v dscl >/dev/null 2>&1; then
    INSTALL_HOME="$(dscl . -read "/Users/$INSTALL_USER" NFSHomeDirectory 2>/dev/null | cut -d' ' -f2- || true)"
fi
INSTALL_HOME="${INSTALL_HOME:-$HOME}"

as_install_user() {
    if [[ "$(id -un)" == "$INSTALL_USER" ]]; then
        HOME="$INSTALL_HOME" "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo -u "$INSTALL_USER" env HOME="$INSTALL_HOME" "$@"
    elif command -v runuser >/dev/null 2>&1; then
        runuser -u "$INSTALL_USER" -- env HOME="$INSTALL_HOME" "$@"
    else
        fail "Cannot run uv as $INSTALL_USER because neither sudo nor runuser is available."
    fi
}

printf '\nInstalling %s\n' "$APP_NAME"
printf 'Source:  %s\n' "$SOURCE_DIR"
printf 'Target:  %s\n' "$INSTALL_DIR"
printf 'Command: %s\n\n' "$COMMAND_PATH"

[[ -f "$SOURCE_DIR/app.py" ]] || fail "app.py was not found."
[[ -f "$SOURCE_DIR/pyproject.toml" ]] || fail "pyproject.toml was not found."
[[ -f "$SOURCE_DIR/uv.lock" ]] || fail "uv.lock was not found."
[[ -d "$SOURCE_DIR/static" ]] || fail "the static directory was not found."
install_linux_prerequisites
command -v tar >/dev/null 2>&1 || fail "tar is required."
command -v cmp >/dev/null 2>&1 || fail "cmp is required."
if (( USE_SUDO == 1 )); then
    command -v sudo >/dev/null 2>&1 || fail "sudo is required to install into $INSTALL_DIR and $BIN_DIR."
fi

find_uv() {
    local candidate
    candidate="$(command -v uv 2>/dev/null || true)"
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
    fi
    for candidate in "$INSTALL_HOME/.local/bin/uv" "$INSTALL_HOME/.cargo/bin/uv"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

UV_FOUND="$(find_uv || true)"
if [[ -z "$UV_FOUND" ]]; then
    printf 'uv was not found; installing it for %s...\n' "$INSTALL_USER"
    UV_INSTALLER="$TMP_ROOT/uv-install.sh"
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh -o "$UV_INSTALLER" || fail "Could not download the uv installer."
    elif command -v wget >/dev/null 2>&1; then
        wget -q https://astral.sh/uv/install.sh -O "$UV_INSTALLER" || fail "Could not download the uv installer."
    else
        fail "curl or wget is required to install uv automatically."
    fi
    chmod 0755 "$TMP_ROOT" "$UV_INSTALLER"
    if [[ "$(id -un)" != "$INSTALL_USER" ]]; then
        as_admin chown "$INSTALL_USER:$INSTALL_GROUP" "$UV_INSTALLER"
    fi
    as_install_user env \
        UV_INSTALL_DIR="$INSTALL_HOME/.local/bin" \
        UV_NO_MODIFY_PATH=1 \
        sh "$UV_INSTALLER" || fail "uv installation failed."
    UV_FOUND="$(find_uv || true)"
    [[ -n "$UV_FOUND" ]] || fail "uv was installed but could not be located."
fi

# Stage the complete release before touching the target. This is what makes an
# in-place upgrade safe when SOURCE_DIR and INSTALL_DIR are the same directory.
mkdir -p "$STAGE_DIR"
MANIFEST_PATH="$SOURCE_DIR/release-manifest.txt"
[[ -f "$MANIFEST_PATH" ]] || fail "The release manifest is missing."
while IFS= read -r relative || [[ -n "$relative" ]]; do
    [[ -n "$relative" ]] || continue
    case "$relative" in
        /*|../*|*/../*|*/..|.) fail "Unsafe path in release manifest: $relative" ;;
    esac
    [[ -f "$SOURCE_DIR/$relative" ]] || fail "Release file is missing: $relative"
done < "$MANIFEST_PATH"
(
    cd "$SOURCE_DIR"
    tar -cf - -T release-manifest.txt
) | tar -C "$STAGE_DIR" -xf -

[[ -f "$STAGE_DIR/app.py" ]] || fail "The staged release is incomplete."
[[ -f "$STAGE_DIR/static/app.js" ]] || fail "The staged frontend is incomplete."
[[ -f "$STAGE_DIR/static/styles.css" ]] || fail "The staged frontend is incomplete."

APP_VERSION="$(tr -d '[:space:]' < "$STAGE_DIR/VERSION" 2>/dev/null || true)"
APP_VERSION="${APP_VERSION:-unknown}"
printf 'Release: %s\n' "$APP_VERSION"

UV_REAL="$(readlink -f "$UV_FOUND" 2>/dev/null || printf '%s' "$UV_FOUND")"
UV_RUNNER="$UV_REAL"

# Keep a stable uv binary if the discovered one may be removed during upgrade
# or belongs to the invoking user's home directory.
case "$UV_REAL" in
    "$INSTALL_HOME"/*|/root/*|"$INSTALL_DIR"/*)
        as_admin install -d -m 0755 "$BIN_DIR"
        if [[ "$UV_REAL" != "$BIN_DIR/uv" ]]; then
            as_admin install -m 0755 "$UV_REAL" "$BIN_DIR/uv"
        fi
        UV_RUNNER="$BIN_DIR/uv"
        ;;
esac

RUNNING_PIDS=""
if command -v pgrep >/dev/null 2>&1; then
    RUNNING_PIDS="$(pgrep -f "${INSTALL_DIR}/app.py" 2>/dev/null | tr '\n' ' ' || true)"
fi

# Preserve uploaded files, Library data, local configuration, and the uv environment. All
# application code is replaced so removed frontend or backend files cannot linger.
as_admin install -d -m 0755 "$INSTALL_DIR"
as_admin install -d -m 0755 "$INSTALL_DIR/files"
as_admin install -d -m 0755 "$INSTALL_DIR/data"

while IFS= read -r -d '' item; do
    name="${item##*/}"
    case "$name" in
        files|data|.venv|.env|.env.*) continue ;;
    esac
    as_admin rm -rf -- "$item"
done < <(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print0)

tar -C "$STAGE_DIR" -cf - . | as_admin tar -C "$INSTALL_DIR" -xf -

if [[ -d "$SOURCE_DIR/files" && "$SOURCE_DIR" != "$INSTALL_DIR" ]]; then
    as_admin cp -an "$SOURCE_DIR/files/." "$INSTALL_DIR/files/" 2>/dev/null || true
fi
if [[ -d "$SOURCE_DIR/data" && "$SOURCE_DIR" != "$INSTALL_DIR" ]]; then
    as_admin cp -an "$SOURCE_DIR/data/." "$INSTALL_DIR/data/" 2>/dev/null || true
fi

if [[ "$EUID" -eq 0 || "$USE_SUDO" -eq 1 ]]; then
    as_admin chown -R "$INSTALL_USER:$INSTALL_GROUP" "$INSTALL_DIR"
fi
as_admin chmod 0755 "$INSTALL_DIR" "$INSTALL_DIR/files" "$INSTALL_DIR/data"

printf 'Verifying installed files...\n'
VERIFY_FAILED=0
while IFS= read -r -d '' relative; do
    if ! as_admin cmp -s "$STAGE_DIR/$relative" "$INSTALL_DIR/$relative"; then
        printf 'Verification failed: %s\n' "$relative" >&2
        VERIFY_FAILED=1
    fi
done < <(cd "$STAGE_DIR" && find . -type f -print0)
(( VERIFY_FAILED == 0 )) || fail "The installed tree does not match the staged release."

printf 'Syncing the locked uv environment...\n'
as_install_user env UV_PROJECT_ENVIRONMENT="$INSTALL_DIR/.venv" \
    "$UV_RUNNER" sync \
    --project "$INSTALL_DIR" \
    --locked \
    --no-dev \
    --python "$PYTHON_REQUEST"

cat > "$LAUNCHER_TMP" <<LAUNCHER
#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="$INSTALL_DIR"
UV_BIN="$UV_RUNNER"
PORT_VALUE="\${NIGHTWIRE_PORT:-\${PORT:-8080}}"

show_help() {
    cat <<'HELP'
Usage: nightwire [--port PORT]

Start the NightWire LAN file server.

Options:
  -p, --port PORT   Listen on this port (default: 8080)
  -h, --help        Show this help message
HELP
}

while [[ \$# -gt 0 ]]; do
    case "\$1" in
        -p|--port)
            [[ \$# -ge 2 ]] || { echo "Missing value after \$1" >&2; exit 2; }
            PORT_VALUE="\$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: \$1" >&2
            show_help >&2
            exit 2
            ;;
    esac
done

[[ "\$PORT_VALUE" =~ ^[0-9]+$ ]] || { echo "Port must be a number." >&2; exit 2; }
(( PORT_VALUE >= 1 && PORT_VALUE <= 65535 )) || { echo "Port must be between 1 and 65535." >&2; exit 2; }
[[ -d "\$APP_DIR" ]] || { echo "NightWire is not installed at \$APP_DIR" >&2; exit 1; }
[[ -x "\$UV_BIN" ]] || { echo "uv is missing at \$UV_BIN" >&2; exit 1; }

export PORT="\$PORT_VALUE"
export UV_PROJECT_ENVIRONMENT="\$APP_DIR/.venv"
cd "\$APP_DIR"
exec "\$UV_BIN" run --project "\$APP_DIR" --locked --no-sync python app.py
LAUNCHER

as_admin install -d -m 0755 "$BIN_DIR"
as_admin install -m 0755 "$LAUNCHER_TMP" "$COMMAND_PATH"

printf '\n%s %s was installed successfully.\n\n' "$APP_NAME" "$APP_VERSION"
printf 'Start:     nightwire\n'
printf 'Port:      nightwire --port 9000\n'
printf 'App:       %s\n' "$INSTALL_DIR"
printf 'Uploads:   %s/files\n' "$INSTALL_DIR"
printf 'Command:   %s\n' "$COMMAND_PATH"

if [[ -n "$RUNNING_PIDS" ]]; then
    printf '\nA previous NightWire process is still running (PID(s): %s).\n' "$RUNNING_PIDS"
    printf 'Stop that process and start NightWire again to load version %s.\n' "$APP_VERSION"
fi
printf '\n'
