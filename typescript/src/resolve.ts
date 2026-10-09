import { fold } from "./bytes.js";
import { Ctx, isValidName } from "./ctx.js";
import type { Entry } from "./ctx.js";
import { launchEnv, overriddenBy } from "./env.js";
import { guarded, MultiAccountError } from "./errors.js";
import type { Warning } from "./errors.js";
import { identityKey } from "./fs.js";
import { parseMarker } from "./marker.js";
import type {
  Inputs,
  MapConfigDirResult,
  MapReason,
  ResolveOptions,
  ResolveResult,
  ResolveSource,
} from "./types.js";

interface Mapping {
  account: string | null;
  canonical: boolean;
  reason: MapReason | null;
}

const warn = (code: Warning["code"], message: string, path?: string): Warning =>
  path === undefined ? { code, message } : { code, message, path };

async function mapping(ctx: Ctx, v: string): Promise<Mapping> {
  const { P, fs } = ctx;
  const d = await ctx.accounts();
  const named = d.entries.filter((e) => e.name !== "default" && e.state === "ok");
  for (const e of named) if (v === e.dir) return { account: e.name, canonical: true, reason: null };
  if (P.isAbsolute(v)) {
    const n = P.normalize(v).normalize("NFC");
    for (const e of named) if (n === e.dir) return { account: e.name, canonical: false, reason: "not-normalized" };
    if (fs.caseInsensitive) {
      for (const e of named) if (fold(n) === fold(e.dir)) return { account: e.name, canonical: false, reason: "case-mismatch" };
    }
    if (n === ctx.configHome("default")) return { account: "default", canonical: false, reason: "default-via-config-dir" };
    try {
      const rv = await fs.realpath(v);
      for (const e of [...named, d.entries[0] as Entry]) {
        try {
          if ((await fs.realpath(e.dir)) === rv) return { account: e.name, canonical: false, reason: "resolved-target" };
        } catch {
          /* candidate has no real path */
        }
      }
    } catch {
      /* value has no real path */
    }
  }
  return { account: null, canonical: false, reason: "foreign" };
}

/** Maps a `CLAUDE_CONFIG_DIR` value to an account (the A4 step 1 table). */
export function mapConfigDir(inputs: Inputs, value: string): Promise<MapConfigDirResult> {
  return guarded(() => mapConfigDirImpl(inputs, value));
}

async function mapConfigDirImpl(inputs: Inputs, value: string): Promise<MapConfigDirResult> {
  const m = await mapping(new Ctx(inputs), value);
  return {
    ...m,
    warnings: m.canonical ? [] : [warn("NON_CANONICAL_CONFIG_DIR", `${value} is not the canonical path of an account`)],
  };
}

/** Result for a bound account. `bindPath` is the ACCOUNT_NOT_FOUND path (marker file or claimed directory). */
async function bindAccount(
  ctx: Ctx,
  name: string,
  source: ResolveSource,
  matchedPath: string | null,
  warnings: Warning[],
  ignored: string[],
  bindPath: string | null,
  candidates: readonly string[] = [name],
): Promise<ResolveResult> {
  const entry = await ctx.lookup(name, bindPath ?? ctx.P.join(ctx.home, `.claude-${name}`));
  const configDir = ctx.configHome(name);
  const w = [...warnings];
  if (name !== "default" && ctx.reserved.includes(name)) w.push(warn("RESERVED_NAME", `${name} is a reserved name`, configDir));
  return {
    account: name,
    pool: null,
    configDir,
    canonical: true,
    reason: null,
    source,
    matchedPath,
    exists: true,
    aliasOf: entry.aliasOf,
    candidates: [...candidates],
    applied: true,
    globalConfig: await ctx.globalConfigPath(name),
    launchEnv: launchEnv(ctx, name),
    overriddenBy: await overriddenBy(ctx, configDir),
    ignoredMarkers: ignored,
    warnings: w,
  };
}

