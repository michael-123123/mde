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
pytest tests/markdown6/ -p no:xdist

# Run a single test file
pytest tests/markdown6/test_export_service.py

# Run a specific test
pytest tests/markdown6/test_export_service.py::TestMarkdownToHtml::test_basic_conversion
```

No linter, formatter, or CI pipeline is configured.

**pytest rules:** Never use `-q` (quiet mode). Don't truncate output (no `| tail`, `| head`, etc.) unless you have a specific reason to.

## Optional System Dependencies

These are native binaries (not pip-installable) that the editor detects at runtime and uses for best quality. All have pip-installable fallbacks, so the editor works without them — just with reduced output quality.

- **pandoc** — best-in-class HTML/PDF/DOCX export (esp. with LaTeX math via `texlive-xetex`). Fallback: `weasyprint` for PDF, `python-docx` for DOCX.
  - Ubuntu/Debian: `sudo apt install pandoc texlive-xetex`
  - macOS: `brew install pandoc`
  - Windows: `choco install pandoc`
- **graphviz** — server-side `dot` rendering for graph diagrams. Fallback: graph source is shown verbatim.
  - Ubuntu/Debian: `sudo apt install graphviz`
  - macOS: `brew install graphviz`
  - Windows: `choco install graphviz`
- **mmdc** (Mermaid CLI) — server-side mermaid diagram rendering. Fallback: client-side `mermaid.js` in the preview.
  - All platforms: `npm install -g @mermaid-js/mermaid-cli` (requires Node.js)

User-configured tool paths take precedence over `PATH`; see `tool_paths.py`.

## Building a Standalone Binary

The editor can be bundled into distributable binaries via `pyside6-deploy` + Nuitka. Three build paths exist, one per target platform. All build output lands under `build/` (gitignored). Tracked inputs live in `packaging/` — build scripts, Nuitka spec files, launcher, installer script. Scripts never mutate their tracked inputs; they stage copies into `$BUILD_DIR` and patch those.

### Python-side build dependencies (shared)

```bash
pip install -e ".[build]"   # Nuitka + patchelf (Linux-only via marker)
```

### External dependencies per build path

Each script's header is the authoritative list; the table here is a summary so newcomers know what they're getting into before running anything.

| Path | Script | External tools (not auto-installed by script) | Tools auto-downloaded to `$BUILD_DIR/.tools/` |
|---|---|---|---|
| Linux → AppImage | `packaging/build.sh --appimage` | C toolchain (`build-essential`). Qt6 runtime libs at build time if the bundled AppImage should be fully self-contained (`libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libfontconfig1 libdbus-1-3`). | `appimagetool` + AppImage static `runtime-x86_64` |
| Windows (real) | `packaging/build-windows-native.sh` | Python 3.12 + Git Bash (for running the script) + a C toolchain (GHA runners have MSVC 2022 preinstalled; dev boxes need it via Visual Studio Build Tools). | — (Nuitka auto-downloads `depends.exe`; we pass `--assume-yes-for-downloads`) |
| Windows via Wine (Linux) | `packaging/build-windows.sh` | **Wine** (`apt install wine64`) + `curl`/`wget`. | `winetricks`, `python-3.12.7-amd64.exe` installer, `depends22_x86.zip` (Wine-specific depends.exe fix), `icu4c-73_2-Win64-MSVC2019.zip` |
| Windows installer | `packaging/make-installer-windows.sh` | **NSIS** 3.x (`apt install nsis` on Linux; native Windows has `choco install nsis`). Works from either a Wine-built or native-built standalone dist. | — |

### Commands

```bash
# --- Linux AppImage -------------------------------------------------
bash packaging/build.sh --appimage             # standalone + AppImage
bash packaging/build.sh                        # onefile .bin, no AppImage
bash packaging/build.sh --build-dir=/tmp/out   # redirect output dir

# --- Windows .exe (real Windows or GHA `windows-latest`) -----------
bash packaging/build-windows-native.sh                  # onefile (default)
bash packaging/build-windows-native.sh --mode=standalone

# --- Windows .exe (Linux host via Wine, for fast local iteration) --
bash packaging/build-windows.sh --mode=standalone       # then wrap with installer
bash packaging/build-windows.sh                         # onefile, --smoke-test optional

# --- Windows installer (wraps either Wine- or native-built dist) ---
bash packaging/make-installer-windows.sh \
    --dist-dir=build/win/deployment/mde_launch.dist   # or build/mde.dist from native
