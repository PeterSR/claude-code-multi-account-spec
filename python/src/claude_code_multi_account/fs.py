"""The filesystem seam: a small protocol, its error type and the stat result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

FILE = "file"
DIR = "dir"
SYMLINK = "symlink"
JUNCTION = "junction"
FIFO = "fifo"
DEVICE = "device"

LINK_TYPES = (SYMLINK, JUNCTION)


class FsError(Exception):
    """A filesystem failure carrying an errno name such as `ENOENT` or `EACCES`."""

    def __init__(self, code: str, path: str | None = None) -> None:
        super().__init__(f"{code}: {path}" if path else code)
        self.code = code
        self.path = path


@dataclass(frozen=True)
class Stat:
    """Result of `lstat` or `stat`. `type` is one of the module constants above."""

    type: str
    dev: int
    ino: int
    size: int
    mode: int
    mtime: float

    @property
    def is_link(self) -> bool:
        return self.type in LINK_TYPES


@runtime_checkable
class Fs(Protocol):
    """Filesystem operations the library needs. All failures raise `FsError`."""

    def lstat(self, path: str) -> Stat:
        """Like `stat` but does not follow a link in the last component."""
        ...

    def stat(self, path: str) -> Stat:
        """Follow links everywhere; never reports a link type."""
        ...

    def readlink(self, path: str) -> str:
        """The stored target of a symlink or junction (EINVAL otherwise)."""
        ...

    def readdir(self, path: str) -> list[str]:
        """Entry names in stored case, sorted bytewise ascending."""
        ...

    def realpath(self, path: str) -> str:
        """Absolute path with every link followed."""
        ...

    def read_file(self, path: str, cap: int | None = None, *, nofollow: bool = False) -> bytes:
        """Open read-only and non-blocking, read at most `cap` bytes (all when None).

        With `nofollow`, a link in the last component fails with ELOOP.
        """
        ...

    def mkdir(self, path: str, mode: int) -> None: ...

    def write_new(self, path: str, data: bytes, mode: int) -> None:
        """Create with O_CREAT|O_EXCL, write, fsync (EEXIST if present)."""
        ...

    def rename(self, src: str, dst: str) -> None: ...

    def symlink(self, target: str, path: str, kind: str) -> None:
        """Create a link; `kind` is `file` or `dir` (a junction on win32 for `dir`)."""
        ...

    def rmdir(self, path: str) -> None: ...

    def unlink(self, path: str) -> None: ...
