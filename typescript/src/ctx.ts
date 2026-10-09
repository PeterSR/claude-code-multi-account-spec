import { randomBytes } from "node:crypto";
import { decodeUtf8 } from "./bytes.js";
import { MultiAccountError } from "./errors.js";
import { fsCode, identityKey, isLink } from "./fs.js";
import type { Fs } from "./fs.js";
import { pathOps } from "./paths.js";
import type { PathOps } from "./paths.js";
import { RESERVED_NAMES } from "./reserved-data.js";
import type { AccountState, Clock, Inputs } from "./types.js";

const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,31}$/;

/** Full match of the account (and pool) name grammar `[a-z0-9][a-z0-9_-]{0,31}`. */
export function isValidName(name: string): boolean {
  return NAME_RE.test(name);
}

/** Names that may not be created, from `spec/reserved.json` (embedded at build). */
export function reservedNames(): readonly string[] {
  return RESERVED_NAMES;
}

/** One account directory found by discovery, plus the facts every operation needs. */
export interface Entry {
  name: string;
  /** Canonical path (`$HOME/.claude` for default). */
  dir: string;
  state: AccountState;
  /** `(dev, ino)` of the config home when state is ok. */
  ident: string | null;
  aliasOf: string | null;
  /** Alias group in order (default first, then names). Null when not ok or identity unknown. */
  group: Entry[] | null;
  /** Alias representative: the first named member, `default` only when alone. Null without a group. */
  rep: Entry | null;
}

export interface Discovery {
  /** `default` first, then named accounts bytewise. */
  entries: Entry[];
  notADirectory: string[];
}

export type SpecState =
  | { status: "none" }
  | { status: "invalid"; path: string }
  | { status: "ok"; data: Record<string, unknown> };

/** Internal per-call context: the inputs plus memoised discovery. */
export class Ctx {
  readonly P: PathOps;
  readonly fs: Fs;
  private discovery: Promise<Discovery> | undefined;
  private readonly specs = new Map<Entry, Promise<SpecState>>();

  constructor(readonly inputs: Inputs) {
    this.P = pathOps(inputs.platform);
    this.fs = inputs.fs;
  }

  get home(): string {
    return this.inputs.home;
  }

  get reserved(): readonly string[] {
    return this.inputs.reserved ?? RESERVED_NAMES;
  }

  requireClock(): Clock {
    if (!this.inputs.clock) throw new Error("this operation needs inputs.clock");
    return this.inputs.clock;
  }

  /** `<pid>.<12 hex>` for temp file names. */
  tempId(): string {
    return this.inputs.tempId ? this.inputs.tempId() : `${process.pid}.${randomBytes(6).toString("hex")}`;
  }

  canonical(name: string): string {
    return this.P.join(this.home, `.claude-${name}`).normalize("NFC");
  }

  /** `$HOME/.claude` for default, else the canonical path. */
  configHome(name: string): string {
    return name === "default" ? this.P.join(this.home, ".claude").normalize("NFC") : this.canonical(name);
  }

  /** `-custom-oauth` when `CLAUDE_CODE_CUSTOM_OAUTH_URL` is set and non-empty, else empty. */
  oauthSuffix(): string {
    return this.inputs.env["CLAUDE_CODE_CUSTOM_OAUTH_URL"] ? "-custom-oauth" : "";
  }

  /** Whether `p` exists and is a regular file after following links. */
  async isRegular(p: string): Promise<boolean> {
    try {
      return (await this.fs.stat(p)).type === "file";
    } catch {
      return false;
    }
  }

  /** The whole file as bytes, through `open`. Throws filesystem errors. */
  async readBytes(p: string, flags: readonly "NOFOLLOW"[] = []): Promise<Uint8Array> {
    const h = await this.fs.open(p, ["RDONLY", "NONBLOCK", ...flags]);
    try {
      const chunks: Uint8Array[] = [];
      let total = 0;
      for (;;) {
        const c = await h.read(65536);
        if (c.length === 0) break;
        chunks.push(c);
        total += c.length;
      }
      const out = new Uint8Array(total);
      let off = 0;
      for (const c of chunks) {
        out.set(c, off);
        off += c.length;
      }
      return out;
    } finally {
      await h.close();
    }
  }

  /** Parsed JSON of a regular file, or undefined for "no data" (missing, not a file, unreadable, invalid). */
  async readJson(p: string): Promise<unknown> {
    try {
      if ((await this.fs.stat(p)).type !== "file") return undefined;
      return JSON.parse(decodeUtf8(await this.readBytes(p)));
    } catch {
      return undefined;
    }
  }

