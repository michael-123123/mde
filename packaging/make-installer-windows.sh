#!/usr/bin/env bash
# Build a Windows installer .exe from a Nuitka standalone dist.
#
# Input (required):
#   --dist-dir=PATH   Path to a Nuitka standalone dist directory (the one
#                     that contains mde.exe or mde_launch.exe plus all the
#                     bundled DLLs / PySide6/ subdir / data files).
#
# Produced by either:
#   - packaging/build-windows.sh       --mode=standalone   (Wine)
#   - packaging/build-windows-native.sh --mode=standalone  (real Windows)
# The installer doesn't care which; it just wraps the bytes it's given.
#
# Default output: $BUILD_DIR/MarkdownEditor-<version>-x86_64-setup.exe
#
# Prerequisites:
#   - NSIS 3.x (`apt install nsis`). Runs natively on Linux — NSIS has a
#     native Linux port, no Wine needed for the installer-build step.
#   - Python 3.11+ with the mde package installed somewhere resolvable
#     (for version detection). Same resolver as build.sh — prefers the
#     `algo` mamba env, falls back to `python` on PATH.
#
# Usage:
#   bash packaging/make-installer-windows.sh --dist-dir=build/win/deployment/mde_launch.dist
#   bash packaging/make-installer-windows.sh --dist-dir=... --output=./out.exe
#   bash packaging/make-installer-windows.sh --dist-dir=... --build-dir=/tmp/out

set -euo pipefail

# -------- Args ----------------------------------------------------------------
DIST_DIR=""
OUTPUT=""
BUILD_DIR=""
for arg in "$@"; do
    case "$arg" in
        --dist-dir=*)   DIST_DIR="${arg#--dist-dir=}" ;;
        --output=*)     OUTPUT="${arg#--output=}" ;;
        --build-dir=*)  BUILD_DIR="${arg#--build-dir=}" ;;
        -h|--help)
            sed -n '1,/^set -euo/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

if [ -z "$DIST_DIR" ]; then
    echo "ERROR: --dist-dir=PATH is required" >&2
    exit 2
fi
if [ ! -d "$DIST_DIR" ]; then
    echo "ERROR: dist dir not found: $DIST_DIR" >&2
    exit 1
fi
# Accept either name: native build renames to mde.exe, Wine build keeps mde_launch.exe.
if [ ! -f "$DIST_DIR/mde.exe" ] && [ ! -f "$DIST_DIR/mde_launch.exe" ]; then
    echo "ERROR: no mde.exe or mde_launch.exe in $DIST_DIR — is that a Nuitka standalone dist?" >&2
    exit 1
fi

# -------- Paths ---------------------------------------------------------------
PACKAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PACKAGING_DIR/.." && pwd)"
[ -z "$BUILD_DIR" ] && BUILD_DIR="$REPO_ROOT/build"
mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
DIST_DIR="$(cd "$DIST_DIR" && pwd)"

NSI_SCRIPT="$PACKAGING_DIR/windows/installer.nsi"
ICON="$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-mark-solid-win10.ico"

[ -f "$NSI_SCRIPT" ] || { echo "Missing $NSI_SCRIPT" >&2; exit 1; }
[ -f "$ICON" ]       || { echo "Missing $ICON" >&2; exit 1; }

# Find makensis. On Linux `apt install nsis` puts it on PATH directly. On
# Windows after `choco install nsis`, PATH propagation into the current bash
# step can be flaky — fall back to common install locations. Chocolatey's
# NSIS installs under "Program Files (x86)\NSIS\" on 64-bit Windows.
MAKENSIS=""
if command -v makensis >/dev/null 2>&1; then
    MAKENSIS=makensis
else
    for candidate in \
        "/c/Program Files (x86)/NSIS/makensis.exe" \
        "/c/Program Files/NSIS/makensis.exe"; do
        [ -x "$candidate" ] && MAKENSIS="$candidate" && break
    done
fi
if [ -z "$MAKENSIS" ]; then
    echo "ERROR: makensis not found." >&2
    echo "       apt install nsis   (Linux)" >&2
    echo "       choco install nsis (Windows)" >&2
    exit 1
fi

# NSIS on Windows is a Windows PE tool; forward-slash POSIX paths from
# Git Bash (e.g. /d/a/mde/...) get fed through MSYS's argument-
# translation layer, which is flaky for -D<name>=<value> forms. Convert
# any paths we pass to makensis into Windows-friendly forward-slash paths
# (D:/a/mde/...) via cygpath -m — same as build-windows-native.sh.
to_win() { command -v cygpath >/dev/null && cygpath -m "$1" || echo "$1"; }

# -------- Version -------------------------------------------------------------
# Prefer mamba env 'algo' if present (matches build.sh pattern); else plain python.
if command -v mamba >/dev/null 2>&1 && mamba env list 2>/dev/null | awk '{print $1}' | grep -qx algo; then
    PY=(mamba run -n algo python)
else
    PY=(python)
fi
VERSION=$("${PY[@]}" -c "from importlib.metadata import version; print(version('markdown-editor'))" 2>/dev/null || echo "0.0.0")

[ -z "$OUTPUT" ] && OUTPUT="$BUILD_DIR/MarkdownEditor-${VERSION}-x86_64-setup.exe"

echo "==> building Windows installer"
echo "    dist:    $DIST_DIR"
echo "    version: $VERSION"
echo "    icon:    $ICON"
echo "    script:  $NSI_SCRIPT"
echo "    output:  $OUTPUT"

# -------- Run makensis --------------------------------------------------------
# -V3 shows warnings + the final "Install size" summary but not every file
# copied (-V4 would be noisy for a 527 MB dist). Paths are pre-converted to
# Windows-style via to_win() so makensis.exe gets unambiguous inputs.
"$MAKENSIS" -V3 \
    -DSOURCE_DIR="$(to_win "$DIST_DIR")" \
    -DAPP_VERSION="$VERSION" \
    -DAPP_ICON="$(to_win "$ICON")" \
    -DOUTPUT_FILE="$(to_win "$OUTPUT")" \
    "$(to_win "$NSI_SCRIPT")"

# -------- Report --------------------------------------------------------------
if [ -f "$OUTPUT" ]; then
    echo ""
    echo "==> built installer: $OUTPUT  ($(du -h "$OUTPUT" | cut -f1))"
    echo "    Test under Wine:  WINEPREFIX=$BUILD_DIR/wine wine \"$OUTPUT\""
    echo "    or via install:   bash packaging/run-wine.sh --exe=\"$OUTPUT\""
else
    echo "==> expected installer not found at $OUTPUT" >&2
    exit 1
fi
