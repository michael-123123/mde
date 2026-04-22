"""Public plugin API for the Markdown editor.

This is the import path **plugin authors** should use:

.. code-block:: python

    from markdown_editor.plugins import (
        register_action,
        register_text_transform,
        register_panel,
        register_fence,
        register_exporter,
        register_markdown_extension,
        on_save,
        on_content_changed,
        on_file_opened,
        on_file_closed,
        get_active_document,
        DocumentHandle,
    )

Everything here is a thin re-export of the corresponding symbol in
:mod:`markdown_editor.markdown6.plugins.api`. The internal module is
where the implementation lives; this shim is the stable contract
plugin authors code against.

Stability promise:

* Names exported here will not change between MDE minor versions
  once we hit 1.0.
* Argument signatures of decorators may grow keyword-only arguments
  (with sensible defaults) but won't drop or rename existing ones.
* Method signatures on :class:`DocumentHandle` are similarly stable.

If you find yourself needing something not exported here, that thing
is either an internal helper (which may change without notice) or a
gap in the public API - please file an issue.

Documentation:

* ``docs/plugins.md`` - tutorial-style plugin authoring guide with
  worked examples for every extension point.
* ``docs/plugin-api-versioning.md`` - full API stability contract
  (what's stable, what's not, deprecation policy, ``mde_api_version``
  semantics).

Reference example plugins (read these for working code) - not
bundled, available under ``docs/plugins-examples/``:

* ``em_dash_to_hyphen/`` - minimal text transform.
* ``wordcount/`` - sidebar panel + signals + plugin settings.
* ``stamp/`` - action + schema-driven Configure dialog (every
  supported field type).
"""

from __future__ import annotations

from markdown_editor.markdown6.plugins.api import (
    Field,
    get_active_document,
    get_all_documents,
    get_app_context,
    get_main_window,
    notify_error,
    notify_info,
    notify_warning,
    on_content_changed,
    on_file_closed,
    on_file_opened,
    on_save,
    plugin_settings,
    register_action,
    register_exporter,
    register_fence,
    register_markdown_extension,
    register_panel,
    register_settings_schema,
    register_text_transform,
)
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle

__all__ = [
    # Registration decorators
    "register_action",
    "register_text_transform",
    "register_panel",
    "register_fence",
    "register_exporter",
    "register_markdown_extension",
    "register_settings_schema",
    # Lifecycle signals
    "on_save",
    "on_content_changed",
    "on_file_opened",
    "on_file_closed",
    # Document access + storage (stable)
    "get_active_document",
    "get_all_documents",
    "plugin_settings",
    "DocumentHandle",
    "Field",
    # Notifications (post info/warning/error to the bell drawer)
    "notify_info",
    "notify_warning",
    "notify_error",
    # Escape hatches (opt-in; not guaranteed stable across versions)
    "get_app_context",
    "get_main_window",
]
