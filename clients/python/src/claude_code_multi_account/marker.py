"""Marker file parsing (A4)."""

from __future__ import annotations

from . import errors as E
from .errors import MultiAccountError
from .fs import DIR, FILE, Fs, FsError
from .ioerr import io_errors
from .models import Marker
from .paths import is_valid_name

MAX_MARKER_BYTES = 1024
_TRIM = " \t\r\x0b\x0c"
_NONE = Marker("none")


def _parse_list(line: str, path: str) -> Marker:
    parts = [p.strip(_TRIM) for p in line.split(",")]
    if any(not (is_valid_name(p) or p == "default") for p in parts) or len(set(parts)) != len(parts):
        raise MultiAccountError(E.MARKER_INVALID, f"invalid marker list {line!r}", path)
    return Marker("list", parts[0], candidates=parts)


@io_errors
def parse_marker(fs: Fs, path: str) -> Marker:
    """Parse the marker at `path`. Returns kind `none` when there is nothing to read; a comma list gives kind `list`.

    Raises `MARKER_INVALID` for a FIFO or device, an unreadable or oversized file, an empty
    file or an invalid first line. A directory or a dangling link is ignored.
    """
    try:
        fs.lstat(path)
        st = fs.stat(path)
    except FsError:
        return _NONE
    if st.type == DIR:
        return _NONE
    if st.type != FILE:
        raise MultiAccountError(E.MARKER_INVALID, "marker is not a regular file", path)
    try:
        data = fs.read_file(path, MAX_MARKER_BYTES + 1)
    except FsError as e:
        raise MultiAccountError(E.MARKER_INVALID, f"cannot read marker: {e.code}", path) from e
    if len(data) > MAX_MARKER_BYTES:
        raise MultiAccountError(E.MARKER_INVALID, "marker is longer than 1024 bytes", path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise MultiAccountError(E.MARKER_INVALID, "marker is not UTF-8", path) from e
    if text.startswith("﻿"):
        text = text[1:]
    for raw in text.split("\n"):
        line = raw.removesuffix("\r").strip(_TRIM)
        if not line or line.startswith("#"):
            continue
        if "," in line:
            return _parse_list(line, path)
        if line == "default":
            return Marker("default", "default", candidates=["default"])
        if line.startswith("@") and is_valid_name(line[1:]):
            return Marker("pool", pool=line[1:])
        if is_valid_name(line):
            return Marker("account", line, candidates=[line])
        raise MultiAccountError(E.MARKER_INVALID, f"invalid marker target {line!r}", path)
    raise MultiAccountError(E.MARKER_INVALID, "marker has no target", path)
