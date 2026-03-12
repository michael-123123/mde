# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`fun` is a feature-rich Qt6 Markdown editor (PySide6) with live preview, wiki links, project management, and export to HTML/PDF/DOCX. Python 3.11+ required.

## Commands

```bash
# Install in development mode (from repo root)
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"

# Run the editor
markdown-editor        # full command
mde                    # short alias
mde /path/to/file.md   # open a file

# Run all markdown6 tests
pytest tests/markdown6/

# Run a single test file
pytest tests/markdown6/test_export_service.py

# Run a specific test
pytest tests/markdown6/test_export_service.py::TestMarkdownToHtml::test_basic_conversion
```

No linter, formatter, or CI pipeline is configured.

## Architecture

Widget-based architecture using Qt signal/slot for inter-component communication. No formal MVC — UI and logic are mixed in widget classes.

### Core Components

**MarkdownEditor** (`markdown_editor.py`) — QMainWindow. Main window owning menus, toolbar, tab widget, and sidebar. Coordinates all panels, file operations, export, and shortcuts. This is the largest file (~2800 lines) and the primary integration point.

**DocumentTab** (`markdown_editor.py:426-638`) — Container for a single open document. Holds an EnhancedEditor, a preview pane (QWebEngineView with QTextBrowser fallback), find/replace bar, and a splitter. Tracks `file_path` and `unsaved_changes`.

**EnhancedEditor** (`enhanced_editor.py`) — QPlainTextEdit subclass. The text editing widget with syntax highlighting, line numbers, code folding, auto-pairs, wiki-link completion, Ctrl+click link navigation, and zoom.

**Sidebar** (`sidebar.py`) + **ActivityBar** (`activity_bar.py`) — VSCode-style sidebar with vertical emoji-tab activity bar containing panels (Project, Outline, Search, References).

**Settings** (`settings.py`) — Singleton (`get_settings()`) managing ~20 settings and ~62 keyboard shortcuts. JSON persistence to `~/.config/markdown-editor/`. Emits `settings_changed`, `shortcut_changed`, `theme_changed` signals.

**Theme** (`theme.py`) — `ThemeColors` dataclass and `StyleSheets` class with factory methods (`dialog()`, `button()`, etc.). Access via `get_theme(dark_mode)`.

### Panels

- **ProjectPanel** (`project_manager.py`) — File tree, project export dialog
- **OutlinePanel** (`outline_panel.py`) — Heading-based document structure
- **ReferencesPanel** (`references_panel.py`) — Backlinks to current document
- **SearchPanel** (`search_panel.py`) — Project-wide regex search
- **CommandPalette** (`command_palette.py`) — Ctrl+Shift+P command access

### Services (stateless modules)

- **export_service.py** — `export_html()`, `export_pdf()`, `export_docx()`, `has_pandoc()`
- **graphviz_service.py** — Graphviz rendering with caching
- **markdown_extensions.py** — `CalloutExtension`, `CodeBlockPreprocessor`

### Key Patterns

**Theme propagation:** Every themed widget stores `self.settings = get_settings()`, connects to `settings_changed`, and implements `_apply_theme()` that reads the current theme and applies stylesheets.

**Adding a panel:** Create a QWidget subclass with signals, add it to the sidebar in `MarkdownEditor._init_ui()`, and connect its signals in MarkdownEditor.

**Adding a shortcut:** Add default in `settings.py` `DEFAULT_SHORTCUTS`, create the action in `_create_menu_bar()`, and register it in `_init_command_palette()`.

**Link detection regexes:** Wiki links `[[target|display]]`, Markdown links `[text](url)`, bare URLs `https?://...`. Duplicated in EnhancedEditor and ReferencesPanel.

## Testing

Uses **pytest** + **pytest-qt**. Tests are in `tests/markdown6/` (13 test modules).

The `conftest.py` provides an autouse `ephemeral_settings` fixture that resets the Settings singleton with `ephemeral=True` before each test, preventing reads/writes to user config. When writing new tests, this happens automatically — no manual setup needed.

Widget tests use `qtbot` from pytest-qt. External tools (pandoc, graphviz) are mocked in tests.

## Known Technical Debt

- `MarkdownEditor` is ~2800 lines; should be split into TabManager, PanelManager, ActionManager
- No model layer — document state lives in DocumentTab UI widget
- Settings is a global singleton (hard to test); should use dependency injection
- Theme application code (`_apply_theme()`) is duplicated across ~10 widget classes
- Link detection regex duplicated between EnhancedEditor and ReferencesPanel
