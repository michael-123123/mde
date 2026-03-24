"""Tests for Logseq preview mode preprocessing."""

import markdown
from markdown_editor.markdown6.markdown_extensions import LogseqExtension


def _convert(text, logseq_mode=True):
    """Helper: convert markdown text with LogseqExtension."""
    md = markdown.Markdown(extensions=[LogseqExtension()])
    md.logseq_mode = logseq_mode
    return md.convert(text)


def _preprocess(lines, logseq_mode=True):
    """Helper: run only the preprocessor, return processed lines."""
    md = markdown.Markdown(extensions=[LogseqExtension()])
    md.logseq_mode = logseq_mode
    preprocessor = md.preprocessors['logseq']
    return preprocessor.run(lines)


class TestNoopWhenDisabled:
    def test_noop_when_disabled(self):
        lines = [
            'id:: abc-123',
            'Some text ((12345678-1234-1234-1234-123456789abc))',
            'TODO Buy milk',
            '{{query (and [[tag]])}}'
        ]
        result = _preprocess(lines, logseq_mode=False)
        assert result == lines


class TestPropertyStripping:
    def test_strips_property_lines(self):
        lines = ['id:: abc-123', 'Normal text', 'tags:: foo, bar']
        result = _preprocess(lines)
        assert 'Normal text' in result
        assert not any('id::' in line for line in result)
        assert not any('tags::' in line for line in result)

    def test_strips_multiline_properties(self):
        lines = [
            'id:: 12345678-1234-1234-1234-123456789abc',
            'collapsed:: true',
            'tags:: foo, bar',
            '',
            'Actual content here',
        ]
        result = _preprocess(lines)
        assert 'Actual content here' in result
        assert not any('::' in line for line in result if line.strip())

    def test_preserves_properties_in_code_blocks(self):
        lines = [
            '```',
            'id:: abc-123',
            'key:: value',
            '```',
        ]
        result = _preprocess(lines)
        assert 'id:: abc-123' in result
        assert 'key:: value' in result


class TestBlockReferences:
    def test_strips_block_references(self):
        lines = ['See ((12345678-1234-1234-1234-123456789abc)) for details']
        result = _preprocess(lines)
        assert result == ['See  for details']

    def test_strips_multiple_block_references(self):
        lines = ['((12345678-1234-1234-1234-123456789abc)) and ((abcdefab-abcd-abcd-abcd-abcdefabcdef))']
        result = _preprocess(lines)
        assert result == [' and ']


class TestMacroStripping:
    def test_strips_embed_macros(self):
        lines = ['{{embed ((12345678-1234-1234-1234-123456789abc))}}']
        result = _preprocess(lines)
        # Line should be empty or stripped
        assert not any(line.strip() for line in result)

    def test_strips_page_embeds(self):
        lines = ['{{embed [[some page]]}}']
        result = _preprocess(lines)
        assert not any('embed' in line for line in result)

    def test_strips_query_macros(self):
        lines = ['{{query (and [[tag]] (task todo))}}']
        result = _preprocess(lines)
        assert not any('query' in line for line in result)

    def test_strips_generic_macros(self):
        lines = ['{{renderer :todomaster}}']
        result = _preprocess(lines)
        assert not any('renderer' in line for line in result)


class TestTaskMarkers:
    def test_converts_todo_to_checkbox(self):
        lines = ['TODO Buy milk']
        result = _preprocess(lines)
        assert result == ['- [ ] Buy milk']

    def test_converts_done_to_checkbox(self):
        lines = ['DONE Buy milk']
        result = _preprocess(lines)
        assert result == ['- [x] Buy milk']

    def test_converts_todo_with_bullet(self):
        lines = ['- TODO Buy milk']
        result = _preprocess(lines)
        assert result == ['- [ ] Buy milk']

    def test_converts_done_with_bullet(self):
        lines = ['- DONE Buy milk']
        result = _preprocess(lines)
        assert result == ['- [x] Buy milk']

    def test_strips_other_task_markers(self):
        for marker in ['LATER', 'NOW', 'DOING', 'WAITING', 'CANCELLED']:
            lines = [f'{marker} Some task']
            result = _preprocess(lines)
            assert result == ['- [ ] Some task'], f'Failed for marker {marker}'

    def test_preserves_indented_task_markers(self):
        lines = ['  - TODO Subtask']
        result = _preprocess(lines)
        assert result == ['  - [ ] Subtask']


class TestNormalMarkdownUnchanged:
    def test_headings_unchanged(self):
        lines = ['# Heading 1', '## Heading 2']
        result = _preprocess(lines)
        assert result == lines

    def test_links_unchanged(self):
        lines = ['[link](https://example.com)', '**bold** and *italic*']
        result = _preprocess(lines)
        assert result == lines

    def test_lists_unchanged(self):
        lines = ['- item 1', '- item 2', '1. ordered']
        result = _preprocess(lines)
        assert result == lines

    def test_code_blocks_unchanged(self):
        lines = ['```python', 'print("hello")', '```']
        result = _preprocess(lines)
        assert result == lines


class TestMixedContent:
    def test_realistic_logseq_page(self):
        lines = [
            'id:: 12345678-1234-1234-1234-123456789abc',
            'tags:: journal, daily',
            '',
            '# Meeting Notes',
            '',
            'TODO Follow up with team',
            'DONE Write meeting summary',
            '',
            'Key points from ((abcdefab-abcd-abcd-abcd-abcdefabcdef)):',
            '- Point one',
            '- Point two',
            '',
            '{{query (and [[meetings]] (task todo))}}',
        ]
        result = _preprocess(lines)
        # Properties stripped
        assert not any('id::' in line for line in result)
        assert not any('tags::' in line for line in result)
        # Task markers converted
        assert '- [ ] Follow up with team' in result
        assert '- [x] Write meeting summary' in result
        # Block ref stripped
        assert any('Key points from ' in line for line in result)
        assert not any('((' in line for line in result)
        # Query stripped
        assert not any('query' in line for line in result)
        # Normal content preserved
        assert '# Meeting Notes' in result
        assert '- Point one' in result
        assert '- Point two' in result


class TestIntegrationWithMarkdownConvert:
    def test_full_pipeline_produces_clean_html(self):
        text = (
            'id:: 12345678-1234-1234-1234-123456789abc\n'
            '\n'
            '# My Page\n'
            '\n'
            'TODO Buy groceries\n'
            'DONE Clean house\n'
            '\n'
            'Normal paragraph here.\n'
        )
        html = _convert(text, logseq_mode=True)
        # Properties should not appear
        assert 'id::' not in html
        # Heading should render
        assert '<h1>' in html or 'My Page' in html
        # Normal paragraph should be present
        assert 'Normal paragraph' in html

    def test_full_pipeline_noop_when_disabled(self):
        text = 'id:: 12345678-1234-1234-1234-123456789abc\nSome text\n'
        html = _convert(text, logseq_mode=False)
        # Property line should still be in the output when disabled
        assert 'id::' in html
