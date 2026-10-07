import { byteCompare, decodeUtf8, encodeUtf8, fold } from "./bytes.js";
import { FsError, isLink } from "./fs.js";
import type { FileType, Fs, FsHandle, FsStat, OpenFlag } from "./fs.js";
import { pathOps } from "./paths.js";
import type { PathOps } from "./paths.js";
import type { Platform } from "./types.js";

/** One entry of the fake filesystem description (conformance/FORMAT.md section 3.1). */
export interface FakeEntry {
  type: FileType;
  content?: string;
  /** Base64 bytes, for content that is not valid UTF-8. Exclusive with `content`. */
  contentBase64?: string;
  /** Octal string such as "0700". */
  mode?: string;
  target?: string;
  inode?: number;
  dev?: number;
  unreadable?: boolean;
  /** RFC 3339 UTC. Defaults to the fake clock's now. */
  mtime?: string;
}

/** A dumped entry (section 3.6). */
export interface DumpEntry {
  type: FileType;
  mode: string;
  content?: string;
  /** Base64 bytes, for content that is not valid UTF-8. Exclusive with `content`. */
  contentBase64?: string;
  target?: string;
}

export interface FakeFsOptions {
  platform: Platform;
  caseInsensitive?: boolean;
  /** Time stamped on implicit and newly created nodes. */
  now: Date;
  /** Flat map from normalised absolute path to entry. */
  entries?: Readonly<Record<string, FakeEntry>>;
  /** Roots (for example the roots of home and cwd) that must exist even when empty. */
  roots?: readonly string[];
}

interface Node {
  type: FileType;
  children: Map<string, Node> | null;
  content: Uint8Array;
  target: string | null;
  dev: number;
  ino: number;
  mode: number;
  mtimeMs: number;
  unreadable: boolean;
}

interface Frame {
  name: string;
  node: Node;
}

const MAX_HOPS = 40;

/**
 * In-memory filesystem implementing the semantics of conformance/FORMAT.md section 3: links,
 * case-insensitive lookup, identity by `(dev, ino)`, and the unreadable flag.
 */
export class FakeFs implements Fs {
  readonly caseInsensitive: boolean;
  private readonly P: PathOps;
  private readonly win: boolean;
  private readonly roots = new Map<string, { name: string; node: Node }>();
  private readonly byIno = new Map<string, Node>();
  private readonly nowMs: number;
  private auto = 1000;

  constructor(opts: FakeFsOptions) {
    this.caseInsensitive = opts.caseInsensitive ?? false;
    this.P = pathOps(opts.platform);
    this.win = opts.platform === "win32";
    this.nowMs = opts.now.getTime();
    const entries = opts.entries ?? {};
    for (const extra of opts.roots ?? []) this.ensureRoot(extra);
    for (const key of Object.keys(entries)) this.ensureRoot(key);
    const depth = (k: string): number => this.P.split(k).parts.length;
    const keys = Object.keys(entries).sort((a, b) => depth(a) - depth(b) || byteCompare(a, b));
    for (const key of keys) this.load(key, entries[key] as FakeEntry);
  }

  // ---- construction helpers

  private rootKey(root: string): string {
    return this.caseInsensitive ? fold(root) : root;
  }

  private newNode(type: FileType, init: Partial<Node> = {}): Node {
    return {
      type,
      children: type === "dir" ? new Map() : null,
      content: new Uint8Array(0),
      target: null,
      dev: 1,
      ino: this.auto++,
      mode: type === "dir" ? 0o755 : type === "symlink" || type === "junction" ? 0o777 : 0o644,
      mtimeMs: this.nowMs,
      unreadable: false,
      ...init,
    };
  }

  private ensureRoot(path: string): { name: string; node: Node } {
    const { root } = this.P.split(path);
    if (root === null) throw new Error(`fake fs: path is not absolute: ${path}`);
    const k = this.rootKey(root);
    let r = this.roots.get(k);
    if (!r) {
      r = { name: root, node: this.newNode("dir") };
      this.roots.set(k, r);
    }
    return r;
  }

  private lookupChild(dir: Node, name: string): { name: string; node: Node } | null {
    const kids = dir.children;
    if (!kids) return null;
    if (this.caseInsensitive) {
      const f = fold(name);
      for (const [k, v] of kids) if (fold(k) === f) return { name: k, node: v };
      return null;
    }
    const v = kids.get(name);
    return v ? { name, node: v } : null;
  }

  private ensureDir(path: string): Node {
    const { parts } = this.P.split(path);
    let cur = this.ensureRoot(path).node;
    for (const c of parts) {
      let next = this.lookupChild(cur, c)?.node;
      if (!next) {
        next = this.newNode("dir");
        cur.children?.set(c, next);
      }
      if (next.type !== "dir") throw new Error(`fake fs: ancestor is not a directory: ${path}`);
      cur = next;
    }
    return cur;
  }

