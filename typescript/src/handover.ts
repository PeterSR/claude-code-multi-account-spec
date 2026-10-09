import { byteCompare } from "./bytes.js";
import { Ctx } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import { readSessions, refuseIfBlocked } from "./sessions.js";
import type { HandoverResult, Inputs } from "./types.js";

const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

/** Options of `handoverSession`. `force` overrides sessions of unknown state, never live ones. */
export interface HandoverOptions {
  overwrite?: boolean;
  force?: boolean;
}

/**
 * `handoverSession(id, from, to, {overwrite, force})`: copies a conversation so `claude --resume <id>` works
 * under another account (B4). Copy, never move; `from` is never touched. Only regular files and directories
 * are copied (links, FIFOs and devices are listed in `skipped`). The copy is built under temporary names next
 * to each destination location and swapped in, so a failure leaves the destination as it was. Returns the
 * copied files and the skipped entries, relative to the config home with `/` separators, sorted bytewise.
 */
export function handoverSession(
  inputs: Inputs,
  id: string,
  from: string,
  to: string,
  opts: HandoverOptions = {},
): Promise<HandoverResult> {
  return guarded(() => handover(inputs, id, from, to, opts));
}

async function handover(inputs: Inputs, id: string, from: string, to: string, opts: HandoverOptions): Promise<HandoverResult> {
  const ctx = new Ctx(inputs);
  const { P, fs } = ctx;
  if (typeof id !== "string" || !SESSION_ID.test(id)) {
    throw new MultiAccountError("INVALID_SESSION_ID", `invalid session id: ${JSON.stringify(id)}`);
  }
  await ctx.gate(from);
  await ctx.gate(to);
  if (await ctx.sameAccount(from, to)) throw new MultiAccountError("SAME_ACCOUNT", `${from} and ${to} are the same account`);
  const src = ctx.configHome(from);
  const dst = ctx.configHome(to);

  const at = (root: string, rel: string): string => {
    const p = P.join(root, ...rel.split("/"));
    if (p !== root && !p.startsWith(root + P.sep)) throw new MultiAccountError("INVALID_SESSION_ID", `location escapes the config home: ${rel}`);
    return p;
  };
  const skippedParents = new Set<string>();
  // Classifies a parent directory: plain dir, absent, or bad (a link or a file: never a location).
  const parentKind = async (root: string, rel: string): Promise<"dir" | "absent" | "bad"> => {
    try {
      const t = (await fs.lstat(at(root, rel))).type;
      return t === "dir" ? "dir" : "bad";
    } catch (e) {
      if (e instanceof MultiAccountError) throw e;
      return "absent";
    }
  };
  const slugsOf = async (root: string): Promise<{ plain: Set<string>; bad: Set<string>; projectsBad: boolean }> => {
    const plain = new Set<string>();
    const bad = new Set<string>();
    const k = await parentKind(root, "projects");
    if (k === "bad") return { plain, bad, projectsBad: true };
    if (k === "dir") {
      let names: string[] = [];
      try {
        names = await fs.readdir(at(root, "projects"));
      } catch {
        names = [];
      }
      for (const n of names) ((await parentKind(root, `projects/${n}`)) === "dir" ? plain : bad).add(n);
    }
    return { plain, bad, projectsBad: false };
  };
  const [sf, st] = [await slugsOf(src), await slugsOf(dst)];
  // Only source-side linked parents are reported as skipped; destination ones fail in step 6 when needed.
  if (sf.projectsBad) skippedParents.add("projects");
  for (const n of sf.bad) skippedParents.add(`projects/${n}`);
  const srcFlat: string[] = [];
  const dstFlat: string[] = [];
  for (const d of ["file-history", "session-env", "tasks"]) {
    const sk = await parentKind(src, d);
    const dk = await parentKind(dst, d);
    if (sk === "bad") skippedParents.add(d);
    else srcFlat.push(d);
    if (dk !== "bad") dstFlat.push(d);
  }
  const rels = (slugs: Iterable<string>, projectsOk: boolean, flat: string[]): string[] => {
    const out = new Set<string>();
    if (projectsOk) for (const s of slugs) out.add(`projects/${s}/${id}.jsonl`).add(`projects/${s}/${id}`);
    for (const d of flat) out.add(`${d}/${id}`);
    return [...out];
  };
  const existing = async (root: string, list: string[]): Promise<{ rel: string; type: string }[]> => {
    const found: { rel: string; type: string }[] = [];
    for (const rel of list) {
      try {
        found.push({ rel, type: (await fs.lstat(at(root, rel))).type });
      } catch (e) {
        if (e instanceof MultiAccountError) throw e;
      }
    }
    return found;
  };
  const srcSlugs = [...sf.plain];
  const destSlugs = [...new Set([...sf.plain, ...st.plain])].filter((n) => !st.bad.has(n));
  const locations = (root: string, list: string[]): Promise<{ rel: string; type: string }[]> => existing(root, list);

  const srcLocs = await locations(src, rels(srcSlugs, !sf.projectsBad, srcFlat));
  if (!srcLocs.some((l) => l.type === "file" || l.type === "dir")) {
    throw new MultiAccountError("SESSION_NOT_FOUND", `session ${id} not found in ${from}`);
  }
  refuseIfBlocked(await readSessions(ctx, from), opts.force === true, id);
  for (const { rel } of srcLocs) {
    const parts = rel.split("/");
    const needed = parts[0] === "projects" ? ["projects", `projects/${parts[1]}`] : [parts[0] as string];
    for (const p of needed) {
      if ((await parentKind(dst, p)) === "bad") {
        throw new MultiAccountError("DESTINATION_BLOCKED", `destination parent is not a plain directory: ${p}`, at(dst, p));
      }
    }
  }
  const dstLocs = await locations(dst, rels(destSlugs, !st.projectsBad, dstFlat));
  if (dstLocs.length > 0 && opts.overwrite !== true) {
    throw new MultiAccountError("SESSION_EXISTS", `session ${id} exists in ${to}`);
  }

  const exists = async (p: string): Promise<boolean> => fs.lstat(p).then(() => true, () => false);
  const madeDirs: string[] = [];
  const mkdirs = async (p: string): Promise<void> => {
    if (await exists(p)) return;
    const parent = P.parent(p);
    if (parent !== null) await mkdirs(parent);
    await fs.mkdir(p, 0o700);
    madeDirs.push(p);
  };
  const remove = async (p: string): Promise<void> => {
    const st = await fs.lstat(p);
    if (st.type === "dir") {
      for (const c of await fs.readdir(p)) await remove(P.join(p, c));
      await fs.rmdir(p);
    } else if (st.type === "junction") {
      await fs.rmdir(p);
    } else {
      await fs.unlink(p);
    }
  };

  const copied: string[] = [];
  const skipped: string[] = [...skippedParents];
  const failed = (p: string, e: unknown): MultiAccountError =>
    new MultiAccountError("IO_ERROR", `cannot copy ${p}: ${e instanceof Error ? e.message : String(e)}`, p);

  // Copies one source entry (lstat decides) to `to`, recording the relative path `rel`. Returns whether anything
  // was created at `to`.
  const copyEntry = async (rel: string, sp: string, to: string): Promise<boolean> => {
    let st;
    try {
      st = await fs.lstat(sp);
    } catch (e) {
      throw failed(sp, e);
    }
    if (st.type === "dir") {
      try {
        await fs.mkdir(to, 0o700);
        for (const c of await fs.readdir(sp)) await copyEntry(`${rel}/${c}`, P.join(sp, c), P.join(to, c));
      } catch (e) {
        if (e instanceof MultiAccountError) throw e;
        throw failed(sp, e);
      }
      return true;
    }
    if (st.type !== "file") {
      skipped.push(rel);
      return false;
    }
    try {
      const data = await ctx.readBytes(sp, ["NOFOLLOW"]);
      const h = await fs.open(to, ["CREAT_EXCL_WRONLY"], st.mode);
      try {
        await h.write(data);
        await h.sync();
      } finally {
        await h.close();
      }
    } catch (e) {
      throw failed(sp, e);
    }
    copied.push(rel);
    return true;
  };

  // Build every location under a temporary sibling name first.
  const built: { rel: string; tmp: string; final: string }[] = [];
  const cleanup = async (): Promise<void> => {
    for (const b of built) await remove(b.tmp).catch(() => undefined);
    for (const d of madeDirs.reverse()) await fs.rmdir(d).catch(() => undefined);
  };
  try {
    for (const { rel, type } of srcLocs) {
      if (type !== "file" && type !== "dir") {
        skipped.push(rel);
        continue;
      }
      const final = at(dst, rel);
      const parent = P.parent(final);
      if (parent !== null) await mkdirs(parent);
      const tmp = `${final}.tmp.${ctx.tempId()}`;
      const item = { rel, tmp, final };
      built.push(item);
      if (!(await copyEntry(rel, at(src, rel), tmp))) built.pop();
    }
  } catch (e) {
    await cleanup();
    throw e;
  }

  // Swap in: the old destination is removed only now that every replacement is complete.
  try {
    for (const d of dstLocs) await remove(at(dst, d.rel));
    for (const b of built) await fs.rename(b.tmp, b.final);
  } catch (e) {
    await cleanup();
    throw e;
  }
  return { copied: copied.sort(byteCompare), skipped: [...new Set(skipped)].sort(byteCompare) };
}
