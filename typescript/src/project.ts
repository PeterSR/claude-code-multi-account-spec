import { byteCompare } from "./bytes.js";
import { Ctx } from "./ctx.js";
import { guarded } from "./errors.js";
import type { Inputs } from "./types.js";

const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

/**
 * `projectSlug(cwd)`: the folder name Claude Code uses under `projects/` for a working directory (B4). Every
 * UTF-16 code unit that is not `[A-Za-z0-9]` becomes `-`; a result longer than 200 characters is cut to 200
 * and gets `-` plus the base 36 text of the absolute 32-bit string hash (`h * 31 + c`) of the original.
 * Pure: no account, no filesystem.
 */
export function projectSlug(cwd: string): string {
  const slug = cwd.replace(/[^A-Za-z0-9]/g, "-");
  if (slug.length <= 200) return slug;
  let h = 0;
  for (let i = 0; i < cwd.length; i++) h = (h * 31 + cwd.charCodeAt(i)) | 0;
  return `${slug.slice(0, 200)}-${Math.abs(h).toString(36)}`;
}

/** One conversation of a project. */
export interface ProjectSession {
  id: string;
  /** The transcript's mtime, UTC with three fractional digits. */
  mtime: string;
}

/**
 * `sessionsFor(name, cwd)`: the transcripts of a project, newest first (B4). `projects` and the project folder
 * must be plain directories; only regular `<id>.jsonl` files (never links) with a valid id are listed.
 */
export function sessionsFor(inputs: Inputs, name: string, cwd: string): Promise<{ sessions: ProjectSession[] }> {
  return guarded(async () => {
    const ctx = new Ctx(inputs);
    await ctx.gate(name);
    const { P, fs } = ctx;
    const projects = P.join(ctx.configHome(name), "projects");
    const dir = P.join(projects, projectSlug(cwd));
    const out: { id: string; ms: number }[] = [];
    try {
      if ((await fs.lstat(projects)).type !== "dir" || (await fs.lstat(dir)).type !== "dir") return { sessions: [] };
      for (const n of await fs.readdir(dir)) {
        if (!n.endsWith(".jsonl")) continue;
        const id = n.slice(0, -".jsonl".length);
        if (!SESSION_ID.test(id)) continue;
        try {
          const st = await fs.lstat(P.join(dir, n));
          if (st.type === "file") out.push({ id, ms: Math.floor(st.mtimeMs) });
        } catch {
          /* vanished */
        }
      }
    } catch {
      return { sessions: [] };
    }
    out.sort((a, b) => b.ms - a.ms || byteCompare(a.id, b.id));
    return { sessions: out.map((s) => ({ id: s.id, mtime: new Date(s.ms).toISOString() })) };
  });
}
