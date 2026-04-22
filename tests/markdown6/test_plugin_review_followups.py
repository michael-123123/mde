"""Tests for findings #1, #2, #5, #6 from local/reviews/plan-system-1.md.

Finding #3 (dead ``accepted`` connect in PluginInfoDialog) is a one-line
cleanup with no behavior change; no test added.
"""

from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QTextBrowser

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugin_info_dialog import (
    PluginInfoDialog,
)
from markdown_editor.markdown6.markdown_editor import MarkdownEditor
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.metadata import PluginMetadata
from markdown_editor.markdown6.plugins.plugin import (
    Plugin,
    PluginSource,
    PluginStatus,
)


# ---------------------------------------------------------------------------
# Finding #1 — atomic_edit rollback must clear the stale tab-title `*`
# ---------------------------------------------------------------------------


@pytest.mark.timeout(15, method="thread")
def test_atomic_edit_rollback_clears_stale_dirty_title(qtbot) -> None:
    """A failing plugin transform on a previously-clean tab must leave
    the tab title with no ``*`` marker — the rollback clears
    ``unsaved_changes`` but pre-fix it didn't repaint the title.
    """
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None
    assert tab.unsaved_changes is False

    doc = DocumentHandle(tab)

    def bad_transform():
        with doc.atomic_edit():
            doc.replace_all("scratch text")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        bad_transform()

    QApplication.processEvents()

    assert doc.text == ""
    assert tab.unsaved_changes is False
    # Pre-fix bug: tab title stayed with a leading '*' because the
    # rollback set the attribute directly and didn't re-run
    # update_tab_title. Post-fix: setModified() fires
    # modificationChanged → DocumentTab's handler repaints the title.
    idx = editor.tab_widget.indexOf(tab)
    assert idx >= 0
    title = editor.tab_widget.tabText(idx)
    assert not title.startswith("*"), f"tab title should be clean, got {title!r}"


# ---------------------------------------------------------------------------
# Finding #2 — PluginInfoDialog must not render the description twice
# ---------------------------------------------------------------------------


def _fake_plugin_with_description(desc: str) -> Plugin:
    meta = PluginMetadata(
        name="demo",
        version="1.0.0",
        description=desc,
        author="",
        mde_api_version="0",
        dependencies=(),
    )
    return Plugin(
        name="demo",
        source=PluginSource.USER,
        directory=None,  # unused in the dialog
        metadata=meta,
        module=None,
        status=PluginStatus.ENABLED,
        detail="",
        missing_deps=(),
        readme_path=None,
    )


def test_plugin_info_dialog_renders_description_once(qtbot) -> None:
    desc = "UNIQUE_SENTINEL_DESCRIPTION_12345"
    dialog = PluginInfoDialog(_fake_plugin_with_description(desc))
    qtbot.addWidget(dialog)

    # Count how many QLabel descendants (anywhere in the dialog) display
    # the description text.
    hits = 0
    for lbl in dialog.findChildren(QLabel):
        if desc in lbl.text():
            hits += 1
    # QTextBrowser (README block) uses setMarkdown, we can ignore it —
    # the dialog under test doesn't include a README, and the duplicate
    # is in two QLabels anyway. One hit is the expected panel; two hits
    # is the duplicated metadata-block render.
    assert hits == 1, f"description rendered {hits} times; expected 1"


# ---------------------------------------------------------------------------
# Finding #5 — register_fence must validate the language tag
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


@pytest.mark.parametrize("bad_name", [
    "foo bar",       # space
    "plant/uml",     # slash
    "hello.world",   # dot
    "with!bang",     # punctuation
    "中文",           # non-ASCII
])
def test_register_fence_rejects_invalid_chars(bad_name: str) -> None:
    """Names that can't match the fence preprocessor regex (``[A-Za-z0-9_-]+``)
    must be rejected at decoration time so the plugin author sees the
    bug on import, not as a silently-never-invoked renderer."""
    with pytest.raises(ValueError):
        @plugin_api.register_fence(bad_name)
        def render(src):
            return "<div></div>"


@pytest.mark.parametrize("ok_name", ["foo", "plant_uml", "svg-inline", "A1"])
def test_register_fence_accepts_valid_names(ok_name: str) -> None:
    @plugin_api.register_fence(ok_name)
    def render(src):
        return "<div></div>"
    assert any(f.name == ok_name for f in plugin_api._REGISTRY.fences())


# ---------------------------------------------------------------------------
# Finding #6 — runtime notify_* must auto-attribute via wrapped callbacks
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx():
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


