"""Reference builtin plugin: replace em-dashes with regular hyphens.

Serves two purposes:

1. Exercises the plugin-loading pipeline end-to-end from a directory
   the wheel actually ships (not a synthetic test fixture), so a
   regression in packaging or discovery shows up in the test suite.
2. Acts as the canonical example of a ``register_text_transform``
   plugin — the smallest useful body of code a plugin author can
   crib from.

The transform itself is deliberately trivial: one ``str.replace``
call. Real-world users can install it if they prefer ASCII hyphens
in their markdown, or disable it from Settings → Plugins.
"""

from __future__ import annotations

from markdown_editor.plugins import register_text_transform

EM_DASH = "\u2014"   # —


@register_text_transform(
    id="em_dash_to_hyphen.replace",
    label="Replace em-dashes with hyphens",
    menu="Transform",                       # → Plugins/Transform/Replace…
    palette_category="Transform",
)
def replace_em_dashes(text: str) -> str:
    return text.replace(EM_DASH, "-")
