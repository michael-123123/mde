#!/usr/bin/env bash
# Bootstrap script: build a Windows .exe of mde on a native Windows host.
#
# Use this when:
#   - You're a developer on Windows with Git Bash + Python 3.12.
#   - You're running inside a GHA `windows-latest` runner.
#
# For building from Linux via Wine, see packaging/build-windows.sh.
#
# What this script does NOT do:
#   - No Wine bottle setup (we're on real Windows).
#   - No winetricks, no mfc42, no 32-bit depends.exe — all Wine workarounds
#     for problems that don't occur on real Windows.
#   - No Chromium-flag smoke test — GHA runners are headless; and on a dev
#     box you just double-click the .exe.
#   - No pyside6-deploy bypass — the subprocess-exit-code quirk that forced
#     bypass under Wine doesn't reproduce on real Windows.
#
# What this script DOES do:
#   - Downloads ICU 73.2 and stages the DLLs (into site-packages/PySide6/ and
#     into a staging dir for Nuitka's --include-data-files). Qt 6.11's
#     qt6core.dll imports icuuc.dll, which neither the PySide6 wheel nor
#     a fresh Windows install provides in the form Qt expects. Same problem
#     we solved under Wine.
#   - Stages the shared pysidedeploy.windows.spec + launcher, substitutes
#     per-run paths/mode/jobs.
#   - Runs pyside6-deploy to produce build/win/deployment/mde_launch.exe.
#
# Usage:
#   bash packaging/build-windows-native.sh                     # default: onefile
#   bash packaging/build-windows-native.sh --mode=standalone
#   bash packaging/build-windows-native.sh --jobs=4            # default: floor(nproc/2)
#   bash packaging/build-windows-native.sh --build-dir=C:/out  # default: <repo>/build
#   bash packaging/build-windows-native.sh --clean             # wipe build/win output
#
# Prerequisites:
#   1. Python 3.12 on PATH.
#        GHA:       actions/setup-python@v5 with python-version '3.12'.
#        Dev box:   python.org installer or `conda install python=3.12`.
#   2. Git for Windows (provides Git Bash, unzip, curl, cygpath).
#   3. Project deps installed:
#        pip install -e ".[build]"
#      The GHA workflow does this in a separate step; dev boxes can run it
#      from the script if missing.

set -euo pipefail

# ============================================================================
# Args
# ============================================================================
MODE="onefile"
JOBS=""
CLEAN=0
BUILD_DIR=""
for arg in "$@"; do
    case "$arg" in
        --mode=*)       MODE="${arg#--mode=}" ;;
        --jobs=*)       JOBS="${arg#--jobs=}" ;;
        --build-dir=*)  BUILD_DIR="${arg#--build-dir=}" ;;
        --clean)        CLEAN=1 ;;
        -h|--help)
            sed -n '1,/^set -euo/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done
if [ -z "$JOBS" ]; then
    JOBS=$(( $(nproc 2>/dev/null || echo 2) / 2 ))
    [ "$JOBS" -lt 1 ] && JOBS=1
fi
case "$MODE" in onefile|standalone) ;; *) echo "--mode must be onefile or standalone" >&2; exit 2 ;; esac

# ============================================================================
# Paths
# ============================================================================
PACKAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PACKAGING_DIR/.." && pwd)"
if [ -z "$BUILD_DIR" ]; then BUILD_DIR="$REPO_ROOT/build"; fi
mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"

TOOLS_DIR="$BUILD_DIR/.tools"
WIN_OUT="$BUILD_DIR/win"
SPEC_SRC="$PACKAGING_DIR/pysidedeploy.windows.spec"
LAUNCH_SRC="$PACKAGING_DIR/mde_launch.py"

# ICU 73.2 — same story as build-windows.sh; Qt 6.9/6.10/6.11 need ICU 73
# and PySide6 wheels don't bundle it. icudt73.dll is intentionally excluded
# because Nuitka's pyside6 plugin already bundles it (error on conflict).
ICU_URL="https://github.com/unicode-org/icu/releases/download/release-73-2/icu4c-73_2-Win64-MSVC2019.zip"
ICU_DLLS="icuuc icuin icuio icutu"
ICU_ZIP="$TOOLS_DIR/icu4c-73_2-Win64-MSVC2019.zip"
ICU_EXTRACT="$TOOLS_DIR/icu73"
ICU_STAGE="$TOOLS_DIR/icu-stage"

