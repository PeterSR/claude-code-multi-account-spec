import { constants } from "node:fs";
import * as fsp from "node:fs/promises";
import type { Stats, BigIntStats } from "node:fs";
import { byteCompare } from "./bytes.js";
import type { FileType, Fs, FsHandle, FsStat, OpenFlag } from "./fs.js";

export interface NodeFsOptions {
  /** Whether the underlying filesystem is case-insensitive (macOS and Windows defaults). Default false. */
  caseInsensitive?: boolean;
  /** Use a directory junction for `symlink(..., "dir")`. Default: true on Windows. */
  junctions?: boolean;
}

function typeOf(st: Stats | BigIntStats): FileType {
  if (st.isDirectory()) return "dir";
  if (st.isFile()) return "file";
  if (st.isSymbolicLink()) return "symlink";
  if (st.isFIFO()) return "fifo";
  return "device";
}

function convert(st: BigIntStats): FsStat {
  return {
    type: typeOf(st),
    dev: st.dev,
    ino: st.ino,
    size: Number(st.size),
    mode: Number(st.mode & 0o7777n),
    mtimeMs: Number(st.mtimeMs),
  };
}

function numericFlags(flags: readonly OpenFlag[]): number {
  let n = 0;
  for (const f of flags) {
    switch (f) {
      case "RDONLY":
        n |= constants.O_RDONLY;
        break;
      case "NOFOLLOW":
        n |= constants.O_NOFOLLOW ?? 0;
        break;
      case "NONBLOCK":
        n |= constants.O_NONBLOCK ?? 0;
        break;
      case "CREAT_EXCL_WRONLY":
        n |= constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY;
        break;
    }
  }
  return n;
}

class NodeHandle implements FsHandle {
  constructor(private readonly fh: fsp.FileHandle) {}

  async read(cap: number): Promise<Uint8Array> {
    const buf = Buffer.alloc(cap);
    let total = 0;
    while (total < cap) {
      const { bytesRead } = await this.fh.read(buf, total, cap - total, null);
      if (bytesRead === 0) break;
      total += bytesRead;
    }
    return buf.subarray(0, total);
  }

  async write(data: Uint8Array): Promise<void> {
    let off = 0;
    while (off < data.length) {
      const { bytesWritten } = await this.fh.write(data, off, data.length - off, null);
      off += bytesWritten;
    }
  }

  sync(): Promise<void> {
    return this.fh.sync();
  }

  close(): Promise<void> {
    return this.fh.close();
  }
}

/**
 * The real filesystem through node:fs/promises. Errors are Node's own system errors, whose `code`
 * matches what the library expects. On Windows `lstat` reports a junction as `symlink`.
 */
export class NodeFs implements Fs {
  readonly caseInsensitive: boolean;
  private readonly junctions: boolean;

  constructor(opts: NodeFsOptions = {}) {
    this.caseInsensitive = opts.caseInsensitive ?? false;
    this.junctions = opts.junctions ?? process.platform === "win32";
  }

  async lstat(path: string): Promise<FsStat> {
    return convert(await fsp.lstat(path, { bigint: true }));
  }

  async stat(path: string): Promise<FsStat> {
    return convert(await fsp.stat(path, { bigint: true }));
  }

  readlink(path: string): Promise<string> {
    return fsp.readlink(path);
  }

  async readdir(path: string): Promise<string[]> {
    return (await fsp.readdir(path)).sort(byteCompare);
  }

  realpath(path: string): Promise<string> {
    return fsp.realpath(path);
  }

  async open(path: string, flags: readonly OpenFlag[], mode = 0o666): Promise<FsHandle> {
    return new NodeHandle(await fsp.open(path, numericFlags(flags), mode));
  }

  mkdir(path: string, mode: number): Promise<void> {
    return fsp.mkdir(path, { mode }).then(() => undefined);
  }

  rename(from: string, to: string): Promise<void> {
    return fsp.rename(from, to);
  }

  symlink(target: string, path: string, kind: "file" | "dir"): Promise<void> {
    const type = kind === "file" ? "file" : this.junctions ? "junction" : "dir";
    return fsp.symlink(target, path, type);
  }

  rmdir(path: string): Promise<void> {
    return fsp.rmdir(path);
  }

  unlink(path: string): Promise<void> {
    return fsp.unlink(path);
  }
}
