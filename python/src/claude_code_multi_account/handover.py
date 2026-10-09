"""B4: copy a conversation from one account to another."""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field

from . import errors as E
from .context import Context
from .errors import MultiAccountError
from .fs import DIR, FILE, JUNCTION, FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import HandoverResult
from .sessions import blocks, live_sessions_in

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", re.ASCII)


@dataclass
class _Plan:
    """What to copy: `dirs` (relative, parents first) and `files` (relative, bytes, mode)."""

    dirs: list[str] = field(default_factory=list)
    files: list[tuple[str, bytes, int]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _lstat_type(ctx: Context, path: str) -> str | None:
    try:
        return ctx.fs.lstat(path).type
    except FsError:
        return None


_KINDS = ("file-history", "session-env", "tasks")


def _plain_dir(ctx: Context, path: str) -> bool:
    return _lstat_type(ctx, path) == DIR


def _slugs(ctx: Context, root: str) -> list[str]:
    """Names under `projects` (only listed when `projects` is a plain directory)."""
    projects = ctx.P.join(root, "projects")
    if not _plain_dir(ctx, projects):
        return []
    try:
        return ctx.fs.readdir(projects)
    except FsError:
        return []


def _bad_parents(ctx: Context, root: str) -> list[str]:
    """Relative parents that exist but are not plain directories (links, files): never locations."""
    out: list[str] = []
    for rel in ["projects", *_KINDS]:
        t = _lstat_type(ctx, _abs(ctx, root, rel))
        if t is not None and t != DIR:
            out.append(rel)
    if _plain_dir(ctx, ctx.P.join(root, "projects")):
        for slug in _slugs(ctx, root):
            t = _lstat_type(ctx, _abs(ctx, root, f"projects/{slug}"))
            if t is not None and t != DIR:
                out.append(f"projects/{slug}")
    return out


def _location_rels(session: str, slugs: list[str], blocked: set[str]) -> list[str]:
    rels: list[str] = []
    for s in slugs:
        if f"projects/{s}" in blocked or "projects" in blocked:
            continue
        rels += [f"projects/{s}/{session}.jsonl", f"projects/{s}/{session}"]
    rels += [f"{d}/{session}" for d in _KINDS if d not in blocked]
    return list(dict.fromkeys(rels))


def _abs(ctx: Context, root: str, rel: str) -> str:
    return ctx.P.join(root, *rel.split("/"))


def _inside(ctx: Context, root: str, path: str) -> bool:
    return path.startswith(root.rstrip(ctx.P.sep) + ctx.P.sep)


def _scan(ctx: Context, root: str, rel: str, plan: _Plan) -> None:
    """Plan one entry by `lstat`: directories and regular files only, nothing is followed."""
    path = _abs(ctx, root, rel)
    st = ctx.fs.lstat(path)
    if st.type == DIR:
        plan.dirs.append(rel)
        for child in ctx.fs.readdir(path):
            _scan(ctx, root, rel + "/" + child, plan)
    elif st.type == FILE:
        plan.files.append((rel, ctx.fs.read_file(path, nofollow=True), st.mode))
    else:
        plan.skipped.append(rel)


def _remove(ctx: Context, path: str) -> None:
    """Remove a location; a link is unlinked and its target left alone."""
    kind = _lstat_type(ctx, path)
    if kind == DIR:
        for child in ctx.fs.readdir(path):
            _remove(ctx, ctx.P.join(path, child))
        ctx.fs.rmdir(path)
    elif kind == JUNCTION:
        ctx.fs.rmdir(path)
    elif kind is not None:
        ctx.fs.unlink(path)


def _mkdirs(ctx: Context, path: str) -> None:
    if _lstat_type(ctx, path) is not None:
        return
    parent = ctx.P.parent(path)
    if parent is not None:
        _mkdirs(ctx, parent)
    ctx.fs.mkdir(path, 0o700)


def _stage(ctx: Context, dst_root: str, top: str, plan: _Plan, staged: list[tuple[str, str]]) -> None:
    """Build one location under a temporary sibling name, recorded in `staged` at once."""
    members_d = [d for d in plan.dirs if d == top or d.startswith(top + "/")]
    members_f = [f for f in plan.files if f[0] == top or f[0].startswith(top + "/")]
    if not members_d and not members_f:
        return
    final = _abs(ctx, dst_root, top)
    _mkdirs(ctx, ctx.P.dirname(final))
    tmp = f"{final}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    staged.append((top, tmp))
    if members_d:
        ctx.fs.mkdir(tmp, 0o700)
        for d in members_d[1:]:
            ctx.fs.mkdir(tmp + ctx.P.sep + d[len(top) + 1:].replace("/", ctx.P.sep), 0o700)
        for rel, data, mode in members_f:
            ctx.fs.write_new(tmp + ctx.P.sep + rel[len(top) + 1:].replace("/", ctx.P.sep), data, mode)
    else:
        _, data, mode = members_f[0]
        ctx.fs.write_new(tmp, data, mode)


@io_errors
def handover_session(
    inp: Inputs, session_id: str, from_name: str, to_name: str, overwrite: bool = False, force: bool = False
) -> HandoverResult:
    """Copy session `session_id` from one account to another (never moves).

    Errors in order: `INVALID_SESSION_ID`, the account gates, `SAME_ACCOUNT`,
    `SESSION_NOT_FOUND`, `SESSION_LIVE` (a live session in the source, or an unknown one unless
    `force`), `SESSION_EXISTS` (unless `overwrite`). Only regular files and directories are
    copied; links, FIFOs and devices are reported in `skipped`. A failure leaves the destination
    as it was.
    """
    if not _ID_RE.fullmatch(session_id):
        raise MultiAccountError(E.INVALID_SESSION_ID, f"invalid session id {session_id!r}")
    ctx = Context(inp)
    ctx.gate(from_name)
    ctx.gate(to_name)
    if ctx.same_account(from_name, to_name):
        raise MultiAccountError(E.SAME_ACCOUNT, f"{from_name!r} and {to_name!r} are the same account")
    src, dst = ctx.config_home(from_name), ctx.config_home(to_name)
    blocked_src, blocked_dst = set(_bad_parents(ctx, src)), set(_bad_parents(ctx, dst))
    src_slugs = [s for s in _slugs(ctx, src) if f"projects/{s}" not in blocked_src]
    dst_slugs = [s for s in _slugs(ctx, dst) if f"projects/{s}" not in blocked_dst]
    rels = _location_rels(session_id, sorted(set(src_slugs) | set(dst_slugs)), blocked_dst)
    src_rels = [r for r in _location_rels(session_id, src_slugs, blocked_src)]
    for r in src_rels:
        if not _inside(ctx, src, _abs(ctx, src, r)):
            raise MultiAccountError(E.INVALID_SESSION_ID, "session location escapes the config home")
    for r in rels:
        if not _inside(ctx, dst, _abs(ctx, dst, r)):
            raise MultiAccountError(E.INVALID_SESSION_ID, "session location escapes the config home")
    found = [r for r in src_rels if _lstat_type(ctx, _abs(ctx, src, r)) is not None]
    if not any(_lstat_type(ctx, _abs(ctx, src, r)) in (FILE, DIR) for r in found):
        raise MultiAccountError(E.SESSION_NOT_FOUND, f"no session {session_id!r} in {from_name!r}")
    for s in live_sessions_in(ctx, from_name):
        if s.session_id == session_id and blocks(s.status, force):
            raise MultiAccountError(E.SESSION_LIVE, f"session {session_id!r} is {s.status} in {from_name!r}")
    for r in found:
        parts = r.split("/")
        needed = ["projects", f"projects/{parts[1]}"] if parts[0] == "projects" else [parts[0]]
        for parent in needed:
            kind = _lstat_type(ctx, _abs(ctx, dst, parent))
            if kind is not None and kind != DIR:
                path = _abs(ctx, dst, parent)
                raise MultiAccountError(E.DESTINATION_BLOCKED, f"{path} is not a plain directory", path)
    existing = [r for r in rels if _lstat_type(ctx, _abs(ctx, dst, r)) is not None]
    if existing and not overwrite:
        raise MultiAccountError(E.SESSION_EXISTS, f"{to_name!r} already has {session_id!r}")
    source = [r for r in found if r in rels]

    plan = _Plan()
    plan.skipped.extend(sorted(blocked_src))
    for rel in source:
        _scan(ctx, src, rel, plan)
    staged: list[tuple[str, str]] = []
    try:
        for rel in source:
            _stage(ctx, dst, rel, plan, staged)
    except FsError:
        for _, tmp in staged:
            _remove(ctx, tmp)
        raise
    for rel in existing:
        _remove(ctx, _abs(ctx, dst, rel))
    for rel, tmp in staged:
        ctx.fs.rename(tmp, _abs(ctx, dst, rel))
    return HandoverResult(sorted(f[0] for f in plan.files), sorted(plan.skipped))
