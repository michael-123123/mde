"""Plugin-supplied fenced-code-block renderer extension.

A single :class:`PluginFenceExtension` is added to the markdown
converter (via :func:`build_markdown`'s ``extra_extensions=``). On
each render its preprocessor scans the source for fenced code blocks
whose language tag matches a name registered via
:func:`api.register_fence`, calls the plugin's callback with the
fence body, and substitutes the returned HTML in place of the fence.

Disabled-plugin fences are skipped at render time (the disabled set
is captured when the extension is constructed; toggling triggers
``_init_markdown`` which builds a new extension with the new set).

Plugin callbacks that raise are caught and logged; the original fence
is left in the source so the user sees the broken block instead of
silently losing content.
"""

from __future__ import annotations

import re

from markdown import Extension
from markdown.preprocessors import Preprocessor

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


# The character set a plugin fence name is allowed to use. Shared
# with ``api.register_fence`` validation so registration and matching
# can't drift from each other.
FENCE_NAME_CHARS = r"[A-Za-z0-9_-]"


# Match a fenced code block whose language tag is just the bare
# alphanumeric name (no extra args). Language captured as group 1,
# body as group 2. Supports both ``` and ~~~ fences but we keep it
# tight on the opening to avoid eating regular code blocks that
# happen to start with the plugin's tag.
_FENCE_RE = re.compile(
    rf'^(?P<fence>`{{3,}}|~{{3,}})(?P<lang>{FENCE_NAME_CHARS}+)\s*\n'
    r'(?P<body>.*?)\n'
    r'(?P=fence)\s*$',
    re.MULTILINE | re.DOTALL,
)


class _PluginFencePreprocessor(Preprocessor):
    def __init__(self, md, disabled: set[str]) -> None:
        super().__init__(md)
        self._disabled = disabled

    def run(self, lines):
        # Imported lazily to avoid the api → registry → fence → api
        # circular import at module-load time.
        from markdown_editor.markdown6.plugins import api as _api

        text = "\n".join(lines)

        def _sub(m: re.Match) -> str:
            lang = m.group("lang")
            fence = _api._REGISTRY.get_fence(lang)
            if fence is None:
                return m.group(0)   # unknown fence — leave alone
            if fence.plugin_name and fence.plugin_name in self._disabled:
                return m.group(0)   # disabled plugin — leave alone
            try:
                html = fence.callback(m.group("body"))
            except BaseException as exc:   # noqa: BLE001 — plugin code
                logger.warning(
                    "Plugin fence %r raised: %s", lang, exc, exc_info=True,
                )
                return m.group(0)
            # Park the plugin's HTML in the markdown htmlStash so the
            # remaining preprocessors / inline patterns / postprocessors
            # don't escape its `<`, `>`, `&` or interpret its angle
            # brackets as markdown syntax.
            return self.md.htmlStash.store(html)

        return _FENCE_RE.sub(_sub, text).split("\n")


class PluginFenceExtension(Extension):
    """Markdown extension that dispatches fenced blocks to plugin
    fence renderers registered via :func:`register_fence`."""

    def __init__(self, *, disabled: set[str] | None = None) -> None:
        super().__init__()
        self._disabled = disabled or set()

    def extendMarkdown(self, md) -> None:
        # Priority 30 = before FencedCodeExtension (priority 25) so we
        # get first crack at fences whose language is registered to a
        # plugin. Anything we don't handle falls through to the
        # built-in fenced code handler.
        md.preprocessors.register(
            _PluginFencePreprocessor(md, self._disabled),
            "plugin_fence", 30,
        )