  private load(key: string, e: FakeEntry): void {
    const parentPath = this.P.parent(key);
    if (parentPath === null) throw new Error(`fake fs: cannot place a root: ${key}`);
    const parent = this.ensureDir(parentPath);
    const name = this.P.split(key).parts.at(-1) as string;
    const dev = e.dev ?? 1;
    if (e.inode !== undefined) {
      const shared = this.byIno.get(`${dev}:${e.inode}`);
      if (shared) {
        parent.children?.set(name, shared);
        return;
      }
    }
    const init: Partial<Node> = { dev, unreadable: e.unreadable === true };
    if (e.mode !== undefined) init.mode = parseInt(e.mode, 8);
    if (e.mtime !== undefined) init.mtimeMs = Date.parse(e.mtime);
    if (e.inode !== undefined) init.ino = e.inode;
    if (e.type === "file") {
      init.content = e.contentBase64 !== undefined ? new Uint8Array(Buffer.from(e.contentBase64, "base64")) : encodeUtf8(e.content ?? "");
    }
    if (isLink(e.type)) init.target = e.target ?? "";
    const node = this.newNode(e.type, init);
    if (e.inode !== undefined) this.byIno.set(`${dev}:${e.inode}`, node);
    const old = parent.children?.get(name);
    if (old && old.type === "dir" && node.type === "dir") node.children = old.children;
    parent.children?.set(name, node);
  }

  // ---- lookup

  private walk(path: string, followLast: boolean): Frame[] {
    const { root, parts } = this.P.split(path);
    if (root === null) throw new FsError("ENOENT", path);
    const r = this.roots.get(this.rootKey(root));
    if (!r) throw new FsError("ENOENT", path);
    let stack: Frame[] = [{ name: r.name, node: r.node }];
    const queue = [...parts];
    let hops = 0;
    while (queue.length > 0) {
      const c = queue.shift() as string;
      if (c === "" || c === ".") continue;
      if (c === "..") {
        if (stack.length > 1) stack.pop();
        continue;
      }
      const cur = (stack[stack.length - 1] as Frame).node;
      if (cur.type !== "dir") throw new FsError("ENOTDIR", path);
      if (cur.unreadable) throw new FsError("EACCES", path);
      const child = this.lookupChild(cur, c);
      if (!child) throw new FsError("ENOENT", path);
      const n = child.node;
      if (isLink(n.type) && (queue.length > 0 || followLast)) {
        hops++;
        if (hops > MAX_HOPS) throw new FsError("ELOOP", path);
        if (n.unreadable) throw new FsError("EACCES", path);
        const t = this.P.split(n.target ?? "");
        if (t.root !== null) {
          const r2 = this.roots.get(this.rootKey(t.root));
          if (!r2) throw new FsError("ENOENT", path);
          stack = [{ name: r2.name, node: r2.node }];
        }
        queue.unshift(...t.parts);
        continue;
      }
      stack.push({ name: child.name, node: n });
    }
    return stack;
  }

  private last(path: string, followLast: boolean): Node {
    const st = this.walk(path, followLast);
    return (st[st.length - 1] as Frame).node;
  }

  private parentOf(path: string): { dir: Node; name: string } {
    const p = this.P.normalize(path);
    const par = this.P.parent(p);
    if (par === null) throw new FsError("EINVAL", path);
    const dir = this.last(par, true);
    if (dir.type !== "dir") throw new FsError("ENOTDIR", path);
    return { dir, name: this.P.split(p).parts.at(-1) as string };
  }

  private exists(path: string): boolean {
    try {
      this.last(path, false);
      return true;
    } catch (e) {
      if (e instanceof FsError && e.code === "ENOENT") return false;
      throw e;
    }
  }

  private statOf(n: Node): FsStat {
    return {
      type: n.type,
      dev: n.dev,
      ino: n.ino,
      size: n.type === "file" ? n.content.length : 0,
      mode: n.mode,
      mtimeMs: n.mtimeMs,
    };
  }

  // ---- Fs

  async lstat(path: string): Promise<FsStat> {
    return this.statOf(this.last(path, false));
  }

  async stat(path: string): Promise<FsStat> {
    return this.statOf(this.last(path, true));
  }

  async readlink(path: string): Promise<string> {
    const n = this.last(path, false);
    if (!isLink(n.type)) throw new FsError("EINVAL", path);
    return n.target ?? "";
  }

  async readdir(path: string): Promise<string[]> {
    const n = this.last(path, true);
    if (n.type !== "dir") throw new FsError("ENOTDIR", path);
    if (n.unreadable) throw new FsError("EACCES", path);
    return [...(n.children?.keys() ?? [])].sort(byteCompare);
  }

