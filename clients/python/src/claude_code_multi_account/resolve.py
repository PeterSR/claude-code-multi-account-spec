"""A4: decide which account applies."""

from __future__ import annotations

from dataclasses import replace

from . import errors as E
from .context import Context
from .env import launch_env, overridden_by
from .errors import MultiAccountError
from .fs import FsError
from .inputs import Inputs, ResolveOptions
from .ioerr import io_errors
from .mapping import map_config_dir_in
from .marker import parse_marker
from .models import Resolution, SpecWarning
from .paths import nfc

_EMPTY_CHECKED = ("CLAUDE_CONFIG_DIR", "CLAUDE_MULTI_ACCOUNT", "CLAUDE_MULTI_ACCOUNT_SOURCE")


@io_errors
def resolve(inp: Inputs, options: ResolveOptions | None = None) -> Resolution:
    """Resolve the account for `inp`: env, then directory binding, then `default`."""
    opts = options or ResolveOptions()
    ctx = Context(inp)
    warnings: list[SpecWarning] = []
    env = dict(inp.env)
    for key in _EMPTY_CHECKED:
        if env.get(key) == "":
            del env[key]
            warnings.append(SpecWarning(E.EMPTY_ENV))
    if opts.ignore_hook_env and env.get("CLAUDE_MULTI_ACCOUNT_SOURCE") == "hook":
        env.pop("CLAUDE_MULTI_ACCOUNT", None)
        env.pop("CLAUDE_CONFIG_DIR", None)

    selected = env.get("CLAUDE_MULTI_ACCOUNT")
    config_dir = env.get("CLAUDE_CONFIG_DIR")
    if selected is not None:
        ctx.check_name(selected)
    if config_dir is not None:
        return _from_config_dir(ctx, config_dir, selected, warnings)
    if selected is not None:
        return _from_selection(ctx, selected, warnings)
    return _walk(ctx, opts, warnings)


def _global_config_for(ctx: Context, value: str) -> str | None:
    """A1 global config for an explicit `CLAUDE_CONFIG_DIR` value (None when relative)."""
    return ctx.global_config_in(value) if ctx.P.is_abs(value) else None


def _from_config_dir(ctx: Context, value: str, selected: str | None, warnings: list[SpecWarning]) -> Resolution:
    account, canonical, reason = map_config_dir_in(ctx, value)
    if selected is not None and not (account is not None and ctx.same_account(selected, account)):
        if selected != "default" and ctx.P.is_abs(value) and nfc(ctx.P.normalize(value)) == ctx.canonical(selected):
            ctx.gate(selected)
        raise MultiAccountError(E.ENV_CONFLICT, f"CLAUDE_MULTI_ACCOUNT={selected} disagrees with CLAUDE_CONFIG_DIR")
    warns = list(warnings)
    if not canonical:
        warns.append(SpecWarning(E.NON_CANONICAL_CONFIG_DIR))
    try:
        exists = ctx.P.is_abs(value) and ctx.fs.stat(value).type == "dir"
    except FsError:
        exists = False
    global_config = _global_config_for(ctx, value)
    if account is None:
        return Resolution(
            None, None, value, False, "foreign", "config-dir", None, exists, None, [], True, global_config, None,
            overridden_by(ctx, value), [], warns,
        )
    base = _account_result(ctx, account, "config-dir", None, [], [])
    return Resolution(
        account, None, value, canonical, reason, "config-dir", None, exists, base.alias_of, [account], True,
        global_config, base.launch_env, overridden_by(ctx, value), [], warns + base.warnings,
    )


def _from_selection(ctx: Context, name: str, warnings: list[SpecWarning]) -> Resolution:
    """Only `CLAUDE_MULTI_ACCOUNT` set: `claude` itself ignores it, so it may not be applied."""
    res = _account_result(ctx, name, "env", None, warnings, [])
    default = ctx.entry("default")
    entry = ctx.entry(name)
    in_default_group = name == "default" or (
        entry is not None and default is not None and bool(entry.group) and entry.group is default.group
    )
    if in_default_group:
        return res
    if ctx.env.get("CLAUDECODE") == "1":
        raise MultiAccountError(E.ENV_CONFLICT, f"CLAUDE_MULTI_ACCOUNT={name} was never applied to this claude")
    return replace(res, applied=False, warnings=res.warnings + [SpecWarning(E.ENV_NOT_APPLIED)])


