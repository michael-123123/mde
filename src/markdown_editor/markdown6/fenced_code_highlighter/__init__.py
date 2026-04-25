"""Editor-side syntax highlighting for fenced code blocks.

Public surface re-exported here. Consumers must NOT import from
`_pygments_backend` or any other submodule directly.
"""

from markdown_editor.markdown6.fenced_code_highlighter._pygments_backend import (  # noqa: F401
    available_schemes,
    highlight_line,
    initial_state,
    is_language_supported,
    scheme_defaults,
)
from markdown_editor.markdown6.fenced_code_highlighter.api import (  # noqa: F401
    DEFAULT_SCHEME_DARK,
    DEFAULT_SCHEME_LIGHT,
    LineResult,
    SchemeDefaults,
    Span,
    State,
)
