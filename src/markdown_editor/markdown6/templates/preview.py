"""HTML templates for the Markdown preview pane.

These are plain strings (not f-strings) intended for use with str.format().
Curly braces in CSS/JS are already escaped as {{ }}.
"""

PREVIEW_TEMPLATE_SIMPLE = """<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: {body_font}; font-size: {font_size}px; line-height: {line_height}; color: {text_color}; background-color: {bg_color}; padding: 10px; }}
        h1 {{ font-size: {h1_size}; font-weight: bold; {heading_font_css} }}
        h2 {{ font-size: {h2_size}; font-weight: bold; {heading_font_css} }}
        h3 {{ font-size: {h3_size}; font-weight: bold; {heading_font_css} }}
        code {{ font-family: {code_font}; font-size: {code_size}; background-color: {code_bg}; }}
        pre {{ font-family: {code_font}; font-size: {code_size}; background-color: {code_bg}; padding: 10px; }}
        blockquote {{ color: {blockquote_color}; margin-left: 20px; padding-left: 10px; border-left: 3px solid {heading_border}; }}
        a {{ color: {link_color}; }}
        table {{ border-collapse: collapse; }}
        th, td {{ border: 1px solid {heading_border}; padding: 5px; }}
        {pygments_css}
    </style>
</head>
<body>
{content}
{scroll_past_end_div}
</body>
</html>"""

