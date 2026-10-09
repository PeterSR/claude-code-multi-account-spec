"""Real filesystem adapter. This is the only module that talks to the operating system."""

from __future__ import annotations

import errno
import os
import stat as stat_mod
import sys
from collections.abc import Callable
from typing import TypeVar

from .fs import DEVICE, DIR, FIFO, FILE, JUNCTION, SYMLINK, FsError, Stat

_T = TypeVar("_T")


def _code(exc: OSError) -> str:
    if exc.errno is None:
        return "EIO"
    return errno.errorcode.get(exc.errno, "EIO")


def _call(path: str, fn: Callable[[], _T]) -> _T:
    try:
        return fn()
    except OSError as exc:
        raise FsError(_code(exc), path) from exc


_MOUNT_POINT_TAG = getattr(stat_mod, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def _kind(st: os.stat_result, follow: bool) -> str:
    mode = st.st_mode
    attrs = getattr(st, "st_file_attributes", 0)
    reparse = getattr(stat_mod, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not follow and attrs & reparse and getattr(st, "st_reparse_tag", 0) == _MOUNT_POINT_TAG:
        return JUNCTION  # only a mount point reparse tag is a junction (not OneDrive placeholders)
    if stat_mod.S_ISLNK(mode):
        return SYMLINK
    if stat_mod.S_ISDIR(mode):
        return DIR
    if stat_mod.S_ISREG(mode):
        return FILE
    if stat_mod.S_ISFIFO(mode):
        return FIFO
    return DEVICE


def _to_stat(st: os.stat_result, path: str, follow: bool) -> Stat:
    return Stat(_kind(st, follow), st.st_dev, st.st_ino, st.st_size, stat_mod.S_IMODE(st.st_mode), st.st_mtime)


class OsFs:
    """`Fs` implementation over the real filesystem."""

    def lstat(self, path: str) -> Stat:
        return _to_stat(_call(path, lambda: os.lstat(path)), path, False)

    def stat(self, path: str) -> Stat:
        return _to_stat(_call(path, lambda: os.stat(path)), path, True)

    def readlink(self, path: str) -> str:
        return _call(path, lambda: os.readlink(path))

    def readdir(self, path: str) -> list[str]:
        return sorted(_call(path, lambda: os.listdir(path)))

    def realpath(self, path: str) -> str:
        try:
            return os.path.realpath(path, strict=True)
        except RuntimeError as exc:  # symlink loop on older Pythons
            raise FsError("ELOOP", path) from exc
        except OSError as exc:
            raise FsError(_code(exc), path) from exc

    def read_file(self, path: str, cap: int | None = None, *, nofollow: bool = False) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        if nofollow:
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            elif stat_mod.S_ISLNK(_call(path, lambda: os.lstat(path)).st_mode):
                raise FsError("ELOOP", path)
        fd = _call(path, lambda: os.open(path, flags))
        try:
            chunks: list[bytes] = []
            left = cap
            while left is None or left > 0:
                want = 65536 if left is None else min(65536, left)
                chunk = _call(path, lambda: os.read(fd, want))
                if not chunk:
                    break
                chunks.append(chunk)
                if left is not None:
                    left -= len(chunk)
            return b"".join(chunks)
        except FsError as e:
            if e.code == "EAGAIN":  # empty non-blocking FIFO: no data
                return b"".join(chunks)
            raise
        finally:
            os.close(fd)

    def mkdir(self, path: str, mode: int) -> None:
        _call(path, lambda: os.mkdir(path, mode))
        _call(path, lambda: os.chmod(path, mode))

    def write_new(self, path: str, data: bytes, mode: int) -> None:
        fd = _call(path, lambda: os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), mode))
        try:
            view = memoryview(data)
            while view:
                n = _call(path, lambda: os.write(fd, view))
                view = view[n:]
            if hasattr(os, "fchmod"):
                os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)

    def rename(self, src: str, dst: str) -> None:
        _call(src, lambda: os.replace(src, dst))  # replace semantics on every OS (os.rename fails on Windows)

    def symlink(self, target: str, path: str, kind: str) -> None:
        if kind == "dir" and sys.platform == "win32":
            import _winapi

            _call(path, lambda: _winapi.CreateJunction(target, path))
            return
        _call(path, lambda: os.symlink(target, path, target_is_directory=(kind == "dir")))

    def rmdir(self, path: str) -> None:
        _call(path, lambda: os.rmdir(path))

    def unlink(self, path: str) -> None:
        _call(path, lambda: os.unlink(path))


__all__ = ["OsFs"]
