"""Command-line interface for the Markdown editor.

Usage:
    mde                              # Open editor
    mde document.md                  # Open file(s)
    mde -p ./project                 # Open project folder
    mde export doc.md -o out.pdf     # Export to PDF
    mde graph -p ./project -o g.svg  # Export document graph
    mde stats doc.md                 # Print file statistics
    mde validate -p ./project        # Check for broken links
"""

import argparse
import errno
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from markdown_editor.markdown6.cli.cli_helpers import (
    get_project_files,
    read_stdin,
)
from markdown_editor.markdown6.cli.desktop_integration import (
    cmd_install_desktop,
    cmd_uninstall_desktop,
)
from markdown_editor.markdown6.cli.shell_completion import (
    cmd_install_autocomplete,
    cmd_uninstall_autocomplete,
)
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
from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


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


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="mde",
        description="A feature-rich Markdown editor with live preview.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mde                           Open editor with new document
  mde doc.md                    Open file in editor
  mde -p ./notes                Open project folder
  mde export doc.md -o out.pdf  Export to PDF
  mde stats doc.md              Show word count and stats
  mde validate -p ./project     Check for broken links
        """,
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="Use alternate config directory",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        metavar="LEVEL",
        help="Log verbosity (debug/info/warning/error). Also reads "
             "MDE_LOG_LEVEL env var. Default: info.",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )

    # GUI mode args (top-level, no subcommand)
    parser.add_argument(
        "-p", "--project",
        type=Path,
        metavar="PATH",
        help="Open project folder",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="Open with a new untitled document",
    )
    parser.add_argument(
        "--line",
        type=int,
        metavar="N",
        help="Jump to line N after opening",
    )
    parser.add_argument(
        "--theme",
        choices=["light", "dark"],
        help="Override theme",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Open in read-only mode",
    )
    parser.add_argument(
        "--zen-mode",
        action="store_true",
        help="Start in Zen mode (hide menu, sidebar, tab bar, and status bar)",
    )
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Use default settings in memory only (don't load or save user settings)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all config files and start with clean default settings",
    )
    parser.add_argument(
        "--plugins-dir",
        action="append",
        type=Path,
        metavar="PATH",
        default=[],
        help="Additional plugin directory to scan (repeatable). "
             "Stacks on top of the built-in and user plugin dirs; does "
             "not replace them.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # Export subcommand
    export_parser = subparsers.add_parser(
        "export",
        help="Export markdown to other formats",
        description="Export markdown files to PDF, HTML, DOCX, or Markdown.",
    )
    export_parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Files to export (or use stdin)",
    )
    export_parser.add_argument(
        "-p", "--project",
        type=Path,
        metavar="PATH",
        help="Export entire project",
    )
    export_parser.add_argument(
        "-o", "--output",
        type=Path,
        metavar="PATH",
        help="Output file (stdout if not specified for HTML/Markdown)",
    )
    export_parser.add_argument(
        "-f", "--format",
        choices=["pdf", "html", "docx", "markdown", "md"],
        default="pdf",
        help="Output format (default: pdf)",
    )
    export_parser.add_argument(
        "--toc",
        action="store_true",
        help="Include table of contents",
    )
    export_parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insert page breaks between files",
    )
    export_parser.add_argument(
        "--title",
        help="Document title (default: filename or 'Document')",
    )
    export_parser.add_argument(
        "--use-pandoc",
        action="store_true",
        help="Use pandoc for export (if available)",
    )
    export_parser.add_argument(
        "--theme",
        choices=["light", "dark"],
        default="light",
        help="Theme for HTML/PDF output (default: light). See "
             "local/html-export-unify.md decision C2.",
    )
    export_parser.add_argument(
        "--canonical-fonts",
        action="store_true",
        help="Ignore the user's preview font/size settings and use "
             "built-in canonical defaults in the exported HTML/PDF "
             "(gives a consistent look across readers). See "
             "local/html-export-unify.md decision G.",
    )

    # Graph subcommand
    graph_parser = subparsers.add_parser(
        "graph",
        help="Export document link graph",
        description="Generate a graph visualization of document links.",
    )
    graph_parser.add_argument(
        "-p", "--project",
        type=Path,
        metavar="PATH",
        required=True,
        help="Project folder to analyze",
    )
    graph_parser.add_argument(
        "-o", "--output",
        type=Path,
        metavar="PATH",
        help="Output file (stdout for DOT format if not specified)",
    )
    graph_parser.add_argument(
        "-f", "--format",
        choices=["svg", "png", "pdf", "dot"],
        default="svg",
        help="Output format (default: svg)",
    )
    graph_parser.add_argument(
        "--engine",
        choices=["dot", "neato", "fdp", "sfdp", "circo", "twopi"],
        default="dot",
        help="Graphviz layout engine (default: dot)",
    )
    graph_parser.add_argument(
        "--labels-below",
        action="store_true",
        help="Place labels below nodes (uses node-as-point style)",
    )
    graph_parser.add_argument(
        "--labels",
        default="{stem}",
        metavar="TEMPLATE",
        help=(
            "Node-label template. Available fields: {stem}, {filename}, "
            "{relative_path}, {relative_path_no_ext}. "
            "Default: {stem}"
        ),
    )
    graph_parser.add_argument(
        "--undirected",
        action="store_true",
        help="Produce an undirected graph (default: directed)",
    )
    graph_parser.add_argument(
        "--broken",
        choices=["red", "exclude", "warning", "normal"],
        default="red",
        help=(
            "How to render links to non-existent files: "
            "red (dashed-red node + edge), exclude (omit entirely), "
            "warning (orange node with '(missing)' suffix), "
            "normal (regular node + edge). Default: red"
        ),
    )
    graph_parser.add_argument(
        "--dark",
        action="store_true",
        help="Apply dark-mode styling to the rendered SVG",
    )
    graph_parser.add_argument(
        "--no-orphans",
        action="store_true",
        help="Exclude files with no links",
    )

    # Stats subcommand
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show file statistics",
        description="Display word count, character count, headings, and links.",
    )
    stats_parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Files to analyze (or use stdin)",
    )
    stats_parser.add_argument(
        "-p", "--project",
        type=Path,
        metavar="PATH",
        help="Analyze entire project",
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # Validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate links in documents",
        description="Check for broken wiki-links and markdown links.",
    )
    validate_parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Files to validate",
    )
    validate_parser.add_argument(
        "-p", "--project",
        type=Path,
        metavar="PATH",
        help="Validate entire project",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # Desktop integration
    subparsers.add_parser(
        "install-desktop",
        help="Install desktop shortcuts and icons",
        description="Install desktop integration (Start Menu shortcut on Windows, "
        ".app bundle on macOS, .desktop entry on Linux).",
    )
    subparsers.add_parser(
        "uninstall-desktop",
        help="Remove desktop shortcuts and icons",
        description="Remove previously installed desktop integration.",
    )

    # Shell completion
    subparsers.add_parser(
        "install-autocomplete",
        help="Install shell tab-completion for mde",
        description="Register argcomplete tab-completion for mde and markdown-editor.",
    )
    subparsers.add_parser(
        "uninstall-autocomplete",
        help="Remove shell tab-completion for mde",
        description="Remove argcomplete tab-completion for mde and markdown-editor.",
    )

    return parser


def cmd_export(args: argparse.Namespace) -> int:
    """Handle export subcommand."""
    from markdown_editor.markdown6 import export_service
    from markdown_editor.markdown6.app_context import init_app_context

    # Build an ephemeral AppContext so the export path has somewhere to
    # read theme / canonical-fonts from. `ephemeral=True` means nothing
    # is loaded from or saved to the user's config files. The CLI
    # applies --theme and --canonical-fonts to this ctx before calling
    # into export_service. See local/html-export-unify.md decisions
    # A1.a, C2, G.
    cli_ctx = init_app_context(ephemeral=True)
    cli_ctx.set("view.theme", args.theme)
    if args.canonical_fonts:
        cli_ctx.set("export.use_canonical_fonts", True)

    # Determine input content
    content_parts = []
    title = args.title or "Document"
    # Source markdown path — used by the renderer to resolve relative
    # `.dot` image references. Set only for single-file exports; None
    # for project/multi-file/stdin (inherently ambiguous).
    source_path: Path | None = None

    if args.project:
        if not args.project.is_dir():
            print(f"Error: Project path is not a directory: {args.project}", file=sys.stderr)
            return 1
        files = get_project_files(args.project)
        if not files:
            print(f"Error: No markdown files found in {args.project}", file=sys.stderr)
            return 1
        title = args.title or args.project.name

        documents = [(f, f.read_text(encoding="utf-8")) for f in files]
        combined = export_service.combine_project_markdown(
            documents,
            include_toc=args.toc,
            page_breaks=args.page_breaks,
            output_format=("html" if args.format == "html" else "markdown"),
        )
        content_parts.append(combined)

    elif args.files:
        for f in args.files:
            if not f.exists():
                print(f"Error: File not found: {f}", file=sys.stderr)
                return 1
        if len(args.files) == 1:
            title = args.title or args.files[0].stem
            source_path = args.files[0]
            content_parts.append(args.files[0].read_text(encoding="utf-8"))
        else:
            # Multi-file: combine via the shared helper so relative `.dot`
            # image refs get absolutized per-file (fixing resolution across
            # files from different source dirs) and the combining logic
            # stays DRY with project export.
            documents = [(f, f.read_text(encoding="utf-8")) for f in args.files]
            combined = export_service.combine_project_markdown(
                documents,
                include_toc=False,
                page_breaks=False,
                output_format=("html" if args.format == "html" else "markdown"),
            )
            content_parts.append(combined)

    else:
        # Read from stdin
        stdin_content = read_stdin()
        if not stdin_content:
            print("Error: No input files specified and nothing on stdin", file=sys.stderr)
            return 1
        content_parts.append(stdin_content)

    content = "\n".join(content_parts)
    fmt = args.format if args.format != "md" else "markdown"

    # Determine output
    output_path = args.output
    if not output_path:
        if fmt in ("html", "markdown"):
            # Output to stdout
            if fmt == "html":
                print(export_service.markdown_to_html(
                    content, title, ctx=cli_ctx, source_path=source_path,
                ))
            else:
                print(content)
            return 0
        else:
            # Need output file for binary formats
            print(f"Error: Output file required for {fmt} format", file=sys.stderr)
            return 1

    # Export to file
    try:
        if fmt == "html":
            export_service.export_html(
                content, output_path, title,
                ctx=cli_ctx, source_path=source_path,
            )
        elif fmt == "pdf":
            export_service.export_pdf(content, output_path, title, use_pandoc=args.use_pandoc)
        elif fmt == "docx":
            export_service.export_docx(content, output_path, title, use_pandoc=args.use_pandoc)
        elif fmt == "markdown":
            output_path.write_text(content, encoding="utf-8")

        if not args.quiet:
            print(f"Exported to {output_path}")
        return 0

    except export_service.ExportError as e:
        print(f"Export error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


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


def cmd_stats(args: argparse.Namespace) -> int:
    """Handle stats subcommand."""
    # WIKI_LINK_PATTERN comes from the shared module. cmd_stats uses its own
    # broader markdown-link pattern (no `.md` extension restriction) because
    # it's counting *all* inline links, not just inter-document ones.
    STATS_MD_LINK_PATTERN = re.compile(r'\[([^\]\n]*)\]\(([^)\s]+)\)')
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)(?:\s*#*\s*)?$', re.MULTILINE)

    def analyze_content(content: str, filename: str = "stdin") -> dict:
        """Analyze markdown content and return stats."""
        # `lines`, `words`, `chars` reflect the raw input; mask only for the
        # link-detection step so verbatim `[[..]]` / `[..](..)` don't get
        # counted as links.
        lines = content.split('\n')
        words = len(content.split())
        chars = len(content)
        chars_no_spaces = len(content.replace(' ', '').replace('\n', ''))

        headings = []
        for match in HEADING_PATTERN.finditer(content):
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append({"level": level, "text": text})

        masked = mask_verbatim_regions(content)
        wiki_links = WIKI_LINK_PATTERN.findall(masked)
        md_links = [(text, url) for text, url in STATS_MD_LINK_PATTERN.findall(masked)]

        return {
            "file": filename,
            "lines": len(lines),
            "words": words,
            "characters": chars,
            "characters_no_spaces": chars_no_spaces,
            "headings": headings,
            "heading_count": len(headings),
            "wiki_links": wiki_links,
            "wiki_link_count": len(wiki_links),
            "markdown_links": [{"text": t, "url": u} for t, u in md_links],
            "markdown_link_count": len(md_links),
        }

    def print_stats(stats: dict, verbose: bool = False):
        """Print stats in human-readable format."""
        print(f"File: {stats['file']}")
        print(f"  Lines:      {stats['lines']:,}")
        print(f"  Words:      {stats['words']:,}")
        print(f"  Characters: {stats['characters']:,} ({stats['characters_no_spaces']:,} without spaces)")
        print(f"  Headings:   {stats['heading_count']}")
        print(f"  Wiki links: {stats['wiki_link_count']}")
        print(f"  MD links:   {stats['markdown_link_count']}")

        if verbose and stats['headings']:
            print("  Outline:")
            for h in stats['headings']:
                indent = "    " + "  " * (h['level'] - 1)
                print(f"{indent}{'#' * h['level']} {h['text']}")

    results = []

    if args.project:
        if not args.project.is_dir():
            print(f"Error: Project path is not a directory: {args.project}", file=sys.stderr)
            return 1
        files = get_project_files(args.project)
        if not files:
            print(f"Error: No markdown files found in {args.project}", file=sys.stderr)
            return 1

        for f in files:
            content = f.read_text(encoding="utf-8")
            stats = analyze_content(content, str(f.relative_to(args.project)))
            results.append(stats)

    elif args.files:
        for f in args.files:
            if not f.exists():
                print(f"Error: File not found: {f}", file=sys.stderr)
                return 1
            content = f.read_text(encoding="utf-8")
            stats = analyze_content(content, str(f))
            results.append(stats)

    else:
        stdin_content = read_stdin()
        if not stdin_content:
            print("Error: No input files specified and nothing on stdin", file=sys.stderr)
            return 1
        stats = analyze_content(stdin_content, "stdin")
        results.append(stats)

    # Output
    if args.json:
        if len(results) == 1:
            print(json.dumps(results[0], indent=2))
        else:
            # Add totals for project
            totals = {
                "total_files": len(results),
                "total_lines": sum(r["lines"] for r in results),
                "total_words": sum(r["words"] for r in results),
                "total_characters": sum(r["characters"] for r in results),
                "total_headings": sum(r["heading_count"] for r in results),
                "total_wiki_links": sum(r["wiki_link_count"] for r in results),
                "total_markdown_links": sum(r["markdown_link_count"] for r in results),
            }
            print(json.dumps({"files": results, "totals": totals}, indent=2))
    else:
        for stats in results:
            print_stats(stats, verbose=args.verbose if hasattr(args, 'verbose') else False)
            print()

        if len(results) > 1:
            print("=" * 40)
            print(f"Total: {len(results)} files")
            print(f"  Lines:      {sum(r['lines'] for r in results):,}")
            print(f"  Words:      {sum(r['words'] for r in results):,}")
            print(f"  Characters: {sum(r['characters'] for r in results):,}")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Handle validate subcommand."""
    # Get files to validate
    if args.project:
        if not args.project.is_dir():
            print(f"Error: Project path is not a directory: {args.project}", file=sys.stderr)
            return 1
        files = get_project_files(args.project)
        base_path = args.project
    elif args.files:
        files = []
        for f in args.files:
            if not f.exists():
                print(f"Error: File not found: {f}", file=sys.stderr)
                return 1
            files.append(f)
        base_path = files[0].parent if files else Path(".")
    else:
        print("Error: No files or project specified", file=sys.stderr)
        return 1

    if not files:
        print("Error: No markdown files found", file=sys.stderr)
        return 1

    # Build file index
    file_index = {f.stem.lower(): f for f in files}

    # Validate links
    issues: list[dict[str, Any]] = []
    for f in files:
        # Mask code spans / fences / math / HTML so verbatim `[[..]]` / `[..](..)`
        # aren't flagged as broken links.
        content = mask_verbatim_regions(f.read_text(encoding="utf-8"))
        file_issues: list[dict[str, Any]] = []

        # Check wiki links
        for match in WIKI_LINK_PATTERN.finditer(content):
            target = match.group(1).lower()
            if target not in file_index:
                # Find line number
                line_num = content[:match.start()].count('\n') + 1
                file_issues.append({
                    "line": line_num,
                    "type": "wiki_link",
                    "target": match.group(1),
                    "message": f"Broken wiki link: [[{match.group(1)}]]",
                })

        # Check markdown links
        for match in MD_LINK_PATTERN.finditer(content):
            target = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            # A pathologically long target (e.g. a bare-prose multi-line link
            # the masker can't strip) can make resolve()/exists() raise
            # OSError(ENAMETOOLONG). Skip rather than crash the whole run.
            try:
                target_path = (f.parent / target).resolve()
                exists = target_path.exists()
            except OSError as e:
                if e.errno == errno.ENAMETOOLONG:
                    logger.warning(
                        "Skipping markdown link at %s:%d: target too long (%d chars)",
                        f, line_num, len(target),
                    )
                    continue
                raise
            if not exists:
                file_issues.append({
                    "line": line_num,
                    "type": "markdown_link",
                    "target": target,
                    "message": f"Broken link: {target}",
                })

        if file_issues:
            rel_path = str(f.relative_to(base_path)) if args.project else str(f)
            issues.append({
                "file": rel_path,
                "issues": file_issues,
            })

    # Output
    if args.json:
        result = {
            "files_checked": len(files),
            "files_with_issues": len(issues),
            "total_issues": sum(len(f["issues"]) for f in issues),
            "issues": issues,
        }
        print(json.dumps(result, indent=2))
    else:
        if not issues:
            print(f"✓ All {len(files)} files validated, no broken links found.")
            return 0

        for file_entry in issues:
            print(f"\n{file_entry['file']}:")
            for issue in file_entry["issues"]:
                print(f"  Line {issue['line']}: {issue['message']}")

        total = sum(len(f["issues"]) for f in issues)
        print(f"\n✗ Found {total} broken link(s) in {len(issues)} file(s)")

    return 1 if issues else 0


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the GUI editor."""
    from markdown_editor.markdown6.app_context import init_app_context

    # Initialize settings before importing editor
    # --reset: delete all config files and start clean
    # --new-session: use ephemeral settings (defaults only, no save)
    # --config: use custom config directory
    if args.reset:
        from markdown_editor.markdown6.app_context import _default_config_dir
        config_dir = args.config or _default_config_dir()
        if config_dir.exists():
            shutil.rmtree(config_dir)
            print(f"Reset: deleted {config_dir}", file=sys.stderr)
        init_app_context(ephemeral=True)
    elif args.new_session:
        init_app_context(ephemeral=True)
    elif args.config:
        init_app_context(config_dir=args.config)

    # Import Qt and editor
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.logger import resolve_level, set_level
    from markdown_editor.markdown6.markdown_editor import (
        MarkdownEditor,
        apply_application_theme,
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    # Apply saved theme at startup (before creating editor)
    ctx = get_app_context()

    # Re-resolve the log level now that settings are loaded. The early
    # main() call only saw CLI + env; this re-apply adds the persisted
    # ``log.level`` setting to the precedence chain. Idempotent if no
    # setting was persisted - resolve_level returns the same value.
    set_level(resolve_level(
        getattr(args, "log_level", None),
        settings_value=ctx.get("log.level"),
    ))

    theme = args.theme if args.theme else ctx.get("view.theme", "light")
    apply_application_theme(theme == "dark")

    # Create editor
    editor = MarkdownEditor(extra_plugin_dirs=args.plugins_dir or None)

    # Apply theme override (also update settings if specified)
    if args.theme:
        editor.ctx.set("view.theme", args.theme)

    # Open project
    if args.project:
        if args.project.is_dir():
            editor.project_panel.set_project_path(args.project)
        else:
            print(f"Warning: Project path is not a directory: {args.project}", file=sys.stderr)

    # Open files
    if args.files and not args.new:
        for f in args.files:
            if f.exists():
                editor.open_file(f)
                # Jump to line if specified
                if args.line:
                    tab = editor.current_tab()
                    if tab:
                        tab.editor.go_to_line(args.line)
            else:
                print(f"Warning: File not found: {f}", file=sys.stderr)
    elif args.new:
        # Ensure at least one new tab
        if editor.tab_widget.count() == 0:
            editor.new_tab()
    else:
        # No explicit files — restore previous session if project matches
        last_path = ctx.get("project.last_path")
        project_path = str(args.project.resolve()) if args.project and args.project.is_dir() else None
        if last_path and (project_path is None or project_path == last_path):
            editor.restore_open_files()

    # Read-only mode: app-wide write lock (not just the active tab).
    # See markdown_editor.MarkdownEditor.set_read_only_mode.
    if args.read_only:
        editor.set_read_only_mode(True)

    # Zen mode (apply before show() so the user never sees a flash of
    # the full chrome).
    if args.zen_mode:
        editor._toggle_zen_mode()

    editor.show()
    ret = app.exec()
    del editor
    return ret


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    from markdown_editor.markdown6.logger import (
        capture_external_stderr,
        resolve_level,
    )
    from markdown_editor.markdown6.logger import setup as setup_logging

    # Redirect native stderr (Chromium / NSS / Qt) through our logger
    # BEFORE setup_logging so our StreamHandler inherits the saved
    # stderr fd instead of the capture pipe.
    capture_external_stderr()

    if argv is None:
        argv = sys.argv[1:]

    parser = create_parser()

    # Best-effort early parse to pick up --log-level before we set up
    # logging. parse_known_args won't fail on positional file paths or
    # unknown flags. If parsing fails entirely (unlikely), fall back to
    # env-var-or-default via resolve_level(None).
    cli_log_level = None
    try:
        early_args, _ = parser.parse_known_args(argv)
        cli_log_level = getattr(early_args, "log_level", None)
    except SystemExit:
        pass
    setup_logging(level=resolve_level(cli_log_level))

    # Enable argcomplete — this is a no-op unless the shell has activated it
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    subcommands = {
        "export", "graph", "stats", "validate",
        "install-desktop", "uninstall-desktop",
        "install-autocomplete", "uninstall-autocomplete",
    }

    # Determine whether the first positional argument is a subcommand.
    # If not, positional args are file paths for GUI mode and must be
    # kept away from the subparser (which rejects unknown choices).
    flags_with_value = {"-p", "--project", "--config", "--line", "--theme"}
    first_positional = None
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == "--":
            break
        if arg.startswith("-"):
            if arg in flags_with_value:
                skip = True
            continue
        first_positional = arg
        break

    if first_positional in subcommands:
        # Subcommand mode — full parse
        args = parser.parse_args(argv)
        if args.command == "export":
            return cmd_export(args)
        elif args.command == "graph":
            return cmd_graph(args)
        elif args.command == "stats":
            return cmd_stats(args)
        elif args.command == "validate":
            return cmd_validate(args)
        elif args.command == "install-desktop":
            return cmd_install_desktop(args)
        elif args.command == "uninstall-desktop":
            return cmd_uninstall_desktop(args)
        elif args.command == "install-autocomplete":
            return cmd_install_autocomplete(args)
        elif args.command == "uninstall-autocomplete":
            return cmd_uninstall_autocomplete(args)

    # GUI mode — separate file paths from flags so argparse
    # doesn't choke on them as invalid subcommands.
    flag_argv = []
    file_args = []
    skip = False
    after_dashdash = False
    for arg in argv:
        if after_dashdash:
            file_args.append(arg)
            continue
        if skip:
            flag_argv.append(arg)
            skip = False
            continue
        if arg == "--":
            after_dashdash = True
            continue
        if arg.startswith("-"):
            flag_argv.append(arg)
            if arg in flags_with_value:
                skip = True
            continue
        file_args.append(arg)

    args, extra = parser.parse_known_args(flag_argv)
    file_args.extend(extra)
    args.files = [Path(f) for f in file_args]
    return cmd_gui(args)


if __name__ == "__main__":
    sys.exit(main())
