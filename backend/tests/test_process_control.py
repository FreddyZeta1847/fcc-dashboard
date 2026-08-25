"""Unit tests for backend.fcc_dashboard.process_control.

These tests launch a real, short-lived, harmless dummy subprocess (a
`python -c "..."` sleep) to verify the detached-launch/liveness/terminate
primitives actually work on this OS -- not FCC itself, which may not be
installed on the machine running the test suite.
"""

import sys
import time
from pathlib import Path

from fcc_dashboard import process_control
from fcc_dashboard.process_control import (
    find_fcc_server_executable,
    is_process_alive,
    launch_detached,
    terminate_process,
)


def _dummy_executable_args(sleep_seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({sleep_seconds})"]


def launch_detached_for_test(args: list[str]) -> int:
    """Test helper: launch a subprocess with arguments, using the same
    detachment approach as launch_detached, for testing against a
    controllable dummy command instead of the no-args fcc-server contract.
    """
    return process_control._launch_detached_args(args)


def test_find_fcc_server_executable_returns_none_when_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert find_fcc_server_executable() is None


def test_find_fcc_server_executable_returns_path_when_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/fcc-server")
    result = find_fcc_server_executable()
    assert result is not None
    assert "fcc-server" in str(result)


def test_launch_detached_starts_a_real_process_and_returns_its_pid():
    pid = launch_detached_for_test(_dummy_executable_args(5))
    try:
        assert is_process_alive(pid)
    finally:
        terminate_process(pid)


def test_is_process_alive_false_for_nonexistent_pid():
    # A PID astronomically unlikely to be in use.
    assert is_process_alive(999_999) is False


def test_terminate_process_stops_a_running_process():
    pid = launch_detached_for_test(_dummy_executable_args(30))
    assert is_process_alive(pid)

    result = terminate_process(pid, timeout=5.0)

    assert result is True
    assert is_process_alive(pid) is False


def test_terminate_process_on_already_stopped_pid_returns_true():
    pid = launch_detached_for_test(_dummy_executable_args(0.1))

    # Poll until the process actually exits instead of sleeping a fixed
    # amount: interpreter startup overhead (not the 0.1s sleep itself)
    # dominates the timing here and varies across machines/runs, so a
    # fixed sleep margin can be too tight -- a poll-until-dead loop is
    # both more reliable and usually faster than always waiting the full
    # fixed margin.
    deadline = time.monotonic() + 15
    while is_process_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert is_process_alive(pid) is False

    result = terminate_process(pid, timeout=5.0)

    assert result is True


def test_launch_detached_calls_launch_detached_args_with_executable_path(monkeypatch):
    calls = []
    monkeypatch.setattr(
        process_control,
        "_launch_detached_args",
        lambda args: calls.append(args) or 42,
    )

    fake_executable = Path("/fake/fcc-server")
    pid = launch_detached(fake_executable)

    assert pid == 42
    # str(Path(...)) rather than a literal "/fake/fcc-server" string,
    # since Path normalizes separators for the current OS (e.g.
    # "\fake\fcc-server" on Windows).
    assert calls == [[str(fake_executable)]]


def test_terminate_process_survives_access_denied_enumerating_children(monkeypatch):
    """`process.children(recursive=True)` raising AccessDenied must not stop
    `terminate_process` from still stopping the main tracked process -- the
    main process was already successfully reached (it's not the same as the
    main process itself being inaccessible), we just couldn't see its
    children.
    """
    pid = launch_detached_for_test(_dummy_executable_args(30))
    assert is_process_alive(pid)

    def raise_access_denied(self, recursive=False):
        raise process_control.psutil.AccessDenied(pid=self.pid)

    monkeypatch.setattr(
        process_control.psutil.Process, "children", raise_access_denied
    )

    try:
        result = terminate_process(pid, timeout=5.0)
        assert result is True
        assert is_process_alive(pid) is False
    finally:
        monkeypatch.undo()
        terminate_process(pid)


def test_terminate_process_swallows_access_denied_on_child_terminate(monkeypatch):
    """A child whose `.terminate()` raises AccessDenied must be skipped
    (best-effort), not propagate out of `terminate_process` and not stop
    the main tracked process from being terminated.
    """
    pid = launch_detached_for_test(_dummy_executable_args(30))
    assert is_process_alive(pid)

    class _FakeAccessDeniedChild:
        def terminate(self):
            raise process_control.psutil.AccessDenied(pid=999_999)

    monkeypatch.setattr(
        process_control.psutil.Process,
        "children",
        lambda self, recursive=False: [_FakeAccessDeniedChild()],
    )

    try:
        result = terminate_process(pid, timeout=5.0)
        assert result is True
        assert is_process_alive(pid) is False
    finally:
        monkeypatch.undo()
        terminate_process(pid)


def test_terminate_process_also_terminates_child_processes():
    parent_script = (
        "import subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        "time.sleep(30)"
    )
    parent_pid = launch_detached_for_test([sys.executable, "-c", parent_script])
    child_pid = None

    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            children = process_control.psutil.Process(parent_pid).children()
            if children:
                child_pid = children[0].pid
                break
            time.sleep(0.05)
        assert child_pid is not None, "dummy child process never appeared"
        assert is_process_alive(child_pid)

        result = terminate_process(parent_pid, timeout=5.0)

        assert result is True
        assert is_process_alive(parent_pid) is False
        assert is_process_alive(child_pid) is False
    finally:
        terminate_process(parent_pid)
        if child_pid is not None:
            terminate_process(child_pid)
