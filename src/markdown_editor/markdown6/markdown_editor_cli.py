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
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


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
        "--new-session",
        action="store_true",
        help="Use default settings in memory only (don't load or save user settings)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all config files and start with clean default settings",
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
        help="Place labels below nodes",
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


def read_stdin() -> str:
    """Read content from stdin if available."""
    try:
        if not sys.stdin.isatty():
            return sys.stdin.read()
    except OSError:
        # Handle pytest capture mode
        pass
    return ""


def get_project_files(project_path: Path) -> list[Path]:
    """Get all markdown files in a project."""
    from markdown_editor.markdown6.app_context import \
        get_project_markdown_files
    return get_project_markdown_files(project_path)


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
    import re

    if not args.project.is_dir():
        print(f"Error: Project path is not a directory: {args.project}", file=sys.stderr)
        return 1

    files = get_project_files(args.project)
    if not files:
        print(f"Error: No markdown files found in {args.project}", file=sys.stderr)
        return 1

    # Patterns for link detection
    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    MD_LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+\.(?:md|mdown))\)', re.IGNORECASE)

    # Build file index (stem -> path)
    file_index = {f.stem.lower(): f for f in files}

    # Parse links
    nodes = {}  # path -> set of linked paths
    for f in files:
        content = f.read_text(encoding="utf-8")
        links = set()

        # Wiki links
        for match in WIKI_LINK_PATTERN.findall(content):
            target = match.lower()
            if target in file_index:
                links.add(file_index[target])

        # Markdown links
        for _, target in MD_LINK_PATTERN.findall(content):
            target_path = (f.parent / target).resolve()
            if target_path.exists():
                links.add(target_path)

        nodes[f] = links

    # Filter orphans if requested
    if args.no_orphans:
        linked_files = set()
        for f, links in nodes.items():
            if links:
                linked_files.add(f)
                linked_files.update(links)
        nodes = {f: links for f, links in nodes.items() if f in linked_files}

    # Generate DOT source
    is_directed = True
    graph_type = "digraph"
    edge_op = "->"

    lines = [f'{graph_type} G {{']
    lines.append(f'    layout={args.engine};')
    lines.append('    bgcolor="transparent";')

    if args.labels_below:
        lines.append('    forcelabels=true;')
        lines.append('    node [shape=point, width=0.15, height=0.15];')
        lines.append('    graph [fontsize=10];')
        if args.engine == "dot":
            lines.append('    nodesep=0.8;')
            lines.append('    ranksep=1.0;')
        else:
            lines.append('    overlap=prism;')
            lines.append('    sep="+20,20";')
    else:
        lines.append('    node [shape=box, style=rounded];')

    # Create node IDs
    node_ids = {f: f"n{i}" for i, f in enumerate(nodes.keys())}

    # Add nodes
    for f, node_id in node_ids.items():
        label = f.stem
        rel_path = f.relative_to(args.project)
        if args.labels_below:
            lines.append(f'    {node_id} [xlabel="{label}"];')
        else:
            lines.append(f'    {node_id} [label="{label}"];')

    # Add edges
    for f, links in nodes.items():
        src_id = node_ids[f]
        for link in links:
            if link in node_ids:
                dst_id = node_ids[link]
                lines.append(f'    {src_id} {edge_op} {dst_id};')

    lines.append('}')
    dot_source = '\n'.join(lines)

    # Output
    if args.format == "dot":
        if args.output:
            args.output.write_text(dot_source, encoding="utf-8")
            if not args.quiet:
                print(f"Exported DOT to {args.output}")
        else:
            print(dot_source)
        return 0

    # Render with graphviz
    try:
        import graphviz
    except ImportError:
        print("Error: graphviz package required for image export. Install with: pip install graphviz", file=sys.stderr)
        return 1

    if not args.output:
        print(f"Error: Output file required for {args.format} format", file=sys.stderr)
        return 1

    try:
        g = graphviz.Source(dot_source, format=args.format, engine=args.engine)
        output_path = str(args.output)
        if output_path.endswith(f".{args.format}"):
            output_path = output_path[:-len(f".{args.format}")-1]
        g.render(output_path, cleanup=True)
        if not args.quiet:
            print(f"Exported graph to {args.output}")
        return 0
    except Exception as e:
        print(f"Error rendering graph: {e}", file=sys.stderr)
        return 1


