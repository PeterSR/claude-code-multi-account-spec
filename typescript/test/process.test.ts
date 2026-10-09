import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, test } from "node:test";
import { claudePidDomain, fromProcess, NodeProcessTable, parseProcStat, probeFileSymlinks } from "../src/process.js";

let root: string;
before(async () => {
  root = await mkdtemp(join(tmpdir(), "ccma-proc-"));
});
after(async () => {
  await rm(root, { recursive: true, force: true });
});

describe("parseProcStat", () => {
  test("takes field 22 after the last parenthesis, whatever the command name holds", () => {
    const tail = "S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 12345678 20 21";
    assert.equal(parseProcStat(`123 (node) ${tail}`), "12345678");
    assert.equal(parseProcStat(`123 (we ird) (name) ${tail}`), "12345678");
  });

  test("returns null for a short line", () => {
    assert.equal(parseProcStat("123 (node) S 1 2"), null);
  });
});

describe("claudePidDomain", () => {
  const io = {
    readFile: () => "11111111111111111111111111111111\n",
    readlink: () => "pid:[1234567890]",
    hostname: () => "MyHost",
  };
  test("linux is machine id plus pid namespace", () => {
    assert.equal(claudePidDomain("linux", io), "linux:11111111111111111111111111111111:pid:[1234567890]");
  });
  test("windows is the lower-cased host name, other platforms the literal", () => {
    assert.equal(claudePidDomain("win32", io), "linux:myhost");
    assert.equal(claudePidDomain("darwin", io), "linux");
  });
  test("linux uses empty parts when the files cannot be read", () => {
    const broken = {
      ...io,
      readFile: (): string => {
        throw new Error("no machine-id");
      },
    };
    assert.equal(claudePidDomain("linux", { ...broken, readlink: broken.readFile }), "linux::");
  });
});

describe("real process table", { skip: process.platform === "win32" }, () => {
  test("reports this process with a start marker that is stable across calls", async () => {
    const table = new NodeProcessTable();
    const a = await table.lookup(process.pid);
    const b = await table.lookup(process.pid);
    assert.ok(a?.procStart);
    assert.deepEqual(a, b);
  });

  test("on Linux the marker is field 22 of /proc/<pid>/stat", { skip: process.platform !== "linux" }, async () => {
    const info = await new NodeProcessTable().lookup(process.pid);
    assert.equal(info?.procStart, parseProcStat(await readFile("/proc/self/stat", "utf8")));
  });

  test("a pid that does not exist is null", async () => {
    assert.equal(await new NodeProcessTable().lookup(2 ** 22 + 12345), null);
  });
});

describe("probeFileSymlinks", () => {
  test("is true in a writable directory and leaves nothing behind", () => {
    assert.equal(probeFileSymlinks(root), true);
    assert.deepEqual(execFileSync("ls", ["-A", root]).toString().trim(), "");
  });
  test("is false where a link cannot be created", () => {
    assert.equal(probeFileSymlinks(join(root, "missing")), false);
  });
});

describe("fromProcess", () => {
  test("fills inputs from the OS", () => {
    const inputs = fromProcess();
    assert.equal(inputs.cwd, process.cwd());
    assert.equal(inputs.platform, process.platform === "win32" || process.platform === "darwin" ? process.platform : "linux");
    assert.ok(inputs.pidDomain?.startsWith("linux"));
    assert.equal(inputs.canCreateSymlinks, true);
    assert.ok(inputs.processTable);
    assert.ok(inputs.clock?.sleep);
    assert.match(inputs.tempId?.() ?? "", new RegExp(`^${process.pid}\\.[0-9a-f]{12}$`));
    assert.equal(typeof inputs.userName, "string");
  });
  test("overrides win", () => {
    assert.equal(fromProcess({ pidDomain: "x" }).pidDomain, "x");
  });
});
