import { execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync, readlinkSync, realpathSync, symlinkSync, unlinkSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { homedir, hostname, userInfo } from "node:os";
import { join } from "node:path";
import { NodeFs } from "./node-fs.js";
import type { Inputs, Platform, ProcessInfo, ProcessTable } from "./types.js";

/**
 * The start marker Claude Code stores as `procStart` on Linux: field 22 (`starttime`) of `/proc/<pid>/stat`
 * as a string. The line is parsed after the last `)` because the command name may contain spaces and
 * parentheses. Returns null when the line has no such field.
 */
export function parseProcStat(stat: string): string | null {
  const rest = stat.slice(stat.lastIndexOf(")") + 1).trim().split(" ");
  // `rest` starts at field 3 (state), so field 22 is index 19.
  const start = rest[19];
  return start === undefined || start === "" ? null : start;
}

interface PidDomainIo {
  readFile(path: string): string;
  readlink(path: string): string;
  hostname(): string;
}

/**
 * The caller's pid domain exactly as Claude Code computes it (SPEC B3): on Linux and WSL
 * `linux:<trim(/etc/machine-id)>:<readlink(/proc/self/ns/pid)>`, on Windows `linux:<lower-cased host name>`,
 * otherwise the literal `linux`. Unreadable Linux parts are empty (`linux::pid:[...]`).
 */
export function claudePidDomain(
  platform: NodeJS.Platform,
  io: PidDomainIo = {
    readFile: (p) => readFileSync(p, "utf8"),
    readlink: (p) => readlinkSync(p),
    hostname,
  },
): string {
  if (platform === "linux") {
    const part = (f: () => string): string => {
      try {
        return f();
      } catch {
        return "";
      }
    };
    return `linux:${part(() => io.readFile("/etc/machine-id").trim())}:${part(() => io.readlink("/proc/self/ns/pid"))}`;
  }
  if (platform === "win32") return `linux:${io.hostname().toLowerCase()}`;
  return "linux";
}

/** Runs a tool. `exit` is its exit code when it ran and failed, `failed` when it could not run or timed out. */
function run(cmd: string, args: string[], env: NodeJS.ProcessEnv): Promise<{ out: string; exit: number; failed: boolean }> {
  return new Promise((resolve) => {
    execFile(cmd, args, { env, timeout: 5000, windowsHide: true }, (err, stdout) => {
      if (!err) return resolve({ out: stdout, exit: 0, failed: false });
      const e = err as { code?: unknown; killed?: boolean };
      resolve({ out: stdout ?? "", exit: typeof e.code === "number" ? e.code : -1, failed: typeof e.code !== "number" || e.killed === true });
    });
  });
}

/**
 * Process table over the real OS, producing the start markers Claude Code records: `procStart` from
 * `/proc/<pid>/stat` on Linux, else the trimmed output of `ps -o lstart= -p <pid>` run with `LC_ALL=C` and
 * `TZ=UTC`; on Windows `procStartFt`, the process creation time as a FILETIME string (best effort through
 * PowerShell; the format was read from Claude Code's code and not run on Windows).
 */
export class NodeProcessTable implements ProcessTable {
  async lookup(pid: number): Promise<ProcessInfo | null> {
    if (process.platform === "linux") {
      try {
        const start = parseProcStat(await readFile(`/proc/${pid}/stat`, "utf8"));
        return start === null ? { lookupError: true } : { procStart: start };
      } catch (e) {
        return (e as { code?: string }).code === "ENOENT" || (e as { code?: string }).code === "ESRCH" ? null : { lookupError: true };
      }
    }
    if (process.platform === "win32") {
      const out = await run(
        "powershell.exe",
        ["-NoProfile", "-NonInteractive", "-Command", `(Get-Process -Id ${pid} -ErrorAction Stop).StartTime.ToFileTime()`],
        process.env,
      );
      const ft = out.out.trim();
      if (/^\d+$/.test(ft)) return { procStartFt: ft };
      return out.failed ? { lookupError: true } : out.exit !== 0 ? null : { lookupError: true };
    }
    const out = await run("ps", ["-o", "lstart=", "-p", String(pid)], { ...process.env, LC_ALL: "C", TZ: "UTC" });
    const s = out.out.trim();
    if (s !== "") return { procStart: s };
    // ps exits 1 with no output for a pid that does not exist; anything else is a failed lookup.
    return !out.failed && out.exit === 1 ? null : { lookupError: true };
  }
}

/**
 * Probes whether this process can create file symlinks in `dir` by creating and removing one (on Windows
 * that needs a privilege or developer mode). Never throws.
 */
export function probeFileSymlinks(dir: string): boolean {
  const probe = join(dir, `.claude-symlink-probe.tmp.${process.pid}.${randomBytes(6).toString("hex")}`);
  try {
    symlinkSync(join(dir, "probe-target"), probe, "file");
  } catch {
    return false;
  }
  try {
    unlinkSync(probe);
  } catch {
    /* a leftover probe link is harmless */
  }
  return true;
}

/**
 * The convenience wrapper that fills `Inputs` from the running process: environment, the physical working
 * directory (`realpath(".")`, never `$PWD`), the home directory, the platform, the real filesystem, clock and
 * process table, Claude Code's own pid domain, `canCreateSymlinks` (probed on Windows, true elsewhere) and the
 * user name from the OS user database. This is the only place the library touches process globals.
 */
export function fromProcess(overrides: Partial<Inputs> = {}): Inputs {
  const platform: Platform = process.platform === "win32" || process.platform === "darwin" ? process.platform : "linux";
  const home = overrides.home ?? homedir();
  const base: Inputs = {
    env: { ...process.env },
    cwd: realpathSync("."),
    home,
    platform,
    fs: new NodeFs({ caseInsensitive: platform !== "linux" }),
    clock: {
      now: () => new Date(),
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    },
    processTable: new NodeProcessTable(),
    pidDomain: claudePidDomain(process.platform),
    canCreateSymlinks: platform === "win32" ? probeFileSymlinks(home) : true,
    lockWaitMs: 2000,
    tempId: () => `${process.pid}.${randomBytes(6).toString("hex")}`,
  };
  try {
    base.userName = userInfo().username;
  } catch {
    /* no passwd entry */
  }
  return { ...base, ...overrides };
}
