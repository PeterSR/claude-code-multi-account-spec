"""B7: the active slot (`~/.claude` and `~/.claude.json` as links to an account)."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable

from . import errors as E
from .atomic import lock_dir
from .context import Context
from .env import credential_manager_in_use
from .errors import MultiAccountError
from .fs import DIR, FILE, JUNCTION, SYMLINK, FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import SlotState
from .paths import is_valid_name
from .sessions import blocks, live_sessions_in

_MISSING = ("ENOENT", "ENOTDIR")


def _unsupported(ctx: Context) -> bool:
    inp = ctx.inp
    if inp.platform == "darwin":
        return True
    if inp.platform == "win32":
        j = ctx.P.join(ctx.home, ".claude.json")
        return credential_manager_in_use(ctx, j) or not inp.can_create_symlinks
    return False


def _resolve_target(ctx: Context, target: str) -> str:
    return ctx.P.normalize(target) if ctx.P.is_abs(target) else ctx.P.join(ctx.home, target)


def _lstat_type(ctx: Context, path: str) -> str | None:
    try:
        return ctx.fs.lstat(path).type
    except FsError:
        return None


def slot_in(ctx: Context) -> SlotState:
    """Compute the slot state (B7) from the filesystem."""
    P, fs = ctx.P, ctx.fs
    if _unsupported(ctx):
        return SlotState("unsupported")
    link = P.join(ctx.home, ".claude")
    json_link = P.join(ctx.home, ".claude.json")
    try:
        st = fs.lstat(link)
    except FsError as e:
        return SlotState("unmanaged" if e.code in _MISSING else "broken")
    if st.type == DIR:
        return SlotState("unmanaged")
    if st.type not in (SYMLINK, JUNCTION):
        return SlotState("broken")
    try:
        target = _resolve_target(ctx, fs.readlink(link))
        prefix = P.join(ctx.home, ".claude-")
        name = target[len(prefix):] if target.startswith(prefix) else ""
        if not is_valid_name(name) or name == "default" or P.join(ctx.home, ".claude-" + name) != target:
            return SlotState("broken")
        if fs.stat(target).type != DIR:
            return SlotState("broken")
        if fs.lstat(json_link).type != SYMLINK:
            return SlotState("broken")
        json_target = _resolve_target(ctx, fs.readlink(json_link))
        if json_target != P.join(target, ".claude.json"):
            return SlotState("broken")
        try:
            if fs.lstat(json_target).type != FILE:
                return SlotState("broken")
        except FsError as e:
            if e.code not in _MISSING:
                return SlotState("broken")
        if _lstat_type(ctx, P.join(target, ".credentials.json")) in (SYMLINK, JUNCTION):
            return SlotState("broken")
    except FsError:
        return SlotState("broken")
    return SlotState("managed", name)


@io_errors
def slot(inp: Inputs) -> SlotState:
    """Report `unmanaged`, `managed` (with name), `broken` or `unsupported`."""
    return slot_in(Context(inp))


def _check_named(ctx: Context, name: str) -> None:
    if not is_valid_name(name) or name == "default":
        raise MultiAccountError(E.INVALID_NAME, f"invalid account name {name!r}")


def _refuse_if_unsupported(state: SlotState) -> None:
    if state.state == "unsupported":
        raise MultiAccountError(E.SLOT_UNSUPPORTED, "the login would not follow a link here")


def _temp(path: str) -> str:
    return f"{path}.tmp.{os.getpid()}.{secrets.token_hex(6)}"


def _probe_links(ctx: Context) -> None:
    """Prove that both link kinds can be created in `home` before anything is moved."""
    for kind in ("file", "dir"):
        probe = _temp(ctx.P.join(ctx.home, ".claude-slot-probe"))
        try:
            ctx.fs.symlink(ctx.P.join(ctx.home, ".claude-slot-probe-target"), probe, kind)
        except FsError as e:
            code = E.SLOT_UNSUPPORTED if ctx.inp.platform == "win32" else E.IO_ERROR
            raise MultiAccountError(code, f"cannot create links: {e.code}", e.path) from e
        _drop_link(ctx, probe)


def _drop_link(ctx: Context, path: str) -> None:
    try:
        if _lstat_type(ctx, path) == JUNCTION:
            ctx.fs.rmdir(path)
        else:
            ctx.fs.unlink(path)
    except FsError:
        pass


@io_errors
def adopt(inp: Inputs, name: str, force: bool = False) -> SlotState:
    """Turn an unmanaged slot into a managed one by moving `~/.claude` to `~/.claude-<name>`.

    Refuses on an existing account, on two competing `.claude.json` files and on a live (or,
    without `force`, unknown) session of `default`; rolls back every step if a later one fails.
    """
    ctx = Context(inp)
    P, fs = ctx.P, ctx.fs
    state = slot_in(ctx)
    _refuse_if_unsupported(state)
    _check_named(ctx, name)
    if name in ctx.reserved:
        raise MultiAccountError(E.RESERVED_NAME, f"{name!r} is reserved")
    if state.state != "unmanaged":
        raise MultiAccountError(E.SLOT_STATE, f"slot is {state.state}, expected unmanaged")
    account = ctx.entry_path(name)
    if _lstat_type(ctx, account) is not None:
        raise MultiAccountError(E.ACCOUNT_EXISTS, f"{account} exists", account)
    link = P.join(ctx.home, ".claude")
    json_link = P.join(ctx.home, ".claude.json")
    inner = P.join(link, ".claude.json")
    outer_type, inner_type = _lstat_type(ctx, json_link), _lstat_type(ctx, inner)
    if outer_type is not None and inner_type is not None:
        raise MultiAccountError(E.SLOT_CONFLICT, "both ~/.claude.json and ~/.claude/.claude.json exist", inner)
    if outer_type not in (None, FILE):
        raise MultiAccountError(E.SLOT_TARGET_INVALID, f"{json_link} is not a regular file", json_link)
    if outer_type is None and inner_type not in (None, FILE):
        raise MultiAccountError(E.SLOT_TARGET_INVALID, f"{inner} is not a regular file", inner)
    creds = P.join(link, ".credentials.json")
    if _lstat_type(ctx, creds) in (SYMLINK, JUNCTION):
        raise MultiAccountError(E.SLOT_TARGET_INVALID, f"{creds} is a link", creds)
    assert inp.clock is not None
    with lock_dir(fs, P.join(ctx.home, ".claude-slot.lock"), inp.clock, inp.lock_wait):
        if any(blocks(s.status, force) for s in live_sessions_in(ctx, "default")):
            raise MultiAccountError(E.SESSION_LIVE, "default has a live or unknown session")
        _probe_links(ctx)
        undo: list[Callable[[], None]] = []
        try:
            if _lstat_type(ctx, link) is not None:
                fs.rename(link, account)
                undo.append(lambda: fs.rename(account, link))
            else:
                fs.mkdir(account, 0o700)
                undo.append(lambda: fs.rmdir(account))
            new_inner = P.join(account, ".claude.json")
            if outer_type is not None:
                fs.rename(json_link, new_inner)
                undo.append(lambda: fs.rename(new_inner, json_link))
            fs.symlink(account, link, "dir")
            undo.append(lambda: _drop_link(ctx, link))
            fs.symlink(new_inner, json_link, "file")
        except FsError:
            for step in reversed(undo):
                try:
                    step()
                except FsError:
                    pass
            raise
    return slot_in(ctx)


@io_errors
def activate(inp: Inputs, name: str, force: bool = False) -> SlotState:
    """Re-point a managed slot at `name` (a named account). Refuses with `SESSION_LIVE` while the
    current slot account has a live (or, without `force`, unknown) session. The two links are
    replaced one after the other; on Windows `~/.claude` is removed and created again."""
    ctx = Context(inp)
    P, fs = ctx.P, ctx.fs
    state = slot_in(ctx)
    _refuse_if_unsupported(state)
    _check_named(ctx, name)
    ctx.gate(name)
    if state.state != "managed" or state.name is None:
        raise MultiAccountError(E.SLOT_STATE, f"slot is {state.state}, expected managed")
    account = ctx.entry_path(name)
    creds = P.join(account, ".credentials.json")
    target_json = P.join(account, ".claude.json")
    if _lstat_type(ctx, creds) in (SYMLINK, JUNCTION):
        raise MultiAccountError(E.SLOT_TARGET_INVALID, f"{creds} is a link", creds)
    if _lstat_type(ctx, target_json) not in (None, FILE):
        raise MultiAccountError(E.SLOT_TARGET_INVALID, f"{target_json} is not a regular file", target_json)
    link = P.join(ctx.home, ".claude")
    json_link = P.join(ctx.home, ".claude.json")
    assert inp.clock is not None
    with lock_dir(fs, P.join(ctx.home, ".claude-slot.lock"), inp.clock, inp.lock_wait):
        if any(blocks(s.status, force) for s in live_sessions_in(ctx, state.name)):
            raise MultiAccountError(E.SESSION_LIVE, f"{state.name!r} has a live or unknown session")
        tmp = _temp(json_link)
        fs.symlink(target_json, tmp, "file")
        _rename_or_clean(ctx, tmp, json_link)
        if inp.platform == "win32":
            old = fs.readlink(link)
            fs.rmdir(link)
            try:
                fs.symlink(account, link, "dir")
            except FsError:
                fs.symlink(old, link, "dir")  # put the previous link back
                raise
        else:
            tmp = _temp(link)
            fs.symlink(account, tmp, "dir")
            _rename_or_clean(ctx, tmp, link)
    return slot_in(ctx)


def _rename_or_clean(ctx: Context, tmp: str, final: str) -> None:
    try:
        ctx.fs.rename(tmp, final)
    except FsError:
        _drop_link(ctx, tmp)
        raise
