"""B2: identity, cached usage and read-only credentials. No network, no token refresh."""

from __future__ import annotations

from typing import Any

from .context import Context
from .env import credential_locations
from .fs import LINK_TYPES, FsError
from .inputs import Inputs
from .ioerr import io_errors
from .jsonio import parse_json
from .models import Credentials, Identity, Resolution, Usage
from .timeutil import format_millis


def _global_config_data(ctx: Context, target: str | Resolution) -> Any:
    """Parsed global config for a name (account gate applies) or a resolution (its `globalConfig`)."""
    if isinstance(target, Resolution):
        return ctx.read_json(target.global_config) if target.global_config is not None else None
    ctx.gate(target)
    return ctx.read_json(ctx.global_config_path(target))


def _identity_of(data: Any) -> Identity | None:
    if not isinstance(data, dict) or not isinstance(data.get("oauthAccount"), dict):
        return None
    o = data["oauthAccount"]
    return Identity(
        email=o.get("emailAddress"),
        org_name=o.get("organizationName"),
        org_uuid=o.get("organizationUuid"),
        organization_type=o.get("organizationType"),
        billing_type=o.get("billingType"),
        user_rate_limit_tier=o.get("userRateLimitTier"),
        organization_rate_limit_tier=o.get("organizationRateLimitTier"),
    )


@io_errors
def identity(inp: Inputs, name: str) -> Identity | None:
    """`oauthAccount` from the global config of the account `name` (account gate applies)."""
    return _identity_of(_global_config_data(Context(inp), name))


@io_errors
def identity_for(inp: Inputs, resolution: Resolution) -> Identity | None:
    """Like `identity` but for a `resolve()` result, reading its `global_config`.

    A status line should use this: for `CLAUDE_CONFIG_DIR=$HOME/.claude` Claude Code uses
    `~/.claude/.claude.json`, which the name `default` would not read.
    """
    return _identity_of(_global_config_data(Context(inp), resolution))


_MISSING = object()
_HOUR_MS = 3_600_000


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _usage_of(ctx: Context, config: Any) -> Usage | None:
    if not isinstance(config, dict) or not isinstance(config.get("cachedUsageUtilization"), dict):
        return None
    cached = config["cachedUsageUtilization"]
    ms = cached.get("fetchedAtMs")
    fetched = format_millis(ms) if _is_num(ms) else None
    windows: dict[str, dict[str, Any]] = {}
    util = cached.get("utilization")
    if isinstance(util, dict):
        for key, w in util.items():
            if isinstance(w, dict):
                u, r = w.get("utilization"), w.get("resets_at")
                windows[key] = {"utilization": u if _is_num(u) else None, "resetsAt": r if isinstance(r, str) else None}
    stale = not _is_num(ms)
    if not stale:
        age = ctx.now().timestamp() * 1000 - ms
        stale = age < 0 or age > _HOUR_MS
    if not stale:
        oauth = config.get("oauthAccount")
        mine = oauth.get("accountUuid", _MISSING) if isinstance(oauth, dict) else _MISSING
        stale = cached.get("accountUuid", _MISSING) != mine
    return Usage(fetched, cached, windows, stale)


@io_errors
def usage(inp: Inputs, name: str) -> Usage | None:
    """`cachedUsageUtilization` of the account `name` with `fetched_at`, `windows` and `stale`."""
    ctx = Context(inp)
    return _usage_of(ctx, _global_config_data(ctx, name))


@io_errors
def usage_for(inp: Inputs, resolution: Resolution) -> Usage | None:
    """Like `usage` but for a `resolve()` result, reading its `global_config`."""
    ctx = Context(inp)
    return _usage_of(ctx, _global_config_data(ctx, resolution))


@io_errors
def credentials(inp: Inputs, name: str) -> Credentials | None:
    """The stored OAuth token from `<config home>/.credentials.json`, read-only; None when absent.

    A link there counts as unreadable (Claude Code opens it with O_NOFOLLOW). An expired token is
    reported with `expired=True`. The refresh token is never returned: tools must not refresh
    (it rotates and a refresh outside Claude Code logs Claude Code out). Keychain items are not
    read.
    """
    ctx = Context(inp)
    ctx.gate(name)
    path = next((loc.file for loc in credential_locations(inp, name) if loc.file), None)
    if path is None:
        return None
    try:
        if ctx.fs.lstat(path).type in LINK_TYPES:
            return None
        raw = parse_json(ctx.fs.read_file(path, nofollow=True))
    except (FsError, ValueError):
        return None
    oauth = raw.get("claudeAiOauth") if isinstance(raw, dict) else None
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    expires = oauth.get("expiresAt")
    expires_ms = expires if isinstance(expires, (int, float)) and not isinstance(expires, bool) else None
    expires_at = format_millis(expires_ms) if expires_ms is not None else None
    expired = False
    if expires_ms is not None:
        expired = expires_ms <= ctx.now().timestamp() * 1000
    scopes = oauth.get("scopes")
    sub, tier = oauth.get("subscriptionType"), oauth.get("rateLimitTier")
    return Credentials(
        source="file",
        path=path,
        access_token=token,
        expires_at=expires_at,
        expired=expired,
        scopes=[s for s in scopes if isinstance(s, str)] if isinstance(scopes, list) else [],
        subscription_type=sub if isinstance(sub, str) else None,
        rate_limit_tier=tier if isinstance(tier, str) else None,
    )
