"""Tests for the public ``markdown_editor.plugins`` shim.

This is the import path plugin authors should use. It re-exports the
stable API surface from the internal
:mod:`markdown_editor.markdown6.plugins.api` module so plugins don't
have to know about the editor's internal package layout.
"""

from __future__ import annotations

import pytest

import markdown_editor.plugins as shim
from markdown_editor.markdown6.plugins import api as internal

# ---------------------------------------------------------------------------
# Required exports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    # Registration decorators
    "register_action",
    "register_text_transform",
    "register_panel",
    "register_fence",
    "register_exporter",
    "register_markdown_extension",
    # Lifecycle signal decorators
    "on_save",
    "on_content_changed",
    "on_file_opened",
    "on_file_closed",
    # Document access + storage (stable)
    "get_active_document",
    "get_all_documents",
    "plugin_settings",
    # Document handle type (for type hints in plugin code)
    "DocumentHandle",
    # Escape hatches (opt-in; not stable)
    "get_app_context",
    "get_main_window",
])
def test_shim_exports(name: str) -> None:
    assert hasattr(shim, name), f"shim missing export: {name!r}"


def test_shim_decorators_are_internal_objects() -> None:
    """Each shim symbol must point at the same object as the internal
    api module — this is what makes the shim a true re-export rather
    than an independently-evolving copy."""
    for name in [
        "register_action",
        "register_text_transform",
        "register_panel",
        "register_fence",
        "register_exporter",
        "register_markdown_extension",
        "on_save",
        "on_content_changed",
        "on_file_opened",
        "on_file_closed",
        "get_active_document",
        "get_all_documents",
        "plugin_settings",
        "get_app_context",
        "get_main_window",
    ]:
        assert getattr(shim, name) is getattr(internal, name), \
            f"shim.{name} is not the same object as internal api.{name}"


def test_shim_does_not_re_export_internals() -> None:
    """Internal-only names (registry singletons, helpers prefixed with
    `_`) must NOT be re-exported — they're not part of the contract.
    """
    for name in ["_REGISTRY", "_set_active_document_provider",
                 "_set_current_plugin_name", "_validate_place"]:
        assert not hasattr(shim, name), (
            f"shim should not re-export internal {name!r}"
        )


def test_decorator_via_shim_works() -> None:
    """End-to-end: registering through the shim populates the same
    underlying registry the editor reads from."""
    internal._REGISTRY.clear()
    try:
        @shim.register_action(id="shim.test", label="Via shim")
        def handler():
            pass
        ids = [a.id for a in internal._REGISTRY.actions()]
        assert "shim.test" in ids
    finally:
        internal._REGISTRY.clear()


def test_shim_has_all_attribute() -> None:
    """``__all__`` lets ``from markdown_editor.plugins import *`` work
    cleanly and gives IDEs a clear public surface to autocomplete."""
    assert hasattr(shim, "__all__")
    assert isinstance(shim.__all__, (list, tuple))
    # Every name in __all__ must actually be exported
    for name in shim.__all__:
        assert hasattr(shim, name), f"__all__ lists {name!r} but it's not exported"
