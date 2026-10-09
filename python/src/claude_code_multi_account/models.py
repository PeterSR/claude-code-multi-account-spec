"""Result types. Field names are snake_case; JSON form is camelCase (see `jsonable`)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class SpecWarning:
    """A non-fatal finding `{code, message, path?}`; `message` defaults to the code."""

    _omit_none: ClassVar[bool] = True

    code: str
    path: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.message is None:
            object.__setattr__(self, "message", self.code)


@dataclass(frozen=True)
class SpecError:
    code: str
    path: str


@dataclass(frozen=True)
class Account:
    """One entry of `list_accounts`."""

    name: str
    config_dir: str
    state: str  # "ok" | "dangling" | "unreadable"
    has_spec_file: bool
    has_global_config: bool
    alias_of: str | None
    spec_error: SpecError | None
    warnings: list[SpecWarning] = field(default_factory=list)


@dataclass(frozen=True)
class Conflict:
    path: str
    accounts: list[str]


@dataclass(frozen=True)
class AccountList:
    accounts: list[Account]
    conflicts: list[Conflict]
    warnings: list[SpecWarning]


@dataclass(frozen=True)
class LaunchEnv:
    """Environment delta to launch an account: variables to set and to unset."""

    set: dict[str, str]
    unset: list[str]


@dataclass(frozen=True)
class EnvDelta:
    """`env()` result: a `LaunchEnv` plus what would still override the login."""

    set: dict[str, str]
    unset: list[str]
    overridden_by: list[str]


@dataclass(frozen=True)
class Resolution:
    """A4 result."""

    account: str | None
    pool: str | None
    config_dir: str | None
    canonical: bool
    reason: str | None
    source: str
    matched_path: str | None
    exists: bool
    alias_of: str | None
    candidates: list[str]
    applied: bool
    global_config: str | None
    launch_env: LaunchEnv | None
    overridden_by: list[str]
    ignored_markers: list[str]
    warnings: list[SpecWarning]


@dataclass(frozen=True)
class ConfigDirMapping:
    account: str | None
    canonical: bool
    reason: str | None
    warnings: list[SpecWarning]


@dataclass(frozen=True)
class Marker:
    kind: str  # "none" | "account" | "default" | "pool" | "list"
    name: str | None = None
    pool: str | None = None
    candidates: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Created:
    name: str
    config_dir: str


@dataclass(frozen=True)
class Keychain:
    service: str
    account: str


@dataclass(frozen=True)
class CredentialLocation:
    """One place Claude Code looks for the login: exactly one field is set."""

    _omit_none: ClassVar[bool] = True

    file: str | None = None
    keychain: Keychain | None = None
    credential_manager: dict[str, Any] | None = None


@dataclass(frozen=True)
class Identity:
    email: str | None
    org_name: str | None
    org_uuid: str | None
    organization_type: str | None
    billing_type: str | None
    user_rate_limit_tier: str | None
    organization_rate_limit_tier: str | None


@dataclass(frozen=True)
class Usage:
    fetched_at: str | None
    data: dict[str, Any]
    windows: dict[str, dict[str, Any]]
    stale: bool


@dataclass(frozen=True)
class Credentials:
    """Stored OAuth token from `.credentials.json`, read-only.

    There is deliberately no refresh token: tools must never refresh (it rotates and logs
    Claude Code out).
    """

    source: str
    path: str
    access_token: str = field(repr=False)
    expires_at: str | None
    expired: bool
    scopes: list[str]
    subscription_type: str | None
    rate_limit_tier: str | None


@dataclass(frozen=True)
class Claims:
    directories: list[str]


@dataclass(frozen=True)
class ProjectSession:
    id: str
    mtime: str


@dataclass(frozen=True)
class Session:
    pid: int
    session_id: str | None
    status: str  # "live" | "dead" | "unknown"


@dataclass(frozen=True)
class LimitEntry:
    """A B5 limit to record. `model` None covers all models; `until` is an RFC 3339 instant."""

    window: str
    model: str | None
    until: str
    reason: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True)
class Limits:
    """The written entries, verbatim (other tools' keys are preserved)."""

    limits: list[Any]


@dataclass(frozen=True)
class HandoverResult:
    """Relative paths from the config home, `/` separated, sorted bytewise."""

    copied: list[str]
    skipped: list[str]


@dataclass(frozen=True)
class SlotState:
    state: str  # "unmanaged" | "managed" | "broken" | "unsupported"
    name: str | None = None


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)


def jsonable(value: Any) -> Any:
    """Convert results to plain JSON values: dataclass fields become camelCase keys.

    Dict keys are data and are left alone. A dataclass with `_omit_none` drops None fields.
    """
    if is_dataclass(value) and not isinstance(value, type):
        omit = getattr(type(value), "_omit_none", False)
        out: dict[str, Any] = {}
        for f in fields(value):
            v = getattr(value, f.name)
            if omit and v is None:
                continue
            out[_camel(f.name)] = jsonable(v)
        return out
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value
