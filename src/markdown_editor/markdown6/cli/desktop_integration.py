"""Desktop integration: install / uninstall the .desktop entry
(Linux), Start Menu shortcut (Windows), or .app bundle (macOS) for
the mde launcher.

Implements ``mde install-desktop`` and ``mde uninstall-desktop``.
The shared ``bundled_binary_path`` helper is also exposed here so the
autocomplete installer (still in markdown_editor_cli) can detect when
it's running from a Nuitka bundle without forming a circular import.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ─── runtime detection (also used by autocomplete) ──────────────────


def bundled_binary_path() -> Path | None:
    """If running from a Nuitka-compiled binary, return the path users should
    execute (the onefile wrapper, or the standalone main binary). Returns None
    when running from a regular Python install.
    """
    onefile = os.environ.get("NUITKA_ONEFILE_BINARY")
    if onefile:
        return Path(onefile)
    if "__compiled__" in globals():
        return Path(sys.executable)
    return None


# ─── shared path / asset helpers ────────────────────────────────────


_ICON_SIZES = [48, 64, 128, 256]


def _icons_dir() -> Path:
    """Return the path to the bundled icons directory.

    cli/desktop.py is one level deeper than the original
    markdown_editor_cli.py, so resolve to the grandparent's icons/.
    """
    return Path(__file__).parent.parent / "icons"


def _data_home() -> Path:
    """Return the user's data directory via QStandardPaths."""
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    ))


def _mde_executable() -> str:
    """Return the path to the mde entry-point script/exe."""
    # Nuitka-compiled binary: point at the onefile or standalone binary itself.
    bundled = bundled_binary_path()
    if bundled:
        return str(bundled)
    # pip installs entry points into Scripts/ on Windows, bin/ on Unix
    scripts_dir = Path(sys.executable).parent
    if sys.platform == "win32":
        exe = scripts_dir / "Scripts" / "mde.exe"
        if exe.exists():
            return str(exe)
        exe = scripts_dir / "mde.exe"
        if exe.exists():
            return str(exe)
    return str(shutil.which("mde") or "mde")


# ─── top-level dispatchers ──────────────────────────────────────────


def cmd_install_desktop(args: argparse.Namespace) -> int:
    """Install desktop integration for the current platform."""
    if sys.platform == "linux":
        return _install_desktop_linux()
    elif sys.platform == "win32":
        return _install_desktop_windows()
    elif sys.platform == "darwin":
        return _install_desktop_macos()
    else:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        return 1


def cmd_uninstall_desktop(args: argparse.Namespace) -> int:
    """Remove desktop integration for the current platform."""
    if sys.platform == "linux":
        return _uninstall_desktop_linux()
    elif sys.platform == "win32":
        return _uninstall_desktop_windows()
    elif sys.platform == "darwin":
        return _uninstall_desktop_macos()
    else:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        return 1


# -- Linux desktop integration ------------------------------------------------


def _install_desktop_linux() -> int:
    """Install freedesktop.org .desktop entry and icons."""
    icons_dir = _icons_dir()
    data_home = _data_home()

    # Install .desktop file - rewrite Exec= to the absolute path of whatever
    # mde entry point we can find, so the .desktop works regardless of PATH.
    # Bundled binaries (Nuitka onefile/standalone) always get an absolute path;
    # pip-installed mde resolves via shutil.which.
    apps_dir = data_home / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    src_desktop = icons_dir / "markdown-editor.desktop"
    dst_desktop = apps_dir / "markdown-editor.desktop"
    src_text = src_desktop.read_text(encoding="utf-8")
    mde_exe = _mde_executable()
    if Path(mde_exe).is_absolute():
        src_text = re.sub(
            r"(?m)^Exec=.*$",
            f"Exec={mde_exe} %F",
            src_text,
        )
    dst_desktop.write_text(src_text, encoding="utf-8")
    print(f"Installed {dst_desktop}")

    # Install icons
    for size in _ICON_SIZES:
        icon_dir = data_home / "icons" / "hicolor" / f"{size}x{size}" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        src_icon = icons_dir / f"markdown-editor-{size}.png"
        dst_icon = icon_dir / "markdown-editor.png"
        shutil.copy2(src_icon, dst_icon)
        print(f"Installed {dst_icon}")

    # Update icon cache if possible
    hicolor = data_home / "icons" / "hicolor"
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-f", str(hicolor)],
                       capture_output=True)

    # Update desktop database if possible
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps_dir)],
                       capture_output=True)

    print("Done. You may need to log out and back in for changes to take effect.")
    return 0


