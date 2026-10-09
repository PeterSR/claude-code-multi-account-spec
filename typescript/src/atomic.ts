import { encodeUtf8 } from "./bytes.js";
import { Ctx } from "./ctx.js";
import { MultiAccountError } from "./errors.js";
import { fsCode, isLink } from "./fs.js";

const STALE_MS = 10_000;
const RETRY_STEP_MS = 100;

/**
 * Takes a `proper-lockfile` style lock (`mkdir <lock>`). A lock more than 10 s older than the clock is
 * stale: it is removed and taken once more. A held lock is retried a bounded number of times (at most
 * `lockWaitMs`, default 2000, in 100 ms steps) when the clock can sleep; without `clock.sleep`, as in the
 * conformance harness, it is LOCK_BUSY at once. A lost race on the takeover is LOCK_BUSY too.
 */
export async function takeLock(ctx: Ctx, lock: string): Promise<void> {
  const clock = ctx.requireClock();
  const wait = ctx.inputs.lockWaitMs ?? 0;
  const attempts = clock.sleep && wait > 0 ? Math.max(1, Math.ceil(wait / RETRY_STEP_MS)) : 1;
  for (let i = 0; i < attempts; i++) {
    if (i > 0) await (clock.sleep as (ms: number) => Promise<void>)(RETRY_STEP_MS);
    try {
      await ctx.fs.mkdir(lock, 0o700);
      return;
    } catch (e) {
      if (fsCode(e) !== "EEXIST") throw e;
    }
    let mtimeMs: number;
    try {
      mtimeMs = (await ctx.fs.lstat(lock)).mtimeMs;
    } catch (e) {
      if (fsCode(e) === "ENOENT") continue;
      throw e;
    }
    if (clock.now().getTime() - mtimeMs > STALE_MS) {
      try {
        await ctx.fs.rmdir(lock);
      } catch (e) {
        if (fsCode(e) !== "ENOENT") throw e;
      }
      try {
        await ctx.fs.mkdir(lock, 0o700);
        return;
      } catch (e) {
        if (fsCode(e) !== "EEXIST") throw e;
      }
    }
  }
  throw new MultiAccountError("LOCK_BUSY", `lock is held: ${lock}`, lock);
}

/** Runs `fn` holding the lock `<file>.lock`, releasing it afterwards (also on error). */
export async function withFileLock<T>(ctx: Ctx, file: string, fn: () => Promise<T>): Promise<T> {
  return withLock(ctx, `${file}.lock`, fn);
}

/** Runs `fn` holding the lock directory `lock`. */
export async function withLock<T>(ctx: Ctx, lock: string, fn: () => Promise<T>): Promise<T> {
  await takeLock(ctx, lock);
  let result: T;
  try {
    result = await fn();
  } catch (e) {
    await ctx.fs.rmdir(lock).catch(() => undefined);
    throw e;
  }
  await ctx.fs.rmdir(lock);
  return result;
}

/**
 * Writes `text` to `path` per the A3 file safety rules, without locking: one symlink hop is followed
 * and the link kept; a temp file `<target>.tmp.<pid>.<12 hex>` (mode 0600, exclusive) is synced and
 * renamed over the target.
 */
export async function writeFileAtomic(ctx: Ctx, path: string, text: string): Promise<void> {
  let target = path;
  try {
    const st = await ctx.fs.lstat(path);
    if (isLink(st.type)) {
      const t = await ctx.fs.readlink(path);
      target = ctx.P.isAbsolute(t) ? t : ctx.P.join(ctx.P.parent(path) ?? "", t);
    }
  } catch (e) {
    if (fsCode(e) !== "ENOENT") throw e;
  }
  const tmp = `${target}.tmp.${ctx.tempId()}`;
  const h = await ctx.fs.open(tmp, ["CREAT_EXCL_WRONLY"], 0o600);
  try {
    try {
      await h.write(encodeUtf8(text));
      await h.sync();
    } finally {
      await h.close();
    }
    await ctx.fs.rename(tmp, target);
  } catch (e) {
    await ctx.fs.unlink(tmp).catch(() => undefined);
    throw e;
  }
}

/** Locked atomic write: `withFileLock` around `writeFileAtomic`. */
export function atomicWrite(ctx: Ctx, path: string, text: string): Promise<void> {
  return withFileLock(ctx, path, () => writeFileAtomic(ctx, path, text));
}
