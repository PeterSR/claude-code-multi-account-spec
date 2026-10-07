import { decodeUtf8 } from "./bytes.js";
import { isValidName } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import type { Fs } from "./fs.js";
import type { MarkerResult } from "./types.js";

const MAX_BYTES = 1024;
const TRIM = new Set([" ", "\t", "\r", "\v", "\f"]);
const none = (): MarkerResult => ({ kind: "none", name: null, pool: null, candidates: [] });

function trimAscii(s: string): string {
  let a = 0;
  let b = s.length;
  while (a < b && TRIM.has(s[a] as string)) a++;
  while (b > a && TRIM.has(s[b - 1] as string)) b--;
  return s.slice(a, b);
}

/**
 * Parses a `.claude-account` marker file (A4 marker parsing). A missing file, a dangling link or a
 * directory is `none`; anything else that is not a valid single target is MARKER_INVALID.
 */
export function parseMarker(fs: Fs, path: string): Promise<MarkerResult> {
  return guarded(() => parseMarkerImpl(fs, path));
}

async function parseMarkerImpl(fs: Fs, path: string): Promise<MarkerResult> {
  const invalid = (why: string): MultiAccountError => new MultiAccountError("MARKER_INVALID", `${path}: ${why}`, path);
  try {
    await fs.lstat(path);
  } catch {
    return none();
  }
  let type;
  try {
    type = (await fs.stat(path)).type;
  } catch {
    return none();
  }
  if (type === "dir") return none();
  if (type !== "file") throw invalid("not a regular file");

  let bytes: Uint8Array;
  try {
    const h = await fs.open(path, ["RDONLY", "NONBLOCK"]);
    try {
      bytes = await h.read(MAX_BYTES + 1);
    } finally {
      await h.close();
    }
  } catch {
    throw invalid("cannot be read");
  }
  if (bytes.length > MAX_BYTES) throw invalid("longer than 1024 bytes");
  let text: string;
  try {
    text = decodeUtf8(bytes);
  } catch {
    throw invalid("not valid UTF-8");
  }
  if (text.startsWith("﻿")) text = text.slice(1);
  for (let line of text.split("\n")) {
    if (line.endsWith("\r")) line = line.slice(0, -1);
    line = trimAscii(line);
    if (line === "" || line.startsWith("#")) continue;
    if (line.includes(",")) {
      const parts = line.split(",").map(trimAscii);
      if (!parts.every((x) => x === "default" || isValidName(x)) || new Set(parts).size !== parts.length) {
        throw invalid("invalid list");
      }
      return { kind: "list", name: parts[0] as string, pool: null, candidates: parts };
    }
    if (line === "default") return { kind: "default", name: "default", pool: null, candidates: ["default"] };
    if (line.startsWith("@") && isValidName(line.slice(1))) {
      return { kind: "pool", name: null, pool: line.slice(1), candidates: [] };
    }
    if (isValidName(line)) return { kind: "account", name: line, pool: null, candidates: [line] };
    throw invalid("invalid target");
  }
  throw invalid("no target");
}
