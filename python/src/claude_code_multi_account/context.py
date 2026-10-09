"""Shared per-call state: path flavour, account discovery, spec files and JSON reads."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import errors as E
from .errors import MultiAccountError
from .fs import DIR, FILE, Fs, FsError
from .inputs import Inputs
from .jsonio import MAX_DEPTH, depth, parse_json
from .models import SpecWarning
from .paths import PathOps, fold, is_valid_name, nfc
from .reserved import reserved_names

SPEC_FILE = ".multi-account.json"


@dataclass
class Entry:
    """A discovered account (internal)."""

    name: str
    dir: str
    state: str
    ident: tuple[int, int] | None = None
    alias_of: str | None = None
    group: list[Entry] = field(default_factory=list)
    representative: Entry | None = None

    @property
    def is_primary(self) -> bool:
        """The alias group's representative (or not in a group): the one that counts once."""
        return self.representative is None or self.representative is self


@dataclass(frozen=True)
class SpecFile:
    """Outcome of reading an account's spec file."""

    kind: str  # "none" | "invalid" | "ok"
    path: str
    data: dict[str, Any] | None = None


class Context:
    """Wraps `Inputs` for one operation; caches discovery and spec files."""

    def __init__(self, inp: Inputs) -> None:
        self.inp = inp
        self.fs: Fs = inp.fs
        self.P = PathOps(inp.platform)
        self.home = inp.home
        self.env = inp.env
        self.reserved: tuple[str, ...] = tuple(inp.reserved) if inp.reserved is not None else reserved_names()
        self.case_insensitive = inp.case_insensitive
        self._entries: list[Entry] | None = None
        self._top_warnings: list[SpecWarning] = []
        self._specs: dict[str, SpecFile] = {}

    # ----- names and paths

    def canonical(self, name: str) -> str:
        return nfc(self.P.join(self.home, ".claude-" + name))

    def config_home(self, name: str) -> str:
        return self.P.join(self.home, ".claude") if name == "default" else self.canonical(name)

    def entry_path(self, name: str) -> str:
        return self.P.join(self.home, ".claude-" + name)

    def check_name(self, name: str, allow_default: bool = True) -> None:
        if not is_valid_name(name) and not (allow_default and name == "default"):
            raise MultiAccountError(E.INVALID_NAME, f"invalid account name {name!r}")

    def env_set(self, key: str) -> bool:
        return bool(self.env.get(key))

    @property
    def oauth_suffix(self) -> str:
        return "-custom-oauth" if self.env_set("CLAUDE_CODE_CUSTOM_OAUTH_URL") else ""

    # ----- file reads

    def is_regular(self, path: str) -> bool:
        try:
            return self.fs.stat(path).type == FILE
        except FsError:
            return False

    def read_json(self, path: str) -> Any:
        """Parsed JSON, or None for a missing file, non-file, read error or parse failure."""
        try:
            if self.fs.stat(path).type != FILE:
                return None
            return parse_json(self.fs.read_file(path))
        except (FsError, ValueError):
            return None

    def global_config_in(self, config_home: str, default_home: str | None = None) -> str:
        """A1 for an explicit config home: legacy `.config.json`, else `.claude<suffix>.json`."""
        legacy = self.P.join(config_home, ".config.json")
        if self.is_regular(legacy):
            return legacy
        return self.P.join(default_home or config_home, ".claude" + self.oauth_suffix + ".json")

    def now(self) -> datetime:
        if self.inp.clock is None:
            raise ValueError("this operation needs Inputs.clock")
        return self.inp.clock.now()

    def global_config_path(self, name: str) -> str:
        """A1: legacy `.config.json` wins, else `.claude<suffix>.json` (in `home` for default)."""
        home = self.config_home(name)
        return self.global_config_in(home, self.home if name == "default" else home)

    # ----- discovery

    def entries(self) -> list[Entry]:
        """`default` first, then discovered named accounts by name."""
        if self._entries is not None:
            return self._entries
        out = [Entry("default", self.config_home("default"), "ok")]
        try:
            names = self.fs.readdir(self.home)
        except FsError:
            names = []
        for n in sorted(names):
            if not n.startswith(".claude-") or not is_valid_name(n[len(".claude-"):]):
                continue
            name = n[len(".claude-"):]
            path = self.P.join(self.home, n)
            state = self._classify(path)
            if state == "not-dir":
                self._top_warnings.append(SpecWarning(E.NOT_A_DIRECTORY, path))
            elif state is not None:
                out.append(Entry(name, self.canonical(name), state))
        groups: dict[tuple[int, int], list[Entry]] = {}
        for e in out:
            if e.state != "ok":
                continue
            try:
                st = self.fs.stat(e.dir)
            except FsError:
                continue
            e.ident = (st.dev, st.ino)
            groups.setdefault(e.ident, []).append(e)
        for g in groups.values():
            named = [m for m in g if m.name != "default"]
            rep = named[0] if named else g[0]
            for m in g:
                m.group = g
                m.representative = rep
                m.alias_of = None if m is rep else rep.name
        self._entries = out
        return out

    def _classify(self, path: str) -> str | None:
        try:
            lst = self.fs.lstat(path)
        except FsError:
            return "unreadable"
        if lst.type == DIR:
            return "ok"
        if lst.is_link:
            try:
                st = self.fs.stat(path)
            except FsError as e:
                return "unreadable" if e.code == "EACCES" else "dangling"
            return "ok" if st.type == DIR else "not-dir"
        return "not-dir"

    def top_warnings(self) -> list[SpecWarning]:
        self.entries()
        return list(self._top_warnings)

    def entry(self, name: str) -> Entry | None:
        for e in self.entries():
            if e.name == name:
                return e
        return None

    def gate(self, name: str, bind_path: str | None = None) -> Entry:
        """Account gate: grammar, then discovered, then available. `default` always passes."""
        self.check_name(name)
        entry = self.entry(name)
        path = self.entry_path(name)
        if name == "default":
            assert entry is not None
            return entry
        if entry is None:
            raise MultiAccountError(E.ACCOUNT_NOT_FOUND, f"no account {name!r}", bind_path or path)
        if entry.state != "ok":
            raise MultiAccountError(E.ACCOUNT_UNAVAILABLE, f"account {name!r} is {entry.state}", path)
        return entry

    def same_account(self, a: str, b: str) -> bool:
        """The same name, or both `ok` members of one alias group."""
        if a == b:
            return True
        ea, eb = self.entry(a), self.entry(b)
        return ea is not None and eb is not None and ea.state == "ok" and bool(ea.group) and ea.group is eb.group

    def primaries(self) -> list[Entry]:
        return [e for e in self.entries() if e.state == "ok" and e.is_primary]

    # ----- spec files

    def expand_claim(self, claim: object) -> str | None:
        """Absolute path or `~/` relative to home; None when invalid."""
        if not isinstance(claim, str):
            return None
        if self.P.is_abs(claim):
            return self.P.normalize(claim)
        if claim.startswith("~/") or (self.P.win and claim.startswith("~\\")):
            return self.P.join(self.home, claim[2:])
        return None

    def spec_file(self, entry: Entry) -> SpecFile:
        cached = self._specs.get(entry.name)
        if cached is None:
            cached = self._read_spec(entry)
            self._specs[entry.name] = cached
        return cached

    def read_spec_fresh(self, entry: Entry) -> SpecFile:
        """Read the spec file again, bypassing the cache (used under a lock)."""
        return self._read_spec(entry)

    def valid_spec_data(self, data: Any) -> bool:
        """The A3 validity rules for an already parsed spec object."""
        if not isinstance(data, dict) or depth(data) > MAX_DEPTH:
            return False
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, (int, float)) or version != 1:
            return False
        if "directories" in data:
            dirs = data["directories"]
            if not isinstance(dirs, list) or any(self.expand_claim(d) is None for d in dirs):
                return False
        return "priority" not in data or _valid_priority(data["priority"])

    def _read_spec(self, entry: Entry) -> SpecFile:
        path = self.P.join(entry.dir, SPEC_FILE)
        try:
            self.fs.lstat(path)
        except FsError as e:
            if e.code in ("ENOENT", "ENOTDIR"):
                return SpecFile("none", path)
            return SpecFile("invalid", path)
        try:
            if self.fs.stat(path).type != FILE:
                return SpecFile("invalid", path)
            data = parse_json(self.fs.read_file(path), MAX_DEPTH)
        except (FsError, ValueError):
            return SpecFile("invalid", path)
        if not self.valid_spec_data(data):
            return SpecFile("invalid", path)
        return SpecFile("ok", path, data)

    def claims(self, entry: Entry) -> list[str]:
        """Expanded claim paths of an account with a valid spec file."""
        sf = self.spec_file(entry)
        if sf.kind != "ok" or sf.data is None:
            return []
        out: list[str] = []
        for d in sf.data.get("directories", []):
            expanded = self.expand_claim(d)
            if expanded is not None:
                out.append(expanded)
        return out

    def fold_eq(self, a: str, b: str) -> bool:
        return fold(a) == fold(b) if self.case_insensitive else a == b


_MAX_SAFE = 2**53 - 1


def _valid_priority(value: object) -> bool:
    """A number with an integer value in the signed 53-bit range."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return -_MAX_SAFE <= value <= _MAX_SAFE
    if isinstance(value, float):
        return math.isfinite(value) and value == int(value) and -_MAX_SAFE <= value <= _MAX_SAFE
    return False
