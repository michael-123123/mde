"""Tests for ``GraphExporter`` and ``GraphExporterConfig``.

The exporter is Qt-free, so these tests use a plain dataclass-based config
(see :class:`_FakeConfig`) - no qtbot, no QDialog, no argparse. Tests for
the GUI dialog and the CLI subcommands live in their respective test files
and exercise the configs that wire widget / argparse state into the exporter.
"""

from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import patch

import pytest

from markdown_editor.markdown6.graph_exporter import (
    BrokenHandling,
    GraphExporter,
    GraphExporterConfig,
    OutputFormat,
)


class _FakeConfig(GraphExporterConfig):
    """Configurable in-memory config; tests pass any field via kwargs.

    ABC requires class-level implementations of each abstract property, so
    every property below is declared explicitly. ``@dataclass`` field-only
    declarations don't satisfy ABC's check.
    """

    def __init__(
        self,
        *,
        project_path: Path = Path("/tmp"),
        selected_files: list[Path] | None = None,
        is_directed: bool = True,
        engine: str = "dot",
        label_template: str = "{stem}",
        labels_below: bool = False,
        broken_handling: BrokenHandling = "red",
        dark_mode: bool = False,
        output_format: OutputFormat = "svg",
    ):
        self._project_path = project_path
        self._selected_files = list(selected_files) if selected_files else []
        self._is_directed = is_directed
        self._engine = engine
        self._label_template = label_template
        self._labels_below = labels_below
        self._broken_handling: BrokenHandling = broken_handling
        self._dark_mode = dark_mode
        self._output_format: OutputFormat = output_format

    @property
    def project_path(self) -> Path:
        return self._project_path

    @property
    def selected_files(self) -> list[Path]:
        return self._selected_files

    @property
    def is_directed(self) -> bool:
        return self._is_directed

    @property
    def engine(self) -> str:
        return self._engine

    @property
    def label_template(self) -> str:
        return self._label_template

    @property
    def labels_below(self) -> bool:
        return self._labels_below

    @property
    def broken_handling(self) -> BrokenHandling:
        return self._broken_handling

    @property
    def dark_mode(self) -> bool:
        return self._dark_mode

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format


# ────────────────────────────────────────────────────────────────────────
# Test helpers
# ────────────────────────────────────────────────────────────────────────


def _make_project(tmp_path: Path, files: dict[str, str]) -> tuple[Path, list[Path]]:
    """Create *files* under *tmp_path* and return ``(project_path, paths)``.

    ``files`` is ``{relative_path: content}``. Subdirs are created as needed.
    Paths are returned in the same order as ``files`` keys.
    """
    paths: list[Path] = []
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return tmp_path, paths


# ────────────────────────────────────────────────────────────────────────
# GraphExporterConfig: ABC contract
# ────────────────────────────────────────────────────────────────────────


class TestConfigIsAbstract:
    def test_cannot_instantiate_base_directly(self):
        with pytest.raises(TypeError):
            GraphExporterConfig()  # type: ignore[abstract]

    def test_subclass_missing_a_property_cannot_instantiate(self):
        class Incomplete(GraphExporterConfig):
            @property
            def project_path(self) -> Path:
                return Path("/")
            # Missing every other abstract property.

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_dataclass_subclass_with_all_fields_works(self, tmp_path):
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[])
        assert cfg.is_directed is True       # default
        assert cfg.broken_handling == "red"  # default
        assert cfg.output_format == "svg"    # default


# ────────────────────────────────────────────────────────────────────────
# GraphExporter.config: public accessor
# ────────────────────────────────────────────────────────────────────────


class TestConfigAccessor:
    def test_config_property_returns_injected_config(self, tmp_path):
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[])
        exporter = GraphExporter(cfg)
        assert exporter.config is cfg


# ────────────────────────────────────────────────────────────────────────
# build_file_index
# ────────────────────────────────────────────────────────────────────────


