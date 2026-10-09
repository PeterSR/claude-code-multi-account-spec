import { withLock } from "./atomic.js";
import { Ctx, isValidName } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import { fsCode, isLink } from "./fs.js";
import { readSessions, refuseIfBlocked } from "./sessions.js";
import type { Inputs } from "./types.js";

export type SlotState = "unmanaged" | "managed" | "broken" | "unsupported";

/** Result of `slot`, `adopt` and `activate`. `name` is set only when managed. */
export interface SlotInfo {
  state: SlotState;
  name: string | null;
}

/** Options of `adopt` and `activate`. `force` overrides sessions of unknown state, never live ones. */
export interface SlotOptions {
  force?: boolean;
}

const info = (state: SlotState, name: string | null = null): SlotInfo => ({ state, name });

async function lstatOrNull(ctx: Ctx, p: string): Promise<Awaited<ReturnType<Ctx["fs"]["lstat"]>> | null> {
  try {
    return await ctx.fs.lstat(p);
  } catch (e) {
    const c = fsCode(e);
    if (c === "ENOENT" || c === "ENOTDIR") return null;
    throw e;
  }
}

async function slotState(ctx: Ctx): Promise<SlotInfo> {
  const { P, fs, inputs } = ctx;
  const L = P.join(ctx.home, ".claude");
  const J = P.join(ctx.home, ".claude.json");
  if (inputs.platform === "darwin") return info("unsupported");
  if (inputs.platform === "win32" && ((await ctx.credentialManagerInUse(J)) || inputs.canCreateSymlinks === false)) {
    return info("unsupported");
  }
  const resolveLink = (target: string): string => (P.isAbsolute(target) ? P.normalize(target) : P.join(ctx.home, target));
  let l;
  try {
    l = await fs.lstat(L);
  } catch (e) {
    const c = fsCode(e);
    return c === "ENOENT" || c === "ENOTDIR" ? info("unmanaged") : info("broken");
  }
  if (l.type === "dir") return info("unmanaged");
  if (!isLink(l.type)) return info("broken");
  try {
    const t = resolveLink(await fs.readlink(L));
    const prefix = P.join(ctx.home, ".claude-");
    if (!t.startsWith(prefix)) return info("broken");
    const name = t.slice(prefix.length);
    if (!isValidName(name) || name === "default" || P.join(ctx.home, `.claude-${name}`) !== t) return info("broken");
    if ((await fs.stat(t)).type !== "dir") return info("broken");
    const jl = await fs.lstat(J);
    if (jl.type !== "symlink") return info("broken");
    const jt = resolveLink(await fs.readlink(J));
    if (jt !== P.join(t, ".claude.json")) return info("broken");
    const inner = await lstatOrNull(ctx, jt).catch(() => ({ type: "device" as const }));
    if (inner !== null && inner.type !== "file") return info("broken");
    const cred = await lstatOrNull(ctx, P.join(t, ".credentials.json")).catch(() => null);
    if (cred !== null && isLink(cred.type)) return info("broken");
    return info("managed", name);
  } catch {
    return info("broken");
  }
}

/** `slot()`: state of the `~/.claude` link pair (B7). `unsupported` takes precedence. */
export function slot(inputs: Inputs): Promise<SlotInfo> {
  return guarded(() => slotState(new Ctx(inputs)));
}

function requireSlotName(name: unknown): asserts name is string {
  if (typeof name !== "string" || !isValidName(name) || name === "default") {
    throw new MultiAccountError("INVALID_NAME", `adopt and activate take a named account: ${JSON.stringify(name)}`);
  }
}

/** Removes a link: a junction needs rmdir, a symlink unlink. */
async function removeLink(ctx: Ctx, p: string): Promise<void> {
  const st = await ctx.fs.lstat(p);
  if (st.type === "junction") return ctx.fs.rmdir(p);
  try {
    await ctx.fs.unlink(p);
  } catch (e) {
    if (ctx.inputs.platform !== "win32") throw e;
    await ctx.fs.rmdir(p);
  }
}

/** Proves links can be created here before anything is moved (a file symlink needs a privilege on Windows). */
async function probeLinks(ctx: Ctx): Promise<void> {
  const probe = ctx.P.join(ctx.home, `.claude-link-probe.tmp.${ctx.tempId()}`);
  try {
    await ctx.fs.symlink(ctx.P.join(ctx.home, ".claude.json"), probe, "file");
  } catch {
    // On Windows this is the missing symlink privilege; elsewhere links should always work, so it is a real error.
    if (ctx.inputs.platform === "win32") throw new MultiAccountError("SLOT_UNSUPPORTED", "this process cannot create file symlinks");
    throw new MultiAccountError("IO_ERROR", "cannot create a symlink in the home directory", ctx.home);
  }
  await removeLink(ctx, probe).catch(() => undefined);
}

/**
 * `adopt(name, {force})`: turns an unmanaged slot into a managed one (B7): moves `~/.claude` to
 * `~/.claude-<name>` and `~/.claude.json` into it, then creates both links. Runs under the slot lock, refuses
 * while a session is live, verifies links can be created first and rolls back if a step fails. Returns the
 * recomputed `slot()`.
 */
