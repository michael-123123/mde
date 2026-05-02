# Changelog

All notable changes to markdown-editor are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.15] - 2026-05-03

### Added

- **Per-language syntax highlighting inside fenced code blocks.** The editor now colours the body of a fenced code block according to its language tag, for any language Pygments supports — Python, JavaScript, Rust, Go, C/C++, Java, C#, Ruby, PHP, YAML, JSON, HTML, CSS, SQL, TOML, Bash, Haskell, Lisp, OCaml, Elixir, Kotlin, Swift, Lua, R, Julia, Dart, Nim, Zig, Clojure, Prolog, Scheme, Fortran, Haml, Slim, Pug, Sass, Terraform, Crystal, Makefile, Dockerfile, Erb, and many more.
- Multi-line constructs (Python docstrings, Rust nested `/* */`, JS template literals, Prolog block comments) carry their state across editor blocks via per-line state checkpointing against Pygments' state machines.
- Editor and preview share a single Pygments colour scheme per theme (`default` for light, `monokai` for dark), so source-code colouring is consistent on both sides.
- New `examples/SYNTAX_HIGHLIGHTING.md` showcase file with sections for 47 languages, including multi-line state and unknown-language fallback.

### Fixed

- **Nested list indentation.** Lists using 2-space (unordered) or 3-space (ordered) indentation now nest properly in the preview instead of collapsing to flat siblings.
- **Strikethrough.** `~~text~~` now renders as `<del>text</del>` in the preview.
- **Preview light-mode code colouring.** Light-mode previews previously used the dark `github-dark` Pygments style on a light background, washing out code. Now uses `default` to match the editor.
- **Diagram-injection race.** Graphviz / Mermaid diagrams could be permanently dropped if their render workers completed before the preview page finished loading (all 10 graphviz diagrams in `examples/DIAGRAMS.md` were affected). Diagram injections now go through an event-driven queue gated on `loadFinished`, with at most one `runJavaScript` outstanding at any moment. Stale-generation entries are discarded inline.

## [0.1.14] - 2026-04-23

### Added

- **Plugin system.** Drop-in Python plugins extend the editor with menu items, sidebar panels, custom export formats, fenced-code renderers, lifecycle handlers, and auto-rendered configuration UIs. Plugins live in `<config_dir>/plugins/<name>/` and ship as a `<name>.py` + `<name>.toml` directory. Public API at `from markdown_editor.plugins import …`. See [`docs/plugins.md`](docs/plugins.md) for the authoring guide and [`docs/plugin-api-versioning.md`](docs/plugin-api-versioning.md) for the stability contract.
- **Extra plugin directories** layer on top of the user dir: pass `--plugins-dir DIR` (repeatable) on the command line or manage a persistent list via **Settings → Plugins → Extra plugin directories**. Useful for per-project plugin sets without copying into the user config.
- **Settings → Plugins tab** lists every discovered plugin with status, enable/disable toggle, ℹ Info dialog (metadata + README), Open plugins folder, and Reload plugins buttons. Plugins with a registered settings schema get an auto-generated Configure… dialog.
- **🔔 Notifications drawer** in the status bar. Plugin runtime errors and plugin-authored notifications surface here without blocking the editor; click the bell to see history.
- **Three example plugins** under [`docs/plugins-examples/`](docs/plugins-examples/) - `em_dash_to_hyphen` (text transform), `wordcount` (sidebar panel + signals + scoped settings), `stamp` (action + every settings-schema field type). Not bundled - copy into your user plugin folder, or run `mde --plugins-dir docs/plugins-examples` to try them in place.
- Preview pane now responds to scroll keys (PageUp/PageDown, arrow keys, Home/End, Space/Shift+Space) by forwarding them to the editor, matching existing wheel-forwarding behaviour. Scrolling either pane keeps the two in sync.

### Changed

- Emit a startup error log when QtWebEngine is unavailable. Without it, the preview silently falls back to QTextBrowser and loses diagrams, math, rich CSS, and code-block copy buttons; the new log surfaces the degradation instead of leaving users to guess.

### Fixed

- The tab dirty flag could remain set after the user undid every change back to the file's on-disk contents. The tab now reflects the editor's actual modified state via the underlying document.

## [0.1.13] - 2026-04-21

### Added
- Pre-built binaries shipped on every GitHub release:
  - `MarkdownEditor-<version>-x86_64.AppImage` - Linux AppImage (static runtime - no libfuse2 dependency on Ubuntu 24+)
  - `MarkdownEditor-<version>-x86_64.exe` - Windows portable onefile
  - `MarkdownEditor-<version>-x86_64-setup.exe` - Windows installer (Start Menu shortcut, uninstaller, optional "add to PATH" and ".md file association")
  - `MarkdownEditor-<version>-x86_64-portable.zip` - Windows portable dist (unzip and run)
