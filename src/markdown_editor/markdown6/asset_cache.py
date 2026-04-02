"""Download and cache external JS/CSS assets for offline HTML export.

Assets are cached in ~/.cache/markdown-editor/assets/ (XDG-compliant).
On first export, assets are downloaded from CDN and stored locally.
Subsequent exports read from cache.
"""

import base64
import os
import re
import urllib.request
from pathlib import Path

# CDN versions — update these to bump asset versions
KATEX_VERSION = "0.16.9"
MERMAID_VERSION = "9.4.3"
VIZ_VERSION = "3.2.4"

KATEX_BASE = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
VIZ_URL = f"https://cdn.jsdelivr.net/npm/@viz-js/viz@{VIZ_VERSION}/lib/viz-standalone.js"


def get_cache_dir() -> Path:
    """Return the asset cache directory, creating it if needed."""
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".cache"
    cache_dir = base / "markdown-editor" / "assets"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _download(url: str) -> bytes:
    """Download a URL and return bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "markdown-editor"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _cached_download(name: str, url: str) -> bytes:
    """Download a file, caching it locally."""
    cache_dir = get_cache_dir()
    path = cache_dir / name
    if path.exists():
        return path.read_bytes()
    data = _download(url)
    path.write_bytes(data)
    return data


def _get_katex_css_with_inlined_fonts() -> str:
    """Download KaTeX CSS and inline all font files as base64 data URIs."""
    css_bytes = _cached_download("katex.min.css", f"{KATEX_BASE}/katex.min.css")
    css = css_bytes.decode("utf-8")

    def inline_font(m):
        font_path = m.group(1)  # e.g. "fonts/KaTeX_Main-Regular.woff2"
        font_name = font_path.replace("/", "_")
        font_url = f"{KATEX_BASE}/{font_path}"
        font_data = _cached_download(font_name, font_url)
        b64 = base64.b64encode(font_data).decode("ascii")
        return f"url(data:font/woff2;base64,{b64})"

    css = re.sub(r'url\((fonts/[^)]+\.woff2)\)', inline_font, css)
    return css


def get_katex_bundle() -> str:
    """Return inline <style> + <script> tags for KaTeX with all assets embedded."""
    css = _get_katex_css_with_inlined_fonts()
    katex_js = _cached_download("katex.min.js", f"{KATEX_BASE}/katex.min.js").decode("utf-8")
    auto_render_js = _cached_download(
        "auto-render.min.js",
        f"{KATEX_BASE}/contrib/auto-render.min.js",
    ).decode("utf-8")

    return (
        f"<style>{css}</style>\n"
        f"<script>{katex_js}</script>\n"
        f"<script>{auto_render_js}</script>\n"
        "<script>"
        "document.addEventListener('DOMContentLoaded', function() {"
        "  renderMathInElement(document.body, {"
        "    delimiters: ["
        "      {left: '$$', right: '$$', display: true},"
        "      {left: '$', right: '$', display: false}"
        "    ]"
        "  });"
        "});"
        "</script>"
    )


def get_mermaid_js_inline() -> str:
    """Return inline <script> tag with mermaid.min.js."""
    js = _cached_download("mermaid.min.js", MERMAID_URL).decode("utf-8")
    return (
        f"<script>{js}</script>\n"
        "<script>mermaid.initialize({startOnLoad: true});</script>"
    )


def get_viz_js_inline() -> str:
    """Return inline <script> tag with viz-standalone.js."""
    js = _cached_download("viz-standalone.js", VIZ_URL).decode("utf-8")
    return f"<script>{js}</script>"


def ensure_cached() -> None:
    """Pre-download all assets to the cache directory."""
    _cached_download("katex.min.css", f"{KATEX_BASE}/katex.min.css")
    _cached_download("katex.min.js", f"{KATEX_BASE}/katex.min.js")
    _cached_download("auto-render.min.js", f"{KATEX_BASE}/contrib/auto-render.min.js")
    _cached_download("mermaid.min.js", MERMAID_URL)
    _cached_download("viz-standalone.js", VIZ_URL)
    # Fonts are downloaded lazily by _get_katex_css_with_inlined_fonts
