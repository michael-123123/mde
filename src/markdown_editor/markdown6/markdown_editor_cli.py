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
import sys
from pathlib import Path

from markdown_editor.markdown6.cli.desktop_integration import (
    cmd_install_desktop,
    cmd_uninstall_desktop,
)
from markdown_editor.markdown6.cli.export import cmd_export
from markdown_editor.markdown6.cli.graph import cmd_graph
from markdown_editor.markdown6.cli.gui import cmd_gui
from markdown_editor.markdown6.cli.shell_completion import (
    cmd_install_autocomplete,
    cmd_uninstall_autocomplete,
)
from markdown_editor.markdown6.cli.stats import cmd_stats
from markdown_editor.markdown6.cli.validate import cmd_validate


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