def cmd_stats(args: argparse.Namespace) -> int:
    """Handle stats subcommand."""
    import re

    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    MD_LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)(?:\s*#*\s*)?$', re.MULTILINE)

    def analyze_content(content: str, filename: str = "stdin") -> dict:
        """Analyze markdown content and return stats."""
        lines = content.split('\n')
        words = len(content.split())
        chars = len(content)
        chars_no_spaces = len(content.replace(' ', '').replace('\n', ''))

        headings = []
        for match in HEADING_PATTERN.finditer(content):
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append({"level": level, "text": text})

        wiki_links = WIKI_LINK_PATTERN.findall(content)
        md_links = [(text, url) for text, url in MD_LINK_PATTERN.findall(content)]

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
    import re

    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    MD_LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+\.(?:md|mdown))\)', re.IGNORECASE)

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
        print(f"Error: No markdown files found", file=sys.stderr)
        return 1

    # Build file index
    file_index = {f.stem.lower(): f for f in files}

    # Validate links
    issues = []
    for f in files:
        content = f.read_text(encoding="utf-8")
        file_issues = []

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
            target_path = (f.parent / target).resolve()
            if not target_path.exists():
                line_num = content[:match.start()].count('\n') + 1
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

        for file_issues in issues:
            print(f"\n{file_issues['file']}:")
            for issue in file_issues["issues"]:
                print(f"  Line {issue['line']}: {issue['message']}")

        total = sum(len(f["issues"]) for f in issues)
        print(f"\n✗ Found {total} broken link(s) in {len(issues)} file(s)")

    return 1 if issues else 0


def _icons_dir() -> Path:
    """Return the path to the bundled icons directory."""
    return Path(__file__).parent / "icons"


_ICON_SIZES = [48, 64, 128, 256]


def _data_home() -> Path:
    """Return the user's data directory via QStandardPaths."""
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    ))


def cmd_install_desktop(args: argparse.Namespace) -> int:
    """Install desktop integration for the current platform."""
    if sys.platform == "linux":
        return _install_desktop_linux()
    elif sys.platform == "win32":
        return _install_desktop_windows()
    elif sys.platform == "darwin":
        return _install_desktop_macos()
    else:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        return 1


def cmd_uninstall_desktop(args: argparse.Namespace) -> int:
    """Remove desktop integration for the current platform."""
    if sys.platform == "linux":
        return _uninstall_desktop_linux()
    elif sys.platform == "win32":
        return _uninstall_desktop_windows()
    elif sys.platform == "darwin":
        return _uninstall_desktop_macos()
    else:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        return 1


# -- Linux desktop integration ------------------------------------------------

def _install_desktop_linux() -> int:
    """Install freedesktop.org .desktop entry and icons."""
    icons_dir = _icons_dir()
    data_home = _data_home()

    # Install .desktop file
    apps_dir = data_home / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    src_desktop = icons_dir / "markdown-editor.desktop"
    dst_desktop = apps_dir / "markdown-editor.desktop"
    shutil.copy2(src_desktop, dst_desktop)
    print(f"Installed {dst_desktop}")

    # Install icons
    for size in _ICON_SIZES:
        icon_dir = data_home / "icons" / "hicolor" / f"{size}x{size}" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        src_icon = icons_dir / f"markdown-editor-{size}.png"
        dst_icon = icon_dir / "markdown-editor.png"
        shutil.copy2(src_icon, dst_icon)
        print(f"Installed {dst_icon}")

    # Update icon cache if possible
    hicolor = data_home / "icons" / "hicolor"
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-f", str(hicolor)],
                       capture_output=True)

    # Update desktop database if possible
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps_dir)],
                       capture_output=True)

    print("Done. You may need to log out and back in for changes to take effect.")
    return 0


def _uninstall_desktop_linux() -> int:
    """Remove .desktop file and icons."""
    data_home = _data_home()
    removed = []

    desktop = data_home / "applications" / "markdown-editor.desktop"
    if desktop.exists():
        desktop.unlink()
        removed.append(str(desktop))

    for size in _ICON_SIZES:
        icon = data_home / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "markdown-editor.png"
        if icon.exists():
            icon.unlink()
            removed.append(str(icon))

    if removed:
        for path in removed:
            print(f"Removed {path}")

        # Update caches
        hicolor = data_home / "icons" / "hicolor"
        if shutil.which("gtk-update-icon-cache"):
            subprocess.run(["gtk-update-icon-cache", "-f", str(hicolor)],
                           capture_output=True)
        apps_dir = data_home / "applications"
        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", str(apps_dir)],
                           capture_output=True)
        print("Done.")
    else:
        print("Nothing to remove.")

    return 0


# -- Windows desktop integration ----------------------------------------------

