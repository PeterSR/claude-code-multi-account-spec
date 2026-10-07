import type { Fs } from "./fs.js";

export type Platform = "linux" | "darwin" | "win32";

/** The environment as a plain map. */
export type Env = Readonly<Record<string, string | undefined>>;

/** Source of the current time. */
export interface Clock {
  now(): Date;
  /** Waits; used only for bounded lock retries. Without it a held lock is LOCK_BUSY at once. */
  sleep?(ms: number): Promise<void>;
}

/**
 * One entry of the process table: the start marker Claude Code records, `procStart` (Linux, macOS) or
 * `procStartFt` (Windows FILETIME string). Opaque strings compared verbatim.
 */
export interface ProcessInfo {
  procStart?: string;
  procStartFt?: string;
  /** True when the lookup itself failed (error, timeout, missing tool): the process may still exist. */
  lookupError?: true;
}

/** The process table seam (B3). Returns null when the pid does not exist. */
export interface ProcessTable {
  lookup(pid: number): Promise<ProcessInfo | null>;
}

/**
 * Everything the library may look at. The core never reads process globals, the real clock,
 * the real filesystem or the real process table; `fromProcess()` fills this from the OS.
 */
export interface Inputs {
  env: Env;
  /** Absolute working directory. */
  cwd: string;
  home: string;
  platform: Platform;
  fs: Fs;
  /** Required by operations that write (they stamp times and judge lock staleness). */
  clock?: Clock;
  /** Required by `liveSessions`; without it every session with a matching file is `dead`. */
  processTable?: ProcessTable;
  /** The caller's own pid domain (B3). Sessions from another domain are `unknown`. */
  pidDomain?: string;
  /** OS user name, used for the macOS keychain account when `env.USER` is unset. */
  userName?: string;
  /** False models Windows without permission to create file symlinks (B7). Default true. */
  canCreateSymlinks?: boolean;
  /** Upper bound in ms for retrying a held lock when `clock.sleep` exists. Default 0 (no wait); `fromProcess` sets 2000. */
  lockWaitMs?: number;
  /** Replaces the embedded reserved-name list. */
  reserved?: readonly string[];
  /** Returns the `<pid>.<12 hex>` part of temp file names. Default: pid 0 and random hex. */
  tempId?: () => string;
}

/** Options of `resolve` (A4). */
export interface ResolveOptions {
  /** Honour `.claude-account` files inside git working trees. Default false. */
  trustRepoMarkers?: boolean;
  /** Ignore `CLAUDE_MULTI_ACCOUNT` and `CLAUDE_CONFIG_DIR` when the source is `hook`. Default false. */
  ignoreHookEnv?: boolean;
  /** Stop the upward walk after any of these directories. */
  ceilingDirs?: readonly string[];
}

export type AccountState = "ok" | "dangling" | "unreadable";

/** One account as reported by `list`. */
export interface Account {
  name: string;
  configDir: string;
  state: AccountState;
  hasSpecFile: boolean;
  hasGlobalConfig: boolean;
  aliasOf: string | null;
  specError: { code: "SPEC_FILE_INVALID"; path: string } | null;
  warnings: import("./errors.js").Warning[];
}

/** Two or more accounts claiming the same directory. */
export interface ClaimConflict {
  path: string;
  accounts: string[];
}

export interface ListResult {
  accounts: Account[];
  conflicts: ClaimConflict[];
  warnings: import("./errors.js").Warning[];
}

export type MapReason =
  | "not-normalized"
  | "case-mismatch"
  | "default-via-config-dir"
  | "resolved-target"
  | "foreign";

export interface MapConfigDirResult {
  account: string | null;
  canonical: boolean;
  reason: MapReason | null;
  warnings: import("./errors.js").Warning[];
}

export type MarkerKind = "none" | "account" | "default" | "pool" | "list";

export interface MarkerResult {
  kind: MarkerKind;
  /** The account (the first entry of a list). */
  name: string | null;
  pool: string | null;
  /** The ordered accounts the marker allows; empty for `none` and `pool`. */
  candidates: string[];
}

export interface LaunchEnv {
  set: Record<string, string>;
  unset: string[];
}

export type ResolveSource = "env" | "config-dir" | "marker-file" | "claim" | "default";

export interface ResolveResult {
  account: string | null;
  pool: string | null;
  configDir: string | null;
  canonical: boolean;
  reason: MapReason | null;
  source: ResolveSource;
  matchedPath: string | null;
  exists: boolean;
  aliasOf: string | null;
  /** Ordered accounts the binding allows; `account` is the first. Empty for a pool or a foreign directory. */
  candidates: string[];
  /** False only for CLAUDE_MULTI_ACCOUNT alone naming an account `claude` will not run as (ENV_NOT_APPLIED). */
  applied: boolean;
  /** The effective global config path `claude` will use; null for a pool or a relative CLAUDE_CONFIG_DIR. */
  globalConfig: string | null;
  launchEnv: LaunchEnv | null;
  overriddenBy: string[];
  ignoredMarkers: string[];
  warnings: import("./errors.js").Warning[];
}

export interface CreateResult {
  name: string;
  configDir: string;
}

export interface EnvOptions {
  /** Also unset `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_API_KEY`. */
  clearAuthOverrides?: boolean;
}

export interface EnvResult extends LaunchEnv {
  overriddenBy: string[];
}

/** Where Claude Code looks for a login. */
export type CredentialLocation =
  | { file: string }
  | { keychain: { service: string; account: string } }
  | { credentialManager: Record<string, never> };

export interface Identity {
  email: string | null;
  orgName: string | null;
  orgUuid: string | null;
  organizationType: string | null;
  billingType: string | null;
  userRateLimitTier: string | null;
  organizationRateLimitTier: string | null;
}

export interface Usage {
  /** `fetchedAtMs` as RFC 3339 UTC with milliseconds, or null when absent. */
  fetchedAt: string | null;
  /** The `cachedUsageUtilization` object verbatim. */
  data: Record<string, unknown>;
  /** Per window of `data.utilization`: its utilization number and `resets_at` string (null when absent). */
  windows: Record<string, { utilization: number | null; resetsAt: string | null }>;
  /** True when the cache is older than an hour, from the future, undated, or belongs to another account uuid. */
  stale: boolean;
}

/** A stored OAuth token, read only. The refresh token is never returned. */
export interface Credentials {
  source: "file";
  path: string;
  accessToken: string;
  /** RFC 3339 UTC with milliseconds, or null when the file has none. */
  expiresAt: string | null;
  /** `expiresAt <= now` with the caller's clock. Never refreshed by this library. */
  expired: boolean;
  scopes: string[];
  subscriptionType: string | null;
  rateLimitTier: string | null;
}

export type SessionStatus = "live" | "dead" | "unknown";

export interface LiveSession {
  pid: number;
  sessionId: string | null;
  status: SessionStatus;
}

export interface HandoverResult {
  /** Relative file paths copied, `/` separated, sorted bytewise. */
  copied: string[];
  /** Relative paths of links, FIFOs and devices that were not copied. */
  skipped: string[];
}