- `install-desktop` / `install-autocomplete` CLI subcommands detect when invoked from a Nuitka-compiled binary and register the absolute bundled-binary path with the OS

### Fixed
- `mde graph -o output.svg` truncated one character from the output filename (off-by-one in extension stripping)

## [0.1.12] - 2026-04-19

### Added
- Copy-to-clipboard button on code blocks in the preview
- Copy-to-clipboard button on rendered mermaid/graphviz diagrams - copies the original source back to the clipboard
- CLI `mde export` now accepts `--theme {light,dark}` and `--canonical-fonts` flags
- New `examples/DIAGRAMS.md` showcasing richer mermaid and graphviz samples

### Changed
- Unified HTML export pipeline: GUI File→Export, CLI `mde export`, project export, and WeasyPrint PDF all now use the same preview-grade renderer. Exports finally honour wiki links, callouts, math, mermaid, graphviz, task lists, and Logseq cleanup instead of the previous stripped-down output
- Code-block copy button uses larger inline-SVG icons
- Consolidated README into the repo root; example content moved under `examples/`

### Fixed
- Initial file open could leave diagrams stuck on "Rendering…" placeholders (duplicate-render race against the asynchronous page load in the preview)
- `mde export -f html` shipped unrendered "Rendering…" placeholders instead of SVGs for any diagram
- Graphviz diagrams in dark mode painted light-grey text on user-chosen pastel fill colours, making labels unreadable; text inside user-filled nodes now uses dark colour for contrast
- Broken `via.placeholder.com` image URLs in the examples replaced with `placehold.co`

## [0.1.11] - 2026-04-15

### Added
- Data-driven action registry with platform-aware shortcut defaults
- Copy and select-all support in the preview pane (Ctrl+C / Ctrl+A)

### Changed
- Extracted DocumentTab into `components/document_tab.py`
- Extracted preview HTML templates into `templates/preview.py`
- Moved editor UI components (table editor, graph export, find/replace) into `components/` package
- Moved inline CSS from widget classes into centralized StyleSheets methods
- Added `preview_blockquote` and `preview_heading_border` to ThemeColors

### Fixed
- Ctrl+C and Ctrl+A always targeting the editor even when the preview pane had focus

## [0.1.10] - 2026-04-12

### Added
- Admonition-style callout support (`!!!` syntax)
- `get_theme_from_ctx()` helper to eliminate theme boilerplate
- Atomic writes for config persistence

### Changed
- Extracted FindReplaceBar into its own module
- Moved ThreadPoolExecutor from module scope to MarkdownEditor instance
- Parented all QTimers to their owning widget to prevent leak warnings

## [0.1.9] - 2026-04-11

### Added
- Bidirectional scroll sync - scrolling the preview now scrolls the editor
- Logging infrastructure across all modules for diagnostics

### Changed
- Settings architecture refactored into AppContext with dependency injection
- Markdown extensions split into individual modules under `extensions/` subpackage
- "Preview Typography" settings tab renamed to "Appearance"

### Fixed
- Math (KaTeX) and Mermaid diagrams not rendering in saved files due to CDN blocking
- Theme change incorrectly marking documents as having unsaved changes
- Deprecated Qt `setFontFamily` API replaced with `setFontFamilies`
- WebEngine page cleanup warnings during test runs

## [0.1.7] - 2026-04-11

### Added
- Preview Typography settings tab with per-element font control
- Scroll-past-end feature for the editor

## [0.1.5] - 2026-04-11

### Added
- Autosave timer that saves dirty tabs on a configurable interval

### Fixed
- Diagram rendering inside nested fenced code blocks
- Duplicate autosave trigger in EnhancedEditor

## [0.1.4] - 2026-04-05

### Removed
- Leftover PyQt5 dependencies that conflict with PySide6

## [0.1.3] - 2026-04-02

### Changed
- Replace modal file-changed dialog with non-modal notification bar
- Replace proportional scroll sync with source-line mapping

## [0.1.2] - 2026-03-29

### Added
- Windows and macOS desktop integration for install-desktop command
- "Show hidden files" setting to control dotfile visibility globally

### Changed
- Replace flat file lists with tree view in export dialogs

## [0.1.1] - 2026-03-29

### Added
- Persist file explorer expanded directories across restarts
- Persist sidebar collapsed/expanded state and active panel across restarts
- Dual-pane find/replace bar spanning both editor and preview

### Fixed
- Preview scroll jump when toggling editor/preview visibility

## [0.1.0] - 2026-03-24

Initial tagged release.

### Added
- GitHub Actions workflow to build and release on version tags
- User-facing README with features, usage, and examples
- MIT license
