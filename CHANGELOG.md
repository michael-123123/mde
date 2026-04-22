# Changelog

All notable changes to markdown-editor are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Plugin system.** Drop-in Python plugins extend the editor with menu items, sidebar panels, custom export formats, fenced-code renderers, lifecycle handlers, and auto-rendered configuration UIs. Plugins live in `<config_dir>/plugins/<name>/` and ship as a `<name>.py` + `<name>.toml` directory. Public API at `from markdown_editor.plugins import …`. See [`docs/plugins.md`](docs/plugins.md) for the authoring guide and [`docs/plugin-api-versioning.md`](docs/plugin-api-versioning.md) for the stability contract.
- **Settings → Plugins tab** lists every discovered plugin with status, enable/disable toggle, ℹ Info dialog (metadata + README), Open plugins folder, and Reload plugins buttons. Plugins with a registered settings schema get an auto-generated Configure… dialog.
- **🔔 Notifications drawer** in the status bar. Plugin runtime errors and plugin-authored notifications surface here without blocking the editor; click the bell to see history.
- **Three bundled reference plugins** under `markdown6/builtin_plugins/`: `em_dash_to_hyphen` (text transform), `wordcount` (sidebar panel + signals + scoped settings), `stamp` (action + every settings-schema field type).

## [0.1.13] - 2026-04-21

### Added
- Pre-built binaries shipped on every GitHub release:
  - `MarkdownEditor-<version>-x86_64.AppImage` — Linux AppImage (static runtime — no libfuse2 dependency on Ubuntu 24+)
  - `MarkdownEditor-<version>-x86_64.exe` — Windows portable onefile
  - `MarkdownEditor-<version>-x86_64-setup.exe` — Windows installer (Start Menu shortcut, uninstaller, optional "add to PATH" and ".md file association")
  - `MarkdownEditor-<version>-x86_64-portable.zip` — Windows portable dist (unzip and run)
- `install-desktop` / `install-autocomplete` CLI subcommands detect when invoked from a Nuitka-compiled binary and register the absolute bundled-binary path with the OS

### Fixed
- `mde graph -o output.svg` truncated one character from the output filename (off-by-one in extension stripping)

## [0.1.12] - 2026-04-19

### Added
- Copy-to-clipboard button on code blocks in the preview
- Copy-to-clipboard button on rendered mermaid/graphviz diagrams — copies the original source back to the clipboard
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
- Bidirectional scroll sync — scrolling the preview now scrolls the editor
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
