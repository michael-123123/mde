"""Entry point for pyside6-deploy. Launches the GUI via the package main()."""
import os

import pygments.plugin as _pp

# Runtime patches that must be in place before anything triggers Qt or pygments
# plugin discovery. Both have to happen at import time of this launcher, but
# `from markdown_editor...` is deferred into the `__main__` guard below so that
# (a) all top-level imports come first (ruff E402) and (b) the patches are
# applied before that import chain pulls in pygments.lexers / Qt.

# Force the bundled (or system) fontconfig to look at the system's /etc/fonts
# config dir. Without this, the conda-bundled libfontconfig points at its
# original conda prefix which doesn't exist at runtime, and Qt ends up picking
# a fallback font that misses color emoji (used by the activity bar) and
# renders the editor in a different monospace than the source launch.
os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")

# Neutralize Pygments entry-point plugin discovery before any pygments lexer
# import. The build env may register plugin lexers/formatters
# (ipython_pygments_lexers, mako, myst_nb, ...) that we don't bundle; without
# this patch, pygments tries to import them at runtime and raises
# ModuleNotFoundError. We only ship the built-in pygments lexers.
_pp.find_plugin_lexers = lambda: iter([])
_pp.find_plugin_formatters = lambda: iter([])
_pp.find_plugin_styles = lambda: iter([])
_pp.find_plugin_filters = lambda: iter([])


if __name__ == "__main__":
    import sys

    from markdown_editor.markdown6.markdown_editor_cli import main

    sys.exit(main())
