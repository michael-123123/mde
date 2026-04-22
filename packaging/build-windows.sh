#!/usr/bin/env bash
# Bootstrap script: build a Windows .exe of mde on a Linux host via Wine.
#
# End-to-end: sets up an isolated Wine bottle, installs Windows Python + all
# project deps, fetches ICU 73.2 DLLs (Qt 6.11 dynamic dependency), works
# around Wine-specific Nuitka issues (32-bit depends.exe + mfc42), compiles
# mde to a Windows .exe via Nuitka 4.0.8, and bundles ICU DLLs into the
# build artifact via Nuitka's --include-data-files (works for both
# standalone dist and onefile archive).
#
# The script is idempotent: rerunning reuses the bottle, cached downloads,
# and pip deps. `--clean` wipes the build output; `--clean-all` also wipes
# the bottle + tool cache (full reset, ~10-15 minutes to rebuild).
#
# Inputs (tracked in git, next to this script):
#   - pysidedeploy.windows.spec     Nuitka config for Windows target (Nuitka 4.0.8
#                                   pin, no Linux-only DLL excludes, .ico icon).
#   - mde_launch.py                 Same launcher as the Linux build.
#
# Usage:
#   bash packaging/build-windows.sh                      # default: onefile mode
#   bash packaging/build-windows.sh --mode=standalone    # dist folder only
#   bash packaging/build-windows.sh --jobs=4             # CPU cap
#   bash packaging/build-windows.sh --build-dir=/tmp/out # output dir (default: <repo>/build)
#   bash packaging/build-windows.sh --clean              # wipe build output (keep bottle)
#   bash packaging/build-windows.sh --clean-all          # also wipe bottle + cached tools
#   bash packaging/build-windows.sh --smoke-test         # after build, launch .exe under Wine
#                                                        # with Wine-compat Chromium flags and
#                                                        # capture a screenshot to local/tmp/
#
# Sibling script: packaging/run-wine.sh - launches an already-built .exe
# under Wine with the same isolation env + Chromium flags. Useful for
# ad-hoc testing without a full rebuild.
#
# Output under $BUILD_DIR (gitignored):
#   - onefile:    win/mde_launch.exe                   (single exec, needs no install)
#   - standalone: win/mde_launch.dist/mde_launch.exe + DLLs
#   - plus the bottle at $BUILD_DIR/wine/ (~3 GB) and cache at $BUILD_DIR/.tools/
#
# BOTTLE ISOLATION (why the env block below):
#
# A "bottle" in CrossOver/Bottles terminology = a WINEPREFIX in upstream Wine.
# Every `wine` invocation in this script exports these five env vars, scoping
# all writes into $BUILD_DIR/wine/ and $BUILD_DIR/wine-xdg/ and nothing else:
#
#   WINEPREFIX        -> $BUILD_DIR/wine                 the bottle itself
#   WINEARCH=win64    -> 64-bit bottle; must be set at first wineboot
#   WINEDLLOVERRIDES  -> disables winemenubuilder.exe so Wine doesn't write
#                        Start-Menu / MIME entries to ~/.local/share/ et al.
#   XDG_DATA_HOME                                         catches any stray
#   XDG_CONFIG_HOME   -> $BUILD_DIR/wine-xdg/             XDG writes (Mono/Gecko
#   XDG_CACHE_HOME                                        cache, etc.)
#
# After `--clean-all` (or manual `rm -rf $BUILD_DIR/wine $BUILD_DIR/wine-xdg`)
# there is no trace of this project's Wine work anywhere on the host.
#
# One shared path remains: ~/.cache/wine/ holds Mono/Gecko MSI downloads
# shared across prefixes. This is Wine's own download cache, not project-
# specific; it's safe to leave alone or clean via `rm -rf ~/.cache/wine/`.

set -euo pipefail

# ============================================================================
# Args
# ============================================================================
MODE="onefile"
JOBS=""
CLEAN=0
CLEAN_ALL=0
BUILD_DIR=""
SMOKE_TEST=0
for arg in "$@"; do
    case "$arg" in
        --mode=*)       MODE="${arg#--mode=}" ;;
        --jobs=*)       JOBS="${arg#--jobs=}" ;;
        --build-dir=*)  BUILD_DIR="${arg#--build-dir=}" ;;
        --clean)        CLEAN=1 ;;
        --clean-all)    CLEAN=1; CLEAN_ALL=1 ;;
        --smoke-test)   SMOKE_TEST=1 ;;
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

