"""Tests for Logseq preview mode preprocessing."""

import markdown

from markdown_editor.markdown6.extensions import LogseqExtension
from markdown_editor.markdown6.html_renderer_core import build_markdown


def _convert(text, logseq_mode=True):
    """Helper: convert markdown text with LogseqExtension."""
    md = markdown.Markdown(extensions=[LogseqExtension()])
    md.logseq_mode = logseq_mode
    return md.convert(text)


def _convert_full_stack(text, logseq_mode=True):
    """Helper: convert through the FULL extension stack the live preview
    uses. Some bugs only appear with the full stack — e.g. interactions
    between LogseqExtension and SourceLineExtension's line-marker
    comments — so we need a test path that exercises the real pipeline."""
    md = build_markdown()
    md.reset()
    md._pending_diagrams = []
    md.mermaid_dark_mode = False
    md.graphviz_dark_mode = False
    md.graphviz_base_path = None
    md.logseq_mode = logseq_mode
    return md.convert(text)


def _pre_blocks(html: str) -> list[str]:
    """Extract a tag-stripped form of every <pre>...</pre> block.
    Used to assert "this fence body actually rendered as a code block",
    rather than the weaker "the html contains the substring somewhere".
    Pygments may syntax-highlight inside <pre>, splitting content into
    nested <span>s — we strip those before returning."""
    import re
    blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL)
    # Strip inner tags so the test can check raw content.
    return [re.sub(r"<[^>]+>", "", b) for b in blocks]


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


class TestBulletPrefixedCodeFence:
    """Logseq stores fenced code blocks as bullets:

        - ```
          id:: <some-uuid>
          <code line 1>
          <code line 2>
          ```

    Markdown's CommonMark rule says a fenced block opens only when the
    line starts with `\`\`\`` after at most 3 spaces. A line starting
    with ``- `\`\`\`\`\`` is a list-item bullet whose CONTENT is three
    backticks, not a fence opener — so the parser sees literal backticks
    inside `<li>` and the architecture-diagram (or whatever's in the
    block) renders flat as a paragraph.

    LogseqExtension must recognise this pattern and unwrap the bullet so
    the fence opens correctly. The Logseq `id::` line that conventionally
    follows the opener is also stripped (it's a block property, not code).
    """

    def test_bullet_prefixed_fence_renders_as_code_block(self):
        text = "\n".join([
            "- some context",
            "\t- ```",
            "\t  hello = 1",
            "\t  ```",
        ]) + "\n"
        html = _convert(text, logseq_mode=True)
        assert "<pre>" in html or "<code>" in html, (
            f"expected a <pre>/<code> block; got:\n{html}"
        )
        assert "hello = 1" in html

    def test_bullet_prefixed_fence_with_id_property(self):
        """The id:: block-property line right after the opener must not
        leak into the rendered code content."""
        text = "\n".join([
            "- top-level",
            "\t- ```",
            "\t  id:: 12625238-cf1d-46de-a67d-ed428f0aa3f4",
            "\t  greeting = \"hello\"",
            "\t  ```",
        ]) + "\n"
        html = _convert(text, logseq_mode=True)
        assert 'greeting = "hello"' in html or "greeting" in html
        # id:: block-property line should NOT appear in rendered output.
        assert "id:: 12625238" not in html

    def test_deeply_nested_bullet_fence(self):
        """LOGSEQ_EXAMPLE.md uses two-tab nesting before a fence. Verify
        the unwrapping handles arbitrary nesting depth."""
        text = "\n".join([
            "- ## Architecture",
            "\t- ### Two-piece",
            "\t\t- ```",
            "\t\t  id:: 12625238-cf1d-46de-a67d-ed428f0aa3f4",
            "\t\t  Claude Desktop -> Fusion API",
            "\t\t  ```",
        ]) + "\n"
        html = _convert(text, logseq_mode=True)
        assert "<pre>" in html or "<code>" in html
        assert "Claude Desktop" in html
        assert "id:: 12625238" not in html

    def test_language_tag_after_bullet_fence_preserved(self):
        text = "\n".join([
            "- code below",
            "\t- ```python",
            "\t  def f(): pass",
            "\t  ```",
        ]) + "\n"
        html = _convert(text, logseq_mode=True)
        assert "def f(): pass" in html
        # Either a <code class="language-python"> via codehilite or a
        # plain <pre><code>...</code></pre> via fenced_code — either is fine
        # for THIS test; what matters is the block opens.
        assert "<pre>" in html or "<code>" in html

    def test_bullet_prefixed_fence_noop_when_logseq_disabled(self):
        """When logseq_mode is OFF, the LogseqExtension must not touch
        anything — including bullet-prefixed fences. Honors the
        flag-controlled opt-in contract."""
        text = "\n".join([
            "- top",
            "\t- ```",
            "\t  hello",
            "\t  ```",
        ]) + "\n"
        # Run only LogseqPreprocessor — its output should equal input
        # (split into lines then rejoined) when the flag is off.
        result = _preprocess(text.split("\n"), logseq_mode=False)
        assert result == text.split("\n")


