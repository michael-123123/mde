# Markdown Editor

A feature-rich, cross-platform Markdown editor built with PySide6 (Qt6) featuring live preview, syntax highlighting, and project management.

## Features

### Editor
- **Syntax highlighting** for Markdown with light/dark theme support
- **Live preview** with synchronized scrolling (using QtWebEngine)
- **Multi-tab interface** with duplicate file detection
- **Code folding** for headings and code blocks
- **Line numbers** with current line highlighting
- **Auto-pairs** for brackets, quotes, and Markdown syntax
- **Auto-indentation** for lists and code blocks
- **Word wrap** toggle
- **Zoom** support (Ctrl++/Ctrl+-/Ctrl+0)

### Navigation
- **Outline panel** - Document structure with heading navigation
- **References panel** - Backlinks showing files that reference the current document
- **Project panel** - File tree for project folder management
- **Command palette** (Ctrl+Shift+P) - Quick access to all commands
- **Go to line** (Ctrl+G)
- **Find and replace** with regex support

### Markdown Features
- **Wiki-style links** - `[[page]]` or `[[page|display text]]` with auto-completion
- **Standard links** - `[text](url)` with Ctrl+click to follow
- **Clickable links in preview** - Opens markdown files in editor, others in default app
- **Tables** - Visual table editor (Ctrl+Shift+T)
- **Code blocks** - Syntax highlighted with Pygments
- **Callouts/Admonitions** - Note, warning, tip, important, caution blocks
- **Snippets** - Insertable templates (Ctrl+J)

### Export
- **HTML** - Standalone HTML with embedded styles
- **PDF** - Via weasyprint (default) or pandoc
- **DOCX** - Via python-docx (default) or pandoc
- **Markdown** - Combined project export
- **Project export** - Combine multiple files with table of contents

### Other
- **Dark/Light themes** - System-wide theme switching
- **Customizable keyboard shortcuts**
- **Recent files** menu
- **Auto-save** (optional)
- **External file change detection**
- **Image paste** from clipboard

## Installation

### Requirements
- Python 3.11+
- PySide6 6.5+

### Install from source

```bash
cd /path/to/fun
pip install -e .
```

### Dependencies

Core Python packages (installed automatically via pip):
- `PySide6` - Qt6 bindings
- `PySide6-Addons` - QtWebEngine for preview
- `markdown` - Markdown parsing
- `Pygments` - Syntax highlighting
- `graphviz` - Python bindings for Graphviz
- `weasyprint` - PDF export fallback
- `python-docx` - DOCX export fallback

### External Tools (optional)

These system-level tools enable additional features. The editor works without them but with reduced functionality. Configure paths in Settings > External Tools.

| Tool | Purpose | Install | Without it |
|------|---------|---------|------------|
| **Pandoc** | High-quality PDF/DOCX export with LaTeX | `apt install pandoc texlive-xetex` | Uses weasyprint/python-docx |
| **Graphviz** (`dot`) | Renders ` ```dot ` / ` ```graphviz ` diagrams | `apt install graphviz` | Falls back to browser-side viz.js |
| **Mermaid CLI** (`mmdc`) | Renders ` ```mermaid ` diagrams to SVG | `npm install -g @mermaid-js/mermaid-cli` | Falls back to browser-side mermaid.js (requires internet) |

Install all optional tools at once (Debian/Ubuntu):
```bash
sudo apt install pandoc texlive-xetex graphviz
npm install -g @mermaid-js/mermaid-cli
```

With conda/mamba:
```bash
mamba install -c conda-forge pandoc graphviz nodejs
npm install -g @mermaid-js/mermaid-cli
```

## Usage

### Launch the editor

```bash
# Using the full command
markdown-editor

# Or the short alias
mde

