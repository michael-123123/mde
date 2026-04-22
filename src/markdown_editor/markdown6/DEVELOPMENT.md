# Markdown Editor - Development Guide

This document provides technical documentation for developers continuing work on this project.

## Architecture Overview

The application follows a loosely coupled widget-based architecture using Qt's signal/slot mechanism for communication. There is no formal MVC separation - UI and logic are mixed within widget classes.

```
┌───────────────────────────────────────────────────────────────────────┐
│                      MarkdownEditor (QMainWindow)                      │
│  - Main window, menus (built from actions.py), toolbar, status bar     │
│  - Tab widget, file operations, export dispatch                        │
│  - Theme propagation via AppContext signals                            │
├───────────┬────────────┬────────────────────────────────────────────┤
│ Activity  │  Sidebar   │              Tab Widget                       │
│  Bar      │  (tool     │  ┌─────────────────────────────────────────┐ │
│ (vertical │   window,  │  │       DocumentTab (components/)          │ │
│  emoji    │   collap-  │  │  ┌──────────────┬────────────────────┐  │ │
│  tabs;    │   sible)   │  │  │ Enhanced-    │   Preview pane     │  │ │
│  compo-   │            │  │  │  Editor      │   (QWebEngineView  │  │ │
│  nents/   │  Stacked:  │  │  │              │    or QTextBrowser)│  │ │
│  activity │  Project / │  │  │ Syntax HL    │                    │  │ │
│  _bar.py) │  Outline / │  │  │ Folding      │   source-line sync │  │ │
│           │  Search /  │  │  │ Line nums    │                    │  │ │
│           │  Refs      │  │  └──────────────┴────────────────────┘  │ │
│           │            │  │  FindReplaceBar  +  ExternalChangeBar     │ │
│           │            │  └─────────────────────────────────────────┘ │
└───────────┴────────────┴────────────────────────────────────────────┘

       AppContext (app_context/)                      actions.py
  ┌──────────────────────────────┐               ┌────────────────────┐
  │ SettingsManager              │               │ MENU_STRUCTURE     │
  │ ShortcutManager              │◀──shortcuts──▶│ ActionDef list →   │
  │ SessionState                 │               │   menus, shortcuts,│
  │ signals: settings_changed,   │               │   palette (built   │
  │   shortcut_changed,          │               │   by helpers)      │
  │   theme_changed              │               └────────────────────┘
  └──────────────────────────────┘
```

## Key Classes

### Core Classes

#### `MarkdownEditor` (`markdown_editor.py`)
The main window class. Responsibilities:
- Window layout, menus (built from `actions.MENU_STRUCTURE` via `build_menu_bar()`), toolbar, status bar
- Tab widget management (create, close, switch tabs)
- File operations (open, save, save as, recent files)
- Export operations (delegates to `export_service`)
- Command palette integration (built via `build_command_palette()`)
- Keyboard shortcut management (applied via `apply_shortcuts()`)
- Theme application coordination

**Key methods:**
- `open_file(path)` — opens file, checks for duplicates, creates tab
- `save_file()` / `save_file_as()` — save operations
- `new_tab()` — creates empty `DocumentTab`
- `update_window_title()` — updates title with project-relative path
- `_handle_link_click(url)` — handles preview link clicks
- `_handle_editor_link_click(path)` — handles Ctrl+click on editor links

#### `DocumentTab` (`components/document_tab.py`)
A container widget for a single document. Contains:
- `EnhancedEditor` — the text editor
- Preview pane (`QWebEngineView` or `QTextBrowser` fallback)
- `FindReplaceBar`
- `ExternalChangeBar` (non-modal reload notification)
- Splitter between editor and preview

**Key attributes:**
- `file_path: Path | None` — current file path
- `unsaved_changes: bool` — dirty state (read-only `@property` derived from `self.editor.document().isModified()`; reset the baseline by calling `document().setModified(False)` on load/save)
- `editor: EnhancedEditor` — the text editor widget

**Signals:**
- `file_changed(path)`
- `modified_changed(bool)`
- `title_changed(title)`

#### `EnhancedEditor` (`enhanced_editor.py`)
The main text editor widget (`QPlainTextEdit` subclass). Responsibilities:
- Syntax highlighting (via MarkdownHighlighter)
- Line number area
- Code folding
- Auto-pairs and auto-indent
- Word count
- Wiki link completion
- Link detection and Ctrl+click handling
- Mouse hover effects for links
- Zoom support
- External file change detection