def _account_result(
    ctx: Context,
    name: str,
    source: str,
    matched: str | None,
    warnings: list[SpecWarning],
    ignored: list[str],
    bind_path: str | None = None,
    candidates: list[str] | None = None,
) -> Resolution:
    entry = ctx.gate(name, bind_path)
    config = ctx.config_home(name)
    warns = list(warnings)
    if name != "default" and name in ctx.reserved:
        warns.append(SpecWarning(E.RESERVED_NAME))
    return Resolution(
        name, None, config, True, None, source, matched, True, entry.alias_of, candidates or [name], True,
        ctx.global_config_path(name), launch_env(ctx, name), overridden_by(ctx, config), list(ignored), warns,
    )


def _levels(ctx: Context, opts: ResolveOptions) -> list[str]:
    ceilings = [ctx.P.normalize(c) for c in opts.ceiling_dirs]
    levels: list[str] = []
    cur: str | None = ctx.P.normalize(ctx.inp.cwd)
    while cur is not None:
        levels.append(cur)
        if any(ctx.fold_eq(cur, c) for c in ceilings):
            break
        cur = ctx.P.parent(cur)
    return levels


def _is_marker_candidate(ctx: Context, path: str) -> bool:
    try:
        ctx.fs.lstat(path)
        return ctx.fs.stat(path).type != "dir"
    except FsError:
        return False


def _has_git(ctx: Context, level: str) -> bool:
    try:
        ctx.fs.lstat(ctx.P.join(level, ".git"))
        return True
    except FsError:
        return False


def _walk(ctx: Context, opts: ResolveOptions, warnings: list[SpecWarning]) -> Resolution:
    levels = _levels(ctx, opts)
    git = [_has_git(ctx, d) for d in levels]
    ignored: list[str] = []
    warns = list(warnings)
    claimants_loaded = False
    for i, level in enumerate(levels):
        marker_path = ctx.P.join(level, ".claude-account")
        if _is_marker_candidate(ctx, marker_path) and not opts.trust_repo_markers and any(git[i:]):
            ignored.append(marker_path)
            warns.append(SpecWarning(E.MARKER_IGNORED_IN_REPO, marker_path))
        else:
            marker = parse_marker(ctx.fs, marker_path)
            if marker.kind in ("account", "default", "list") and marker.name is not None:
                ctx.gate(marker.candidates[0], marker_path)
                for later in marker.candidates[1:]:
                    entry = ctx.entry(later)
                    if later != "default" and (entry is None or entry.state != "ok"):
                        warns.append(SpecWarning(E.CANDIDATE_UNAVAILABLE, ctx.entry_path(later)))
                return _account_result(
                    ctx, marker.name, "marker-file", marker_path, warns, ignored, marker_path, marker.candidates
                )
            if marker.kind == "pool":
                return Resolution(
                    None, marker.pool, None, False, None, "marker-file", marker_path, False, None, [], True, None,
                    None, overridden_by(ctx, None), ignored, warns,
                )
        if not claimants_loaded:
            for e in ctx.entries():
                if e.state == "ok":
                    sf = ctx.spec_file(e)
                    if sf.kind == "invalid":
                        raise MultiAccountError(E.SPEC_FILE_INVALID, "invalid spec file", sf.path)
            claimants_loaded = True
        claimants = _claimants(ctx, level)
        if len(claimants) > 1:
            raise MultiAccountError(E.CLAIM_CONFLICT, f"{', '.join(claimants)} claim the same directory", level)
        if claimants:
            return _account_result(ctx, claimants[0], "claim", level, warns, ignored, level)
    return _account_result(ctx, "default", "default", None, warns, ignored)


def _claimants(ctx: Context, level: str) -> list[str]:
    try:
        here = ctx.fs.stat(level)
    except FsError:
        return []
    out: list[str] = []
    for e in ctx.primaries():
        for claim in ctx.claims(e):
            try:
                st = ctx.fs.stat(claim)
            except FsError:
                continue
            if (st.dev, st.ino) == (here.dev, here.ino):
                out.append(e.name)
                break
    return out


__all__ = ["resolve"]
