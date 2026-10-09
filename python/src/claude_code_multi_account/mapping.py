"""A4 step 1: map a `CLAUDE_CONFIG_DIR` value to an account."""

from __future__ import annotations

from . import errors as E
from .context import Context
from .fs import FsError
from .inputs import Inputs
from .ioerr import io_errors
from .models import ConfigDirMapping, SpecWarning
from .paths import fold, nfc

# (account, canonical, reason)
_Mapped = tuple[str | None, bool, str | None]


def map_config_dir_in(ctx: Context, value: str) -> _Mapped:
    """The mapping table. Rows 1 to 3 range over ok named accounts, 4 and 5 add `default`."""
    entries = ctx.entries()
    named = [e for e in entries if e.name != "default" and e.state == "ok"]
    for e in named:
        if value == e.dir:
            return e.name, True, None
    if not ctx.P.is_abs(value):
        return None, False, "foreign"
    norm = nfc(ctx.P.normalize(value))
    for e in named:
        if norm == e.dir:
            return e.name, False, "not-normalized"
    if ctx.case_insensitive:
        for e in named:
            if fold(norm) == fold(e.dir):
                return e.name, False, "case-mismatch"
    if norm == ctx.config_home("default"):
        return "default", False, "default-via-config-dir"
    try:
        target = ctx.fs.realpath(value)
    except FsError:
        return None, False, "foreign"
    for e in named + [entries[0]]:
        try:
            if ctx.fs.realpath(e.dir) == target:
                return e.name, False, "resolved-target"
        except FsError:
            continue
    return None, False, "foreign"


@io_errors
def map_config_dir(inp: Inputs, value: str) -> ConfigDirMapping:
    """Map a `CLAUDE_CONFIG_DIR` value to an account, with the reason when not canonical."""
    account, canonical, reason = map_config_dir_in(Context(inp), value)
    warnings = [] if canonical else [SpecWarning(E.NON_CANONICAL_CONFIG_DIR)]
    return ConfigDirMapping(account, canonical, reason, warnings)
