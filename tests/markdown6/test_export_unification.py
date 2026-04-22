"""Class II unified-export contract tests.

These tests FAIL today (against the current stripped export_service) and
must PASS after the renderer-unification refactor
(see local/html-export-unify.md). They lock the post-refactor behavioral
contract:

1. CLI `mde export -f html` produces preview-grade HTML — wiki links,
   callouts, math markers, mermaid/graphviz containers, task-list
   checkboxes, syntax-highlighted code.
2. Project export (via `export_service.export_html`) produces the same.
3. GUI single-file export (via `MarkdownEditor._export_html` /
   `get_html_template`) and CLI/project export produce structurally
   equivalent HTML for the same input, modulo the locked export-side
   differences (no `scroll_past_end_div`, `export.use_canonical_fonts`).
4. `html_renderer_core.py` exists and carries the non-Qt-application
   constraint marker comment.
5. `app_context/*.py` files carry the same non-Qt-application marker.
6. `AppContext.ephemeral_copy()` exists and returns an independent
   AppContext instance.
7. CLI argparse surface includes `--theme` and `--canonical-fonts`.
8. WeasyPrint PDF still produces non-empty output (H1 degradation
   contract — no feature-parity assertion).
9. Exported HTML carries `<meta charset="UTF-8">` and a non-empty
   `<title>...</title>` (decision N+T1).

Assertions are structural properties of the output (e.g. "contains a
`<div class=\"callout callout-note\">`" or "`[[foo]]` does not appear
literally") — not byte-equal snapshots. Class II is a *contract* spec,
not a golden master. The Class I invariance tests are the byte-equal
spec for the preview path.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from markdown_editor.markdown6 import export_service
from markdown_editor.markdown6.app_context import get_app_context

# ─── Source-tree references ─────────────────────────────────────────

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "markdown_editor" / "markdown6"
HTML_RENDERER_CORE_PATH = SRC_ROOT / "html_renderer_core.py"

APP_CONTEXT_FILES_WITH_MARKER = [
    SRC_ROOT / "app_context" / "__init__.py",
    SRC_ROOT / "app_context" / "settings_manager.py",
    SRC_ROOT / "app_context" / "shortcut_manager.py",
    SRC_ROOT / "app_context" / "session_state.py",
]

# Marker substring that must appear (in some form) in the top-of-file
# comment of each non-Qt-application-safe module. The test checks for
# this exact substring; implementations may phrase the surrounding
# comment differently as long as this substring is present verbatim.
NON_QT_APP_MARKER = "NON-QT-APPLICATION-SAFE"


# ─── Markdown fixture exercising every export-relevant feature ──────

MIXED_FIXTURE = """# Heading

Paragraph with **bold** and a [[wiki-target]] and inline $x^2$ math.

> [!NOTE]
> This is a GitHub-style callout.

!!! warning
    And an admonition-style callout.

```python
def greet(name):
    return f"Hello, {name}"
```

- [ ] unchecked task
- [x] checked task

```mermaid
graph TD
    A --> B
```

