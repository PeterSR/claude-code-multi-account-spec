"""B4 helpers: Claude Code's project folder name for a directory, and the sessions stored in it."""

from __future__ import annotations

import re

from .context import Context
from .fs import DIR, FILE, FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import ProjectSession
from .timeutil import format_millis

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", re.ASCII)
_ALNUM = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _units(text: str) -> list[int]:
    """UTF-16 code units of `text` (astral characters are two units, lone surrogates one)."""
    raw = text.encode("utf-16-le", "surrogatepass")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def project_slug(cwd: str) -> str:
    """Claude Code's folder name under `projects/` for `cwd`.

    Every UTF-16 code unit outside `[A-Za-z0-9]` becomes `-`. Beyond 200 characters the name is
    the first 200, `-`, and base 36 of abs(h) where h is a 32-bit `h * 31 + unit` hash of the
    original text. Pure: no filesystem.
    """
    units = _units(cwd)
    slug = "".join(chr(u) if u < 128 and u in _ALNUM else "-" for u in units)
    if len(slug) <= 200:
        return slug
    h = 0
    for u in units:
        h = (h * 31 + u) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    n = abs(h)
    digits = ""
    while n:
        n, r = divmod(n, 36)
        digits = _DIGITS[r] + digits
    return slug[:200] + "-" + (digits or "0")


@io_errors
def sessions_for(inp: Inputs, name: str, cwd: str) -> list[ProjectSession]:
    """Sessions stored for the project of `cwd`, newest first (then id ascending)."""
    ctx = Context(inp)
    ctx.gate(name)
    projects = ctx.P.join(ctx.config_home(name), "projects")
    folder = ctx.P.join(projects, project_slug(cwd))
    found: list[tuple[int, str]] = []
    try:
        for p in (projects, folder):
            if ctx.fs.lstat(p).type != DIR:
                return []
        for entry in ctx.fs.readdir(folder):
            sid = entry[: -len(".jsonl")]
            if not entry.endswith(".jsonl") or not _ID_RE.fullmatch(sid):
                continue
            st = ctx.fs.lstat(ctx.P.join(folder, entry))
            if st.type == FILE:
                found.append((round(st.mtime * 1000), sid))
    except FsError:
        if not found:
            return []
        raise
    found.sort(key=lambda t: (-t[0], t[1]))
    return [ProjectSession(sid, format_millis(ms) or "") for ms, sid in found]
