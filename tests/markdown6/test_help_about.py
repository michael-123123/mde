"""Help → About and Help → Version.

The About dialog was previously a long bullet list of "features" that
duplicated the README and drifted from it. Replaced with a short intro
(lifted from the README's opening paragraph) plus a dynamically-
computed version string. A separate Help → Version action shows just
the version in its own popup.
"""

from __future__ import annotations

import pytest

from markdown_editor.markdown6.markdown_editor import (
    _about_text,
    _version_text,
    get_app_version,
)


@pytest.mark.timeout(15, method="thread")
def test_version_is_a_nonempty_string():
    """The version helper must always return a string - even in dev
    installs where importlib.metadata may not know the package."""
    v = get_app_version()
    assert isinstance(v, str)
    assert v  # non-empty


@pytest.mark.timeout(15, method="thread")
def test_about_text_contains_version():
    """The About dialog body must include the version so users have a
    one-stop place to find what they're running."""
    text = _about_text()
    assert get_app_version() in text


@pytest.mark.timeout(15, method="thread")
def test_about_text_is_short():
    """About text is meant to be a quick description - not a feature
    list. Cap is generous (~600 chars); the old version was ~400 chars
    of bullet salad."""
    text = _about_text()
    assert len(text) < 600, f"about text bloated again ({len(text)} chars)"


@pytest.mark.timeout(15, method="thread")
def test_about_text_has_short_intro():
    """A one-line intro pulled from the README - sets context before
    the version is shown."""
    text = _about_text()
    # The README's opening paragraph mentions Qt6 and PySide6.
    assert "Markdown" in text
    assert "preview" in text.lower()


@pytest.mark.timeout(15, method="thread")
def test_version_text_is_just_version():
    """The Help → Version popup is deliberately minimal - just the
    version string, no features, no description."""
    text = _version_text()
    v = get_app_version()
    assert v in text
    # Sanity: not the full About text. Should be much shorter.
    assert len(text) < 100


@pytest.mark.timeout(15, method="thread")
def test_help_version_action_registered():
    """`help.version` is wired into the actions registry."""
    from markdown_editor.markdown6.actions import MENU_STRUCTURE

    found = False
    for menu in MENU_STRUCTURE:
        if menu.label == "&Help":
            for item in menu.items:
                if getattr(item, "id", None) == "help.version":
                    found = True
                    break
    assert found, "help.version must be registered under Help menu"


@pytest.mark.timeout(15, method="thread")
def test_about_dialog_has_centered_icon(qtbot):
    """The About dialog shows the mde symbol centered at the top.
    QMessageBox's static factories left-align the icon next to the
    text; we build a custom QDialog so the icon can sit centered above
    a centered body. This test asserts the dialog has an icon QLabel
    with a non-null pixmap and AlignCenter alignment."""
    from markdown_editor.markdown6.markdown_editor import _build_about_dialog
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    dialog = _build_about_dialog(None)
    qtbot.addWidget(dialog)
    icon_label = dialog.findChild(QLabel, "brand_icon")
    assert icon_label is not None, "About dialog must contain an icon QLabel"
    assert not icon_label.pixmap().isNull(), "icon pixmap must be loaded"
    assert icon_label.alignment() & Qt.AlignmentFlag.AlignHCenter, (
        "icon must be horizontally centered"
    )


@pytest.mark.timeout(15, method="thread")
def test_about_dialog_has_centered_text(qtbot):
    from markdown_editor.markdown6.markdown_editor import _build_about_dialog
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    dialog = _build_about_dialog(None)
    qtbot.addWidget(dialog)
    text_label = dialog.findChild(QLabel, "brand_text")
    assert text_label is not None
    assert text_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert get_app_version() in text_label.text()


@pytest.mark.timeout(15, method="thread")
def test_version_dialog_has_centered_icon(qtbot):
    """Same icon-centered treatment for the smaller Help → Version
    popup — the brand should be present and centered."""
    from markdown_editor.markdown6.markdown_editor import _build_version_dialog
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    dialog = _build_version_dialog(None)
    qtbot.addWidget(dialog)
    icon_label = dialog.findChild(QLabel, "brand_icon")
    assert icon_label is not None
    assert not icon_label.pixmap().isNull()
    assert icon_label.alignment() & Qt.AlignmentFlag.AlignHCenter


@pytest.mark.timeout(15, method="thread")
def test_version_dialog_has_centered_text(qtbot):
    from markdown_editor.markdown6.markdown_editor import _build_version_dialog
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    dialog = _build_version_dialog(None)
    qtbot.addWidget(dialog)
    text_label = dialog.findChild(QLabel, "brand_text")
    assert text_label is not None
    assert text_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert get_app_version() in text_label.text()


@pytest.mark.timeout(15, method="thread")
def test_show_about_does_not_throw(qtbot, monkeypatch):
    """Smoke test the dialog plumbing - calling _show_about with a
    real editor must not raise. Stub exec so the modal doesn't block."""
    from PySide6.QtWidgets import QDialog
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor._show_about()


@pytest.mark.timeout(15, method="thread")
def test_show_version_does_not_throw(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor._show_version()
