"""Tests for callout extensions (GitHub-style and admonition-style)."""

import markdown

from markdown_editor.markdown6.extensions.callouts import (CalloutExtension,
                                                           get_callout_css)


def _convert(text):
    """Helper: convert markdown text with CalloutExtension + admonition."""
    md = markdown.Markdown(extensions=[CalloutExtension(), 'admonition'])
    return md.convert(text)


class TestGitHubStyleCallouts:
    """Existing GitHub-style > [!TYPE] callouts."""

    def test_note_callout(self):
        result = _convert("> [!NOTE]\n> This is a note")
        assert 'callout-note' in result
        assert 'This is a note' in result

    def test_warning_callout(self):
        result = _convert("> [!WARNING]\n> Be careful")
        assert 'callout-warning' in result
        assert 'Be careful' in result

    def test_tip_callout(self):
        result = _convert("> [!TIP]\n> A helpful tip")
        assert 'callout-tip' in result
        assert 'A helpful tip' in result


class TestAdmonitionStyleCallouts:
    """Python-Markdown !!! admonition syntax."""

    def test_note_with_title(self):
        result = _convert('!!! note "My Title"\n    This is a note.')
        assert 'admonition note' in result
        assert 'My Title' in result
        assert 'This is a note.' in result

    def test_warning_no_title(self):
        result = _convert('!!! warning\n    Be careful here.')
        assert 'admonition warning' in result
        assert 'Be careful here.' in result

    def test_tip_with_title(self):
        result = _convert('!!! tip "Pro Tip"\n    Helpful tips go here.')
        assert 'admonition tip' in result
        assert 'Pro Tip' in result
        assert 'Helpful tips go here.' in result

    def test_multiple_admonition_types(self):
        """All types listed in the README should work."""
        types = [
            'note', 'warning', 'tip', 'important', 'caution',
            'abstract', 'info', 'success', 'question',
            'failure', 'danger', 'bug', 'example', 'quote',
        ]
        for t in types:
            result = _convert(f'!!! {t}\n    Content for {t}.')
            assert 'admonition' in result, f"admonition class missing for type: {t}"
            assert f'Content for {t}.' in result, f"content missing for type: {t}"

    def test_multiline_content(self):
        text = '!!! note "Title"\n    Line one.\n\n    Line two.'
        result = _convert(text)
        assert 'Line one.' in result
        assert 'Line two.' in result


class TestCalloutCSS:
    """CSS includes admonition styles."""

    def test_light_css_has_admonition(self):
        css = get_callout_css(dark_mode=False)
        assert '.admonition' in css

    def test_dark_css_has_admonition(self):
        css = get_callout_css(dark_mode=True)
        assert '.admonition' in css
