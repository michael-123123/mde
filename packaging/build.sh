#!/usr/bin/env bash
# Bootstrap script: build a standalone/onefile Linux binary of mde using
# pyside6-deploy + Nuitka, optionally packaged as an AppImage.
#
# Inputs (tracked in git, next to this script):
#   - pysidedeploy.spec   (Nuitka + pyside6-deploy config)
#   - mde_launch.py       (entry point that dispatches to the full CLI)
#
# These inputs are never modified by the script — they are copied into the
# build dir at the start of each run, and the copies are patched with per-run
# values (mode, --jobs, etc.). Fresh copies every run = reproducible builds
# + no git dirt.
#
# Usage:
#   bash packaging/build.sh                        # default: onefile mode
#   bash packaging/build.sh --mode=standalone      # build a dist folder only
#   bash packaging/build.sh --appimage             # standalone + AppImage
#   bash packaging/build.sh --mode=standalone --appimage   # same thing
#   bash packaging/build.sh --jobs=4               # CPU cap (default: floor(nproc/2))
#   bash packaging/build.sh --build-dir=/tmp/out   # output dir (default: <repo>/build)
#   bash packaging/build.sh --clean                # wipe outputs in build dir
#   bash packaging/build.sh --clean-all            # also wipe cached .appdir and .tools/
#
# Output (always under $BUILD_DIR, default <repo>/build/, all gitignored):
#   - onefile:     mde.bin                                          (single ~180 MB exec)
#   - standalone:  mde.dist/mde_launch.bin + mde.dist/ folder       (~590 MB)
#   - appimage:    MarkdownEditor-<version>-x86_64.AppImage          (single ~220 MB exec)
#
# Runtime notes for the produced AppImage:
#   - Packaged with the AppImage *static* runtime (see APPIMAGE_RUNTIME_URL
#     below), which embeds libfuse inside the image itself. End users therefore
#     do NOT need libfuse2 installed — this is the main issue on Ubuntu 24.04+
#     where libfuse2 was dropped from the default install.
#   - If the host has no FUSE kernel support at all (WSL1, minimal containers,
#     hardened sandboxes), end users can still launch via:
#         ./MarkdownEditor-*-x86_64.AppImage --appimage-extract-and-run
#     which extracts to a temp dir and runs from there — no mount needed.
#
# One-time prerequisites (not auto-installed by this script):
#   1. mamba (or conda) with an 'algo' env on Python 3.11+:
#        mamba create -n algo python=3.12
#   2. Project deps in that env (pulls PySide6, markdown, pygments, weasyprint,
#      pydantic, Nuitka, patchelf, argcomplete, etc. from pyproject.toml):
#        mamba run -n algo pip install -e ".[build]"
#   3. A system C toolchain (Nuitka compiles Python -> C -> native):
#        Ubuntu/Debian:  sudo apt install build-essential
#        Fedora/RHEL:    sudo dnf group install "Development Tools"
#        macOS:          xcode-select --install   (not tested for mde yet)
#   4. For --appimage: curl or wget (for the one-time appimagetool + runtime
#      downloads; both are cached under $BUILD_DIR/.tools/ and reused).
#
# Runtime-optional system tools (not bundled, detected at runtime): pandoc,
# graphviz, mmdc — see CLAUDE.md "Optional System Dependencies".

set -euo pipefail

# -------- Defaults / args -----------------------------------------------------
MODE="onefile"
JOBS=""
CLEAN=0
CLEAN_ALL=0
APPIMAGE=0
BUILD_DIR=""
for arg in "$@"; do
    case "$arg" in
        --mode=*)       MODE="${arg#--mode=}" ;;
        --jobs=*)       JOBS="${arg#--jobs=}" ;;
        --build-dir=*)  BUILD_DIR="${arg#--build-dir=}" ;;
        --clean)        CLEAN=1 ;;
        --clean-all)    CLEAN=1; CLEAN_ALL=1 ;;
        --appimage)     APPIMAGE=1 ;;
        -h|--help)
            sed -n '1,/^set -euo/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

if [ -z "$JOBS" ]; then
    JOBS=$(( $(nproc 2>/dev/null || echo 2) / 2 ))
    [ "$JOBS" -lt 1 ] && JOBS=1
fi

case "$MODE" in
    onefile|standalone) ;;
    *) echo "--mode must be onefile or standalone (got: $MODE)" >&2; exit 2 ;;
esac

# --appimage needs the standalone dist. If user asked for onefile + appimage,
# override to standalone (the onefile would not be used anyway).
if [ "$APPIMAGE" -eq 1 ] && [ "$MODE" = "onefile" ]; then
    echo "==> --appimage requires the standalone dist; switching mode=standalone"
    MODE="standalone"
