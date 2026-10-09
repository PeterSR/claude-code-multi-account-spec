import { byteCompare } from "./bytes.js";
import { Ctx, isValidName } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import { isAvailable } from "./state.js";
import type { Inputs } from "./types.js";

async function members(ctx: Ctx, pool: string): Promise<string[]> {
  if (!isValidName(pool)) throw new MultiAccountError("INVALID_NAME", `invalid pool name: ${JSON.stringify(pool)}`);
  const d = await ctx.accounts();
  for (const e of d.entries) {
    if (e.state !== "ok") continue;
    const s = await ctx.specFor(e);
    if (s.status === "invalid") throw new MultiAccountError("SPEC_FILE_INVALID", `invalid spec file: ${s.path}`, s.path);
  }
  const out: { prio: number; name: string }[] = [];
  for (const e of await ctx.primaries()) {
    const s = await ctx.specFor(e);
    if (s.status === "ok" && s.data["pool"] === pool) {
      const p = s.data["priority"];
      out.push({ prio: typeof p === "number" ? p : 0, name: e.name });
    }
  }
  return out.sort((a, b) => b.prio - a.prio || byteCompare(a.name, b.name)).map((m) => m.name);
}

async function firstAvailable(ctx: Ctx, names: readonly string[], now: Date, model: string | null): Promise<string | null> {
  for (const n of names) if (await isAvailable(ctx, n, now, model)) return n;
  return null;
}

/** Candidates after `current` in list order (first occurrence), then those up to and including it; all if absent. */
function afterCurrent(list: readonly string[], current: string): readonly string[] {
  const i = list.indexOf(current);
  return i < 0 ? list : [...list.slice(i + 1), ...list.slice(0, i + 1)];
}

/** `poolMembers(pool)`: the members of a pool in pick order, without availability (B6). */
export function poolMembers(inputs: Inputs, pool: string): Promise<string[]> {
  return guarded(async () => members(new Ctx(inputs), pool));
}

/** `pick(pool, now, {model})`: the available member with the highest priority, ties by name; null if none (B6). */
export function pick(inputs: Inputs, pool: string, now: Date, opts: { model?: string | null } = {}): Promise<string | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    return firstAvailable(ctx, await members(ctx, pool), now, opts.model ?? null);
  });
}

/** `next(pool, current, now, {model})`: the next available member after `current`, wrapping; null if none (B6). */
export function next(
  inputs: Inputs,
  pool: string,
  current: string,
  now: Date,
  opts: { model?: string | null } = {},
): Promise<string | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    return firstAvailable(ctx, afterCurrent(await members(ctx, pool), current), now, opts.model ?? null);
  });
}

/** Validates every name, then keeps those that are usable accounts (`default` or `ok`); others are skipped. */
async function usable(ctx: Ctx, candidates: readonly string[]): Promise<string[]> {
  for (const c of candidates) {
    if (!isValidName(c)) throw new MultiAccountError("INVALID_NAME", `invalid account name: ${JSON.stringify(c)}`);
  }
  const out: string[] = [];
  for (const c of candidates) {
    const e = await ctx.entry(c);
    if (e && e.state === "ok") out.push(c);
  }
  return out;
}

/**
 * `pickFrom(candidates, now, {model})`: the first available account of an ordered list, normally the
 * `candidates` of a resolution (B6). Names are validated; candidates that are not usable accounts are skipped.
 */
export function pickFrom(
  inputs: Inputs,
  candidates: readonly string[],
  now: Date,
  opts: { model?: string | null } = {},
): Promise<string | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    return firstAvailable(ctx, await usable(ctx, candidates), now, opts.model ?? null);
  });
}

/**
 * `nextFrom(candidates, current, now, {model})`: the next available candidate after `current`, wrapping (B6).
 * An alias group is one account, so the candidates that are the same account as `current` are passed over until
 * the last step.
 */
export function nextFrom(
  inputs: Inputs,
  candidates: readonly string[],
  current: string,
  now: Date,
  opts: { model?: string | null } = {},
): Promise<string | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const ok = new Set(await usable(ctx, candidates));
    let pos = -1;
    for (const [i, c] of candidates.entries()) {
      if (await ctx.sameAccount(c, current)) {
        pos = i;
        break;
      }
    }
    let order: string[];
    if (pos < 0) order = [...candidates];
    else {
      order = [];
      for (const c of [...candidates.slice(pos + 1), ...candidates.slice(0, pos)]) {
        if (!(await ctx.sameAccount(c, current))) order.push(c);
      }
      order.push(candidates[pos] as string);
    }
    return firstAvailable(ctx, order.filter((c) => ok.has(c)), now, opts.model ?? null);
  });
}
