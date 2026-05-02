"""Pygments-backed implementation of the fenced-code highlighter API.

This is the ONLY module that imports Pygments. Swap it out (tree-sitter,
KSyntaxHighlighting, custom) without touching consumers — the public
surface in `api.py` is the stable contract.

─── Acknowledged smell ────────────────────────────────────────────────

Pygments has THREE flavours of lexer in the wild and our per-line
state-resuming model has to handle each. None of them expose a clean
"give me (tokens, end_state) for this line, resuming from this state"
function, so we bridge each one differently.

  Flavour 1: `RegexLexer` (most languages — python, c, rust, sql, ...)

    `get_tokens_unprocessed(text, stack=...)` takes a starting state
    stack as a public kwarg, but its final `statestack` local is
    discarded on StopIteration — no way to read end-of-line state.

    We run our own match-loop driver (`_run_regex_driver`) that
    mirrors Pygments' loop and exposes the final stack. It reads
    `lexer._tokens` (the compiled rule table) and replays Pygments'
    state-transition logic (`#pop` / `#push` / int / tuple / str) by
    hand. Stable for ~15 years of Pygments; canary tests (see
    `tests/markdown6/test_pygments_api_canary.py`) pin the data
    shapes so a future bump fails loudly.

  Flavour 2: `ExtendedRegexLexer` (yaml, ruby, php, html, xml, ...)

    Uses callable actions of the form `action(lexer, match, context)`
    — three arguments — plus a `LexerContext` object whose CONCRETE
    SUBCLASS varies per lexer. YAML uses `YamlLexerContext` with extra
    `indent`/`next_indent` fields that its callbacks read; passing the
    generic `LexerContext` crashes mid-callback with `AttributeError`.

    We don't track cross-line state for this flavour. Each line is
    lexed in isolation by calling Pygments' own `get_tokens_unprocessed`
    with no context — Pygments constructs the right subclass for the
    lexer and lexes correctly. Cost: cross-line constructs (YAML `|`/
    `>` block scalars, Ruby heredocs, multi-line PHP HEREDOC) won't
    carry colour from line N to line N+1. Acceptable for the fenced-
    code-block use case, where blocks are short and the per-line
    constructs (keys, values, tags, attributes) all work correctly.

  Flavour 3: hand-rolled `Lexer` subclasses (json, ...)

    Don't inherit from `RegexLexer` at all; no `_tokens`, no resumable
    state. We re-lex the line in isolation each call and return a
    sentinel "no carryover" stack. Cross-line constructs in such
    lexers are not preserved across editor blocks. Acceptable because
    the few lexers that fall here have no multi-line state (JSON's
    grammar is line-local).

  Flavour 4: `RegexLexer` subclasses that OVERRIDE
            `get_tokens_unprocessed` (elixir, common lisp, prolog
            in some versions, ...)

    These lexers run `RegexLexer.get_tokens_unprocessed` to get raw
    tokens, then post-process — e.g. ElixirLexer turns `Name` into
    `Keyword.Declaration` based on the value. Our `_run_regex_driver`
    bypasses the override (it walks `lexer._tokens` directly), so the
    post-processing is lost and the editor sees raw `Name` everywhere
    while the preview gets the reclassified colours.

    Detected via `type(lexer).get_tokens_unprocessed is not
    RegexLexer.get_tokens_unprocessed`. Treated like flavour 3:
    per-line lex via the lexer's own method, no state carry-over.

Alternatives considered (rejected):

  - Re-lex from the fence-open line every time (no state tracking).
    O(block_size) per keystroke — janky on large blocks.
  - Monkey-patch `RegexLexer.get_tokens_unprocessed`. Same amount of
    duplicated code, but with additional process-global side effects.
  - `sys.settrace` to read the generator's frame. Slow, fragile.
  - Use Pygments' built-in formatters and parse their output. Adds
    an HTML pass per keystroke; doesn't expose end-state either.

If Pygments ever exposes end-state via a public API
(`tokens, state = lexer.lex_line(...)`), delete `_run_regex_driver`
and call through. The ExtendedRegexLexer path can stay as-is — it's
already using Pygments' own driver.

See `local/plans/fenced-code-highlighting-pygments.md` for the full
design discussion.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import functools

from pygments.lexer import ExtendedRegexLexer, RegexLexer
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
    raw_tokens, end_stack = _lex_line(lexer, text + "\n", prev_state._opaque)
    spans: list[Span] = []
    for pos, tok_type, tok_text in raw_tokens:
        if pos >= text_len:
            continue   # synthetic-newline token
        end = min(pos + len(tok_text), text_len)
        if end <= pos:
            continue
        styling = _resolve_styling(style, tok_type)
        spans.append(Span(
            start=pos,
            length=end - pos,
            color=_hex(styling.get("color")),
            bgcolor=_hex(styling.get("bgcolor")),
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


_NO_CARRYOVER_STATE = ("__no_carryover__",)


def _lex_line(lexer, text, in_stack):
    """Tokenize one line, resuming from `in_stack`, returning
    (tokens, final_stack).

    Dispatches on the lexer's flavour. See the "Acknowledged smell"
    block at the top of this module for why each path looks different.
    """
    if isinstance(lexer, ExtendedRegexLexer):
        # See "Acknowledged smell" above: ExtendedRegexLexer subclasses
        # use lexer-specific LexerContext subclasses (e.g. YamlLexerContext)
        # whose extra fields its callbacks read. Constructing a generic
        # LexerContext crashes mid-callback. Lex this line in isolation
        # with no context; Pygments constructs the right subclass.
        tokens = list(lexer.get_tokens_unprocessed(text))
        return tokens, _NO_CARRYOVER_STATE
    if isinstance(lexer, RegexLexer):
        # Some RegexLexer subclasses (ElixirLexer, CommonLispLexer, ...)
        # override get_tokens_unprocessed to post-process the parent's
        # token stream — e.g. reclassifying Name -> Keyword.Declaration
        # based on value. Our driver walks `_tokens` directly and would
        # bypass that override. Detect it and fall back to per-line.
        if type(lexer).get_tokens_unprocessed is not RegexLexer.get_tokens_unprocessed:
            tokens = list(lexer.get_tokens_unprocessed(text))
            return tokens, _NO_CARRYOVER_STATE
        return _run_regex_driver(lexer, text, in_stack)
    # Hand-rolled Lexer subclass — no `_tokens`, no resumable state.
    # Lex this line in isolation and return a sentinel so we don't
    # try to resume from it on the next call.
    tokens = list(lexer.get_tokens_unprocessed(text))
    return tokens, _NO_CARRYOVER_STATE


def _run_regex_driver(lexer, text, in_stack):
    """RegexLexer-flavour driver: faithful copy of
    `RegexLexer.get_tokens_unprocessed`'s match loop, exposing the final
    stack. See "Acknowledged smell" at the top of this module."""
    if in_stack == _NO_CARRYOVER_STATE:
        in_stack = ("root",)
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
