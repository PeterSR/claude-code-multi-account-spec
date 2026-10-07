import { withFileLock, writeFileAtomic } from "./atomic.js";
import { decodeUtf8 } from "./bytes.js";
import { Ctx, isObject, jsonDepth, MAX_DEPTH, parseRfc3339 } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import { fsCode } from "./fs.js";
import type { Inputs } from "./types.js";

/** One availability limit (B5). `model` is null (or absent) for a window covering all models. */
export interface LimitEntry {
  window: string;
  model?: string | null;
  until: string;
  reason?: string;
  updatedBy?: string;
  updatedAt?: string;
}

/** The entry passed to `markLimited`; `updatedAt` is stamped from the clock. */
export type LimitInput = Omit<LimitEntry, "updatedAt">;

/** Result of the B5 writes: the limits as written. Entries written by other tools are carried verbatim. */
export interface LimitsResult {
  limits: unknown[];
}

type StateDoc = Record<string, unknown> & { limits: unknown[] };

const statePath = (ctx: Ctx, name: string): string => ctx.P.join(ctx.configHome(name), ".multi-account-state.json");

function stateUnderstood(d: unknown): d is Record<string, unknown> {
  return (
    isObject(d) &&
    d["version"] === 1 &&
    (!("limits" in d) || Array.isArray(d["limits"])) &&
    jsonDepth(d) <= MAX_DEPTH
  );
}

/** For reads: anything not understood is an empty state. */
async function readState(ctx: Ctx, name: string): Promise<unknown[]> {
  const d = await ctx.readJson(statePath(ctx, name));
  if (!stateUnderstood(d)) return [];
  return (d["limits"] as unknown[] | undefined) ?? [];
}

/** For writes: a missing file is empty, any other problem is STATE_FILE_INVALID and nothing is written. */
async function readStateForWrite(ctx: Ctx, name: string): Promise<StateDoc> {
  const path = statePath(ctx, name);
  const invalid = (): MultiAccountError => new MultiAccountError("STATE_FILE_INVALID", `state file not understood: ${path}`, path);
  let type: string;
  try {
    type = (await ctx.fs.stat(path)).type;
  } catch (e) {
    const c = fsCode(e);
    if (c === "ENOENT" || c === "ENOTDIR") return { version: 1, limits: [] };
    throw invalid();
  }
  if (type !== "file") throw invalid();
  let d: unknown;
  try {
    d = JSON.parse(decodeUtf8(await ctx.readBytes(path)));
  } catch {
    throw invalid();
  }
  if (!stateUnderstood(d)) throw invalid();
  return { ...d, limits: (d["limits"] as unknown[] | undefined) ?? [] };
}

function entryKey(x: unknown): string | null {
  if (!isObject(x) || typeof x["window"] !== "string") return null;
  const m = x["model"];
  return JSON.stringify([x["window"], m === undefined ? null : m]);
}

const untilOf = (x: unknown): number | null => (isObject(x) ? parseRfc3339(x["until"]) : null);

function dropPast(limits: unknown[], nowUs: number): unknown[] {
  return limits.filter((x) => {
    const u = untilOf(x);
    return u === null || u > nowUs;
  });
}

function validEntry(e: unknown): e is LimitInput {
  if (!isObject(e)) return false;
  if (typeof e["window"] !== "string" || e["window"] === "") return false;
  const m = e["model"];
  if (m !== undefined && m !== null && (typeof m !== "string" || m === "")) return false;
  if (parseRfc3339(e["until"]) === null) return false;
  for (const k of ["reason", "updatedBy"]) if (k in e && typeof e[k] !== "string") return false;
  return true;
}

const nowUs = (now: Date): number => now.getTime() * 1000;

/**
 * `markLimited(name, entry)`: merge under the lock, keeping the new entry when its `until` is equal or later,
 * dropping past entries (B5). Entries and keys written by other tools are preserved verbatim. Fails with
 * INVALID_ENTRY for a bad entry and STATE_FILE_INVALID for a state file it does not understand.
 */