/** Binds a marker's entries: every one must exist, in list order; the first is the account. */
async function bindList(
  ctx: Ctx,
  names: readonly string[],
  source: ResolveSource,
  matchedPath: string,
  warnings: Warning[],
  ignored: string[],
  bindPath: string,
): Promise<ResolveResult> {
  await ctx.lookup(names[0] as string, bindPath);
  const w = [...warnings];
  for (const n of names.slice(1)) {
    const e = await ctx.entry(n);
    if (!e || e.state !== "ok") w.push(warn("CANDIDATE_UNAVAILABLE", `${n} is not an available account`, matchedPath));
  }
  return bindAccount(ctx, names[0] as string, source, matchedPath, w, ignored, bindPath, names);
}

/**
 * Decides which account applies (A4): env, then the nearest marker or claim above `cwd`, then default.
 * All inputs are explicit; nothing is read from the process.
 */
export function resolve(inputs: Inputs, opts: ResolveOptions = {}): Promise<ResolveResult> {
  return guarded(() => resolveImpl(inputs, opts));
}

async function resolveImpl(inputs: Inputs, opts: ResolveOptions): Promise<ResolveResult> {
  const ctx = new Ctx(inputs);
  const { P, fs } = ctx;
  const warnings: Warning[] = [];
  const env: Record<string, string | undefined> = { ...inputs.env };
  for (const k of ["CLAUDE_CONFIG_DIR", "CLAUDE_MULTI_ACCOUNT", "CLAUDE_MULTI_ACCOUNT_SOURCE"]) {
    if (env[k] === "") {
      delete env[k];
      warnings.push(warn("EMPTY_ENV", `${k} is set but empty; treated as unset`));
    }
  }
  if (opts.ignoreHookEnv && env["CLAUDE_MULTI_ACCOUNT_SOURCE"] === "hook") {
    delete env["CLAUDE_MULTI_ACCOUNT"];
    delete env["CLAUDE_CONFIG_DIR"];
  }
  const M = env["CLAUDE_MULTI_ACCOUNT"];
  const V = env["CLAUDE_CONFIG_DIR"];
  if (M !== undefined && !isValidName(M)) {
    throw new MultiAccountError("INVALID_NAME", `invalid CLAUDE_MULTI_ACCOUNT: ${JSON.stringify(M)}`);
  }

  if (V !== undefined) {
    const m = await mapping(ctx, V);
    if (M !== undefined && !(m.account !== null && (await ctx.sameAccount(m.account, M)))) {
      if (M !== "default" && P.isAbsolute(V) && P.normalize(V).normalize("NFC") === ctx.canonical(M)) await ctx.gate(M);
      throw new MultiAccountError("ENV_CONFLICT", `CLAUDE_MULTI_ACCOUNT=${M} disagrees with CLAUDE_CONFIG_DIR=${V}`);
    }
    const w = [...warnings];
    if (!m.canonical) w.push(warn("NON_CANONICAL_CONFIG_DIR", `${V} is not the canonical path of an account`));
    let exists = false;
    try {
      exists = P.isAbsolute(V) && (await fs.stat(V)).type === "dir";
    } catch {
      exists = false;
    }
    const globalConfig = P.isAbsolute(V) ? await ctx.globalConfigForHome(V) : null;
    if (m.account === null) {
      return {
        account: null,
        pool: null,
        configDir: V,
        canonical: false,
        reason: "foreign",
        source: "config-dir",
        matchedPath: null,
        exists,
        aliasOf: null,
        candidates: [],
        applied: true,
        globalConfig,
        launchEnv: null,
        overriddenBy: await overriddenBy(ctx, V),
        ignoredMarkers: [],
        warnings: w,
      };
    }
    const r = await bindAccount(ctx, m.account, "config-dir", null, [], [], null);
    return {
      ...r,
      configDir: V,
      canonical: m.canonical,
      reason: m.reason,
      exists,
      globalConfig,
      overriddenBy: await overriddenBy(ctx, V),
      warnings: [...w, ...r.warnings],
    };
  }
  if (M !== undefined) {
    const r = await bindAccount(ctx, M, "env", null, warnings, [], null);
    if (await ctx.sameAccount(M, "default")) return r;
    if (env["CLAUDECODE"] === "1") {
      throw new MultiAccountError("ENV_CONFLICT", `CLAUDE_MULTI_ACCOUNT=${M} was never applied: claude ignores it`);
    }
    return {
      ...r,
      applied: false,
      warnings: [...r.warnings, warn("ENV_NOT_APPLIED", `CLAUDE_MULTI_ACCOUNT=${M} is ignored by claude; apply launchEnv`)],
    };
  }
  return walk(ctx, opts, warnings);
}