**Signals:**
- `word_count_changed(int, int)` - words, characters
- `cursor_position_changed(int, int)` - line, column
- `file_externally_modified()` - File changed on disk
- `link_ctrl_clicked(str)` - Ctrl+click on link

**Key methods:**
- `_find_link_at_cursor(cursor)` - Detects wiki/markdown/URL links
- `wrap_selection(wrapper)` - Wraps selection with markdown syntax
- `format_bold()`, `format_italic()`, etc. - Formatting operations
- `move_line_up()`, `move_line_down()` - Line manipulation
- `fold_all()`, `unfold_all()` - Folding operations

### Panel Classes

#### `ProjectPanel` (`project_manager.py`)
File tree panel for project folder management.

**Signals:**
- `file_selected(str)` - Single click on file
- `file_double_clicked(str)` - Double click opens file

**Key methods:**
- `open_project(path)` - Opens folder as project
- `_show_export_dialog()` - Opens ProjectExportDialog

#### `OutlinePanel` (`components/outline_panel.py`)
Document structure panel showing headings.

**Signals:**
- `heading_clicked(int)` - Line number of clicked heading

**Key methods:**
- `update_outline(text)` - Parses markdown and updates tree
- `_parse_headings(text)` - Extracts heading structure

#### `ReferencesPanel` (`components/references_panel.py`)
Backlinks panel showing files that reference the current document.

**Signals:**
- `file_clicked(str)` - File path clicked
- `reference_clicked(str, int)` - File path and line number

**Key methods:**
- `update_references(file_path, project_path)` - Scans for references
- `_find_references(file_path, project_path)` - Search logic

### Support Classes

#### `AppContext` (`app_context/`)
Package containing the application-context facade. Owns `SettingsManager`, `ShortcutManager`, `SessionState`. JSON persistence to `~/.config/markdown-editor/` via `temp_files.atomic_write()`.

**Signals:**
- `settings_changed(str, object)` — key, new_value
- `shortcut_changed(str, str)` — action, new_shortcut (delegated from `ShortcutManager`)
- `theme_changed(str)` — theme name

**Access:** `from markdown_editor.markdown6.app_context import get_app_context`

#### `SearchPanel` (`components/search_panel.py`)
Project-wide regex search with results tree and jump-to-match.

#### `CommandPalette` (`components/command_palette.py`)
Ctrl+Shift+P command access. Commands are built from `actions.py` via `build_command_palette()`.

#### `Sidebar` / `ActivityBar` (`components/sidebar.py`, `components/activity_bar.py`)
VSCode-style split: `ActivityBar` exposes vertical emoji-tabs that toggle a collapsible `Sidebar` tool-window containing the panels above.

#### `GraphExportDialog` (`components/graph_export.py`)
Document wiki-link graph visualization + export (SVG/PNG/PDF) with selectable layout engine.

#### `SettingsDialog` (`components/settings_dialog.py`)
Multi-page settings dialog (Editor, View, Appearance/Preview, Files, Tools, Keyboard).

#### `SnippetManager` / `SnippetPopup` (`snippets.py`)
Snippet system (Ctrl+J) with searchable popup and `${1:placeholder}` cursor placement.

#### `FileTreeWidget` (`file_tree_widget.py`)
Reusable checkbox file-tree widget used by export and graph dialogs.

#### `MarkdownHighlighter` (syntax_highlighter.py)
QSyntaxHighlighter for markdown with dark/light theme support.

#### `export_service` (export_service.py)
Stateless module for export operations.

**Key functions:**
- `has_pandoc()` - Check if pandoc is available
- `export_html(content, path, title)` - HTML export
- `export_pdf(content, path, title, use_pandoc=False)` - PDF export
- `export_docx(content, path, title, use_pandoc=False)` - DOCX export

#### `ThemeColors` / `StyleSheets` (theme.py)
Centralized theme definitions and stylesheet generators.

```python
from markdown_editor.markdown6.theme import get_theme, get_theme_from_ctx, StyleSheets
theme = get_theme(dark_mode=True)           # explicit
theme = get_theme_from_ctx(ctx)              # from AppContext settings (0.1.10+)
stylesheet = StyleSheets.dialog(theme) + StyleSheets.button(theme)
```

