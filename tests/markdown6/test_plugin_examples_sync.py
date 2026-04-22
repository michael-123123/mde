"""The example plugins under ``docs/plugins-examples/`` and the test
fixtures under ``tests/markdown6/fixtures/plugins/`` must stay
byte-identical.

Why two copies: tests should not reach outside ``tests/`` for
fixtures (keeps the suite self-contained and hermetic), but the
``docs/plugins-examples/`` copies double as user-facing reference
material that must stay valid against the current API. If the two
drift, either the docs freeze while the tests keep working, or the
tests keep passing against an outdated example. This test fails
loudly on any divergence so authors know to update both.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_DOCS_DIR = _ROOT / "docs" / "plugins-examples"
_FIXTURES_DIR = _ROOT / "tests" / "markdown6" / "fixtures" / "plugins"
_PLUGIN_NAMES = ("em_dash_to_hyphen", "stamp", "wordcount")


@pytest.mark.parametrize("name", _PLUGIN_NAMES)
def test_example_plugin_matches_test_fixture(name: str) -> None:
    docs_subdir = _DOCS_DIR / name
    fixture_subdir = _FIXTURES_DIR / name
    assert docs_subdir.is_dir(), f"missing example dir: {docs_subdir}"
    assert fixture_subdir.is_dir(), f"missing fixture dir: {fixture_subdir}"

    cmp = filecmp.dircmp(
        str(docs_subdir), str(fixture_subdir),
        ignore=["__pycache__"],
    )

    def _walk(d: filecmp.dircmp, path: str = "") -> list[str]:
        out: list[str] = []
        for f in d.left_only:
            out.append(f"only in example/: {path}{f}")
        for f in d.right_only:
            out.append(f"only in fixture/: {path}{f}")
        for f in d.diff_files:
            out.append(f"content differs: {path}{f}")
        for f in d.funny_files:
            out.append(f"could not compare: {path}{f}")
        for sub_name, sub_cmp in d.subdirs.items():
            out.extend(_walk(sub_cmp, f"{path}{sub_name}/"))
        return out

    differences = _walk(cmp)
    assert not differences, (
        f"docs/plugins-examples/{name}/ and "
        f"tests/markdown6/fixtures/plugins/{name}/ drifted:\n  "
        + "\n  ".join(differences)
    )