WINE_USER="$(whoami)"
PY_VERSION="3.12.7"
PY_INSTALLER="$TOOLS_DIR/python-${PY_VERSION}-amd64.exe"
PY_INSTALLER_URL="https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-amd64.exe"
WINETRICKS="$TOOLS_DIR/winetricks"
WINETRICKS_URL="https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"
DEPENDS_X86_URL="https://dependencywalker.com/depends22_x86.zip"
# Qt 6.9/6.10/6.11 are built against ICU 73.2 on Windows. PySide6 6.6+ stopped
# bundling ICU DLLs (they assume Windows 10 1703+ provides ICU in System32,
# which Wine doesn't). We must stage ICU 73 ourselves. qt6core.dll imports
# the unsuffixed name `icuuc.dll`, so we place both suffixed and unsuffixed
# copies next to qt6core.dll - both in the bottle (so pip-installed PySide6
# works) and in the Nuitka dist dir (so the packaged .exe works).
ICU_URL="https://github.com/unicode-org/icu/releases/download/release-73-2/icu4c-73_2-Win64-MSVC2019.zip"
# Note: icudt is already bundled by Nuitka's pyside6 plugin (as icudt73.dll),
# so we do NOT include it here to avoid a "data file conflicts with dll" error.
ICU_DLLS="icuuc icuin icuio icutu"

if [ ! -f "$SPEC_SRC" ];   then echo "Missing $SPEC_SRC" >&2;   exit 1; fi
if [ ! -f "$LAUNCH_SRC" ]; then echo "Missing $LAUNCH_SRC" >&2; exit 1; fi
if ! command -v wine >/dev/null; then echo "wine not installed (apt install wine64)" >&2; exit 1; fi

echo "==> mde Windows build (via Wine)"
echo "    mode:   $MODE"
echo "    jobs:   $JOBS"
echo "    repo:   $REPO_ROOT"
echo "    build:  $BUILD_DIR"
echo "    bottle: $BUILD_DIR/wine"

# ============================================================================
# Clean
# ============================================================================
if [ "$CLEAN" -eq 1 ]; then
    echo "==> cleaning Windows build output"
    rm -rf "$WIN_OUT"
fi
if [ "$CLEAN_ALL" -eq 1 ]; then
    echo "==> cleaning bottle + tools cache (full reset)"
    rm -rf "$BUILD_DIR/wine" "$BUILD_DIR/wine-xdg" "$TOOLS_DIR"
fi
mkdir -p "$TOOLS_DIR" "$WIN_OUT"

# ============================================================================
# Isolation env (exported for every wine invocation below)
# ============================================================================
export WINEPREFIX="$BUILD_DIR/wine"
export WINEARCH=win64
export WINEDLLOVERRIDES="winemenubuilder.exe=d"
export XDG_DATA_HOME="$BUILD_DIR/wine-xdg/data"
export XDG_CONFIG_HOME="$BUILD_DIR/wine-xdg/config"
export XDG_CACHE_HOME="$BUILD_DIR/wine-xdg/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"

# Silence Wine fixme/err noise. Override with WINEDEBUG=+loaddll when debugging.
: "${WINEDEBUG:=-all}"
export WINEDEBUG

