# Example plugins

These are reference plugins showing how to use each extension point of the [`mde` plugin API](../plugins.md). **They are not bundled with the editor** - nothing in this directory loads automatically.

| Plugin | Demonstrates |
|---|---|
| [`em_dash_to_hyphen/`](em_dash_to_hyphen/) | Minimal `register_text_transform` (em-dash → hyphen). |
| [`wordcount/`](wordcount/) | `register_panel` + `@on_content_changed` + `@on_file_opened` + `plugin_settings`. |
| [`stamp/`](stamp/) | `register_action` + `register_settings_schema` covering every supported field type. |

## Installing an example

Copy the plugin's directory into your user plugin dir, then restart the editor:

```bash
# Linux
cp -r docs/plugins-examples/wordcount ~/.config/markdown-editor/plugins/

# macOS
cp -r docs/plugins-examples/wordcount \
   "$HOME/Library/Application Support/markdown-editor/plugins/"

# Windows (PowerShell)
Copy-Item -Recurse docs\plugins-examples\wordcount `
   "$env:APPDATA\markdown-editor\plugins\"
```

The **Open plugins folder** button in **Settings → Plugins** reveals that directory in your file manager.

## Writing your own

Start with [`../plugins.md`](../plugins.md) (the authoring guide) - it walks through each extension point with worked code. The examples here are mirrored from that guide, so you can read them side by side.
