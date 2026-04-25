"""Public API for editor-side syntax highlighting of fenced code blocks.

This module defines the ONLY symbols consumers should import. No Pygments
type, symbol, or concept leaks past this file. The Pygments-specific
backend lives in `_pygments_backend` and is swappable (tree-sitter,
KSyntaxHighlighting, custom) without touching consumers.

Vocabulary: spans carry **resolved styling primitives** (color, bgcolor,
bold, italic). The backend resolves whatever rich token taxonomy it
uses against whatever colour scheme is requested, and hands back baked
hex strings. Consumers apply `setFormat`-style calls without needing
to know what a "Token" is.

Design rationale: see local/plans/fenced-code-highlighting-pygments.md.
"""

from __future__ import annotations

from dataclasses import dataclass


# Default colour schemes per UI theme. Consumers (editor & preview)
# read these so both panes colour source code consistently. Values are
# backend-neutral strings passed back to `highlight_line(..., scheme=)`
# and `scheme_defaults`.
DEFAULT_SCHEME_LIGHT = "default"
DEFAULT_SCHEME_DARK = "monokai"


@dataclass(frozen=True)
class Span:
    """One coloured run on a single line.

    `color` and `bgcolor` are `#rrggbb` hex strings, or None when the
    scheme leaves the underlying token unstyled (the consumer should
    paint the scheme defaults from `SchemeDefaults` for those gaps).
    """

    start: int        # offset into the line (in chars)
    length: int
    color: str | None = None
    bgcolor: str | None = None
    bold: bool = False
    italic: bool = False


class State:
    """Opaque state-at-end-of-line handle.

    Callers treat this as a black box: read from the previous line's
    `LineResult.next_state`, pass to `highlight_line`, store between
    calls (e.g. in `QTextBlockUserData`). Internals belong to the
    backend and may change without notice.
    """

    __slots__ = ("_opaque",)

    def __init__(self, opaque):
        object.__setattr__(self, "_opaque", opaque)

    def __eq__(self, other):
        return isinstance(other, State) and self._opaque == other._opaque

    def __hash__(self):
        return hash(self._opaque)

    def __repr__(self):
        return f"State({self._opaque!r})"


@dataclass(frozen=True)
class LineResult:
    """Result of lexing one line: what to paint, and the state for the next line."""

    spans: list[Span]
    next_state: State


@dataclass(frozen=True)
class SchemeDefaults:
    """Scheme-level default styling, applied as the background fill
    behind a fenced code block before per-token spans are layered on top.

    `default_color` is the foreground used when a span has `color=None`.
    `bgcolor` is the scheme's intended block background.
    """

    default_color: str   # '#rrggbb'
    bgcolor: str         # '#rrggbb'


def initial_state() -> State:
    """State to use at the start of a fenced block (no prior context)."""
    raise NotImplementedError


def is_language_supported(lang: str) -> bool:
    """True if `lang` (or an alias of it) has a known lexer."""
    raise NotImplementedError


def highlight_line(
    lang: str, text: str, prev_state: State, scheme: str,
) -> LineResult:
    """Lex one line of source under `scheme`, resuming from `prev_state`.

    Returns spans whose styling is fully resolved against the scheme
    (color/bold/italic baked in). Unknown `lang` yields empty spans
    and unchanged state.
    """
    raise NotImplementedError


def scheme_defaults(scheme: str) -> SchemeDefaults:
    """Default text and background colors for `scheme`.

    Consumers paint these as the fenced-block background fill so that
    untokenized characters and scheme-defined background match faithfully.
    Raises `ValueError` for unknown schemes.
    """
    raise NotImplementedError


def available_schemes() -> list[str]:
    """Return the names of all available colour schemes, sorted."""
    raise NotImplementedError