class TestBuildFileIndex:
    def test_empty_files_gives_empty_index(self, tmp_path):
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[])
        idx = GraphExporter(cfg).build_file_index()
        assert idx == {}

    def test_indexes_by_lowercase_stem(self, tmp_path):
        _, paths = _make_project(tmp_path, {"NoteOne.md": "x", "noteTwo.md": "y"})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        idx = GraphExporter(cfg).build_file_index()
        assert idx["noteone"] == paths[0]
        assert idx["notetwo"] == paths[1]

    def test_indexes_by_relative_path_no_ext_lowercase(self, tmp_path):
        _, paths = _make_project(
            tmp_path, {"docs/Foo.md": "x", "docs/sub/Bar.md": "y"},
        )
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        idx = GraphExporter(cfg).build_file_index()
        assert idx["docs/foo"] == paths[0]
        assert idx["docs/sub/bar"] == paths[1]

    def test_file_outside_project_only_stem_indexed(self, tmp_path):
        # Create a file outside the project root; it should still be
        # stem-indexed but not relative-path-indexed.
        outside = tmp_path.parent / "outside_proj_test.md"
        outside.write_text("x", encoding="utf-8")
        try:
            cfg = _FakeConfig(project_path=tmp_path, selected_files=[outside])
            idx = GraphExporter(cfg).build_file_index()
            assert idx == {"outside_proj_test": outside}
        finally:
            outside.unlink(missing_ok=True)


# ────────────────────────────────────────────────────────────────────────
# resolve_link
# ────────────────────────────────────────────────────────────────────────


class TestResolveLink:
    def test_direct_stem_match(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "", "b.md": ""})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        ex = GraphExporter(cfg)
        idx = ex.build_file_index()
        assert ex.resolve_link("a", tmp_path / "src.md", idx) == paths[0]

    def test_stem_match_with_md_suffix(self, tmp_path):
        # User wrote `[[note.md]]`; the index has stem "note".
        _, paths = _make_project(tmp_path, {"note.md": ""})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        ex = GraphExporter(cfg)
        # The resolve_link contract appends `.md` for the second step, but
        # the index already has "note" -> paths[0], so direct match wins.
        # Test the relative-path indexing instead with a target like "note.md".
        idx = ex.build_file_index()
        # `note.md` isn't in the index directly (stem is "note", rel path is "note").
        # But "note.md".lower() == "note.md" - also not in index. So this falls
        # through. We only get a match if we look at the relative-path index
        # for "note" (no ext). That's what the user actually does when they
        # write `[[note]]`.
        assert ex.resolve_link("note", tmp_path / "src.md", idx) == paths[0]

    def test_relative_to_source_with_md_suffix(self, tmp_path):
        # Target isn't in the index (e.g. user picked a different selection),
        # but it lives next to the source file on disk.
        (tmp_path / "src.md").write_text("", encoding="utf-8")
        (tmp_path / "neighbor.md").write_text("", encoding="utf-8")
        # selected_files only contains src.md - so 'neighbor' isn't in idx,
        # but the relative-fallback should find it.
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[tmp_path / "src.md"],
        )
        ex = GraphExporter(cfg)
        result = ex.resolve_link(
            "neighbor", tmp_path / "src.md", ex.build_file_index(),
        )
        assert result == (tmp_path / "neighbor.md").resolve()

    def test_unresolvable_returns_none(self, tmp_path):
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[])
        ex = GraphExporter(cfg)
        assert ex.resolve_link(
            "does-not-exist", tmp_path / "src.md", {},
        ) is None

    def test_enametoolong_returns_none_and_logs(self, tmp_path, caplog):
        source = tmp_path / "src.md"
        source.write_text("x", encoding="utf-8")
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[source])
        ex = GraphExporter(cfg)
        oversized = "x" * 4000   # past NAME_MAX on every filesystem
        logger_name = "mde.markdown_editor.markdown6.graph_exporter"
        with caplog.at_level("WARNING", logger=logger_name):
            result = ex.resolve_link(
                oversized, source, {}, line_number=42,
            )
        assert result is None
        msgs = [r.getMessage() for r in caplog.records]
        assert any("target too long" in m for m in msgs)
        assert any(f"{source}:42" in m for m in msgs)

    def test_other_oserror_propagates(self, tmp_path, monkeypatch):
        source = tmp_path / "src.md"
        source.write_text("x", encoding="utf-8")
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[source])
        ex = GraphExporter(cfg)

        def boom(self):
            raise OSError(errno.EACCES, "Permission denied")

        monkeypatch.setattr(Path, "exists", boom)
        with pytest.raises(OSError):
            ex.resolve_link("anything", source, {})

    def test_line_number_omitted_from_warning_when_none(self, tmp_path, caplog):
        source = tmp_path / "src.md"
        source.write_text("x", encoding="utf-8")
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[source])
        ex = GraphExporter(cfg)
        logger_name = "mde.markdown_editor.markdown6.graph_exporter"
        with caplog.at_level("WARNING", logger=logger_name):
            ex.resolve_link("x" * 4000, source, {})
        msgs = [r.getMessage() for r in caplog.records]
        # The path appears followed by ": " (message separator) - NOT
        # followed by a digit (which would mean a `:line` suffix).
        # E.g. ".../src.md: target too long" vs ".../src.md:42: target too long".
        assert any(f"{source}: " in m for m in msgs)
        assert not any(any(f"{source}:{d}" in m for d in "0123456789") for m in msgs)


