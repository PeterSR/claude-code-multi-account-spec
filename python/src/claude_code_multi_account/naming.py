"""Canonical paths (A2), a pure function of `home` and the name."""

from __future__ import annotations

from . import errors as E
from .errors import MultiAccountError
from .paths import PathOps, is_valid_name, nfc


def canonical_path(home: str, name: str, platform: str) -> str:
    """`nfc(join(home, ".claude-" + name))`; for `default` it is `join(home, ".claude")`.

    Pure: reserved names are allowed and the filesystem is never touched.
    """
    ops = PathOps(platform)
    if name == "default":
        return nfc(ops.join(home, ".claude"))
    if not is_valid_name(name):
        raise MultiAccountError(E.INVALID_NAME, f"invalid account name {name!r}")
    return nfc(ops.join(home, ".claude-" + name))
