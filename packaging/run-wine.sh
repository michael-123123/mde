#!/usr/bin/env bash
# Launch a Windows mde .exe under Wine using the project's isolated bottle
# and the Chromium flags required for QtWebEngine to render under Wine.
#
# Usage:
#   bash packaging/run-wine.sh                       # default exe + no args → opens empty GUI
#   bash packaging/run-wine.sh README.md             # default exe, open README.md
#   bash packaging/run-wine.sh --version             # default exe, --version
#   bash packaging/run-wine.sh stats README.md       # default exe, CLI subcommand
#   bash packaging/run-wine.sh --exe=/path/to/mde.exe [args...]   # custom exe
#   bash packaging/run-wine.sh --build-dir=/tmp/out [args...]      # custom bottle location
#
# Default exe, tried in order:
#   $BUILD_DIR/win/deployment/mde_launch.dist/mde_launch.exe     (standalone)
#   $BUILD_DIR/win/deployment/mde_launch.exe                     (onefile)
#
# The Chromium flags are **Wine-only**; on real Windows these aren't needed
# (and some would weaken security). They live here, not in the .exe, so the
# shipped binary stays clean for end users.
#
# Prerequisite: `bash packaging/build-windows.sh` has been run at least once,
# so the bottle at $BUILD_DIR/wine exists.

set -euo pipefail

# -------- Args ---------------------------------------------------------------
EXE=""
BUILD_DIR=""
# Pull --exe= and --build-dir= out of argv; everything else passes to the .exe.
PASSTHRU=()
for arg in "$@"; do
    case "$arg" in
        --exe=*)        EXE="${arg#--exe=}" ;;
        --build-dir=*)  BUILD_DIR="${arg#--build-dir=}" ;;
        --wine-help)
            sed -n '1,/^set -euo/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0 ;;
        *) PASSTHRU+=("$arg") ;;
    esac
done

# -------- Paths --------------------------------------------------------------
PACKAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PACKAGING_DIR/.." && pwd)"
if [ -z "$BUILD_DIR" ]; then BUILD_DIR="$REPO_ROOT/build"; fi
BUILD_DIR="$(cd "$BUILD_DIR" 2>/dev/null && pwd || echo "$BUILD_DIR")"

if [ -z "$EXE" ]; then
    for candidate in \
        "$BUILD_DIR/win/deployment/mde_launch.dist/mde_launch.exe" \
        "$BUILD_DIR/win/deployment/mde_launch.exe"; do
        if [ -f "$candidate" ]; then EXE="$candidate"; break; fi
    done
fi

if [ -z "$EXE" ] || [ ! -f "$EXE" ]; then
    echo "ERROR: no .exe found. Tried:" >&2
    echo "  $BUILD_DIR/win/deployment/mde_launch.dist/mde_launch.exe" >&2
    echo "  $BUILD_DIR/win/deployment/mde_launch.exe" >&2
    echo "Run 'bash packaging/build-windows.sh' first, or pass --exe=<path>." >&2
    exit 1
fi

if [ ! -d "$BUILD_DIR/wine" ]; then
    echo "ERROR: no Wine bottle at $BUILD_DIR/wine" >&2
    echo "Run 'bash packaging/build-windows.sh' first, or pass --build-dir=<dir>" \
         "pointing at a dir whose 'wine/' subdir is a valid bottle." >&2
    exit 1
fi

if ! command -v wine >/dev/null; then
    echo "ERROR: wine not installed (apt install wine64)" >&2
    exit 1
fi

# -------- Isolation env + Wine-compat Chromium flags -------------------------
export WINEPREFIX="$BUILD_DIR/wine"
export WINEARCH=win64
export WINEDLLOVERRIDES="winemenubuilder.exe=d"
export XDG_DATA_HOME="$BUILD_DIR/wine-xdg/data"
export XDG_CONFIG_HOME="$BUILD_DIR/wine-xdg/config"
export XDG_CACHE_HOME="$BUILD_DIR/wine-xdg/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"

# LANG/LC_ALL — Wine returns LOCALE_NEUTRAL (0x1000) without this, which .NET
# and some Qt code paths reject. Harmless if already set.
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

# QtWebEngine/Chromium flags, Wine-only (see build-windows.sh header for per-flag
# rationale, sourced from slop/bim-assistant/plugin/run-devshell-wine.sh).
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---single-process --no-sandbox --disable-gpu --use-angle=swiftshader --disable-direct-composition --disable-d3d11 --disable-dev-shm-usage}"

# Silence Wine fixme/err noise by default. Override with WINEDEBUG=+loaddll etc.
export WINEDEBUG="${WINEDEBUG:--all}"

# -------- Run ----------------------------------------------------------------
echo "==> wine $EXE ${PASSTHRU[*]:-}"
echo "    bottle: $WINEPREFIX"
exec wine "$EXE" "${PASSTHRU[@]}"
