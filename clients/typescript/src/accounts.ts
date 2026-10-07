import { byteCompare } from "./bytes.js";
import { Ctx, isValidName } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import type { Warning } from "./errors.js";
import { identityKey } from "./fs.js";
import { pathOps } from "./paths.js";
import type { Account, ClaimConflict, Inputs, ListResult, Platform } from "./types.js";

/**
 * Canonical config dir of an account: `join(home, ".claude-" + name)` in NFC with the platform's path
 * semantics. `default` gives `$HOME/.claude`. Pure: never touches the filesystem and allows reserved names.
 */
export function canonicalPath(home: string, name: string, platform: Platform): string {
  if (name !== "default" && !isValidName(name)) {
    throw new MultiAccountError("INVALID_NAME", `invalid account name: ${JSON.stringify(name)}`);
  }
  const P = pathOps(platform);
  return P.join(home, name === "default" ? ".claude" : `.claude-${name}`).normalize("NFC");
}

/** Lists the accounts under `home` (A2 discovery), their alias relations and claim conflicts. */
export function list(inputs: Inputs): Promise<ListResult> {
  return guarded(() => listImpl(inputs));
}

async function listImpl(inputs: Inputs): Promise<ListResult> {
  const ctx = new Ctx(inputs);
  const d = await ctx.accounts();
  const accounts: Account[] = [];
  for (const e of d.entries) {
    const ok = e.state === "ok";
    let hasSpecFile = false;
    let hasGlobalConfig = false;
    let specError: Account["specError"] = null;
    if (ok) {
      hasSpecFile = await ctx.isRegular(ctx.P.join(e.dir, ".multi-account.json"));
      hasGlobalConfig = await ctx.isRegular(await ctx.globalConfigPath(e.name));
      const spec = await ctx.specFor(e);
      if (spec.status === "invalid") specError = { code: "SPEC_FILE_INVALID", path: spec.path };
    }
    const warnings: Warning[] = [];
    if (e.name !== "default" && ctx.reserved.includes(e.name)) {
      warnings.push({ code: "RESERVED_NAME", message: `${e.name} is a reserved name`, path: e.dir });
    }
    accounts.push({
      name: e.name,
      configDir: e.dir,
      state: e.state,
      hasSpecFile,
      hasGlobalConfig,
      aliasOf: e.aliasOf,
      specError,
      warnings,
    });
  }

  const byIdentity = new Map<string, { path: string; name: string }[]>();
  for (const e of await ctx.primaries()) {
    const spec = await ctx.specFor(e);
    if (spec.status !== "ok") continue;
    const dirs = spec.data["directories"];
    for (const x of Array.isArray(dirs) ? dirs : []) {
      const path = ctx.expandClaim(x);
      if (path === null) continue;
      let key: string;
      try {
        key = identityKey(await ctx.fs.stat(path));
      } catch {
        continue;
      }
      const l = byIdentity.get(key) ?? [];
      if (!l.some((m) => m.name === e.name)) l.push({ path, name: e.name });
      byIdentity.set(key, l);
    }
  }
  const conflicts: ClaimConflict[] = [];
  for (const l of byIdentity.values()) {
    if (new Set(l.map((m) => m.name)).size >= 2) {
      conflicts.push({ path: (l[0] as { path: string }).path, accounts: l.map((m) => m.name) });
    }
  }
  conflicts.sort((a, b) => byteCompare(a.path, b.path));

  const warnings: Warning[] = d.notADirectory.map((path) => ({
    code: "NOT_A_DIRECTORY" as const,
    message: `${path} is not a directory`,
    path,
  }));
  return { accounts, conflicts, warnings };
}