def _uninstall_desktop_linux() -> int:
    """Remove .desktop file and icons."""
    data_home = _data_home()
    removed = []

    desktop = data_home / "applications" / "markdown-editor.desktop"
    if desktop.exists():
        desktop.unlink()
        removed.append(str(desktop))

    for size in _ICON_SIZES:
        icon = data_home / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "markdown-editor.png"
        if icon.exists():
            icon.unlink()
            removed.append(str(icon))

    if removed:
        for path in removed:
            print(f"Removed {path}")

        # Update caches
        hicolor = data_home / "icons" / "hicolor"
        if shutil.which("gtk-update-icon-cache"):
            subprocess.run(["gtk-update-icon-cache", "-f", str(hicolor)],
                           capture_output=True)
        apps_dir = data_home / "applications"
        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", str(apps_dir)],
                           capture_output=True)
        print("Done.")
    else:
        print("Nothing to remove.")

    return 0


# -- Windows desktop integration ----------------------------------------------


def _windows_start_menu_dir() -> Path:
    """Return the user's Start Menu Programs directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _create_windows_shortcut(link_path: Path, target: str, icon_path: str,
                             description: str) -> None:
    """Create a Windows .lnk shortcut using PowerShell."""
    # PowerShell COM approach - no extra dependencies
    ps_script = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{link_path}"); '
        f'$s.TargetPath = "{target}"; '
        f'$s.IconLocation = "{icon_path}"; '
        f'$s.Description = "{description}"; '
        f'$s.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, check=True,
    )


def _install_desktop_windows() -> int:
    """Install Start Menu shortcut on Windows."""
    icons_dir = _icons_dir()
    ico_path = icons_dir / "markdown-mark-solid-win10.ico"
    mde_exe = _mde_executable()

    # Create Start Menu shortcut
    start_menu = _windows_start_menu_dir()
    start_menu.mkdir(parents=True, exist_ok=True)
    lnk_path = start_menu / "Markdown Editor.lnk"
    _create_windows_shortcut(lnk_path, mde_exe, str(ico_path),
                             "Markdown Editor with live preview")
    print(f"Installed {lnk_path}")

    print("Done.")
    return 0


def _uninstall_desktop_windows() -> int:
    """Remove Start Menu shortcut on Windows."""
    removed = []

    lnk = _windows_start_menu_dir() / "Markdown Editor.lnk"
    if lnk.exists():
        lnk.unlink()
        removed.append(str(lnk))

    if removed:
        for path in removed:
            print(f"Removed {path}")
        print("Done.")
    else:
        print("Nothing to remove.")

    return 0


# -- macOS desktop integration ------------------------------------------------


_MACOS_APP_DIR = Path.home() / "Applications"
_MACOS_APP_NAME = "Markdown Editor.app"


def _install_desktop_macos() -> int:
    """Install .app bundle in ~/Applications."""
    app_dir = _MACOS_APP_DIR / _MACOS_APP_NAME
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"

    # Create directory structure
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    # Write Info.plist - bundled as an asset alongside the icons,
    # matching the Linux .desktop file's treatment so the bundle
    # metadata is editable from outside the Python source.
    plist_text = (_icons_dir() / "Info.plist").read_text(encoding="utf-8")
    (contents / "Info.plist").write_text(plist_text)
    print(f"Installed {contents / 'Info.plist'}")

    # Write launcher script that finds the pip-installed mde
    mde_path = shutil.which("mde") or "mde"
    launcher = macos_dir / "mde-launcher"
    launcher.write_text(
        f'#!/bin/bash\nexec "{mde_path}" "$@"\n'
    )
    launcher.chmod(0o755)
    print(f"Installed {launcher}")

    # Convert PNG icon to icns using sips (built into macOS)
    icons_dir = _icons_dir()
    src_icon = icons_dir / "markdown-editor-256.png"
    dst_icon = resources / "app.icns"
    result = subprocess.run(
        ["sips", "-s", "format", "icns", str(src_icon),
         "--out", str(dst_icon)],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"Installed {dst_icon}")
    else:
        # Fallback: copy PNG as-is (icon may not display perfectly)
        shutil.copy2(src_icon, resources / "app.png")
        print("Warning: sips conversion failed, copied PNG icon instead")

    print(f"Done. '{_MACOS_APP_NAME}' is now in ~/Applications.")
    print("You can drag it to the Dock or find it in Launchpad.")
    return 0


def _uninstall_desktop_macos() -> int:
    """Remove .app bundle from ~/Applications."""
    app_dir = _MACOS_APP_DIR / _MACOS_APP_NAME

    if app_dir.exists():
        shutil.rmtree(app_dir)
        print(f"Removed {app_dir}")
        print("Done.")
    else:
        print("Nothing to remove.")

    return 0
