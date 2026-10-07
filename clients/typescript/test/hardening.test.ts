import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile, stat } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, test } from "node:test";
import {
  create,
  FakeFs,
  handoverSession,
  markLimited,
  MultiAccountError,
  NodeFs,
  reservedNames,
} from "../src/index.js";
import type { Fs, Inputs } from "../src/index.js";

let root: string;
before(async () => {
  root = await mkdtemp(join(tmpdir(), "ccma-hard-"));
});
after(async () => {
  await rm(root, { recursive: true, force: true });
});

const clock = { now: () => new Date("2026-10-07T12:00:00Z") };

function real(home: string): Inputs {
  return { env: {}, cwd: home, home, platform: "linux", fs: new NodeFs(), clock };
}

describe("reserved names", () => {
  test("the embedded list matches spec/reserved.json", () => {
    const data = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "..", "..", "spec", "reserved.json"), "utf8")) as {
      names: { name: string }[];
    };
    assert.deepEqual([...reservedNames()], data.names.map((n) => n.name));
  });
});

describe("handover on the real filesystem", () => {
  test("a traversing session id is refused and nothing is touched", async () => {
    const home = join(root, "trav");
    await mkdir(join(home, ".claude-a"), { recursive: true });
    await mkdir(join(home, ".claude-b"));
    await writeFile(join(home, ".claude-a", ".credentials.json"), "secret");
    for (const id of ["..", "../.credentials.json", "a/b", "a\\b", ".", "", "/etc"]) {
      await assert.rejects(
        handoverSession(real(home), id, "a", "b", { overwrite: true }),
        (e: unknown) => e instanceof MultiAccountError && e.code === "INVALID_SESSION_ID",
      );
    }
    assert.equal(await readFile(join(home, ".claude-a", ".credentials.json"), "utf8"), "secret");
    await assert.rejects(stat(join(home, ".claude-b", ".credentials.json")));
  });

  test("a FIFO and links are skipped, not opened, and the copy does not hang", { timeout: 20000 }, async () => {
    const home = join(root, "fifo");
    const dir = join(home, ".claude-a", "session-env", "s1");
    await mkdir(dir, { recursive: true });
    await mkdir(join(home, ".claude-b"));
    await writeFile(join(dir, "real.txt"), "data");
    execFileSync("mkfifo", [join(dir, "pipe")]);
    await symlink(join(root, "outside"), join(dir, "link"));
    const r = await handoverSession(real(home), "s1", "a", "b");
    assert.deepEqual(r.copied, ["session-env/s1/real.txt"]);
    assert.deepEqual(r.skipped, ["session-env/s1/link", "session-env/s1/pipe"]);
    assert.equal(await readFile(join(home, ".claude-b", "session-env", "s1", "real.txt"), "utf8"), "data");
  });
});

describe("IO_ERROR", () => {
  test("an unexpected filesystem error is wrapped with its path", async () => {
    const home = join(root, "no-such-home");
    await assert.rejects(create(real(home), "work"), (e: unknown) => {
      assert.ok(e instanceof MultiAccountError);
      assert.equal(e.code, "IO_ERROR");
      assert.ok(e.path?.startsWith(home));
      return true;
    });
  });
});

function fake(entries: Record<string, { type: "dir" | "file"; mtime?: string }> = {}): FakeFs {
  return new FakeFs({
    platform: "linux",
    now: new Date("2026-10-07T12:00:00Z"),
    entries: { "/home/p": { type: "dir" }, "/home/p/.claude-work": { type: "dir" }, ...entries },
    roots: ["/home/p"],
  });
}

const entry = { window: "five_hour", model: null, until: "2026-10-08T00:00:00Z", reason: "r", updatedBy: "t" };

describe("locks", () => {
  test("a held lock is retried a bounded number of times through the clock, then LOCK_BUSY", async () => {
    const fs = fake({ "/home/p/.claude-work/.multi-account-state.json.lock": { type: "dir" } });
    let sleeps = 0;
    const inputs: Inputs = {
      env: {},
      cwd: "/home/p",
      home: "/home/p",
      platform: "linux",
      fs,
      clock: { now: clock.now, sleep: async () => void sleeps++ },
      lockWaitMs: 500,
    };
    await assert.rejects(markLimited(inputs, "work", entry), (e: unknown) => e instanceof MultiAccountError && e.code === "LOCK_BUSY");
    assert.equal(sleeps, 4);
  });

  test("a lock released while waiting is taken", async () => {
    const fs = fake({ "/home/p/.claude-work/.multi-account-state.json.lock": { type: "dir" } });
    const inputs: Inputs = {
      env: {},
      cwd: "/home/p",
      home: "/home/p",
      platform: "linux",
      fs,
      clock: { now: clock.now, sleep: () => fs.rmdir("/home/p/.claude-work/.multi-account-state.json.lock") },
      lockWaitMs: 500,
    };
    const r = await markLimited(inputs, "work", entry);
    assert.equal(r.limits.length, 1);
  });

  test("losing the race when taking over a stale lock is LOCK_BUSY, not a raw EEXIST", async () => {
    const lock = "/home/p/.claude-work/.multi-account-state.json.lock";
    const inner = fake({ [lock]: { type: "dir", mtime: "2026-10-07T11:00:00Z" } });
    let mkdirs = 0;
    const racing: Fs = new Proxy(inner, {
      get(target, prop) {
        if (prop === "mkdir") {
          return async (p: string, m: number): Promise<void> => {
            if (p === lock && ++mkdirs === 2) {
              await target.mkdir(p, m); // someone else wins the second mkdir
            }
            return target.mkdir(p, m);
          };
        }
        const v = Reflect.get(target, prop, target) as unknown;
        return typeof v === "function" ? (v as (...a: unknown[]) => unknown).bind(target) : v;
      },
    });
    const inputs: Inputs = { env: {}, cwd: "/home/p", home: "/home/p", platform: "linux", fs: racing, clock };
    await assert.rejects(markLimited(inputs, "work", entry), (e: unknown) => e instanceof MultiAccountError && e.code === "LOCK_BUSY");
  });
});
