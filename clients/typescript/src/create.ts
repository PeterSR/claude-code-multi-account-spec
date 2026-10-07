import { atomicWrite } from "./atomic.js";
import { Ctx, isValidName } from "./ctx.js";
import { guarded, MultiAccountError } from "./errors.js";
import type { CreateResult, Inputs } from "./types.js";

/**
 * Creates `$HOME/.claude-<name>` (mode 0700) with a minimal `.multi-account.json` (A2 Create).
 * Fails with INVALID_NAME, RESERVED_NAME or ACCOUNT_EXISTS. Logging in is left to `claude`.
 */
export function create(inputs: Inputs, name: string): Promise<CreateResult> {
  return guarded(() => createImpl(inputs, name));
}

async function createImpl(inputs: Inputs, name: string): Promise<CreateResult> {
  const ctx = new Ctx(inputs);
  if (!isValidName(name)) throw new MultiAccountError("INVALID_NAME", `invalid account name: ${JSON.stringify(name)}`);
  if (ctx.reserved.includes(name)) throw new MultiAccountError("RESERVED_NAME", `reserved account name: ${name}`);
  const dir = ctx.P.join(ctx.home, `.claude-${name}`);
  let exists = true;
  try {
    await ctx.fs.lstat(dir);
  } catch {
    exists = false;
  }
  if (exists) throw new MultiAccountError("ACCOUNT_EXISTS", `account already exists: ${dir}`, dir);
  const now = ctx.requireClock().now();
  await ctx.fs.mkdir(dir, 0o700);
  const createdAt = now.toISOString().replace(/\.\d{3}Z$/, "Z");
  await atomicWrite(ctx, ctx.P.join(dir, ".multi-account.json"), JSON.stringify({ version: 1, createdAt }));
  return { name, configDir: ctx.canonical(name) };
}