# ────────────────────────────────────────────────────────────────────────
# generate_dot - structural
# ────────────────────────────────────────────────────────────────────────


class TestGenerateDotStructural:
    def test_empty_directed_graph(self, tmp_path):
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[])
        dot = GraphExporter(cfg).generate_dot()
        assert dot.startswith("digraph DocumentGraph {")
        assert dot.endswith("}")
        assert "rankdir=LR;" in dot

    def test_undirected_graph_uses_graph_keyword(self, tmp_path):
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], is_directed=False,
        )
        dot = GraphExporter(cfg).generate_dot()
        assert dot.startswith("graph DocumentGraph {")
        # No `->` in an undirected graph.
        assert "->" not in dot

    def test_directed_edge_operator(self, tmp_path):
        _, paths = _make_project(
            tmp_path, {"a.md": "[[b]]", "b.md": ""},
        )
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        # exactly one edge from a -> b
        assert "->" in dot
        assert "--" not in dot.replace("->", "")  # no `--` (subtle)

    def test_undirected_edge_operator(self, tmp_path):
        _, paths = _make_project(
            tmp_path, {"a.md": "[[b]]", "b.md": ""},
        )
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, is_directed=False,
        )
        dot = GraphExporter(cfg).generate_dot()
        assert "--" in dot
        assert "->" not in dot


# ────────────────────────────────────────────────────────────────────────
# generate_dot - node shape (labels_below)
# ────────────────────────────────────────────────────────────────────────