```

CI: `.github/workflows/build-linux.yml` (Ubuntu 22.04) and `.github/workflows/build-windows.yml` (Windows Server 2022) mirror these scripts.

**Notes:**
- On conda/mamba envs, Nuitka requires either `conda install libpython-static` or `--static-libpython=no` in the spec's `extra_args`.
- `mode = standalone` produces a dist folder; `mode = onefile` produces a single self-extracting binary. The installer wraps standalone.
- External **runtime** tools (pandoc, graphviz, mmdc) are **not** bundled — they remain optional runtime deps with pip-installable fallbacks (see "Optional System Dependencies" above).
- Cap parallel compiler jobs at `floor(nproc / 2)` on dev machines (default in scripts) so the build doesn't clobber CPU for interactive work. CI workflows override to `--jobs=$(nproc)` since nothing else runs there.

### Verifying a bundled binary

After any Nuitka/pyside6-deploy rebuild, **compare screenshots of the bundled binary against the equivalent source launch**. The source launch is the ground truth; a bundled binary can silently drop assets (icons, fonts, stylesheets, plugin-registered lexers) in ways only a visual diff catches.

Minimal check:

```bash
# Capture source launch (reference)
mde /path/to/some.md &  SRC_PID=$!
sleep 5 && import -window root local/tmp/mde_source.png
kill $SRC_PID

# Capture bundled launch
build/mde.dist/mde_launch.bin /path/to/some.md &  BIN_PID=$!
sleep 5 && import -window root local/tmp/mde_bundled.png
kill $BIN_PID

