#!/usr/bin/env bash
set -Eeuo pipefail

# Recursively replace an existing NightWire source or installation with the
# release containing this script. User uploads, .venv, .git, and .env files are
# preserved. Add --install to also run the repaired system installer afterward.
#
# Examples:
#   ./update-existing.sh /path/to/original/NightWire
#   ./update-existing.sh --install /srv/nightwire
#   NIGHTWIRE_EXISTING_DIR=/opt/nightwire ./update-existing.sh --install

RELEASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_DIR="${NIGHTWIRE_EXISTING_DIR:-}"
RUN_INSTALL=0
TMP_ROOT="$(mktemp -d)"
STAGE_DIR="$TMP_ROOT/release"

cleanup() {
    rm -rf -- "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
    printf '\nError: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'HELP'
Usage: ./update-existing.sh [--install] [EXISTING_NIGHTWIRE_DIR]

Replace an existing NightWire tree with this extracted release.

Arguments:
  EXISTING_NIGHTWIRE_DIR   Existing source or installation directory.
                           Defaults to $NIGHTWIRE_EXISTING_DIR, then /srv/nightwire.

Options:
  --install                Run the system installer after replacing the tree.
  -h, --help               Show this help message.

Preserved paths:
  files/  .venv/  .git/  .env  .env.*
HELP
}

for argument in "$@"; do
    case "$argument" in
        --install) RUN_INSTALL=1 ;;
        -h|--help) usage; exit 0 ;;
        -*) fail "Unknown option: $argument" ;;
        *)
            [[ -z "$TARGET_DIR" ]] || fail "Only one target directory may be supplied."
            TARGET_DIR="$argument"
            ;;
    esac
done

TARGET_DIR="${TARGET_DIR:-/srv/nightwire}"
TARGET_DIR="$(readlink -m -- "$TARGET_DIR")"

[[ "$TARGET_DIR" != "/" ]] || fail "Refusing to replace the filesystem root."
[[ -f "$RELEASE_DIR/app.py" ]] || fail "Run this script from the extracted NightWire release."
[[ -f "$RELEASE_DIR/uv.lock" ]] || fail "The release is missing uv.lock."
[[ -f "$RELEASE_DIR/static/app.js" ]] || fail "The release frontend is incomplete."
command -v tar >/dev/null 2>&1 || fail "tar is required."
command -v cmp >/dev/null 2>&1 || fail "cmp is required."

if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    TARGET_USER="$SUDO_USER"
else
    TARGET_USER="$(id -un)"
fi
TARGET_GROUP="$(id -gn "$TARGET_USER")"

if [[ -e "$TARGET_DIR" ]]; then
    TARGET_UID="$(stat -c '%u' "$TARGET_DIR" 2>/dev/null || id -u "$TARGET_USER")"
    TARGET_GID="$(stat -c '%g' "$TARGET_DIR" 2>/dev/null || id -g "$TARGET_USER")"
else
    TARGET_UID="$(id -u "$TARGET_USER")"
    TARGET_GID="$(id -g "$TARGET_USER")"
fi

as_root() {
    if [[ "$EUID" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        "$@"
    fi
}

printf '\nUpdating NightWire tree\n'
printf 'Release: %s\n' "$RELEASE_DIR"
printf 'Target:  %s\n\n' "$TARGET_DIR"

# Stage first, so the target can safely be the same directory as this script or
# a parent directory containing the extracted release.
mkdir -p "$STAGE_DIR"
MANIFEST_PATH="$RELEASE_DIR/release-manifest.txt"
[[ -f "$MANIFEST_PATH" ]] || fail "The release manifest is missing."
while IFS= read -r relative || [[ -n "$relative" ]]; do
    [[ -n "$relative" ]] || continue
    case "$relative" in
        /*|../*|*/../*|*/..|.) fail "Unsafe path in release manifest: $relative" ;;
    esac
    [[ -f "$RELEASE_DIR/$relative" ]] || fail "Release file is missing: $relative"
done < "$MANIFEST_PATH"
(
    cd "$RELEASE_DIR"
    tar -cf - -T release-manifest.txt
) | tar -C "$STAGE_DIR" -xf -

as_root mkdir -p "$TARGET_DIR"

while IFS= read -r -d '' item; do
    name="${item##*/}"
    case "$name" in
        files|.venv|.git|.env|.env.*) continue ;;
    esac
    as_root rm -rf -- "$item"
done < <(find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -print0)

tar -C "$STAGE_DIR" -cf - . | as_root tar -C "$TARGET_DIR" -xf -
as_root mkdir -p "$TARGET_DIR/files"
as_root chown -R "$TARGET_UID:$TARGET_GID" "$TARGET_DIR"
as_root chmod 0755 "$TARGET_DIR" "$TARGET_DIR/files"

printf 'Verifying replaced files...\n'
VERIFY_FAILED=0
while IFS= read -r -d '' relative; do
    if ! as_root cmp -s "$STAGE_DIR/$relative" "$TARGET_DIR/$relative"; then
        printf 'Verification failed: %s\n' "$relative" >&2
        VERIFY_FAILED=1
    fi
done < <(cd "$STAGE_DIR" && find . -type f -print0)
(( VERIFY_FAILED == 0 )) || fail "The target tree does not match the extracted release."

VERSION="$(tr -d '[:space:]' < "$TARGET_DIR/VERSION" 2>/dev/null || true)"
printf 'NightWire %s replaced successfully.\n' "${VERSION:-release}"

if (( RUN_INSTALL == 1 )); then
    printf '\nRunning the system installer from the updated tree...\n'
    exec "$TARGET_DIR/install.sh"
fi

printf '\nTo update the system installation too, run:\n'
printf '  %q --install %q\n\n' "$RELEASE_DIR/update-existing.sh" "$TARGET_DIR"
