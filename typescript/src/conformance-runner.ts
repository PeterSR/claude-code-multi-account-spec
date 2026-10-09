// Conformance runner (conformance/FORMAT.md section 1): one case on stdin, one JSON object on stdout.
// Uses only the fake filesystem, fake process table and fixed clock built from the case.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  canonicalPath,
  create,
  credentialLocations,
  env,
  activate,
  availableAt,
  claim,
  identityFor,
  limits,
  poolMembers,
  projectSlug,
  sessionOfPid,
  sessionsFor,
  specFile,
  unclaim,
  updateSpecFile,
  usageFor,
  adopt,
  available,
  clearLimited,
  credentials,
  FakeFs,
  handoverSession,
  markLimited,
  next,
  nextFrom,
  pick,
  pickFrom,
  slot,
  identity,
  list,
  liveSessions,
  mapConfigDir,
  MultiAccountError,
  parseMarker,
  reservedNames,
  resolve,
  usage,
} from "./index.js";
import type { FakeEntry, Inputs, LimitInput, Platform, ProcessInfo, ProcessTable, ResolveOptions } from "./index.js";

interface Case {
  platform: Platform;
  caseInsensitive: boolean;
  home: string;
  cwd: string;
  env: Record<string, string>;
  options?: ResolveOptions & { canCreateSymlinks?: boolean; userName?: string };
  now: string;
  reserved?: string[] | null;
  fs: Record<string, FakeEntry>;
  processes?: Record<string, { procStart?: string; procStartFt?: string; pidDomain?: string; lookupError?: boolean }>;
  callerPidDomain?: string;
  op: { name: string; args?: Record<string, unknown> };
}

const WRITE_OPS = new Set(["create", "handover_session", "mark_limited", "clear_limited", "adopt", "activate", "update_spec_file", "claim", "unclaim"]);

function readStdin(): string {
  return readFileSync(0, "utf8");
}

function reservedFor(c: Case): readonly string[] {
  if (c.reserved) return c.reserved;
  const root = process.env["CCMA_REPO_ROOT"] ?? process.cwd();
  try {
    const data = JSON.parse(readFileSync(join(root, "spec", "reserved.json"), "utf8")) as { names: { name: string }[] };
    return data.names.map((n) => n.name);
  } catch {
    return reservedNames();
  }
}

