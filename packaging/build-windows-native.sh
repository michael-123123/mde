#!/usr/bin/env bash
# Build a Windows .exe of mde on a native Windows host (dev box or GHA
# `windows-latest` runner). Native sibling of packaging/build.sh (Linux).
#
# For building from Linux via Wine — a genuinely different pipeline with
# bottle setup, depends.exe workarounds, MSVC runtime staging, ICU DLL
# staging, Chromium flags — see packaging/build-windows.sh. Real Windows
# needs none of those: the OS provides MSVC redist + ICU, Nuitka compiles
# with the preinstalled MSVC/MinGW, and Qt resolves its DLL imports
# naturally against System32 + the PySide6 wheel.
#
# Inputs (tracked in git, next to this script):
#   - pysidedeploy.windows.spec   Windows-specific Nuitka config (no Linux-
#                                 only DLL excludes, .ico icon, Nuitka pin)
#   - mde_launch.py               Launcher, shared with the Linux build
#
# Usage (mirrors packaging/build.sh):
#   bash packaging/build-windows-native.sh                   # default: onefile
#   bash packaging/build-windows-native.sh --mode=standalone
#   bash packaging/build-windows-native.sh --jobs=4          # default: floor(nproc/2)
#   bash packaging/build-windows-native.sh --build-dir=C:/out
#   bash packaging/build-windows-native.sh --clean
#
# Prerequisites (not auto-installed):
#   1. Python 3.12 on PATH
#        GHA:       actions/setup-python@v5
#        Dev box:   python.org installer or conda
#   2. Git for Windows (provides Git Bash — the shell this script runs in)
#   3. Project + build deps:  pip install -e ".[build]"
#      (brings PySide6, Nuitka, etc.)

set -euo pipefail

# -------- Defaults / args -----------------------------------------------------
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

# -------- Paths ---------------------------------------------------------------
PACKAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PACKAGING_DIR/.." && pwd)"
[ -z "$BUILD_DIR" ] && BUILD_DIR="$REPO_ROOT/build"
mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
WIN_OUT="$BUILD_DIR/win"
SPEC_SRC="$PACKAGING_DIR/pysidedeploy.windows.spec"
LAUNCH_SRC="$PACKAGING_DIR/mde_launch.py"

[ -f "$SPEC_SRC" ]   || { echo "Missing $SPEC_SRC" >&2;   exit 1; }
[ -f "$LAUNCH_SRC" ] || { echo "Missing $LAUNCH_SRC" >&2; exit 1; }
command -v python >/dev/null         || { echo "python not on PATH" >&2; exit 1; }
command -v pyside6-deploy >/dev/null || { echo "pyside6-deploy not on PATH (run: pip install -e '.[build]')" >&2; exit 1; }

echo "==> mde Windows build (native)"
echo "    mode:    $MODE"
echo "    jobs:    $JOBS"
echo "    python:  $(python --version 2>&1)"
echo "    repo:    $REPO_ROOT"
echo "    build:   $BUILD_DIR"

# -------- Clean (optional) ----------------------------------------------------
if [ "$CLEAN" -eq 1 ]; then
    echo "==> cleaning $WIN_OUT"
    rm -rf "$WIN_OUT"
fi
mkdir -p "$WIN_OUT"

# -------- Stage inputs in build dir ------------------------------------------
# Same pattern as packaging/build.sh: copy tracked spec + launcher into the
# build dir and patch per-run values (paths, mode, --jobs) on the copy so
# the committed files stay pristine.
#
# Use forward slashes for Windows paths via `cygpath -m` — Python, Nuitka,
# and pyside6-deploy all accept them, and they avoid the shlex-eats-
# backslash pitfall if any future change injects paths into extra_args.
to_win() { command -v cygpath >/dev/null && cygpath -m "$1" || echo "$1"; }

WIN_SPEC="$WIN_OUT/pysidedeploy.spec"
WIN_LAUNCH="$WIN_OUT/mde_launch.py"
WIN_ICON="$(to_win "$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-mark-solid-win10.ico")"
WIN_OUT_W="$(to_win "$WIN_OUT")"
WIN_LAUNCH_W="$(to_win "$WIN_LAUNCH")"

cp "$SPEC_SRC"   "$WIN_SPEC"
cp "$LAUNCH_SRC" "$WIN_LAUNCH"

sed -i \
    -e "s|^mode = .*|mode = $MODE|" \
    -e "/^extra_args = /s|\$| --jobs=$JOBS --assume-yes-for-downloads|" \
    -e "s|^project_dir = .*|project_dir = $WIN_OUT_W|" \
    -e "s|^input_file = .*|input_file = $WIN_LAUNCH_W|" \
    -e "s|^exec_directory = .*|exec_directory = $WIN_OUT_W|" \
    -e "s|^icon = .*|icon = $WIN_ICON|" \
    "$WIN_SPEC"
# --assume-yes-for-downloads: on first run Nuitka needs to download
# depends.exe (for DLL dependency analysis). Without this flag it prompts
# interactively on stdin and defaults to "no" in non-interactive contexts
# like GHA runners. Wine build sidesteps this by invoking Nuitka directly
# with the flag; on native Windows we have to bake it into the spec.

echo "==> staged spec (at $WIN_SPEC):"
grep -E "^mode|^extra_args|^input_file|^project_dir|^exec_directory|^icon" "$WIN_SPEC" | sed 's/^/    /'

# -------- Build via pyside6-deploy --------------------------------------------
# Fail fast if PySide6 can't be imported — Nuitka's pyside6 plugin does the
# same import during its build-time scan, so a 15-minute Nuitka run that ends
# with "PySide6 not installed" is a waste.
python -c "from PySide6 import QtCore; import sys; sys.stderr.write(f'PySide6 {QtCore.__version__} ready\n')"
pyside6-deploy -c "$(to_win "$WIN_SPEC")" -f

# -------- Report --------------------------------------------------------------
# pyside6-deploy places its final output in $exec_directory (= $WIN_OUT),
# renamed from mde_launch.* to match the spec's `title = mde`. Nuitka's
# intermediate output under $WIN_OUT/deployment/ is kept for inspection
# but is NOT where the shipped artifact lives.
if [ "$MODE" = "onefile" ]; then
    OUT="$WIN_OUT/mde.exe"
else
    OUT="$WIN_OUT/mde.dist/mde_launch.exe"
fi
if [ -f "$OUT" ]; then
    echo "==> built Windows binary: $OUT  ($(du -h "$OUT" | cut -f1))"
else
    echo "==> expected output not found at $OUT" >&2
    exit 1
fi