## Signal Flow

### Opening a File
```
User double-clicks file in ProjectPanel
    → file_double_clicked signal
    → MarkdownEditor.open_file(path)
        → Check for duplicate tabs (by resolved path)
        → Create DocumentTab if needed
        → Load content, set file_path
        → Trigger render_markdown()
        → Update outline, references, window title
```

### Link Click in Preview
```
User clicks link in preview
    → LinkInterceptPage.acceptNavigationRequest()
    → link_clicked signal
    → DocumentTab receives, re-emits link_clicked
    → MarkdownEditor._handle_link_click(url)
        → If .md file: open_file()
        → Else: QDesktopServices.openUrl()
```

### Ctrl+Click in Editor
```
User Ctrl+clicks on link text
    → EnhancedEditor.mousePressEvent()
    → _find_link_at_cursor() detects link
    → link_ctrl_clicked signal
    → MarkdownEditor._handle_editor_link_click(path)
        → Resolve path relative to current file
        → open_file()
```

### Settings Change
```
User changes setting in SettingsDialog
    → AppContext.set(key, value)
    → settings_changed signal
    → All listening widgets receive and update
        → EnhancedEditor._on_setting_changed()
        → OutlinePanel._on_setting_changed()
        → etc.
```

### Theme Change
```
AppContext.set("view.theme", "dark")
    → theme_changed signal
    → MarkdownEditor._on_theme_changed()
        → apply_application_theme(dark_mode)
        → Update all panels and dialogs
```

### Command Palette Dispatch
```
User types Ctrl+Shift+P
    → CommandPalette pops up with entries built from actions.py
    → User selects a Command
    → Command.callback() is invoked
        → Routes back to the corresponding method on MarkdownEditor
           (the ActionDef.method name; resolved by apply_shortcuts /
            build_command_palette at startup)
```

### Session Restore on Startup
```
MarkdownEditor.__init__()
    → AppContext loads settings, shortcuts, SessionState JSON
    → Read project.last_path, project.open_files, project.active_tab
    → Open project (ProjectPanel.open_project)
    → For each remembered open file: open_file(path)
    → Activate the last active tab, restore sidebar state
    → ExternalChangeBar starts watching loaded files
```

### Source-Line Scroll Sync (bidirectional)
```
SourceLinePreprocessor / SourceLinePostprocessor
    → emit data-source-line="N" on HTML block elements
Editor scrolls:
    → EnhancedEditor.cursor_position_changed(line, col)
    → DocumentTab scrolls preview to element with matching data-source-line
Preview scrolls:
    → JS in preview page posts the topmost visible data-source-line to Qt
    → DocumentTab scrolls editor to that line
```

### Async Diagram Render Pipeline
```
Preview HTML contains a placeholder <div data-mermaid-src="..."> or <div data-dot-src="...">
    → DocumentTab submits the source to mermaid_service / graphviz_service
    → Service checks in-memory MD5 cache; on miss, runs mmdc/dot in a thread
    → On completion: service returns SVG; DocumentTab injects it into the
      placeholder via QWebChannel / document.getElementById replacement
    → Errors are rendered as inline error SVG with the stderr text
```

## Adding New Features

### Adding a New Panel

1. Create the panel class under `components/`:
```python
# components/my_panel.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..theme import get_theme_from_ctx

class MyPanel(QWidget):
    item_clicked = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._init_ui()
        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key, value):
        if key == "view.theme":
            self._apply_theme()
```

2. In `MarkdownEditor._init_ui()`, register an `ActivityTab` and add the panel as a page to the sidebar's stacked widget:
```python
self.my_panel = MyPanel(self.ctx)
self.sidebar.add_panel("my", "🧩", "My Panel", self.my_panel)
```

3. Connect signals in `MarkdownEditor`:
```python
self.my_panel.item_clicked.connect(self._on_my_panel_item_clicked)
```

4. If the panel should be toggleable via shortcut / command palette, add a toggle `ActionDef` to `actions.MENU_STRUCTURE` — that single entry handles menu, shortcut, and palette registration.

### Adding a New Menu Item / Keyboard Shortcut

Since 0.1.11 the menu bar, keyboard shortcuts, and command palette are all wired up from a single `ActionDef` entry in `actions.py`. One edit registers all three.

