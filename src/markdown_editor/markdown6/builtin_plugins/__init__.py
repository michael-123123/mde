"""Directory reserved for plugins shipped with the editor.

Currently empty — nothing is bundled by default. The plugin loader
still scans this directory at startup (``markdown6/plugins/loader.py``),
so dropping a plugin package in here makes it a built-in again.

Example plugins (that used to live here) now live under
``docs/plugins-examples/`` — they are not loaded automatically; users
opt in by copying them into ``<config_dir>/plugins/``.

Any subdirectories added here are deliberately NOT Python packages
themselves — they are loaded via ``importlib.util.spec_from_file_location``
so they don't get imported twice (once by the Python import machinery,
once by the loader) and so accidental
``import markdown_editor.markdown6.builtin_plugins.foo`` doesn't
trigger plugin registration side-effects.
"""
