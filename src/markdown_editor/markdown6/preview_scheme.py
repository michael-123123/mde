"""Custom URL scheme that serves preview HTML to QWebEngineView,
sidestepping the hardcoded 2 MB ``setHtml()`` size cap.

``QWebEngineView.setHtml(html, baseUrl)`` percent-encodes the HTML
and passes it through a URL; Chromium then refuses URLs longer than
~2 MB and silently leaves the page blank. Markdown files that
produce HTML larger than that (a 4 MB exported AI conversation log
expands to ~5.6 MB of HTML) hit the cap and don't render at all.

This module:

1. Registers ``mde-preview://`` as a custom scheme at module import
   time. Qt requires the registration to happen before any
   ``QWebEngineProfile`` is constructed; running the call at import
   time means simply ``import markdown_editor.markdown6.preview_scheme``
   somewhere before ``QApplication`` is enough.
2. Provides a ``PreviewSchemeHandler`` that stores HTML by key in
   memory and serves it on request. ``DocumentTab`` stores its
   rendered HTML via ``set_html(key, html)`` and points its
   ``QWebEngineView`` at ``mde-preview://<key>/``; the handler
   responds with the stored bytes.
3. Exposes ``get_handler()``, a lazy singleton that installs itself
   on the default ``QWebEngineProfile`` on first call.

Scheme flags chosen to mirror what ``setHtml`` provides:

- ``SecureScheme`` so scripts (KaTeX, mermaid) can run.
- ``LocalScheme`` + ``LocalAccessAllowed`` so the page can load
  resources from ``file://`` URLs (images sitting next to the
  source markdown file, etc.).
- ``CorsEnabled`` so the served origin can be cross-origin to other
  schemes when needed.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QIODevice, QObject, QUrl
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)


SCHEME = b"mde-preview"
SCHEME_STR = SCHEME.decode("ascii")


def _register_scheme() -> None:
    """Register the ``mde-preview`` URL scheme. Idempotent: Qt no-ops
    re-registration with the same name."""
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)


_register_scheme()


class PreviewSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves preview HTML from an in-memory dict, keyed by tab.

    ``DocumentTab`` stores its rendered HTML via ``set_html(key, html)``
    and points its ``QWebEngineView`` at ``mde-preview://<key>/``.
    On the next page load, ``requestStarted`` is called with the URL;
    we look up the key (the URL host) and reply with the stored
    bytes.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store: dict[str, bytes] = {}

    def set_html(self, key: str, html: str) -> None:
        self._store[key] = html.encode("utf-8")

    def get_html(self, key: str) -> str | None:
        data = self._store.get(key)
        return None if data is None else data.decode("utf-8")

    def remove(self, key: str) -> None:
        self._store.pop(key, None)

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802  (Qt API)
        url = job.requestUrl()
        key = url.host()
        data = self._store.get(key)
        if data is None:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        # The QBuffer must outlive the reply (Qt streams from it
        # asynchronously). Parenting it to the job lets Qt clean it
        # up when the job completes.
        buf = QBuffer(parent=job)
        buf.setData(data)
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(b"text/html", buf)


_handler: PreviewSchemeHandler | None = None


def get_handler() -> PreviewSchemeHandler:
    """Return the singleton handler. Installs it on the default
    ``QWebEngineProfile`` on first call. A ``QApplication`` must
    already exist when this runs."""
    global _handler
    if _handler is None:
        _handler = PreviewSchemeHandler()
        QWebEngineProfile.defaultProfile().installUrlSchemeHandler(
            SCHEME, _handler,
        )
    return _handler


def preview_url(key: str) -> QUrl:
    """URL a ``QWebEngineView`` should load to fetch the HTML stored
    under ``key`` via ``get_handler().set_html(key, html)``."""
    return QUrl(f"{SCHEME_STR}://{key}/")
