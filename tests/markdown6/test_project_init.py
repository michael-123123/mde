"""Project initialization on MarkdownEditor construction.

Fix 1 of the ``mde -p .`` slowness investigation: the editor used to
do two project loads on every ``mde -p X`` invocation because the
constructor unconditionally ran ``_restore_last_project()`` (walking
the previously-saved project) and then ``cmd_gui`` overwrote it via
``set_project_path(X)`` after construction. The constructor now
accepts an explicit ``project_path`` override - if provided, it is
used directly; otherwise the last saved path is restored. Either
way, every project-aware panel (project, references, search, plus
the wiki-link completion list) sees a single, consistent path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_editor.markdown6.markdown_editor import MarkdownEditor
from markdown_editor.markdown6.project_manager import ProjectPanel


@pytest.fixture
def two_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Two empty project directories: ``last`` (simulating the
    previously-saved path) and ``override`` (the one explicitly
    passed on the command line)."""
    last = tmp_path / "last"
    override = tmp_path / "override"
    last.mkdir()
    override.mkdir()
    return last, override


@pytest.mark.timeout(15, method="thread")
def test_constructor_accepts_project_path_parameter(qtbot, tmp_path):
    """The constructor exposes a ``project_path`` keyword. Smoke test
    that simply passing it doesn't raise."""
    editor = MarkdownEditor(project_path=tmp_path)
    qtbot.addWidget(editor)


@pytest.mark.timeout(15, method="thread")
def test_explicit_project_path_takes_effect(qtbot, tmp_path):
    """When the caller passes ``project_path=X``, every project-aware
    panel ends up pointed at X."""
    editor = MarkdownEditor(project_path=tmp_path)
    qtbot.addWidget(editor)
    assert editor.project_panel.project_path == tmp_path
    assert editor.references_panel.project_path == tmp_path
    assert editor.search_panel.project_path == tmp_path


@pytest.mark.timeout(15, method="thread")
def test_explicit_project_path_skips_last_path_restore(
    qtbot, monkeypatch, two_dirs
):
    """When an explicit ``project_path`` is supplied, the previously
    saved ``project.last_path`` is never walked. Today's code does a
    full rglob over the saved path before cmd_gui replaces it - that
    is the wasted-walk that motivated this fix.

    We assert by spying on ``ProjectPanel.set_project_path`` and
    requiring exactly one call, with the override path."""
    last, override = two_dirs

    # Seed last_path so the old code path would try to restore it.
    from markdown_editor.markdown6.app_context import get_app_context
    get_app_context().set("project.last_path", str(last))

    calls: list[Path] = []
    original = ProjectPanel.set_project_path

    def spy(self, path):
        calls.append(path)
        return original(self, path)

    monkeypatch.setattr(ProjectPanel, "set_project_path", spy)

    editor = MarkdownEditor(project_path=override)
    qtbot.addWidget(editor)

    assert calls == [override], (
        f"set_project_path should fire exactly once with override; got {calls}"
    )


@pytest.mark.timeout(15, method="thread")
def test_no_explicit_path_restores_last_path(qtbot, two_dirs):
    """When ``project_path=None`` and a previous ``last_path`` exists,
    the constructor restores it (the bare ``mde`` use case)."""
    last, _ = two_dirs

    from markdown_editor.markdown6.app_context import get_app_context
    get_app_context().set("project.last_path", str(last))

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    assert editor.project_panel.project_path == last
    assert editor.references_panel.project_path == last
    assert editor.search_panel.project_path == last


