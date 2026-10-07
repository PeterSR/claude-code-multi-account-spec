"""Real process table, pid domain and OS probes."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from claude_code_multi_account import OsFs, from_process
from claude_code_multi_account.process import (
    OsProcessTable,
    linux_pid_domain,
    os_pid_domain,
    os_user_name,
    parse_proc_stat_start,
    probe_symlinks,
    LookupFailed,
    ps_start,
)

STAT = "4242 (weird ) name (x)) S 1 4242 4242 0 -1 4194560 100 0 0 0 1 2 0 0 20 0 1 0 12345678 1000 10 18446744073709551615"


def test_parse_proc_stat_uses_field_22_after_last_paren() -> None:
    assert parse_proc_stat_start(STAT) == "12345678"
    assert parse_proc_stat_start("garbage") is None
    assert parse_proc_stat_start("1 (a) S 1") is None


def test_linux_pid_domain_formula() -> None:
    dom = linux_pid_domain(lambda p: "11111111111111111111111111111111\n", lambda p: "pid:[1234567890]")
    assert dom == "linux:11111111111111111111111111111111:pid:[1234567890]"


def test_linux_pid_domain_unreadable_parts_are_empty() -> None:
    def boom(path: str) -> str:
        raise FileNotFoundError(path)

    assert linux_pid_domain(boom, boom) == "linux::"
    assert linux_pid_domain(boom, lambda p: "pid:[1]") == "linux::pid:[1]"


def test_other_platform_domains() -> None:
    assert os_pid_domain("darwin") == "linux"
    assert os_pid_domain("win32").startswith("linux:")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs /proc")
def test_own_process_start_matches_proc() -> None:
    table = OsProcessTable("linux")
    me = table.lookup(os.getpid())
    assert me is not None and me.proc_start and me.proc_start.isdigit()
    assert me.pid_domain == os_pid_domain("linux")
    assert table.lookup(2**22 + 12345) is None


@pytest.mark.skipif(shutil.which("ps") is None or sys.platform == "win32", reason="needs ps")
def test_ps_start_is_stable_and_missing_pid_is_none() -> None:
    first = ps_start(os.getpid())
    assert first is not None
    assert first == ps_start(os.getpid())
    assert ps_start(2**22 + 12345) is None


def test_ps_missing_tool_is_lookup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(LookupFailed):
        ps_start(1)
    info = OsProcessTable("darwin").lookup(1)
    assert info is not None and info.lookup_error


def test_probe_symlinks_leaves_nothing_behind(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX")
    assert probe_symlinks(OsFs(), str(tmp_path)) is True
    assert list(tmp_path.iterdir()) == []
    assert probe_symlinks(OsFs(), str(tmp_path / "missing")) is False


def test_user_name_from_user_database() -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX")
    import pwd

    assert os_user_name() == pwd.getpwuid(os.getuid()).pw_name


def test_from_process_fills_everything(tmp_path: Path) -> None:
    inp = from_process({"HOME": str(tmp_path)})
    assert inp.home == str(tmp_path)
    assert inp.clock is not None and inp.lock_wait > 0
    assert inp.caller_pid_domain == os_pid_domain(inp.platform)
    assert inp.user_name