```dot
digraph G {
    A -> B;
}
```
"""


# ─── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def mixed_md_file(tmp_path):
    """A markdown file on disk containing the mixed fixture."""
    p = tmp_path / "in.md"
    p.write_text(MIXED_FIXTURE, encoding="utf-8")
    return p


@pytest.fixture
def no_diagram_tools(monkeypatch):
    """Force mermaid/graphviz binaries absent so the JS-fallback path
    is deterministic — same setup as Class I invariance tests."""
    monkeypatch.setattr(
        "markdown_editor.markdown6.mermaid_service.has_mermaid",
        lambda: False,
    )
    monkeypatch.setattr(
        "markdown_editor.markdown6.graphviz_service.has_graphviz",
        lambda: False,
    )


# ─── Assertion helpers ──────────────────────────────────────────────

def _assert_preview_grade(html: str, *, label: str):
    """Structural assertions — the HTML was produced by the full
    extension stack (wiki links, callouts, math, diagrams, tasks,
    syntax highlighting). Used by every export-path test."""
    # Wiki link rendered, not literal
    assert "[[wiki-target]]" not in html, (
        f"{label}: wiki link unrendered — stripped renderer still in use"
    )
    assert "wiki-target" in html, f"{label}: wiki link text missing"
    # Callouts (GitHub and admonition) produced callout divs
    assert "callout" in html.lower(), (
        f"{label}: no callout divs — CalloutExtension not running"
    )
    # Math markers (either KaTeX placeholder or specific math class)
    assert "math" in html.lower() or "katex" in html.lower(), (
        f"{label}: no math markers — MathExtension not running"
    )
    # Mermaid container
    assert "mermaid" in html.lower(), (
        f"{label}: no mermaid container — MermaidExtension not running"
    )
    # Graphviz container
    assert "graphviz" in html.lower(), (
        f"{label}: no graphviz container — GraphvizExtension not running"
    )
    # Task list markup
    assert "task-list-item" in html or 'class="checkbox' in html, (
        f"{label}: no task-list markup — TaskListExtension not running"
    )
    # Syntax-highlighted python code (Pygments emits 'highlight' class
    # spans for the CodeHilite extension)
    assert "highlight" in html, (
        f"{label}: no Pygments highlight classes — code not highlighted"
    )


# ─── Test group 1: export_service produces preview-grade HTML ────────

class TestExportServiceProducesPreviewGradeHTML:
    """`export_service.markdown_to_html` and `export_html` must produce
    full preview-grade HTML — not the stripped `[extra, codehilite,
    tables, toc]` output they produce today."""

    def test_markdown_to_html_contains_full_feature_set(self, no_diagram_tools):
        html = export_service.markdown_to_html(MIXED_FIXTURE, title="X")
        _assert_preview_grade(html, label="export_service.markdown_to_html")

    def test_export_html_file_contains_full_feature_set(self, tmp_path, no_diagram_tools):
        out = tmp_path / "out.html"
        export_service.export_html(MIXED_FIXTURE, out, title="X")
        html = out.read_text(encoding="utf-8")
        _assert_preview_grade(html, label="export_service.export_html")


# ─── Test group 2: CLI `mde export -f html` ─────────────────────────

class TestCLIExportProducesPreviewGradeHTML:
    """The CLI's `mde export` subcommand must produce preview-grade
    HTML for both single-file and project exports."""

    def _build_args(self, **overrides) -> argparse.Namespace:
        """Build an argparse.Namespace matching the CLI surface.
        Includes the new --theme / --canonical-fonts flags added in
        Task 6."""
        defaults = dict(
            files=[], project=None, output=None, format="html",
            toc=False, page_breaks=False, title=None, use_pandoc=False,
            theme="light", canonical_fonts=False, quiet=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_single_file_html_export(self, tmp_path, mixed_md_file, no_diagram_tools):
        from markdown_editor.markdown6.markdown_editor_cli import cmd_export
        out = tmp_path / "out.html"
        args = self._build_args(files=[mixed_md_file], output=out)
        rc = cmd_export(args)
        assert rc == 0, "cmd_export returned non-zero"
        html = out.read_text(encoding="utf-8")
        _assert_preview_grade(html, label="CLI single-file export")

    def test_project_html_export(self, tmp_path, no_diagram_tools):
        from markdown_editor.markdown6.markdown_editor_cli import cmd_export
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a.md").write_text(MIXED_FIXTURE, encoding="utf-8")
        (proj / "b.md").write_text("# B\n\nSee [[wiki]].\n", encoding="utf-8")
        out = tmp_path / "out.html"
        args = self._build_args(project=proj, output=out)
        rc = cmd_export(args)
        assert rc == 0
        html = out.read_text(encoding="utf-8")
        _assert_preview_grade(html, label="CLI project export")


# ─── Test group 3: export HTML has <meta charset> and <title> (N+T1) ─

class TestExportHTMLMetaTags:
    """Decision N+T1: exported HTML must carry `<meta charset=\"UTF-8\">`
    and a populated `<title>...</title>`."""

    def test_meta_charset_present(self, tmp_path, no_diagram_tools):
        out = tmp_path / "out.html"
        export_service.export_html(MIXED_FIXTURE, out, title="My Doc")
        html = out.read_text(encoding="utf-8")
        assert '<meta charset="UTF-8">' in html, (
            "exported HTML missing <meta charset='UTF-8'> — added to "
            "PREVIEW_TEMPLATE_FULL via decision N3"
        )

    def test_title_populated_by_export_wrapper(self, tmp_path, no_diagram_tools):
        """T1: export wrapper replaces the empty `<title></title>`
        placeholder with the caller-supplied title."""
        out = tmp_path / "out.html"
        export_service.export_html(MIXED_FIXTURE, out, title="My Special Doc")
        html = out.read_text(encoding="utf-8")
        assert "<title>My Special Doc</title>" in html, (
            "exported HTML's <title> not populated — T1's export-wrapper "
            ".replace() not wired"
        )
        # The empty placeholder must have been replaced, not left in
        assert "<title></title>" not in html

    def test_cli_single_file_title_is_filename_stem(self, tmp_path, mixed_md_file, no_diagram_tools):
        from markdown_editor.markdown6.markdown_editor_cli import cmd_export
        out = tmp_path / "out.html"
        args = argparse.Namespace(
            files=[mixed_md_file], project=None, output=out, format="html",
            toc=False, page_breaks=False, title=None, use_pandoc=False,
            theme="light", canonical_fonts=False,
        )
        cmd_export(args)
        html = out.read_text(encoding="utf-8")
        assert f"<title>{mixed_md_file.stem}</title>" in html, (
            "CLI default title should be the input filename stem"
        )

    def test_cli_explicit_title_flag(self, tmp_path, mixed_md_file, no_diagram_tools):
        from markdown_editor.markdown6.markdown_editor_cli import cmd_export
        out = tmp_path / "out.html"
        args = argparse.Namespace(
            files=[mixed_md_file], project=None, output=out, format="html",
            toc=False, page_breaks=False, title="Custom", use_pandoc=False,
            theme="light", canonical_fonts=False,
        )
        cmd_export(args)
        html = out.read_text(encoding="utf-8")
        assert "<title>Custom</title>" in html


# ─── Test group 4: `scroll_past_end_div` is off in exports (E) ──────

class TestScrollPastEndOffInExports:
    """Decision E: export call sites must hand the renderer a ctx with
    `editor.scroll_past_end=False`. The output must not contain the
    trailing `height: 80vh` placeholder div."""

    def test_export_html_has_no_scroll_past_end_div(self, tmp_path, no_diagram_tools):
        # Make sure the default IS on, so the check is meaningful
        ctx = get_app_context()
        assert ctx.get("editor.scroll_past_end", True), (
            "precondition: scroll_past_end default is True"
        )
        out = tmp_path / "out.html"
        export_service.export_html(MIXED_FIXTURE, out, title="X")
        html = out.read_text(encoding="utf-8")
        assert "height: 80vh" not in html, (
            "exported HTML contains scroll-past-end div — decision E "
            "requires the export path override scroll_past_end=False"
        )


# ─── Test group 5: AppContext.ephemeral_copy() (E implementation) ───

class TestAppContextEphemeralCopy:
    """Decision E requires `AppContext` to expose an ephemeral_copy()
    method so GUI export paths can get a mutable copy without touching
    the live ctx."""

    def test_method_exists(self):
        ctx = get_app_context()
        assert hasattr(ctx, "ephemeral_copy"), (
            "AppContext.ephemeral_copy() method missing"
        )
        assert callable(ctx.ephemeral_copy)

    def test_copy_is_independent(self):
        ctx = get_app_context()
        ctx.set("view.theme", "light")
        copy = ctx.ephemeral_copy()
        copy.set("view.theme", "dark")
        assert ctx.get("view.theme") == "light", (
            "mutating ephemeral copy changed the original — copy is "
            "not actually independent"
        )
        assert copy.get("view.theme") == "dark"

    def test_copy_starts_with_same_values(self):
        ctx = get_app_context()
        ctx.set("view.preview_font_size", 17)
        copy = ctx.ephemeral_copy()
        assert copy.get("view.preview_font_size") == 17

    def test_copy_does_not_persist(self, tmp_path):
        """Ephemeral copies must not write to disk. Mutating the copy's
        settings after instantiation should not create any file on disk
        in the user's config directory."""
        ctx = get_app_context()
        copy = ctx.ephemeral_copy()
        copy.set("view.theme", "dark")
        # If a settings file were written, it would be under
        # ~/.config/markdown-editor/. We can't check that exactly
        # here without intruding on the user, but the ephemeral flag
        # on the underlying manager should be set.
        assert getattr(copy, "_ephemeral", False) is True or \
               getattr(getattr(copy, "_settings", None), "_ephemeral", False) is True, (
            "ephemeral copy not actually ephemeral — could persist "
            "mutations to disk"
        )


