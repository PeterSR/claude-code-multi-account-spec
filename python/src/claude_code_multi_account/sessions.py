"""B3: live sessions of an account."""

from __future__ import annotations

import re

from .context import Context
from .fs import FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import Session

_SESSION_FILE = re.compile(r"([1-9][0-9]{0,9})\.json", re.ASCII)


def blocks(status: str, force: bool) -> bool:
    """A session blocks when it is `live`, or `unknown` and `force` is not set."""
    return status == "live" or (status == "unknown" and not force)


def live_sessions_in(ctx: Context, name: str) -> list[Session]:
    """Sessions registered under `<config home>/sessions`, sorted by pid (no account gate)."""
    inp = ctx.inp
    sessions_dir = ctx.P.join(ctx.config_home(name), "sessions")
    try:
        names = ctx.fs.readdir(sessions_dir)
    except FsError:
        return []
    out: list[Session] = []
    for fname in names:
        m = _SESSION_FILE.fullmatch(fname)
        if not m:
            continue
        data = ctx.read_json(ctx.P.join(sessions_dir, fname))
        if not isinstance(data, dict):
            continue
        pid = int(m.group(1))
        sid = data.get("sessionId")
        out.append(Session(pid, sid if isinstance(sid, str) else None, _status(ctx, inp, pid, data)))
    return sorted(out, key=lambda s: s.pid)


def _status(ctx: Context, inp: Inputs, pid: int, data: dict[str, object]) -> str:
    domain = data.get("pidDomain")
    if domain is not None and domain != inp.caller_pid_domain:
        return "unknown"
    proc = inp.processes.lookup(pid)
    if proc is None:
        return "dead"
    if proc.lookup_error:
        return "unknown"
    file_ft = data.get("procStartFt")
    if isinstance(file_ft, str) and file_ft:
        return "live" if file_ft == proc.proc_start_ft else "dead"
    file_start = data.get("procStart")
    if isinstance(file_start, str):
        return "live" if file_start == proc.proc_start else "dead"
    return "unknown"


@io_errors
def live_sessions(inp: Inputs, name: str) -> list[Session]:
    """Sessions of `name`. `live`: the pid exists and its start marker matches the record;
    `dead`: no such pid or a different start marker; `unknown`: another pid domain, or a record
    without a start marker. Best effort: Claude Code does not register every process."""
    ctx = Context(inp)
    ctx.gate(name)
    return live_sessions_in(ctx, name)


@io_errors
def session_of_pid(inp: Inputs, name: str, pid: int) -> str | None:
    """The `sessionId` in `<config home>/sessions/<pid>.json`, or None. No liveness check."""
    ctx = Context(inp)
    ctx.gate(name)
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        return None
    data = ctx.read_json(ctx.P.join(ctx.config_home(name), "sessions", f"{pid}.json"))
    sid = data.get("sessionId") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and sid else None
