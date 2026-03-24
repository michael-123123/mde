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
import sys
from pathlib import Path
from typing import TextIO


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
    files = []
    for ext in ["*.md", "*.markdown"]:
        files.extend(project_path.rglob(ext))
    return sorted(files)


def cmd_export(args: argparse.Namespace) -> int:
    """Handle export subcommand."""
    from markdown_editor.markdown6 import export_service

    # Determine input content
    content_parts = []
    title = args.title or "Document"

    if args.project:
        if not args.project.is_dir():
            print(f"Error: Project path is not a directory: {args.project}", file=sys.stderr)
            return 1
        files = get_project_files(args.project)
        if not files:
            print(f"Error: No markdown files found in {args.project}", file=sys.stderr)
            return 1
        title = args.title or args.project.name

        if args.toc:
            content_parts.append("# Table of Contents\n")
            for i, f in enumerate(files, 1):
                name = f.stem.replace("-", " ").replace("_", " ").title()
                content_parts.append(f"{i}. [{name}](#{name.lower().replace(' ', '-')})")
            content_parts.append("\n---\n")

        for f in files:
            if args.page_breaks and content_parts:
                if args.format == "html":
                    content_parts.append('<div style="page-break-before: always;"></div>\n')
                else:
                    content_parts.append("\n---\n")
            content_parts.append(f.read_text(encoding="utf-8"))
            content_parts.append("\n\n")

    elif args.files:
        for f in args.files:
            if not f.exists():
                print(f"Error: File not found: {f}", file=sys.stderr)
                return 1
            content_parts.append(f.read_text(encoding="utf-8"))
            if len(args.files) > 1:
                content_parts.append("\n\n")
        if len(args.files) == 1:
            title = args.title or args.files[0].stem

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
                print(export_service.markdown_to_html(content, title))
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
            export_service.export_html(content, output_path, title)
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


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the GUI editor."""
    from markdown_editor.markdown6.settings import init_settings

    # Initialize settings before importing editor
    # --reset: delete all config files and start clean
    # --new-session: use ephemeral settings (defaults only, no save)
    # --config: use custom config directory
    if args.reset:
        import shutil
        from markdown_editor.markdown6.settings import _default_config_dir
        config_dir = args.config or _default_config_dir()
        if config_dir.exists():
            shutil.rmtree(config_dir)
            print(f"Reset: deleted {config_dir}", file=sys.stderr)
        init_settings(ephemeral=True)
    elif args.new_session:
        init_settings(ephemeral=True)
    elif args.config:
        init_settings(config_dir=args.config)

    # Import Qt and editor
    from PySide6.QtWidgets import QApplication
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor, apply_application_theme
    from markdown_editor.markdown6.settings import get_settings

    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    # Apply saved theme at startup (before creating editor)
    settings = get_settings()
    theme = args.theme if args.theme else settings.get("view.theme", "light")
    apply_application_theme(theme == "dark")

    # Create editor
    editor = MarkdownEditor()

    # Apply theme override (also update settings if specified)
    if args.theme:
        editor.settings.set("view.theme", args.theme)

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
                    tab = editor.get_current_tab()
                    if tab:
                        tab.editor.go_to_line(args.line)
            else:
                print(f"Warning: File not found: {f}", file=sys.stderr)
    elif args.new:
        # Ensure at least one new tab
        if editor.tab_widget.count() == 0:
            editor.new_file()
    else:
        # No explicit files — restore previous session if project matches
        last_path = settings.get("project.last_path")
        project_path = str(args.project.resolve()) if args.project and args.project.is_dir() else None
        if last_path and (project_path is None or project_path == last_path):
            editor.restore_open_files()

    # Read-only mode
    if args.read_only:
        tab = editor.get_current_tab()
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
    subcommands = {"export", "graph", "stats", "validate"}

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
