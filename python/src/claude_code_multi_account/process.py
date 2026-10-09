"""Real process table, pid domain and OS probes (used only by `from_process`).

Formulas are Claude Code's, byte for byte (SPEC B3). The pure parsers take text so tests need no
real process.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Callable

from .fs import Fs, FsError
from .inputs import ProcessInfo


def parse_proc_stat_start(text: str) -> str | None:
    """Field 22 (`starttime`) of a `/proc/<pid>/stat` line, parsed after the last `)`."""
    close = text.rfind(")")
    if close < 0:
        return None
    rest = text[close + 1:].split()
    # rest[0] is field 3 (state), so field 22 is rest[19]
    return rest[19] if len(rest) > 19 else None


def linux_pid_domain(
    read_text: Callable[[str], str] | None = None, readlink: Callable[[str], str] | None = None
) -> str:
    """`linux:<trim(/etc/machine-id)>:<readlink(/proc/self/ns/pid)>`; an unreadable part is empty."""

    def _read(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    try:
        machine = (read_text or _read)("/etc/machine-id").strip()
    except OSError:
        machine = ""
    try:
        ns = (readlink or os.readlink)("/proc/self/ns/pid")
    except OSError:
        ns = ""
    return f"linux:{machine}:{ns}"


def os_pid_domain(platform: str) -> str:
    """The caller's `pidDomain` for this platform."""
    if platform == "win32":
        import socket

        return "linux:" + socket.gethostname().lower()
    if platform == "linux":
        return linux_pid_domain()
    return "linux"


class LookupFailed(Exception):
    """The process lookup itself failed (tool missing, timeout, unreadable): outcome unknown."""


def ps_start(pid: int) -> str | None:
    """`ps -o lstart= -p <pid>` with `LC_ALL=C` and `TZ=UTC`, trimmed; None if no such process.

    Raises `LookupFailed` when `ps` is missing, times out or fails in another way.
    """
    env = dict(os.environ, LC_ALL="C", TZ="UTC")
    try:
        out = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, env=env, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise LookupFailed(str(e)) from e
    text = out.stdout.strip()
    if out.returncode == 0 and text:
        return text
    if out.returncode == 1 and not text and not out.stderr.strip():
        return None  # ps found no such pid
    raise LookupFailed(f"ps exited {out.returncode}")


def windows_start_ft(pid: int) -> str | None:  # pragma: no cover - Windows only
    """Process creation time as a decimal FILETIME string; None if no such process.

    Raises `LookupFailed` for any other failure (for example access denied).
    """
    if sys.platform != "win32":
        raise LookupFailed("not Windows")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: no such pid
            return None
        raise LookupFailed(f"OpenProcess failed: {ctypes.get_last_error()}")
    try:
        created, exited, kern, user = (wintypes.FILETIME() for _ in range(4))
        ok = kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in (created, exited, kern, user)))
        if not ok:
            raise LookupFailed("GetProcessTimes failed")
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


class OsProcessTable:
    """The real process table: `/proc` on Linux, `ps` on other POSIX, `GetProcessTimes` on Windows."""

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self._domain = os_pid_domain(platform)

    def lookup(self, pid: int) -> ProcessInfo | None:
        if self.platform == "linux":
            try:
                with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
                    start = parse_proc_stat_start(fh.read())
            except (FileNotFoundError, ProcessLookupError):
                return None
            except OSError:
                return self._failed()
            return ProcessInfo(self._domain, proc_start=start) if start else self._failed()
        try:
            if self.platform == "win32":
                ft = windows_start_ft(pid)
                return ProcessInfo(self._domain, proc_start_ft=ft) if ft else None
            start = ps_start(pid)
            return ProcessInfo(self._domain, proc_start=start) if start else None
        except LookupFailed:
            return self._failed()

    def _failed(self) -> ProcessInfo:
        return ProcessInfo(self._domain, lookup_error=True)


def os_user_name() -> str | None:
    """The user name from the OS user database (passwd entry on POSIX, the account on Windows)."""
    if sys.platform == "win32":  # pragma: no cover - Windows only
        import ctypes

        size = ctypes.c_uint32(257)
        buf = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.advapi32.GetUserNameW(buf, ctypes.byref(size)):
            return buf.value
        return None
    try:
        import pwd

        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError):
        return None


def probe_symlinks(fs: Fs, home: str) -> bool:
    """True when a file symlink can be created (and removed) in `home`."""
    probe = os.path.join(home, f".claude-symlink-probe.tmp.{os.getpid()}.{secrets.token_hex(6)}")
    try:
        fs.symlink(os.path.join(home, ".claude-symlink-probe-target"), probe, "file")
    except FsError:
        return False
    try:
        fs.unlink(probe)
    except FsError:
        pass
    return True