fi

# -------- Paths ---------------------------------------------------------------
# PACKAGING_DIR = this script's directory (holds the tracked inputs).
# REPO_ROOT    = parent of PACKAGING_DIR.
# BUILD_DIR    = --build-dir arg, or <repo>/build.
PACKAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PACKAGING_DIR/.." && pwd)"
if [ -z "$BUILD_DIR" ]; then
    BUILD_DIR="$REPO_ROOT/build"
fi
mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"   # resolve to absolute

SPEC_SRC="$PACKAGING_DIR/pysidedeploy.spec"
LAUNCH_SRC="$PACKAGING_DIR/mde_launch.py"
SPEC="$BUILD_DIR/pysidedeploy.spec"
LAUNCH="$BUILD_DIR/mde_launch.py"

APPDIR="$BUILD_DIR/.appdir"
TOOLS_DIR="$BUILD_DIR/.tools"
APPIMAGETOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
# Static AppImage runtime — embeds FUSE so end-users don't need libfuse2.
APPIMAGE_RUNTIME="$TOOLS_DIR/runtime-x86_64"
APPIMAGE_RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"

if [ ! -f "$SPEC_SRC" ];   then echo "Missing $SPEC_SRC" >&2;   exit 1; fi
if [ ! -f "$LAUNCH_SRC" ]; then echo "Missing $LAUNCH_SRC" >&2; exit 1; fi

echo "==> mde build"
echo "    mode:     $MODE"
echo "    appimage: $([ "$APPIMAGE" -eq 1 ] && echo yes || echo no)"
echo "    jobs:     $JOBS"
echo "    repo:     $REPO_ROOT"
echo "    build:    $BUILD_DIR"

# -------- Clean (optional) ----------------------------------------------------
if [ "$CLEAN" -eq 1 ]; then
    echo "==> cleaning build output"
    rm -rf "$BUILD_DIR/mde.dist" "$BUILD_DIR/deployment" "$BUILD_DIR/mde.bin" "$APPDIR"
    rm -f  "$BUILD_DIR"/MarkdownEditor-*-x86_64.AppImage
fi
if [ "$CLEAN_ALL" -eq 1 ]; then
    echo "==> cleaning cached tools"
    rm -rf "$TOOLS_DIR"
fi

# -------- Stage inputs in build dir -------------------------------------------
# Fresh copies every run — the tracked originals in packaging/ are never touched.
cp "$SPEC_SRC"   "$SPEC"
cp "$LAUNCH_SRC" "$LAUNCH"

# Patch the staged spec with per-run values:
#   1) set mode=<arg>
#   2) append --jobs=$JOBS to extra_args
#   3) rewrite the input_file / project_dir / exec_directory / icon paths so
#      they point at the (possibly non-default) $BUILD_DIR / repo paths.
ICON_ABS="$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-editor-256.png"
sed -i \
    -e "s|^mode = .*|mode = $MODE|" \
    -e "/^extra_args = /s|\$| --jobs=$JOBS|" \
    -e "s|^project_dir = .*|project_dir = $BUILD_DIR|" \
    -e "s|^input_file = .*|input_file = $LAUNCH|" \
    -e "s|^exec_directory = .*|exec_directory = $BUILD_DIR|" \
    -e "s|^icon = .*|icon = $ICON_ABS|" \
    "$SPEC"

echo "==> staged spec (at $SPEC):"
grep -E "^mode|^extra_args|^input_file|^project_dir|^exec_directory|^icon" "$SPEC" | sed 's/^/    /'

# -------- Build via pyside6-deploy --------------------------------------------
# See comments inline in the tracked spec / this header for why each flag is
# there (--static-libpython=no, --include-package=..., --include-package-data=...,
# --noinclude-dlls=libsmime3.so|libfontconfig.so.1, --noinclude-qt-translations).
# The launcher sets FONTCONFIG_PATH=/etc/fonts and neutralizes pygments'
# entry-point plugin discovery.

mamba run -n algo pyside6-deploy -c "$SPEC" -f

# -------- Post-build cleanup --------------------------------------------------
# Belt-and-braces: Nuitka's pyside6 plugin sometimes re-adds libfontconfig
# despite --noinclude-dlls. Remove it from the standalone dist so the system
# copy is used. For onefile this would be inside the packed archive already.
if [ -f "$BUILD_DIR/mde.dist/libfontconfig.so.1" ]; then
    echo "==> post-build: removing bundled libfontconfig.so.1 from dist"
    rm "$BUILD_DIR/mde.dist/libfontconfig.so.1"
