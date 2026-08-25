"""Unit tests for backend.fcc_dashboard.process_control.

These tests launch a real, short-lived, harmless dummy subprocess (a
`python -c "..."` sleep) to verify the detached-launch/liveness/terminate
primitives actually work on this OS -- not FCC itself, which may not be
installed on the machine running the test suite.
"""

import sys
import time

from fcc_dashboard.process_control import (
    find_fcc_server_executable,
    is_process_alive,
    launch_detached,
    terminate_process,
)
from fcc_dashboard import process_control


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
    time.sleep(0.5)  # let it exit naturally
    assert is_process_alive(pid) is False

    result = terminate_process(pid, timeout=5.0)

    assert result is True
