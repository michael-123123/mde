"""Tests for ``logger.capture_external_stderr``.

The function redirects OS-level fd 2 through a pipe so native libraries
(Chromium / NSS / Qt) that bypass Python's ``sys.stderr`` are routed
through the ``mde.external`` logger at DEBUG. Verify by writing a line
straight to fd 2 (the same path Chromium uses) and checking it shows
up on the logger.

NOTE: fd-2 manipulation is process-global. These tests:
- use ``os.write(2, ...)`` to bypass Python's stderr buffering
- restore stderr at teardown (best-effort) so other tests aren't
  contaminated
- skip on Windows where the function is a documented no-op
"""

import logging
import os
import sys
import time

import pytest

if sys.platform == "win32":
    pytest.skip("capture is a no-op on Windows", allow_module_level=True)

from markdown_editor.markdown6 import logger as mde_logger


@pytest.fixture
def restore_fd2():
    """Save and restore fd 2 + sys.stderr around each test.

    Without this, the capture sticks across tests, breaking any later
    test that introspects stderr or expects unmodified pipes.
    """
    saved_fd = os.dup(2)
    saved_stderr = sys.stderr
    saved_flag = mde_logger._external_capture_started
    yield
    os.dup2(saved_fd, 2)
    os.close(saved_fd)
    sys.stderr = saved_stderr
    mde_logger._external_capture_started = saved_flag


def test_fd2_writes_are_captured_via_external_logger(restore_fd2, caplog):
    """A line written directly to fd 2 should arrive on the
    ``mde.external`` logger at DEBUG."""
    mde_logger.capture_external_stderr()

    # Drive caplog at DEBUG so the captured line is visible.
    with caplog.at_level(logging.DEBUG, logger="mde.external"):
        # Simulate what Chromium's native logger does: a direct fd 2 write.
        os.write(
            2,
            b"[ERROR:nss_util.cc(357)] After loading Root Certs, "
            b"loaded==false: NSS error code: -8018\n",
        )
        # Reader is a daemon thread - give it a beat to drain.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if any("nss_util" in r.message for r in caplog.records):
                break
            time.sleep(0.02)

    msgs = [r.message for r in caplog.records if r.name == "mde.external"]
    assert any("nss_util" in m for m in msgs), (
        f"expected NSS line to surface on mde.external; got {msgs!r}"
    )


def test_python_logger_output_does_not_loop_back(restore_fd2, caplog):
    """Smoke check: our own Python logging output (which goes to
    ``sys.stderr``) must NOT come back through the capture pipe -
    otherwise every log line would be duplicated under
    ``mde.external``."""
    mde_logger.capture_external_stderr()

    pytest_logger = logging.getLogger("mde.something_normal")
    with caplog.at_level(logging.DEBUG):
        pytest_logger.info("an ordinary log line")
        time.sleep(0.1)

    # No record from mde.external whose body is "an ordinary log line".
    external_msgs = [
        r.message for r in caplog.records if r.name == "mde.external"
    ]
    assert all("an ordinary log line" not in m for m in external_msgs), (
        f"python stderr looped back into the capture pipe: {external_msgs!r}"
    )


def test_capture_is_idempotent(restore_fd2):
    """Calling twice should not stack pipes or threads."""
    mde_logger.capture_external_stderr()
    fd2_after_first = os.dup(2)
    mde_logger.capture_external_stderr()
    fd2_after_second = os.dup(2)
    # Both dups should reference the SAME underlying file (same pipe writer).
    # We can't compare fds directly, but ``os.fstat`` gives a stable ino.
    assert os.fstat(fd2_after_first).st_ino == os.fstat(fd2_after_second).st_ino
    os.close(fd2_after_first)
    os.close(fd2_after_second)
