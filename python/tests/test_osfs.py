"""The real OS adapter against a temporary directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from claude_code_multi_account import FsError, Inputs, OsFs, ResolveOptions, from_process, list_accounts, parse_marker, resolve

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")


@pytest.fixture()
def fs() -> OsFs:
    return OsFs()


def test_lstat_and_stat_on_symlink(tmp_path: Path, fs: OsFs) -> None:
    (tmp_path / "real").mkdir()
    os.symlink(tmp_path / "real", tmp_path / "link")
    os.symlink(tmp_path / "missing", tmp_path / "dangling")
    assert fs.lstat(str(tmp_path / "link")).type == "symlink"
    assert fs.stat(str(tmp_path / "link")).type == "dir"
    assert fs.lstat(str(tmp_path / "real")).ino == fs.stat(str(tmp_path / "link")).ino
    assert fs.readlink(str(tmp_path / "link")) == str(tmp_path / "real")
    with pytest.raises(FsError) as err:
        fs.stat(str(tmp_path / "dangling"))
    assert err.value.code == "ENOENT"
    with pytest.raises(FsError) as err2:
        fs.readlink(str(tmp_path / "real"))
    assert err2.value.code == "EINVAL"


def test_readdir_sorted_and_errors(tmp_path: Path, fs: OsFs) -> None:
    for n in ("b", "a", ".claude-x"):
        (tmp_path / n).write_text("")
    assert fs.readdir(str(tmp_path)) == [".claude-x", "a", "b"]
    with pytest.raises(FsError) as err:
        fs.readdir(str(tmp_path / "a"))
    assert err.value.code == "ENOTDIR"


def test_read_file_nofollow(tmp_path: Path, fs: OsFs) -> None:
    (tmp_path / "f").write_text("hello")
    os.symlink(tmp_path / "f", tmp_path / "l")
    assert fs.read_file(str(tmp_path / "l")) == b"hello"
    assert fs.read_file(str(tmp_path / "f"), 2, nofollow=True) == b"he"
    with pytest.raises(FsError) as err:
        fs.read_file(str(tmp_path / "l"), nofollow=True)
    assert err.value.code == "ELOOP"


def test_read_file_fifo_does_not_block(tmp_path: Path, fs: OsFs) -> None:
    os.mkfifo(tmp_path / "fifo")
    assert fs.read_file(str(tmp_path / "fifo"), 16) == b""


def test_write_new_exclusive_and_rename(tmp_path: Path, fs: OsFs) -> None:
    p = str(tmp_path / "x.tmp")
    fs.write_new(p, b"data", 0o600)
    assert (os.stat(p).st_mode & 0o777) == 0o600
    with pytest.raises(FsError) as err:
        fs.write_new(p, b"again", 0o600)
    assert err.value.code == "EEXIST"
    fs.rename(p, str(tmp_path / "x"))
    assert (tmp_path / "x").read_bytes() == b"data"


def test_realpath_follows_links_and_reports_loops(tmp_path: Path, fs: OsFs) -> None:
    (tmp_path / "d").mkdir()
    os.symlink(tmp_path / "d", tmp_path / "l")
    assert fs.realpath(str(tmp_path / "l")) == os.path.realpath(tmp_path / "d")
    os.symlink(tmp_path / "b", tmp_path / "a")
    os.symlink(tmp_path / "a", tmp_path / "b")
    with pytest.raises(FsError) as err:
        fs.realpath(str(tmp_path / "a"))
    assert err.value.code == "ELOOP"


def test_library_on_real_tree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude-work").mkdir(parents=True)
    (home / "proj").mkdir()
    (home / "proj" / ".claude-account").write_text("work\n")
    inp = Inputs(env={}, cwd=str(home / "proj"), home=str(home), platform="linux", fs=OsFs())
    res = resolve(inp, ResolveOptions(ceiling_dirs=[str(tmp_path)]))
    assert (res.account, res.source) == ("work", "marker-file")
    assert [a.name for a in list_accounts(inp).accounts] == ["default", "work"]
    assert parse_marker(OsFs(), str(home / "proj" / ".claude-account")).name == "work"


def test_from_process_uses_real_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    inp = from_process({"HOME": str(tmp_path)})
    assert inp.cwd == os.path.realpath(tmp_path)
    assert inp.home == str(tmp_path)