export function adopt(inputs: Inputs, name: string, opts: SlotOptions = {}): Promise<SlotInfo> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const { P, fs } = ctx;
    if ((await slotState(ctx)).state === "unsupported") throw new MultiAccountError("SLOT_UNSUPPORTED", "slot is unsupported here");
    requireSlotName(name);
    if (ctx.reserved.includes(name)) throw new MultiAccountError("RESERVED_NAME", `reserved account name: ${name}`);
    if ((await slotState(ctx)).state !== "unmanaged") throw new MultiAccountError("SLOT_STATE", "the slot is not unmanaged");
    const A = P.join(ctx.home, `.claude-${name}`);
    if ((await fs.lstat(A).then(() => true, () => false))) {
      throw new MultiAccountError("ACCOUNT_EXISTS", `account already exists: ${A}`, A);
    }
    const L = P.join(ctx.home, ".claude");
    const J = P.join(ctx.home, ".claude.json");
    const haveL = (await lstatOrNull(ctx, L)) !== null;
    const jn = await lstatOrNull(ctx, J);
    const innerPath = P.join(L, ".claude.json");
    const inner = haveL ? await lstatOrNull(ctx, innerPath) : null;
    if (jn !== null && inner !== null) {
      throw new MultiAccountError("SLOT_CONFLICT", "both ~/.claude.json and ~/.claude/.claude.json exist", innerPath);
    }
    if (jn !== null && jn.type !== "file") throw new MultiAccountError("SLOT_TARGET_INVALID", "~/.claude.json is not a regular file", J);
    if (jn === null && inner !== null && inner.type !== "file") {
      throw new MultiAccountError("SLOT_TARGET_INVALID", "~/.claude/.claude.json is not a regular file", innerPath);
    }
    const credPath = P.join(L, ".credentials.json");
    const cred = haveL ? await lstatOrNull(ctx, credPath) : null;
    if (cred !== null && isLink(cred.type)) {
      throw new MultiAccountError("SLOT_TARGET_INVALID", "~/.claude/.credentials.json is a link", credPath);
    }
    await withLock(ctx, P.join(ctx.home, ".claude-slot.lock"), async () => {
      refuseIfBlocked(await readSessions(ctx, "default"), opts.force === true);
      await probeLinks(ctx);
      const undo: (() => Promise<void>)[] = [];
      try {
        if (haveL) {
          await fs.rename(L, A);
          undo.push(() => fs.rename(A, L));
        } else {
          await fs.mkdir(A, 0o700);
          undo.push(() => fs.rmdir(A));
        }
        if (jn !== null) {
          await fs.rename(J, P.join(A, ".claude.json"));
          undo.push(() => fs.rename(P.join(A, ".claude.json"), J));
        }
        await fs.symlink(A, L, "dir");
        undo.push(() => removeLink(ctx, L));
        await fs.symlink(P.join(A, ".claude.json"), J, "file");
      } catch (e) {
        for (const u of undo.reverse()) await u().catch(() => undefined);
        throw e;
      }
    });
    return slotState(ctx);
  });
}

/**
 * `activate(name, {force})`: re-points a managed slot under the slot lock, refusing while a session in the
 * current slot account is live (B7). `~/.claude.json` is replaced first, then `~/.claude`; on Windows, where a
 * rename cannot replace a junction, the link is removed and created again. Returns the recomputed `slot()`.
 */
export function activate(inputs: Inputs, name: string, opts: SlotOptions = {}): Promise<SlotInfo> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const { P, fs } = ctx;
    const s = await slotState(ctx);
    if (s.state === "unsupported") throw new MultiAccountError("SLOT_UNSUPPORTED", "slot is unsupported here");
    requireSlotName(name);
    await ctx.gate(name);
    if (s.state !== "managed" || s.name === null) throw new MultiAccountError("SLOT_STATE", "the slot is not managed");
    const current = s.name;
    const A = P.join(ctx.home, `.claude-${name}`);
    for (const f of [".credentials.json", ".claude.json"]) {
      const p = P.join(A, f);
      const st = await lstatOrNull(ctx, p);
      if (st !== null && (f === ".credentials.json" ? isLink(st.type) : st.type !== "file")) {
        throw new MultiAccountError("SLOT_TARGET_INVALID", `${f} of ${name} cannot be used in the slot`, p);
      }
    }
    const L = P.join(ctx.home, ".claude");
    const J = P.join(ctx.home, ".claude.json");
    await withLock(ctx, P.join(ctx.home, ".claude-slot.lock"), async () => {
      refuseIfBlocked(await readSessions(ctx, current), opts.force === true);
      const tj = `${J}.tmp.${ctx.tempId()}`;
      await fs.symlink(P.join(A, ".claude.json"), tj, "file");
      await fs.rename(tj, J);
      if (ctx.inputs.platform === "win32") {
        await removeLink(ctx, L);
        await fs.symlink(A, L, "dir");
      } else {
        const tl = `${L}.tmp.${ctx.tempId()}`;
        await fs.symlink(A, tl, "dir");
        await fs.rename(tl, L);
      }
    });
    return slotState(ctx);
  });
}
