"""File safety rules (A3): lock directory, one-hop symlink write, temp file plus rename."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

from . import errors as E
from .errors import MultiAccountError
from .fs import Fs, FsError
from .paths import PathOps
from .timeutil import Clock

STALE_LOCK_SECONDS = 10
RETRY_STEP = 0.05


def _busy(lock: str) -> MultiAccountError:
    return MultiAccountError(E.LOCK_BUSY, f"locked: {lock}", lock)


def _try_take(fs: Fs, lock: str, clock: Clock) -> bool:
    """One acquisition attempt, with stale takeover. False when held by someone else."""
    try:
        fs.mkdir(lock, 0o700)
        return True
    except FsError as e:
        if e.code != "EEXIST":
            raise
    try:
        age = clock.now().timestamp() - fs.lstat(lock).mtime
    except FsError as e:
        if e.code == "ENOENT":  # released between our two calls
            return False
        raise
    if age <= STALE_LOCK_SECONDS:
        return False
    try:
        fs.rmdir(lock)
        fs.mkdir(lock, 0o700)
    except FsError as e:
        if e.code in ("EEXIST", "ENOENT", "ENOTEMPTY"):  # lost the takeover race
            raise _busy(lock) from e
        raise
    return True


@contextmanager
def lock_dir(fs: Fs, lock: str, clock: Clock, wait: float = 0.0) -> Iterator[None]:
    """Hold `mkdir <lock>` (proper-lockfile layout). A lock older than 10 s is stale.

    While the lock is held by someone else, retry for at most `wait` seconds (counted in
    `RETRY_STEP` sleeps through the clock seam), then fail with `LOCK_BUSY`.
    """
    waited = 0.0
    while not _try_take(fs, lock, clock):
        if waited >= wait:
            raise MultiAccountError(E.LOCK_BUSY, f"locked: {lock}", lock)
        clock.sleep(RETRY_STEP)
        waited += RETRY_STEP
    try:
        yield
    finally:
        try:
            fs.rmdir(lock)
        except FsError:
            pass


def write_file_atomic(fs: Fs, ops: PathOps, path: str, data: bytes) -> None:
    """Write `data` to `path` (following one link hop) via a 0600 temp file and rename."""
    target = path
    try:
        if fs.lstat(path).is_link:
            link = fs.readlink(path)
            target = link if ops.is_abs(link) else ops.join(ops.dirname(path), link)
    except FsError as e:
        if e.code not in ("ENOENT", "ENOTDIR"):
            raise
    tmp = f"{target}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    fs.write_new(tmp, data, 0o600)
    try:
        fs.rename(tmp, target)
    except FsError:
        try:
            fs.unlink(tmp)
        except FsError:
            pass
        raise
