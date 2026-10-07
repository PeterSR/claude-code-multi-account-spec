"""A2: create an account directory."""

from __future__ import annotations

from . import errors as E
import json

from .atomic import lock_dir, write_file_atomic
from .context import SPEC_FILE, Context
from .errors import MultiAccountError
from .fs import FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import Created
from .paths import is_valid_name
from .timeutil import format_time


@io_errors
def create(inp: Inputs, name: str) -> Created:
    """Make `~/.claude-<name>` (mode 0700) with a minimal `.multi-account.json`.

    Fails with `INVALID_NAME`, `RESERVED_NAME` or `ACCOUNT_EXISTS`. Needs `inp.clock`.
    """
    ctx = Context(inp)
    if not is_valid_name(name):
        raise MultiAccountError(E.INVALID_NAME, f"invalid account name {name!r}")
    if name in ctx.reserved:
        raise MultiAccountError(E.RESERVED_NAME, f"{name!r} is reserved")
    if inp.clock is None:
        raise ValueError("create needs Inputs.clock")
    path = ctx.entry_path(name)
    try:
        ctx.fs.lstat(path)
    except FsError:
        pass
    else:
        raise MultiAccountError(E.ACCOUNT_EXISTS, f"{path} exists", path)
    spec = {"version": 1, "createdAt": format_time(inp.clock.now())}
    ctx.fs.mkdir(path, 0o700)
    target = ctx.P.join(path, SPEC_FILE)
    with lock_dir(ctx.fs, target + ".lock", inp.clock, inp.lock_wait):
        write_file_atomic(ctx.fs, ctx.P, target, json.dumps(spec, indent=2).encode("utf-8"))
    return Created(name, ctx.canonical(name))
