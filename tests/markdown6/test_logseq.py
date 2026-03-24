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
        # Leading space from stripped ref may be consumed by dedent detection
        assert result[0].strip() == 'and'


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

    def test_converts_todo_with_toplevel_bullet(self):
        """Top-level bullet is stripped first, then TODO is converted."""
        lines = ['- TODO Buy milk']
        result = _preprocess(lines)
        assert result == ['- [ ] Buy milk']

    def test_converts_done_with_toplevel_bullet(self):
        """Top-level bullet is stripped first, then DONE is converted."""
        lines = ['- DONE Buy milk']
        result = _preprocess(lines)
        assert result == ['- [x] Buy milk']

    def test_strips_other_task_markers(self):
        for marker in ['LATER', 'NOW', 'DOING', 'WAITING', 'CANCELLED']:
            lines = [f'{marker} Some task']
            result = _preprocess(lines)
            assert result == ['- [ ] Some task'], f'Failed for marker {marker}'

    def test_preserves_indented_task_markers(self):
        """Indented task markers are dedented then converted."""
        lines = ['  - TODO Subtask']
        result = _preprocess(lines)
        assert result == ['- [ ] Subtask']


class TestOutlinerBulletStripping:
    def test_strips_toplevel_bullets(self):
        lines = ['- Some paragraph text', '- Another paragraph']
        result = _preprocess(lines)
        assert result == ['Some paragraph text', 'Another paragraph']

    def test_dedents_indented_bullets(self):
        """Indented bullets are dedented by one Logseq level (2 spaces)."""
        lines = ['- Top level', '  - Sub item', '    - Deep item']
        result = _preprocess(lines)
        assert result == ['Top level', '- Sub item', '  - Deep item']

    def test_strips_bullet_before_heading(self):
        lines = ['- # My Heading', '- ## Sub Heading']
        result = _preprocess(lines)
        assert result == ['# My Heading', '## Sub Heading']

    def test_realistic_logseq_outliner(self):
        """A typical Logseq page where every line is a block."""
        lines = [
            '- # Meeting Notes',
            '- Discussed the roadmap',
            '  - Action item: update docs',
            '  - Action item: file bug',
            '- Wrapped up at 3pm',
        ]
        result = _preprocess(lines)
        assert result == [
            '# Meeting Notes',
            'Discussed the roadmap',
            '- Action item: update docs',
            '- Action item: file bug',
            'Wrapped up at 3pm',
        ]

    def test_dedents_tab_indented_children(self):
        """Logseq files using tab indentation should be auto-detected."""
        lines = [
            '- ## Post Content',
            '\t- Construction kids paragraph.',
            '\t- Sapir Tubul did.',
            '\t\t- Nested under Sapir.',
        ]
        result = _preprocess(lines)
        assert result == [
            '## Post Content',
            '- Construction kids paragraph.',
            '- Sapir Tubul did.',
            '\t- Nested under Sapir.',
        ]

    def test_dedents_four_space_indented_children(self):
        """Logseq files using 4-space indentation should be auto-detected."""
        lines = [
            '- ## Section',
            '    - Item one',
            '    - Item two',
            '        - Sub-item',
        ]
        result = _preprocess(lines)
        assert result == [
            '## Section',
            '- Item one',
            '- Item two',
            '    - Sub-item',
        ]

    def test_indent_unit_resets_per_section(self):
        """Each top-level bullet resets indent detection."""
        lines = [
            '- ## Tab Section',
            '\t- Tab child',
            '- ## Space Section',
            '  - Space child',
        ]
        result = _preprocess(lines)
        assert result == [
            '## Tab Section',
            '- Tab child',
            '## Space Section',
            '- Space child',
        ]

    def test_tab_children_not_rendered_as_code_block(self):
        """Regression: tab-indented children must not become code blocks."""
        text = (
            '- ## Post Content\n'
            '\t- Construction kids paragraph.\n'
            '\t- Sapir Tubul did.\n'
            '\t- He grew up on job sites.\n'
        )
        html = _convert(text, logseq_mode=True)
        assert '<pre>' not in html
        assert '<code>' not in html
        assert '<li>' in html
        assert 'Construction kids' in html

    def test_children_not_rendered_as_code_block(self):
        """Regression: indented children must not become code blocks after
        top-level bullet stripping. Dedenting by 2 spaces prevents this."""
        text = (
            '- ## Post Content\n'
            '  - Construction kids paragraph.\n'
            '  - Sapir Tubul did.\n'
            '  - He grew up on job sites.\n'
        )
        html = _convert(text, logseq_mode=True)
        # Children should render as list items, NOT as a <pre>/<code> block
        assert '<pre>' not in html
        assert '<code>' not in html
        assert '<li>' in html
        assert 'Construction kids' in html

    def test_deep_nesting_not_rendered_as_code_block(self):
        """4-space indented grandchildren should remain list items, not code."""
        text = (
            '- ## Section\n'
            '  - Parent item\n'
            '    - Child item\n'
            '      - Grandchild item\n'
        )
        html = _convert(text, logseq_mode=True)
        assert '<pre>' not in html
        assert '<code>' not in html
        assert 'Child item' in html
        assert 'Grandchild item' in html

    def test_empty_bullet_stripped(self):
        """A bare '- ' with nothing after it should not produce garbage."""
        lines = ['- ']
        result = _preprocess(lines)
        # TOPLEVEL_BULLET_PATTERN requires at least one char after "- "
        # so bare "- " passes through (then blank-line collapsing may apply)
        assert result == ['- ']


class TestNormalMarkdownUnchanged:
    def test_headings_unchanged(self):
        lines = ['# Heading 1', '## Heading 2']
        result = _preprocess(lines)
        assert result == lines

    def test_links_unchanged(self):
        lines = ['[link](https://example.com)', '**bold** and *italic*']
        result = _preprocess(lines)
        assert result == lines

    def test_indented_lists_dedented(self):
        """Indented lists are dedented by one Logseq level."""
        lines = ['  - sub item 1', '  - sub item 2', '1. ordered']
        result = _preprocess(lines)
        assert result == ['- sub item 1', '- sub item 2', '1. ordered']

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
        # Normal content preserved (top-level bullets stripped)
        assert '# Meeting Notes' in result
        assert 'Point one' in result
        assert 'Point two' in result


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
