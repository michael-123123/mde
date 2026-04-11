"""Temporary file management with app cache directory and automatic cleanup."""

import atexit
import shutil
import tempfile
from pathlib import Path

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


_tracked: set[Path] = set()
_cache_dir: Path | None = None


def _get_cache_dir() -> Path:
    """Get or create the app cache directory for temp files.

    Uses QStandardPaths.CacheLocation (e.g. ~/.cache/Markdown Editor/tmp/)
    if a QApplication exists, otherwise falls back to the system temp dir.
    """
    global _cache_dir
    if _cache_dir is not None:
        return _cache_dir

    try:
        from PySide6.QtCore import QStandardPaths
        cache_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation,
        )
        if cache_root:
            d = Path(cache_root) / 'tmp'
            d.mkdir(parents=True, exist_ok=True)
            _cache_dir = d
            return _cache_dir
    except Exception:
        logger.debug("QStandardPaths unavailable, using system temp dir")

    _cache_dir = Path(tempfile.gettempdir())
    return _cache_dir


def create_temp_file(
    suffix: str = '.tmp',
    prefix: str = 'mde_',
    content: str | bytes | None = None,
) -> Path:
    """Create a tracked temp file. Cleaned up on app exit.

    Args:
        suffix: File extension (e.g. '.svg', '.md')
        prefix: Filename prefix
        content: Optional content to write immediately

    Returns:
        Path to the created file.
    """
    tmp = tempfile.NamedTemporaryFile(
        suffix=suffix, prefix=prefix, dir=str(_get_cache_dir()), delete=False,
    )
    if content is not None:
        if isinstance(content, str):
            tmp.write(content.encode('utf-8'))
        else:
            tmp.write(content)
    tmp.close()
    path = Path(tmp.name)
    _tracked.add(path)
    return path


def create_temp_dir(prefix: str = 'mde_') -> Path:
    """Create a tracked temp directory. Cleaned up on app exit.

    Returns:
        Path to the created directory.
    """
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=str(_get_cache_dir())))
    _tracked.add(path)
    return path


def cleanup():
    """Delete all tracked temp files and directories."""
    for path in list(_tracked):
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        except OSError:
            logger.warning(f"Could not clean up temp path: {path}")
    _tracked.clear()


atexit.register(cleanup)
