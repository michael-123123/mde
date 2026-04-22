"""Directory of builtin plugins shipped with the editor.

Each subdirectory here is a plugin package consumed at runtime by the
plugin loader (``markdown6/plugins/loader.py``). The subdirectories are
deliberately NOT Python packages themselves — they are loaded via
``importlib.util.spec_from_file_location`` so they don't get imported
twice (once by the Python import machinery, once by the loader) and
so accidental ``import markdown_editor.markdown6.builtin_plugins.foo``
doesn't trigger plugin registration side-effects.
"""
