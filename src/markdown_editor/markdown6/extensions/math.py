"""LaTeX math block and inline math support."""

import re

from markdown import Extension
from markdown.postprocessors import Postprocessor
from markdown.preprocessors import Preprocessor


class MathPreprocessor(Preprocessor):
    """Preprocessor to protect math blocks from other processing."""

    MATH_BLOCK_PATTERN = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    MATH_INLINE_PATTERN = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')

    def __init__(self, md):
        super().__init__(md)
        self.math_blocks = []

    def run(self, lines):
        text = '\n'.join(lines)

        # Protect block math
        def replace_block(m):
            idx = len(self.math_blocks)
            self.math_blocks.append(('block', m.group(1)))
            return f'MATHBLOCK{idx}ENDMATHBLOCK'

        text = self.MATH_BLOCK_PATTERN.sub(replace_block, text)

        # Protect inline math
        def replace_inline(m):
            idx = len(self.math_blocks)
            self.math_blocks.append(('inline', m.group(1)))
            return f'MATHINLINE{idx}ENDMATHINLINE'

        text = self.MATH_INLINE_PATTERN.sub(replace_inline, text)

        # Store for postprocessor
        self.md.math_blocks = self.math_blocks

        return text.split('\n')


class MathPostprocessor(Postprocessor):
    """Postprocessor to restore math blocks."""

    def run(self, text):
        if not hasattr(self.md, 'math_blocks'):
            return text

        for idx, (math_type, content) in enumerate(self.md.math_blocks):
            if math_type == 'block':
                placeholder = f'MATHBLOCK{idx}ENDMATHBLOCK'
                replacement = f'<div class="math-block">$${content}$$</div>'
            else:
                placeholder = f'MATHINLINE{idx}ENDMATHINLINE'
                replacement = f'<span class="math-inline">${content}$</span>'

            text = text.replace(placeholder, replacement)

        return text


class MathExtension(Extension):
    """Extension for LaTeX math support."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            MathPreprocessor(md),
            'math_pre',
            30
        )
        md.postprocessors.register(
            MathPostprocessor(md),
            'math_post',
            25
        )


def get_math_js() -> str:
    """Get JavaScript for math rendering with KaTeX."""
    return """
    <script>
        // Polyfill for structuredClone (not available in older Chromium)
        if (typeof structuredClone === 'undefined') {
            window.structuredClone = function(obj) {
                return JSON.parse(JSON.stringify(obj));
            };
        }
    </script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {
            delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '$', right: '$', display: false}
            ]
        });"></script>
    """
