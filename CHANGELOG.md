# Changelog

All notable changes to markdown-editor are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