fi

# -------- AppImage packaging (optional) ---------------------------------------
if [ "$APPIMAGE" -eq 1 ]; then
    echo ""
    echo "==> packaging AppImage"

    VERSION=$(mamba run -n algo python -c \
        "from importlib.metadata import version; print(version('markdown-editor'))" \
        2>/dev/null || echo "0.0.0")
    APPIMAGE_OUT="$BUILD_DIR/MarkdownEditor-${VERSION}-x86_64.AppImage"
    echo "    version:  $VERSION"
    echo "    output:   $APPIMAGE_OUT"

    mkdir -p "$TOOLS_DIR"
    _fetch() {
        local url="$1"; local dest="$2"
        echo "==> downloading (one-time) $(basename "$dest")"
        if command -v curl >/dev/null; then
            curl -fL --progress-bar "$url" -o "$dest"
        elif command -v wget >/dev/null; then
            wget -q --show-progress "$url" -O "$dest"
        else
            echo "Need curl or wget to download $(basename "$dest")" >&2
            exit 1
        fi
    }
    if [ ! -x "$APPIMAGETOOL" ]; then
        _fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL"; chmod +x "$APPIMAGETOOL"
    fi
    if [ ! -f "$APPIMAGE_RUNTIME" ]; then
        _fetch "$APPIMAGE_RUNTIME_URL" "$APPIMAGE_RUNTIME"
    fi

    # Build the AppDir from scratch each time so stale files don't leak.
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
             "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    # Copy the entire standalone dist into usr/bin/. The main binary will be at
    # $APPDIR/usr/bin/mde_launch.bin; relative paths inside the dist (RPATHs,
    # Qt plugin search) all resolve correctly from this layout.
    cp -a "$BUILD_DIR/mde.dist/." "$APPDIR/usr/bin/"

    # The bundled launcher isn't meant to run as ARGV0 from a random cwd,
    # so we wrap it in an AppRun script that resolves its own dir and execs
    # the binary with the user's args.
    cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export APPDIR="$HERE"
exec "$HERE/usr/bin/mde_launch.bin" "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"

    # Top-level .desktop and icon are required by appimagetool.
    DESKTOP_SRC="$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-editor.desktop"
    DESKTOP_TOP="$APPDIR/markdown-editor.desktop"
    DESKTOP_USR="$APPDIR/usr/share/applications/markdown-editor.desktop"
    sed 's|^Exec=.*|Exec=AppRun %F|' "$DESKTOP_SRC" > "$DESKTOP_TOP"
    cp "$DESKTOP_TOP" "$DESKTOP_USR"

    ICON_SRC="$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-editor-256.png"
    cp "$ICON_SRC" "$APPDIR/markdown-editor.png"
    cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/markdown-editor.png"

    # --appimage-extract-and-run avoids needing FUSE on the build host.
    # --runtime-file embeds the static runtime so the end-user host doesn't
    # need libfuse2 either.
    echo "==> running appimagetool (static runtime)"
    ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run \
        --runtime-file "$APPIMAGE_RUNTIME" \
        "$APPDIR" "$APPIMAGE_OUT"
fi

# -------- Report --------------------------------------------------------------
echo ""
if [ "$APPIMAGE" -eq 1 ]; then
    if [ -f "$APPIMAGE_OUT" ]; then
        echo "==> built AppImage:         $APPIMAGE_OUT  ($(du -h "$APPIMAGE_OUT" | cut -f1))"
        echo "    Launch:   chmod +x $APPIMAGE_OUT && $APPIMAGE_OUT [file.md]"
    else
        echo "==> expected AppImage not found at $APPIMAGE_OUT" >&2
        exit 1
    fi
elif [ "$MODE" = "onefile" ]; then
    OUT="$BUILD_DIR/mde.bin"
    if [ -f "$OUT" ]; then
        echo "==> built onefile binary:   $OUT  ($(du -h "$OUT" | cut -f1))"
        echo "    Launch:   $OUT [file.md]"
    else
        echo "==> expected onefile output not found at $OUT" >&2
        exit 1
    fi
else
    OUT="$BUILD_DIR/mde.dist/mde_launch.bin"
    if [ -f "$OUT" ]; then
        SIZE=$(du -sh "$BUILD_DIR/mde.dist" | cut -f1)
        echo "==> built standalone dist:  $BUILD_DIR/mde.dist  ($SIZE)"
        echo "    Launch:   $OUT [file.md]"
    else
        echo "==> expected standalone output not found at $OUT" >&2
        exit 1
    fi
fi
