"""Shell tab-completion: register / unregister argcomplete completions
for the ``mde`` and ``markdown-editor`` commands across bash, zsh,
and fish.

Implements ``mde install-autocomplete`` and ``mde uninstall-autocomplete``.

The ``import argcomplete`` calls inside each per-shell installer are
intentionally local: argcomplete is an optional runtime dependency.
``cmd_install_autocomplete`` checks for it once at entry and bails with
a friendly hint if it's missing, so the per-shell helpers can assume
the import succeeds.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from markdown_editor.markdown6.cli.desktop_integration import bundled_binary_path


_COMPLETABLE_COMMANDS = ["mde", "markdown-editor"]


def _completable_commands() -> list[str]:
    """Command names to register shell completion for. Adds the bundled
    binary's basename when running from a Nuitka onefile/standalone, so
    completion works if the user puts mde.bin on PATH under its own name."""
    commands = list(_COMPLETABLE_COMMANDS)
    bundled = bundled_binary_path()
    if bundled and bundled.name not in commands:
        commands.append(bundled.name)
    return commands


def cmd_install_autocomplete(args: argparse.Namespace) -> int:
    """Register argcomplete shell completion for mde and markdown-editor."""
    try:
        import argcomplete  # noqa: F401
    except ImportError:
        print("argcomplete is not installed. Run: pip install argcomplete", file=sys.stderr)
        return 1

    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        _install_autocomplete_zsh()
    elif "fish" in shell:
        _install_autocomplete_fish()
    else:
        _install_autocomplete_bash()

    return 0


def _install_autocomplete_bash():
    """Install bash completion via ~/.bash_completion.d/."""
    import argcomplete

    comp_dir = Path.home() / ".bash_completion.d"
    comp_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _completable_commands():
        comp_file = comp_dir / cmd
        comp_file.write_text(argcomplete.shellcode([cmd], shell="bash"))
        print(f"Installed {comp_file}")

    # Ensure ~/.bash_completion.d/ is sourced
    bashrc = Path.home() / ".bashrc"
    sourcer = 'for f in ~/.bash_completion.d/*; do [ -f "$f" ] && . "$f"; done'
    if bashrc.exists() and sourcer not in bashrc.read_text():
        print("\nAdd this to your ~/.bashrc if not already present:")
        print(f"  {sourcer}")
    print("Then restart your shell or run: source ~/.bashrc")


def _install_autocomplete_zsh():
    """Install zsh completion."""
    import argcomplete

    comp_dir = Path.home() / ".zfunc"
    comp_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _completable_commands():
        comp_file = comp_dir / f"_{cmd}"
        comp_file.write_text(argcomplete.shellcode([cmd], shell="zsh"))
        print(f"Installed {comp_file}")

    zshrc = Path.home() / ".zshrc"
    lines_needed = ['fpath=(~/.zfunc $fpath)', 'autoload -Uz compinit && compinit']
    existing = zshrc.read_text() if zshrc.exists() else ""
    missing = [line for line in lines_needed if line not in existing]
    if missing:
        print("\nAdd these to your ~/.zshrc if not already present:")
        for line in missing:
            print(f"  {line}")
    print("Then restart your shell or run: exec zsh")


def _install_autocomplete_fish():
    """Install fish completion."""
    import argcomplete

    comp_dir = Path.home() / ".config" / "fish" / "completions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _completable_commands():
        comp_file = comp_dir / f"{cmd}.fish"
        comp_file.write_text(argcomplete.shellcode([cmd], shell="fish"))
        print(f"Installed {comp_file}")

    print("Completions will be active in new fish sessions.")


def cmd_uninstall_autocomplete(args: argparse.Namespace) -> int:
    """Remove argcomplete shell completions for mde and markdown-editor."""
    removed = []

    commands = _completable_commands()

    # bash
    comp_dir = Path.home() / ".bash_completion.d"
    for cmd in commands:
        f = comp_dir / cmd
        if f.exists():
            f.unlink()
            removed.append(str(f))

    # zsh
    zfunc_dir = Path.home() / ".zfunc"
    for cmd in commands:
        f = zfunc_dir / f"_{cmd}"
        if f.exists():
            f.unlink()
            removed.append(str(f))

    # fish
    fish_dir = Path.home() / ".config" / "fish" / "completions"
    for cmd in commands:
        f = fish_dir / f"{cmd}.fish"
        if f.exists():
            f.unlink()
            removed.append(str(f))

    if removed:
        for path in removed:
            print(f"Removed {path}")
        print("Restart your shell for changes to take effect.")
    else:
        print("Nothing to remove.")

    return 0
