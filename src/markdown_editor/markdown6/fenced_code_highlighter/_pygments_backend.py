"""Pygments-backed implementation of the fenced-code highlighter API.

This is the ONLY module that imports Pygments. Swap it out (tree-sitter,
KSyntaxHighlighting, custom) without touching consumers — the public
surface in `api.py` is the stable contract.

─── Acknowledged smell ────────────────────────────────────────────────

We re-implement ~30 lines of Pygments' `RegexLexer.get_tokens_unprocessed`
match loop below (`_run_driver`). This is not gratuitous: Pygments'
published API accepts an initial `stack` kwarg but discards its final
`statestack` local on StopIteration. There is no public way to read
end-of-line state, which we need to resume lexing on the next editor
block.

Two consequences we accept:

  1. We read `lexer._tokens` (the compiled rule table), which is
     underscore-prefixed. Structurally it has been a dict[str, list]
     of 3-tuples since Pygments 0.x. A canary test (see
     tests/markdown6/test_pygments_api_canary.py) asserts this shape
     so a future Pygments bump fails loudly rather than silently
     miscoloring.

  2. Our driver must faithfully mirror Pygments' state-transition
     handling (`#pop` / `#push` / int / tuple / string).
     `_apply_state_transition` below is a literal translation of the
     upstream code.

Alternatives considered (rejected):

  - Re-lex from the fence-open line every time (no state tracking).
    O(block_size) per keystroke — janky on large blocks.
  - Monkey-patch `RegexLexer.get_tokens_unprocessed`. Same amount of
    duplicated code, but with additional process-global side effects.
  - `sys.settrace` to read the generator's frame. Slow, fragile.

If Pygments ever exposes end-state (e.g. `tokens, state = lexer.lex_line(...)`),
delete this whole block and call through.

See `local/plans/fenced-code-highlighting-pygments.md` for the full
design discussion.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import functools

from pygments.lexer import RegexLexer
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_all_styles, get_style_by_name
from pygments.token import Token, _TokenType
from pygments.util import ClassNotFound

from markdown_editor.markdown6.fenced_code_highlighter.api import (
    LineResult,
    SchemeDefaults,
    Span,
    State,
)


_INITIAL_OPAQUE = ("root",)
_INITIAL_STATE = State(opaque=_INITIAL_OPAQUE)


@functools.cache
def _get_lexer(alias: str) -> RegexLexer | None:
    try:
        return get_lexer_by_name(alias)
    except ClassNotFound:
        return None


@functools.cache
def _get_style(scheme: str):
    try:
        return get_style_by_name(scheme)
    except ClassNotFound as exc:
        raise ValueError(
            f"Unknown code-color scheme: {scheme!r}. "
            f"Available: {', '.join(available_schemes())}"
        ) from exc


def initial_state() -> State:
    return _INITIAL_STATE


def is_language_supported(lang: str) -> bool:
    return _get_lexer(lang) is not None


def available_schemes() -> list[str]:
    return sorted(get_all_styles())


def scheme_defaults(scheme: str) -> SchemeDefaults:
    style = _get_style(scheme)
    text_style = style.style_for_token(Token.Text)
    default_color = _hex(text_style.get("color")) or "#000000"
    bg = style.background_color or "#ffffff"
    if not bg.startswith("#"):
        bg = "#" + bg
    return SchemeDefaults(default_color=default_color, bgcolor=bg)


def highlight_line(
    lang: str, text: str, prev_state: State, scheme: str,
) -> LineResult:
    """Tokenize one editor line, resuming from `prev_state`, with each
    token's color/bold/italic resolved against `scheme`.

    Note: a trailing '\\n' is appended before lexing. Many Pygments
    lexers define line-scoped states (C's `'macro'` for `#include`,
    shell heredoc prologues, etc.) that are expected to pop when the
    lexer hits a newline. The editor hands us lines WITHOUT trailing
    newlines (Qt's `QTextBlock` doesn't include them), so we synthesise
    one to make those line-scoped states close at end-of-line. Any
    tokens emitted at or past `len(text)` belong to the synthetic
    newline and are dropped.
    """
    lexer = _get_lexer(lang)
    if lexer is None:
        return LineResult(spans=[], next_state=prev_state)
    style = _get_style(scheme)
    text_len = len(text)
    raw_tokens, end_stack = _run_driver(lexer, text + "\n", prev_state._opaque)
    spans: list[Span] = []
    for pos, tok_type, tok_text in raw_tokens:
        if pos >= text_len:
            continue   # synthetic-newline token
        end = min(pos + len(tok_text), text_len)
        if end <= pos:
            continue
        styling = _resolve_styling(style, tok_type)
        color = _hex(styling.get("color"))
        bgcolor = _hex(styling.get("bgcolor"))
        if color is None and bgcolor is None and not styling.get("bold") and not styling.get("italic"):
            # Token is unstyled by this scheme — skip; the consumer's
            # SchemeDefaults background fill covers this character.
            continue
        spans.append(Span(
            start=pos,
            length=end - pos,
            color=color,
            bgcolor=bgcolor,
            bold=bool(styling.get("bold")),
            italic=bool(styling.get("italic")),
        ))
    return LineResult(spans=spans, next_state=State(opaque=end_stack))


def _hex(c: str | None) -> str | None:
    """Pygments stores colors as bare hex (`'66d9ef'`); the public API
    uses `'#rrggbb'`. Normalise here, leave None as None."""
    if not c:
        return None
    return c if c.startswith("#") else "#" + c


_EMPTY_STYLING: dict = {}


def _resolve_styling(style, token_type) -> dict:
    """Look up styling for `token_type` in `style`, walking ancestors
    manually if the style doesn't know this exact subtype.

    Pygments' built-in `style.style_for_token()` raises `KeyError` for
    some valid-but-uncommon subtypes (e.g. prolog's
    `Token.Literal.String.Atom`) because the style's pre-populated
    `_styles` dict didn't inherit through them. We fall back to walking
    the token's parent chain ourselves.
    """
    cur = token_type
    while cur is not None:
        try:
            return style.style_for_token(cur)
        except KeyError:
            cur = cur.parent
    return _EMPTY_STYLING


def _run_driver(lexer, text, in_stack):
    """Tokenize one line, resuming from `in_stack`, returning
    (tokens, final_stack).

    Faithful copy of `RegexLexer.get_tokens_unprocessed`'s match loop —
    see "Acknowledged smell" above for why this exists.
    """
    tokendefs = lexer._tokens
    statestack = list(in_stack)
    statetokens = tokendefs[statestack[-1]]
    pos = 0
    tokens: list[tuple] = []
    while pos < len(text):
        matched = False
        for rexmatch, action, new_state in statetokens:
            m = rexmatch(text, pos)
            if m is None:
                continue
            if action is not None:
                if type(action) is _TokenType:
                    tokens.append((pos, action, m.group()))
                else:
                    tokens.extend(action(lexer, m))
            pos = m.end()
            if new_state is not None:
                _apply_state_transition(statestack, new_state)
                statetokens = tokendefs[statestack[-1]]
            matched = True
            break
        if not matched:
            tokens.append((pos, Token.Error, text[pos]))
            pos += 1
    return tokens, tuple(statestack)


def _apply_state_transition(statestack: list, new_state) -> None:
    """Mirror of Pygments' transition handling. Kept in lockstep with upstream."""
    if isinstance(new_state, tuple):
        for s in new_state:
            if s == "#pop" and len(statestack) > 1:
                statestack.pop()
            elif s == "#push":
                statestack.append(statestack[-1])
            else:
                statestack.append(s)
    elif isinstance(new_state, int):
        if abs(new_state) >= len(statestack):
            del statestack[1:]
        else:
            del statestack[new_state:]
    elif new_state == "#push":
        statestack.append(statestack[-1])
