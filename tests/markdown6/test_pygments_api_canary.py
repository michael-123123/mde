"""Canary tests that pin Pygments internals our backend relies on.

These tests guard against Pygments changing the data/API shapes that
`fenced_code_highlighter._pygments_backend._run_driver` assumes. If any
of these fail after a Pygments version bump, DO NOT monkey-patch the
tests — re-validate `_run_driver` against the new Pygments and update
both the driver and this canary together.

Background: see the "Acknowledged smell" block in `_pygments_backend.py`
and `local/plans/fenced-code-highlighting-pygments.md`.
"""

import inspect
import re

import pytest
from pygments.lexer import RegexLexer
from pygments.lexers import get_lexer_by_name
from pygments.lexers.python import PythonLexer
from pygments.token import _TokenType


def test_get_tokens_unprocessed_accepts_stack_kwarg():
    """The entire checkpointing approach hinges on this kwarg being public."""
    sig = inspect.signature(RegexLexer.get_tokens_unprocessed)
    assert "stack" in sig.parameters
    assert sig.parameters["stack"].default == ("root",)


def test_lexer_tokens_attribute_is_dict_of_state_lists():
    """Our driver iterates `lexer._tokens[state_name]` as a list of rules."""
    lex = PythonLexer()
    assert hasattr(lex, "_tokens")
    assert isinstance(lex._tokens, dict)
    assert "root" in lex._tokens
    assert isinstance(lex._tokens["root"], list)
    assert len(lex._tokens["root"]) > 0


def test_each_rule_is_a_three_tuple():
    """Rule shape: (compiled_regex_match, action, new_state)."""
    lex = PythonLexer()
    first_rule = lex._tokens["root"][0]
    assert isinstance(first_rule, tuple)
    assert len(first_rule) == 3

    rexmatch, action, new_state = first_rule
    # rexmatch is the bound `match` method of a compiled pattern
    assert callable(rexmatch)
    # action is either a _TokenType or a callable (bygroups / using / ...)
    assert isinstance(action, _TokenType) or callable(action)
    # new_state is None, a string, an int, a tuple, or '#push' / '#pop'
    assert new_state is None or isinstance(new_state, (str, int, tuple))


def test_python_lexer_has_expected_states():
    """Our docstring test assumes 'tdqs' (triple-double-string) and
    'tsqs' (triple-single-string) states exist in the Python lexer."""
    lex = PythonLexer()
    assert "tdqs" in lex._tokens
    assert "tsqs" in lex._tokens


def test_token_type_importable():
    """`_TokenType` is how we identify "this action is a token type" vs
    "this action is a callable that yields tokens" in the driver."""
    # The import at module top-level is itself the assertion; this test
    # just documents the dependency.
    assert _TokenType is not None


def test_stack_kwarg_actually_threads_state():
    """End-to-end: passing stack=('root','tdqs') into a Python lexer
    tokenizes a plain word as String.Double (mid-docstring). If this
    breaks, the whole plan is invalid."""
    lex = PythonLexer()
    tokens = list(lex.get_tokens_unprocessed("world", stack=("root", "tdqs")))
    # Exactly one token of type String.Double covering 'world'
    assert len(tokens) == 1
    pos, tok_type, text = tokens[0]
    assert pos == 0
    assert text == "world"
    # Token.Literal.String.Double should be in its ancestry chain
    from pygments.token import String
    assert String in tok_type.split()


def test_class_not_found_is_the_error_get_lexer_raises():
    """`_get_lexer` catches `ClassNotFound` for unknown languages."""
    from pygments.util import ClassNotFound
    with pytest.raises(ClassNotFound):
        get_lexer_by_name("klingon-not-a-real-language")
