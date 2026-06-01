"""``mde graph`` - export a visualization of the document link graph
for a project (SVG / PNG / PDF / raw DOT).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from markdown_editor.markdown6.cli.cli_helpers import get_project_files
from markdown_editor.markdown6.graph_exporter import (
    BrokenHandling,
    GraphExporter,
    GraphExporterConfig,
    OutputFormat,
)
from markdown_editor.markdown6.link_detection import (
    MD_LINK_PATTERN,
    WIKI_LINK_PATTERN,
    mask_verbatim_regions,
)


class CliGraphExporterConfig(GraphExporterConfig):
    """``GraphExporterConfig`` reading from an argparse ``Namespace``.

    The file list is built outside (so ``--no-orphans`` filtering can run
    before construction) and passed in explicitly.
    """

    def __init__(self, args: argparse.Namespace, files: list[Path]):
        self._args = args
        self._files = files

    @property
    def project_path(self) -> Path:
        return self._args.project

    @property
    def selected_files(self) -> list[Path]:
        return self._files

    @property
    def is_directed(self) -> bool:
        return not self._args.undirected

    @property
    def engine(self) -> str:
        return self._args.engine

    @property
    def label_template(self) -> str:
        return self._args.labels

    @property
    def labels_below(self) -> bool:
        return self._args.labels_below

    @property
    def broken_handling(self) -> BrokenHandling:
        return self._args.broken

    @property
    def dark_mode(self) -> bool:
        return self._args.dark

    @property
    def output_format(self) -> OutputFormat:
        return self._args.format


def cmd_graph(args: argparse.Namespace) -> int:
    """Handle graph subcommand."""
    if not args.project.is_dir():
        print(f"Error: Project path is not a directory: {args.project}", file=sys.stderr)
        return 1

    files = get_project_files(args.project)
    if not files:
        print(f"Error: No markdown files found in {args.project}", file=sys.stderr)
        return 1

    # Filter orphans pre-export, while we still have the raw file list.
    # The exporter's selected_files is what shows up as nodes; pruning here
    # is the simplest place to do it.
    if args.no_orphans:
        files = _filter_orphan_files(files)

    exporter = GraphExporter(CliGraphExporterConfig(args, files))

    # DOT format with no `--output` writes to stdout instead of a file.
    if args.format == "dot" and not args.output:
        print(exporter.generate_dot())
        return 0

    if not args.output:
        print(f"Error: Output file required for {args.format} format", file=sys.stderr)
        return 1

    try:
        exporter.export(args.output)
    except ImportError:
        print(
            "Error: graphviz package required for image export. "
            "Install with: pip install graphviz",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(f"Error rendering graph: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Exported graph to {args.output}")
    return 0


def _filter_orphan_files(files: list[Path]) -> list[Path]:
    """Keep only files that participate in at least one link.

    Mirrors the previous ``--no-orphans`` semantics: a file stays if it
    links to another, OR if another file links to it. Uses the same
    pattern-based scan the exporter does (but skips path resolution to
    keep this purely textual / cheap).
    """
    # Build a set of {linked-to-stem-or-relpath} across all files.
    targets: set[str] = set()
    for f in files:
        content = mask_verbatim_regions(f.read_text(encoding="utf-8"))
        for match in WIKI_LINK_PATTERN.findall(content):
            targets.add(match.lower())
        for match in MD_LINK_PATTERN.finditer(content):
            targets.add(Path(match.group(2)).stem.lower())

    # Keep a file if it has any outbound link, or if any other file
    # references its stem.
    kept = []
    for f in files:
        content = mask_verbatim_regions(f.read_text(encoding="utf-8"))
        has_outbound = bool(
            WIKI_LINK_PATTERN.findall(content) or MD_LINK_PATTERN.findall(content)
        )
        has_inbound = f.stem.lower() in targets
        if has_outbound or has_inbound:
            kept.append(f)
    return kept