if [ ! -f "$SPEC_SRC" ];   then echo "Missing $SPEC_SRC" >&2;   exit 1; fi
if [ ! -f "$LAUNCH_SRC" ]; then echo "Missing $LAUNCH_SRC" >&2; exit 1; fi
if ! command -v python >/dev/null; then
    echo "ERROR: python not on PATH. Install Python 3.12 first." >&2
    exit 1
fi
if ! command -v pyside6-deploy >/dev/null; then
    echo "ERROR: pyside6-deploy not on PATH. Run 'pip install -e \".[build]\"' first." >&2
    exit 1
fi

PY_VERSION=$(python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
echo "==> mde Windows build (native)"
echo "    mode:    $MODE"
echo "    jobs:    $JOBS"
echo "    python:  $(python --version 2>&1) ($(command -v python))"
echo "    repo:    $REPO_ROOT"
echo "    build:   $BUILD_DIR"

# ============================================================================
# Clean
# ============================================================================
if [ "$CLEAN" -eq 1 ]; then
    echo "==> cleaning Windows build output"
    rm -rf "$WIN_OUT"
fi
mkdir -p "$TOOLS_DIR" "$WIN_OUT"

# ============================================================================
# Helpers
# ============================================================================
# Convert a Git-Bash POSIX path to a forward-slash Windows path
# (e.g. /d/a/mde -> D:/a/mde). Python and Nuitka both accept this on Windows.
#
# We deliberately use -m (mixed mode, forward slashes) rather than -w
# (native Windows backslashes). Reason: pyside6-deploy reads the spec's
# `extra_args` line and pipes it through Python's shlex.split() in POSIX
# mode, which eats backslashes — turning `D:\a\mde\...icuin.dll` into the
# nonsense `D:amde...icuin.dll` before Nuitka sees it. Forward slashes
# survive shlex intact.
to_win() {
    if command -v cygpath >/dev/null; then
        cygpath -m "$1"
    else
        # Fallback: naive /c/foo -> C:/foo (forward slashes, same reason)
        echo "$1" | sed -E 's|^/([a-zA-Z])/|\U\1:/|'
    fi
}

# ============================================================================
# Fetch + stage ICU 73.2 DLLs
# ============================================================================
if [ ! -f "$ICU_ZIP" ]; then
    echo "==> downloading ICU 73.2 Win64 MSVC2019"
    curl -fL --progress-bar "$ICU_URL" -o "$ICU_ZIP"
fi
if [ ! -d "$ICU_EXTRACT/bin64" ]; then
    rm -rf "$ICU_EXTRACT" && mkdir -p "$ICU_EXTRACT"
    echo "==> extracting ICU zip (outer + inner)"
    unzip -oq "$ICU_ZIP" -d "$ICU_EXTRACT/outer"
    INNER_ZIP=$(find "$ICU_EXTRACT/outer" -name "icu-windows.zip" | head -1)
    unzip -oq "$INNER_ZIP" -d "$ICU_EXTRACT"
fi

# Stage into site-packages/PySide6/ so `python -c "from PySide6 import QtCore"`
# works on this host (Nuitka's pyside6 plugin does this import during its
# build-time scan, so it MUST work before we invoke pyside6-deploy).
#
# Python prints a Windows backslash path on GHA windows-latest
# (C:\hostedtoolcache\...\PySide6). Mixed separators in Git Bash's cp
# destination (`"$BS_PATH/foo.dll"`) are unreliable — copies can land in the
# wrong place or no-op silently. Normalize to POSIX via cygpath first.
PYSIDE6_DIR=$(python -c "import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent)" 2>/dev/null || echo "")
if [ -z "$PYSIDE6_DIR" ]; then
    echo "ERROR: could not resolve PySide6 install dir (is PySide6 installed?)" >&2
    exit 1
fi
if command -v cygpath >/dev/null; then
    PYSIDE6_DIR=$(cygpath -u "$PYSIDE6_DIR")
fi

# Helper: copy ICU DLLs (both versioned and unsuffixed) from the extracted
# zip into a destination dir. Fails loudly on any missing source or cp error.
stage_icu_dlls() {
    local dest="$1"
    local icu src
    for icu in $ICU_DLLS; do
        src="$ICU_EXTRACT/bin64/${icu}73.dll"
        if [ ! -f "$src" ]; then
            echo "ERROR: ICU source DLL missing: $src" >&2
            echo "       (extraction of $ICU_ZIP to $ICU_EXTRACT may have failed)" >&2
            exit 1
        fi
        cp "$src" "$dest/${icu}73.dll"
        cp "$src" "$dest/${icu}.dll"
    done
}

if [ ! -f "$PYSIDE6_DIR/icuuc73.dll" ]; then
    echo "==> staging ICU 73.2 DLLs into $PYSIDE6_DIR"
    stage_icu_dlls "$PYSIDE6_DIR"
    if [ ! -f "$PYSIDE6_DIR/icuuc73.dll" ]; then
        echo "ERROR: ICU copy into $PYSIDE6_DIR reported success but file missing" >&2
        exit 1
    fi
fi

# Fail fast — if the import still breaks, don't waste 2 minutes inside
# Nuitka before we see a confusing "PySide6 not installed" plugin error.
if ! python -c "from PySide6 import QtCore" 2>/dev/null; then
    echo "ERROR: 'from PySide6 import QtCore' still fails after ICU staging." >&2
    echo "       Run: python -c 'from PySide6 import QtCore' to see the real error." >&2
    python -c "from PySide6 import QtCore" || true
    exit 1
fi

# Stage dedicated dir for Nuitka's --include-data-files (puts ICU INSIDE the
# bundle artifact — works for both standalone and onefile).
if [ ! -f "$ICU_STAGE/icuuc73.dll" ]; then
    echo "==> staging ICU 73.2 DLLs into $ICU_STAGE (for --include-data-files)"
    rm -rf "$ICU_STAGE" && mkdir -p "$ICU_STAGE"
    stage_icu_dlls "$ICU_STAGE"
fi

# ============================================================================
# Stage Windows spec + launcher in $WIN_OUT, patch per-run values
# ============================================================================
WIN_SPEC="$WIN_OUT/pysidedeploy.spec"
WIN_LAUNCH="$WIN_OUT/mde_launch.py"
WIN_ICON_ABS="$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-mark-solid-win10.ico"

cp "$SPEC_SRC"   "$WIN_SPEC"
cp "$LAUNCH_SRC" "$WIN_LAUNCH"

# Append --include-data-files for each ICU DLL to extra_args.
ICU_EXTRA=""
for dll in "$ICU_STAGE"/*.dll; do
    name=$(basename "$dll")
    ICU_EXTRA="$ICU_EXTRA --include-data-files=$(to_win "$dll")=$name"
done

# Rewrite placeholders + append --jobs + ICU.
# Use sed with | separator (paths contain / or \).
# Escape backslashes in Windows paths for sed.
escape_sed() { printf '%s' "$1" | sed 's/[\\&|]/\\&/g'; }

WIN_OUT_WIN=$(to_win "$WIN_OUT")
WIN_LAUNCH_WIN=$(to_win "$WIN_LAUNCH")
WIN_ICON_WIN=$(to_win "$WIN_ICON_ABS")

sed -i \
    -e "s|^mode = .*|mode = $MODE|" \
    -e "/^extra_args = /s|\$| --jobs=$JOBS$(escape_sed "$ICU_EXTRA")|" \
    -e "s|^project_dir = .*|project_dir = $(escape_sed "$WIN_OUT_WIN")|" \
    -e "s|^input_file = .*|input_file = $(escape_sed "$WIN_LAUNCH_WIN")|" \
    -e "s|^exec_directory = .*|exec_directory = $(escape_sed "$WIN_OUT_WIN")|" \
    -e "s|^icon = .*|icon = $(escape_sed "$WIN_ICON_WIN")|" \
    "$WIN_SPEC"

echo "==> staged Windows spec:"
grep -E "^mode|^extra_args|^icon|^input_file|^project_dir|^exec_directory|^packages" "$WIN_SPEC" | sed 's/^/    /'

# ============================================================================
# Run pyside6-deploy
# ============================================================================
echo ""
echo "==> running pyside6-deploy"
cd "$WIN_OUT"
pyside6-deploy -c "$(to_win "$WIN_SPEC")" -f

# ============================================================================
# Report
# ============================================================================
echo ""
if [ "$MODE" = "onefile" ]; then
    OUT="$WIN_OUT/deployment/mde_launch.exe"
else
    OUT="$WIN_OUT/deployment/mde_launch.dist/mde_launch.exe"
fi
if [ -f "$OUT" ]; then
    SIZE=$(du -h "$OUT" | cut -f1)
    echo "==> built Windows binary: $OUT  ($SIZE)"
    if [ "$MODE" = "standalone" ]; then
        DSIZE=$(du -sh "$WIN_OUT/deployment/mde_launch.dist" | cut -f1)
        echo "    dist size: $DSIZE"
    fi
else
    echo "==> expected output not found at $OUT" >&2
    exit 1
fi