# ─── Test group 6: non-Qt-application constraint markers ────────────

class TestNonQtApplicationConstraintMarkers:
    """Decision A requires the renderer core and the app_context modules
    to remain loadable in non-Qt-application environments. This
    constraint is documented via a marker comment in each file; a
    future change that removes the marker (implying the constraint is
    dropped) must break this test."""

    def test_html_renderer_core_exists(self):
        assert HTML_RENDERER_CORE_PATH.exists(), (
            f"{HTML_RENDERER_CORE_PATH} not created — Task 4 incomplete"
        )

    def test_html_renderer_core_has_marker(self):
        assert HTML_RENDERER_CORE_PATH.exists()  # precondition
        text = HTML_RENDERER_CORE_PATH.read_text(encoding="utf-8")
        assert NON_QT_APP_MARKER in text, (
            f"html_renderer_core.py missing the {NON_QT_APP_MARKER} "
            f"constraint marker — see decision A"
        )

    @pytest.mark.parametrize("path", APP_CONTEXT_FILES_WITH_MARKER, ids=lambda p: p.name)
    def test_app_context_files_have_marker(self, path):
        assert path.exists(), f"{path} not found"
        text = path.read_text(encoding="utf-8")
        assert NON_QT_APP_MARKER in text, (
            f"{path.name} missing the {NON_QT_APP_MARKER} constraint "
            f"marker — see decision A"
        )


