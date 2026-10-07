"""Explicit inputs to every operation, and the one wrapper that fills them from the process."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .fs import Fs
from .timeutil import Clock


@dataclass(frozen=True)
class ProcessInfo:
    """One entry of the process table.

    `proc_start` is Claude Code's `procStart` string (Linux and other POSIX), `proc_start_ft` its
    Windows `procStartFt`. `pid_domain` is the domain the pid belongs to. `lookup_error` marks a lookup
    that failed (error or timeout): the process may or may not exist, so the session is `unknown`.
    """

    pid_domain: str
    proc_start: str | None = None
    proc_start_ft: str | None = None
    lookup_error: bool = False


class ProcessTable(Protocol):
    """Process table seam (B3): look up a pid, or None when no such process exists."""

    def lookup(self, pid: int) -> ProcessInfo | None: ...


class EmptyProcessTable:
    """A process table with no processes."""

    def lookup(self, pid: int) -> ProcessInfo | None:
        return None


@dataclass(frozen=True)
class ResolveOptions:
    """A4 options."""

    trust_repo_markers: bool = False
    ignore_hook_env: bool = False
    ceiling_dirs: Sequence[str] = ()


@dataclass(frozen=True)
class Inputs:
    """Everything an operation may look at. Nothing is read from process globals.

    `platform` is `linux`, `darwin` or `win32`. `clock` is needed by write operations,
    `processes` by B3. `case_insensitive` says whether the filesystem folds case.
    `user_name` (B1) and `can_create_symlinks` (B7) stand for the OS user database and a symlink
    probe, which `from_process` fills. `lock_wait` bounds, in seconds, how long a write waits for
    a held lock before giving up with `LOCK_BUSY` (0 means fail at once).
    """

    env: Mapping[str, str]
    cwd: str
    home: str
    platform: str
    fs: Fs
    clock: Clock | None = None
    processes: ProcessTable = field(default_factory=EmptyProcessTable)
    caller_pid_domain: str = "host-1"
    reserved: Sequence[str] | None = None
    user_name: str | None = None
    can_create_symlinks: bool = True
    case_insensitive: bool = False
    lock_wait: float = 0.0


def platform_name() -> str:
    """`linux`, `darwin` or `win32` for the running interpreter."""
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def from_process(env: Mapping[str, str] | None = None) -> Inputs:
    """Build `Inputs` from the running process: environment, physical cwd, home, real FS and clock.

    The working directory is `realpath(".")`, never `$PWD`. The process table and the caller's
    pid domain follow Claude Code's formulas (SPEC B3), `can_create_symlinks` is found by creating
    and removing a file symlink in `$HOME`, and `user_name` comes from the OS user database.
    """
    from .osfs import OsFs
    from .process import (
        OsProcessTable,
        os_pid_domain,
        os_user_name,
        probe_symlinks,
    )
    from .timeutil import SystemClock

    environ = dict(os.environ if env is None else env)
    platform = platform_name()
    home = environ.get("USERPROFILE") if platform == "win32" else environ.get("HOME")
    if not home:
        home = os.path.expanduser("~")
    fs = OsFs()
    return Inputs(
        env=environ,
        cwd=os.path.realpath("."),
        home=home,
        platform=platform,
        fs=fs,
        clock=SystemClock(),
        processes=OsProcessTable(platform),
        caller_pid_domain=os_pid_domain(platform),
        user_name=os_user_name(),
        can_create_symlinks=probe_symlinks(fs, home),
        case_insensitive=platform in ("win32", "darwin"),
        lock_wait=2.0,
    )