class TestBulletPrefixedFenceFullStack:
    """Same scenarios as TestBulletPrefixedCodeFence, but driven through
    the FULL extension stack the live preview uses. Some interactions
    between LogseqExtension and other extensions only show up here:

      - SourceLineExtension (priority 200) injects HTML comment markers
        between lines BEFORE LogseqExtension runs. Those markers can
        land inside what would have been a fence body, breaking the
        fence parsing.
      - NormalizeListIndentExtension (priority 105) rewrites bullet
        indentation BEFORE LogseqExtension's bullet-fence detection.

    These tests are the regression target for the LOGSEQ_EXAMPLE.md bug:
    the architecture diagram (a fenced code block inside an outliner
    bullet) was rendered as a flat paragraph in both normal and Logseq
    modes."""

    def test_bullet_fence_renders_as_code_in_full_stack(self):
        text = "\n".join([
            "- top-level",
            "\t- ```",
            "\t  hello = 1",
            "\t  ```",
        ]) + "\n"
        html = _convert_full_stack(text, logseq_mode=True)
        pres = _pre_blocks(html)
        assert pres, f"no <pre> block found; got: {html}"
        # The fence body MUST live inside a <pre>; just-substring-checking
        # the html lets a one-liner stray fence pass.
        assert any("hello = 1" in p for p in pres), (
            f"'hello = 1' not in any <pre> block; pres={pres}; html={html}"
        )

    def test_logseq_example_md_architecture_diagram_renders(self):
        """Mirror of the snippet in examples/LOGSEQ_EXAMPLE.md that
        ships with the editor — the original bug report."""
        text = "\n".join([
            "- ## Architecture",
            "\tid:: d1e60b6d-5d26-4d0e-89ee-cd6c8d936f5b",
            "\t- ### Two-piece design",
            "\t\tid:: 57750f44-c16f-4862-bc45-60d76372e53a",
            "\t\t- ```",
            "\t\t\tid:: 12625238-cf1d-46de-a67d-ed428f0aa3f4",
            "\t\t  Claude Desktop -> Fusion API",
            "\t\t  ```",
        ]) + "\n"
        html = _convert_full_stack(text, logseq_mode=True)
        pres = _pre_blocks(html)
        assert pres, f"no <pre> block found; got: {html}"
        assert any("Claude Desktop" in p for p in pres), (
            f"diagram body not in any <pre>; pres={pres}"
        )
        # Logseq id-properties stripped.
        assert "id:: d1e60b6d" not in html
        assert "id:: 12625238" not in html

    def test_bullet_fence_with_language_tag_full_stack(self):
        text = "\n".join([
            "- ## Code",
            "\t- ```python",
            "\t  def f(): pass",
            "\t  ```",
        ]) + "\n"
        html = _convert_full_stack(text, logseq_mode=True)
        pres = _pre_blocks(html)
        assert pres
        assert any("def" in p and ("f()" in p or "f(): pass" in p) for p in pres), (
            f"python source body not in any <pre>; pres={pres}"
        )


class TestTagsAsPageLinks:
    """`#tag` should render as a wiki-style link to a page named `tag`,
    so clicking opens `<root>/pages/tag.md` (via `_do_handle_link_click`'s
    Logseq fallback).

    Implementation: LogseqPreprocessor rewrites `#tag` to `[[tag|#tag]]`
    in pass 1. The rendering and click-handling are then handled by the
    existing WikiLinkExtension and the existing click handler — no new
    HTML element type, no new click branch.
    """

    def test_simple_tag_rewritten(self):
        result = _preprocess(["use #foo for filtering"], logseq_mode=True)
        assert result == ["use [[foo|#foo]] for filtering"]

    def test_namespaced_tag_rewritten(self):
        result = _preprocess(["#book/fiction is a category"], logseq_mode=True)
        assert result == ["[[book/fiction|#book/fiction]] is a category"]

    def test_atx_heading_not_rewritten(self):
        # Heading hashes have a space after them — the tag regex requires
        # a word char after #, so headings are not matched.
        for line in ["# Heading", "## Sub", "### Deeper", "######  many"]:
            result = _preprocess([line], logseq_mode=True)
            assert result == [line], f"heading altered: {line!r} -> {result!r}"

    def test_url_fragment_not_rewritten(self):
        # A `#` preceded by a word char (e.g. inside a URL) must not match.
        for line in [
            "see https://example.com#anchor for details",
            "[link](https://docs.com#section-1)",
            "an email#literal in source",
        ]:
            result = _preprocess([line], logseq_mode=True)
            assert result == [line], f"non-tag altered: {line!r} -> {result!r}"

    def test_double_hash_not_rewritten(self):
        # `##heading` is two consecutive hashes; the second # has a #
        # before it, so the lookbehind blocks it. The first # has nothing
        # before it but is followed by another # (not a word char), so
        # the capture group fails to match.
        result = _preprocess(["##nested"], logseq_mode=True)
        assert result == ["##nested"]

    def test_tag_inside_fenced_code_block_not_rewritten(self):
        result = _preprocess([
            "before",
            "```",
            "code with #tag inside",
            "```",
            "after",
        ], logseq_mode=True)
        assert "code with #tag inside" in result
        assert not any("[[tag|#tag]]" in line for line in result)

    def test_tag_not_rewritten_when_logseq_disabled(self):
        result = _preprocess(["#foo"], logseq_mode=False)
        assert result == ["#foo"]

    def test_full_pipeline_tag_renders_as_wiki_link(self):
        html = _convert_full_stack("use #foo here", logseq_mode=True)
        # The tag should become a wiki-link <a> with the tag name as href
        # and #tag as the display text.
        assert 'class="wiki-link"' in html
        assert 'href="foo.md"' in html
        assert ">#foo</a>" in html

    def test_full_pipeline_no_tag_link_in_normal_mode(self):
        html = _convert_full_stack("use #foo here", logseq_mode=False)
        # Without logseq_mode, #foo should remain as plain text inside
        # whatever block it's in (no wiki-link <a> for it).
        assert 'class="wiki-link"' not in html
        # The literal "#foo" should be present somewhere.
        assert "#foo" in html


