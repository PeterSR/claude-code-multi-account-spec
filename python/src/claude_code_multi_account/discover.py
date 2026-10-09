"""Account discovery: `list_accounts` (the `discover` case op)."""

from __future__ import annotations

from . import errors as E
from .fs import FsError
from .context import SPEC_FILE, Context
from .inputs import Inputs
from .ioerr import io_errors
from .models import Account, AccountList, Conflict, SpecError, SpecWarning


@io_errors
def list_accounts(inp: Inputs) -> AccountList:
    """List `default` and every discovered account, with alias and claim-conflict facts."""
    ctx = Context(inp)
    accounts: list[Account] = []
    for e in ctx.entries():
        ok = e.state == "ok"
        spec_error = None
        has_spec = has_global = False
        if ok:
            has_spec = ctx.is_regular(ctx.P.join(e.dir, SPEC_FILE))
            has_global = ctx.is_regular(ctx.global_config_path(e.name))
            sf = ctx.spec_file(e)
            if sf.kind == "invalid":
                spec_error = SpecError(E.SPEC_FILE_INVALID, sf.path)
        warnings = [SpecWarning(E.RESERVED_NAME)] if e.name != "default" and e.name in ctx.reserved else []
        accounts.append(Account(e.name, e.dir, e.state, has_spec, has_global, e.alias_of, spec_error, warnings))
    return AccountList(accounts, _conflicts(ctx), ctx.top_warnings())


def _conflicts(ctx: Context) -> list[Conflict]:
    groups: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for e in ctx.primaries():
        for claim in ctx.claims(e):
            try:
                st = ctx.fs.stat(claim)
            except FsError:  # missing or unreadable claims are ignored
                continue
            members = groups.setdefault((st.dev, st.ino), [])
            if all(name != e.name for _, name in members):
                members.append((claim, e.name))
    out = [Conflict(m[0][0], [n for _, n in m]) for m in groups.values() if len(m) >= 2]
    return sorted(out, key=lambda c: c.path)
