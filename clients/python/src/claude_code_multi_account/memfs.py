"""In-memory filesystem implementing the fake-FS semantics of conformance/FORMAT.md."""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from .fs import DEVICE, DIR, FIFO, FILE, JUNCTION, LINK_TYPES, SYMLINK, FsError, Stat
from .paths import PathOps, fold

_DEFAULT_MODES = {DIR: 0o755, FILE: 0o644, SYMLINK: 0o777, JUNCTION: 0o777}
_MAX_HOPS = 40


class _Node:
    __slots__ = ("type", "children", "content", "target", "dev", "ino", "mode", "mtime", "unreadable")

    def __init__(self, type_: str, dev: int, ino: int, mode: int, mtime: float) -> None:
        self.type = type_
        self.children: dict[str, _Node] = {}
        self.content = b""
        self.target = ""
        self.dev = dev
        self.ino = ino
        self.mode = mode
        self.mtime = mtime
        self.unreadable = False


class _Root:
    def __init__(self, name: str, node: _Node) -> None:
        self.name = name
        self.node = node


def _parse_time(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class MemoryFs:
    """A tree of nodes loaded from a flat `{path: entry}` map (see FORMAT.md section 3)."""

    def __init__(
        self,
        entries: Mapping[str, Mapping[str, Any]],
        *,
        platform: str,
        case_insensitive: bool,
        now: datetime,
        extra_roots: Iterable[str] = (),
    ) -> None:
        self.P = PathOps(platform)
        self.ci = case_insensitive
        self.now = now.timestamp()
        self._roots: dict[str, _Root] = {}
        self._auto = 1000
        self._by_inode: dict[tuple[int, int], _Node] = {}
        for p in list(extra_roots) + list(entries):
            root, _ = self.P.split(p)
            if root is not None:
                self._root(root)
        order = sorted(entries, key=lambda k: (len(self.P.split(k)[1]), k))
        for key in order:
            self._load(key, entries[key])

    # ----- loading

    def _rkey(self, root: str) -> str:
        return fold(root) if self.ci else root

    def _new_ino(self) -> int:
        self._auto += 1
        return self._auto - 1

    def _root(self, root: str) -> _Root:
        key = self._rkey(root)
        found = self._roots.get(key)
        if found is None:
            found = _Root(root, _Node(DIR, 1, self._new_ino(), 0o755, self.now))
            self._roots[key] = found
        return found

    def _find(self, parent: _Node, name: str) -> tuple[str, _Node] | None:
        if self.ci:
            f = fold(name)
            for k, v in parent.children.items():
                if fold(k) == f:
                    return k, v
            return None
        exact = parent.children.get(name)
        return (name, exact) if exact is not None else None

    def _ensure_dir(self, path: str) -> _Node:
        root, comps = self.P.split(path)
        assert root is not None
        cur = self._root(root).node
        for c in comps:
            hit = self._find(cur, c)
            if hit is None:
                created = _Node(DIR, 1, self._new_ino(), 0o755, self.now)
                cur.children[c] = created
                cur = created
            else:
                cur = hit[1]
        return cur

    def _load(self, key: str, e: Mapping[str, Any]) -> None:
        type_ = e["type"]
        parent_path = self.P.parent(key)
        assert parent_path is not None
        parent = self._ensure_dir(parent_path)
        name = self.P.split(key)[1][-1]
        dev = int(e.get("dev", 1))
        if "inode" in e:
            seen = self._by_inode.get((dev, int(e["inode"])))
            if seen is not None:
                parent.children[name] = seen
                return
        mode = int(e["mode"], 8) if "mode" in e else _DEFAULT_MODES.get(type_, 0o644)
        mtime = _parse_time(e["mtime"]) if "mtime" in e else self.now
        ino = int(e["inode"]) if "inode" in e else self._new_ino()
        node = _Node(type_, dev, ino, mode, mtime)
        node.unreadable = bool(e.get("unreadable", False))
        if "inode" in e:
            self._by_inode[(dev, ino)] = node
        if type_ == FILE:
            if "contentBase64" in e:
                node.content = base64.b64decode(e["contentBase64"])
            else:
                node.content = str(e.get("content", "")).encode("utf-8")
        if type_ in LINK_TYPES:
            node.target = e["target"]
        old = parent.children.get(name)
        if old is not None and old.type == DIR and type_ == DIR:
            node.children = old.children
        parent.children[name] = node

    # ----- lookup

    def _walk(self, path: str, follow_last: bool) -> list[tuple[str, _Node]]:
        root, comps = self.P.split(path)
        if root is None:
            raise FsError("ENOENT", path)
        found = self._roots.get(self._rkey(root))
        if found is None:
            raise FsError("ENOENT", path)
        stack: list[tuple[str, _Node]] = [(found.name, found.node)]
        queue = list(comps)
        hops = 0
        while queue:
            comp = queue.pop(0)
            if comp == ".":
                continue
            if comp == "..":
                if len(stack) > 1:
                    stack.pop()
                continue
            cur = stack[-1][1]
            if cur.type != DIR:
                raise FsError("ENOTDIR", path)
            if cur.unreadable:
                raise FsError("EACCES", path)
            hit = self._find(cur, comp)
            if hit is None:
                raise FsError("ENOENT", path)
            name, child = hit
            if child.type in LINK_TYPES and (queue or follow_last):
                hops += 1
                if hops > _MAX_HOPS:
                    raise FsError("ELOOP", path)
                if child.unreadable:
                    raise FsError("EACCES", path)
                troot, tcomps = self.P.split(child.target)
                if troot is not None:
                    other = self._roots.get(self._rkey(troot))
                    if other is None:
                        raise FsError("ENOENT", path)
                    stack = [(other.name, other.node)]
                queue = list(tcomps) + queue
                continue
            stack.append((name, child))
        return stack

    def _node(self, path: str, follow_last: bool = True) -> _Node:
        return self._walk(path, follow_last)[-1][1]

    def _parent_and_name(self, path: str) -> tuple[_Node, str]:
        norm = self.P.normalize(path)
        parent = self.P.parent(norm)
        if parent is None:
            raise FsError("EEXIST", path)
        pn = self._node(parent)
        if pn.type != DIR:
            raise FsError("ENOTDIR", path)
        return pn, self.P.split(norm)[1][-1]

    def _must_not_exist(self, path: str) -> None:
        try:
            self._node(path, False)
        except FsError as e:
            if e.code == "ENOENT":
                return
            raise
        raise FsError("EEXIST", path)

    @staticmethod
    def _stat(n: _Node) -> Stat:
        size = len(n.content) if n.type == FILE else 0
        return Stat(n.type, n.dev, n.ino, size, n.mode, n.mtime)

    # ----- Fs protocol

    def lstat(self, path: str) -> Stat:
        return self._stat(self._node(path, False))

    def stat(self, path: str) -> Stat:
        return self._stat(self._node(path, True))

    def readlink(self, path: str) -> str:
        n = self._node(path, False)
        if n.type not in LINK_TYPES:
            raise FsError("EINVAL", path)
        return n.target

    def readdir(self, path: str) -> list[str]:
        n = self._node(path, True)
        if n.type != DIR:
            raise FsError("ENOTDIR", path)
        if n.unreadable:
            raise FsError("EACCES", path)
        return sorted(n.children)

    def realpath(self, path: str) -> str:
        stack = self._walk(path, True)
        return stack[0][0] + self.P.sep.join(name for name, _ in stack[1:])

    def read_file(self, path: str, cap: int | None = None, *, nofollow: bool = False) -> bytes:
        n = self._node(path, not nofollow)
        if n.type in LINK_TYPES:
            raise FsError("ELOOP", path)
        if n.type == DIR:
            raise FsError("EISDIR", path)
        if n.unreadable:
            raise FsError("EACCES", path)
        if n.type in (FIFO, DEVICE):
            return b""
        return n.content if cap is None else n.content[:cap]

    def mkdir(self, path: str, mode: int) -> None:
        self._must_not_exist(path)
        pn, name = self._parent_and_name(path)
        pn.children[name] = _Node(DIR, 1, self._new_ino(), mode, self.now)

    def write_new(self, path: str, data: bytes, mode: int) -> None:
        self._must_not_exist(path)
        pn, name = self._parent_and_name(path)
        node = _Node(FILE, 1, self._new_ino(), mode, self.now)
        node.content = bytes(data)
        pn.children[name] = node

    def symlink(self, target: str, path: str, kind: str) -> None:
        self._must_not_exist(path)
        pn, name = self._parent_and_name(path)
        type_ = JUNCTION if (self.P.win and kind == "dir") else SYMLINK
        node = _Node(type_, 1, self._new_ino(), 0o777, self.now)
        node.target = target
        pn.children[name] = node

    def rename(self, src: str, dst: str) -> None:
        spn, sname = self._parent_and_name(src)
        hit = self._find(spn, sname)
        if hit is None:
            raise FsError("ENOENT", src)
        skey, node = hit
        dpn, dname = self._parent_and_name(dst)
        existing = self._find(dpn, dname)
        if existing is not None:
            dkey, other = existing
            if self.P.win and (node.type == JUNCTION or other.type == JUNCTION):
                raise FsError("EEXIST", dst)
            if (other.type == DIR) != (node.type == DIR):
                raise FsError("EEXIST", dst)
            if other.type == DIR and other.children:
                raise FsError("ENOTEMPTY", dst)
            del dpn.children[dkey]
        del spn.children[skey]
        dpn.children[dname] = node

    def rmdir(self, path: str) -> None:
        pn, name = self._parent_and_name(path)
        hit = self._find(pn, name)
        if hit is None:
            raise FsError("ENOENT", path)
        if hit[1].type not in (DIR, JUNCTION):
            raise FsError("ENOTDIR", path)
        if hit[1].children:
            raise FsError("ENOTEMPTY", path)
        del pn.children[hit[0]]

    def unlink(self, path: str) -> None:
        pn, name = self._parent_and_name(path)
        hit = self._find(pn, name)
        if hit is None:
            raise FsError("ENOENT", path)
        if hit[1].type in (DIR, JUNCTION):
            raise FsError("EISDIR", path)
        del pn.children[hit[0]]

    # ----- test and harness helpers

    def dump(self) -> dict[str, dict[str, Any]]:
        """Flat map of every path reachable through the tree (not through links)."""
        out: dict[str, dict[str, Any]] = {}

        def rec(path: str, n: _Node) -> None:
            e: dict[str, Any] = {"type": n.type, "mode": "%04o" % n.mode}
            if n.type == FILE:
                try:
                    e["content"] = n.content.decode("utf-8")
                except UnicodeDecodeError:
                    e["contentBase64"] = base64.b64encode(n.content).decode("ascii")
            if n.type in LINK_TYPES:
                e["target"] = n.target
            out[path] = e
            if n.type == DIR:
                for k in sorted(n.children):
                    rec(path + self.P.sep + k, n.children[k])

        for r in self._roots.values():
            for k in sorted(r.node.children):
                rec(r.name + k, r.node.children[k])
        return out