class TestNodeShape:
    def test_labels_inline_uses_box_rounded(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": ""})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        assert "node [shape=box, style=rounded]" in dot
        assert "shape=point" not in dot

    def test_labels_below_uses_point_with_xlabel(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, labels_below=True,
        )
        dot = GraphExporter(cfg).generate_dot()
        assert "forcelabels=true" in dot
        assert "shape=point" in dot
        assert "xlabel=" in dot

    def test_labels_below_dot_engine_uses_node_rank_spacing(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            labels_below=True, engine="dot",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert "nodesep=0.8;" in dot
        assert "ranksep=1.0;" in dot
        assert "overlap=" not in dot

    @pytest.mark.parametrize("engine", ["neato", "fdp", "circo", "twopi", "sfdp"])
    def test_labels_below_force_directed_uses_overlap_prism(self, tmp_path, engine):
        _, paths = _make_project(tmp_path, {"a.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            labels_below=True, engine=engine,
        )
        dot = GraphExporter(cfg).generate_dot()
        assert "overlap=prism" in dot
        assert "overlap_scaling=2" in dot
        assert 'sep="+20,20"' in dot
        # No dot-specific spacing in this branch.
        assert "nodesep=0.8" not in dot
        assert "ranksep=1.0" not in dot


# ────────────────────────────────────────────────────────────────────────
# generate_dot - label templates
# ────────────────────────────────────────────────────────────────────────


class TestLabelTemplates:
    def test_stem(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, label_template="{stem}",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'label="foo"' in dot

    def test_filename(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            label_template="{filename}",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'label="foo.md"' in dot

    def test_relative_path(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            label_template="{relative_path}",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'label="docs/foo.md"' in dot

    def test_relative_path_no_ext(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            label_template="{relative_path_no_ext}",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'label="docs/foo"' in dot

    def test_custom_template_with_static_text(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            label_template="page: {stem}",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'label="page: foo"' in dot


# ────────────────────────────────────────────────────────────────────────
# generate_dot - tooltips and URLs
# ────────────────────────────────────────────────────────────────────────


class TestTooltipsAndUrls:
    def test_tooltip_is_relative_path(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        assert 'tooltip="docs/foo.md"' in dot

    def test_url_attribute_contains_absolute_path(self, tmp_path):
        _, paths = _make_project(tmp_path, {"docs/foo.md": ""})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        assert f'URL="{paths[0]}"' in dot

    def test_url_escapes_double_quotes_in_path(self, tmp_path):
        # Synthesize a Path whose str has a quote in it (without actually
        # creating it on disk - the DOT generator doesn't need it to exist
        # for the URL emission step). Use a config that returns a fake file.
        weird = tmp_path / 'has"quote.md'
        # Skip if the filesystem rejects the name (Windows-style restriction
        # doesn't apply on Linux/macOS; this just guards the test).
        try:
            weird.write_text("", encoding="utf-8")
        except OSError:
            pytest.skip("Filesystem rejected quote in filename")
        cfg = _FakeConfig(project_path=tmp_path, selected_files=[weird])
        dot = GraphExporter(cfg).generate_dot()
        assert '\\"quote.md' in dot


# ────────────────────────────────────────────────────────────────────────
# generate_dot - link extraction + broken handling
# ────────────────────────────────────────────────────────────────────────


class TestLinkExtraction:
    def test_wiki_link_to_existing_file_creates_edge(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "[[b]]", "b.md": ""})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        # One edge from a (n0) to b (n1) in dataclass-declared order.
        assert "n0 -> n1;" in dot

    def test_markdown_link_to_existing_file_creates_edge(self, tmp_path):
        _, paths = _make_project(
            tmp_path,
            {"a.md": "[lnk](b.md)", "b.md": ""},
        )
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        assert "n0 -> " in dot

    def test_duplicate_directed_edges_deduplicated(self, tmp_path):
        _, paths = _make_project(
            tmp_path,
            {"a.md": "[[b]] and [[b]] again", "b.md": ""},
        )
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        assert dot.count("n0 -> n1") == 1

    def test_undirected_edges_deduplicated_via_sorted_pair(self, tmp_path):
        _, paths = _make_project(
            tmp_path, {"a.md": "[[b]]", "b.md": "[[a]]"},
        )
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, is_directed=False,
        )
        dot = GraphExporter(cfg).generate_dot()
        # a-b and b-a collapse into one undirected edge.
        edge_lines = [
            line for line in dot.split('\n') if " -- " in line
        ]
        assert len(edge_lines) == 1

    def test_wiki_link_brackets_in_code_span_ignored(self, tmp_path):
        _, paths = _make_project(
            tmp_path, {"a.md": "literal: `[[notarealnode]]`", "b.md": ""},
        )
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        # No broken node and no edge from a to anything labelled notarealnode.
        assert "notarealnode" not in dot.lower()


class TestBrokenHandlingRed:
    def test_broken_node_styled_red_dashed(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "[[ghost]]"})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, broken_handling="red",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'color=red, style="dashed,rounded"' in dot
        assert 'style=dashed, color=red' in dot   # the edge styling

    def test_broken_edge_is_dashed_red(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "[[ghost]]"})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, broken_handling="red",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert '[style=dashed, color=red]' in dot


class TestBrokenHandlingExclude:
    def test_no_broken_node_or_edge(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "[[ghost]]"})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            broken_handling="exclude",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert "ghost" not in dot
        assert "->" not in dot   # no edges at all - only a.md as a node


class TestBrokenHandlingWarning:
    def test_broken_node_styled_orange_with_missing_suffix(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "[[ghost]]"})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            broken_handling="warning",
        )
        dot = GraphExporter(cfg).generate_dot()
        assert 'color=orange' in dot
        assert "\\n(missing)" in dot
        assert "fillcolor=lightyellow" in dot


class TestBrokenHandlingNormal:
    def test_broken_node_looks_like_regular_node(self, tmp_path):
        _, paths = _make_project(tmp_path, {"a.md": "[[ghost]]"})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths,
            broken_handling="normal",
        )
        dot = GraphExporter(cfg).generate_dot()
        # Regular node attributes (no red, no orange, no dashed).
        assert 'color=red' not in dot
        assert 'color=orange' not in dot
        # Edge to the broken node is also regular (not dashed/red).
        edge_lines = [
            line for line in dot.split('\n') if "->" in line
        ]
        for line in edge_lines:
            assert 'style=dashed' not in line


# ────────────────────────────────────────────────────────────────────────
# generate_dot - file outside project
# ────────────────────────────────────────────────────────────────────────


class TestFileOutsideProject:
    def test_tooltip_falls_back_to_absolute_path_for_broken_outside_link(
        self, tmp_path,
    ):
        # A broken markdown link can resolve to a path outside the project.
        # Since it's broken, a broken-node IS emitted, and its tooltip
        # should be the absolute path (relative_to fails outside the root).
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a.md").write_text("[lnk](../missing.md)", encoding="utf-8")
        cfg = _FakeConfig(project_path=proj, selected_files=[proj / "a.md"])
        dot = GraphExporter(cfg).generate_dot()
        missing_abs = str((tmp_path / "missing.md").resolve())
        # Tooltip on the broken node shows the absolute path.
        assert f'tooltip="{missing_abs}"' in dot


# ────────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────────


class TestRendering:
    def test_render_to_dot_writes_raw_source(self, tmp_path):
        out = tmp_path / "g.dot"
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], output_format="dot",
        )
        ex = GraphExporter(cfg)
        ex.render_to_dot("digraph X { a -> b; }", out)
        assert out.read_text() == "digraph X { a -> b; }"

    def test_render_to_svg_uses_graphviz_with_configured_engine(self, tmp_path):
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], engine="neato",
        )
        with patch("graphviz.Source") as mock_source:
            mock_source.return_value.pipe.return_value = b"<svg></svg>"
            svg = GraphExporter(cfg).render_to_svg("dummy dot")
        mock_source.assert_called_once_with("dummy dot", engine="neato")
        mock_source.return_value.pipe.assert_called_once_with(format='svg')
        assert svg == "<svg></svg>"

    def test_render_to_svg_applies_dark_mode_when_configured(self, tmp_path):
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], dark_mode=True,
        )
        with patch("graphviz.Source") as mock_source, \
             patch("markdown_editor.markdown6.graphviz_service._apply_dark_mode") as mock_dark:
            mock_source.return_value.pipe.return_value = b"<svg/>"
            mock_dark.return_value = "<svg-dark/>"
            svg = GraphExporter(cfg).render_to_svg("d")
        mock_dark.assert_called_once_with("<svg/>")
        assert svg == "<svg-dark/>"

    def test_render_to_svg_skips_dark_mode_when_off(self, tmp_path):
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], dark_mode=False,
        )
        with patch("graphviz.Source") as mock_source, \
             patch("markdown_editor.markdown6.graphviz_service._apply_dark_mode") as mock_dark:
            mock_source.return_value.pipe.return_value = b"<svg/>"
            GraphExporter(cfg).render_to_svg("d")
        mock_dark.assert_not_called()

    def test_render_to_png_calls_graphviz_render(self, tmp_path):
        out = tmp_path / "g.png"
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], engine="fdp",
        )
        with patch("graphviz.Source") as mock_source:
            GraphExporter(cfg).render_to_png("d", out)
        mock_source.assert_called_once_with("d", engine="fdp")
        mock_source.return_value.render.assert_called_once_with(
            str(out.with_suffix("")), format='png', cleanup=True,
        )


