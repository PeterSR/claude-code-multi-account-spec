import { Ctx, isObject } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import type { Inputs, LiveSession, SessionStatus } from "./types.js";

/**
 * `liveSessions(name)`: reads `<config home>/sessions/<pid>.json` (B3). Only canonical file names count
 * (`[1-9][0-9]{0,9}.json`). The pid domain and start marker are compared as SPEC B3 says: another domain
 * is `unknown`, a missing process is `dead`, `procStartFt` (else `procStart`) equal is `live` and different
 * is `dead`, and a record with no marker for an existing pid is `unknown`. Sorted by pid.
 */
export function liveSessions(inputs: Inputs, name: string): Promise<LiveSession[]> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    return readSessions(ctx, name);
  });
}

/** Session listing without the account gate (shared with B4 and B7). */
export async function readSessions(ctx: Ctx, name: string): Promise<LiveSession[]> {
  const dir = ctx.P.join(ctx.configHome(name), "sessions");
  let names: string[];
  try {
    names = await ctx.fs.readdir(dir);
  } catch {
    return [];
  }
  const out: LiveSession[] = [];
  for (const n of names) {
    const m = /^([1-9][0-9]{0,9})\.json$/.exec(n);
    if (!m) continue;
    const d = await ctx.readJson(ctx.P.join(dir, n));
    if (!isObject(d)) continue;
    const pid = Number(m[1]);
    const domain = d["pidDomain"];
    let status: SessionStatus;
    if (domain !== undefined && domain !== null && domain !== ctx.inputs.pidDomain) {
      status = "unknown";
    } else {
      const proc = (await ctx.inputs.processTable?.lookup(pid)) ?? null;
      const ft = d["procStartFt"];
      const ps = d["procStart"];
      if (proc === null) status = "dead";
      else if (proc.lookupError) status = "unknown";
      else if (typeof ft === "string" && ft !== "") status = proc.procStartFt === ft ? "live" : "dead";
      else if (typeof ps === "string") status = proc.procStart === ps ? "live" : "dead";
      else status = "unknown";
    }
    const sid = d["sessionId"];
    out.push({ pid, sessionId: typeof sid === "string" ? sid : null, status });
  }
  return out.sort((a, b) => a.pid - b.pid);
}

/**
 * Throws SESSION_LIVE when a session blocks: it is `live`, or `unknown` and `force` is not set (`force` never
 * overrides `live`). With `sessionId` only that session counts.
 */
export function refuseIfBlocked(sessions: readonly LiveSession[], force: boolean, sessionId?: string): void {
  for (const s of sessions) {
    if (sessionId !== undefined && s.sessionId !== sessionId) continue;
    if (s.status === "live") throw new MultiAccountError("SESSION_LIVE", `a live session blocks this (pid ${s.pid})`);
    if (s.status === "unknown" && !force) {
      throw new MultiAccountError("SESSION_LIVE", `a session of unknown state blocks this (pid ${s.pid}); pass force to override`);
    }
  }
}

/**
 * `sessionOfPid(name, pid)`: the `sessionId` of `<config home>/sessions/<pid>.json`, or null (B3). Claude Code
 * rewrites the record when the conversation changes, so this is the current session of that process. No
 * liveness check.
 */
export function sessionOfPid(inputs: Inputs, name: string, pid: number): Promise<string | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    if (!Number.isInteger(pid) || pid < 1) return null;
    const d = await ctx.readJson(ctx.P.join(ctx.configHome(name), "sessions", `${pid}.json`));
    return isObject(d) && typeof d["sessionId"] === "string" && d["sessionId"] !== "" ? d["sessionId"] : null;
  });
}
