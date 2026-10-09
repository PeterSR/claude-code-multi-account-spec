import { createHash } from "node:crypto";
import { byteCompare } from "./bytes.js";
import { Ctx, isObject, isValidName } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import type { CredentialLocation, EnvOptions, EnvResult, Inputs, LaunchEnv } from "./types.js";

function requireName(name: string): void {
  if (name !== "default" && !isValidName(name)) {
    throw new MultiAccountError("INVALID_NAME", `invalid account name: ${JSON.stringify(name)}`);
  }
}

/** Variables that replace the login and that `clearAuthOverrides` unsets. */
const AUTH_CLEARABLE = [
  "CLAUDE_CODE_OAUTH_TOKEN",
  "ANTHROPIC_API_KEY",
  "ANTHROPIC_AUTH_TOKEN",
  "CLAUDE_CODE_USE_BEDROCK",
  "CLAUDE_CODE_USE_VERTEX",
  "CLAUDE_CODE_USE_FOUNDRY",
  "ANTHROPIC_PROFILE",
] as const;
const TRUTHY_VARS = new Set(["CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"]);
const TRUTHY = new Set(["1", "true", "yes", "on"]);

/** The B1 launch delta for an account (internal, pure). */
export function launchEnv(ctx: Ctx, name: string, clearAuthOverrides = false): LaunchEnv {
  const set: Record<string, string> = { CLAUDE_MULTI_ACCOUNT: name };
  const unset = new Set(["CLAUDE_MULTI_ACCOUNT_SOURCE", "CLAUDE_SECURESTORAGE_CONFIG_DIR"]);
  if (name === "default") unset.add("CLAUDE_CONFIG_DIR");
  else set["CLAUDE_CONFIG_DIR"] = ctx.canonical(name);
  if (clearAuthOverrides) for (const k of AUTH_CLEARABLE) unset.add(k);
  return { set, unset: [...unset].sort(byteCompare) };
}

function counts(src: Readonly<Record<string, string | undefined>>, k: string): boolean {
  const v = src[k];
  if (v === undefined) return false;
  return TRUTHY_VARS.has(k) ? TRUTHY.has(v.trim().toLowerCase()) : v !== "";
}

/**
 * Variables and settings that replace the login (A4 `overriddenBy`), in fixed order. `configDir` is
 * where `settings.json` is looked up (its `env` block and `apiKeyHelper`); null skips that.
 */
export async function overriddenBy(ctx: Ctx, configDir: string | null, clearAuthOverrides = false): Promise<string[]> {
  const env = ctx.inputs.env;
  let settingsEnv: Record<string, string> = {};
  let helper = false;
  if (configDir !== null) {
    const settings = await ctx.readJson(ctx.P.join(configDir, "settings.json"));
    if (isObject(settings)) {
      const e = settings["env"];
      if (isObject(e)) {
        settingsEnv = Object.fromEntries(Object.entries(e).filter((kv): kv is [string, string] => typeof kv[1] === "string"));
      }
      const h = settings["apiKeyHelper"];
      helper = typeof h === "string" && h !== "";
    }
  }
  const out: string[] = [];
  for (const k of AUTH_CLEARABLE) if ((!clearAuthOverrides && counts(env, k)) || counts(settingsEnv, k)) out.push(k);
  if (env["CLAUDE_SECURESTORAGE_CONFIG_DIR"] !== undefined) out.push("CLAUDE_SECURESTORAGE_CONFIG_DIR");
  if (env["CLAUDE_CODE_CUSTOM_OAUTH_URL"]) out.push("CLAUDE_CODE_CUSTOM_OAUTH_URL");
  if (helper) out.push("apiKeyHelper");
  return out;
}

/**
 * `env(name)`: the environment delta to launch as an account (B1). Launch with this, never with
 * `CLAUDE_CONFIG_DIR=$HOME/.claude` for default. Also reports `overriddenBy`.
 */
export function env(inputs: Inputs, name: string, opts: EnvOptions = {}): Promise<EnvResult> {
  return guarded(async () => {
    requireName(name);
    const ctx = new Ctx(inputs);
    const clear = opts.clearAuthOverrides === true;
    return { ...launchEnv(ctx, name, clear), overriddenBy: await overriddenBy(ctx, ctx.configHome(name), clear) };
  });
}

/** `credentialLocations(name)`: the ordered places Claude Code looks for a login on this platform (B1). */
export function credentialLocations(inputs: Inputs, name: string): Promise<CredentialLocation[]> {
  return guarded(() => credentialLocationsImpl(inputs, name));
}

async function credentialLocationsImpl(inputs: Inputs, name: string): Promise<CredentialLocation[]> {
  requireName(name);
  const ctx = new Ctx(inputs);
  const home = ctx.configHome(name);
  const file: CredentialLocation = { file: ctx.P.join(home, ".credentials.json") };
  switch (inputs.platform) {
    case "linux":
      return [file];
    case "darwin": {
      let service = `Claude Code${ctx.oauthSuffix()}-credentials`;
      if (name !== "default") service += `-${createHash("sha256").update(home, "utf8").digest("hex").slice(0, 8)}`;
      let account = inputs.env["USER"] || inputs.userName || "claude-code-user";
      if (!/^[a-zA-Z0-9._-]+$/.test(account)) account = "claude-code-user";
      return [{ keychain: { service, account } }, file];
    }
    case "win32":
      return (await ctx.credentialManagerInUse(await ctx.globalConfigPath(name)))
        ? [{ credentialManager: {} }, file]
        : [file];
  }
}
