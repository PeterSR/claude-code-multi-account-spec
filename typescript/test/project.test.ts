import assert from "node:assert/strict";
import { test } from "node:test";
import { projectSlug } from "../src/index.js";

test("projectSlug replaces every non-alphanumeric code unit", () => {
  assert.equal(projectSlug("/home/p/my.proj"), "-home-p-my-proj");
  assert.equal(projectSlug("\u{1F600}"), "--");
});

test("projectSlug cuts long paths to 200 characters plus a base 36 hash", () => {
  const cwd = `/${"a".repeat(250)}`;
  const slug = projectSlug(cwd);
  assert.match(slug, /^-a{199}-[0-9a-z]+$/);
  assert.equal(projectSlug(cwd), slug);
  assert.notEqual(projectSlug(`${cwd}b`), slug);
});