# Open a specific file
mde /path/to/file.md
```

### Keyboard Shortcuts

#### File Operations
| Shortcut | Action |
|----------|--------|
| Ctrl+N | New file |
| Ctrl+O | Open file |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save as |
| Ctrl+W | Close tab |
| Ctrl+Q | Quit |

#### Edit Operations
| Shortcut | Action |
|----------|--------|
| Ctrl+Z | Undo |
| Ctrl+Shift+Z | Redo |
| Ctrl+F | Find |
| Ctrl+R | Replace |
| Ctrl+G | Go to line |
| Ctrl+/ | Toggle comment |
| Ctrl+Shift+D | Duplicate line |
| Ctrl+Shift+K | Delete line |
| Alt+Up | Move line up |
| Alt+Down | Move line down |

#### Markdown Formatting
| Shortcut | Action |
|----------|--------|
| Ctrl+B | Bold |
| Ctrl+I | Italic |
| Ctrl+K | Insert link |
| Ctrl+` | Inline code |
| Ctrl+] | Increase heading level |
| Ctrl+[ | Decrease heading level |
| Ctrl+Shift+I | Insert image |
| Ctrl+Shift+T | Insert table |
| Ctrl+J | Insert snippet |

#### View
| Shortcut | Action |
|----------|--------|
| Ctrl+Shift+P | Command palette |
| Ctrl+Shift+V | Toggle preview |
| Ctrl+Shift+O | Open project folder |
| Ctrl+Alt+O | Toggle outline |
| Ctrl+Shift+E | Toggle project panel |
| Ctrl+Shift+R | Toggle references |
| Ctrl+Shift+L | Toggle line numbers |
| Alt+Z | Toggle word wrap |
| F5 | Refresh preview |
| F11 | Fullscreen |
| Ctrl++ | Zoom in |
| Ctrl+- | Zoom out |
| Ctrl+0 | Reset zoom |

#### Navigation
| Shortcut | Action |
|----------|--------|
| Ctrl+Tab | Next tab |
| Ctrl+Shift+Tab | Previous tab |
| Alt+1-9 | Go to tab 1-9 |
| F3 | Find next |
| Shift+F3 | Find previous |

### Wiki Links

The editor supports wiki-style links for easy cross-referencing:

```markdown
[[another-page]]           # Links to another-page.md
[[folder/page]]            # Links to folder/page.md
[[page|Display Text]]      # Links to page.md, shows "Display Text"
```

- Type `[[` to trigger auto-completion
- Ctrl+click on a wiki link to open it
- Links without extensions automatically get `.md` appended

### Callouts

Use callout blocks for highlighted notes:

```markdown
!!! note "Optional Title"
    This is a note callout.

!!! warning
    This is a warning without a custom title.

!!! tip "Pro Tip"
    Helpful tips go here.
```

Supported types: `note`, `warning`, `tip`, `important`, `caution`, `abstract`, `info`, `success`, `question`, `failure`, `danger`, `bug`, `example`, `quote`

### Project Export

1. Open a project folder (Ctrl+Shift+E, then click "Open Folder")
2. Click "Export" in the project panel
3. Select files to include (drag to reorder)
4. Choose format (HTML, PDF, DOCX, Markdown)
5. Options:
   - Include Table of Contents
   - Insert page breaks between files
   - Use Pandoc (if installed, for LaTeX PDF)

## Configuration

Settings are stored in `~/.config/markdown-editor/`:

- `settings.json` - Editor preferences
- `shortcuts.json` - Custom keyboard shortcuts

### Settings Dialog

Access via Edit menu or use the command palette. Configure:

- **Editor**: Font, tab size, line numbers, word wrap, auto-pairs
- **View**: Theme, preview font size, sync scrolling
- **Files**: Recent files limit, external change detection
- **External Tools**: Paths to pandoc, graphviz (dot), mermaid CLI (mmdc)
- **Shortcuts**: Customize all keyboard shortcuts

## Project Structure

```
src/fun/markdown6/
├── markdown_editor.py    # Main window, tabs, menus
├── enhanced_editor.py    # Text editor widget
├── syntax_highlighter.py # Markdown highlighting
├── theme.py              # Color themes and stylesheets
├── settings.py           # Settings management
├── settings_dialog.py    # Settings UI
├── export_service.py     # PDF/DOCX/HTML export
├── tool_paths.py         # External tool path resolution
├── mermaid_service.py    # Mermaid diagram rendering
├── graphviz_service.py   # Graphviz diagram rendering
├── project_manager.py    # Project panel and export dialog
├── outline_panel.py      # Document outline
├── references_panel.py   # Backlinks panel
├── command_palette.py    # Command palette
├── snippets.py           # Snippet definitions
├── table_editor.py       # Visual table editor
├── searchable_popup.py   # Base popup widget
└── markdown_extensions.py # Custom markdown extensions
```

## License

See LICENSE file in repository root.
