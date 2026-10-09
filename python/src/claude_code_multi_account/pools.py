"""B6: pools of accounts and ordered candidate lists."""

from __future__ import annotations

from . import errors as E
from .context import Context
from .errors import MultiAccountError
from .inputs import Inputs
from .ioerr import io_errors
from .limits import is_available
from .paths import is_valid_name


def _members(ctx: Context, pool: str) -> list[str]:
    if not is_valid_name(pool):
        raise MultiAccountError(E.INVALID_NAME, f"invalid pool name {pool!r}")
    for e in ctx.entries():
        if e.state == "ok":
            sf = ctx.spec_file(e)
            if sf.kind == "invalid":
                raise MultiAccountError(E.SPEC_FILE_INVALID, "invalid spec file", sf.path)
    found: list[tuple[int, str]] = []
    for e in ctx.primaries():
        data = ctx.spec_file(e).data
        if data is not None and data.get("pool") == pool:
            found.append((-int(data.get("priority", 0)), e.name))
    return [n for _, n in sorted(found)]


def _first_available(ctx: Context, names: list[str], model: str | None) -> str | None:
    return next((n for n in names if is_available(ctx, n, model)), None)


def _rotation(order: list[str], current: str) -> list[str]:
    """Entries after `current`, then those up to and including it (all when not present)."""
    if current in order:
        i = order.index(current)
        return order[i + 1:] + order[: i + 1]
    return order


@io_errors
def pick(inp: Inputs, pool: str, model: str | None = None) -> str | None:
    """The available member with the highest priority (ties by name), or None."""
    ctx = Context(inp)
    return _first_available(ctx, _members(ctx, pool), model)


@io_errors
def next_in_pool(inp: Inputs, pool: str, current: str, model: str | None = None) -> str | None:
    """The next available member after `current` in pick order, wrapping; None if none."""
    ctx = Context(inp)
    return _first_available(ctx, _rotation(_members(ctx, pool), current), model)


def _usable(ctx: Context, candidates: list[str]) -> list[str]:
    """Validate every name (`INVALID_NAME`), then drop those that are not `default` or an ok account."""
    for name in candidates:
        ctx.check_name(name)
    return [n for n in candidates if n == "default" or (ctx.entry(n) is not None and ctx.entry(n).state == "ok")]  # type: ignore[union-attr]


@io_errors
def pick_from(inp: Inputs, candidates: list[str], model: str | None = None) -> str | None:
    """The first available account of an ordered list (normally `Resolution.candidates`).

    Candidates that are not usable accounts are skipped, not errors; a bad name is `INVALID_NAME`.
    """
    ctx = Context(inp)
    return _first_available(ctx, _usable(ctx, list(candidates)), model)


@io_errors
def next_from(inp: Inputs, candidates: list[str], current: str, model: str | None = None) -> str | None:
    """The next available account after `current` in an ordered list, wrapping; None if none.

    An alias group counts as one account: candidates that are the same account as `current` are
    tried last, and only once.
    """
    ctx = Context(inp)
    usable = _usable(ctx, list(candidates))
    pos = next((i for i, n in enumerate(usable) if ctx.same_account(n, current)), None)
    if pos is None:
        order = usable
    else:
        rest = usable[pos + 1:] + usable[:pos]
        order = [n for n in rest if not ctx.same_account(n, current)] + [usable[pos]]
    return _first_available(ctx, order, model)


@io_errors
def pool_members(inp: Inputs, pool: str) -> list[str]:
    """Members of `pool` in `pick` order, without looking at availability."""
    return _members(Context(inp), pool)
