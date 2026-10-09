"""Fake filesystem semantics and packaged data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_code_multi_account import FsError, MemoryFs, canonical_path, reserved_names


def _fs(entries: dict[str, dict[str, object]], ci: bool = False) -> MemoryFs:
    return MemoryFs(entries, platform="linux", case_insensitive=ci, now=datetime(2026, 10, 6, tzinfo=timezone.utc))


def test_links_and_hops() -> None:
    fs = _fs({"/h/real": {"type": "dir"}, "/h/l": {"type": "symlink", "target": "real"}})
    assert fs.lstat("/h/l").type == "symlink"
    assert fs.stat("/h/l").type == "dir"
    assert fs.realpath("/h/l") == "/h/real"


def test_loop_is_eloop() -> None:
    fs = _fs({"/a": {"type": "symlink", "target": "/b"}, "/b": {"type": "symlink", "target": "/a"}})
    with pytest.raises(FsError) as err:
        fs.stat("/a")
    assert err.value.code == "ELOOP"


def test_case_insensitive_keeps_stored_case() -> None:
    fs = _fs({"/h/.claude-Work": {"type": "dir"}}, ci=True)
    assert fs.readdir("/h") == [".claude-Work"]
    assert fs.realpath("/h/.CLAUDE-work") == "/h/.claude-Work"


def test_shared_inode_is_one_directory() -> None:
    fs = _fs({"/a": {"type": "dir", "inode": 5}, "/b": {"type": "dir", "inode": 5}, "/a/x": {"type": "file"}})
    assert fs.readdir("/b") == ["x"]


def test_rename_over_file_and_dump() -> None:
    fs = _fs({"/d/a": {"type": "file", "content": "1"}, "/d/b": {"type": "file", "content": "2"}})
    fs.rename("/d/a", "/d/b")
    assert fs.dump()["/d/b"]["content"] == "1"
    assert "/d/a" not in fs.dump()


def test_packaged_reserved_matches_spec() -> None:
    spec = Path(__file__).resolve().parents[2] / "spec" / "reserved.json"
    if not spec.exists():
        pytest.skip("not inside the spec repo")
    assert reserved_names() == tuple(n["name"] for n in json.loads(spec.read_text())["names"])


def test_canonical_path_win32() -> None:
    assert canonical_path("C:/Users//p/", "work", "win32") == "C:\\Users\\p\\.claude-work"


def test_bundled_nfc_matches_go_tables_and_known_cases() -> None:
    import re

    from claude_code_multi_account.nfc import nfc
    from claude_code_multi_account.nfc_tables import CCC, COMP, DECOMP

    assert nfc("josé") == "josé"
    assert nfc("ạ̇") == nfc("ạ̇") == "ạ̇"
    assert nfc("각") == "각"
    assert nfc("Å") == "Å"
    assert nfc("\U00010d69") == "\U00010d69"
    go = Path(__file__).resolve().parents[2] / "go" / "nfc_tables.go"
    if not go.exists():
        pytest.skip("Go tables not found")
    text = go.read_text()

    def block(name: str) -> str:
        return text.split(f"var {name} ")[1].split("\n}\n")[0]

    go_ccc = {int(a, 16): int(b) for a, b in re.findall(r"0x([0-9A-F]+):\s+(\d+),", block("nfcCCC"))}
    go_comp = {(int(a, 16), int(b, 16)): int(c, 16) for a, b, c in re.findall(r"\{0x([0-9A-F]+), 0x([0-9A-F]+)\}:\s+0x([0-9A-F]+)", block("nfcComp"))}
    go_decomp = {int(a, 16): tuple(int(x, 16) for x in b.split(", ")) for a, b in re.findall(r"0x([0-9A-F]+):\s+\{([^}]*)\}", block("nfcDecomp"))}
    assert go_ccc == CCC and go_comp == COMP and go_decomp == DECOMP
