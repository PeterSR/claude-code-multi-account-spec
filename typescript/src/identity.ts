import { Ctx, isObject } from "./ctx.js";
import { guarded } from "./errors.js";
import { isLink } from "./fs.js";
import type { Credentials, Identity, Inputs, ResolveResult, Usage } from "./types.js";

/** Global config of a name (gated) or of a resolution (its `globalConfig`, null gives no data). */
async function globalConfig(ctx: Ctx, target: string | Pick<ResolveResult, "globalConfig">): Promise<Record<string, unknown> | null> {
  let path: string | null;
  if (typeof target === "string") {
    await ctx.gate(target);
    path = await ctx.globalConfigPath(target);
  } else {
    path = target.globalConfig;
  }
  if (path === null) return null;
  const d = await ctx.readJson(path);
  return isObject(d) ? d : null;
}

const str = (x: unknown): string | null => (x === undefined ? null : (x as string | null));

/**
 * `identity(name or resolution)`: who is logged in, read from `oauthAccount` in the global config (B2).
 * A status line should pass the resolution, whose `globalConfig` is the file `claude` really uses.
 * No credential is read. Null when there is no data.
 */
export function identity(inputs: Inputs, name: string): Promise<Identity | null> {
  return identityOf(inputs, name);
}

/** `identityFor(resolution)`: as `identity`, from the resolution's `globalConfig`. */
export function identityFor(inputs: Inputs, res: Pick<ResolveResult, "globalConfig">): Promise<Identity | null> {
  return identityOf(inputs, res);
}

function identityOf(inputs: Inputs, target: string | Pick<ResolveResult, "globalConfig">): Promise<Identity | null> {
  return guarded(async () => {
    const d = await globalConfig(new Ctx(inputs), target);
    const o = d?.["oauthAccount"];
    if (!isObject(o)) return null;
    return {
      email: str(o["emailAddress"]),
      orgName: str(o["organizationName"]),
      orgUuid: str(o["organizationUuid"]),
      organizationType: str(o["organizationType"]),
      billingType: str(o["billingType"]),
      userRateLimitTier: str(o["userRateLimitTier"]),
      organizationRateLimitTier: str(o["organizationRateLimitTier"]),
    };
  });
}

/** `usage(name or resolution)`: `cachedUsageUtilization` from the global config, as fresh as Claude Code left it (B2). */
export function usage(inputs: Inputs, name: string): Promise<Usage | null> {
  return usageOf(inputs, name);
}

/** `usageFor(resolution)`: as `usage`, from the resolution's `globalConfig`. */
export function usageFor(inputs: Inputs, res: Pick<ResolveResult, "globalConfig">): Promise<Usage | null> {
  return usageOf(inputs, res);
}

function usageOf(inputs: Inputs, target: string | Pick<ResolveResult, "globalConfig">): Promise<Usage | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    const d = await globalConfig(ctx, target);
    const u = d?.["cachedUsageUtilization"];
    if (!isObject(u)) return null;
    const ms = u["fetchedAtMs"];
    const windows: Usage["windows"] = {};
    const util = u["utilization"];
    if (isObject(util)) {
      for (const [k, v] of Object.entries(util)) {
        if (!isObject(v)) continue;
        windows[k] = {
          utilization: typeof v["utilization"] === "number" ? v["utilization"] : null,
          resetsAt: typeof v["resets_at"] === "string" ? v["resets_at"] : null,
        };
      }
    }
    const oauth = d?.["oauthAccount"];
    const ownUuid = isObject(oauth) ? oauth["accountUuid"] : undefined;
    const age = typeof ms === "number" ? ctx.requireClock().now().getTime() - ms : NaN;
    const stale = typeof ms !== "number" || age < 0 || age > 3_600_000 || u["accountUuid"] !== ownUuid;
    return { fetchedAt: typeof ms === "number" ? isoMillis(ms) : null, data: u, windows, stale };
  });
}

/** Milliseconds since the epoch as RFC 3339 UTC with exactly three fractional digits, or null if out of range. */
function isoMillis(ms: number): string | null {
  const t = new Date(ms);
  return Number.isNaN(t.getTime()) ? null : t.toISOString();
}

/**
 * `credentials(name)`: the stored OAuth token from `<config home>/.credentials.json`, read only, never a
 * keychain (B2). A link there counts as unreadable, as it does for Claude Code (O_NOFOLLOW). The refresh
 * token is never returned. An expired token is reported as `expired: true`. Tools MUST NOT refresh tokens:
 * run `claude` under that account instead. Needs `inputs.clock`.
 */
export function credentials(inputs: Inputs, name: string): Promise<Credentials | null> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    const path = ctx.P.join(ctx.configHome(name), ".credentials.json");
    try {
      if (isLink((await ctx.fs.lstat(path)).type)) return null;
    } catch {
      return null;
    }
    const data = await ctx.readJson(path);
    const o = isObject(data) ? data["claudeAiOauth"] : undefined;
    if (!isObject(o) || typeof o["accessToken"] !== "string" || o["accessToken"] === "") return null;
    const ms = o["expiresAt"];
    const expiresAt = typeof ms === "number" ? isoMillis(ms) : null;
    const now = ctx.requireClock().now().getTime();
    const scopes = Array.isArray(o["scopes"]) ? o["scopes"].filter((s): s is string => typeof s === "string") : [];
    const strOrNull = (x: unknown): string | null => (typeof x === "string" ? x : null);
    return {
      source: "file",
      path,
      accessToken: o["accessToken"],
      expiresAt,
      expired: typeof ms === "number" && expiresAt !== null && ms <= now,
      scopes,
      subscriptionType: strOrNull(o["subscriptionType"]),
      rateLimitTier: strOrNull(o["rateLimitTier"]),
    };
  });
}