  /** Effective global config file of an account (A1): legacy `.config.json`, else `.claude<suffix>.json`. */
  async globalConfigPath(name: string): Promise<string> {
    const home = this.configHome(name);
    const legacy = this.P.join(home, ".config.json");
    if (await this.isRegular(legacy)) return legacy;
    const file = `.claude${this.oauthSuffix()}.json`;
    return this.P.join(name === "default" ? this.home : home, file);
  }

  /** Global config file when the config home is `home` (a CLAUDE_CONFIG_DIR value): legacy first, then the suffixed name. */
  async globalConfigForHome(home: string): Promise<string> {
    const legacy = this.P.join(home, ".config.json");
    if (await this.isRegular(legacy)) return legacy;
    return this.P.join(home, `.claude${this.oauthSuffix()}.json`);
  }

  /** Whether Credential Manager is in use on Windows: forced by env or cached in the global config at `configPath`. */
  async credentialManagerInUse(configPath: string): Promise<boolean> {
    if (this.inputs.env["CLAUDE_CODE_FORCE_WINDOWS_CREDMAN"] === "1") return true;
    const d = await this.readJson(configPath);
    if (isObject(d)) {
      const g = d["cachedGrowthBookFeatures"];
      if (isObject(g) && g["tengu_windows_credman"] === true) return true;
    }
    return false;
  }

  // ---- discovery

  accounts(): Promise<Discovery> {
    this.discovery ??= this.discover();
    return this.discovery;
  }

  private async discover(): Promise<Discovery> {
    const { P, fs } = this;
    const entries: Entry[] = [
      { name: "default", dir: this.configHome("default"), state: "ok", ident: null, aliasOf: null, group: null, rep: null },
    ];
    const notADirectory: string[] = [];
    let names: string[] = [];
    try {
      names = await fs.readdir(this.home);
    } catch {
      names = [];
    }
    for (const n of names) {
      if (!n.startsWith(".claude-")) continue;
      const name = n.slice(".claude-".length);
      if (!isValidName(name)) continue;
      const path = P.join(this.home, n);
      const dir = this.canonical(name);
      let linkish = false;
      try {
        linkish = isLink((await fs.lstat(path)).type);
      } catch {
        entries.push({ name, dir, state: "unreadable", ident: null, aliasOf: null, group: null, rep: null });
        continue;
      }
      try {
        const st = await fs.stat(path);
        if (st.type !== "dir") {
          notADirectory.push(path);
          continue;
        }
        entries.push({ name, dir, state: "ok", ident: null, aliasOf: null, group: null, rep: null });
      } catch (e) {
        if (linkish) {
          entries.push({ name, dir, state: fsCode(e) === "EACCES" ? "unreadable" : "dangling", ident: null, aliasOf: null, group: null, rep: null });
        }
      }
    }
    const groups = new Map<string, Entry[]>();
    for (const e of entries) {
      if (e.state !== "ok") continue;
      try {
        e.ident = identityKey(await fs.stat(e.dir));
      } catch {
        continue;
      }
      const g = groups.get(e.ident) ?? [];
      g.push(e);
      groups.set(e.ident, g);
    }
    for (const g of groups.values()) {
      const rep = g.find((m) => m.name !== "default") ?? (g[0] as Entry);
      for (const m of g) {
        m.group = g;
        m.rep = rep;
        if (m !== rep) m.aliasOf = rep.name;
      }
    }
    return { entries, notADirectory };
  }

  async entry(name: string): Promise<Entry | undefined> {
    return (await this.accounts()).entries.find((e) => e.name === name);
  }

  /** Accounts that count once: ok ones, with only the representative of each alias group. */
  async primaries(): Promise<Entry[]> {
    return (await this.accounts()).entries.filter((e) => e.state === "ok" && (e.rep === null || e.rep === e));
  }

  /** True for the same name, or two members of one alias group. */
  async sameAccount(a: string, b: string): Promise<boolean> {
    if (a === b) return true;
    const x = await this.entry(a);
    const y = await this.entry(b);
    return x !== undefined && y !== undefined && x.group !== null && x.group === y.group;
  }

  /**
   * Account gate (FORMAT.md section 4): grammar, then `default` is always present, else the account must
   * be discovered and usable.
   */
  async gate(name: string): Promise<Entry> {
    if (!isValidName(name)) throw new MultiAccountError("INVALID_NAME", `invalid account name: ${JSON.stringify(name)}`);
    return this.lookup(name, this.P.join(this.home, `.claude-${name}`));
  }

