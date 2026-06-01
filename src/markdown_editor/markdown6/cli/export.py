"""``mde export`` - export markdown to HTML / PDF / DOCX / Markdown
from one or more files, a whole project, or stdin.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from markdown_editor.markdown6.cli.cli_helpers import (
    get_project_files,
    read_stdin,
)


def cmd_export(args: argparse.Namespace) -> int:
    """Handle export subcommand."""
    # ``export_service`` and ``app_context`` are imported lazily so that
    # other CLI subcommands (``stats``, ``validate``, plain GUI launch)
    # don't pay their load cost - export_service pulls in the markdown
    # rendering stack and app_context transitively loads Qt.
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
    # Source markdown path - used by the renderer to resolve relative
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