# Then inspect both images (and diff if possible)
```

Any difference in icons, panel layout, theme, or syntax highlighting is a bundling miss — investigate before declaring the binary good.

## Architecture

Widget-based architecture using Qt signal/slot for inter-component communication. No formal MVC — UI and logic are mixed in widget classes. Source lives under `src/markdown_editor/markdown6/` with subpackages `app_context/`, `components/`, `extensions/`, `plugins/`, `builtin_plugins/`, and `templates/`. The public plugin API shim lives one level up at `src/markdown_editor/plugins/`.

### Core Components

**MarkdownEditor** (`markdown_editor.py`) — QMainWindow. Main window owning menus, toolbar, tab widget, and sidebar. Coordinates all panels, file operations, export, and shortcuts. The primary integration point (~1800 lines).

**DocumentTab** (`components/document_tab.py`) — Container for a single open document. Holds an `EnhancedEditor`, a preview pane (QWebEngineView with QTextBrowser fallback), find/replace bar, external-change bar, and a splitter. Tracks `file_path` and `unsaved_changes`, drives markdown rendering, async diagram rendering, and source-line scroll sync.

**EnhancedEditor** (`enhanced_editor.py`) — QPlainTextEdit subclass. Text editing widget with syntax highlighting, line numbers, code folding, auto-pairs/auto-indent, wiki-link completion, Ctrl+click link navigation, snippet expansion, image paste, and zoom.

**Sidebar** (`components/sidebar.py`) + **ActivityBar** (`components/activity_bar.py`) — VSCode-style sidebar: vertical emoji-tab activity bar toggles a collapsible tool window containing panels (Project, Outline, Search, References).

**Actions registry** (`actions.py`) — Data-driven single source of truth for menus, shortcuts, and command palette. `MENU_STRUCTURE` is a list of `MenuDef`/`SubmenuDef`/`ActionDef` entries; `build_menu_bar()`, `apply_shortcuts()`, and `build_command_palette()` wire everything up from it. `PALETTE_ONLY` adds palette-only commands.

**AppContext** (`app_context/`) — Package containing the application context facade (`get_app_context()`, `init_app_context()`). Owns:
- `settings_manager.py` — user preferences (theme, editor, preview, tools, etc.), atomic JSON writes
- `shortcut_manager.py` — keyboard shortcut defaults (50+ actions) with platform-aware defaults, JSON persistence
- `session_state.py` — recent files, open tabs, last project path, sidebar state
Emits `settings_changed`, `shortcut_changed`, `theme_changed` signals. JSON persistence to `~/.config/markdown-editor/`. Injected into widgets via constructor `ctx` parameter.

**Theme** (`theme.py`) — `ThemeColors` dataclass with `DARK_THEME` / `LIGHT_THEME` instances, and `StyleSheets` class with factory methods (`dialog()`, `button()`, `editor()`, `menu_bar()`, `tab_widget()`, `popup()`, etc.). Access via `get_theme(dark_mode)` or `get_theme_from_ctx(ctx)`.

### Panels (all in `components/`)

- **ProjectPanel** (`project_manager.py`, top-level) — File tree with lazy loading, filter search, and context menu
- **OutlinePanel** (`components/outline_panel.py`) — Heading-based document structure
- **ReferencesPanel** (`components/references_panel.py`) — Backlinks and forward links for the current document
- **SearchPanel** (`components/search_panel.py`) — Project-wide regex search with jump-to-match
- **CommandPalette** (`components/command_palette.py`) — Ctrl+Shift+P command access, built from the actions registry

### Dialogs / other components

- **SettingsDialog** (`components/settings_dialog.py`) — Multi-page settings (Editor, View, Preview/Appearance, Files, Tools, Keyboard)
- **GraphExportDialog** (`components/graph_export.py`) — Document link graph visualisation with layout engines (dot/neato/fdp/…), exports SVG/PNG/PDF
- **TableEditorDialog** (`components/table_editor.py`) — Visual table builder (Ctrl+Shift+T)
- **FindReplaceBar** (`components/find_replace_bar.py`) — Find/replace toolbar spanning editor and preview
- **ExternalChangeBar** (`components/external_change_bar.py`) — Non-modal notification bar when a file is modified externally

### Services (stateless modules)

- **export_service.py** — `markdown_to_html()`, `export_html()`, `export_pdf()`, `export_docx()`, `has_pandoc()`
- **graphviz_service.py** — `render_dot()` with in-memory MD5 cache; `has_graphviz()`
- **mermaid_service.py** — `render_mermaid()` with in-memory MD5 cache; `has_mermaid()`; falls back to client-side mermaid.js when `mmdc` is not available
- **tool_paths.py** — `get_pandoc_path()` / `get_dot_path()` / `get_mmdc_path()` + their `has_*` counterparts (user-configured path in settings → PATH lookup)
- **logger.py** — colored `getLogger()` / `setup()` under an `mde` namespace
- **temp_files.py** — tracked temp files/dirs (auto-cleaned on exit) and `atomic_write()` (used for config persistence)
- **snippets.py** — `Snippet`, `SnippetManager`, `SnippetPopup` (Ctrl+J)
- **syntax_highlighter.py** — `MarkdownHighlighter` with dark/light theme switching
- **file_tree_widget.py** — reusable checkbox file-tree widget (used by export and graph dialogs)
- **templates/preview.py** — HTML preview page templates (full and simple)

### Markdown extensions

Extensions live in the `extensions/` subpackage. The package's `__init__.py` re-exports the public API from each module, so callers can `from markdown_editor.markdown6.extensions import MermaidExtension, ...`.

- `callouts.py` — `CalloutExtension` (supports both GitHub `> [!NOTE]` and admonition `!!! note` syntaxes)
- `diagrams.py` — `MermaidExtension`, `GraphvizExtension` with caching and async placeholder support
- `lists.py` — `BreaklessListExtension`, `TaskListExtension`
- `logseq.py` — `LogseqExtension` (cleans up Logseq-specific syntax for preview)
- `math.py` — `MathExtension` (KaTeX/MathJax markers for `$…$` and `$$…$$`)
- `source_lines.py` — `SourceLineExtension` (emits `data-source-line` attributes for editor↔preview scroll sync)
- `wikilinks.py` — `WikiLinkExtension` (`[[target]]` / `[[target|display]]`)

### Plugin system

Plugins extend the editor without core changes. Discovery scans builtin (`markdown6/builtin_plugins/`) and user (`<config_dir>/plugins/`) directories; plugins ship as `<name>/<name>.py` + `<name>/<name>.toml` directories. Six extension points + lifecycle signals + scoped settings + auto-rendered Configure dialog from a declarative `Field` schema. Errors never crash the editor — they show up in Settings → Plugins (errored plugins) or the bell drawer in the status bar (runtime errors).

For full plugin authoring documentation, see [`docs/plugins.md`](docs/plugins.md). For the API stability contract, see [`docs/plugin-api-versioning.md`](docs/plugin-api-versioning.md). Read the bundled `em_dash_to_hyphen` / `wordcount` / `stamp` plugins under `markdown6/builtin_plugins/` for working code.

Plugin-system architecture (under `markdown6/plugins/`):

- `metadata.py` — `[tool.mde.plugin]` TOML parser
- `loader.py` — discovery + dep check + import (never raises)
- `plugin.py` — `Plugin` dataclass + `PluginStatus` / `PluginSource` enums
- `registry.py` — record dataclasses + central `PluginRegistry`
- `api.py` — public API: `register_*`, `on_*`, `notify_*`, `plugin_settings`, `Field`, `register_settings_schema`
- `signals.py` — lifecycle signal dispatch
- `fence.py` — markdown extension that dispatches plugin fences
- `editor_integration.py` — menu/palette injection, panel installation, live disable/enable
- `scoped_settings.py` — `PluginSettings` dict-like façade backed by `plugins.<id>.<key>`
- `document_handle.py` — Qt-free `DocumentHandle` plugins receive
- `reload.py` — discover-only "Reload plugins" diff helper

Plugin runtime errors route into `markdown6/notifications.py:NotificationCenter` (one per `AppContext`) and surface via `components/notification_bell.py` (status bar). The Settings → Plugins page lives in `components/plugins_page.py` with `components/plugin_configure_dialog.py` and `components/plugin_info_dialog.py` as supporting modals.

**Important rule for plugin code:** plugin authors should import from `markdown_editor.plugins` (the shim) — *not* from `markdown_editor.markdown6.plugins.*` (the internal namespace). Same rule applies to bundled plugins under `builtin_plugins/`. The shim re-exports the stable surface; reaching past it forfeits stability guarantees.

### CLI

**markdown_editor_cli.py** — `mde` entry point. Subcommands: `export`, `graph`, `stats`, `validate`, `install-desktop` / `uninstall-desktop`, `install-autocomplete` / `uninstall-autocomplete`. Bare `mde` (with optional file paths) launches the GUI.

### Key Patterns

**Theme propagation:** Every themed widget receives `ctx` (AppContext) via constructor, connects to `ctx.settings_changed`, and implements `_apply_theme()` that reads the current theme (via `get_theme_from_ctx(ctx)`) and applies stylesheets.

**Adding a panel:** Create a QWidget subclass under `components/` with signals, add a tab to `ActivityBar` and a page to `Sidebar`'s stacked widget in `MarkdownEditor._init_ui()`, and connect its signals in `MarkdownEditor`.

**Adding a menu item / shortcut / palette entry:** Add a single `ActionDef` to `MENU_STRUCTURE` (or to `PALETTE_ONLY` for palette-only entries) in `actions.py`. The menu, shortcut, and command-palette entry are all wired up automatically by `build_menu_bar()`, `apply_shortcuts()`, and `build_command_palette()`. Default shortcuts (with platform-aware `QKeySequence.StandardKey` on Ctrl+N, Ctrl+S, etc.) live in `app_context/shortcut_manager.py`.

**Adding a markdown extension:** Create a new module under `extensions/`, export the `Extension` class and any required pre/postprocessors, and add it to the `markdown.Markdown(extensions=[...])` list where the preview is rendered (in `components/document_tab.py`). Also add a re-export line to `extensions/__init__.py` so the extension is accessible from the package root.

**Adding a plugin (instead of editing core):** if a feature can be expressed as a plugin (custom action, sidebar panel, fence renderer, exporter, markdown extension, lifecycle handler), prefer that over a core change. See `docs/plugins.md` for the authoring guide. Bundled plugins under `markdown6/builtin_plugins/` are the canonical examples.

**Link detection regexes:** Wiki links `[[target|display]]`, Markdown links `[text](url)`, bare URLs `https?://...`. Duplicated in `EnhancedEditor` and `components/references_panel.py`.