1. Add the default shortcut in `app_context/shortcut_manager.py`:
```python
DEFAULT_SHORTCUTS = {
    ...
    "my_feature.action": "Ctrl+Shift+M",
}
```

2. Add the action to `MENU_STRUCTURE` in `actions.py` (or to `PALETTE_ONLY` for a palette-only entry) and implement the handler on `MarkdownEditor`:
```python
# actions.py
MENU_STRUCTURE = [
    ...
    MenuDef("Tools", [
        ...
        ActionDef(
            label="My Action",
            method="_my_action_handler",
            shortcut_id="my_feature.action",
            palette_name="My Action",
            palette_category="Tools",
        ),
    ]),
]
```

3. `build_menu_bar(editor)`, `apply_shortcuts(editor, action_defs)`, and `build_command_palette(editor, action_defs)` will create the menu item, assign the shortcut, and register the palette entry automatically.

### Adding a New Export Format

1. Add export function in export_service.py:
```python
def export_xyz(content: str, output_path: str | Path, title: str = "Document") -> None:
    # Implementation
    pass
```

2. Update ProjectExportDialog._init_ui() format combo:
```python
self.format_combo.addItems(["HTML", "PDF", "DOCX", "Markdown", "XYZ"])
```

3. Update export logic in ProjectExportDialog._export():
```python
elif format_type == "xyz":
    export_service.export_xyz(combined, output_path, title)
```

### Adding a Plugin

Plugins live outside the core code — they're Python directories the editor discovers from any of three roots: `markdown_editor/markdown6/builtin_plugins/<name>/` (reserved for plugins shipped with the editor; currently empty), `<config_dir>/plugins/<name>/` (the user's installed plugins), and any extra dirs added via `--plugins-dir DIR` (CLI, repeatable) or the `plugins.extra_dirs` setting (managed in **Settings → Plugins → Extra plugin directories**). All sources are additive. The plugin API is documented for *plugin authors* in [`docs/plugins.md`](../../../docs/plugins.md); the stability contract is in [`docs/plugin-api-versioning.md`](../../../docs/plugin-api-versioning.md).

When adding a plugin yourself:

1. Use the public shim only — `from markdown_editor.plugins import register_action, on_save, plugin_settings, ...`. Do **not** import from `markdown_editor.markdown6.plugins.*` (the deeper internal namespace is not stable).
2. Match the directory name in `<name>.py`, `<name>.toml`, and `[tool.mde.plugin].name`. The loader fails `METADATA_ERROR` if any of those disagree.
3. Read the example plugins as references — they live under [`docs/plugins-examples/`](../../../docs/plugins-examples/): `em_dash_to_hyphen` (text transform), `wordcount` (panel + signals + scoped settings), `stamp` (action + settings schema with every supported field type).

Internal plugin-system architecture lives under `markdown6/plugins/`:

| File | Responsibility |
|---|---|
| `metadata.py` | `[tool.mde.plugin]` TOML parser and validation |
| `loader.py` | Discovery + dependency check + import |
| `plugin.py` | `Plugin` dataclass + `PluginStatus` / `PluginSource` enums |
| `registry.py` | Records (`PluginAction`, `PluginPanel`, `PluginFence`, …) and the central `PluginRegistry` |
| `api.py` | Public API surface (registration decorators, lifecycle signal decorators, `notify_*`, etc.) |
| `signals.py` | `SignalKind` + `dispatch()` |
| `fence.py` | `PluginFenceExtension` (markdown extension that dispatches plugin fences) |
| `editor_integration.py` | Menu/palette injection, panel installation, live-disable filtering |
| `scoped_settings.py` | `PluginSettings` dict-like façade backed by `plugins.<id>.<key>` |
| `document_handle.py` | Qt-free `DocumentHandle` plugins receive (with opt-in `editor` / `preview` escape hatches) |
| `reload.py` | Discover-only "Reload plugins" diff |

Plugin runtime errors route into `markdown6/notifications.py:NotificationCenter` (one per `AppContext`), surfaced through the bell button + drawer in the status bar. The `notify_*` helpers in the shim let plugins post their own non-error notifications too.

### Adding a New Markdown Extension

