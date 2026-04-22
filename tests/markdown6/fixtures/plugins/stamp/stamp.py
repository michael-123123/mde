"""Stamp — third bundled reference plugin.

Demonstrates the schema-driven Configure UI: the plugin declares a
list of :class:`Field` records, the framework auto-renders a config
dialog accessible via the ``Configure…`` button on the plugin's row
in Settings → Plugins, and the user's choices route through
:func:`plugin_settings("stamp")` storage.

Touches every supported field type at once (str, str+choices,
str+multiline, int with bounds, bool) so it exercises the dialog
end-to-end.
"""

from __future__ import annotations

from datetime import datetime

from markdown_editor.plugins import (
    Field,
    get_active_document,
    plugin_settings,
    register_action,
    register_settings_schema,
)

_PLUGIN_ID = "stamp"


# ---------------------------------------------------------------------------
# User-editable schema — auto-rendered as the Configure dialog
# ---------------------------------------------------------------------------

register_settings_schema(fields=[
    Field("text", "Stamp text",
          default="—Stamp—",
          description="Text inserted at the cursor when the stamp action fires."),
    Field("position", "Position",
          default="cursor",
          choices=("cursor", "line-start", "line-end"),
          description="Where in the current line to place the stamp."),
    Field("repeat", "Repeat count",
          type=int, default=1, min=1, max=20,
          description="How many copies to insert in a row."),
    Field("include_timestamp", "Include timestamp",
          type=bool, default=False,
          description="Append the current date/time after the stamp text."),
    Field("notes", "Notes (multiline)",
          default="",
          widget="multiline",
          description="Free-form notes — stored but not used by the action. "
                      "Useful for verifying the multiline widget."),
])


# ---------------------------------------------------------------------------
# Action that uses the configured values
# ---------------------------------------------------------------------------


def _build_stamp(s) -> str:
    text = s.get("text", "—Stamp—")
    if s.get("include_timestamp", False):
        text = f"{text} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    repeat = max(1, int(s.get("repeat", 1)))
    return text * repeat


@register_action(
    id="stamp.insert",
    label="Insert stamp",
    palette_category="Stamp",
)
def insert_stamp() -> None:
    doc = get_active_document()
    if doc is None:
        return

    s = plugin_settings(_PLUGIN_ID)
    stamp = _build_stamp(s)
    position = s.get("position", "cursor")

    with doc.atomic_edit():
        if position == "line-start":
            # Naive line-start: prepend to whole text. For a real plugin
            # we'd reach into the editor's QTextCursor for the current
            # line; this is the simple version that exercises the storage
            # round-trip.
            doc.replace_all(stamp + "\n" + doc.text)
        elif position == "line-end":
            doc.replace_all(doc.text + "\n" + stamp)
        else:
            doc.insert_at_cursor(stamp)
