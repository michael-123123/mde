"""``mde stats`` - print word / line / heading / link counts for one
or more markdown files, a whole project, or stdin.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from markdown_editor.markdown6.cli.cli_helpers import (
    get_project_files,
    read_stdin,
)
from markdown_editor.markdown6.link_detection import (
    WIKI_LINK_PATTERN,
    mask_verbatim_regions,
)


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
