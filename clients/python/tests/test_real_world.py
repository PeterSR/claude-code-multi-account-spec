"""End to end on a real temporary home: write ops, slot, handover safety, lock retry, crashes."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_code_multi_account import (
    FixedClock,
    Inputs,
    LimitEntry,
    MultiAccountError,
    OsFs,
    ProcessInfo,
    activate,
    adopt,
    available,
    clear_limited,
    create,
    handover_session,
    live_sessions,
    mark_limited,
    resolve,
    slot,
)
from claude_code_multi_account.jsonio import parse_json
from claude_code_multi_account.timeutil import parse_instant

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX tree")
NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


class _Procs:
    def __init__(self, table: dict[int, ProcessInfo]) -> None:
        self.table = table

    def lookup(self, pid: int) -> ProcessInfo | None:
        return self.table.get(pid)


def _inp(home: Path, procs: dict[int, ProcessInfo] | None = None, **kw: object) -> Inputs:
    return Inputs(
        env={}, cwd=str(home), home=str(home), platform="linux", fs=OsFs(), clock=FixedClock(NOW),
        processes=_Procs(procs or {}), caller_pid_domain="d", **kw,  # type: ignore[arg-type]
    )


def _code(fn: object) -> str:
    with pytest.raises(MultiAccountError) as err:
        fn()  # type: ignore[operator]
    return err.value.code


def test_repeated_mark_limited_replaces_on_real_fs(tmp_path: Path) -> None:
    create(_inp(tmp_path), "work")
    entry = LimitEntry("seven_day", None, "2026-10-09T14:00:00Z", "rate_limit", "t")
    mark_limited(_inp(tmp_path), "work", entry)
    again = mark_limited(_inp(tmp_path), "work", LimitEntry("seven_day", None, "2026-10-10T14:00:00Z", "x", "t"))
    assert [e["until"] for e in again.limits] == ["2026-10-10T14:00:00Z"]
    assert not available(_inp(tmp_path), "work")
    assert clear_limited(_inp(tmp_path), "work", "seven_day", None).limits == []
    assert sorted(p.name for p in (tmp_path / ".claude-work").iterdir() if ".lock" in p.name or ".tmp." in p.name) == []


def test_state_file_not_understood_is_never_overwritten(tmp_path: Path) -> None:
    create(_inp(tmp_path), "work")
    state = tmp_path / ".claude-work" / ".multi-account-state.json"
    state.write_text('{"version": 2, "limits": []}')
    assert _code(lambda: mark_limited(_inp(tmp_path), "work", LimitEntry("w", None, "2026-12-01T00:00:00Z"))) == "STATE_FILE_INVALID"
    assert state.read_text() == '{"version": 2, "limits": []}'
    assert _code(lambda: mark_limited(_inp(tmp_path), "work", LimitEntry("w", None, "tomorrow"))) == "INVALID_ENTRY"


def test_fresh_lock_is_busy_and_retry_is_bounded(tmp_path: Path) -> None:
    create(_inp(tmp_path), "work")
    lock = tmp_path / ".claude-work" / ".multi-account-state.json.lock"
    lock.mkdir()
    os.utime(lock, (NOW.timestamp(), NOW.timestamp()))
    entry = LimitEntry("w", None, "2026-12-01T00:00:00Z")
    assert _code(lambda: mark_limited(_inp(tmp_path), "work", entry)) == "LOCK_BUSY"
    assert _code(lambda: mark_limited(_inp(tmp_path, lock_wait=0.2), "work", entry)) == "LOCK_BUSY"


@pytest.mark.parametrize("bad", ["..", "../.credentials.json", "a/b", "a\\b", ".", "", "/etc/passwd"])
def test_handover_rejects_traversal_ids(tmp_path: Path, bad: str) -> None:
    for n in ("work", "personal"):
        (tmp_path / f".claude-{n}").mkdir()
    (tmp_path / ".claude-work" / ".credentials.json").write_text("secret")
    assert _code(lambda: handover_session(_inp(tmp_path), bad, "work", "personal", overwrite=True)) == "INVALID_SESSION_ID"
    assert not (tmp_path / ".claude-personal" / ".credentials.json").exists()
    assert (tmp_path / ".claude-personal").is_dir()


def test_handover_skips_links_and_fifos_and_refuses_same_account(tmp_path: Path) -> None:
    for n in ("work", "personal"):
        (tmp_path / f".claude-{n}").mkdir()
    env_dir = tmp_path / ".claude-work" / "session-env" / "s1"
    env_dir.mkdir(parents=True)
    (env_dir / "ok.txt").write_text("hi")
    os.symlink("/etc/hostname", env_dir / "link")
    os.mkfifo(env_dir / "pipe")
    res = handover_session(_inp(tmp_path), "s1", "work", "personal")
    assert res.copied == ["session-env/s1/ok.txt"]
    assert res.skipped == ["session-env/s1/link", "session-env/s1/pipe"]
    assert (tmp_path / ".claude-personal" / "session-env" / "s1" / "ok.txt").read_text() == "hi"
    assert _code(lambda: handover_session(_inp(tmp_path), "s1", "work", "work", overwrite=True)) == "SAME_ACCOUNT"
    assert (env_dir / "ok.txt").exists()


def test_handover_unknown_session_blocks_unless_forced(tmp_path: Path) -> None:
    for n in ("work", "personal"):
        (tmp_path / f".claude-{n}").mkdir()
    (tmp_path / ".claude-work" / "tasks" / "s2").mkdir(parents=True)
    sessions = tmp_path / ".claude-work" / "sessions"
    sessions.mkdir()
    (sessions / "77.json").write_text(json.dumps({"sessionId": "s2", "pidDomain": "elsewhere", "procStart": "1"}))
    assert [s.status for s in live_sessions(_inp(tmp_path), "work")] == ["unknown"]
    assert _code(lambda: handover_session(_inp(tmp_path), "s2", "work", "personal")) == "SESSION_LIVE"
    assert handover_session(_inp(tmp_path), "s2", "work", "personal", force=True).skipped == []


def test_adopt_then_activate_with_live_guard(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude.json").write_text("{}")
    (tmp_path / ".claude-b").mkdir()
    assert adopt(_inp(tmp_path), "a").state == "managed"
    assert os.readlink(tmp_path / ".claude") == str(tmp_path / ".claude-a")
    assert (tmp_path / ".claude-a" / ".claude.json").is_file()
    assert _code(lambda: activate(_inp(tmp_path), "default")) == "INVALID_NAME"
    sessions = tmp_path / ".claude-a" / "sessions"
    sessions.mkdir()
    (sessions / "5.json").write_text(json.dumps({"sessionId": "x", "pidDomain": "d", "procStart": "9"}))
    live = {5: ProcessInfo("d", proc_start="9")}
    assert _code(lambda: activate(_inp(tmp_path, live), "b")) == "SESSION_LIVE"
    assert slot(_inp(tmp_path)).name == "a"
    assert activate(_inp(tmp_path), "b").name == "b"
    assert os.readlink(tmp_path / ".claude.json") == str(tmp_path / ".claude-b" / ".claude.json")
    assert not [p for p in tmp_path.iterdir() if ".tmp." in p.name or p.name.endswith(".lock")]


def test_adopt_refuses_to_clobber_inner_global_config(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".claude.json").write_text('{"inner": 1}')
    (tmp_path / ".claude.json").write_text("{}")
    assert _code(lambda: adopt(_inp(tmp_path), "a")) == "SLOT_CONFLICT"
    assert (tmp_path / ".claude" / ".claude.json").read_text() == '{"inner": 1}'


def test_io_error_for_unreadable_file(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    (tmp_path / ".claude-w").mkdir()
    (tmp_path / ".claude-w" / "tasks" / "s").mkdir(parents=True)
    (tmp_path / ".claude-w" / "tasks" / "s" / "f").write_text("x")
    os.chmod(tmp_path / ".claude-w" / "tasks" / "s" / "f", 0)
    (tmp_path / ".claude-v").mkdir()
    assert _code(lambda: handover_session(_inp(tmp_path), "s", "w", "v")) == "IO_ERROR"
    assert not (tmp_path / ".claude-v" / "tasks").exists()


def test_pathological_spec_files_do_not_crash(tmp_path: Path) -> None:
    (tmp_path / ".claude-w").mkdir()
    spec = tmp_path / ".claude-w" / ".multi-account.json"
    spec.write_text("[" * 20000 + "]" * 20000)
    assert _code(lambda: resolve(_inp(tmp_path))) == "SPEC_FILE_INVALID"
    spec.write_text('{"version": 1, "pool": "p", "priority": 1e400}')
    assert _code(lambda: resolve(_inp(tmp_path))) == "SPEC_FILE_INVALID"
    spec.write_bytes(b'{"version": 1, "label": "caf\xe9"}')
    assert _code(lambda: resolve(_inp(tmp_path))) == "SPEC_FILE_INVALID"


def test_json_and_instant_helpers() -> None:
    with pytest.raises(ValueError):
        parse_json(b"[NaN]")
    with pytest.raises(ValueError):
        parse_json(b'{"a":{"b":{}}}', 2)
    assert parse_json(b'{"a":{}}', 2) == {"a": {}}
    assert parse_instant("2026-10-09T16:00:00+02:00") == parse_instant("2026-10-09T14:00:00Z")
    assert parse_instant("2026-10-09t14:00:00z") is None
    assert parse_instant("2026-02-30T00:00:00Z") is None
    assert parse_instant("2026-10-09T14:00:60Z") is None


def test_project_slug_utf16_and_hash() -> None:
    from claude_code_multi_account import project_slug

    assert project_slug("/home/p/my.proj") == "-home-p-my-proj"
    assert project_slug("/a\U0001f600b") == "-a--b"  # an astral character is two UTF-16 units
    long = "/" + "x" * 250
    slug = project_slug(long)
    assert slug.startswith("-" + "x" * 199 + "-") and len(slug) > 201
    h = 0
    for c in long:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    h = h - (1 << 32) if h >= 1 << 31 else h
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    n, out = abs(h), ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    assert slug.endswith("-" + out)


def test_handover_into_linked_destination_parent_is_blocked(tmp_path: Path) -> None:
    for n in ("work", "personal"):
        (tmp_path / f".claude-{n}").mkdir()
    (tmp_path / ".claude-work" / "tasks" / "s1").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    os.symlink(tmp_path / "elsewhere", tmp_path / ".claude-personal" / "tasks")
    assert _code(lambda: handover_session(_inp(tmp_path), "s1", "work", "personal")) == "DESTINATION_BLOCKED"
    assert list((tmp_path / "elsewhere").iterdir()) == []
