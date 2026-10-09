"""B1: launch environment delta and credential locations."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .context import Context
from .inputs import Inputs
from .ioerr import io_errors
from .models import CredentialLocation, EnvDelta, Keychain, LaunchEnv

_ACCOUNT_RE = re.compile(r"[a-zA-Z0-9._-]+")
_FALLBACK_USER = "claude-code-user"
_PLAIN_AUTH_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_USE_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
_AUTH_VARS = _PLAIN_AUTH_VARS + _USE_VARS + ("ANTHROPIC_PROFILE",)
_TRUTHY = ("1", "true", "yes", "on")


def _applies(key: str, value: object) -> bool:
    """Non-empty string, and for the `CLAUDE_CODE_USE_*` variables also truthy."""
    if not isinstance(value, str) or not value:
        return False
    return value.strip().lower() in _TRUTHY if key in _USE_VARS else True


def launch_env(ctx: Context, name: str, clear_auth_overrides: bool = False) -> LaunchEnv:
    """The env delta for `name` (sorted `unset`, no duplicates)."""
    set_: dict[str, str] = {"CLAUDE_MULTI_ACCOUNT": name}
    unset = {"CLAUDE_MULTI_ACCOUNT_SOURCE", "CLAUDE_SECURESTORAGE_CONFIG_DIR"}
    if name == "default":
        unset.add("CLAUDE_CONFIG_DIR")
    else:
        set_["CLAUDE_CONFIG_DIR"] = ctx.canonical(name)
    if clear_auth_overrides:
        unset.update(_AUTH_VARS)
    return LaunchEnv(set_, sorted(unset))


def overridden_by(ctx: Context, config_home: str | None, cleared: bool = False) -> list[str]:
    """Things that replace the login, in the fixed order of A4: auth variables (from `env` unless
    cleared, or from `settings.json` `env`), storage and OAuth overrides, then `apiKeyHelper`."""
    settings = ctx.read_json(ctx.P.join(config_home, "settings.json")) if config_home is not None else None
    settings_env: dict[str, Any] = {}
    if isinstance(settings, dict) and isinstance(settings.get("env"), dict):
        settings_env = settings["env"]
    out: list[str] = []
    for key in _AUTH_VARS:
        if (not cleared and _applies(key, ctx.env.get(key))) or _applies(key, settings_env.get(key)):
            out.append(key)
    if "CLAUDE_SECURESTORAGE_CONFIG_DIR" in ctx.env:
        out.append("CLAUDE_SECURESTORAGE_CONFIG_DIR")
    if ctx.env_set("CLAUDE_CODE_CUSTOM_OAUTH_URL"):
        out.append("CLAUDE_CODE_CUSTOM_OAUTH_URL")
    if isinstance(settings, dict):
        helper = settings.get("apiKeyHelper")
        if isinstance(helper, str) and helper:
            out.append("apiKeyHelper")
    return out


@io_errors
def env(inp: Inputs, name: str, clear_auth_overrides: bool = False) -> EnvDelta:
    """Delta to launch `name`: what to set, what to unset, and what still overrides the login."""
    ctx = Context(inp)
    ctx.check_name(name)
    delta = launch_env(ctx, name, clear_auth_overrides)
    return EnvDelta(delta.set, delta.unset, overridden_by(ctx, ctx.config_home(name), clear_auth_overrides))


def credential_manager_in_use(ctx: Context, global_config: str) -> bool:
    """Windows Credential Manager: forced by env, or cached in the global config."""
    if ctx.env.get("CLAUDE_CODE_FORCE_WINDOWS_CREDMAN") == "1":
        return True
    data = ctx.read_json(global_config)
    if isinstance(data, dict):
        features = data.get("cachedGrowthBookFeatures")
        if isinstance(features, dict) and features.get("tengu_windows_credman") is True:
            return True
    return False


@io_errors
def credential_locations(inp: Inputs, name: str) -> list[CredentialLocation]:
    """Ordered places Claude Code looks for the login of `name` on `inp.platform`."""
    ctx = Context(inp)
    ctx.check_name(name)
    home = ctx.config_home(name)
    file_loc = CredentialLocation(file=ctx.P.join(home, ".credentials.json"))
    if inp.platform == "darwin":
        service = "Claude Code" + ctx.oauth_suffix + "-credentials"
        if name != "default":
            service += "-" + hashlib.sha256(home.encode("utf-8")).hexdigest()[:8]
        user = ctx.env.get("USER") or inp.user_name or _FALLBACK_USER
        if not _ACCOUNT_RE.fullmatch(user):
            user = _FALLBACK_USER
        return [CredentialLocation(keychain=Keychain(service, user)), file_loc]
    if inp.platform == "win32" and credential_manager_in_use(ctx, ctx.global_config_path(name)):
        return [CredentialLocation(credential_manager={}), file_loc]
    return [file_loc]
