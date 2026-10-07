"""Platform-flavoured path helpers built on posixpath and ntpath (never os.path)."""

from __future__ import annotations

import ntpath
import posixpath
import re
from types import ModuleType

from .nfc import nfc as nfc

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_WIN_ROOT_RE = re.compile(r"([A-Za-z]):[\\/]")
_WIN_SPLIT_RE = re.compile(r"[\\/]+")
_FOLD_TABLE = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}


def is_valid_name(name: object) -> bool:
    """True when `name` fully matches the account (and pool) name grammar."""
    return isinstance(name, str) and _NAME_RE.fullmatch(name) is not None


def fold(text: str) -> str:
    """ASCII-only lower-casing, used for case-insensitive comparison."""
    return text.translate(_FOLD_TABLE)


class PathOps:
    """Path operations for one platform flavour (`linux`, `darwin` or `win32`)."""

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.win = platform == "win32"
        self.sep = "\\" if self.win else "/"
        self._m: ModuleType = ntpath if self.win else posixpath

    def split(self, path: str) -> tuple[str | None, list[str]]:
        """Split into (root or None for a relative path, components)."""
        if self.win:
            m = _WIN_ROOT_RE.match(path)
            if m:
                return m.group(1) + ":\\", [c for c in _WIN_SPLIT_RE.split(path[3:]) if c]
            return None, [c for c in _WIN_SPLIT_RE.split(path) if c]
        if path.startswith("/"):
            return "/", [c for c in path.split("/") if c]
        return None, [c for c in path.split("/") if c]

    def is_abs(self, path: str) -> bool:
        """Absolute in the platform's sense (win32: a drive letter and a separator)."""
        return self.split(path)[0] is not None

    def normalize(self, path: str) -> str:
        """Lexical normalisation, like Node's `path.normalize`."""
        if not self.win and path.startswith("//"):
            path = "/" + path.lstrip("/")
        return str(self._m.normpath(path))

    def join(self, *parts: str) -> str:
        """Join then normalise, like Node's `path.join`."""
        return self.normalize(self.sep.join(parts))

    def dirname(self, path: str) -> str:
        return str(self._m.dirname(self.normalize(path)))

    def basename(self, path: str) -> str:
        return str(self._m.basename(self.normalize(path)))

    def parent(self, path: str) -> str | None:
        """The parent directory, or None at a root."""
        norm = self.normalize(path)
        up = str(self._m.dirname(norm))
        return None if up == norm else up
