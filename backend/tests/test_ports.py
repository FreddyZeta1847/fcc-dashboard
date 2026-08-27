"""Unit tests for backend.fcc_dashboard.ports.

The port probe is exercised against a *real* socket the test itself holds open,
rather than a mock, because the whole point of `is_port_free()` is what the OS
actually does with a bind -- and the Windows `SO_REUSEADDR` trap the module
guards against would sail straight through a mocked socket.

Process inspection is stubbed instead: `psutil` behaviour on a live machine
(which PIDs exist, which are readable) is not reproducible in a test suite.
"""

from __future__ import annotations

import socket
from datetime import datetime

import psutil
import pytest

from fcc_dashboard import ports
from fcc_dashboard.ports import (
    DEFAULT_PORT,
    NoFreePortError,
    PortHolder,
    describe_port_holder,
    find_free_port,
    format_conflict_notice,
    is_port_free,
    resolve_port,
)


@pytest.fixture
def held_port():
    """Bind a real loopback socket and yield its port, still held open."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    try:
        yield holder.getsockname()[1]
    finally:
        holder.close()


class _StubProcess:
    """Minimal psutil.Process stand-in. Any attribute may raise instead."""

    def __init__(self, *, name="python.exe", exe="", cmdline=(), create_time=0.0,
                 raises=()):
        self._name = name
        self._exe = exe
        self._cmdline = list(cmdline)
        self._create_time = create_time
        self._raises = set(raises)

    def _maybe_raise(self, attr):
        if attr in self._raises:
            raise psutil.AccessDenied(pid=1234)

    def name(self):
        self._maybe_raise("name")
        return self._name

    def exe(self):
        self._maybe_raise("exe")
        return self._exe

    def cmdline(self):
        self._maybe_raise("cmdline")
        return self._cmdline

    def create_time(self):
        self._maybe_raise("create_time")
        return self._create_time


# --- is_port_free ---------------------------------------------------------


def test_is_port_free_false_while_port_is_held(held_port):
    assert is_port_free(held_port) is False


def test_is_port_free_true_once_port_is_released():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    assert is_port_free(port) is True


# --- find_free_port -------------------------------------------------------


def test_find_free_port_skips_the_occupied_port(held_port, monkeypatch):
    monkeypatch.setattr(ports, "is_port_free", lambda p, host=None: p != held_port)

    assert find_free_port(held_port, span=3) == held_port + 1


def test_find_free_port_returns_start_when_it_is_free(monkeypatch):
    monkeypatch.setattr(ports, "is_port_free", lambda p, host=None: True)

    assert find_free_port(8001, span=9) == 8001


def test_find_free_port_raises_when_whole_range_is_taken(monkeypatch):
    monkeypatch.setattr(ports, "is_port_free", lambda p, host=None: False)

    with pytest.raises(NoFreePortError) as excinfo:
        find_free_port(8001, span=9)

    # The message must name the range and the escape hatch, since this is the
    # one path where the user is left with nothing running.
    assert "8001-8009" in str(excinfo.value)
    assert "FCC_DASHBOARD_PORT" in str(excinfo.value)


def test_find_free_port_does_not_scan_into_fccs_own_port():
    """The default span must stop well short of 8082, FCC's own port."""
    assert DEFAULT_PORT + ports.PORT_SCAN_SPAN - 1 < 8082


# --- describe_port_holder -------------------------------------------------


def test_describe_port_holder_returns_none_when_sockets_unreadable(monkeypatch):
    def _denied(kind):
        raise psutil.AccessDenied(pid=None)

    monkeypatch.setattr(psutil, "net_connections", _denied)

    assert describe_port_holder(8000) is None


def test_describe_port_holder_returns_none_when_nothing_listens(monkeypatch):
    monkeypatch.setattr(psutil, "net_connections", lambda kind: [])

    assert describe_port_holder(8000) is None


