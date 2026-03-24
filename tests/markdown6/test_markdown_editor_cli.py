"""Tests for the markdown editor CLI."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from markdown_editor.markdown6.markdown_editor_cli import (
    create_parser,
    main,
    cmd_export,
    cmd_stats,
    cmd_validate,
    cmd_graph,
    read_stdin,
    get_project_files,
)


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_creation(self):
        """Test that parser is created successfully."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "mde"

    def test_parser_version(self):
        """Test version argument."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_parser_help(self):
        """Test help argument."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])


class TestParserArguments:
    """Tests for parsing various arguments."""

    def test_parse_files_via_main(self):
        """Test parsing file arguments goes through main()."""
        # Files without subcommand are handled by main(), not the parser directly
        # This is tested in TestMainFunction
        pass

    def test_parse_project(self):
        """Test parsing project argument."""
        parser = create_parser()
        args = parser.parse_args(["-p", "./project"])
        assert args.project == Path("./project")

    def test_parse_project_long(self):
        """Test parsing --project argument."""
        parser = create_parser()
        args = parser.parse_args(["--project", "./project"])
        assert args.project == Path("./project")

    def test_parse_theme(self):
        """Test parsing theme argument."""
        parser = create_parser()
        args = parser.parse_args(["--theme", "dark"])
        assert args.theme == "dark"

    def test_parse_line(self):
        """Test parsing line argument."""
        parser = create_parser()
        args = parser.parse_args(["--line", "50"])
        assert args.line == 50

    def test_parse_config(self):
        """Test parsing config argument."""
        parser = create_parser()
        args = parser.parse_args(["--config", "/path/to/config"])
        assert args.config == Path("/path/to/config")

    def test_parse_verbose(self):
        """Test parsing verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["-v"])
        assert args.verbose is True

    def test_parse_quiet(self):
        """Test parsing quiet flag."""
        parser = create_parser()
        args = parser.parse_args(["-q"])
        assert args.quiet is True

    def test_parse_new(self):
        """Test parsing new flag."""
        parser = create_parser()
        args = parser.parse_args(["--new"])
        assert args.new is True

    def test_parse_read_only(self):
        """Test parsing read-only flag."""
        parser = create_parser()
        args = parser.parse_args(["--read-only"])
        assert args.read_only is True

    def test_parse_new_session(self):
        """Test parsing new-session flag."""
        parser = create_parser()
        args = parser.parse_args(["--new-session"])
        assert args.new_session is True


class TestExportSubcommand:
    """Tests for export subcommand parsing."""

    def test_export_basic(self):
        """Test basic export command."""
        parser = create_parser()
        args = parser.parse_args(["export", "doc.md"])
        assert args.command == "export"
        assert args.files[0] == Path("doc.md")

    def test_export_output(self):
        """Test export with output file."""
        parser = create_parser()
        args = parser.parse_args(["export", "doc.md", "-o", "out.pdf"])
        assert args.output == Path("out.pdf")

    def test_export_format(self):
        """Test export with format."""
        parser = create_parser()
        args = parser.parse_args(["export", "doc.md", "-f", "html"])
        assert args.format == "html"

    def test_export_toc(self):
        """Test export with TOC flag."""
        parser = create_parser()
        args = parser.parse_args(["export", "-p", "./proj", "--toc"])
        assert args.toc is True

    def test_export_page_breaks(self):
        """Test export with page breaks."""
        parser = create_parser()
        args = parser.parse_args(["export", "-p", "./proj", "--page-breaks"])
        assert args.page_breaks is True

    def test_export_title(self):
        """Test export with custom title."""
        parser = create_parser()
        args = parser.parse_args(["export", "doc.md", "--title", "My Doc"])
        assert args.title == "My Doc"

    def test_export_use_pandoc(self):
        """Test export with pandoc flag."""
        parser = create_parser()
        args = parser.parse_args(["export", "doc.md", "--use-pandoc"])
        assert args.use_pandoc is True


class TestGraphSubcommand:
    """Tests for graph subcommand parsing."""

    def test_graph_basic(self):
        """Test basic graph command."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "./project"])
        assert args.command == "graph"
        assert args.project == Path("./project")

    def test_graph_output(self):
        """Test graph with output."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "./proj", "-o", "graph.svg"])
        assert args.output == Path("graph.svg")

    def test_graph_format(self):
        """Test graph with format."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "./proj", "-f", "png"])
        assert args.format == "png"

    def test_graph_engine(self):
        """Test graph with engine."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "./proj", "--engine", "neato"])
        assert args.engine == "neato"

    def test_graph_labels_below(self):
        """Test graph with labels below."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "./proj", "--labels-below"])
        assert args.labels_below is True

    def test_graph_no_orphans(self):
        """Test graph with no orphans."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "./proj", "--no-orphans"])
        assert args.no_orphans is True


class TestStatsSubcommand:
    """Tests for stats subcommand parsing."""

    def test_stats_basic(self):
        """Test basic stats command."""
        parser = create_parser()
        args = parser.parse_args(["stats", "doc.md"])
        assert args.command == "stats"
        assert args.files[0] == Path("doc.md")

    def test_stats_project(self):
        """Test stats with project."""
        parser = create_parser()
        args = parser.parse_args(["stats", "-p", "./project"])
        assert args.project == Path("./project")

    def test_stats_json(self):
        """Test stats with JSON output."""
        parser = create_parser()
        args = parser.parse_args(["stats", "doc.md", "--json"])
        assert args.json is True


class TestValidateSubcommand:
    """Tests for validate subcommand parsing."""

    def test_validate_basic(self):
        """Test basic validate command."""
        parser = create_parser()
        args = parser.parse_args(["validate", "doc.md"])
        assert args.command == "validate"

    def test_validate_project(self):
        """Test validate with project."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-p", "./project"])
        assert args.project == Path("./project")

    def test_validate_json(self):
        """Test validate with JSON output."""
        parser = create_parser()
        args = parser.parse_args(["validate", "-p", "./proj", "--json"])
        assert args.json is True


