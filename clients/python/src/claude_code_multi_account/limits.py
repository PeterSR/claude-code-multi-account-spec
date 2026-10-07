"""B5: availability state in `.multi-account-state.json`."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from . import errors as E
from .atomic import lock_dir, write_file_atomic
from .context import Context
from .errors import MultiAccountError
from .fs import FILE, FsError
from .inputs import Inputs
from .ioerr import io_errors
from .jsonio import MAX_DEPTH, parse_json
from .models import LimitEntry, Limits
from .timeutil import Instant, format_time, instant_of, parse_instant

STATE_FILE = ".multi-account-state.json"


class _Invalid(Exception):
    """The state file is present but not understood."""


def _load_state(ctx: Context, path: str) -> dict[str, Any]:
    """The state object (an empty one when the file or link target is missing).

    Raises `_Invalid` for anything present that is not a version 1 JSON object.
    """
    try:
        if ctx.fs.stat(path).type != FILE:
            raise _Invalid
        data = parse_json(ctx.fs.read_file(path), MAX_DEPTH)
    except FsError as e:
        if e.code in ("ENOENT", "ENOTDIR"):
            return {"version": 1, "limits": []}
        raise _Invalid from e
    except ValueError as e:
        raise _Invalid from e
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(data, dict) or isinstance(version, bool) or version != 1:
        raise _Invalid
    if "limits" in data and not isinstance(data["limits"], list):
        raise _Invalid
    data.setdefault("limits", [])
    return data


def _until(entry: object) -> Instant | None:
    return parse_instant(entry.get("until")) if isinstance(entry, dict) else None


def _key(entry: object) -> tuple[str, Any] | None:
    if not isinstance(entry, dict) or not isinstance(entry.get("window"), str):
        return None
    return entry["window"], entry.get("model")


def _modify(
    ctx: Context, path: str, change: Callable[[list[Any]], list[Any]]
) -> Limits:
    """Read, change and write the state file with the lock held across all three."""
    now = instant_of(ctx.now())
    assert ctx.inp.clock is not None
    with lock_dir(ctx.fs, path + ".lock", ctx.inp.clock, ctx.inp.lock_wait):
        try:
            state = _load_state(ctx, path)
        except _Invalid as e:
            raise MultiAccountError(E.STATE_FILE_INVALID, "state file is not understood", path) from e
        limits = change(list(state["limits"]))
        state["limits"] = [e for e in limits if (u := _until(e)) is None or u > now]
        state["version"] = 1
        write_file_atomic(ctx.fs, ctx.P, path, json.dumps(state, indent=2).encode("utf-8"))
    return Limits(state["limits"])


def _validate(entry: LimitEntry) -> None:
    ok = (
        isinstance(entry.window, str) and entry.window != ""
        and (entry.model is None or (isinstance(entry.model, str) and entry.model != ""))
        and parse_instant(entry.until) is not None
        and (entry.reason is None or isinstance(entry.reason, str))
        and (entry.updated_by is None or isinstance(entry.updated_by, str))
    )
    if not ok:
        raise MultiAccountError(E.INVALID_ENTRY, "invalid limit entry")


@io_errors
def mark_limited(inp: Inputs, name: str, entry: LimitEntry) -> Limits:
    """Record a limit. The later `until` wins per `(window, model)`; past entries are dropped.

    Other tools' entries and keys are preserved verbatim. An unreadable or non-version-1 state
    file is never overwritten (`STATE_FILE_INVALID`); a bad `entry` is `INVALID_ENTRY`.
    """
    ctx = Context(inp)
    ctx.gate(name)
    _validate(entry)
    path = ctx.P.join(ctx.config_home(name), STATE_FILE)
    new: dict[str, Any] = {"window": entry.window, "model": entry.model, "until": entry.until}
    if entry.reason is not None:
        new["reason"] = entry.reason
    if entry.updated_by is not None:
        new["updatedBy"] = entry.updated_by
    new["updatedAt"] = format_time(ctx.now())
    new_until = parse_instant(entry.until)
    assert new_until is not None

    def change(limits: list[Any]) -> list[Any]:
        for i, old in enumerate(limits):
            if _key(old) == (entry.window, entry.model):
                old_until = _until(old)
                if old_until is None or new_until >= old_until:
                    limits[i] = new
                return limits
        limits.append(new)
        return limits

    return _modify(ctx, path, change)


@io_errors
def clear_limited(inp: Inputs, name: str, window: str, model: str | None = None) -> Limits:
    """Remove the `(window, model)` entries and drop past ones. No state file means no write."""
    ctx = Context(inp)
    ctx.gate(name)
    path = ctx.P.join(ctx.config_home(name), STATE_FILE)
    try:
        ctx.fs.lstat(path)
    except FsError:
        return Limits([])
    return _modify(ctx, path, lambda ls: [e for e in ls if _key(e) != (window, model)])


def is_available(ctx: Context, name: str, model: str | None) -> bool:
    """True when no entry applying to `model` has `until > now` (no gate). Unreadable state
    counts as empty."""
    try:
        state = _load_state(ctx, ctx.P.join(ctx.config_home(name), STATE_FILE))
    except _Invalid:
        return True
    now = instant_of(ctx.now())
    for e in state["limits"]:
        until = _until(e)
        if until is None or until <= now:
            continue
        m = e.get("model")
        if m is None or (model is not None and m == model):
            return False
    return True


@io_errors
def available(inp: Inputs, name: str, model: str | None = None) -> bool:
    """Whether `name` is free of limits applying to `model` at the clock's now."""
    ctx = Context(inp)
    ctx.gate(name)
    return is_available(ctx, name, model)


def _applying(ctx: Context, name: str, model: str | None) -> list[tuple[Instant, Any]]:
    """Readable entries that apply to `model` (null model, or equal), with their instants."""
    try:
        state = _load_state(ctx, ctx.P.join(ctx.config_home(name), STATE_FILE))
    except _Invalid:
        return []
    out: list[tuple[Instant, Any]] = []
    for e in state["limits"]:
        until = _until(e)
        if until is None:
            continue
        m = e.get("model")
        if m is None or (model is not None and m == model):
            out.append((until, e))
    return out


@io_errors
def limits(inp: Inputs, name: str) -> Limits:
    """The state file's limit entries in file order (past ones included); unreadable state is empty."""
    ctx = Context(inp)
    ctx.gate(name)
    try:
        state = _load_state(ctx, ctx.P.join(ctx.config_home(name), STATE_FILE))
    except _Invalid:
        return Limits([])
    out: list[Any] = []
    for e in state["limits"]:
        if not isinstance(e, dict) or not isinstance(e.get("window"), str) or _until(e) is None:
            continue

        def text(k: str) -> str | None:
            v = e.get(k)
            return v if isinstance(v, str) else None

        out.append({
            "window": e["window"], "model": text("model"), "until": e["until"],
            "reason": text("reason"), "updatedBy": text("updatedBy"), "updatedAt": text("updatedAt"),
        })
    return Limits(out)


@io_errors
def available_at(inp: Inputs, name: str, model: str | None = None) -> str | None:
    """When `name` is next available for `model`: None if now, else the latest applying `until` in UTC."""
    ctx = Context(inp)
    ctx.gate(name)
    now = instant_of(ctx.now())
    later = [u for u, _ in _applying(ctx, name, model) if u > now]
    if not later:
        return None
    secs, nanos = max(later)
    text = datetime.fromtimestamp(secs, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    ms = nanos // 1_000_000
    return f"{text}.{ms:03d}Z" if ms else text + "Z"
