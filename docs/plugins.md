# Writing plugins for `mde`

`mde` plugins are Python directories you drop into a known location. They register menu items, sidebar panels, custom export formats, fenced-code renderers, lifecycle handlers, and configuration UIs — all through a small, Qt-free API surface.

This guide walks through the basics. For the stability promise (what's guaranteed not to break across versions) see [`plugin-api-versioning.md`](plugin-api-versioning.md). For the project README and overall feature overview, see [`../README.md`](../README.md). For internal architecture (if you're modifying the editor itself), see [`../src/markdown_editor/markdown6/DEVELOPMENT.md`](../src/markdown_editor/markdown6/DEVELOPMENT.md).

## Where plugins live

| Kind | Location |
|---|---|
| **User plugins** | `~/.config/markdown-editor/plugins/<name>/` on Linux. The exact path is the value of `QStandardPaths.GenericConfigLocation`, which is `~/Library/Application Support/markdown-editor/plugins/` on macOS and `%APPDATA%\markdown-editor\plugins\` on Windows. |
| **Built-in plugins** | `markdown_editor/markdown6/builtin_plugins/`. Reserved for plugins shipped with the editor; **currently empty**. |
| **Extra dirs (CLI)** | one or more `--plugins-dir DIR` flags. Stacks on top of the user dir — useful for per-project plugin sets without polluting your user config. |
| **Extra dirs (settings)** | the `plugins.extra_dirs` list. Manage it from **Settings → Plugins → Extra plugin directories** with the *Add directory…* / *Remove selected* buttons. Persists across launches. |

All four sources are additive — none replaces another. Inside Settings → Plugins, the **"Open plugins folder"** button reveals the user dir in your file manager and creates it if missing.

The reference example plugins (`em_dash_to_hyphen`, `wordcount`, `stamp`) live under [`../docs/plugins-examples/`](plugins-examples/). They are not bundled with the editor; copy any of them into your user dir to install.

## File layout

A plugin is a directory whose name **must match** the plugin's `name` field. The directory contains a `.py` and a `.toml`, both named after the directory:

```
my_plugin/
  my_plugin.py        # entry point (must match dir name)
  my_plugin.toml      # metadata
  README.md           # optional; rendered in Settings → Plugins → Info
  assets/             # optional; whatever your plugin needs
```

If the names don't line up, or if the `.py` raises during import, the editor catches the error and shows the plugin in Settings → Plugins with an error status — it never crashes the editor.

## The minimum plugin

A do-nothing plugin needs three lines of TOML and an empty `.py`:

```toml
# my_plugin/my_plugin.toml
[tool.mde.plugin]
name = "my_plugin"      # must match the directory name
version = "1.0.0"
```

```python
# my_plugin/my_plugin.py
# nothing yet
```

Restart the editor; `my_plugin` shows up in Settings → Plugins with status "Enabled". Now you can register things.

## Adding an action

```python
from markdown_editor.plugins import register_action, get_active_document

@register_action(
    id="my_plugin.greet",
    label="Insert greeting",
    palette_category="Greetings",
    shortcut="Ctrl+Alt+G",      # optional
)
def greet():
    doc = get_active_document()
    if doc is None:
        return                   # no open tab — silently no-op
    doc.insert_at_cursor("Hello, world!")
```

The framework adds an entry under **Plugins → Insert greeting**, binds the shortcut, and shows it in the command palette (`Ctrl+Shift+P`).

If the plugin raises, the action's exception is caught, logged, and surfaced in the **🔔 notifications drawer** (status bar, right) — the editor stays running.

## A pure-text transform

If your action just rewrites the document text, prefer `register_text_transform`. The framework handles atomic apply (single undo step, rolled back if your function raises):

```python
from markdown_editor.plugins import register_text_transform

@register_text_transform(
    id="my_plugin.uppercase_headings",
    label="Uppercase headings",
)
def upper(text: str) -> str:
    return "\n".join(
        line.upper() if line.startswith("#") else line
        for line in text.splitlines()
    )