@pytest.mark.timeout(15, method="thread")
def test_no_explicit_path_and_no_last_path_leaves_panels_empty(qtbot):
    """Fresh launch, no override and no prior project: all panels
    start without a project path set."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    assert editor.project_panel.project_path is None
    assert editor.references_panel.project_path is None
    assert editor.search_panel.project_path is None


@pytest.mark.timeout(15, method="thread")
def test_explicit_path_propagates_to_references_panel(qtbot, two_dirs):
    """Latent gap closed by this fix: today's cmd_gui only updates
    project_panel when ``-p`` is passed, leaving references_panel and
    search_panel pointed at the previous project. The unified
    constructor parameter must update all three."""
    last, override = two_dirs

    from markdown_editor.markdown6.app_context import get_app_context
    get_app_context().set("project.last_path", str(last))

    editor = MarkdownEditor(project_path=override)
    qtbot.addWidget(editor)
    assert editor.references_panel.project_path == override, (
        "references_panel must follow the override, not last_path"
    )
    assert editor.search_panel.project_path == override, (
        "search_panel must follow the override, not last_path"
    )


# NOTE: "what if explicit project_path doesn't exist?" - fallback policy
# is an open question. Today (without the fix), _restore_last_project
# runs unconditionally, so a bogus -p path silently leaves the editor
# pointed at last_path. With this fix we have to choose: fall back, or
# leave projectless. Deferring the decision; cmd_gui already filters
# args.project through ``args.project.is_dir()`` before passing it.


# ──────────────────── --clean ────────────────────


@pytest.mark.timeout(15, method="thread")
def test_clean_skips_last_path_restore(qtbot, two_dirs):
    """``MarkdownEditor(clean=True)`` opens with no project even when
    ``project.last_path`` is saved. The whole point of the flag is to
    bypass the slow auto-restore path."""
    last, _ = two_dirs

    from markdown_editor.markdown6.app_context import get_app_context
    get_app_context().set("project.last_path", str(last))

    editor = MarkdownEditor(clean=True)
    qtbot.addWidget(editor)
    assert editor.project_panel.project_path is None
    assert editor.references_panel.project_path is None
    assert editor.search_panel.project_path is None


@pytest.mark.timeout(15, method="thread")
def test_clean_with_explicit_project_path_loads_the_override(qtbot, two_dirs):
    """``--clean -p X`` keeps the override semantics: the user asked
    for X, so open X. ``--clean`` only suppresses the implicit
    last_path restore, not an explicit project."""
    last, override = two_dirs

    from markdown_editor.markdown6.app_context import get_app_context
    get_app_context().set("project.last_path", str(last))

    editor = MarkdownEditor(clean=True, project_path=override)
    qtbot.addWidget(editor)
    assert editor.project_panel.project_path == override


@pytest.mark.timeout(15, method="thread")
def test_clean_default_is_false(qtbot, two_dirs):
    """Sanity: omitting clean keeps today's restore-last behaviour
    intact. Regression guard so the new kwarg doesn't accidentally
    invert the default."""
    last, _ = two_dirs

    from markdown_editor.markdown6.app_context import get_app_context
    get_app_context().set("project.last_path", str(last))

    editor = MarkdownEditor()  # clean omitted
    qtbot.addWidget(editor)
    assert editor.project_panel.project_path == last


@pytest.mark.timeout(15, method="thread")
def test_clean_leaves_project_panel_empty(qtbot):
    """No-project state must show NOTHING in the project panel.
    QFileSystemModel's default (no setRootPath) is to display the
    filesystem root, so ``mde --clean`` would otherwise render '/'
    in the left pane - exactly the wrong default. The fix is to hide
    the project-panel chrome (filter input, file tree, action
    buttons) until a project is actually loaded."""
    editor = MarkdownEditor(clean=True)
    qtbot.addWidget(editor)
    panel = editor.project_panel
    assert panel.filter_input.isHidden()
    assert panel.tree_view.isHidden()
    assert panel.export_btn.isHidden()
    assert panel.graph_btn.isHidden()
    assert panel.sort_btn.isHidden()


@pytest.mark.timeout(15, method="thread")
def test_project_panel_chrome_shown_when_project_loaded(qtbot, tmp_path):
    """Regression: when a project is set (via override here), the
    panel chrome unhides so the user sees the normal project view."""
    editor = MarkdownEditor(project_path=tmp_path)
    qtbot.addWidget(editor)
    panel = editor.project_panel
    assert not panel.filter_input.isHidden()
    assert not panel.tree_view.isHidden()
    assert not panel.export_btn.isHidden()
    assert not panel.graph_btn.isHidden()
    assert not panel.sort_btn.isHidden()


@pytest.mark.timeout(15, method="thread")
def test_clean_does_not_bind_model_to_tree_view(qtbot):
    """``--clean`` must not bind QFileSystemModel to the tree view.

    ``QTreeView.setModel(...)`` makes Qt query the model for
    ``rowCount(QModelIndex())`` to set up the layout. QFileSystemModel
    answers that by enumerating its current root (filesystem ``/`` if
    setRootPath was never called). That's one readdir of '/' on every
    --clean launch - small but counter to the flag's promise. Defer
    the bind until set_project_path runs."""
    editor = MarkdownEditor(clean=True)
    qtbot.addWidget(editor)
    assert editor.project_panel.tree_view.model() is None


@pytest.mark.timeout(15, method="thread")
def test_set_project_path_binds_model(qtbot, tmp_path):
    """Regression for the deferred-bind: once a project is loaded,
    the tree view must be bound to the proxy (which wraps
    QFileSystemModel) so the user can navigate the tree."""
    editor = MarkdownEditor(project_path=tmp_path)
    qtbot.addWidget(editor)
    assert editor.project_panel.tree_view.model() is editor.project_panel.proxy


@pytest.mark.timeout(15, method="thread")
def test_set_project_path_hides_non_name_columns(qtbot, tmp_path):
    """Regression: the file explorer must show ONLY the Name column.
    The other QFileSystemModel columns (Size, Type, Date Modified)
    must be hidden so the name column gets the full pane width.

    Bug history: the hideColumn loop used to live in _init_ui and ran
    AFTER ``setModel(self.proxy)``. After ``setModel`` was deferred to
    set_project_path (so empty / --clean state doesn't trigger a
    filesystem-root enumeration), the hideColumn loop in _init_ui now
    runs BEFORE any model is bound. Qt's QHeaderView reinitialises
    its sections on setModel and the prior hide flags are discarded -
    so all four columns end up visible, squeezing the Name column to
    a width that truncates every filename to ~3 characters."""
    editor = MarkdownEditor(project_path=tmp_path)
    qtbot.addWidget(editor)
    panel = editor.project_panel
    assert not panel.tree_view.isColumnHidden(0), (
        "Name column (0) must be visible"
    )
    for i in range(1, panel.file_model.columnCount()):
        assert panel.tree_view.isColumnHidden(i), (
            f"non-name column {i} must be hidden so the Name column "
            f"gets the full pane width"
        )
