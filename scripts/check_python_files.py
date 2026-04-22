#!/usr/bin/env python
"""Smoke-check every Python source file tracked by git.

For each file in `git ls-files '*.py'` we run two checks:

1. **AST parse** — `ast.parse()` reports any syntax error without
   executing the file.
2. **Import** — `importlib.util.spec_from_file_location` +
   `exec_module` runs the file's top-level code. This catches import
   errors, circular imports, runtime failures in module-level code,
   etc. that a pure syntax check misses.

Plugin example + test-fixture files under ``docs/plugins-examples/``
and ``tests/markdown6/fixtures/plugins/`` are deliberately skipped
for the import check: those files are designed to be loaded by
``markdown_editor.markdown6.plugins.loader.load_plugin``, which
sets the ``_CURRENT_PLUGIN_NAME`` context and handles id-collision
across the loader's curated imports. A naive
``spec_from_file_location`` on them in this same process would
re-register globally and collide — not a real bug, just the wrong
entry point. The plugin loader's behavior is covered by its own
tests (``tests/markdown6/test_plugin_loader.py``, etc.).

Usage::

    python scripts/check_python_files.py

Exits non-zero if any file fails either check. No failures and the
script prints a one-line "Checked N files" summary followed by the
AST and import failure counts (both 0 in a clean tree).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover — tqdm is optional
    def tqdm(iterable, **_kwargs):
        return iterable


# Plugin-fixture / example files are designed to be loaded by the
# plugin loader (which sets the ``_CURRENT_PLUGIN_NAME`` context and
# handles id collisions across repeated imports). Importing them
# naively in this same process would re-register globally and
# collide. Excluded from the import check; covered separately by
# the plugin-loader test suite.
EXCLUDED_IMPORT_PREFIXES = (
    "docs/plugins-examples/",
    "tests/markdown6/fixtures/plugins/",
)


def main() -> int:
    files = subprocess.check_output(
        ["git", "ls-files", "*.py"]
    ).decode().splitlines()
    files = [f for f in files if f]

    ast_fail: list[tuple[str, str]] = []
    imp_fail: list[tuple[str, str]] = []
    imp_skipped: list[str] = []

    for f in tqdm(files, desc="ast+import", unit="file"):
        try:
            with open(f) as h:
                ast.parse(h.read())
        except BaseException as e:  # noqa: BLE001 — parse failures bubble everything
            ast_fail.append((f, f"{type(e).__name__}: {e}"))

        if f.startswith(EXCLUDED_IMPORT_PREFIXES):
            imp_skipped.append(f)
            continue

        try:
            mod_name = "mde_verify_" + f.replace("/", "_").replace(".", "_")
            spec = spec_from_file_location(mod_name, f)
            if spec is None or spec.loader is None:
                imp_fail.append((f, "could not build import spec"))
                continue
            mod = module_from_spec(spec)
            # Insert into sys.modules before exec so that code in the
            # module that does sys.modules[__name__] (common for
            # class decorators, dataclass reflection, etc.) finds
            # itself.
            sys.modules[mod_name] = mod
            try:
                spec.loader.exec_module(mod)
            finally:
                sys.modules.pop(mod_name, None)
        except BaseException as e:  # noqa: BLE001 — import failures bubble everything
            imp_fail.append((f, f"{type(e).__name__}: {e}"))

    print(f"Checked {len(files)} python files tracked by git")
    print(f"AST parse failures: {len(ast_fail)}")
    for f, e in ast_fail:
        print(f"  {f}")
        print(f"    {e}")
    print(
        f"Import failures: {len(imp_fail)} "
        f"(skipped {len(imp_skipped)} plugin-fixture files)"
    )
    for f, e in imp_fail:
        print(f"  {f}")
        print(f"    {e}")

    return 1 if (ast_fail or imp_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