```

Text transforms are atomic by construction — your `(str) -> str` function can't observe the live document, so it can't leave it half-modified.

## Imperative actions with atomic edits

For multi-step or cursor-aware mutations, use `with doc.atomic_edit():`. Everything inside collapses into one Ctrl+Z step; if anything raises, the document rolls back to its pre-block state:

```python
from markdown_editor.plugins import register_action, get_active_document

@register_action(id="my_plugin.bold_select", label="Bold selection")
def bold():
    doc = get_active_document()
    if doc is None:
        return
    with doc.atomic_edit():
        if doc.has_selection:
            doc.wrap_selection("**", "**")
        else:
            doc.insert_at_cursor("****")
            doc.move_cursor(-2)      # cursor between the asterisks
```

## Custom fenced-code renderer

Render any fence language as inline HTML — same mechanism as the built-in `mermaid` and `graphviz` blocks:

```python
from markdown_editor.plugins import register_fence

@register_fence("plantuml")
def render_plantuml(source: str) -> str:
    # call PlantUML jar / online renderer / whatever
    return f"<svg>...</svg>"     # framework embeds your HTML
```

Now ` ```plantuml ` ... ` ``` ` blocks in any document render via your callback.

## Sidebar panel

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from markdown_editor.plugins import register_panel, on_content_changed, get_active_document

_PANEL = None

class MyPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.label = QLabel("0 chars")
        layout.addWidget(self.label)

    def update_count(self, n):
        self.label.setText(f"{n} chars")

@register_panel(id="my_plugin.charcount", label="Char Count", icon="🔢")
def make_panel():
    global _PANEL
    _PANEL = MyPanel()
    return _PANEL

@on_content_changed
def _on_change(_doc):
    if _PANEL is None:
        return
    doc = get_active_document()
    if doc is not None:
        _PANEL.update_count(len(doc.text))
```

This is the one extension point that necessarily exposes Qt — building a UI requires Qt widgets. The plugin's *registration* surface is still Qt-free; only the factory's return value (the `QWidget`) crosses into Qt.

## Custom export format

```python
from pathlib import Path
from markdown_editor.plugins import register_exporter

@register_exporter(
    id="my_plugin.jekyll",
    label="Jekyll Post",
    extensions=["md"],         # save dialog filter
)
def export_jekyll(doc, path: Path):
    frontmatter = "---\nlayout: post\n---\n\n"
    path.write_text(frontmatter + doc.text)
```

The framework adds **Plugins → Export → Jekyll Post**, opens a save dialog filtered to `.md`, then calls your function with the chosen path. No active document → dialog is not opened.

## Markdown extension passthrough

If your plugin is best expressed as a `markdown.Extension` (preprocessor / postprocessor / inline pattern), register it directly:

```python
from markdown import Extension
from markdown.preprocessors import Preprocessor
from markdown_editor.plugins import register_markdown_extension

class _Pre(Preprocessor):
    def run(self, lines):
        return [l.replace("<3", "❤") for l in lines]

class _HeartExt(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(_Pre(md), "_heart", 25)

register_markdown_extension(_HeartExt())
```

Both the live preview and the export pipeline pick it up automatically.

## Lifecycle signals

```python
from markdown_editor.plugins import on_save, on_content_changed, on_file_opened, on_file_closed

@on_save
def _on_save(doc):
    print(f"Saved: {doc.file_path}")

@on_file_opened
def _on_open(doc):
    print(f"Opened: {doc.file_path}")
```

Handlers receive a `DocumentHandle` — Qt-free wrapper exposing `text`, `file_path`, `has_selection`, `is_dirty`, and the mutator methods. `on_content_changed` fires after every keystroke; debounce inside your handler if you do anything expensive.

If your handler raises, it's caught, logged, and surfaced in the notifications drawer — other handlers still run.

## Plugin settings

