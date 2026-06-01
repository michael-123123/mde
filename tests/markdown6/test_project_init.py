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