PREVIEW_TEMPLATE_FULL = """
        <!DOCTYPE html>
        <html>
        <head>
            {math_js}
            <style>
                body {{
                    font-family: {body_font};
                    font-size: {font_size}px;
                    line-height: {line_height};
                    color: {text_color};
                    background-color: {bg_color};
                    max-width: 100%;
                    padding: 20px;
                    margin: 0;
                }}
                * {{
                    box-sizing: border-box;
                }}
                h1 {{
                    font-size: {h1_size};
                    font-weight: 600;
                    {heading_font_css}
                    border-bottom: 1px solid {heading_border};
                    padding-bottom: 0.3em;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h2 {{
                    font-size: {h2_size};
                    font-weight: 600;
                    {heading_font_css}
                    border-bottom: 1px solid {heading_border};
                    padding-bottom: 0.3em;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h3 {{ font-size: {h3_size}; font-weight: 600; {heading_font_css} margin-top: 24px; margin-bottom: 16px; }}
                h4 {{ font-size: {h4_size}; font-weight: 600; {heading_font_css} margin-top: 24px; margin-bottom: 16px; }}
                h5 {{ font-size: {h5_size}; font-weight: 600; {heading_font_css} margin-top: 24px; margin-bottom: 16px; }}
                h6 {{ font-size: {h6_size}; font-weight: 600; {heading_font_css} margin-top: 24px; margin-bottom: 16px; }}
                p {{ margin-top: 0; margin-bottom: 16px; }}
                code {{
                    font-family: {code_font};
                    font-size: {code_size};
                    background-color: {code_bg};
                    padding: 0.2em 0.4em;
                    border-radius: 3px;
                }}
                pre {{
                    font-family: {code_font};
                    font-size: {code_size};
                    background-color: {code_bg};
                    padding: 16px;
                    overflow: auto;
                    border-radius: 6px;
                    line-height: 1.2;
                    margin: 0 0 16px 0;
                    white-space: pre;
                    position: relative;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                    font-size: 100%;
                    line-height: inherit;
                    display: block;
                }}
                /* Pygments highlight container */
                .highlight {{
                    background-color: {code_bg};
                    padding: 16px;
                    border-radius: 6px;
                    overflow: auto;
                    margin-bottom: 16px;
                    line-height: 1.2;
                    position: relative;
                }}
                /* Copy-to-clipboard button on code blocks (preview only) */
                .mde-copy-btn {{
                    position: absolute;
                    top: 6px;
                    right: 6px;
                    padding: 2px 6px;
                    font-size: 12px;
                    line-height: 1;
                    color: {text_color};
                    background-color: {bg_color};
                    border: 1px solid {heading_border};
                    border-radius: 4px;
                    cursor: pointer;
                    opacity: 0;
                    transition: opacity 0.15s ease-in-out;
                    z-index: 2;
                    font-family: {body_font};
                }}
                #md-content .highlight:hover > .mde-copy-btn,
                #md-content pre:hover > .mde-copy-btn,
                .mde-copy-btn:focus,
                .mde-copy-btn.mde-copied {{
                    opacity: 1;
                }}
                .mde-copy-btn:hover {{
                    border-color: {link_color};
                }}
                .mde-copy-btn.mde-copied {{
                    color: {link_color};
                    border-color: {link_color};
                }}
                .highlight pre {{
                    margin: 0;
                    padding: 0;
                    background-color: transparent;
                    line-height: 1.2;
                }}
                .highlight code {{
                    line-height: 1.2;
                }}
                /* Remove any margins/padding inside code blocks */
                pre *, .highlight * {{
                    margin: 0;
                    padding: 0;
                    line-height: 1.2;
                }}
                pre span, .highlight span {{
                    display: inline;
                }}
                .codehilite {{
                    background-color: {code_bg};
                    padding: 16px;
                    border-radius: 6px;
                    overflow: auto;
                    margin-bottom: 16px;
                }}
                .codehilite pre {{
                    margin: 0;
                    padding: 0;
                    background-color: transparent;
                    line-height: 1.2;
                }}
                blockquote {{
                    margin: 0;
                    padding: 0 1em;
                    color: {blockquote_color};
                    border-left: 0.25em solid {heading_border};
                }}
                ul, ol {{
                    display: block;
                    padding-left: 2em;
                    margin-top: 0;
                    margin-bottom: 16px;
                    list-style-position: outside;
                }}
                ul {{ list-style-type: disc; }}
                ol {{ list-style-type: decimal; }}
                li {{
                    display: list-item;
                    margin-top: 0.25em;
                }}
                table {{ border-collapse: collapse; margin-top: 0; margin-bottom: 16px; width: 100%; }}
                th, td {{ padding: 6px 13px; border: 1px solid {heading_border}; }}
                th {{ font-weight: 600; background-color: {code_bg}; }}
                hr {{ height: 0.25em; padding: 0; margin: 24px 0; background-color: {heading_border}; border: 0; }}
                a {{ color: {link_color}; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                img {{ max-width: 100%; box-sizing: border-box; }}
                /* Wiki links */
                a.wiki-link {{
                    color: {link_color};
                    border-bottom: 1px dashed {link_color};
                }}
                a.wiki-link:hover {{
                    border-bottom-style: solid;
                }}
                /* Math blocks */
                .math-block {{
                    overflow-x: auto;
                    padding: 16px 0;
                }}
                .math-inline {{
                    padding: 0 2px;
                }}
                /* Mermaid diagrams */
                .mermaid {{
                    background: {code_bg};
                    padding: 16px;
                    border-radius: 6px;
                    margin: 16px 0;
                    text-align: center;
                }}
                /* Pygments syntax highlighting */
                {pygments_css}
                /* Callouts */
                {callout_css}
                /* Graphviz */
                {graphviz_css}
                /* Mermaid */
                {mermaid_css}
                /* Task lists */
                {tasklist_css}
                /* When zoomed, let diagram SVGs scale instead of fitting container */
                body.zoomed .mermaid-diagram svg,
                body.zoomed .graphviz-diagram svg {{
                    max-width: none;
                }}
                /* Diagram loading placeholder */
                .diagram-loading {{
                    padding: 16px;
                    border-radius: 6px;
                    background: {code_bg};
                    margin: 8px 0;
                    text-align: left;
                }}
                .diagram-loading-source {{
                    font-size: 80%;
                    opacity: 0.5;
                    max-height: 120px;
                    overflow: hidden;
                    margin: 0 0 8px 0;
                    background: transparent;
                    padding: 0;
                }}
                .diagram-loading-spinner {{
                    color: {blockquote_color};
                    font-style: italic;
                    font-size: 0.9em;
                }}
                /* Ctrl+hover hint — only the hovered element */
                body.ctrl-held img,
                body.ctrl-held .mermaid-diagram svg,
                body.ctrl-held .graphviz-diagram svg {{
                    cursor: pointer;
                }}
                body.ctrl-held img:hover,
                body.ctrl-held .mermaid-diagram:hover svg,
                body.ctrl-held .graphviz-diagram:hover svg {{
                    filter: drop-shadow(0 0 3px {link_color}) drop-shadow(0 0 1px {link_color});
                }}
            </style>
        </head>
        <body class="{body_class}" data-total-lines="{total_lines}">
            <div id="md-content">{content}</div>
            {scroll_past_end_div}
            {mermaid_js}
            {graphviz_js}
            <script>
            /* Ctrl+click on images/diagrams → open in external app */
            document.addEventListener('mousemove', function(e) {{
                document.body.classList.toggle('ctrl-held', e.ctrlKey || e.metaKey);
            }});
            document.addEventListener('keydown', function(e) {{
                if (e.key === 'Control' || e.key === 'Meta') document.body.classList.add('ctrl-held');
            }});
            document.addEventListener('keyup', function(e) {{
                if (e.key === 'Control' || e.key === 'Meta') document.body.classList.remove('ctrl-held');
            }});
            window.addEventListener('blur', function() {{
                document.body.classList.remove('ctrl-held');
            }});
            document.addEventListener('click', function(e) {{
                if (!e.ctrlKey && !e.metaKey) return;
                var el = e.target;
                while (el && el !== document.body) {{
                    if (el.tagName === 'IMG') {{
                        e.preventDefault();
                        e.stopPropagation();
                        window.location.href = 'open-image://img?src=' + encodeURIComponent(el.src);
                        return;
                    }}
                    if (el.tagName === 'svg' || (el.classList && (
                        el.classList.contains('mermaid-diagram') ||
                        el.classList.contains('graphviz-diagram')))) {{
                        var container = el.closest('.mermaid-diagram, .graphviz-diagram');
                        if (container && container.dataset.source) {{
                            e.preventDefault();
                            e.stopPropagation();
                            var kind = container.classList.contains('mermaid-diagram') ? 'mermaid' : 'graphviz';
                            window._pendingDiagramSource = container.dataset.source;
                            window.location.href = 'open-image://diagram?kind=' + kind;
                            return;
                        }}
                    }}
                    el = el.parentElement;
                }}
            }}, true);

            /* Source-line-based scroll synchronization */
            function scrollToSourceLine(line) {{
                var anchors = document.querySelectorAll('[data-source-line]');
                if (anchors.length === 0) {{
                    /* Fallback to proportional scroll */
                    var total = document.body.dataset.totalLines || 1;
                    window.scrollTo(0, document.body.scrollHeight * (line / total));
                    return;
                }}

                var before = null, after = null;
                for (var i = 0; i < anchors.length; i++) {{
                    var al = parseInt(anchors[i].dataset.sourceLine, 10);
                    if (al <= line) {{
                        before = {{ el: anchors[i], line: al }};
                    }}
                    if (al > line && after === null) {{
                        after = {{ el: anchors[i], line: al }};
                        break;
                    }}
                }}

                if (!before && !after) return;

                var targetY;
                if (!before) {{
                    targetY = after.el.getBoundingClientRect().top + window.scrollY;
                }} else if (!after) {{
                    var beforeY = before.el.getBoundingClientRect().top + window.scrollY;
                    var docBottom = document.body.scrollHeight;
                    var totalLines = parseInt(document.body.dataset.totalLines || '0', 10);
                    if (totalLines > before.line) {{
                        var t = (line - before.line) / (totalLines - before.line);
                        targetY = beforeY + t * (docBottom - beforeY);
                    }} else {{
                        targetY = beforeY;
                    }}
                }} else {{
                    var beforeY = before.el.getBoundingClientRect().top + window.scrollY;
                    var afterY = after.el.getBoundingClientRect().top + window.scrollY;
                    var t = (after.line === before.line) ? 0 : (line - before.line) / (after.line - before.line);
                    targetY = beforeY + t * (afterY - beforeY);
                }}

                window.scrollTo(0, Math.max(0, targetY));
            }}

            /* Copy-to-clipboard button on every <pre> in the preview.
               Buttons are injected on initial load and re-injected after
               incremental innerHTML updates via a MutationObserver. */
            (function() {{
                if (window._mdeCopyInit) return;
                window._mdeCopyInit = true;

                var ICON_IDLE = String.fromCodePoint(0x1F4CB);  /* clipboard */
                var ICON_DONE = String.fromCodePoint(0x2713);   /* check mark */

                function installButton(pre) {{
                    var host = pre.closest('.highlight') || pre;
                    if (host.querySelector(':scope > .mde-copy-btn')) return;
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'mde-copy-btn';
                    btn.setAttribute('aria-label', 'Copy code');
                    btn.title = 'Copy code';
                    btn.textContent = ICON_IDLE;
                    host.appendChild(btn);
                }}

                function installAll() {{
                    var content = document.getElementById('md-content');
                    if (!content) return;
                    var pres = content.querySelectorAll('pre');
                    for (var i = 0; i < pres.length; i++) installButton(pres[i]);
                }}

                function fallbackCopy(text) {{
                    try {{
                        var ta = document.createElement('textarea');
                        ta.value = text;
                        ta.setAttribute('readonly', '');
                        ta.style.position = 'fixed';
                        ta.style.opacity = '0';
                        document.body.appendChild(ta);
                        ta.select();
                        var ok = document.execCommand('copy');
                        document.body.removeChild(ta);
                        return ok;
                    }} catch (e) {{
                        return false;
                    }}
                }}

                function flash(btn, ok) {{
                    btn.textContent = ok ? ICON_DONE : '!';
                    btn.classList.add('mde-copied');
                    setTimeout(function() {{
                        btn.textContent = ICON_IDLE;
                        btn.classList.remove('mde-copied');
                    }}, 1500);
                }}

                document.addEventListener('click', function(e) {{
                    var btn = e.target && e.target.closest && e.target.closest('.mde-copy-btn');
                    if (!btn) return;
                    e.preventDefault();
                    e.stopPropagation();
                    var host = btn.parentElement;
                    if (!host) return;
                    var pre = host.tagName === 'PRE' ? host : host.querySelector('pre');
                    if (!pre) return;
                    var code = pre.querySelector('code');
                    var text = (code || pre).textContent || '';
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(text).then(
                            function() {{ flash(btn, true); }},
                            function() {{ flash(btn, fallbackCopy(text)); }}
                        );
                    }} else {{
                        flash(btn, fallbackCopy(text));
                    }}
                }});

                installAll();
                var content = document.getElementById('md-content');
                if (content && typeof MutationObserver !== 'undefined') {{
                    var observer = new MutationObserver(function() {{ installAll(); }});
                    observer.observe(content, {{ childList: true, subtree: true }});
                }}
            }})();
            </script>
        </body>
        </html>
        """