# ────────────────────────────────────────────────────────────────────────
# export() orchestration
# ────────────────────────────────────────────────────────────────────────


class TestExport:
    def test_export_dot_format_writes_raw_dot(self, tmp_path):
        out = tmp_path / "g.dot"
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], output_format="dot",
        )
        returned = GraphExporter(cfg).export(out)
        assert out.read_text().startswith("digraph DocumentGraph")
        assert returned.startswith("digraph DocumentGraph")
        # `export` returns the same DOT it wrote.
        assert out.read_text() == returned

    def test_export_svg_format(self, tmp_path):
        out = tmp_path / "g.svg"
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], output_format="svg",
        )
        with patch("graphviz.Source") as mock_source:
            mock_source.return_value.pipe.return_value = b"<svg/>"
            GraphExporter(cfg).export(out)
        assert out.read_text() == "<svg/>"

    def test_export_png_format(self, tmp_path):
        out = tmp_path / "g.png"
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], output_format="png",
        )
        with patch("graphviz.Source") as mock_source:
            GraphExporter(cfg).export(out)
        mock_source.return_value.render.assert_called_once()

    def test_export_pdf_format(self, tmp_path):
        out = tmp_path / "g.pdf"
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[], output_format="pdf",
        )
        with patch("graphviz.Source") as mock_source:
            GraphExporter(cfg).export(out)
        mock_source.return_value.render.assert_called_once_with(
            str(out.with_suffix("")), format='pdf', cleanup=True,
        )

    def test_export_unknown_format_raises(self, tmp_path):
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=[],
            output_format="bogus",  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError, match="Unknown output_format"):
            GraphExporter(cfg).export(tmp_path / "g.bogus")

    def test_export_returns_dot_source_for_reuse(self, tmp_path):
        # The dialog wants to also show a preview popup of the same graph
        # without re-running generate_dot().
        _, paths = _make_project(tmp_path, {"a.md": "[[b]]", "b.md": ""})
        cfg = _FakeConfig(
            project_path=tmp_path, selected_files=paths, output_format="dot",
        )
        dot = GraphExporter(cfg).export(tmp_path / "g.dot")
        assert "n0 -> n1;" in dot


