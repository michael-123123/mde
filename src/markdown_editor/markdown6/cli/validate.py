"""``mde validate`` - check for broken wiki links and markdown links
across one or more files or an entire project.
"""

from __future__ import annotations

import argparse
import errno
import json
import sys
from pathlib import Path
from typing import Any

from markdown_editor.markdown6.cli.cli_helpers import get_project_files
from markdown_editor.markdown6.link_detection import (
    MD_LINK_PATTERN,
    WIKI_LINK_PATTERN,
    mask_verbatim_regions,
)
from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


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