export function markLimited(inputs: Inputs, name: string, entry: LimitInput): Promise<LimitsResult> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    if (!validEntry(entry)) throw new MultiAccountError("INVALID_ENTRY", "invalid limit entry");
    const now = ctx.requireClock().now();
    const e: Record<string, unknown> = {
      ...entry,
      model: entry.model ?? null,
      updatedAt: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
    };
    const path = statePath(ctx, name);
    return withFileLock(ctx, path, async () => {
      const st = await readStateForWrite(ctx, name);
      const limits = st.limits;
      const key = entryKey(e);
      const i = limits.findIndex((o) => entryKey(o) === key);
      if (i < 0) limits.push(e);
      else {
        const ou = untilOf(limits[i]);
        if (ou === null || (parseRfc3339(e["until"]) as number) >= ou) limits[i] = e;
      }
      st.limits = dropPast(limits, nowUs(now));
      st["version"] = 1;
      await writeFileAtomic(ctx, path, JSON.stringify(st));
      return { limits: st.limits };
    });
  });
}

/** `clearLimited(name, window, model)`: removes one entry and drops past ones; writes nothing if there is no state file. */
export function clearLimited(inputs: Inputs, name: string, window: string, model: string | null = null): Promise<LimitsResult> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    const path = statePath(ctx, name);
    try {
      await ctx.fs.lstat(path);
    } catch {
      return { limits: [] };
    }
    const now = ctx.requireClock().now();
    return withFileLock(ctx, path, async () => {
      const st = await readStateForWrite(ctx, name);
      const key = JSON.stringify([window, model]);
      st.limits = dropPast(
        st.limits.filter((x) => entryKey(x) !== key),
        nowUs(now),
      );
      st["version"] = 1;
      await writeFileAtomic(ctx, path, JSON.stringify(st));
      return { limits: st.limits };
    });
  });
}

/** Availability of an already gated account (internal). */
export async function isAvailable(ctx: Ctx, name: string, now: Date, model: string | null): Promise<boolean> {
  const limits = await readState(ctx, name);
  for (const x of limits) {
    if (!isObject(x)) continue;
    const m = x["model"];
    if (m === undefined || m === null || (model !== null && m === model)) {
      const u = untilOf(x);
      if (u !== null && u > nowUs(now)) return false;
    }
  }
  return true;
}

/** `available(name, now, {model})`: true when no entry applying to `model` has `until > now` (B5). */
export function available(
  inputs: Inputs,
  name: string,
  now: Date,
  opts: { model?: string | null } = {},
): Promise<boolean> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    return isAvailable(ctx, name, now, opts.model ?? null);
  });
}

/** An entry as `limits` reports it. */
export interface LimitView {
  window: string;
  model: string | null;
  until: string;
  reason: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
}

/**
 * `limits(name)`: the entries of the state file, in file order, past ones included (B5). Read only; a file
 * that is missing or not understood has none, and entries without a string `window` or a readable `until`
 * are left out.
 */
export function limits(inputs: Inputs, name: string): Promise<{ limits: LimitView[] }> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    const out: LimitView[] = [];
    const s = (x: unknown): string | null => (typeof x === "string" ? x : null);
    for (const x of await readState(ctx, name)) {
      if (!isObject(x) || typeof x["window"] !== "string" || untilOf(x) === null) continue;
      out.push({
        window: x["window"],
        model: s(x["model"]),
        until: x["until"] as string,
        reason: s(x["reason"]),
        updatedBy: s(x["updatedBy"]),
        updatedAt: s(x["updatedAt"]),
      });
    }
    return { limits: out };
  });
}

function formatInstant(us: number): string {
  const ms = Math.floor(us / 1000);
  const iso = new Date(ms).toISOString();
  return ms % 1000 === 0 ? iso.replace(/\.000Z$/, "Z") : iso;
}

/**
 * `availableAt(name, now, {model})`: null when the account is available now, else the latest `until` among the
 * entries that apply to `model`, as UTC (milliseconds only when non-zero) (B5).
 */
export function availableAt(
  inputs: Inputs,
  name: string,
  now: Date,
  opts: { model?: string | null } = {},
): Promise<string | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    const model = opts.model ?? null;
    let latest: number | null = null;
    for (const x of await readState(ctx, name)) {
      if (!isObject(x)) continue;
      const m = x["model"];
      if (!(m === undefined || m === null || (model !== null && m === model))) continue;
      const u = untilOf(x);
      if (u !== null && u > nowUs(now) && (latest === null || u > latest)) latest = u;
    }
    return latest === null ? null : formatInstant(latest);
  });
}