def test_describe_port_holder_returns_none_when_process_already_exited(monkeypatch):
    monkeypatch.setattr(ports, "_listening_pid", lambda port: 4242)

    def _gone(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(psutil, "Process", _gone)

    assert describe_port_holder(8000) is None


def test_describe_port_holder_identifies_our_own_server(monkeypatch):
    monkeypatch.setattr(ports, "_listening_pid", lambda port: 4242)
    monkeypatch.setattr(
        psutil,
        "Process",
        lambda pid: _StubProcess(
            name="python.exe",
            exe=r"C:\proj\backend\.venv\Scripts\fcc-dashboard-server.exe",
            create_time=1756224112.0,
        ),
    )

    holder = describe_port_holder(8000)

    assert holder is not None
    assert holder.pid == 4242
    assert holder.is_own_server is True
    assert holder.started_at is not None


def test_describe_port_holder_marks_unrelated_process_as_foreign(monkeypatch):
    monkeypatch.setattr(ports, "_listening_pid", lambda port: 99)
    monkeypatch.setattr(
        psutil,
        "Process",
        lambda pid: _StubProcess(name="nginx.exe", exe=r"C:\nginx\nginx.exe"),
    )

    holder = describe_port_holder(8000)

    assert holder is not None
    assert holder.is_own_server is False
    assert holder.name == "nginx.exe"


# --- _looks_like_own_server: the cascading probe --------------------------


def test_own_server_detected_via_cmdline_when_exe_is_denied():
    """A denied exe() lookup must not stop the cmdline() check from answering."""
    process = _StubProcess(
        name="python.exe",
        cmdline=["python", "-m", "fcc_dashboard"],
        raises=("exe",),
    )

    assert ports._looks_like_own_server(process) is True


def test_own_server_false_when_every_lookup_is_denied():
    process = _StubProcess(raises=("name", "exe", "cmdline"))

    assert ports._looks_like_own_server(process) is False


def test_process_started_at_is_none_when_denied():
    assert ports._process_started_at(_StubProcess(raises=("create_time",))) is None


# --- format_conflict_notice -----------------------------------------------


def _own_holder():
    return PortHolder(
        pid=46056,
        name="python.exe",
        started_at=datetime(2026, 8, 26, 18, 1),
        is_own_server=True,
    )


def test_notice_for_own_server_warns_and_gives_a_stop_command():
    notice = format_conflict_notice(_own_holder(), 8000, 8001)

    assert "OLDER fcc-dashboard server" in notice
    assert "46056" in notice
    assert "2026-08-26 18:01" in notice
    assert "Stop it with:" in notice
    assert "http://localhost:8001" in notice


def test_notice_for_foreign_process_offers_no_kill_advice():
    holder = PortHolder(
        pid=1234, name="nginx.exe", started_at=None, is_own_server=False
    )

    notice = format_conflict_notice(holder, 8000, 8001)

    assert "nginx.exe" in notice
    assert "1234" in notice
    assert "Stop it with:" not in notice
    assert "OLDER" not in notice


def test_notice_when_holder_is_unknown():
    notice = format_conflict_notice(None, 8000, 8001)

    assert "could not be identified" in notice
    assert "Stop it with:" not in notice
    assert "-> Starting on port 8001 instead" in notice


def test_notice_omits_start_time_when_unavailable():
    holder = PortHolder(pid=7, name="python.exe", started_at=None, is_own_server=True)

    notice = format_conflict_notice(holder, 8000, 8001)

    assert "(PID 7)" in notice
    assert "started" not in notice


# --- resolve_port ---------------------------------------------------------


def test_resolve_port_uses_default_quietly_when_free(monkeypatch):
    monkeypatch.delenv(ports.PORT_ENV_VAR, raising=False)
    monkeypatch.setattr(ports, "is_port_free", lambda p, host=None: True)

    port, notice = resolve_port()

    assert port == DEFAULT_PORT
    assert notice is None


def test_resolve_port_falls_back_and_explains_when_default_is_taken(monkeypatch):
    monkeypatch.delenv(ports.PORT_ENV_VAR, raising=False)
    monkeypatch.setattr(ports, "is_port_free", lambda p, host=None: p != DEFAULT_PORT)
    monkeypatch.setattr(ports, "describe_port_holder", lambda port: _own_holder())

    port, notice = resolve_port()

    assert port == DEFAULT_PORT + 1
    assert notice is not None
    assert "OLDER fcc-dashboard server" in notice


def test_resolve_port_honours_explicit_override_without_probing(monkeypatch):
    monkeypatch.setenv(ports.PORT_ENV_VAR, "8005")

    def _should_not_run(*args, **kwargs):
        raise AssertionError("an explicit port must not trigger a scan")

    monkeypatch.setattr(ports, "is_port_free", _should_not_run)

    port, notice = resolve_port()

    assert port == 8005
    assert notice is None


def test_resolve_port_rejects_a_non_numeric_override(monkeypatch):
    monkeypatch.setenv(ports.PORT_ENV_VAR, "not-a-port")

    with pytest.raises(ValueError, match="must be a number"):
        resolve_port()


def test_resolve_port_rejects_an_out_of_range_override(monkeypatch):
    monkeypatch.setenv(ports.PORT_ENV_VAR, "70000")

    with pytest.raises(ValueError, match="between 1 and 65535"):
        resolve_port()


def test_resolve_port_ignores_a_blank_override(monkeypatch):
    """An empty or whitespace-only value is an unset variable, not an error."""
    monkeypatch.setenv(ports.PORT_ENV_VAR, "   ")
    monkeypatch.setattr(ports, "is_port_free", lambda p, host=None: True)

    port, notice = resolve_port()

    assert port == DEFAULT_PORT
    assert notice is None