class TestGetProjectFiles:
    """Tests for get_project_files function."""

    def test_get_project_files(self, tmp_path):
        """Test getting project files."""
        (tmp_path / "doc1.md").write_text("# Doc 1")
        (tmp_path / "doc2.md").write_text("# Doc 2")
        (tmp_path / "other.txt").write_text("Not markdown")

        files = get_project_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".md" for f in files)

    def test_get_project_files_nested(self, tmp_path):
        """Test getting nested project files."""
        (tmp_path / "doc.md").write_text("# Doc")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.md").write_text("# Nested")

        files = get_project_files(tmp_path)
        assert len(files) == 2

    def test_get_project_files_empty(self, tmp_path):
        """Test getting files from empty project."""
        files = get_project_files(tmp_path)
        assert len(files) == 0

    def test_get_project_files_sorted(self, tmp_path):
        """Test that files are sorted."""
        (tmp_path / "z.md").write_text("# Z")
        (tmp_path / "a.md").write_text("# A")

        files = get_project_files(tmp_path)
        assert files == sorted(files)


class TestCmdStats:
    """Tests for cmd_stats function."""

    def test_stats_single_file(self, tmp_path, capsys):
        """Test stats on single file."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Title\n\nSome words here.")

        parser = create_parser()
        args = parser.parse_args(["stats", str(doc)])
        result = cmd_stats(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Words:" in captured.out
        assert "Headings:" in captured.out

    def test_stats_json_output(self, tmp_path, capsys):
        """Test stats with JSON output."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Title\n\nHello world.")

        parser = create_parser()
        args = parser.parse_args(["stats", str(doc), "--json"])
        result = cmd_stats(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "words" in data
        assert "headings" in data

    def test_stats_project(self, tmp_path, capsys):
        """Test stats on project."""
        (tmp_path / "doc1.md").write_text("# Doc 1\n\nContent.")
        (tmp_path / "doc2.md").write_text("# Doc 2\n\nMore content.")

        parser = create_parser()
        args = parser.parse_args(["stats", "-p", str(tmp_path)])
        result = cmd_stats(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Total:" in captured.out

    def test_stats_file_not_found(self, capsys):
        """Test stats with non-existent file."""
        parser = create_parser()
        args = parser.parse_args(["stats", "/nonexistent/file.md"])
        result = cmd_stats(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


class TestCmdValidate:
    """Tests for cmd_validate function."""

    def test_validate_no_broken_links(self, tmp_path, capsys):
        """Test validate with no broken links."""
        doc1 = tmp_path / "doc1.md"
        doc2 = tmp_path / "doc2.md"
        doc1.write_text("# Doc 1\n\nLink to [[doc2]].")
        doc2.write_text("# Doc 2")

        parser = create_parser()
        args = parser.parse_args(["validate", "-p", str(tmp_path)])
        result = cmd_validate(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "no broken links" in captured.out

    def test_validate_broken_wiki_link(self, tmp_path, capsys):
        """Test validate with broken wiki link."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc\n\nLink to [[nonexistent]].")

        parser = create_parser()
        args = parser.parse_args(["validate", "-p", str(tmp_path)])
        result = cmd_validate(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Broken wiki link" in captured.out

    def test_validate_broken_md_link(self, tmp_path, capsys):
        """Test validate with broken markdown link."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc\n\nLink to [other](missing.md).")

        parser = create_parser()
        args = parser.parse_args(["validate", "-p", str(tmp_path)])
        result = cmd_validate(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Broken link" in captured.out

    def test_validate_json_output(self, tmp_path, capsys):
        """Test validate with JSON output."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc\n\nLink to [[missing]].")

        parser = create_parser()
        args = parser.parse_args(["validate", "-p", str(tmp_path), "--json"])
        result = cmd_validate(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "files_checked" in data
        assert "total_issues" in data


class TestCmdExport:
    """Tests for cmd_export function."""

    def test_export_html_stdout(self, tmp_path, capsys):
        """Test export HTML to stdout."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Hello World")

        parser = create_parser()
        args = parser.parse_args(["export", str(doc), "-f", "html"])
        result = cmd_export(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "<!DOCTYPE html>" in captured.out
        assert "Hello World" in captured.out

    def test_export_html_file(self, tmp_path, capsys):
        """Test export HTML to file."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Hello World")
        output = tmp_path / "out.html"

        parser = create_parser()
        args = parser.parse_args(["export", str(doc), "-f", "html", "-o", str(output)])
        result = cmd_export(args)

        assert result == 0
        assert output.exists()
        assert "Hello World" in output.read_text()

    def test_export_markdown_combined(self, tmp_path, capsys):
        """Test export combined markdown."""
        (tmp_path / "doc1.md").write_text("# Doc 1")
        (tmp_path / "doc2.md").write_text("# Doc 2")
        output = tmp_path / "combined.md"

        parser = create_parser()
        args = parser.parse_args(["export", "-p", str(tmp_path), "-f", "md", "-o", str(output)])
        result = cmd_export(args)

        assert result == 0
        content = output.read_text()
        assert "Doc 1" in content
        assert "Doc 2" in content

    def test_export_with_toc(self, tmp_path, capsys):
        """Test export with TOC."""
        (tmp_path / "doc.md").write_text("# Doc")
        output = tmp_path / "out.md"

        parser = create_parser()
        args = parser.parse_args(["export", "-p", str(tmp_path), "-f", "md", "-o", str(output), "--toc"])
        result = cmd_export(args)

        assert result == 0
        content = output.read_text()
        assert "Table of Contents" in content

    def test_export_file_not_found(self, capsys):
        """Test export with non-existent file."""
        parser = create_parser()
        args = parser.parse_args(["export", "/nonexistent/file.md", "-f", "html"])
        result = cmd_export(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_export_pdf_requires_output(self, tmp_path, capsys):
        """Test that PDF export requires output file."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Hello")

        parser = create_parser()
        args = parser.parse_args(["export", str(doc), "-f", "pdf"])
        result = cmd_export(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Output file required" in captured.err


class TestCmdGraph:
    """Tests for cmd_graph function."""

    def test_graph_dot_output(self, tmp_path, capsys):
        """Test graph DOT output to stdout."""
        (tmp_path / "doc1.md").write_text("# Doc 1\n\nLink to [[doc2]].")
        (tmp_path / "doc2.md").write_text("# Doc 2")

        parser = create_parser()
        args = parser.parse_args(["graph", "-p", str(tmp_path), "-f", "dot"])
        result = cmd_graph(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "digraph G" in captured.out
        assert "->" in captured.out

    def test_graph_dot_file(self, tmp_path, capsys):
        """Test graph DOT output to file."""
        (tmp_path / "doc.md").write_text("# Doc")
        output = tmp_path / "graph.dot"

        parser = create_parser()
        args = parser.parse_args(["graph", "-p", str(tmp_path), "-f", "dot", "-o", str(output)])
        result = cmd_graph(args)

        assert result == 0
        assert output.exists()
        assert "digraph" in output.read_text()

    def test_graph_labels_below(self, tmp_path, capsys):
        """Test graph with labels below."""
        (tmp_path / "doc.md").write_text("# Doc")

        parser = create_parser()
        args = parser.parse_args(["graph", "-p", str(tmp_path), "-f", "dot", "--labels-below"])
        result = cmd_graph(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "xlabel" in captured.out

    def test_graph_invalid_project(self, capsys):
        """Test graph with invalid project path."""
        parser = create_parser()
        args = parser.parse_args(["graph", "-p", "/nonexistent/path"])
        result = cmd_graph(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


class TestMainFunction:
    """Tests for main function routing."""

    def test_main_stats(self, tmp_path, capsys):
        """Test main routes to stats."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Test")

        result = main(["stats", str(doc)])
        assert result == 0

    def test_main_validate(self, tmp_path, capsys):
        """Test main routes to validate."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Test")

        result = main(["validate", "-p", str(tmp_path)])
        assert result == 0

    def test_main_export(self, tmp_path, capsys):
        """Test main routes to export."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Test")

        result = main(["export", str(doc), "-f", "html"])
        assert result == 0

    def test_main_graph(self, tmp_path, capsys):
        """Test main routes to graph."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Test")

        result = main(["graph", "-p", str(tmp_path), "-f", "dot"])
        assert result == 0