async function walk(ctx: Ctx, opts: ResolveOptions, warnings: Warning[]): Promise<ResolveResult> {
  const { P, fs } = ctx;
  const levels: string[] = [];
  const ceilings = (opts.ceilingDirs ?? []).map((c) => P.normalize(c));
  const same = (a: string, b: string): boolean => (fs.caseInsensitive ? fold(a) === fold(b) : a === b);
  for (let cur: string | null = P.normalize(ctx.inputs.cwd); cur !== null; cur = P.parent(cur)) {
    levels.push(cur);
    if (ceilings.some((c) => same(cur as string, c))) break;
  }
  const git: boolean[] = [];
  for (const d of levels) {
    try {
      await fs.lstat(P.join(d, ".git"));
      git.push(true);
    } catch {
      git.push(false);
    }
  }
  const trust = opts.trustRepoMarkers === true;
  const ignored: string[] = [];
  const w = [...warnings];
  let claims: { entry: Entry; idents: Set<string> }[] | undefined;

  for (const [i, dir] of levels.entries()) {
    const mp = P.join(dir, ".claude-account");
    let candidate = false;
    try {
      await fs.lstat(mp);
      try {
        candidate = (await fs.stat(mp)).type !== "dir";
      } catch {
        candidate = false;
      }
    } catch {
      /* no entry */
    }
    if (candidate && !trust && git.slice(i).some(Boolean)) {
      ignored.push(mp);
      w.push(warn("MARKER_IGNORED_IN_REPO", `ignored marker inside a git working tree: ${mp}`, mp));
    } else {
      const m = await parseMarker(fs, mp);
      if (m.kind === "account" || m.kind === "default" || m.kind === "list") {
        return bindList(ctx, m.candidates, "marker-file", mp, w, ignored, mp);
      }
      if (m.kind === "pool") {
        return {
          account: null,
          pool: m.pool,
          configDir: null,
          canonical: false,
          reason: null,
          source: "marker-file",
          matchedPath: mp,
          exists: false,
          aliasOf: null,
          candidates: [],
          applied: true,
          globalConfig: null,
          launchEnv: null,
          overriddenBy: await overriddenBy(ctx, null),
          ignoredMarkers: ignored,
          warnings: w,
        };
      }
    }

    if (claims === undefined) {
      const okEntries = (await ctx.accounts()).entries.filter((e) => e.state === "ok");
      for (const e of okEntries) {
        const s = await ctx.specFor(e);
        if (s.status === "invalid") {
          throw new MultiAccountError("SPEC_FILE_INVALID", `invalid spec file: ${s.path}`, s.path);
        }
      }
      claims = [];
      for (const e of await ctx.primaries()) {
        const s = await ctx.specFor(e);
        const idents = new Set<string>();
        if (s.status === "ok") {
          const ds = s.data["directories"];
          for (const x of Array.isArray(ds) ? ds : []) {
            const p = ctx.expandClaim(x);
            if (p === null) continue;
            try {
              idents.add(identityKey(await fs.stat(p)));
            } catch {
              /* claim does not exist: ignored */
            }
          }
        }
        claims.push({ entry: e, idents });
      }
    }
    let here: string;
    try {
      here = identityKey(await fs.stat(dir));
    } catch {
      continue;
    }
    const claimants = claims.filter((c) => c.idents.has(here)).map((c) => c.entry.name);
    if (claimants.length > 1) {
      throw new MultiAccountError("CLAIM_CONFLICT", `${claimants.join(", ")} all claim ${dir}`, dir);
    }
    if (claimants.length === 1) return bindAccount(ctx, claimants[0] as string, "claim", dir, w, ignored, dir);
  }
  return bindAccount(ctx, "default", "default", null, w, ignored, null);
}