async function run(c: Case, inputs: Inputs): Promise<unknown> {
  const a = (c.op.args ?? {}) as Record<string, unknown>;
  const name = a["name"] as string;
  switch (c.op.name) {
    case "canonical_path":
      return { path: canonicalPath(c.home, name, c.platform) };
    case "discover":
      return list(inputs);
    case "resolve":
      return resolve(inputs, c.options ?? {});
    case "map_config_dir":
      return mapConfigDir(inputs, a["value"] as string);
    case "parse_marker":
      return parseMarker(inputs.fs, a["path"] as string);
    case "create":
      return create(inputs, name);
    case "env":
      return env(inputs, name, { clearAuthOverrides: a["clearAuthOverrides"] === true });
    case "credentials":
      return credentials(inputs, name);
    case "credential_locations":
      return { locations: await credentialLocations(inputs, name) };
    case "identity":
      return a["resolve"] === true ? identityFor(inputs, await resolve(inputs, c.options ?? {})) : identity(inputs, name);
    case "usage":
      return a["resolve"] === true ? usageFor(inputs, await resolve(inputs, c.options ?? {})) : usage(inputs, name);
    case "live_sessions":
      return { sessions: await liveSessions(inputs, name) };
    case "handover_session":
      return handoverSession(inputs, a["id"] as string, a["from"] as string, a["to"] as string, {
        overwrite: a["overwrite"] === true,
        force: a["force"] === true,
      });
    case "mark_limited":
      return markLimited(inputs, name, a["entry"] as LimitInput);
    case "clear_limited":
      return clearLimited(inputs, name, a["window"] as string, (a["model"] as string | null | undefined) ?? null);
    case "available":
      return { available: await available(inputs, name, new Date(c.now), { model: (a["model"] as string | undefined) ?? null }) };
    case "pick":
      return { account: await pick(inputs, a["pool"] as string, new Date(c.now), { model: (a["model"] as string | undefined) ?? null }) };
    case "next":
      return {
        account: await next(inputs, a["pool"] as string, a["current"] as string, new Date(c.now), {
          model: (a["model"] as string | undefined) ?? null,
        }),
      };
    case "pick_from":
      return {
        account: await pickFrom(inputs, a["candidates"] as string[], new Date(c.now), { model: (a["model"] as string | undefined) ?? null }),
      };
    case "next_from":
      return {
        account: await nextFrom(inputs, a["candidates"] as string[], a["current"] as string, new Date(c.now), {
          model: (a["model"] as string | undefined) ?? null,
        }),
      };
    case "limits":
      return limits(inputs, name);
    case "available_at":
      return { availableAt: await availableAt(inputs, name, new Date(c.now), { model: (a["model"] as string | undefined) ?? null }) };
    case "pool_members":
      return { members: await poolMembers(inputs, a["pool"] as string) };
    case "session_of_pid":
      return { sessionId: await sessionOfPid(inputs, name, a["pid"] as number) };
    case "project_slug":
      return { slug: projectSlug(a["cwd"] as string) };
    case "sessions_for":
      return sessionsFor(inputs, name, a["cwd"] as string);
    case "spec_file":
      return specFile(inputs, name);
    case "update_spec_file":
      return updateSpecFile(inputs, name, a["patch"] as Record<string, unknown>);
    case "claim":
      return claim(inputs, name, a["dir"] as string);
    case "unclaim":
      return unclaim(inputs, name, a["dir"] as string);
    case "slot":
      return slot(inputs);
    case "adopt":
      return adopt(inputs, name, { force: a["force"] === true });
    case "activate":
      return activate(inputs, name, { force: a["force"] === true });
    default:
      throw new Error(`operation not implemented in this library yet: ${c.op.name}`);
  }
}

async function main(): Promise<void> {
  const c = JSON.parse(readStdin()) as Case;
  const now = new Date(c.now);
  const fs = new FakeFs({
    platform: c.platform,
    caseInsensitive: c.caseInsensitive,
    now,
    entries: c.fs,
    roots: [c.home, c.cwd],
  });
  const procs = c.processes ?? {};
  const processTable: ProcessTable = {
    lookup: async (pid) => {
      const p = procs[String(pid)];
      if (!p) return null;
      const info: ProcessInfo = {};
      if (p.lookupError === true) info.lookupError = true;
      if (p.procStart !== undefined) info.procStart = p.procStart;
      if (p.procStartFt !== undefined) info.procStartFt = p.procStartFt;
      return info;
    },
  };
  let n = 0;
  const inputs: Inputs = {
    env: c.env,
    cwd: c.cwd,
    home: c.home,
    platform: c.platform,
    fs,
    clock: { now: () => now },
    processTable,
    pidDomain: c.callerPidDomain ?? "host-1",
    canCreateSymlinks: c.options?.canCreateSymlinks ?? true,
    reserved: reservedFor(c),
    tempId: () => `1234.${(n++).toString(16).padStart(12, "0")}`,
  };
  if (c.options?.userName !== undefined) inputs.userName = c.options.userName;

  const out: Record<string, unknown> = {};
  try {
    out["result"] = await run(c, inputs);
  } catch (e) {
    if (e instanceof MultiAccountError) out["error"] = { code: e.code, path: e.path, message: e.message };
    else throw e;
  }
  if (WRITE_OPS.has(c.op.name)) out["fs"] = fs.dump();
  process.stdout.write(`${JSON.stringify(out)}\n`);
}

main().catch((e: unknown) => {
  process.stderr.write(`${e instanceof Error ? (e.stack ?? e.message) : String(e)}\n`);
  process.exit(1);
});