## Testing

Uses **pytest** + **pytest-qt**. Tests are in `tests/markdown6/` (26 test modules).

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

## Merging to Master

Never merge branches into master directly via `git merge`. Always go through a GitHub PR:

1. Merge or rebase from master into the feature branch to ensure it's up to date. Resolve any conflicts.
2. Push the branch to origin.
3. Create a PR with `gh pr create`.
4. Approve the PR with `gh pr review --approve`. GitHub forbids approving your own PR — if you are the PR author, this step will fail with `Can not approve your own pull request`. That's expected on this single-author repo; skip the approval and continue to step 5.
5. Merge the PR with `gh pr merge --merge --delete-branch`.

The PR must only be approved and merged when the branch has a clean merge/rebase from master. This applies any time you are asked to merge to master/main.

## Known Technical Debt

- `MarkdownEditor` is ~1800 lines; could still be split into TabManager and PanelManager
- No model layer — document state lives in `DocumentTab` UI widget
- ~~Settings is a global singleton (hard to test); should use dependency injection~~ (resolved: `AppContext` with DI)
- ~~"Adding a shortcut" required edits in three places~~ (resolved: data-driven `actions.py` registry)
- ~~`DocumentTab` defined inside `markdown_editor.py`~~ (resolved: extracted to `components/document_tab.py`)
- Theme application code (`_apply_theme()`) is duplicated across ~10 widget classes
- Link detection regex duplicated between `EnhancedEditor` and `components/references_panel.py`