def _windows_start_menu_dir() -> Path:
    """Return the user's Start Menu Programs directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _mde_executable() -> str:
    """Return the path to the mde entry-point script/exe."""
    # pip installs entry points into Scripts/ on Windows, bin/ on Unix
    scripts_dir = Path(sys.executable).parent
    if sys.platform == "win32":
        exe = scripts_dir / "Scripts" / "mde.exe"
        if exe.exists():
            return str(exe)
        exe = scripts_dir / "mde.exe"
        if exe.exists():
            return str(exe)
    return str(shutil.which("mde") or "mde")


def _create_windows_shortcut(link_path: Path, target: str, icon_path: str,
                             description: str) -> None:
    """Create a Windows .lnk shortcut using PowerShell."""
    # PowerShell COM approach — no extra dependencies
    ps_script = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{link_path}"); '
        f'$s.TargetPath = "{target}"; '
        f'$s.IconLocation = "{icon_path}"; '
        f'$s.Description = "{description}"; '
        f'$s.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, check=True,
    )


def _install_desktop_windows() -> int:
    """Install Start Menu shortcut on Windows."""
    icons_dir = _icons_dir()
    ico_path = icons_dir / "markdown-mark-solid-win10.ico"
    mde_exe = _mde_executable()

    # Create Start Menu shortcut
    start_menu = _windows_start_menu_dir()
    start_menu.mkdir(parents=True, exist_ok=True)
    lnk_path = start_menu / "Markdown Editor.lnk"
    _create_windows_shortcut(lnk_path, mde_exe, str(ico_path),
                             "Markdown Editor with live preview")
    print(f"Installed {lnk_path}")

    print("Done.")
    return 0


def _uninstall_desktop_windows() -> int:
    """Remove Start Menu shortcut on Windows."""
    removed = []

    lnk = _windows_start_menu_dir() / "Markdown Editor.lnk"
    if lnk.exists():
        lnk.unlink()
        removed.append(str(lnk))

    if removed:
        for path in removed:
            print(f"Removed {path}")
        print("Done.")
    else:
        print("Nothing to remove.")

    return 0


# -- macOS desktop integration ------------------------------------------------

_MACOS_APP_DIR = Path.home() / "Applications"
_MACOS_APP_NAME = "Markdown Editor.app"

_MACOS_INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Markdown Editor</string>
    <key>CFBundleDisplayName</key>
    <string>Markdown Editor</string>
    <key>CFBundleIdentifier</key>
    <string>com.markdown-editor.mde</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>mde-launcher</string>
    <key>CFBundleIconFile</key>
    <string>app.icns</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>md</string>
                <string>markdown</string>
                <string>mkd</string>
                <string>mdown</string>
            </array>
            <key>CFBundleTypeName</key>
            <string>Markdown Document</string>
            <key>CFBundleTypeRole</key>
            <string>Editor</string>
        </dict>
    </array>
</dict>
</plist>
"""


def _install_desktop_macos() -> int:
    """Install .app bundle in ~/Applications."""
    app_dir = _MACOS_APP_DIR / _MACOS_APP_NAME
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"

    # Create directory structure
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    # Write Info.plist
    (contents / "Info.plist").write_text(_MACOS_INFO_PLIST)
    print(f"Installed {contents / 'Info.plist'}")

    # Write launcher script that finds the pip-installed mde
    mde_path = shutil.which("mde") or "mde"
    launcher = macos_dir / "mde-launcher"
    launcher.write_text(
        f'#!/bin/bash\nexec "{mde_path}" "$@"\n'
    )
    launcher.chmod(0o755)
    print(f"Installed {launcher}")

    # Convert PNG icon to icns using sips (built into macOS)
    icons_dir = _icons_dir()
    src_icon = icons_dir / "markdown-editor-256.png"
    dst_icon = resources / "app.icns"
    result = subprocess.run(
        ["sips", "-s", "format", "icns", str(src_icon),
         "--out", str(dst_icon)],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"Installed {dst_icon}")
    else:
        # Fallback: copy PNG as-is (icon may not display perfectly)
        shutil.copy2(src_icon, resources / "app.png")
        print(f"Warning: sips conversion failed, copied PNG icon instead")

    print(f"Done. '{_MACOS_APP_NAME}' is now in ~/Applications.")
    print("You can drag it to the Dock or find it in Launchpad.")
    return 0


def _uninstall_desktop_macos() -> int:
    """Remove .app bundle from ~/Applications."""
    app_dir = _MACOS_APP_DIR / _MACOS_APP_NAME

    if app_dir.exists():
        shutil.rmtree(app_dir)
        print(f"Removed {app_dir}")
        print("Done.")
    else:
        print("Nothing to remove.")

    return 0


_COMPLETABLE_COMMANDS = ["mde", "markdown-editor"]