Extensions live in the `extensions/` subpackage (`callouts.py`, `diagrams.py`, `lists.py`, `logseq.py`, `math.py`, `source_lines.py`, `wikilinks.py`). The package's `__init__.py` re-exports the public API so callers can `from markdown_editor.markdown6.extensions import MermaidExtension, ...`.

1. Create a new module under `extensions/`:
```python
# extensions/my_ext.py
from markdown import Extension
from markdown.preprocessors import Preprocessor

class MyPreprocessor(Preprocessor):
    def run(self, lines):
        # Process lines
        return new_lines

class MyExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MyPreprocessor(md), 'my_ext', 25)
```

2. Register it where the preview markdown instance is constructed (`components/document_tab.py`):
```python
from ..extensions.my_ext import MyExtension
self.md = markdown.Markdown(extensions=[..., MyExtension()])
```

3. (Optional) Add a re-export line to `extensions/__init__.py` so the extension is accessible from the package root.

## Code Patterns

### Theme Application
All widgets that need theming should:
1. Accept `ctx` (AppContext) as constructor parameter
2. Connect to settings_changed signal
3. Implement `_apply_theme()` method
4. Call `_apply_theme()` in `__init__` and when theme changes

```python
def _on_setting_changed(self, key, value):
    if key == "view.theme":
        self._apply_theme()

def _apply_theme(self):
    theme = get_theme(self.ctx.get("view.theme") == "dark")
    self.setStyleSheet(StyleSheets.dialog(theme) + StyleSheets.button(theme))
```

### Progress Dialogs
For long operations, use QProgressDialog:
```python
progress = QProgressDialog("Working...", "Cancel", 0, total, self)
progress.setWindowModality(Qt.WindowModality.WindowModal)
progress.setMinimumDuration(0)

for i, item in enumerate(items):
    if progress.wasCanceled():
        return
    progress.setLabelText(f"Processing: {item.name}")
    progress.setValue(i)
    QApplication.processEvents()
    # Do work

progress.setValue(total)
```

### File Path Handling
Always resolve paths for comparison:
```python
# Checking if file is already open
if tab.file_path and tab.file_path.resolve() == path.resolve():
    # Same file
```

### Link Detection Patterns
The editor recognizes these link patterns:
- Wiki links: `\[\[([^\]|]+)(?:\|[^\]]+)?\]\]`
- Markdown links: `\[([^\]]*)\]\(([^)]+)\)`
- Bare URLs: `https?://[^\s<>\[\]]+`

## Known Technical Debt

### Architecture Issues
1. **MarkdownEditor is still large** (~1800 lines) — could still extract `TabManager` and `PanelManager`. `ActionManager`-style concerns are already addressed by `actions.py`.
2. **No Model layer** — document state is mixed with UI in `DocumentTab`.
3. ~~**Global settings singleton**~~ — resolved: settings refactored into `AppContext` with dependency injection.
4. ~~**Action/shortcut/palette duplication** (three-place registration)~~ — resolved: single `ActionDef` in `actions.py` wires all three.
5. ~~**DocumentTab defined inside markdown_editor.py**~~ — resolved: extracted to `components/document_tab.py` (0.1.11).
6. **Duplicated theme handling** — each widget implements its own `_apply_theme()`.

### Code Duplication
1. Theme application code repeated in ~10 widget classes.
2. Link detection regex duplicated between `EnhancedEditor` and `components/references_panel.py`.
3. Similar panel initialization patterns repeated across `components/`.