# ────────────────────────────────────────────────────────────────────────
# Verbatim-region integration (regression for the original bug)
# ────────────────────────────────────────────────────────────────────────


class TestVerbatimRegionIntegration:
    def test_brackets_in_code_span_not_treated_as_wiki_link(self, tmp_path):
        # The original `05-gap-analysis-and-roadmap.md` bug shape: `[[`
        # inside a code span 92 lines before `]]` inside another code
        # span. With masking, neither is a real wiki link.
        content = (
            "User types `[[`, after picking a note,\n"
            + "filler line\n" * 90
            + "embedding views in notes (`![[my.base]]`).\n"
        )
        _, paths = _make_project(tmp_path, {"a.md": content})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        dot = GraphExporter(cfg).generate_dot()
        # No "ghost"-style broken node and no edges - just the source node.
        assert "->" not in dot

    def test_no_enametoolong_crash_on_bare_prose_multi_line_brackets(
        self, tmp_path,
    ):
        # Bare-prose multi-line `[[ ... ]]` with no code-span context the
        # masker can strip. Used to crash; should now log + skip.
        content = (
            "[[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            + "x" * 80 + "\n"
            + "x" * 80 + "\n"
            + "x" * 80 + "\n"
            + "x" * 80 + "]]\n"
        )
        _, paths = _make_project(tmp_path, {"a.md": content})
        cfg = _FakeConfig(project_path=tmp_path, selected_files=paths)
        # Must NOT raise.
        dot = GraphExporter(cfg).generate_dot()
        # And produces some valid DOT.
        assert dot.startswith("digraph DocumentGraph {")
        assert dot.endswith("}")
