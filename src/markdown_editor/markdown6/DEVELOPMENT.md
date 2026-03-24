# Markdown Editor - Development Guide

This document provides technical documentation for developers continuing work on this project.

## Architecture Overview

The application follows a loosely coupled widget-based architecture using Qt's signal/slot mechanism for communication. There is no formal MVC separation - UI and logic are mixed within widget classes.

```
┌─────────────────────────────────────────────────────────────────┐
│                      MarkdownEditor (QMainWindow)                │
│  - Main window, menus, toolbar, status bar                       │
│  - Tab management, file operations                               │
│  - Coordinates all panels and editor tabs                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌─────────────────────────────────────────┐  │
│  │  Side Panel  │  │              Tab Widget                  │  │
│  │  (QToolBox)  │  │  ┌─────────────────────────────────────┐│  │
│  │              │  │  │         DocumentTab (per file)      ││  │
│  │ ┌──────────┐ │  │  │  ┌─────────────┬─────────────────┐  ││  │
│  │ │ Project  │ │  │  │  │ Enhanced    │   Preview       │  ││  │
│  │ │  Panel   │ │  │  │  │ Editor      │   (WebEngine    │  ││  │
│  │ └──────────┘ │  │  │  │             │    or TextBrowser│  ││  │
│  │ ┌──────────┐ │  │  │  │ - Syntax HL │                 │  ││  │
│  │ │ Outline  │ │  │  │  │ - Folding   │                 │  ││  │
│  │ │  Panel   │ │  │  │  │ - Line nums │                 │  ││  │
│  │ └──────────┘ │  │  │  └─────────────┴─────────────────┘  ││  │
│  │ ┌──────────┐ │  │  └─────────────────────────────────────┘│  │
│  │ │References│ │  └─────────────────────────────────────────┘  │
│  │ │  Panel   │ │                                               │
│  │ └──────────┘ │                                               │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Key Classes

### Core Classes

#### `MarkdownEditor` (markdown_editor.py:640+)
The main window class. Responsibilities:
- Window layout, menus, toolbar, status bar
- Tab widget management (create, close, switch tabs)
- File operations (open, save, save as, recent files)
- Export operations (delegates to `export_service`)
- Command palette integration
- Keyboard shortcut management
- Theme application coordination

**Key methods:**
- `open_file(path)` - Opens file, checks for duplicates, creates tab
- `save_file()` / `save_file_as()` - Save operations
- `new_tab()` - Creates empty DocumentTab
- `update_window_title()` - Updates title with project-relative path
- `_handle_link_click(url)` - Handles preview link clicks
- `_handle_editor_link_click(path)` - Handles Ctrl+click on editor links

#### `DocumentTab` (markdown_editor.py:426-638)
A container widget for a single document. Contains:
- `EnhancedEditor` - The text editor
- Preview pane (QWebEngineView or QTextBrowser fallback)
- Find/Replace bar
- Splitter between editor and preview

**Key attributes:**
- `file_path: Path | None` - Current file path
- `unsaved_changes: bool` - Dirty state
- `editor: EnhancedEditor` - The text editor widget

**Signals:**
- `link_clicked(QUrl)` - Emitted when preview link is clicked

#### `EnhancedEditor` (enhanced_editor.py:127+)
The main text editor widget (QPlainTextEdit subclass). Responsibilities:
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

#### `ProjectPanel` (project_manager.py:47+)
File tree panel for project folder management.

**Signals:**
- `file_selected(str)` - Single click on file
- `file_double_clicked(str)` - Double click opens file

**Key methods:**
- `open_project(path)` - Opens folder as project
- `_show_export_dialog()` - Opens ProjectExportDialog

#### `OutlinePanel` (outline_panel.py:24+)
Document structure panel showing headings.

**Signals:**
- `heading_clicked(int)` - Line number of clicked heading

**Key methods:**
- `update_outline(text)` - Parses markdown and updates tree
- `_parse_headings(text)` - Extracts heading structure

#### `ReferencesPanel` (references_panel.py:29+)
Backlinks panel showing files that reference current document.

**Signals:**
- `file_clicked(str)` - File path clicked
- `reference_clicked(str, int)` - File path and line number

**Key methods:**
- `update_references(file_path, project_path)` - Scans for references
- `_find_references(file_path, project_path)` - Search logic

### Support Classes

#### `Settings` (settings.py:107+)
Singleton settings manager with JSON persistence.

**Signals:**
- `settings_changed(str, object)` - key, new_value
- `shortcut_changed(str, str)` - action, new_shortcut
- `theme_changed(str)` - theme name

**Access:** `from fun.markdown6.settings import get_settings`

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
from fun.markdown6.theme import get_theme, StyleSheets
theme = get_theme(dark_mode=True)
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
    → Settings.set(key, value)
    → settings_changed signal
    → All listening widgets receive and update
        → EnhancedEditor._on_setting_changed()
        → OutlinePanel._on_setting_changed()
        → etc.
```

### Theme Change
```
Settings.set("view.theme", "dark")
    → theme_changed signal
    → MarkdownEditor._on_theme_changed()
        → apply_application_theme(dark_mode)
        → Update all panels and dialogs
```

## Adding New Features

### Adding a New Panel