# ============================================================================
# Bottle init (once, idempotent)
# ============================================================================
if [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "==> wineboot -u (first-time bottle init at $WINEPREFIX)"
    wineboot -u
fi

# ============================================================================
# winetricks (bash script; no apt/sudo needed)
# ============================================================================
if [ ! -x "$WINETRICKS" ]; then
    echo "==> downloading winetricks to $WINETRICKS"
    curl -fL --progress-bar "$WINETRICKS_URL" -o "$WINETRICKS"
    chmod +x "$WINETRICKS"
fi

# ============================================================================
# Windows Python 3.12 (once)
# ============================================================================
if [ ! -f "$PY_INSTALLER" ]; then
    echo "==> downloading Python $PY_VERSION Windows installer"
    curl -fL --progress-bar "$PY_INSTALLER_URL" -o "$PY_INSTALLER"
fi
PY_EXE="$WINEPREFIX/drive_c/users/$WINE_USER/AppData/Local/Programs/Python/Python312/python.exe"
if [ ! -f "$PY_EXE" ]; then
    echo "==> installing Python $PY_VERSION into bottle (silent)"
    wine "$PY_INSTALLER" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=0
    wine python --version
fi

# ============================================================================
# Fix 1: Nuitka's depends.exe breaks under Wine - use 32-bit build + mfc42.
# Ref: Nuitka issue #2194.
# ============================================================================
MFC42_FLAG="$WINEPREFIX/drive_c/windows/syswow64/mfc42.dll"
if [ ! -f "$MFC42_FLAG" ]; then
    echo "==> winetricks -q mfc42 (required by 32-bit depends.exe under WoW64)"
    "$WINETRICKS" -q mfc42
fi
NUITKA_DEP_CACHE="$WINEPREFIX/drive_c/users/$WINE_USER/AppData/Local/Nuitka/Nuitka/Cache/downloads/depends/x86_64"
if [ ! -f "$NUITKA_DEP_CACHE/depends.exe" ] || ! file "$NUITKA_DEP_CACHE/depends.exe" | grep -q "Intel 80386"; then
    echo "==> staging 32-bit depends.exe into Nuitka cache"
    mkdir -p "$NUITKA_DEP_CACHE"
    curl -fL --progress-bar "$DEPENDS_X86_URL" -o "$TOOLS_DIR/depends22_x86.zip"
    unzip -oq "$TOOLS_DIR/depends22_x86.zip" -d "$NUITKA_DEP_CACHE"
fi

# ============================================================================
# Fix 2: MSVC 2015-2022 runtime for PySide6's Qt6Core.dll
# (MSVCP140 / VCRUNTIME140).
# ============================================================================
VCRUN_FLAG="$WINEPREFIX/drive_c/windows/system32/msvcp140.dll"
if [ ! -f "$VCRUN_FLAG" ]; then
    echo "==> winetricks -q vcrun2022 (MSVC 2015-2022 runtime)"
    "$WINETRICKS" -q vcrun2022
fi

# ============================================================================
# Fix 3: ICU 73.2 DLLs (icuuc, icuin, icuio, icutu) for Qt 6.11.
# Download once, extract to TOOLS_DIR. Two staging targets:
#   1. Bottle's PySide6/ dir - so `wine python -c "from PySide6 import QtCore"`
#      works during the build phase.
#   2. A dedicated icu-stage/ dir we later pass to Nuitka via
#      --include-data-files=... - this is what puts ICU inside the bundled
#      artifact (works for both standalone dist and onefile archive).
# qt6core.dll imports "icuuc.dll" (unsuffixed), so we place both suffixed
# (icuuc73.dll) and unsuffixed (icuuc.dll) copies in both locations.
# icudt73.dll is intentionally excluded - Nuitka's pyside6 plugin already
# bundles it; including it again errors with "data file conflicts with dll".
# ============================================================================
ICU_ZIP="$TOOLS_DIR/icu4c-73_2-Win64-MSVC2019.zip"
ICU_EXTRACT="$TOOLS_DIR/icu73"
if [ ! -f "$ICU_ZIP" ]; then
    echo "==> downloading ICU 73.2 Win64 MSVC2019 zip"
    curl -fL --progress-bar "$ICU_URL" -o "$ICU_ZIP"
fi
# The outer zip contains an inner icu-windows.zip. Extract both.
if [ ! -d "$ICU_EXTRACT/bin64" ]; then
    rm -rf "$ICU_EXTRACT" && mkdir -p "$ICU_EXTRACT"
    unzip -oq "$ICU_ZIP" -d "$ICU_EXTRACT/outer"
    INNER_ZIP=$(find "$ICU_EXTRACT/outer" -name "icu-windows.zip" | head -1)
    unzip -oq "$INNER_ZIP" -d "$ICU_EXTRACT"
fi
# Stage into bottle's PySide6 dir so `wine python -c "from PySide6 import QtCore"` works.
PYSIDE6_DIR="$WINEPREFIX/drive_c/users/$WINE_USER/AppData/Local/Programs/Python/Python312/Lib/site-packages/PySide6"
if [ -d "$PYSIDE6_DIR" ] && [ ! -f "$PYSIDE6_DIR/icuuc73.dll" ]; then
    echo "==> staging ICU 73.2 DLLs into bottle's PySide6 dir"
    for icu in $ICU_DLLS; do
        src="$ICU_EXTRACT/bin64/${icu}73.dll"
        [ -f "$src" ] || continue
        cp "$src" "$PYSIDE6_DIR/${icu}73.dll"
        cp "$src" "$PYSIDE6_DIR/${icu}.dll"
    done
fi

# Also stage a dedicated "for Nuitka" dir so we can pass --include-data-files
# to Nuitka and the ICU DLLs land inside the bundle (standalone dist AND
# onefile archive). The post-build copy alternative only works for standalone.
ICU_STAGE="$TOOLS_DIR/icu-stage"
if [ ! -f "$ICU_STAGE/icuuc73.dll" ]; then
    rm -rf "$ICU_STAGE" && mkdir -p "$ICU_STAGE"
    for icu in $ICU_DLLS; do
        src="$ICU_EXTRACT/bin64/${icu}73.dll"
        [ -f "$src" ] || continue
        cp "$src" "$ICU_STAGE/${icu}73.dll"
        cp "$src" "$ICU_STAGE/${icu}.dll"
    done
fi

# ============================================================================
# Project + build deps (once)
# ============================================================================
MDE_INSTALLED_FLAG="$WINEPREFIX/drive_c/users/$WINE_USER/AppData/Local/Programs/Python/Python312/Lib/site-packages/markdown_editor"
if [ ! -d "$MDE_INSTALLED_FLAG" ]; then
    echo "==> upgrading pip in bottle"
    wine python -m pip install --upgrade pip
    echo "==> installing project deps via Z: drive"
    # Wine sees / as Z: - so the repo root becomes Z:\home\michael\src\mde
    REPO_ROOT_WIN='Z:'"$(echo "$REPO_ROOT" | tr '/' '\\')"
    wine python -m pip install -e "${REPO_ROOT_WIN}[build]"
fi

# ============================================================================
# Stage Windows spec + launcher in $WIN_OUT, patch per-run values
# ============================================================================
WIN_SPEC="$WIN_OUT/pysidedeploy.spec"
WIN_LAUNCH="$WIN_OUT/mde_launch.py"
WIN_ICON_ABS="$REPO_ROOT/src/markdown_editor/markdown6/icons/markdown-mark-solid-win10.ico"

cp "$SPEC_SRC"   "$WIN_SPEC"
cp "$LAUNCH_SRC" "$WIN_LAUNCH"

sed -i \
    -e "s|^mode = .*|mode = $MODE|" \
    -e "/^extra_args = /s|\$| --jobs=$JOBS|" \
    -e "s|^project_dir = .*|project_dir = $WIN_OUT|" \
    -e "s|^input_file = .*|input_file = $WIN_LAUNCH|" \
    -e "s|^exec_directory = .*|exec_directory = $WIN_OUT|" \
    -e "s|^icon = .*|icon = $WIN_ICON_ABS|" \
    "$WIN_SPEC"

echo "==> staged Windows spec:"
grep -E "^mode|^extra_args|^icon|^input_file|^project_dir|^exec_directory|^packages" "$WIN_SPEC" | sed 's/^/    /'

# ============================================================================
# Run Nuitka directly under Wine (bypassing pyside6-deploy's subprocess wrapper).
#
# Why not pyside6-deploy: under Wine, the wrapper catches Nuitka's exit code
# as 0xC0000005 even though Nuitka completed successfully and wrote the .exe.
# The wrapper also expects the dist at a different path than Nuitka actually
# produces (exec_directory/mde_launch.dist vs output-dir/mde_launch.dist).
# Invoking Nuitka directly avoids both issues and replicates exactly what
# pyside6-deploy would run anyway.
# ============================================================================
# Read the Nuitka args from the staged spec's extra_args line (everything after
# the =) plus pyside6-deploy's implicit Nuitka args.
EXTRA_ARGS=$(grep "^extra_args = " "$WIN_SPEC" | sed 's/^extra_args = //')
NUITKA_STANDALONE_FLAG="--standalone"
[ "$MODE" = "onefile" ] && NUITKA_STANDALONE_FLAG="--onefile"

# Convert Linux paths to Wine Z: paths for Nuitka
to_win() { echo "Z:$1" | tr '/' '\\'; }
LAUNCH_WIN=$(to_win "$WIN_LAUNCH")
OUTPUT_DIR_WIN=$(to_win "$WIN_OUT/deployment")
ICON_WIN=$(to_win "$WIN_ICON_ABS")

# Build the list of --include-data-files flags for ICU DLLs. Passing them
# to Nuitka (rather than post-build copying) is what makes ICU end up INSIDE
# the onefile archive too - post-build copy only works for standalone dist.
ICU_INCLUDE_ARGS=()
ICU_STAGE_WIN=$(to_win "$ICU_STAGE")
for dll in "$ICU_STAGE"/*.dll; do
    name=$(basename "$dll")
    ICU_INCLUDE_ARGS+=("--include-data-files=${ICU_STAGE_WIN}\\${name}=${name}")
done

echo ""
echo "==> running Nuitka directly under Wine"
cd "$WIN_OUT"
wine python -m nuitka \
    "$LAUNCH_WIN" \
    --follow-imports \
    --enable-plugin=pyside6 \
    --output-dir="$OUTPUT_DIR_WIN" \
    $EXTRA_ARGS \
    "${ICU_INCLUDE_ARGS[@]}" \
    $NUITKA_STANDALONE_FLAG \
    --noinclude-dlls=*.cpp.o \
    --noinclude-dlls=*.qsb \
    --windows-icon-from-ico="$ICON_WIN"

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
    echo "==> built Windows binary: $OUT  ($(du -h "$OUT" | cut -f1))"
    if [ "$MODE" = "standalone" ]; then
        SIZE=$(du -sh "$WIN_OUT/deployment/mde_launch.dist" | cut -f1)
        echo "    dist size: $SIZE"
    fi
else
    echo "==> expected output not found at $OUT" >&2
    exit 1
fi

# ============================================================================
# Smoke test under Wine (optional - --smoke-test)
#
# Wine's Chromium emulation is incomplete (no WSALookupServiceBegin, no real
# GPU compositing, etc.), so QtWebEngine needs a pile of Chromium flags to
# render anything under Wine. These flags are WINE-ONLY and must not be baked
# into the .exe. We set them here just for the smoke test.
# ============================================================================
if [ "$SMOKE_TEST" -eq 1 ]; then
    echo ""
    echo "==> smoke test under Wine"
    echo "    Chromium flags applied are Wine-compat only (not present on real-Windows runs)."
    export LANG="en_US.UTF-8"
    export LC_ALL="en_US.UTF-8"
    export QTWEBENGINE_CHROMIUM_FLAGS="--single-process --no-sandbox --disable-gpu --use-angle=swiftshader --disable-direct-composition --disable-d3d11 --disable-dev-shm-usage"
    echo ""
    echo "-- mde.exe --version"
    wine "$OUT" --version 2>&1 | grep -vE "^[0-9a-f]+:(fixme|err:|warn:)"
    echo ""
    echo "-- mde.exe stats README.md"
    wine "$OUT" stats "$REPO_ROOT/README.md" 2>&1 | grep -vE "^[0-9a-f]+:(fixme|err:|warn:)" | head -10
    echo ""
    echo "-- GUI launch (12 s, captures screenshot)"
    mkdir -p "$REPO_ROOT/local/tmp"
    wine "$OUT" "$REPO_ROOT/README.md" > /tmp/mde-win-smoke.out 2> /tmp/mde-win-smoke.err &
    SMOKE_PID=$!
    sleep 12
    if command -v xwininfo >/dev/null; then
        WID=$(xwininfo -root -tree 2>/dev/null | grep -oP '0x[0-9a-f]+(?=\s+"README\.md)' | head -1)
        GEOM=$(xwininfo -id "$WID" 2>/dev/null | awk '/Absolute upper-left X/{x=$NF} /Absolute upper-left Y/{y=$NF} /Width:/{w=$NF} /Height:/{h=$NF} END{print w"x"h"+"x"+"y}')
        if [ -n "$WID" ] && command -v import >/dev/null; then
            import -window root "$REPO_ROOT/local/tmp/mde-win-smoke-full.png"
            [ -n "$GEOM" ] && convert "$REPO_ROOT/local/tmp/mde-win-smoke-full.png" -crop "$GEOM" +repage "$REPO_ROOT/local/tmp/mde-win-smoke.png"
            echo "   screenshot: $REPO_ROOT/local/tmp/mde-win-smoke.png  (geom $GEOM)"
        else
            echo "   (xwininfo/import missing - skipped screenshot)"
        fi
    fi
    kill $SMOKE_PID 2>/dev/null; wait $SMOKE_PID 2>/dev/null
fi

# ============================================================================
# Smoke-test helper: launch the produced .exe under Wine with the Chromium
# flags needed to work around Wine's incomplete Chromium API surface.
#
# These flags are Wine-only. Do NOT bake them into the .exe or its launcher
# - on real Windows, Chromium's normal process model + sandbox work fine,
# and --no-sandbox / --single-process weaken security. They only exist here
# so the developer can eyeball the Wine-built .exe before shipping to real
# Windows users.
#
# Recipe (discovered in slop/bim-assistant/plugin/run-devshell-wine.sh for
# a WebView2 variant of the same underlying Chromium; the flags transfer
# because QtWebEngine bundles the same fork):
#
#   --single-process                  skip renderer subprocess spawn (Wine
#                                     can't create the IPC channels it needs)
#   --no-sandbox                      Chromium sandbox uses Linux kernel
#                                     primitives Wine can't pass through
#   --disable-gpu                     no real GPU compositing under Wine
#   --use-angle=swiftshader           force software ANGLE (default egl-angle
#                                     fails with ContextResult::kFatalFailure)
#   --disable-direct-composition      Wine doesn't implement
#                                     DCompositionCreateDevice3
#   --disable-d3d11                   belt-and-braces for D3D11 paths
#   --disable-dev-shm-usage           /dev/shm semantics differ under Wine
#
# LANG=LC_ALL=en_US.UTF-8 avoids Wine returning LOCALE_NEUTRAL which some
# runtimes reject.
#
# Usage (after the build completes):
#   $ source packaging/build-windows.sh --source-env   # (not implemented,
#     just copy the exports below into a shell to run smoke tests manually)
#
#   WINEPREFIX="$BUILD_DIR/wine" WINEARCH=win64 \
#     WINEDLLOVERRIDES="winemenubuilder.exe=d" \
#     XDG_DATA_HOME="$BUILD_DIR/wine-xdg/data" \
#     XDG_CONFIG_HOME="$BUILD_DIR/wine-xdg/config" \
#     XDG_CACHE_HOME="$BUILD_DIR/wine-xdg/cache" \
#     LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 \
#     QTWEBENGINE_CHROMIUM_FLAGS="--single-process --no-sandbox --disable-gpu --use-angle=swiftshader --disable-direct-composition --disable-d3d11 --disable-dev-shm-usage" \
#     wine "$OUT" ./README.md

# ============================================================================
# KNOWN GOTCHAS
# ============================================================================
# - `git` is not on PATH inside the bottle, so setuptools-scm falls back to
#   fallback_version (0.1.0) when it computes the version during editable
#   install. mde.exe's `--version` therefore shows "mde 0.1.0" regardless of
#   the checked-out tag. Fix when we care: pre-compute the version on the
#   Linux side and export SETUPTOOLS_SCM_PRETEND_VERSION before pip install.
#
# - pyside6-deploy's Nuitka-pin + >=/!= spec parsing is broken; the spec
#   uses `packages = Nuitka==4.0.8` (exact pin). Do not change to `>=`.
#
# - If you delete the bottle (`--clean-all`), the next run redownloads Python,
#   ICU zip, depends22_x86.zip, and reinstalls all pip deps. This takes
#   ~10-15 minutes. Just `--clean` (without -all) keeps the bottle and is
#   much faster.
