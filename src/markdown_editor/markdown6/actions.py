"""Data-driven action registry for menus, shortcuts, and command palette.

Each action is defined once. The menu bar, shortcut bindings, and command
palette are all generated from the same data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtGui import QKeySequence

from markdown_editor.markdown6.components.command_palette import Command

if TYPE_CHECKING:
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

# ---------------------------------------------------------------------------
# Menu item types
# ---------------------------------------------------------------------------

SEPARATOR = None


@dataclass
class ActionDef:
    """Definition of a single action."""
    id: str                           # e.g. "file.new"
    label: str                        # menu label with & mnemonic
    method: str                       # method name on MarkdownEditor
    shortcut_id: str = ""             # key into ShortcutManager (defaults to id)
    checkable: bool = False           # whether the action is checkable
    checked_setting: str = ""         # ctx setting key for initial checked state
    checked_default: bool = False     # default if setting not found
    palette_name: str = ""            # display name in command palette (empty = skip)
    palette_category: str = ""        # category in command palette
    attr: str = ""                    # store as self.<attr> on MarkdownEditor (empty = auto)
    args: tuple = ()                  # extra args passed via lambda


@dataclass
class SubmenuDef:
    """Definition of a submenu."""
    label: str
    items: list                       # list of ActionDef | SubmenuDef | SEPARATOR
    attr: str = ""                    # store as self.<attr> on MarkdownEditor


@dataclass
class MenuDef:
    """Definition of a top-level menu."""
    label: str
    items: list                       # list of ActionDef | SubmenuDef | SEPARATOR


def _action_attr(action: ActionDef) -> str:
    """Derive the self.<attr> name for an action."""
    if action.attr:
        return action.attr
    # "file.new" -> "new_action", "edit.undo" -> "undo_action"
    return action.id.split(".")[-1] + "_action"


def _shortcut_id(action: ActionDef) -> str:
    """Derive the shortcut ID for an action."""
    return action.shortcut_id or action.id


# ---------------------------------------------------------------------------
# Menu structure — single source of truth
# ---------------------------------------------------------------------------

MENU_STRUCTURE: list[MenuDef] = [
    MenuDef("&File", [
        ActionDef("file.new", "&New Tab", "new_tab",
                  palette_name="New Tab", palette_category="File"),
        ActionDef("file.open", "&Open...", "open_file",
                  palette_name="Open File", palette_category="File"),
        ActionDef("file.open_project", "Open &Project Folder...", "_open_project",
                  palette_name="Open Project Folder", palette_category="File"),
        SubmenuDef("Open &Recent", [], attr="recent_menu"),
        SEPARATOR,
        ActionDef("file.save", "&Save", "save_file",
                  palette_name="Save", palette_category="File"),
        ActionDef("file.save_as", "Save &As...", "save_file_as",
                  attr="save_as_action", palette_name="Save As", palette_category="File"),
        SEPARATOR,
        SubmenuDef("&Export", [
            ActionDef("export.html", "Export to &HTML...", "_export_html",
                      attr="export_html_action",
                      palette_name="Export to HTML", palette_category="Export"),
            ActionDef("export.pdf", "Export to &PDF...", "_export_pdf",
                      attr="export_pdf_action",
                      palette_name="Export to PDF", palette_category="Export"),
            ActionDef("export.docx", "Export to &DOCX...", "_export_docx",
                      attr="export_docx_action",
                      palette_name="Export to DOCX", palette_category="Export"),
        ]),
        SEPARATOR,
        ActionDef("file.close_tab", "&Close Tab", "_close_current_tab",
                  palette_name="Close Current Tab", palette_category="Tabs"),
        SEPARATOR,
        ActionDef("file.quit", "&Quit", "close"),
    ]),

    MenuDef("&Edit", [
        ActionDef("edit.undo", "&Undo", "_undo",
                  palette_name="Undo", palette_category="Edit"),
        ActionDef("edit.redo", "&Redo", "_redo",
                  palette_name="Redo", palette_category="Edit"),
        SEPARATOR,
        ActionDef("edit.cut", "Cu&t", "_cut"),
        ActionDef("edit.copy", "&Copy", "_copy"),
        ActionDef("edit.paste", "&Paste", "_paste"),
        ActionDef("edit.select_all", "Select &All", "_select_all"),
        SEPARATOR,
        ActionDef("edit.find", "&Find...", "_show_find",
                  palette_name="Find", palette_category="Edit"),
        ActionDef("edit.replace", "&Replace...", "_show_replace",
                  palette_name="Replace", palette_category="Edit"),
        ActionDef("edit.go_to_line", "&Go to Line...", "_go_to_line",
                  palette_name="Go to Line", palette_category="Edit"),
        SEPARATOR,
        ActionDef("edit.duplicate_line", "&Duplicate Line", "_duplicate_line",
                  palette_name="Duplicate Line", palette_category="Edit"),
        ActionDef("edit.delete_line", "De&lete Line", "_delete_line",
                  palette_name="Delete Line", palette_category="Edit"),
        ActionDef("edit.move_line_up", "Move Line &Up", "_move_line_up",
                  palette_name="Move Line Up", palette_category="Edit"),
        ActionDef("edit.move_line_down", "Move Line &Down", "_move_line_down",
                  palette_name="Move Line Down", palette_category="Edit"),
        SEPARATOR,
        ActionDef("edit.toggle_comment", "Toggle &Comment", "_toggle_comment",
                  palette_name="Toggle Comment", palette_category="Edit"),
        SEPARATOR,
        ActionDef("edit.settings", "Se&ttings...", "_show_settings",
                  attr="settings_action",
                  palette_name="Open Settings", palette_category="Settings"),
    ]),

    MenuDef("F&ormat", [
        ActionDef("markdown.bold", "&Bold", "_format_bold",
                  palette_name="Bold", palette_category="Format"),
        ActionDef("markdown.italic", "&Italic", "_format_italic",
                  palette_name="Italic", palette_category="Format"),
        ActionDef("markdown.code", "&Code", "_format_code",
                  palette_name="Code", palette_category="Format"),
        SEPARATOR,
        ActionDef("markdown.link", "Insert &Link", "_format_link",
                  attr="link_action",
                  palette_name="Insert Link", palette_category="Format"),
        ActionDef("markdown.image", "Insert &Image", "_format_image",
                  attr="image_action",
                  palette_name="Insert Image", palette_category="Format"),
        SEPARATOR,
        ActionDef("markdown.heading_increase", "Increase &Heading Level", "_heading_increase",
                  palette_name="Increase Heading Level", palette_category="Format"),
        ActionDef("markdown.heading_decrease", "&Decrease Heading Level", "_heading_decrease",
                  palette_name="Decrease Heading Level", palette_category="Format"),
        SEPARATOR,
        SubmenuDef("&Insert", [
            ActionDef("insert.table", "&Table...", "_insert_table",
                      palette_name="Insert Table", palette_category="Insert"),
            ActionDef("insert.snippet", "&Snippet...", "_show_snippet_popup",
                      palette_name="Insert Snippet", palette_category="Insert"),
            SEPARATOR,
            ActionDef("insert.math", "&Math Block", "_insert_math",
                      palette_name="Insert Math Block", palette_category="Insert"),
            ActionDef("insert.mermaid", "M&ermaid Diagram", "_insert_mermaid",
                      palette_name="Insert Mermaid Diagram", palette_category="Insert"),
            SEPARATOR,
            ActionDef("insert.callout_note", "Callout: &Note", "_insert_callout",
                      args=("NOTE",),
                      palette_name="Insert Note Callout", palette_category="Insert"),
            ActionDef("insert.callout_warning", "Callout: &Warning", "_insert_callout",
                      args=("WARNING",),
                      palette_name="Insert Warning Callout", palette_category="Insert"),
            ActionDef("insert.callout_tip", "Callout: &Tip", "_insert_callout",
                      args=("TIP",),
                      palette_name="Insert Tip Callout", palette_category="Insert"),
        ]),
    ]),

    MenuDef("&View", [
        ActionDef("view.command_palette", "&Command Palette...", "_show_command_palette"),
        SEPARATOR,
        SubmenuDef("&Panels", [
            ActionDef("view.toggle_outline", "Toggle &Outline", "_toggle_outline_panel",
                      checkable=True,
                      palette_name="Toggle Outline Panel", palette_category="View"),
            ActionDef("view.toggle_project", "Toggle &Project Panel", "_toggle_project_panel",
                      checkable=True,
                      palette_name="Toggle Project Panel", palette_category="View"),
            ActionDef("view.toggle_references", "Toggle &References Panel", "_toggle_references_panel",
                      checkable=True,
                      palette_name="Toggle References Panel", palette_category="View"),
            ActionDef("view.toggle_search", "Toggle &Search Panel", "_toggle_search_panel",
                      checkable=True,
                      palette_name="Toggle Search Panel", palette_category="View"),
            SEPARATOR,
            ActionDef("view.toggle_sidebar", "Toggle Si&debar", "_toggle_sidebar",
                      palette_name="Toggle Sidebar", palette_category="View"),
        ]),
        SEPARATOR,
        SubmenuDef("&Folding", [
            ActionDef("view.fold_all", "Fold &All", "_fold_all",
                      palette_name="Fold All", palette_category="View"),
            ActionDef("view.unfold_all", "&Unfold All", "_unfold_all",
                      palette_name="Unfold All", palette_category="View"),
        ]),
        SEPARATOR,
        ActionDef("view.refresh_preview", "&Refresh Preview", "_refresh_preview"),
        SEPARATOR,
        ActionDef("view.toggle_preview", "Toggle &Preview", "_toggle_preview",
                  checkable=True, checked_setting="view.show_preview", checked_default=True,
                  palette_name="Toggle Preview", palette_category="View"),
        ActionDef("view.toggle_line_numbers", "Toggle &Line Numbers", "_toggle_line_numbers",
                  checkable=True, checked_setting="editor.show_line_numbers", checked_default=True),
        ActionDef("view.toggle_word_wrap", "Toggle &Word Wrap", "_toggle_word_wrap",
                  checkable=True, checked_setting="editor.word_wrap", checked_default=True),
        ActionDef("view.toggle_whitespace", "Toggle Whi&tespace", "_toggle_whitespace",
                  checkable=True, checked_setting="editor.show_whitespace", checked_default=False),
        ActionDef("view.toggle_logseq_mode", "&Logseq Mode", "_toggle_logseq_mode",
                  attr="toggle_logseq_action",
                  checkable=True, checked_setting="view.logseq_mode", checked_default=False),
        SEPARATOR,
        ActionDef("view.zoom_in", "Zoom &In", "_zoom_in",
                  palette_name="Zoom In", palette_category="View"),
        ActionDef("view.zoom_out", "Zoom &Out", "_zoom_out",
                  palette_name="Zoom Out", palette_category="View"),
        ActionDef("view.zoom_reset", "&Reset Zoom", "_zoom_reset",
                  palette_name="Reset Zoom", palette_category="View"),
        SEPARATOR,
        ActionDef("view.fullscreen", "&Fullscreen", "_toggle_fullscreen",
                  checkable=True,
                  palette_name="Toggle Fullscreen", palette_category="View"),
        SEPARATOR,
        ActionDef("tabs.next", "&Next Tab", "_next_tab",
                  palette_name="Next Tab", palette_category="Tabs"),
        ActionDef("tabs.previous", "&Previous Tab", "_prev_tab",
                  palette_name="Previous Tab", palette_category="Tabs"),
    ]),

    MenuDef("&Tools", [
        ActionDef("tools.export_graph", "Export Document &Graph...", "_show_graph_export",
                  attr="export_graph_action"),
    ]),

    MenuDef("&Help", [
        ActionDef("help.about", "&About", "_show_about"),
    ]),
]

# Command-palette-only entries (no menu item)
PALETTE_ONLY: list[ActionDef] = [
    ActionDef("view.toggle_theme", "", "_toggle_theme",
              palette_name="Toggle Light/Dark Theme", palette_category="View"),
]


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

def _make_callback(editor: MarkdownEditor, method_name: str, args: tuple):
    """Create a callback, wrapping in a lambda if args are needed."""
    method = getattr(editor, method_name)
    if args:
        return lambda *_a, _m=method, _args=args: _m(*_args)
    return method


def _build_items(editor: MarkdownEditor, menu, items: list) -> list[ActionDef]:
    """Recursively build menu items. Returns all ActionDefs encountered."""
    from PySide6.QtWidgets import QMenu

    all_actions: list[ActionDef] = []

    for item in items:
        if item is SEPARATOR:
            menu.addSeparator()
        elif isinstance(item, SubmenuDef):
            submenu = QMenu(item.label, editor)
            menu.addMenu(submenu)
            if item.attr:
                setattr(editor, item.attr, submenu)
            all_actions.extend(_build_items(editor, submenu, item.items))
        elif isinstance(item, ActionDef):
            action = menu.addAction(item.label)
            action.triggered.connect(_make_callback(editor, item.method, item.args))

            if item.checkable:
                action.setCheckable(True)
                if item.checked_setting:
                    action.setChecked(
                        editor.ctx.get(item.checked_setting, item.checked_default)
                    )

            attr_name = _action_attr(item)
            setattr(editor, attr_name, action)
            all_actions.append(item)

    return all_actions


def build_menu_bar(editor: MarkdownEditor) -> dict[str, ActionDef]:
    """Build the entire menu bar from MENU_STRUCTURE.

    Returns a dict mapping action IDs to their ActionDefs.
    """
    menubar = editor.menuBar()
    all_actions: list[ActionDef] = []

    for menu_def in MENU_STRUCTURE:
        menu = menubar.addMenu(menu_def.label)
        all_actions.extend(_build_items(editor, menu, menu_def.items))

    return {a.id: a for a in all_actions}


def apply_shortcuts(editor: MarkdownEditor, action_defs: dict[str, ActionDef]):
    """Apply shortcuts from ShortcutManager to all registered actions."""
    for action_id, action_def in action_defs.items():
        shortcut = editor.ctx.get_shortcut(_shortcut_id(action_def))
        if shortcut:
            attr_name = _action_attr(action_def)
            action = getattr(editor, attr_name, None)
            if action:
                action.setShortcut(QKeySequence(shortcut))


def build_command_palette(editor: MarkdownEditor, action_defs: dict[str, ActionDef]) -> list[Command]:
    """Build command palette entries from action definitions."""
    commands = []

    all_defs = list(action_defs.values()) + PALETTE_ONLY
    for action_def in all_defs:
        if not action_def.palette_name:
            continue
        shortcut = editor.ctx.get_shortcut(_shortcut_id(action_def))
        callback = _make_callback(editor, action_def.method, action_def.args)
        commands.append(Command(
            id=action_def.id,
            name=action_def.palette_name,
            shortcut=shortcut or "",
            callback=callback,
            category=action_def.palette_category,
        ))

    return commands
