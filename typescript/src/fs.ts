/** Kinds of directory entry. `junction` is a Windows directory junction; the Fs decides what one is. */
export type FileType = "dir" | "file" | "symlink" | "junction" | "fifo" | "device";

/** Result of `lstat` and `stat`. `dev` and `ino` together identify an object (bigint on real disks). */
export interface FsStat {
  type: FileType;
  dev: number | bigint;
  ino: number | bigint;
  size: number;
  /** Permission bits, for example 0o700. */
  mode: number;
  mtimeMs: number;
}

/** Flags understood by `Fs.open`. */
export type OpenFlag = "RDONLY" | "NOFOLLOW" | "NONBLOCK" | "CREAT_EXCL_WRONLY";

/** An open file. */
export interface FsHandle {
  /** Reads at most `cap` bytes (fewer at end of file or on a FIFO with no data). */
  read(cap: number): Promise<Uint8Array>;
  write(data: Uint8Array): Promise<void>;
  sync(): Promise<void>;
  close(): Promise<void>;
}

/**
 * The filesystem seam. Every method rejects with an error whose `code` is a POSIX name
 * (ENOENT, ENOTDIR, EACCES, ELOOP, EEXIST, EINVAL, EISDIR, ENOTEMPTY), as Node's fs does.
 */
export interface Fs {
  /** Whether names compare case-insensitively on this filesystem (used for ceilings and mapping). */
  readonly caseInsensitive: boolean;
  /** Like `stat` but does not follow a link in the last component. */
  lstat(path: string): Promise<FsStat>;
  /** Follows links in every component. Never reports a link type. */
  stat(path: string): Promise<FsStat>;
  readlink(path: string): Promise<string>;
  /** Entry names in stored case, sorted bytewise ascending. */
  readdir(path: string): Promise<string[]>;
  realpath(path: string): Promise<string>;
  open(path: string, flags: readonly OpenFlag[], mode?: number): Promise<FsHandle>;
  mkdir(path: string, mode: number): Promise<void>;
  rename(from: string, to: string): Promise<void>;
  /** Creates a link. On Windows `dir` makes a junction. The target is stored verbatim. */
  symlink(target: string, path: string, kind: "file" | "dir"): Promise<void>;
  rmdir(path: string): Promise<void>;
  unlink(path: string): Promise<void>;
}

/** Error raised by the in-memory filesystem, shaped like a Node system error. */
export class FsError extends Error {
  readonly code: string;
  readonly path: string | undefined;
  constructor(code: string, path?: string) {
    super(path === undefined ? code : `${code}: ${path}`);
    this.name = "FsError";
    this.code = code;
    this.path = path;
  }
}

/** The `code` of a filesystem error, or undefined when `e` is not one. */
export function fsCode(e: unknown): string | undefined {
  if (typeof e === "object" && e !== null && "code" in e) {
    const code = (e as { code: unknown }).code;
    if (typeof code === "string") return code;
  }
  return undefined;
}

/** Stable identity key of two paths' `(dev, ino)`: equal keys mean the same object. */
export function identityKey(st: FsStat): string {
  return `${st.dev}:${st.ino}`;
}

/** True for symlink and junction. */
export function isLink(type: FileType): boolean {
  return type === "symlink" || type === "junction";
}