# ─── Test group 7: CLI argparse surface (C and G decisions) ─────────

class TestCLIArgparseSurface:
    """CLI must expose --theme and --canonical-fonts flags on the
    `export` subcommand (decisions C2 and G).

    Uses subprocess so we test the actual argparse surface rather than
    a hand-built Namespace."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "markdown_editor.markdown6.markdown_editor_cli", *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_export_help_mentions_theme_flag(self):
        result = self._run_cli("export", "--help")
        assert result.returncode == 0
        assert "--theme" in result.stdout, (
            "CLI `mde export --help` does not mention --theme flag "
            "(decision C2)"
        )

    def test_export_help_mentions_canonical_fonts_flag(self):
        result = self._run_cli("export", "--help")
        assert result.returncode == 0
        assert "--canonical-fonts" in result.stdout, (
            "CLI `mde export --help` does not mention --canonical-fonts "
            "flag (decision G)"
        )

    def test_theme_flag_accepts_dark(self, tmp_path, mixed_md_file):
        out = tmp_path / "out.html"
        result = self._run_cli(
            "export", str(mixed_md_file), "-f", "html",
            "-o", str(out), "--theme", "dark",
        )
        assert result.returncode == 0, (
            f"--theme dark rejected: stderr={result.stderr}"
        )
        assert out.exists()


# ─── Test group 8: GUI single-file vs CLI structural equivalence ────

class TestGUIAndCLIStructuralEquivalence:
    """The GUI single-file export and the CLI export must produce
    structurally equivalent HTML for the same input (both use the
    unified renderer). They may differ in theme-determined colors or
    in the title value, but the body feature set must be identical."""

    def test_cli_output_contains_same_feature_markers_as_preview(
        self, tmp_path, mixed_md_file, no_diagram_tools,
    ):
        from markdown_editor.markdown6.markdown_editor_cli import cmd_export

        # CLI output
        out = tmp_path / "out.html"
        args = argparse.Namespace(
            files=[mixed_md_file], project=None, output=out, format="html",
            toc=False, page_breaks=False, title=None, use_pandoc=False,
            theme="light", canonical_fonts=False,
        )
        cmd_export(args)
        cli_html = out.read_text(encoding="utf-8")

        # Preview-style rendering via the shared MarkdownEditor path
        from markdown_editor.markdown6.markdown_editor import MarkdownEditor
        class _H:
            pass
        h = _H()
        h.ctx = get_app_context()
        MarkdownEditor._init_markdown.__get__(h)()
        h.md.reset()
        h.md._pending_diagrams = []
        h.md.mermaid_dark_mode = False
        h.md.graphviz_dark_mode = False
        h.md.graphviz_base_path = None
        h.md.logseq_mode = False
        preview_body = h.md.convert(MIXED_FIXTURE)

        # Every feature present in preview body must also be present in
        # CLI output (the template wrapping adds more, so we check
        # one-way: preview ⊆ CLI).
        for marker in [
            "wiki-target",       # WikiLinks
            "callout",           # Callouts
            "mermaid",           # Mermaid
            "task-list-item",    # TaskList (or "checkbox")
            "highlight",         # Pygments/CodeHilite
        ]:
            if marker in preview_body:
                assert marker in cli_html, (
                    f"Preview body contains {marker!r} but CLI export "
                    f"does not — unified renderer not wired into CLI path"
                )


# ─── Test group 9: WeasyPrint PDF degradation contract (H1) ─────────

class TestWeasyprintPdfDegradationContract:
    """Decision H1: WeasyPrint PDF rides on the unified HTML renderer.
    Math via KaTeX and JS-fallback diagrams will be degraded, but the
    PDF must still be produced (non-empty, no crash)."""

    def test_weasyprint_pdf_produces_nonempty_output(self, tmp_path, no_diagram_tools):
        # Skip if weasyprint cannot run in this environment (missing
        # system libs like libcairo / libpango). That's an environment
        # gap, not an H1-contract issue.
        try:
            from weasyprint import HTML as _WeasyHTML
            _WeasyHTML(string="<html><body>hi</body></html>").write_pdf()
        except Exception as e:
            pytest.skip(f"WeasyPrint not functional in this env: {e}")

        out = tmp_path / "out.pdf"
        export_service.export_pdf(MIXED_FIXTURE, out, title="X", use_pandoc=False)
        assert out.exists(), "WeasyPrint PDF not written"
        assert out.stat().st_size > 0, "WeasyPrint PDF is empty"


# ─── Test group 10: export_service has no hardcoded stripped template ─

class TestExportServiceHasNoHardcodedTemplate:
    """Sanity: after unification, export_service.py must not carry the
    old hardcoded template string or the stripped extension list."""

    def test_no_hardcoded_light_stack(self):
        text = (SRC_ROOT / "export_service.py").read_text(encoding="utf-8")
        # The old template had this specific CSS declaration:
        assert "-apple-system, BlinkMacSystemFont" not in text, (
            "export_service.py still carries the old hardcoded CSS "
            "stack — it should delegate to html_renderer_core instead"
        )

    def test_no_stripped_extension_list(self):
        text = (SRC_ROOT / "export_service.py").read_text(encoding="utf-8")
        # The old construction listed exactly these four extensions:
        assert '["extra", "codehilite", "tables", "toc"]' not in text, (
            "export_service.py still carries the stripped extension "
            "list — it should delegate to html_renderer_core"
        )