  /** Finds a (valid) account name, failing with ACCOUNT_NOT_FOUND at `notFoundPath` or ACCOUNT_UNAVAILABLE. */
  async lookup(name: string, notFoundPath: string): Promise<Entry> {
    const e = await this.entry(name);
    if (!e) throw new MultiAccountError("ACCOUNT_NOT_FOUND", `account not found: ${name}`, notFoundPath);
    if (e.state !== "ok") {
      throw new MultiAccountError("ACCOUNT_UNAVAILABLE", `account is ${e.state}: ${name}`, this.P.join(this.home, `.claude-${name}`));
    }
    return e;
  }

  // ---- spec file (A3)

  /** A valid claim is an absolute path or `~/...`; returns the normalised path, or null if invalid. */
  expandClaim(x: unknown): string | null {
    if (typeof x !== "string") return null;
    if (this.P.isAbsolute(x)) return this.P.normalize(x);
    if (x.startsWith("~/") || (this.inputs.platform === "win32" && x.startsWith("~\\"))) {
      return this.P.join(this.home, x.slice(2));
    }
    return null;
  }

  specFor(e: Entry): Promise<SpecState> {
    let s = this.specs.get(e);
    if (!s) {
      s = this.loadSpec(e);
      this.specs.set(e, s);
    }
    return s;
  }

  /** Reads and validates the spec file afresh (no cache). */
  async loadSpec(e: Entry): Promise<SpecState> {
    const p = this.P.join(e.dir, ".multi-account.json");
    try {
      await this.fs.lstat(p);
    } catch (err) {
      const c = fsCode(err);
      return c === "ENOENT" || c === "ENOTDIR" ? { status: "none" } : { status: "invalid", path: p };
    }
    let data: unknown;
    try {
      if ((await this.fs.stat(p)).type !== "file") return { status: "invalid", path: p };
      data = JSON.parse(decodeUtf8(await this.readBytes(p)));
    } catch {
      return { status: "invalid", path: p };
    }
    return this.validateSpec(data, p);
  }

  /** Applies the A3 validity rules to parsed spec file content. */
  validateSpec(data: unknown, p: string): SpecState {
    if (!isObject(data) || jsonDepth(data) > MAX_DEPTH || data["version"] !== 1) return { status: "invalid", path: p };
    if ("priority" in data) {
      const pr = data["priority"];
      if (typeof pr !== "number" || !Number.isInteger(pr) || Math.abs(pr) > Number.MAX_SAFE_INTEGER) {
        return { status: "invalid", path: p };
      }
    }
    if ("directories" in data) {
      const ds = data["directories"];
      if (!Array.isArray(ds) || ds.some((x) => this.expandClaim(x) === null)) return { status: "invalid", path: p };
    }
    return { status: "ok", data };
  }
}

/** Deepest nesting of arrays and objects (top-level object is level 1), iteratively. */
export function jsonDepth(x: unknown): number {
  let best = 0;
  const stack: [unknown, number][] = [[x, 1]];
  while (stack.length > 0) {
    const [v, d] = stack.pop() as [unknown, number];
    if (Array.isArray(v)) {
      best = Math.max(best, d);
      for (const c of v) stack.push([c, d + 1]);
    } else if (typeof v === "object" && v !== null) {
      best = Math.max(best, d);
      for (const c of Object.values(v)) stack.push([c, d + 1]);
    }
  }
  return best;
}

/** Maximum nesting of spec and state files. */
export const MAX_DEPTH = 100;

/**
 * Parses an RFC 3339 instant (upper-case T and Z, or a numeric offset, optional fraction) to microseconds
 * since the epoch, or null when it is not a valid one.
 */
export function parseRfc3339(s: unknown): number | null {
  if (typeof s !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})$/.exec(s);
  if (!m) return null;
  const [y, mo, d, h, mi, se] = [1, 2, 3, 4, 5, 6].map((i) => Number(m[i]));
  if ((se as number) > 59 || (h as number) > 23 || (mi as number) > 59) return null;
  const t = Date.UTC(y as number, (mo as number) - 1, d as number, h as number, mi as number, se as number);
  const check = new Date(t);
  if (check.getUTCFullYear() !== y || check.getUTCMonth() !== (mo as number) - 1 || check.getUTCDate() !== d) return null;
  const frac = m[7] ? Number((m[7].slice(1) + "000000").slice(0, 6)) : 0;
  let offMin = 0;
  const z = m[8] as string;
  if (z !== "Z") {
    const oh = Number(z.slice(1, 3));
    const om = Number(z.slice(4, 6));
    if (oh > 23 || om > 59) return null;
    offMin = (oh * 60 + om) * (z[0] === "-" ? -1 : 1);
  }
  return (t - offMin * 60_000) * 1000 + frac;
}

export function isObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}