  async realpath(path: string): Promise<string> {
    const st = this.walk(path, true);
    const first = st[0] as Frame;
    return first.name + st.slice(1).map((f) => f.name).join(this.P.sep);
  }

  async open(path: string, flags: readonly OpenFlag[], mode = 0o644): Promise<FsHandle> {
    if (flags.includes("CREAT_EXCL_WRONLY")) {
      if (this.exists(path)) throw new FsError("EEXIST", path);
      const { dir, name } = this.parentOf(path);
      const node = this.newNode("file", { mode, mtimeMs: this.nowMs });
      dir.children?.set(name, node);
      return {
        read: async () => new Uint8Array(0),
        write: async (data) => {
          const merged = new Uint8Array(node.content.length + data.length);
          merged.set(node.content);
          merged.set(data, node.content.length);
          node.content = merged;
        },
        sync: async () => {},
        close: async () => {},
      };
    }
    if (flags.includes("NOFOLLOW") && isLink(this.last(path, false).type)) throw new FsError("ELOOP", path);
    const n = this.last(path, true);
    if (n.type === "dir") throw new FsError("EISDIR", path);
    if (n.unreadable) throw new FsError("EACCES", path);
    let pos = 0;
    return {
      read: async (cap) => {
        if (n.type !== "file") return new Uint8Array(0);
        const chunk = n.content.slice(pos, pos + cap);
        pos += chunk.length;
        return chunk;
      },
      write: async () => {
        throw new FsError("EBADF", path);
      },
      sync: async () => {},
      close: async () => {},
    };
  }

  async mkdir(path: string, mode: number): Promise<void> {
    if (this.exists(path)) throw new FsError("EEXIST", path);
    const { dir, name } = this.parentOf(path);
    dir.children?.set(name, this.newNode("dir", { mode }));
  }

  async rename(from: string, to: string): Promise<void> {
    const a = this.parentOf(from);
    const found = this.lookupChild(a.dir, a.name);
    if (!found) throw new FsError("ENOENT", from);
    const b = this.parentOf(to);
    const existing = this.lookupChild(b.dir, b.name);
    if (existing) {
      if (this.win && (existing.node.type === "junction" || found.node.type === "junction")) throw new FsError("EEXIST", to);
      if ((existing.node.type === "dir") !== (found.node.type === "dir")) throw new FsError("EEXIST", to);
      if (existing.node.type === "dir" && (existing.node.children?.size ?? 0) > 0) throw new FsError("ENOTEMPTY", to);
      b.dir.children?.delete(existing.name);
    }
    a.dir.children?.delete(found.name);
    b.dir.children?.set(b.name, found.node);
  }

  async symlink(target: string, path: string, kind: "file" | "dir"): Promise<void> {
    if (this.exists(path)) throw new FsError("EEXIST", path);
    const { dir, name } = this.parentOf(path);
    const type: FileType = this.win && kind === "dir" ? "junction" : "symlink";
    dir.children?.set(name, this.newNode(type, { target, mode: 0o777 }));
  }

  async rmdir(path: string): Promise<void> {
    const { dir, name } = this.parentOf(path);
    const found = this.lookupChild(dir, name);
    if (!found) throw new FsError("ENOENT", path);
    if (found.node.type === "junction") {
      dir.children?.delete(found.name);
      return;
    }
    if (found.node.type !== "dir") throw new FsError("ENOTDIR", path);
    if ((found.node.children?.size ?? 0) > 0) throw new FsError("ENOTEMPTY", path);
    dir.children?.delete(found.name);
  }

  async unlink(path: string): Promise<void> {
    const { dir, name } = this.parentOf(path);
    const found = this.lookupChild(dir, name);
    if (!found) throw new FsError("ENOENT", path);
    if (found.node.type === "dir" || found.node.type === "junction") throw new FsError("EISDIR", path);
    dir.children?.delete(found.name);
  }

  /** Full dump: one key per path reachable through the tree (not through links), section 3.6. */
  dump(): Record<string, DumpEntry> {
    const out: Record<string, DumpEntry> = {};
    const sep = this.P.sep;
    const rec = (path: string, n: Node): void => {
      const e: DumpEntry = { type: n.type, mode: (n.mode & 0o7777).toString(8).padStart(4, "0") };
      if (n.type === "file") {
        try {
          e.content = decodeUtf8(n.content);
        } catch {
          e.contentBase64 = Buffer.from(n.content).toString("base64");
        }
      }
      if (isLink(n.type)) e.target = n.target ?? "";
      out[path] = e;
      if (n.children) for (const [k, v] of n.children) rec(path.endsWith(sep) ? path + k : path + sep + k, v);
    };
    for (const r of this.roots.values()) {
      if (r.node.children) for (const [k, v] of r.node.children) rec(r.name + k, v);
    }
    return out;
  }
}
