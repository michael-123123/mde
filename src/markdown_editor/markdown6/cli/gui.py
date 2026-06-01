"""GUI launch path. Bare ``mde`` (with optional file paths and
GUI-mode flags like ``--theme``, ``--read-only``, ``--zen-mode``)
ends up here. CLI-only subcommands (``export``, ``stats`` etc.) skip
this module entirely - that's why every heavy import below is
deferred to the function body.
"""

from __future__ import annotations

import argparse
import shutil
import sys


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the GUI editor.

    Every Qt / AppContext / editor import inside the function is lazy
    on purpose: the four CLI subcommand handlers (``export``, ``graph``,
    ``stats``, ``validate``) never invoke cmd_gui, and they should not
    pay the Qt-load cost just because the GUI launcher happens to live
    in the same parser tree.
    """
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
        # No explicit files - restore previous session if project matches
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
