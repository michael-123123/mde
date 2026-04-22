"""Tests for the `extra_plugin_dirs` mechanism: extra plugin directories
contributed by the constructor, by ``plugins.extra_dirs`` settings, and
by the ``--plugins-dir`` CLI flag.

The mechanism is purely additive — it never replaces the default
``builtin_plugins/`` + ``<config_dir>/plugins/`` scan, only stacks
on top.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.markdown_editor_cli import create_parser


def _make_plugin_dir(root: Path, name: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.toml").write_text(textwrap.dedent(f"""
        [tool.mde.plugin]
        name = "{name}"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (d / f"{name}.py").write_text(
        "from markdown_editor.plugins import register_text_transform\n"
        f"@register_text_transform(id='{name}.t', label='{name}')\n"
        "def t(text):\n"
        "    return text\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Constructor argument
# ---------------------------------------------------------------------------


def test_extra_plugin_dirs_constructor_arg_is_scanned(qtbot, tmp_path: Path):
    """A directory passed via ``MarkdownEditor(extra_plugin_dirs=[...])``
    is scanned alongside the default roots."""
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    extra = tmp_path / "extra"
    extra.mkdir()
    _make_plugin_dir(extra, "from_extra")

    editor = MarkdownEditor(extra_plugin_dirs=[extra])
    try:
        names = {p.name for p in editor._plugins}
        assert "from_extra" in names
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


def test_multiple_extra_dirs_all_scanned(qtbot, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    extra_a = tmp_path / "a"
    extra_a.mkdir()
    _make_plugin_dir(extra_a, "alpha")
    extra_b = tmp_path / "b"
    extra_b.mkdir()
    _make_plugin_dir(extra_b, "beta")

    editor = MarkdownEditor(extra_plugin_dirs=[extra_a, extra_b])
    try:
        names = {p.name for p in editor._plugins}
        assert {"alpha", "beta"} <= names
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_extra_dirs_from_settings_are_scanned(qtbot, tmp_path: Path):
    """Directories listed in the ``plugins.extra_dirs`` setting are
    scanned at editor startup."""
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    extra = tmp_path / "from_settings"
    extra.mkdir()
    _make_plugin_dir(extra, "settings_plugin")

    ctx = get_app_context()
    ctx.set("plugins.extra_dirs", [str(extra)], save=False)

    editor = MarkdownEditor()
    try:
        names = {p.name for p in editor._plugins}
        assert "settings_plugin" in names
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


def test_constructor_and_settings_dirs_both_scanned(qtbot, tmp_path: Path):
    """Constructor arg + settings list are additive, not exclusive."""
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    a = tmp_path / "from_cli"
    a.mkdir()
    _make_plugin_dir(a, "cli_plugin")
    b = tmp_path / "from_settings"
    b.mkdir()
    _make_plugin_dir(b, "settings_plugin")

    ctx = get_app_context()
    ctx.set("plugins.extra_dirs", [str(b)], save=False)

    editor = MarkdownEditor(extra_plugin_dirs=[a])
    try:
        names = {p.name for p in editor._plugins}
        assert {"cli_plugin", "settings_plugin"} <= names
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


def test_nonexistent_extra_dir_is_silently_skipped(qtbot, tmp_path: Path):
    """A path in extra_dirs that doesn't exist must not crash startup —
    the editor logs and continues, like missing builtin/user dirs do."""
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    real = tmp_path / "real"
    real.mkdir()
    _make_plugin_dir(real, "real_plugin")
    missing = tmp_path / "does_not_exist"

    editor = MarkdownEditor(extra_plugin_dirs=[missing, real])
    try:
        names = {p.name for p in editor._plugins}
        assert "real_plugin" in names
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


# ---------------------------------------------------------------------------
# CLI flag
# ---------------------------------------------------------------------------


def test_cli_plugins_dir_is_repeatable():
    """``--plugins-dir`` can be passed multiple times; they all stack."""
    parser = create_parser()
    args = parser.parse_args([
        "--plugins-dir", "/tmp/a",
        "--plugins-dir", "/tmp/b",
    ])
    assert args.plugins_dir == [Path("/tmp/a"), Path("/tmp/b")]


def test_cli_plugins_dir_defaults_to_empty():
    """No flag → empty list (not None) so the launch path can iterate
    without a None-check."""
    parser = create_parser()
    args = parser.parse_args([])
    assert args.plugins_dir == []
