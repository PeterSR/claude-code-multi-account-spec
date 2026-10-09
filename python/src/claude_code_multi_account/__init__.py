"""Python library for the claude-code-multi-account spec (Part A and building blocks B1 to B7)."""

from .create import create
from .discover import list_accounts
from .env import credential_locations, env
from .errors import MultiAccountError
from .fs import Fs, FsError, Stat
from .handover import handover_session
from .identity import credentials, identity, identity_for, usage, usage_for
from .projects import project_slug, sessions_for
from .specfile import claim, spec_file, unclaim, update_spec_file
from .inputs import (
    EmptyProcessTable,
    Inputs,
    ProcessInfo,
    ProcessTable,
    ResolveOptions,
    from_process,
)
from .limits import available, available_at, clear_limited, limits, mark_limited
from .mapping import map_config_dir
from .marker import parse_marker
from .memfs import MemoryFs
from .models import (
    Account,
    AccountList,
    ConfigDirMapping,
    Conflict,
    HandoverResult,
    Created,
    CredentialLocation,
    Credentials,
    EnvDelta,
    Identity,
    Keychain,
    LaunchEnv,
    LimitEntry,
    Limits,
    Marker,
    Resolution,
    Session,
    SlotState,
    SpecError,
    SpecWarning,
    Usage,
)
from .naming import canonical_path
from .osfs import OsFs
from .pools import next_from, next_in_pool, pick, pick_from, pool_members
from .reserved import reserved_names
from .resolve import resolve
from .sessions import live_sessions, session_of_pid
from .slot import activate, adopt, slot
from .timeutil import Clock, FixedClock, SystemClock

__all__ = [
    "available_at", "claim", "identity_for", "limits", "pool_members", "project_slug", "session_of_pid",
    "sessions_for", "spec_file", "unclaim", "update_spec_file", "usage_for",
    "HandoverResult", "LimitEntry", "Limits", "SlotState", "activate", "adopt", "available", "clear_limited",
    "handover_session", "mark_limited", "next_from", "next_in_pool", "pick", "pick_from", "slot",
    "Account", "AccountList", "Clock", "ConfigDirMapping", "Conflict", "Created", "CredentialLocation",
    "Credentials", "EmptyProcessTable", "EnvDelta", "FixedClock", "Fs", "FsError", "Identity", "Inputs",
    "Keychain", "LaunchEnv", "Marker", "MemoryFs", "MultiAccountError", "OsFs", "ProcessInfo",
    "ProcessTable", "Resolution", "ResolveOptions", "Session", "SpecError", "SpecWarning", "Stat",
    "SystemClock", "Usage", "canonical_path", "create", "credential_locations", "credentials", "env",
    "from_process", "identity", "list_accounts", "live_sessions", "map_config_dir", "parse_marker",
    "reserved_names", "resolve", "usage",
]
