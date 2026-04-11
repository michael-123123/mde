# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`markdown-editor` is a feature-rich Qt6 Markdown editor (PySide6) with live preview, wiki links, project management, and export to HTML/PDF/DOCX. Python 3.11+ required.

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
# pytest-xdist is installed — on first test run, check if it's available
# (python -c "import xdist"), and if so use -n4 for all subsequent runs.

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

**AppContext** (`app_context.py`) — Application context facade (`get_app_context()`) managing settings, shortcuts (via `ShortcutManager`), and session state (via `SessionState`). JSON persistence to `~/.config/markdown-editor/`. Emits `settings_changed`, `shortcut_changed`, `theme_changed` signals. Injected into widgets via constructor `ctx` parameter.

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

**Theme propagation:** Every themed widget receives `ctx` (AppContext) via constructor, connects to `ctx.settings_changed`, and implements `_apply_theme()` that reads the current theme and applies stylesheets.

**Adding a panel:** Create a QWidget subclass with signals, add it to the sidebar in `MarkdownEditor._init_ui()`, and connect its signals in MarkdownEditor.

**Adding a shortcut:** Add default in `shortcut_manager.py` `DEFAULT_SHORTCUTS`, create the action in `_create_menu_bar()`, and register it in `_init_command_palette()`.

**Link detection regexes:** Wiki links `[[target|display]]`, Markdown links `[text](url)`, bare URLs `https?://...`. Duplicated in EnhancedEditor and ReferencesPanel.

## Testing

Uses **pytest** + **pytest-qt**. Tests are in `tests/markdown6/` (13 test modules).

The `conftest.py` provides an autouse `ephemeral_settings` fixture that resets the global AppContext with `ephemeral=True` before each test, preventing reads/writes to user config. When writing new tests, this happens automatically — no manual setup needed.

Widget tests use `qtbot` from pytest-qt. External tools (pandoc, graphviz) are mocked in tests.

## Bug Fixes

Follow this process strictly when fixing bugs:

1. **Reproduce first.** Before writing any fix, write a test (or run a manual reproduction) that demonstrates the bug. You must see it fail. If you cannot reproduce the bug, do not proceed with a fix — investigate further or ask for clarification.
2. **Write a regression test.** The test must fail before the fix and pass after. This is non-negotiable.
3. **Fix the bug.** Identify the root cause and fix it. Commit messages should explain *why* the bug happened, not just what changed.
4. **Verify the fix.** After applying the fix, reproduce the original bug scenario again. If the bug is still reproducible, the fix is not done — do not report it as fixed. Run the regression test and any related tests to confirm they pass.

Do not skip steps. Do not claim a bug is fixed without completing step 4.

## Changelog

`CHANGELOG.md` is maintained at the repo root. When tagging a new release (`vX.Y.Z`), summarize all commits since the previous tag into a new entry at the top of the changelog. Use the sections `Added`, `Changed`, `Fixed`, `Removed`, `Deprecated` — only include sections that apply. Entries should be user-facing descriptions, not implementation details. When reviewing commits for changelog entries, exclude changes to `CHANGELOG.md` itself from consideration — only look at the non-changelog parts of each diff.

## Known Technical Debt

- `MarkdownEditor` is ~2800 lines; should be split into TabManager, PanelManager, ActionManager
- No model layer — document state lives in DocumentTab UI widget
- ~~Settings is a global singleton (hard to test); should use dependency injection~~ (resolved: AppContext with DI)
- Theme application code (`_apply_theme()`) is duplicated across ~10 widget classes
- Link detection regex duplicated between EnhancedEditor and ReferencesPanel
