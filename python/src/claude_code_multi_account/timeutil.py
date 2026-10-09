"""RFC 3339 helpers (UTC)."""

from __future__ import annotations

import calendar
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class Clock(Protocol):
    """Clock seam: returns the current instant as an aware datetime."""

    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None:
        """Wait (used by lock retries); a fixed clock may do nothing."""
        ...


class FixedClock:
    """A clock that always returns the same instant."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def sleep(self, seconds: float) -> None:
        return None


class SystemClock:
    """The real clock. Used only by the process convenience wrapper."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def parse_time(text: str) -> datetime:
    """Parse an RFC 3339 instant (a trailing `Z` is accepted on every Python version)."""
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def format_time(dt: datetime) -> str:
    """`YYYY-MM-DDTHH:MM:SSZ`."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_millis(ms: float) -> str | None:
    """Epoch milliseconds as `YYYY-MM-DDTHH:MM:SS.mmmZ`, or None when out of range."""
    try:
        whole = int(ms // 1)
        dt = _EPOCH + timedelta(milliseconds=whole)
    except (OverflowError, ValueError):
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (whole % 1000)


_INSTANT_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(?:Z|([+-])(\d{2}):(\d{2}))", re.ASCII
)

# (whole seconds since the epoch, nanoseconds): compares exactly, unlike datetime.
Instant = tuple[int, int]


def parse_instant(text: object) -> Instant | None:
    """Strict RFC 3339 instant (upper-case T and Z, offset allowed, no leap second), else None."""
    if not isinstance(text, str):
        return None
    m = _INSTANT_RE.fullmatch(text)
    if not m:
        return None
    y, mo, d, hh, mi, ss = (int(m.group(i)) for i in range(1, 7))
    off_h = int(m.group(9)) if m.group(9) else 0
    off_m = int(m.group(10)) if m.group(10) else 0
    if hh > 23 or mi > 59 or ss > 59 or off_h > 23 or off_m > 59:
        return None
    try:
        datetime(y, mo, d)
    except ValueError:
        return None
    secs = calendar.timegm((y, mo, d, hh, mi, ss, 0, 0, 0))
    if m.group(8):
        offset = (off_h * 3600 + off_m * 60) * (1 if m.group(8) == "+" else -1)
        secs -= offset
    nanos = int((m.group(7) or "").ljust(9, "0") or 0)
    return secs, nanos


def instant_of(dt: datetime) -> Instant:
    """The `Instant` of an aware datetime."""
    return int(calendar.timegm(dt.astimezone(timezone.utc).timetuple())), dt.microsecond * 1000