# ---------------------------------------------------------------------------
# Finding #8 — test-coverage tightening
# ---------------------------------------------------------------------------


def test_disabled_plugin_fence_source_appears_verbatim(qtbot, ctx) -> None:
    """A disabled plugin's fence MUST NOT be re-rendered AND MUST leave
    the fence source visible in the rendered output — the user shouldn't
    see the raw ``source`` text disappear just because they toggled the
    plugin off.
    """
    import markdown

    from markdown_editor.markdown6.plugins.fence import PluginFenceExtension

    @plugin_api.register_fence("mybox", _plugin_name="myplug")
    def render(src):
        return f"<div class='rendered'>{src}</div>"

    text = (
        "before\n"
        "```mybox\nsome inner content\n```\n"
        "after\n"
    )

    # Enabled → callback runs, placeholder substitution happens.
    md_enabled = markdown.Markdown(
        extensions=[PluginFenceExtension(disabled=set())],
    )
    html_enabled = md_enabled.convert(text)
    assert "rendered" in html_enabled
    assert "some inner content" in html_enabled

    # Disabled → callback skipped AND the original fence body stays
    # visible in the rendered output (default markdown code-block
    # handling kicks in and renders as a <pre><code> block).
    md_disabled = markdown.Markdown(
        extensions=[PluginFenceExtension(disabled={"myplug"})],
    )
    html_disabled = md_disabled.convert(text)
    assert "rendered" not in html_disabled
    assert "some inner content" in html_disabled


def test_atomic_edit_on_real_document_tab_title_clean_after_rollback(
    qtbot,
) -> None:
    """Same contract as ``test_atomic_edit_rollback_clears_stale_dirty_title``
    but explicit: starts with a clean tab and asserts both the dirty flag
    and the tab title afterwards. Guards against future regressions in
    the modificationChanged signal wiring.
    """
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None
    tab.editor.setPlainText("initial content")
    tab.editor.document().setModified(False)
    editor.update_tab_title(tab)
    idx = editor.tab_widget.indexOf(tab)
    assert not editor.tab_widget.tabText(idx).startswith("*")

    doc = DocumentHandle(tab)
    with pytest.raises(RuntimeError):
        with doc.atomic_edit():
            doc.insert_at_cursor("more")
            raise RuntimeError("abort")
    QApplication.processEvents()

    assert doc.text == "initial content"
    assert tab.unsaved_changes is False
    assert tab.editor.document().isModified() is False
    assert not editor.tab_widget.tabText(idx).startswith("*")


def test_notification_center_clear_no_unread_does_not_fire_signal(
    qtbot, ctx,
) -> None:
    """``clear()`` when there are no unread items must not emit
    ``unread_count_changed`` (previously only the unread case was
    tested)."""
    # Prime the center with a read notification so there IS history
    # but zero unread.
    ctx.notifications.post_info("t", "m")
    ctx.notifications.mark_all_read()
    assert ctx.notifications.unread_count() == 0

    fired: list[int] = []
    ctx.notifications.unread_count_changed.connect(fired.append)
    ctx.notifications.clear()
    assert fired == [], (
        "unread_count_changed must not fire when clear() is called "
        "with no unread notifications"
    )


def test_notify_from_action_callback_attributes_to_plugin(
    qtbot, ctx, tmp_path,
) -> None:
    """A plugin action that calls ``notify_info(...)`` at runtime must
    produce a notification whose ``source`` identifies the plugin.

    Pre-fix: ``_CURRENT_PLUGIN_NAME`` was only set during import; at
    callback time it was empty, so runtime notifications came out as
    ``source=""``. Post-fix: the callback wrappers in
    ``editor_integration`` stamp the plugin name around invocation.
    """
    plugin_dir = tmp_path / "attrib_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "attrib_plugin.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "attrib_plugin"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (plugin_dir / "attrib_plugin.py").write_text(textwrap.dedent("""
        from markdown_editor.plugins import register_action, notify_info

        @register_action(id="attrib_plugin.ping", label="Ping")
        def ping():
            notify_info("hello", "from action")
    """).lstrip(), encoding="utf-8")

    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    [action] = [
        a for a in plugin_api._REGISTRY.actions()
        if a.id == "attrib_plugin.ping"
    ]

    from markdown_editor.markdown6.plugins.editor_integration import (
        _wrap_action_callback,
    )
    _wrap_action_callback(action)()
    QApplication.processEvents()

    entries = ctx.notifications.all()
    [entry] = [n for n in entries if "from action" in n.message]
    assert entry.source == "plugin:attrib_plugin"
