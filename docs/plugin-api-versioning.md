# Plugin API versioning contract

This document is the authoritative statement of what plugin authors can rely on between MDE versions, what may change, and how deprecation works.

For a tutorial-style introduction to writing plugins, see [`plugins.md`](plugins.md). For the project's main README and high-level overview, see [`../README.md`](../README.md).

## Stability scope

The **public API** is everything exported from the top-level `markdown_editor.plugins` module:

```python
from markdown_editor.plugins import (
    # Registration decorators
    register_action, register_text_transform, register_panel,
    register_fence, register_exporter, register_markdown_extension,
    register_settings_schema,
    # Lifecycle signals
    on_save, on_content_changed, on_file_opened, on_file_closed,
    # Document access + storage
    get_active_document, get_all_documents, plugin_settings,
    DocumentHandle, Field,
    # Notifications
    notify_info, notify_warning, notify_error,
)
```

These names will not be removed or renamed within the same major version of MDE (post-1.0 — see "Pre-1.0 caveat" below).

The **TOML metadata schema** (`[tool.mde.plugin]` section) is also part of the public API. Required fields' semantics are stable across the same major version; new optional fields may be added.

## What's *not* part of the stable API

* Anything imported directly from `markdown_editor.markdown6.*` (the deeper internal namespace). The shim re-exports the stable surface; reaching past it is opting out of stability.
* The two **escape hatches** explicitly documented as opt-in unstable: `get_app_context`, `get_main_window`, and the `DocumentHandle.editor` / `DocumentHandle.preview` properties. These let advanced plugins reach into Qt; their signatures and behavior may change between minor versions without deprecation.
* The internal plugin registry (`markdown_editor.markdown6.plugins.api._REGISTRY`), the loader's `_set_active_document_provider` hook, and any name prefixed with `_`.

## Allowed changes within a major version

* **Adding** new registration decorators, signals, or helpers.
* **Adding** new keyword-only arguments to existing decorator signatures (with sensible defaults so old plugins keep working).
* **Adding** new optional fields to dataclasses (`Field`, `Notification`, etc.) and new values to enums (`Severity`, `PluginStatus`).
* **Adding** new optional keys / subtables to the TOML schema.

## Disallowed changes within a major version

* Removing or renaming exported names.
* Removing or renaming existing decorator parameters.
* Changing the type of an existing parameter or return value in a way that would break a calling plugin.
* Removing existing values from `Severity` / `PluginStatus`.
* Making a previously-optional TOML field required, or removing a previously-supported field.

## Plugin-declared API version

Each plugin declares the API major version it was written for in its TOML:

```toml
[tool.mde.plugin]
mde_api_version = "1"   # the MDE major version this plugin targets
```

Behavior:

| Editor major | Plugin's `mde_api_version` major | Result |
|---|---|---|
| same | same | loads normally |
| `0` (pre-stable) | any | loads normally (no enforcement; advisory only) |
| `1` or later | mismatched major | loaded with status `API_MISMATCH` — disabled, reason shown in Settings → Plugins |

This means once we tag MDE 1.0.0, a plugin declaring `mde_api_version = "1"` continues to work through 1.x; if/when MDE 2.0 ships, that plugin needs an updated `mde_api_version` (and possibly code changes) to load.

## Pre-1.0 caveat (current state)

MDE is currently at 0.x. The plugin API is **not stable** — minor version bumps may break plugins. The `mde_api_version` field is parsed but not enforced.

The contract above takes effect once we tag 1.0.0. Until then, plugins that ship with the editor (the bundled `em_dash_to_hyphen`, `wordcount`, `stamp` examples) are kept in sync with API changes; external plugin authors should expect to make small updates between minor releases.

## Deprecation policy (post-1.0)

When a public-API symbol needs to be removed or renamed:

1. The symbol is **deprecated** in a minor release — kept working, but a `DeprecationWarning` is logged at plugin load time naming the deprecated symbol and the recommended replacement.
2. The deprecation period is at least one full minor release.
3. The next major version may then remove the symbol.

For example:
* MDE 1.4 deprecates `register_text_transform` in favor of a hypothetical `register_transform`.
* MDE 1.5, 1.6, ... still support `register_text_transform` but log a deprecation warning each time it's used.
* MDE 2.0 may remove `register_text_transform` entirely.

## Where to ask if you're unsure

If you're not sure whether something you're using is stable, check:

1. Is it imported from `markdown_editor.plugins`? → covered by this contract.
2. Is it imported from `markdown_editor.markdown6.*`? → not stable.
3. Is it `get_app_context()`, `get_main_window()`, or `doc.editor` / `doc.preview`? → escape hatch, not stable.
4. Otherwise: file an issue and we'll either add it to the public API or document why it can't be.
