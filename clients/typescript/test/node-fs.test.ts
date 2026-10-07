import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, symlink, writeFile, stat as nodeStat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, test } from "node:test";
import { create, list, NodeFs, resolve } from "../src/index.js";
import type { Inputs } from "../src/index.js";

const fs = new NodeFs();
let root: string;

before(async () => {
  root = await mkdtemp(join(tmpdir(), "ccma-nodefs-"));
});

after(async () => {
  await rm(root, { recursive: true, force: true });
});

describe("NodeFs", () => {
  test("lstat and stat tell links from targets, and dangling links fail stat", async () => {
    const dir = join(root, "links");
    await mkdir(dir);
    await mkdir(join(dir, "real"));
    await symlink(join(dir, "real"), join(dir, "to-real"));
    await symlink(join(dir, "missing"), join(dir, "dangling"));
    assert.equal((await fs.lstat(join(dir, "to-real"))).type, "symlink");
    const viaLink = await fs.stat(join(dir, "to-real"));
    const direct = await fs.stat(join(dir, "real"));
    assert.equal(viaLink.type, "dir");
    assert.equal(`${viaLink.dev}:${viaLink.ino}`, `${direct.dev}:${direct.ino}`);
    assert.equal((await fs.lstat(join(dir, "dangling"))).type, "symlink");
    await assert.rejects(fs.stat(join(dir, "dangling")), { code: "ENOENT" });
    assert.equal(await fs.readlink(join(dir, "to-real")), join(dir, "real"));
    await assert.rejects(fs.readlink(join(dir, "real")), { code: "EINVAL" });
  });

  test("readdir returns names bytewise sorted", async () => {
    const dir = join(root, "sorted");
    await mkdir(dir);
    for (const n of ["b", "B", "a", "_x", "Z"]) await writeFile(join(dir, n), "");
    assert.deepEqual(await fs.readdir(dir), ["B", "Z", "_x", "a", "b"]);
  });

  test("open with NOFOLLOW refuses a symlink with ELOOP but follows without it", async () => {
    const dir = join(root, "nofollow");
    await mkdir(dir);
    await writeFile(join(dir, "target"), "secret");
    await symlink(join(dir, "target"), join(dir, ".credentials.json"));
    await assert.rejects(fs.open(join(dir, ".credentials.json"), ["RDONLY", "NOFOLLOW"]), { code: "ELOOP" });
    const h = await fs.open(join(dir, ".credentials.json"), ["RDONLY"]);
    assert.equal(Buffer.from(await h.read(100)).toString(), "secret");
    await h.close();
  });

  test("exclusive create fails with EEXIST, writes, and rename replaces", async () => {
    const dir = join(root, "excl");
    await mkdir(dir);
    const tmp = join(dir, "f.tmp.1.abc");
    const h = await fs.open(tmp, ["CREAT_EXCL_WRONLY"], 0o600);
    await h.write(Buffer.from("hello"));
    await h.sync();
    await h.close();
    await assert.rejects(fs.open(tmp, ["CREAT_EXCL_WRONLY"], 0o600), { code: "EEXIST" });
    assert.equal((await nodeStat(tmp)).mode & 0o777, 0o600);
    await fs.rename(tmp, join(dir, "f"));
    const r = await fs.open(join(dir, "f"), ["RDONLY"]);
    assert.equal(Buffer.from(await r.read(100)).toString(), "hello");
    await r.close();
  });

  test("mkdir applies the mode, reports EEXIST, and rmdir refuses a non-empty directory", async () => {
    const dir = join(root, "mk");
    await fs.mkdir(dir, 0o700);
    assert.equal((await nodeStat(dir)).mode & 0o777, 0o700);
    await assert.rejects(fs.mkdir(dir, 0o700), { code: "EEXIST" });
    await writeFile(join(dir, "x"), "");
    await assert.rejects(fs.rmdir(dir), { code: "ENOTEMPTY" });
    await fs.unlink(join(dir, "x"));
    await fs.rmdir(dir);
  });

  test("realpath follows links", async () => {
    const dir = join(root, "rp");
    await mkdir(join(dir, "data"), { recursive: true });
    await symlink(join(dir, "data"), join(dir, "link"));
    assert.equal(await fs.realpath(join(dir, "link")), await fs.realpath(join(dir, "data")));
  });
});

describe("library over the real filesystem", () => {
  test("create, list and resolve a relocated account through a link", async () => {
    const home = join(root, "home");
    await mkdir(home);
    const inputs: Inputs = {
      env: {},
      cwd: home,
      home,
      platform: "linux",
      fs,
      clock: { now: () => new Date("2026-10-06T12:00:00Z") },
    };
    const made = await create(inputs, "work");
    assert.equal(made.configDir, join(home, ".claude-work"));
    assert.equal((await nodeStat(made.configDir)).mode & 0o777, 0o700);

    await mkdir(join(root, "elsewhere"));
    await symlink(join(root, "elsewhere"), join(home, ".claude-moved"));
    await symlink(join(root, "nowhere"), join(home, ".claude-gone"));
    const listed = await list(inputs);
    const byName = Object.fromEntries(listed.accounts.map((a) => [a.name, a]));
    assert.equal(byName["work"]?.hasSpecFile, true);
    assert.equal(byName["moved"]?.state, "ok");
    assert.equal(byName["gone"]?.state, "dangling");

    await writeFile(join(home, ".claude-account"), "work\n");
    const r = await resolve(inputs, { ceilingDirs: [root] });
    assert.equal(r.account, "work");
    assert.equal(r.source, "marker-file");
  });
});