### Potential Improvements
1. Extract a signal hub for centralized event management.
2. Create a base `ThemedWidget` class to reduce duplication.
3. Add a proper Model layer for document state.
4. Implement an app-wide undo/redo framework (beyond the editor's built-in undo).

## File Reference

All paths are relative to `src/markdown_editor/markdown6/`.

### Top-level

| File | Lines | Primary Class / Purpose |
|------|------:|------------------------|
| `markdown_editor.py`       | 1816 | `MarkdownEditor` QMainWindow; primary integration point |
| `markdown_editor_cli.py`   | 1330 | `mde` CLI entry point: GUI mode + `export`/`graph`/`stats`/`validate`/`(un)install-desktop`/`(un)install-autocomplete` |
| `actions.py`               |  351 | `ActionDef`, `MenuDef`, `MENU_STRUCTURE`, `PALETTE_ONLY`; `build_menu_bar`, `apply_shortcuts`, `build_command_palette` |
| `enhanced_editor.py`       | 1471 | `EnhancedEditor`, `LineNumberArea`, `WikiLinkCompleter`, `FoldingRegion` |
| `syntax_highlighter.py`    |  329 | `MarkdownHighlighter` |
| `theme.py`                 |  765 | `ThemeColors`, `StyleSheets`, `get_theme`, `get_theme_from_ctx` |
| `export_service.py`        |  269 | `markdown_to_html`, `export_html/pdf/docx`, `has_pandoc`, `ExportError` |
| `graphviz_service.py`      |  302 | `render_dot`, `has_graphviz` (cached) |
| `mermaid_service.py`       |  255 | `render_mermaid`, `has_mermaid` (cached) |
| `tool_paths.py`            |   68 | `get_pandoc_path` / `get_dot_path` / `get_mmdc_path` + `has_*` |
| `notifications.py`         | ~135 | `NotificationCenter` (in-memory, signals, capped history); read by the bell + drawer in the status bar |
| `snippets.py`              |  406 | `Snippet`, `SnippetManager`, `SnippetPopup` |
| `searchable_popup.py`      |   99 | `SearchablePopup` base class |
| `logger.py`                |   77 | Colored `getLogger` / `setup` under `mde` namespace |
| `temp_files.py`            |  121 | `create_temp_file`, `create_temp_dir`, `atomic_write` |
| `file_tree_widget.py`      |  192 | `FileTreeWidget` (checkbox file tree) |
| `project_manager.py`       |  589 | `ProjectPanel`, `ProjectConfig` |

### `app_context/`

| File | Lines | Purpose |
|------|------:|---------|
| `__init__.py`          | 246 | `AppContext` facade, `get_app_context()`, `init_app_context()` |
| `settings_manager.py`  | 133 | `SettingsManager` — user preferences |
| `shortcut_manager.py`  | 206 | `ShortcutManager` — keyboard-shortcut defaults + persistence |
| `session_state.py`     | 129 | `SessionState` — recent files, open tabs, sidebar state |

### `components/`

| File | Lines | Purpose |
|------|------:|---------|
| `activity_bar.py`       |  232 | `ActivityBar`, `ActivityTab` |
| `sidebar.py`            |  255 | Collapsible `Sidebar` tool window |
| `document_tab.py`       |  661 | `DocumentTab` — per-document editor + preview container |
| `outline_panel.py`      |  167 | `OutlinePanel`, `Heading` |
| `references_panel.py`   |  261 | `ReferencesPanel`, `Reference` |
| `search_panel.py`       |  281 | `SearchPanel`, `SearchMatch` |
| `command_palette.py`    |  133 | `CommandPalette`, `Command` |
| `find_replace_bar.py`   |  401 | `FindReplaceBar` |
| `external_change_bar.py`|   64 | `ExternalChangeBar` |
| `settings_dialog.py`    |  844 | `SettingsDialog` multi-page (Editor, View, Appearance, Files, Tools, Shortcuts, **Plugins**) |
| `table_editor.py`       |  287 | `TableEditorDialog` |
| `graph_export.py`       | 1120 | `GraphExportDialog` |
| `plugins_page.py`       | ~290 | `PluginsSettingsPage` — Settings → Plugins UI (rows, Open Folder, Reload, Configure / Info buttons) |
| `plugin_configure_dialog.py` | ~190 | `PluginConfigureDialog` — auto-rendered from a plugin's `register_settings_schema` |
| `plugin_info_dialog.py` | ~130 | `PluginInfoDialog` — metadata + status detail + README rendering |
| `notification_bell.py`  | ~225 | `NotificationBellButton` (status bar) + `NotificationDrawer` popup |

### `plugins/` (plugin system internals)

| File | Lines | Purpose |
|------|------:|---------|
| `metadata.py`         | ~160 | `[tool.mde.plugin]` TOML parsing + validation |
| `loader.py`           | ~270 | Discovery + dep check + import; never raises |
| `plugin.py`           |  ~60 | `Plugin` dataclass; `PluginStatus`, `PluginSource` enums |
| `registry.py`         | ~165 | All plugin record dataclasses + central `PluginRegistry` |
| `api.py`              | ~430 | Public API: `register_*`, `on_*`, `notify_*`, `plugin_settings`, `Field`, `register_settings_schema` |
| `signals.py`          |  ~85 | `SignalKind` + `dispatch()` for plugin lifecycle handlers |
| `fence.py`            |  ~95 | `PluginFenceExtension` markdown extension |
| `editor_integration.py` | ~625 | Menu/palette/panel injection + live disable + cluster ordering |
| `scoped_settings.py`  | ~100 | `PluginSettings` dict-like façade |
| `document_handle.py`  | ~140 | Qt-free `DocumentHandle` (with opt-in escape hatches) |
| `reload.py`           |  ~90 | Discover-only "Reload plugins" diff helper |

The public shim lives one level up at `src/markdown_editor/plugins/__init__.py` and re-exports the stable surface.

### `builtin_plugins/`

Reserved for plugins shipped with the editor. **Currently empty** — nothing is bundled by default. The loader still scans this directory at startup, so dropping a plugin package here makes it a built-in again.

The reference plugins that used to live here are now under [`docs/plugins-examples/`](../../../docs/plugins-examples/) (`em_dash_to_hyphen`, `wordcount`, `stamp`); the test suite carries self-contained copies under `tests/markdown6/fixtures/plugins/`.

### `extensions/`

| File | Lines | Purpose |
|------|------:|---------|
| `callouts.py`     | 224 | GitHub `> [!NOTE]` + admonition `!!!` styling |
| `diagrams.py`     | 260 | Mermaid + Graphviz code-fence processors (cached) |
| `lists.py`        | 123 | Breakless lists + task lists |
| `logseq.py`       | 127 | Logseq-flavoured markdown cleanup |
| `math.py`         | 101 | `$…$` / `$$…$$` math blocks with KaTeX/MathJax |
| `source_lines.py` | 103 | `data-source-line` attrs for editor↔preview scroll sync |
| `wikilinks.py`    |  49 | `[[target]]` / `[[target|display]]` |

### `templates/`

| File | Lines | Purpose |
|------|------:|---------|
| `preview.py` | 332 | HTML preview page templates |

## Testing

Tests live in `tests/markdown6/` and use **pytest** + **pytest-qt**. External tools (pandoc, graphviz, mmdc) are mocked. Plugin-system tests are spread across ~25 `test_plugin_*.py` modules covering metadata parsing, the loader, document handle atomicity, every extension point, the Settings → Plugins UI, the notification drawer, and end-to-end failure-mode walks.

`tests/markdown6/conftest.py` provides an autouse `ephemeral_settings` fixture that resets the global `AppContext` with `ephemeral=True` before each test, so tests never touch the user's real `~/.config/markdown-editor/` files. Widget tests use the `qtbot` fixture.

Run the full suite:

```bash
pytest tests/markdown6/ -p no:xdist
```

Run a single module or test:

```bash
pytest tests/markdown6/test_export_service.py
pytest tests/markdown6/test_export_service.py::TestMarkdownToHtml::test_basic_conversion
```

(Never use `-q` or truncate the output — see the rule in top-level `CLAUDE.md`.)

Example unit test for a stateless service:

```python
# tests/markdown6/test_export_service.py
from markdown_editor.markdown6 import export_service

def test_markdown_to_html():
    html = export_service.markdown_to_html("# Hello", "Test")
    assert "<h1>Hello</h1>" in html
```

## Dependencies

Core runtime (from `pyproject.toml`):
- `PySide6 >= 6.5` — Qt bindings
- `PySide6-Addons >= 6.5` — WebEngine for preview
- `markdown >= 3.5` — Markdown parsing
- `Pygments >= 2.0` — syntax highlighting
- `weasyprint >= 60.0` — PDF export fallback
- `python-docx >= 1.0` — DOCX export fallback
- `graphviz >= 0.20` — Python bindings for Graphviz
- `pydantic >= 2.0` — data models and validation
- `email-validator` — dependency of pydantic's `EmailStr`
- `argcomplete >= 3.0` — shell tab-completion for `mde`

Dev extras (`pip install -e ".[dev]"`):
- `pytest >= 7.0`
- `pytest-qt >= 4.0`

Optional system tools (configurable paths in Settings → Tools):
- `pandoc` + `texlive-xetex` — high-quality PDF/DOCX export
- `graphviz` (`dot`) — native Graphviz rendering
- `@mermaid-js/mermaid-cli` (`mmdc`) — native Mermaid rendering
