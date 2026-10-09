import nodePath from "node:path";
import type { Platform } from "./types.js";

/** Path operations for one platform flavour, built on node:path posix or win32. */
export interface PathOps {
  readonly sep: string;
  /** Node `join` semantics, with no trailing separator except on a bare root. */
  join(...parts: string[]): string;
  /** Node `normalize` semantics, with no trailing separator except on a bare root. */
  normalize(p: string): string;
  /** Absolute in the spec's sense: `/x` on posix, `<letter>:` plus a separator on win32. */
  isAbsolute(p: string): boolean;
  /** Parent of a normalised absolute path, or null at a root. */
  parent(p: string): string | null;
  /** Splits an absolute path into its root prefix and components. Null root for relative paths. */
  split(p: string): { root: string | null; parts: string[] };
}

const WIN_ROOT = /^([A-Za-z]):[\\/]/;

function stripTrailing(p: string, ops: typeof nodePath.posix, rootLen: (s: string) => number): string {
  let end = p.length;
  const min = rootLen(p);
  while (end > min && (p[end - 1] === ops.sep || (ops === nodePath.win32 && p[end - 1] === "/"))) end--;
  return p.slice(0, end);
}

/** Builds the path operations for a platform input. */
export function pathOps(platform: Platform): PathOps {
  const win = platform === "win32";
  const base = win ? nodePath.win32 : nodePath.posix;
  const rootLen = (s: string): number => (win ? (WIN_ROOT.test(s) ? 3 : 0) : s.startsWith("/") ? 1 : 0);
  const clean = (p: string): string => stripTrailing(base.normalize(p), base, rootLen);
  const isAbsolute = (p: string): boolean => (win ? WIN_ROOT.test(p) : p.startsWith("/"));
  const split = (p: string): { root: string | null; parts: string[] } => {
    if (win) {
      const m = WIN_ROOT.exec(p);
      if (m) return { root: `${m[1]}:\\`, parts: p.slice(3).split(/[\\/]+/).filter((c) => c !== "") };
      return { root: null, parts: p.split(/[\\/]+/).filter((c) => c !== "") };
    }
    if (p.startsWith("/")) return { root: "/", parts: p.split("/").filter((c) => c !== "") };
    return { root: null, parts: p.split("/").filter((c) => c !== "") };
  };
  return {
    sep: base.sep,
    join: (...parts) => clean(base.join(...parts)),
    normalize: clean,
    isAbsolute,
    parent(p) {
      const d = clean(base.dirname(p));
      return d === p || d === "." ? null : d;
    },
    split,
  };
}