class TestResolveLogseqPage:
    """`resolve_logseq_page(name, current_file)` searches Logseq's
    conventional `pages/` and `journals/` directories, walking up from
    the current file's directory to find a graph root."""

    def test_finds_sibling_page(self, tmp_path):
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        # Layout:
        #   tmp/pages/Foo.md
        #   tmp/pages/Bar.md  (current file)
        pages = tmp_path / "pages"
        pages.mkdir()
        foo = pages / "Foo.md"
        foo.write_text("foo")
        bar = pages / "Bar.md"
        bar.write_text("bar")
        result = resolve_logseq_page("Foo", bar)
        assert result == foo

    def test_finds_page_when_current_at_graph_root(self, tmp_path):
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        # Layout:
        #   tmp/index.md   (current file, at root)
        #   tmp/pages/Foo.md
        index = tmp_path / "index.md"
        index.write_text("index")
        pages = tmp_path / "pages"
        pages.mkdir()
        foo = pages / "Foo.md"
        foo.write_text("foo")
        assert resolve_logseq_page("Foo", index) == foo

    def test_finds_namespaced_page_with_triple_underscore(self, tmp_path):
        """Logseq stores `[[a/b]]` as `a___b.md`."""
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        pages = tmp_path / "pages"
        pages.mkdir()
        page = pages / "a___b.md"
        page.write_text("nested")
        current = tmp_path / "index.md"
        current.write_text("")
        assert resolve_logseq_page("a/b", current) == page

    def test_finds_journal_page(self, tmp_path):
        """If the file lives in `journals/`, find it there."""
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        journals = tmp_path / "journals"
        journals.mkdir()
        page = journals / "2026_04_26.md"
        page.write_text("daily")
        current = tmp_path / "pages" / "Foo.md"
        current.parent.mkdir()
        current.write_text("")
        assert resolve_logseq_page("2026_04_26", current) == page

    def test_returns_none_when_not_found(self, tmp_path):
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        pages = tmp_path / "pages"
        pages.mkdir()
        current = pages / "Bar.md"
        current.write_text("")
        assert resolve_logseq_page("NotARealPage", current) is None

    def test_returns_none_when_current_file_is_none(self):
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        assert resolve_logseq_page("Foo", None) is None

    def test_does_not_walk_past_graph_root_marker(self, tmp_path):
        """Stop walking up once a directory with `logseq/` or `pages/`
        is found — that's the Logseq graph root. Don't keep climbing
        and accidentally match a Foo.md two levels up."""
        from markdown_editor.markdown6.extensions.logseq import (
            resolve_logseq_page,
        )
        # Layout:
        #   tmp/Foo.md            ← should NOT be matched (above graph root)
        #   tmp/graph/pages/Bar.md ← current file
        #   tmp/graph/pages/...    ← Foo.md NOT here
        #   tmp/graph/logseq/      ← marks graph root
        outer = tmp_path / "Foo.md"
        outer.write_text("OUTER")
        graph = tmp_path / "graph"
        graph.mkdir()
        (graph / "logseq").mkdir()
        pages = graph / "pages"
        pages.mkdir()
        bar = pages / "Bar.md"
        bar.write_text("bar")
        # Foo.md is NOT in pages/ — only outside the graph.
        assert resolve_logseq_page("Foo", bar) is None
