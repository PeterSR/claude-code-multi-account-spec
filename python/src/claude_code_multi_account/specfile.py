"""A3: read and edit an account's spec file (`.multi-account.json`), including claims."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import errors as E
from .atomic import lock_dir, write_file_atomic
from .context import SPEC_FILE, Context, Entry
from .errors import MultiAccountError
from .fs import FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import Claims
from .paths import fold


def _invalid(path: str) -> MultiAccountError:
    return MultiAccountError(E.SPEC_FILE_INVALID, "invalid spec file", path)


@io_errors
def spec_file(inp: Inputs, name: str) -> dict[str, Any] | None:
    """The validated spec file object of `name`, or None when absent (`SPEC_FILE_INVALID` if bad)."""
    ctx = Context(inp)
    sf = ctx.spec_file(ctx.gate(name))
    if sf.kind == "invalid":
        raise _invalid(sf.path)
    return sf.data


def _modify(
    ctx: Context, entry: Entry, change: Callable[[dict[str, Any], bool], dict[str, Any] | None]
) -> dict[str, Any] | None:
    """Under the lock read the file (absent: `{"version": 1}`), apply `change(data, existed)`.

    `change` returns the new object to write, or None to write nothing. The result is the object
    written, or the unchanged one.
    """
    path = ctx.P.join(entry.dir, SPEC_FILE)
    clock = ctx.inp.clock
    if clock is None:
        raise ValueError("this operation needs Inputs.clock")
    with lock_dir(ctx.fs, path + ".lock", clock, ctx.inp.lock_wait):
        sf = ctx.read_spec_fresh(entry)
        if sf.kind == "invalid":
            raise _invalid(path)
        existed = sf.kind == "ok"
        data: dict[str, Any] = dict(sf.data) if sf.data is not None else {"version": 1}
        new = change(json.loads(json.dumps(data)), existed)
        if new is None:
            return data
        if not ctx.valid_spec_data(new):
            raise MultiAccountError(E.INVALID_ENTRY, "result is not a valid spec file")
        write_file_atomic(ctx.fs, ctx.P, path, json.dumps(new, indent=2).encode("utf-8"))
        return new


@io_errors
def update_spec_file(inp: Inputs, name: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge `patch` into the spec file: a None value deletes the key. Unknown keys are kept."""
    ctx = Context(inp)
    entry = ctx.gate(name)
    if not isinstance(patch, dict):
        raise MultiAccountError(E.INVALID_ENTRY, "patch must be an object")

    def change(data: dict[str, Any], existed: bool) -> dict[str, Any] | None:
        for k, v in patch.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        return data

    result = _modify(ctx, entry, change)
    assert result is not None
    return result


def _same_dir(ctx: Context, a: str, b: str) -> bool:
    """Same directory by `(dev, ino)`; when either cannot be stat'ed, equal normalised paths."""
    try:
        sa, sb = ctx.fs.stat(a), ctx.fs.stat(b)
        return (sa.dev, sa.ino) == (sb.dev, sb.ino)
    except FsError:
        pass
    na, nb = ctx.P.normalize(a), ctx.P.normalize(b)
    return fold(na) == fold(nb) if ctx.case_insensitive else na == nb


def _expand(ctx: Context, directory: str) -> str:
    ok = ctx.P.is_abs(directory) or directory.startswith("~/") or (ctx.P.win and directory.startswith("~\\"))
    expanded = ctx.expand_claim(directory) if ok else None
    if expanded is None:
        raise MultiAccountError(E.INVALID_ENTRY, f"claim must be absolute or start with ~/: {directory!r}")
    return expanded


def _stored_form(ctx: Context, expanded: str) -> str:
    home = ctx.P.normalize(ctx.home)
    cmp_e, cmp_h = (fold(expanded), fold(home)) if ctx.case_insensitive else (expanded, home)
    if cmp_e == cmp_h:
        return "~/"
    prefix = home.rstrip(ctx.P.sep) + ctx.P.sep
    cmp_p = fold(prefix) if ctx.case_insensitive else prefix
    if cmp_e.startswith(cmp_p):
        return "~/" + expanded[len(prefix):].replace(ctx.P.sep, "/")
    return expanded


def _directories(data: dict[str, Any]) -> list[str]:
    d = data.get("directories", [])
    return list(d) if isinstance(d, list) else []


@io_errors
def claim(inp: Inputs, name: str, directory: str) -> Claims:
    """Add `directory` to the account's claims (stored as `~/...` below home).

    `CLAIM_CONFLICT` when another account already claims the same directory.
    """
    ctx = Context(inp)
    entry = ctx.gate(name)
    expanded = _expand(ctx, directory)
    for other in ctx.primaries():
        if other is entry or (entry.group and other.group is entry.group):
            continue
        sf = ctx.spec_file(other)
        if sf.kind == "invalid":
            raise _invalid(sf.path)
        for c in ctx.claims(other):
            if _same_dir(ctx, c, expanded):
                raise MultiAccountError(E.CLAIM_CONFLICT, f"{other.name!r} already claims {expanded}", expanded)
    stored = _stored_form(ctx, expanded)

    def change(data: dict[str, Any], existed: bool) -> dict[str, Any] | None:
        for d in _directories(data):
            e = ctx.expand_claim(d)
            if e is not None and _same_dir(ctx, e, expanded):
                return None
        data["directories"] = _directories(data) + [stored]
        return data

    result = _modify(ctx, entry, change)
    return Claims(_directories(result) if result is not None else [])


@io_errors
def unclaim(inp: Inputs, name: str, directory: str) -> Claims:
    """Remove every claim of the account that is the same directory as `directory`."""
    ctx = Context(inp)
    entry = ctx.gate(name)
    expanded = _expand(ctx, directory)
    pre = ctx.read_spec_fresh(entry)
    if pre.kind == "invalid":
        raise _invalid(pre.path)
    if pre.kind == "none":
        return Claims([])

    def change(data: dict[str, Any], existed: bool) -> dict[str, Any] | None:
        kept = [d for d in _directories(data) if not _same_claim(ctx, d, expanded)]
        if len(kept) == len(_directories(data)):
            return None
        data["directories"] = kept
        return data

    result = _modify(ctx, entry, change)
    return Claims(_directories(result) if result is not None else [])


def _same_claim(ctx: Context, stored: str, expanded: str) -> bool:
    e = ctx.expand_claim(stored)
    return e is not None and _same_dir(ctx, e, expanded)