Two layers, both backed by the same storage (`plugins.<your_id>.<key>` in the editor's main settings file):

**Programmatic** — your plugin reads/writes its own state:

```python
from markdown_editor.plugins import plugin_settings

s = plugin_settings("my_plugin")
s["last_run"] = "2026-04-22T10:00"
last = s.get("last_run", "")
```

**User-facing config** — the framework auto-renders a Configure dialog from your schema:

```python
from markdown_editor.plugins import register_settings_schema, Field

register_settings_schema(fields=[
    Field("api_key", "API Key", description="Your service token"),
    Field("max_results", "Max results", type=int, default=10, min=1, max=100),
    Field("model", "Model", default="gpt-4",
          choices=("gpt-4", "gpt-3.5-turbo")),
    Field("verbose", "Verbose logging", type=bool, default=False),
    Field("note", "Notes", widget="multiline", default=""),
])
```

A **Configure…** button appears on your plugin's row in Settings → Plugins. Field types: `str` (line edit), `str` + `choices` (dropdown), `str` + `widget="multiline"` (text area), `int` (spin box, optional `min`/`max`), `float` (double spin), `bool` (checkbox).

## Posting notifications

```python
from markdown_editor.plugins import notify_info, notify_warning, notify_error

notify_info("Export complete", f"Wrote {path}")
notify_warning("Cache stale", "Will rebuild on next render")
notify_error("Fetch failed", str(exc))
```

Source defaults to `plugin:<your_name>` so notifications group correctly in the bell drawer.

## Declaring dependencies

If your plugin needs a third-party Python module, declare it:

```toml
[tool.mde.plugin.dependencies]
python = ["requests", "openai>=1.0"]
```

The loader checks each module is importable before running your `.py`. Missing → plugin disabled with status "Error (missing deps)" and a clear message in Settings → Plugins; nothing crashes.

Note: the version spec (`>=1.0`) is currently advisory — only the bare module name is checked.

## Debugging

When something goes wrong:

1. **Settings → Plugins** — shows the status of every discovered plugin. Errored plugins have a grayed checkbox and the error reason in the row.
2. **ℹ Info button** on the plugin's row — opens a dialog with full status detail + your README.md.
3. **🔔 Notifications drawer** (status bar) — runtime errors during action / transform / signal handler execution land here.
4. **Editor logs** — every plugin error is also logged via `mde.markdown_editor.markdown6.plugins.*`. Run mde from a terminal to see them live.

## Disabling and re-enabling

Settings → Plugins lets the user toggle each plugin's enable checkbox. Toggle takes effect immediately for plugins that were loaded at startup — menu entries hide/show, sidebar panels disappear/reappear, fences/extensions are removed/added from the live preview.

Re-enabling a plugin that was disabled at startup time still requires a restart, because its `.py` was never imported (its registrations don't exist in memory).

## Plugin lifecycle TL;DR

- **Loaded** once at editor startup.
- **No hot reload.** "Reload Plugins" (in the command palette + Settings → Plugins button) re-runs *discovery* and tells you what's new on disk; restart for new plugins to actually load.
- **Disabled plugins** are still imported (so live re-enable works) — only their actions/panels/etc. are hidden.
- **Errored plugins** are not re-invoked until you fix them and restart.

## API stability

See [`plugin-api-versioning.md`](plugin-api-versioning.md). Short version: stuff exported from `markdown_editor.plugins` is stable across the same major editor version (post-1.0); MDE 0.x is explicitly unstable. Reach into deeper namespaces (`markdown_editor.markdown6.*`) at your own risk.

## Worked examples

The example plugins under [`plugins-examples/`](plugins-examples/) are the best place to read real working code:

| Plugin | Demonstrates |
|---|---|
| [`em_dash_to_hyphen`](plugins-examples/em_dash_to_hyphen/) | Minimal `register_text_transform` plugin. |
| [`wordcount`](plugins-examples/wordcount/) | `register_panel` + `@on_content_changed` + `@on_file_opened` + `plugin_settings`. |
| [`stamp`](plugins-examples/stamp/) | `register_action` + `register_settings_schema` (every supported field type). |

To install one, copy the directory into your user plugin folder (see [`plugins-examples/README.md`](plugins-examples/README.md) for paste-ready commands per OS) and restart the editor — or point at the source directly with `mde --plugins-dir docs/plugins-examples`.