def cmd_install_autocomplete(args: argparse.Namespace) -> int:
    """Register argcomplete shell completion for mde and markdown-editor."""
    try:
        import argcomplete  # noqa: F401
    except ImportError:
        print("argcomplete is not installed. Run: pip install argcomplete", file=sys.stderr)
        return 1

    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        _install_autocomplete_zsh()
    elif "fish" in shell:
        _install_autocomplete_fish()
    else:
        _install_autocomplete_bash()

    return 0


def _install_autocomplete_bash():
    """Install bash completion via ~/.bash_completion.d/."""
    comp_dir = Path.home() / ".bash_completion.d"
    comp_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _COMPLETABLE_COMMANDS:
        comp_file = comp_dir / cmd
        comp_file.write_text(
            f'eval "$(register-python-argcomplete {cmd})"\n'
        )
        print(f"Installed {comp_file}")

    # Ensure ~/.bash_completion.d/ is sourced
    bashrc = Path.home() / ".bashrc"
    sourcer = 'for f in ~/.bash_completion.d/*; do [ -f "$f" ] && . "$f"; done'
    if bashrc.exists() and sourcer not in bashrc.read_text():
        print(f"\nAdd this to your ~/.bashrc if not already present:")
        print(f"  {sourcer}")
    print("Then restart your shell or run: source ~/.bashrc")


def _install_autocomplete_zsh():
    """Install zsh completion."""
    comp_dir = Path.home() / ".zfunc"
    comp_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _COMPLETABLE_COMMANDS:
        comp_file = comp_dir / f"_{cmd}"
        result = subprocess.run(
            ["register-python-argcomplete", "--shell", "zsh", cmd],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            comp_file.write_text(result.stdout)
            print(f"Installed {comp_file}")
        else:
            print(f"Failed to generate completion for {cmd}: {result.stderr}", file=sys.stderr)

    zshrc = Path.home() / ".zshrc"
    lines_needed = ['fpath=(~/.zfunc $fpath)', 'autoload -Uz compinit && compinit']
    existing = zshrc.read_text() if zshrc.exists() else ""
    missing = [l for l in lines_needed if l not in existing]
    if missing:
        print(f"\nAdd these to your ~/.zshrc if not already present:")
        for line in missing:
            print(f"  {line}")
    print("Then restart your shell or run: exec zsh")


def _install_autocomplete_fish():
    """Install fish completion."""
    comp_dir = Path.home() / ".config" / "fish" / "completions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _COMPLETABLE_COMMANDS:
        result = subprocess.run(
            ["register-python-argcomplete", "--shell", "fish", cmd],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            comp_file = comp_dir / f"{cmd}.fish"
            comp_file.write_text(result.stdout)
            print(f"Installed {comp_file}")
        else:
            print(f"Failed to generate completion for {cmd}: {result.stderr}", file=sys.stderr)

    print("Completions will be active in new fish sessions.")


def cmd_uninstall_autocomplete(args: argparse.Namespace) -> int:
    """Remove argcomplete shell completions for mde and markdown-editor."""
    removed = []

    # bash
    comp_dir = Path.home() / ".bash_completion.d"
    for cmd in _COMPLETABLE_COMMANDS:
        f = comp_dir / cmd
        if f.exists():
            f.unlink()
            removed.append(str(f))

    # zsh
    zfunc_dir = Path.home() / ".zfunc"
    for cmd in _COMPLETABLE_COMMANDS:
        f = zfunc_dir / f"_{cmd}"
        if f.exists():
            f.unlink()
            removed.append(str(f))

    # fish
    fish_dir = Path.home() / ".config" / "fish" / "completions"
    for cmd in _COMPLETABLE_COMMANDS:
        f = fish_dir / f"{cmd}.fish"
        if f.exists():
            f.unlink()
            removed.append(str(f))

    if removed:
        for path in removed:
            print(f"Removed {path}")
        print("Restart your shell for changes to take effect.")
    else:
        print("Nothing to remove.")

    return 0


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
    from markdown_editor.markdown6.markdown_editor import (
        MarkdownEditor, apply_application_theme)

    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    # Apply saved theme at startup (before creating editor)
    ctx = get_app_context()
    theme = args.theme if args.theme else ctx.get("view.theme", "light")
    apply_application_theme(theme == "dark")

    # Create editor
    editor = MarkdownEditor()

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

    # Read-only mode
    if args.read_only:
        tab = editor.current_tab()
        if tab:
            tab.editor.setReadOnly(True)

    editor.show()
    ret = app.exec()
    del editor
    return ret


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    if argv is None:
        argv = sys.argv[1:]

    parser = create_parser()

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