1. Create panel class in new file:
```python
# my_panel.py
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal

class MyPanel(QWidget):
    item_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self._init_ui()
        self._apply_theme()
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key, value):
        if key == "view.theme":
            self._apply_theme()
```

2. Add to MarkdownEditor._init_ui():
```python
self.my_panel = MyPanel()
my_page = QWidget()
my_layout = QVBoxLayout(my_page)
my_layout.setContentsMargins(0, 0, 0, 0)
my_layout.addWidget(self.my_panel)
self.side_toolbox.addItem(my_page, "MY PANEL")
```

3. Connect signals in MarkdownEditor:
```python
self.my_panel.item_clicked.connect(self._on_my_panel_item_clicked)
```

### Adding a New Keyboard Shortcut

1. Add default in settings.py DEFAULT_SHORTCUTS:
```python
"my_feature.action": "Ctrl+Shift+M",
```

2. Create action in MarkdownEditor._create_menu_bar():
```python
self.my_action = menu.addAction("My Action")
self.my_action.setShortcut(self.settings.get_shortcut("my_feature.action"))
self.my_action.triggered.connect(self._my_action_handler)
```

3. Add to command palette in MarkdownEditor._init_command_palette():
```python
commands.append(Command(
    "my_feature.action",
    "My Action Description",
    self.settings.get_shortcut("my_feature.action"),
    self._my_action_handler,
    "Category"
))
```

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

### Adding a New Markdown Extension

1. Create preprocessor/extension in markdown_extensions.py:
```python
class MyPreprocessor(Preprocessor):
    def run(self, lines):
        # Process lines
        return new_lines

class MyExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MyPreprocessor(md), 'my_ext', 25)
```

2. Add to markdown instance in MarkdownEditor.__init__():
```python
from .markdown_extensions import MyExtension
self.md = markdown.Markdown(extensions=[..., MyExtension()])
```

## Code Patterns

### Theme Application
All widgets that need theming should:
1. Store settings reference: `self.settings = get_settings()`
2. Connect to settings_changed signal
3. Implement `_apply_theme()` method
4. Call `_apply_theme()` in `__init__` and when theme changes

```python
def _on_setting_changed(self, key, value):
    if key == "view.theme":
        self._apply_theme()

def _apply_theme(self):
    theme = get_theme(self.settings.get("view.theme") == "dark")
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
1. **MarkdownEditor is too large** (~2600 lines) - Should extract:
   - TabManager for tab operations
   - PanelManager for side panel coordination
   - ActionManager for menu/shortcut handling

2. **No Model layer** - Document state is mixed with UI in DocumentTab

3. **Global settings singleton** - Makes testing difficult; should use dependency injection

4. **Duplicated theme handling** - Each widget implements its own `_apply_theme()`

### Code Duplication
1. Theme application code repeated in ~10 locations
2. Link detection regex duplicated in EnhancedEditor and ReferencesPanel
3. Similar panel initialization patterns repeated

### Potential Improvements
1. Extract signal hub for centralized event management
2. Create base ThemedWidget class to reduce duplication
3. Add proper Model layer for document state
4. Implement undo/redo framework
5. Add unit tests (currently none)

## File Reference

| File | Lines | Primary Class | Purpose |
|------|-------|---------------|---------|
| markdown_editor.py | ~2600 | MarkdownEditor, DocumentTab | Main window, tabs |
| enhanced_editor.py | ~1200 | EnhancedEditor | Text editor widget |
| settings.py | ~280 | Settings | Settings management |
| settings_dialog.py | ~450 | SettingsDialog | Settings UI |
| project_manager.py | ~500 | ProjectPanel, ProjectExportDialog | Project management |
| outline_panel.py | ~150 | OutlinePanel | Document outline |
| references_panel.py | ~230 | ReferencesPanel | Backlinks |
| syntax_highlighter.py | ~250 | MarkdownHighlighter | Syntax highlighting |
| theme.py | ~390 | ThemeColors, StyleSheets | Theming |
| export_service.py | ~200 | (module) | Export functions |
| command_palette.py | ~100 | CommandPalette | Command palette |
| snippets.py | ~400 | SnippetManager, SnippetPopup | Snippets |
| table_editor.py | ~200 | TableEditorDialog | Table editing |
| searchable_popup.py | ~110 | SearchablePopup | Base popup class |
| markdown_extensions.py | ~100 | CalloutExtension | Custom markdown |

## Testing

Currently no automated tests exist. To add tests:

1. Add pytest to dev dependencies (already in pyproject.toml)
2. Create tests/ directory
3. Use pytest-qt for widget testing

```python
# tests/test_export_service.py
from fun.markdown6 import export_service

def test_has_pandoc():
    # Returns bool, doesn't crash
    result = export_service.has_pandoc()
    assert isinstance(result, bool)

def test_markdown_to_html():
    html = export_service.markdown_to_html("# Hello", "Test")
    assert "<h1>Hello</h1>" in html
```

## Dependencies

Core runtime:
- PySide6 >= 6.5 (Qt bindings)
- PySide6-Addons >= 6.5 (WebEngine)
- markdown >= 3.5 (parsing)
- Pygments >= 2.0 (syntax highlighting)
- weasyprint >= 60.0 (PDF export)
- python-docx >= 1.0 (DOCX export)

Optional:
- pandoc (system) - Enhanced PDF/DOCX export with LaTeX support
