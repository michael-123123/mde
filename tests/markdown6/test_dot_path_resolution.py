"""Tests for `.dot` image reference resolution in export paths.

Covers F3 (source_path plumbing so single-file exports resolve
relative `.dot` refs) and F8 Part 2 (pre-concatenation path
absolutization so multi-file / project exports resolve correctly
across files from different directories). Also locks R1 — the
`_DOT_IMAGE_RE` regex is case-insensitive, matching the renderer's
postprocessor behavior.

The tests mock `graphviz_service.render_dot_file` so they don't
depend on the `dot` binary being installed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# ─── Unit tests: _absolutize_dot_image_paths ───────────────────────

class TestAbsolutizeDotImagePaths:
    """Pure string-transformation tests for the absolutizer."""

    def _sub(self, content: str, source_path: Path) -> str:
        from markdown_editor.markdown6.export_service import (
            _absolutize_dot_image_paths,
        )
        return _absolutize_dot_image_paths(content, source_path)

    def test_rewrites_relative_path(self, tmp_path):
        (tmp_path / "src.md").touch()
        out = self._sub("Here: ![g](./graph.dot)", tmp_path / "src.md")
        expected = str((tmp_path / "graph.dot").resolve())
        assert expected in out, f"relative path not absolutized: {out!r}"
        assert "./graph.dot" not in out

    def test_preserves_title(self, tmp_path):
        (tmp_path / "src.md").touch()
        out = self._sub('![g](./graph.dot "my title")', tmp_path / "src.md")
        assert '"my title"' in out, (
            f"image title attribute not preserved: {out!r}"
        )

    def test_skips_absolute_paths(self, tmp_path):
        (tmp_path / "src.md").touch()
        out = self._sub("![g](/abs/path/graph.dot)", tmp_path / "src.md")
        assert out == "![g](/abs/path/graph.dot)", (
            f"absolute path should be left alone: {out!r}"
        )

    def test_skips_urls(self, tmp_path):
        (tmp_path / "src.md").touch()
        for url in (
            "http://example.com/g.dot",
            "https://example.com/g.dot",
        ):
            out = self._sub(f"![g]({url})", tmp_path / "src.md")
            assert url in out, f"url not preserved: {out!r}"

    def test_case_insensitive_uppercase_DOT(self, tmp_path):
        """R1 coverage — uppercase `.DOT` must be absolutized too."""
        (tmp_path / "src.md").touch()
        out = self._sub("![g](./Graph.DOT)", tmp_path / "src.md")
        expected = str((tmp_path / "Graph.DOT").resolve())
        assert expected in out, (
            f"uppercase .DOT not absolutized (regex not IGNORECASE): {out!r}"
        )

    def test_non_dot_extension_untouched(self, tmp_path):
        (tmp_path / "src.md").touch()
        out = self._sub("![g](./graph.png)", tmp_path / "src.md")
        assert out == "![g](./graph.png)", (
            f"non-.dot ref should be untouched: {out!r}"
        )

    def test_dot_bak_suffix_untouched(self, tmp_path):
        """A path ending in `.dot.bak` should NOT match `.dot`."""
        (tmp_path / "src.md").touch()
        out = self._sub("![g](./graph.dot.bak)", tmp_path / "src.md")
        assert out == "![g](./graph.dot.bak)"

    def test_links_not_images_untouched(self, tmp_path):
        """Non-image `[text](./foo.dot)` links should not be rewritten."""
        (tmp_path / "src.md").touch()
        out = self._sub("See [graph source](./graph.dot)", tmp_path / "src.md")
        assert out == "See [graph source](./graph.dot)"

    def test_multiple_refs_in_one_string(self, tmp_path):
        (tmp_path / "src.md").touch()
        out = self._sub(
            "![a](./a.dot) and ![b](./sub/b.dot)",
            tmp_path / "src.md",
        )
        abs_a = str((tmp_path / "a.dot").resolve())
        abs_b = str((tmp_path / "sub" / "b.dot").resolve())
        assert abs_a in out, f"first ref not absolutized: {out!r}"
        assert abs_b in out, f"second ref not absolutized: {out!r}"


# ─── Unit tests: combine_project_markdown absolutizes per file ─────

class TestCombineProjectMarkdownAbsolutizesDotPaths:
    """The combiner must absolutize `.dot` refs on a per-file basis so
    relative refs anchored to each file's parent dir resolve correctly
    after concatenation."""

    def test_per_file_resolution(self, tmp_path):
        from markdown_editor.markdown6.export_service import (
            combine_project_markdown,
        )

        a_dir = tmp_path / "dir_a"
        b_dir = tmp_path / "dir_b"
        a_dir.mkdir()
        b_dir.mkdir()

        a_md = a_dir / "a.md"
        b_md = b_dir / "b.md"

        # Each file references `./graph.dot` — same relative path but
        # anchored to different parent dirs.
        documents = [
            (a_md, "# A\n\n![graph](./graph.dot)\n"),
            (b_md, "# B\n\n![graph](./graph.dot)\n"),
        ]
        combined = combine_project_markdown(documents)

        # The combined string must contain each file's RESOLVED
        # absolute path, not the literal `./graph.dot` (which would
        # resolve to whichever parent graphviz_base_path happened to
        # point at — i.e. wrong for at least one file).
        abs_a = str((a_dir / "graph.dot").resolve())
        abs_b = str((b_dir / "graph.dot").resolve())
        assert abs_a in combined, (
            f"dir_a's graph.dot not absolutized to {abs_a}"
        )
        assert abs_b in combined, (
            f"dir_b's graph.dot not absolutized to {abs_b}"
        )


# ─── Integration: CLI single-file export wires source_path ─────────

class TestCLISingleFileExportPassesSourcePath:
    """The CLI single-file export (F3) must pass `source_path=args.files[0]`
    so the renderer's `graphviz_base_path` points to the source dir,
    enabling the renderer's postprocessor to resolve relative `.dot`
    refs against the right directory."""

    def test_render_dot_file_called_with_resolved_path(
        self, tmp_path, monkeypatch,
    ):
        # Set up the source .md with a relative .dot image ref.
        src_md = tmp_path / "doc.md"
        dot_file = tmp_path / "graph.dot"
        src_md.write_text("![graph](./graph.dot)\n", encoding="utf-8")
        dot_file.write_text("digraph G { A -> B; }\n", encoding="utf-8")

        # Mock has_graphviz=True and render_dot_file → sentinel SVG.
        # Capture the path the renderer receives so we can assert on it.
        called_with: list[Path] = []

        def fake_render_dot_file(file_path, dark_mode=False):
            called_with.append(Path(file_path))
            return ('<svg class="sentinel">ok</svg>', None)

        monkeypatch.setattr(
            "markdown_editor.markdown6.graphviz_service.has_graphviz",
            lambda: True,
        )
        monkeypatch.setattr(
            "markdown_editor.markdown6.graphviz_service.render_dot_file",
            fake_render_dot_file,
        )

        # Invoke cmd_export with a hand-built Namespace.
        from markdown_editor.markdown6.markdown_editor_cli import cmd_export

        out = tmp_path / "out.html"
        args = argparse.Namespace(
            files=[src_md], project=None, output=out, format="html",
            toc=False, page_breaks=False, title=None, use_pandoc=False,
            theme="light", canonical_fonts=False, quiet=True,
        )
        rc = cmd_export(args)
        assert rc == 0, "cmd_export returned non-zero"

        # Renderer should have been called with the resolved absolute
        # path to our .dot file (resolved via source_path parent).
        assert called_with, (
            "graphviz_service.render_dot_file was never called — "
            "source_path plumbing broken"
        )
        expected = (tmp_path / "graph.dot").resolve()
        assert called_with[0] == expected, (
            f"Expected render_dot_file called with {expected}, "
            f"got {called_with[0]}"
        )

        # And the sentinel SVG must appear in the output.
        html = out.read_text(encoding="utf-8")
        assert "sentinel" in html, "rendered SVG not inlined"


# ─── Integration: CLI multi-file export absolutizes per file ───────

class TestCLIMultiFileExportAbsolutizesDotPaths:
    """CLI multi-file export (F8 Part 1 + Part 2) must route through
    `combine_project_markdown`, which absolutizes `.dot` refs per file
    so each file's `./graph.dot` resolves against its own parent."""

    def test_multiple_files_different_dirs(self, tmp_path, monkeypatch):
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()

        a_md = a_dir / "a.md"
        b_md = b_dir / "b.md"
        a_dot = a_dir / "graph.dot"
        b_dot = b_dir / "graph.dot"

        a_md.write_text("# A\n\n![g](./graph.dot)\n", encoding="utf-8")
        b_md.write_text("# B\n\n![g](./graph.dot)\n", encoding="utf-8")
        a_dot.write_text("digraph A { a -> a; }", encoding="utf-8")
        b_dot.write_text("digraph B { b -> b; }", encoding="utf-8")

        called_with: list[Path] = []

        def fake_render_dot_file(file_path, dark_mode=False):
            called_with.append(Path(file_path))
            return (f'<svg>{Path(file_path).parent.name}</svg>', None)

        monkeypatch.setattr(
            "markdown_editor.markdown6.graphviz_service.has_graphviz",
            lambda: True,
        )
        monkeypatch.setattr(
            "markdown_editor.markdown6.graphviz_service.render_dot_file",
            fake_render_dot_file,
        )

        from markdown_editor.markdown6.markdown_editor_cli import cmd_export

        out = tmp_path / "combined.html"
        args = argparse.Namespace(
            files=[a_md, b_md], project=None, output=out, format="html",
            toc=False, page_breaks=False, title=None, use_pandoc=False,
            theme="light", canonical_fonts=False, quiet=True,
        )
        rc = cmd_export(args)
        assert rc == 0

        # Both files' .dot refs should have been resolved — each
        # against ITS OWN parent dir.
        assert len(called_with) == 2, (
            f"expected 2 render_dot_file calls, got {len(called_with)}: "
            f"{called_with}"
        )
        called_paths = {p.resolve() for p in called_with}
        assert a_dot.resolve() in called_paths, (
            f"dir_a/graph.dot not rendered — per-file absolutization "
            f"failed. Calls: {called_with}"
        )
        assert b_dot.resolve() in called_paths, (
            f"dir_b/graph.dot not rendered — per-file absolutization "
            f"failed. Calls: {called_with}"
        )

        html = out.read_text(encoding="utf-8")
        assert "<svg>a</svg>" in html
        assert "<svg>b</svg>" in html
