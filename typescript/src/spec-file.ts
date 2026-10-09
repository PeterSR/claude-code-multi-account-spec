import { withFileLock, writeFileAtomic } from "./atomic.js";
import { Ctx, isObject } from "./ctx.js";
import type { Entry } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import { identityKey } from "./fs.js";
import type { Inputs } from "./types.js";

type Spec = Record<string, unknown>;

const specPath = (ctx: Ctx, e: Entry): string => ctx.P.join(e.dir, ".multi-account.json");

function invalid(path: string): MultiAccountError {
  return new MultiAccountError("SPEC_FILE_INVALID", `invalid spec file: ${path}`, path);
}

/** The validated spec file of an account, null when absent; SPEC_FILE_INVALID otherwise. Never cached. */
async function readSpec(ctx: Ctx, e: Entry): Promise<Spec | null> {
  const s = await ctx.loadSpec(e);
  if (s.status === "invalid") throw invalid(s.path);
  return s.status === "none" ? null : s.data;
}

/** `specFile(name)`: the spec file object verbatim if valid, null if absent, SPEC_FILE_INVALID otherwise (A3). */
export function specFile(inputs: Inputs, name: string): Promise<Record<string, unknown> | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    return readSpec(ctx, await ctx.gate(name));
  });
}

/** Writes `next` after checking it is still a valid spec file; INVALID_ENTRY otherwise (nothing is written). */
async function writeSpec(ctx: Ctx, e: Entry, next: Spec): Promise<void> {
  const path = specPath(ctx, e);
  if (ctx.validateSpec(next, path).status !== "ok") throw new MultiAccountError("INVALID_ENTRY", "the result is not a valid spec file");
  await writeFileAtomic(ctx, path, JSON.stringify(next));
}

/**
 * `updateSpecFile(name, patch)`: merges keys into the spec file under the lock (A3). A null value deletes a key,
 * any other sets it; a result that is not a valid spec file is INVALID_ENTRY. Returns the new object.
 */
export function updateSpecFile(inputs: Inputs, name: string, patch: Record<string, unknown>): Promise<Spec> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const e = await ctx.gate(name);
    if (!isObject(patch)) throw new MultiAccountError("INVALID_ENTRY", "patch must be an object");
    return withFileLock(ctx, specPath(ctx, e), async () => {
      const next: Spec = { ...((await readSpec(ctx, e)) ?? { version: 1 }) };
      for (const [k, v] of Object.entries(patch)) {
        if (v === null) delete next[k];
        else next[k] = v;
      }
      await writeSpec(ctx, e, next);
      return next;
    });
  });
}

/** Expands a claim argument; INVALID_ENTRY unless absolute or `~/`. */
function expand(ctx: Ctx, dir: string): string {
  const e = typeof dir === "string" ? ctx.expandClaim(dir) : null;
  if (e === null) throw new MultiAccountError("INVALID_ENTRY", `not an absolute path or ~/ path: ${JSON.stringify(dir)}`);
  return e;
}

function stored(ctx: Ctx, e: string): string {
  const fold = (s: string): string => (ctx.fs.caseInsensitive ? s.replace(/[A-Z]/g, (c) => c.toLowerCase()) : s);
  const home = ctx.P.normalize(ctx.home);
  if (fold(e) === fold(home)) return "~/";
  const prefix = home.endsWith(ctx.P.sep) ? home : home + ctx.P.sep;
  if (fold(e).startsWith(fold(prefix))) return `~/${e.slice(prefix.length).split(ctx.P.sep).join("/")}`;
  return e;
}

async function sameDir(ctx: Ctx, a: string, b: string): Promise<boolean> {
  try {
    return identityKey(await ctx.fs.stat(a)) === identityKey(await ctx.fs.stat(b));
  } catch {
    const f = (s: string): string => (ctx.fs.caseInsensitive ? s.replace(/[A-Z]/g, (c) => c.toLowerCase()) : s);
    return f(ctx.P.normalize(a)) === f(ctx.P.normalize(b));
  }
}

async function entriesOf(spec: Spec | null): Promise<string[]> {
  const ds = spec?.["directories"];
  return Array.isArray(ds) ? (ds as string[]) : [];
}

/**
 * `claim(name, dir)`: adds a directory to the account's claims (A3). Refuses with CLAIM_CONFLICT when another
 * account already claims the same directory, and writes nothing when this account does. Returns the list after.
 */
export function claim(inputs: Inputs, name: string, dir: string): Promise<{ directories: string[] }> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const me = await ctx.gate(name);
    const e = expand(ctx, dir);
    for (const o of await ctx.primaries()) {
      if (o.group !== null && o.group === me.group) continue;
      if (o === me) continue;
      const s = await readSpec(ctx, o);
      for (const x of await entriesOf(s)) {
        const p = ctx.expandClaim(x);
        if (p !== null && (await sameDir(ctx, p, e))) throw new MultiAccountError("CLAIM_CONFLICT", `${o.name} already claims ${e}`, e);
      }
    }
    return withFileLock(ctx, specPath(ctx, me), async () => {
      const spec = await readSpec(ctx, me);
      const have = await entriesOf(spec);
      for (const x of have) {
        const p = ctx.expandClaim(x);
        if (p !== null && (await sameDir(ctx, p, e))) return { directories: have };
      }
      const next: Spec = { ...(spec ?? { version: 1 }), directories: [...have, stored(ctx, e)] };
      await writeSpec(ctx, me, next);
      return { directories: next["directories"] as string[] };
    });
  });
}

/** `unclaim(name, dir)`: removes every claim of the same directory; writes only if something was removed (A3). */
export function unclaim(inputs: Inputs, name: string, dir: string): Promise<{ directories: string[] }> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const me = await ctx.gate(name);
    const e = expand(ctx, dir);
    return withFileLock(ctx, specPath(ctx, me), async () => {
      const spec = await readSpec(ctx, me);
      if (spec === null) return { directories: [] };
      const have = await entriesOf(spec);
      const keep: string[] = [];
      for (const x of have) {
        const p = ctx.expandClaim(x);
        if (!(p !== null && (await sameDir(ctx, p, e)))) keep.push(x);
      }
      if (keep.length === have.length) return { directories: have };
      await writeSpec(ctx, me, { ...spec, directories: keep });
      return { directories: keep };
    });
  });
}
