"""Entry point for pyside6-deploy. Launches the GUI via the package main()."""
# Force the bundled (or system) fontconfig to look at the system's /etc/fonts
# config dir. Without this, the conda-bundled libfontconfig points at its
# original conda prefix which doesn't exist at runtime, and Qt ends up picking
# a fallback font that misses color emoji (used by the activity bar) and
# renders the editor in a different monospace than the source launch.
import os
os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")

# Neutralize Pygments entry-point plugin discovery before any pygments import.
# The build env may register plugin lexers/formatters (ipython_pygments_lexers,
# mako, myst_nb, ...) that we don't bundle; without this patch, pygments tries
# to import them at runtime and raises ModuleNotFoundError. We only ship the
# built-in pygments lexers, which cover all real use in this app.
import pygments.plugin as _pp
_pp.find_plugin_lexers = lambda: iter([])
_pp.find_plugin_formatters = lambda: iter([])
_pp.find_plugin_styles = lambda: iter([])
_pp.find_plugin_filters = lambda: iter([])

import sys

from markdown_editor.markdown6.markdown_editor_cli import main

if __name__ == "__main__":
    sys.exit(main())
