# claude-code-multi-account-spec (draft v0.2.3)

A recommended way to **store** several Claude Code accounts on one machine and to **address** them,
so that switchers, launchers, status lines and shell hooks written by different people agree on
where an account lives and which one applies. Libraries in Go, TypeScript and Python implement it,
held to identical behaviour by a shared
conformance suite.

It is a standard plus libraries, not a tool. There is no CLI, and no config folder of its own:
everything the spec defines lives either in an account's own directory or in the directory being
worked in, so it reads as part of Claude Code rather than as something installed next to it.

The spec has two parts. **Part A (storage and addressing)** is normative and is what "conforming"
means. **Part B (building blocks)** is optional helpers for tool builders. Each block stands alone,
and a tool may use any, all or none of them.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

This document is sufficient on its own: the conformance suite (`conformance/`) only pins the same
behaviour down as data. Sharing config between accounts (CLAUDE.md, skills, settings, plugins) is
out of scope for this version.

## Names used by the spec

Everything is namespaced under "multi account", a term Claude Code is unlikely to adopt for its own
files or variables.

| Kind | Name |
|---|---|
| Account directory | `~/.claude-<name>` |
| Env var selecting an account | `CLAUDE_MULTI_ACCOUNT` |
| Env var saying who set the selection | `CLAUDE_MULTI_ACCOUNT_SOURCE` |
| Directory marker file | `.claude-account` |
| Spec file inside an account | `.multi-account.json` |
| Volatile state inside an account (Part B) | `.multi-account-state.json` |
| Slot lock (Part B, B7) | `~/.claude-slot.lock` |

---

# Part A: storage and addressing (normative)

## A1. Model

An **account** is one Claude Code config directory, and therefore one login. Claude Code computes
its **config home** as

```
(CLAUDE_CONFIG_DIR ?? join(homedir(), ".claude")).normalize("NFC")
```

taking the variable verbatim: no `~` expansion, no trimming, no trailing separator removal, no
realpath. Using account X means running `claude` with `CLAUDE_CONFIG_DIR` set to X's directory, or
unset for `default` (A2). `claude` reads only `CLAUDE_CONFIG_DIR`. It never reads
`CLAUDE_MULTI_ACCOUNT`, which exists for tools.

Most of what Claude Code keeps follows the config home: `.credentials.json`, `settings.json`,
`projects/`, `sessions/`, `file-history/`, `session-env/`, `tasks/`, `plans/`, plugins, skills. The
exceptions a conforming tool MUST know about:

- **Global config file.** For `default` it is `$HOME/.claude.json`, outside the config home. For
  any other account it is `<config home>/.claude.json`. The name is `.claude<suffix>.json`, where
  the suffix is `-custom-oauth` when `CLAUDE_CODE_CUSTOM_OAUTH_URL` is set, else empty. A legacy
  `<config home>/.config.json`, if present, takes precedence over it. Claude Code tests the legacy
  file with `existsSync`, so a directory would count; this spec requires a regular file and accepts
  the difference. When `CLAUDE_CONFIG_DIR` is set, Claude Code uses
  `join(CLAUDE_CONFIG_DIR, ".claude<suffix>.json")` whatever the directory is, so
  `CLAUDE_CONFIG_DIR=$HOME/.claude` uses `~/.claude/.claude.json`, not `~/.claude.json`. The
  `globalConfig` field of a resolution (A4) reports the file that applies.
- **Credential store.** On Linux the login is always `<config home>/.credentials.json`. On macOS it
  is a keychain item (A2), with `.credentials.json` as a fallback. On Windows it is
  `.credentials.json` unless Claude Code is using Windows Credential Manager
  (`CLAUDE_CODE_FORCE_WINDOWS_CREDMAN=1`, or the GrowthBook flag `tengu_windows_credman` cached in
  the global config). `CLAUDE_SECURESTORAGE_CONFIG_DIR` (undocumented, used for teammates) moves
  the credential store elsewhere and is inherited by child processes. When it is defined, even as
  the empty string, Claude Code uses it (an empty value means `~/.claude`), so every account then
  reads the default login. The spec does not use it, and reports it as an override.
- **Paths hard-coded to `homedir()/.claude`** regardless of `CLAUDE_CONFIG_DIR`:
  `.device-keys.json`, `state/settings-review.json`, `state/unattended-serving-consent.json`,
  `state/served-calls`, `bridge-spawn/`. With `CLAUDE_CONFIG_DIR` set, IDE lockfile scanning also
  looks in `~/.claude/ide`. These are shared by every account.
- **Variables and settings that replace the login entirely:** `CLAUDE_CODE_OAUTH_TOKEN`,
  `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
  `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_PROFILE` (a federation profile read from
  `ANTHROPIC_CONFIG_DIR`, default `$XDG_CONFIG_HOME/anthropic` or `~/.config/anthropic`), an `env`
  block in the account's `settings.json` setting any of those, and an `apiKeyHelper` setting. When
  one applies, the account's directory still holds history and settings but not the identity that
  is billed. A4 reports these as `overriddenBy`. Project settings (`.claude/settings.json` in the
  working tree) and managed settings can replace the login too, and are out of scope for
  `overriddenBy`.

Conforming tools MUST NOT copy or rewrite credentials between accounts in order to switch.

## A2. Storage

| Account | Config dir | Global config file |
|---|---|---|
| `default` | `$HOME/.claude` | `$HOME/.claude.json` (Claude Code's asymmetry, not ours) |
| `<name>` | `$HOME/.claude-<name>` | `$HOME/.claude-<name>/.claude.json` |

### Names

- **Name to path is a pure function.** No registry, no lookup. Any tool can address account `work`
  as `$HOME/.claude-work` with zero configuration.
- **Grammar:** `^[a-z0-9][a-z0-9_-]{0,31}$`, matched as a whole string (no trailing newline
  allowance). Lowercase only, so names behave the same on case-insensitive filesystems. A pool name
  has the same grammar.
- **Reserved names** are listed in `spec/reserved.json`, so every implementation reads the same
  data. `default` is reserved because it names `~/.claude`; `account` because `~/.claude-account`
  is also where a marker file in `$HOME` lives (A4); the rest are known non-account siblings left
  by other tools. A reserved name blocks **creation** only. A directory that already exists under a
  name reserved later is still discovered, with a `RESERVED_NAME` warning, and resolves with that
  warning too.
- **Case folding** where this spec compares paths case-insensitively (case-insensitive filesystems
  and Windows) is ASCII-only: `A-Z` map to `a-z`, every other character compares exactly. Names are
  ASCII, so only the home part of a path can differ in non-ASCII case, which is not folded.

### Canonical path

The canonical config dir of account `<name>` is exactly

```
path.join(home, ".claude-" + name).normalize("NFC")
```

with Node's `path.join` semantics for the platform (`path.posix` or `path.win32`), so duplicate
and trailing separators are collapsed and `.` and `..` are resolved lexically. `home` is the `home`
input to the library (A4). When the caller does not supply it, it defaults to Node's
`os.homedir()` rules: `$HOME` if set and non-empty, else the password database on POSIX;
`%USERPROFILE%` on Windows. Drive-letter case is kept as given. `\\?\` prefixes are never produced.
A relative path is never absolute and never matches an account. `canonical_path` is a pure
function: it never touches the filesystem and does not apply reservation. `canonical_path("default")`
is `$HOME/.claude`.

**Unicode version.** NFC is Unicode 16.0, the version the Go and TypeScript runtimes use. A runtime
with an older table (for example Python before 3.14) normalises characters added in 16.0
differently, so an implementation MUST bundle its own Unicode 16.0 NFC tables and use them
whatever the runtime provides. Checking the runtime version, or warning about it, does not make an
implementation conformant. The conformance NFC cases only use characters stable since Unicode 6.0, so they pass on
older runtimes and cannot detect the difference. That is a known limit of the suite.

Symlinks are never resolved. On macOS Claude Code names the keychain item
`Claude Code<oauth suffix>-credentials-<first 8 hex of sha256(config home)>` when
`CLAUDE_CONFIG_DIR` is set, so `~/.claude-work/` and `~/.claude-work` are two different logins.
A link path keeps its login when the data behind it moves.

**`default` is launched with `CLAUDE_CONFIG_DIR` unset, never set to `$HOME/.claude`.** Only the
unset form uses the unsuffixed keychain item `Claude Code<oauth suffix>-credentials`, and only the
unset form reads `$HOME/.claude.json`. `CLAUDE_CONFIG_DIR=$HOME/.claude` on any OS moves the global
config to `~/.claude/.claude.json`, and on macOS it also selects a hashed keychain item, so it looks
like a logged-out account.

### Discovery

Discovery lists the entries of `home` with `readdir` and considers those named `.claude-<name>`
where `<name>` matches the grammar **exactly, with exact case**. `resolve()` and `list()` MUST
both go through this readdir check, so that on a case-insensitive filesystem `.claude-Work` is not
found as `work` by one and rejected by the other. Entries that do not match are ignored silently.

Per entry, after `lstat` and `stat`:

| Entry | Result |
|---|---|
| Directory, or link to a directory | Account exists, `state: "ok"` |
| Link whose target is missing or cannot be resolved (unmounted drive, deleted target, loop, more than 40 hops) | Listed with `state: "dangling"`; addressing it is `ACCOUNT_UNAVAILABLE` |
| Regular file, or link to a non-directory | Not an account; warning `NOT_A_DIRECTORY` |
| Unreadable (`EACCES`) | Listed with `state: "unreadable"`; addressing it is `ACCOUNT_UNAVAILABLE` |

An existing directory needs no marker inside it: an empty `~/.claude-work` is an account, ready
for `claude` to log in. This adopts existing directories with no migration. `default` always
exists and is always listed with `state: "ok"`, even when `~/.claude` is missing.

`list()` returns `{accounts, conflicts, warnings}`. `accounts[0]` is `default`, then the discovered
accounts sorted bytewise by name. Each account is

```
{ name, configDir, state, hasSpecFile, hasGlobalConfig, aliasOf, specError, warnings }
```

- `hasSpecFile`: `.multi-account.json` is a regular file (after following links).
- `hasGlobalConfig`: the effective global config file (A1) exists as a regular file. Both `has*`
  are false when `state` is not `ok`.
- `aliasOf`: the alias representative's name, or null (below).
- `specError`: null, or `{code: "SPEC_FILE_INVALID", path}` (A3). The account is otherwise listed
  normally.
- `warnings`: account-level, `RESERVED_NAME` for a reserved name that exists (never for `default`).
- Top-level `warnings` holds `NOT_A_DIRECTORY` entries `{code, path}`.
- `conflicts`: claim conflicts (A4 step 2). Each is `{path, accounts}`, sorted by `path`.

### Create

`create(name)` makes `$HOME/.claude-<name>` with mode 0700 and writes a minimal
`.multi-account.json` containing exactly `{"version": 1, "createdAt": "<now>"}` (A3). It fails with
`INVALID_NAME`, `RESERVED_NAME` or `ACCOUNT_EXISTS`, in that order. Any existing entry at the path
blocks it, including a dangling link, and on a case-insensitive filesystem a differently cased
entry. Logging in is left to `claude` itself.

### Relocation

An account dir MAY be a symlink (a directory junction on Windows) to wherever the data actually
lives. Tools address it by the link path and never the target. The filesystem is the only
indirection the spec allows. A junction is a reparse point with tag `IO_REPARSE_TAG_MOUNT_POINT`;
other reparse points (such as OneDrive placeholders) are not junctions.

- **Link the directory, never files inside it.** Claude Code opens `.credentials.json` with
  `O_NOFOLLOW` and treats a link there as unreadable. A link on a parent directory is fine.
- **`.claude.json` MAY be a link, one hop only.** Claude Code writes it through a symlink by
  reading the link once and replacing the target atomically; a chain of links would have its
  middle link replaced by a regular file.
- **Aliases.** Two account paths that resolve to the same directory (same device and inode) are
  one account under several names. An alias group is the set of `ok` accounts with one identity.
  Its **representative** is the first named account in name order. `default` never represents a
  group that contains a named account. Every member other than the representative, `default`
  included, carries `aliasOf: <representative>`; the representative has `aliasOf: null`. Claims,
  claim conflicts, pool membership (B6) and the `resolved-target` mapping row (A4) all use the
  representative, so an account's own claims bind to its stable name and not to `default`, which
  moves when the slot is switched (B7). A path whose identity cannot be determined is never equal
  to another path, so it never forms an alias.

## A3. The account's spec file

An account MAY contain `.multi-account.json`, which Claude Code ignores. `default` MAY have one at
`~/.claude/.multi-account.json`.

```json
{
  "version": 1,
  "label": "Personal",
  "createdAt": "2026-09-25T05:30:00Z",
  "directories": ["~/dev/personal"],
  "pool": "team",
  "priority": 0
}
```

- `version` MUST be `1`. `label` is free text. `createdAt` is RFC 3339 in UTC.
- `directories` are the account's **claims** (A4). Each entry is an absolute path (on Windows a
  drive letter followed by a separator; `\x` and `C:x` are not absolute) or starts with `~/`
  (also `~\` on Windows), expanded against `home`; a bare `~/` is `home`. `~user`, a bare `~` and
  relative paths are invalid.
- `pool` and `priority` are Part B (B6). `priority`, if present, MUST be a number whose value is an
  integer between -(2^53-1) and 2^53-1 inclusive (`2.0` is fine, `1.5`, `1e400` and strings are
  not).
- Account identity (email, org, plan) is never stored here; it is read live from Claude Code's
  own files.
- Unknown keys are preserved on write, so Part B and other tools can extend the file.
- The file is read as strict UTF-8 JSON, nested at most 100 levels deep (the top-level object is
  level 1). A spec file that is absent has no claims. A spec file that is present and is not a
  regular file (after following links; a directory, a dangling link, an unreadable file, a link
  loop), is not valid UTF-8 JSON, is not an object, has `version` other than `1`, has an invalid
  `directories` entry or an invalid `priority`, or is nested too deeply is **invalid**. Addressing
  that would need to consult it fails with `SPEC_FILE_INVALID` naming the file; `list()` reports
  the account with the error. An invalid spec file is never silently skipped, because skipping it
  can silently change which account a directory resolves to.
- Spec files are read lazily: A4 step 2 loads every account's spec file the first time the walk
  needs claims, in order `default` then names, over `ok` accounts, and the first invalid file
  fails. Env, config-dir and marker bindings never read them. B6 reads all of them.
- Writes follow the file safety rules (below).

### Reading and editing the spec file

Tools should not reimplement the validation and the safe write above. Four operations do it. All
apply the account gate (A2; `default` is allowed) and work on the account's own file, so for an alias
group the file is the same whichever name is used.

- `specFile(name)` returns the validated object verbatim (unknown keys included), `null` if the file
  is absent, and fails with `SPEC_FILE_INVALID` if it is invalid.
- `updateSpecFile(name, patch)` merges the top-level keys of `patch` (an object) into the file: a key
  with a value sets it, a `null` value removes the key. It runs under the file safety rules, starts
  from `{"version": 1}` when there is no file, preserves unknown keys, and returns the new object.
  It refuses with `SPEC_FILE_INVALID` if the existing file is invalid, and with `INVALID_ENTRY` if the
  merged object would be invalid by the rules above (a bad `version`, `priority` or `directories`
  entry, too deep, a non-object patch); in both cases nothing is written. It never writes something
  `specFile` would then reject.
- `claim(name, dir)` adds a directory to the account's `directories`. `dir` is an absolute path or
  starts with `~/` (anything else is `INVALID_ENTRY`); it is lexically normalised. It is stored as
  `~/<rest>` when it is at or below `home` (`~/` for `home` itself, with `/` separators even on
  Windows) and as the absolute path otherwise. If another account (counting an alias group once)
  already claims the same directory, it fails with `CLAIM_CONFLICT` (path: the normalised
  directory) and writes nothing; directories are compared by identity when they exist, else by
  normalised path (with the case folding of the filesystem). An invalid spec file in another
  account is `SPEC_FILE_INVALID`. If the account already claims the directory (by the same
  comparison) nothing is written. The result is `{directories}`, the account's list afterwards.
- `unclaim(name, dir)` removes every entry that is the same directory by that comparison, writes only
  if something was removed, never creates a file, and returns `{directories}`.

### File safety rules (A3, B5, B6, B7)

Every file the spec defines is written like this:

1. Take a lock directory `<file>.lock` using the layout `proper-lockfile` uses (which Claude Code
   uses): `mkdir <file>.lock`; a lock whose mtime is more than 10 s old is stale and may be taken
   over by removing it and trying `mkdir` once more. Read, modify and write under the lock, then
   remove the lock, also on error. The lock is named after the path as the spec names it (for
   example `<account>/.multi-account-state.json.lock`), never after a link target, so every
   conforming tool locks the same name for the same file. A tool that resolves links first (such
   as `proper-lockfile` itself) does not exclude us on a symlinked file. The spec does not
   prescribe a retry policy: an implementation MAY retry while the lock is held, but MUST bound
   the retries (by count or time), and giving up is the error `LOCK_BUSY`. A lost race when taking
   over a stale lock is also `LOCK_BUSY`, never a raw `EEXIST`. Release removes the lock
   unconditionally, so an operation that outlives the stale window can remove a lock someone else
   took over; the operations here are short and this is accepted.
2. If the path is a symlink, read it once and write to its target (one hop), as Claude Code does.
   Never replace the link itself. A link whose target is missing counts as an absent file and is
   written through.
3. Write a temp file in the same directory, named `<file>.tmp.<pid>.<12 random hex>`, opened with
   `O_CREAT|O_EXCL`, mode 0600. `fsync`, then rename over the target with replace semantics
   (`rename(2)`, `os.replace`, not Python's `os.rename`, which fails on Windows when the target
   exists). The temp file is removed on error.
4. Directories the spec creates are mode 0700.

Any unexpected filesystem error (one the spec does not name) surfaces as `IO_ERROR` with the path,
never as a raw platform error.

## A4. Addressing

`resolve(inputs, options)` decides which account applies. Libraries MUST take everything as
explicit inputs and never read process globals on their own; the convenience wrapper that fills
them from the process is separate.

- **Inputs:** `env` (map), `cwd` (absolute path), `home`, `platform` (`linux`, `darwin`,
  `win32`).
- **Options:** `trustRepoMarkers` (default `false`), `ignoreHookEnv` (default `false`),
  `ceilingDirs` (default none). `ignoreHookEnv` is for the shell hook that set the variables
  itself. A status line or any tool running inside a `claude` that was started from such a shell
  MUST NOT set it, because it would ignore the `CLAUDE_CONFIG_DIR` that `claude` obeys.

### Step 0: normalise env

For each of `CLAUDE_CONFIG_DIR`, `CLAUDE_MULTI_ACCOUNT`, `CLAUDE_MULTI_ACCOUNT_SOURCE`, in that
order, a value that is the empty string is treated as unset, with one `EMPTY_ENV` warning per
variable. (Claude Code would use `""` as a relative config home; nothing conforming produces that.)
No other variable gets this treatment: the login-override variables (below) count as set only when
non-empty, without a warning, except `CLAUDE_SECURESTORAGE_CONFIG_DIR`, which counts when defined
(A1). If `ignoreHookEnv` is set and `CLAUDE_MULTI_ACCOUNT_SOURCE=hook`, both `CLAUDE_MULTI_ACCOUNT`
and `CLAUDE_CONFIG_DIR` are treated as unset, without a warning. This lets a shell hook recompute the
binding on `cd` without being stuck on its own earlier export.

### Step 1: env

`CLAUDE_CONFIG_DIR` is what `claude` actually obeys, so it is the source of truth. Checks run in
this order.

1. A `CLAUDE_MULTI_ACCOUNT` that is set and fails the grammar is `INVALID_NAME`, even when
   `CLAUDE_CONFIG_DIR` is set.
2. Map `CLAUDE_CONFIG_DIR`, if set, to an account (table below).
3. If both are set: they agree when the mapped account is the same account as the named one (the
   same name, or two members of one alias group). If they do not agree, then when the named account
   is not `default` and `CLAUDE_CONFIG_DIR`, normalised as in row 2 of the table, equals that
   name's canonical path, the answer is the account gate result for that name (`ACCOUNT_NOT_FOUND`
   or `ACCOUNT_UNAVAILABLE`), because the variables agree and the account is the problem. Otherwise
   it is `ENV_CONFLICT` (a mapping to `null` never agrees). When they agree the result is the
   mapping (`source: "config-dir"`).
4. If only `CLAUDE_CONFIG_DIR` is set, the mapping is the result (`source: "config-dir"`).
5. If only `CLAUDE_MULTI_ACCOUNT` is set, it names the account (`source: "env"`); an undiscovered
   one is `ACCOUNT_NOT_FOUND` and a dangling or unreadable one `ACCOUNT_UNAVAILABLE`. `claude`
   itself ignores this variable, so with `CLAUDE_CONFIG_DIR` unset it runs as `default`. When the
   named account is `default` or in `default`'s alias group, the result is `applied: true`.
   Otherwise the answer depends on context. If `env.CLAUDECODE` is exactly `"1"` (the process is
   inside `claude`, which sets it for its children), the selection was never applied and the
   result is `ENV_CONFLICT`. Otherwise the result is that account with `applied: false` and the
   warning `ENV_NOT_APPLIED`, so a reporter can show "work (not applied)" and a launcher knows it
   must apply `launchEnv`. A launcher that is told which account to use calls `env(name)` and does
   not `resolve()`: inside a `claude` started from the user's shell (for example from its Bash tool)
   a stale `CLAUDE_MULTI_ACCOUNT` would otherwise give `ENV_CONFLICT`.

Mapping a `CLAUDE_CONFIG_DIR` value `v`, first match wins. Rows 1 to 3 range over discovered named
accounts with state `ok`; rows 4 and 5 add `default`, and row 5 tries named accounts in name order
before `default`. A relative `v` matches no row and is `foreign`.

| Condition | `account` | `canonical` | `reason` |
|---|---|---|---|
| `v` equals the canonical path of a discovered account (compared as given: on macOS Claude Code hashes the NFC form, but on Linux the NFD spelling really is another directory, so the raw value is what is compared) | that name | `true` | `null` |
| `v` lexically normalised (absolute, separators collapsed, no trailing separator, NFC) equals one | that name | `false` | `not-normalized` |
| Same, but only case-insensitively (ASCII fold), on a case-insensitive filesystem | that name | `false` | `case-mismatch` |
| `v` normalised equals `$HOME/.claude` (the directory need not exist) | `default` | `false` | `default-via-config-dir` |
| `realpath(v)` equals `realpath` of an account's config home | that name | `false` | `resolved-target` |
| Otherwise | `null` | `false` | `foreign` |

Every non-canonical result carries the warning `NON_CANONICAL_CONFIG_DIR`: on macOS it is a
different login than the canonical path, and `default-via-config-dir` also uses a different global
config file. A foreign directory is reported, not rejected.

### Step 2: directory binding

Walk from `cwd` upward to the filesystem root, stopping early after any directory in
`ceilingDirs` (entries are lexically normalised and compared with the case folding of the
filesystem). `cwd` is used as given, after lexical normalisation; the process wrapper fills it
from the physical working directory (`realpath(".")`), never from `$PWD`. At each level, in order:

1. **Marker file.** If `<dir>/.claude-account` is a marker (parsing below), it binds
   (`source: "marker-file"`).
2. **Claims.** If any account claims `<dir>`, it binds (`source: "claim"`). Directories are
   compared by identity (device and inode after following links), so `~/dev` and `/home/p/dev`,
   case variants, and links to the same directory all match. Claims that do not exist are ignored.
   Only the representative of an alias group claims. Two accounts claiming the same directory is
   `CLAIM_CONFLICT` (path: the level's directory), raised only when the walk reaches that level;
   `list()` reports all conflicts.

The nearest level wins; at the same level the marker file wins. A directory the walk cannot read
counts as having no marker and is not an error. A binding never falls back: an invalid marker, a
missing account or a conflict is the answer, not a reason to look further up.

**Marker parsing.** The entry is followed if it is a link. A dangling link counts as no marker. A
directory is ignored (it may be an unrelated `~/.claude-account` account dir from before `account`
was reserved). Any other non-regular file (FIFO, device) is `MARKER_INVALID` and is not read. A
regular file is opened with `O_NONBLOCK`, and a file that cannot be opened is `MARKER_INVALID`. At
most 1024 bytes are read; a longer file is `MARKER_INVALID`. Content MUST be valid UTF-8, else
`MARKER_INVALID`. A leading BOM is stripped, lines split on `\n` with a trailing `\r` removed,
each line is trimmed of ASCII space, tab, CR, VT and FF, and blank lines and lines starting with
`#` are skipped. The first remaining line is the target and later lines are ignored. The target is
one of:

- a valid account name, or `default` (to override a claim or marker further up);
- `@<pool>` (below);
- an **ordered list** `name, name, ...`: two or more entries separated by commas, optional spaces
  around the commas (ASCII space or tab), each entry a valid name or `default`, no duplicates, no `@pool`. The entries
  are in order of preference. This is how a project says "use `work` first, then `personal`",
  which pools (B6) cannot express because priority belongs to the account, not to the project.

No remaining line, or any other target (an empty entry, a trailing comment, a bad entry), is
`MARKER_INVALID` with the marker's path. A marker in a list binds the first entry as the account
(`account`, `launchEnv`), reports the whole list as `candidates`, and requires every entry to
exist: a missing first entry is `ACCOUNT_NOT_FOUND` with the marker path, a dangling or unreadable
one `ACCOUNT_UNAVAILABLE`. Only the first entry must exist. A later entry that is undiscovered,
dangling or unreadable does not fail resolution (an unmounted drive behind the second account must
not break the first): `candidates` still lists it as written, and the warning
`CANDIDATE_UNAVAILABLE` (path: that entry's account path) is added per such entry. Syntax errors in
any entry stay `MARKER_INVALID`. Claims are always a single account. Choosing among
candidates is the caller's job (B6 `pick_from`, `next_from`).

**Markers in git working trees.** A cloned repository can contain a `.claude-account` and so pick
which account, and therefore which org and billing, runs its code. Unless `trustRepoMarkers` is
set, a marker at or below a directory that contains `.git` (file or directory) is ignored. A level
counts as in a working tree when it or any ancestor level within the walk (the ceiling cuts the
lookahead) has `.git`. Ignored markers are listed in `ignoredMarkers` (nearest first, with one
`MARKER_IGNORED_IN_REPO` warning each), are not read or parsed, and a directory marker is skipped
silently, not listed. Claims are not affected: they are the way to bind repositories, because they
live with the account, not with the code. A `$HOME` that is itself a git working tree (some
dotfile setups) therefore disables every marker below it; use claims or `trustRepoMarkers`.

**Pools.** A marker target of `@<pool>` (pool name grammar is the account grammar) is a valid
binding in Part A. A claim cannot carry a pool, since claims are paths owned by an account. The
result has `account: null`, `pool: "<pool>"`, `configDir: null`, `canonical: false`,
`reason: null`, `exists: false`, `aliasOf: null`, `launchEnv: null`, `globalConfig: null`,
`candidates: []`, `applied: true`, `source: "marker-file"` and `matchedPath` the marker. Choosing a
member is Part B (B6); a Part A-only tool reports the pool rather than failing.

A binding to a missing account is `ACCOUNT_NOT_FOUND` naming the binding's path (the marker file,
or the claimed directory), never a fallback: silently running as the wrong account is the failure
this spec exists to prevent.

### Step 3: default

Nothing matched: `account: "default"`, `source: "default"`. When `default` is in an alias group
with a named account (the slot, B7) it carries `aliasOf: <that account>`.

### Result

```json
{
  "account": "personal",
  "pool": null,
  "configDir": "/home/user/.claude-personal",
  "canonical": true,
  "reason": null,
  "source": "marker-file",
  "matchedPath": "/home/user/dev/personal/.claude-account",
  "exists": true,
  "aliasOf": null,
  "candidates": ["personal"],
  "applied": true,
  "globalConfig": "/home/user/.claude-personal/.claude.json",
  "launchEnv": {
    "set": { "CLAUDE_CONFIG_DIR": "/home/user/.claude-personal", "CLAUDE_MULTI_ACCOUNT": "personal" },
    "unset": ["CLAUDE_MULTI_ACCOUNT_SOURCE", "CLAUDE_SECURESTORAGE_CONFIG_DIR"]
  },
  "overriddenBy": [],
  "ignoredMarkers": [],
  "warnings": []
}
```

- `configDir` is the account's canonical path; for `default` it is `$HOME/.claude` and is
  informational only. **Launch with `launchEnv`, never with `CLAUDE_CONFIG_DIR=$configDir`.**
  For `source: "config-dir"`, `configDir` is the variable's value as given.
- `matchedPath` is the marker file for `marker-file`, the walked directory (not the claim string)
  for `claim`, and `null` for `env`, `config-dir` and `default`.
- `exists` is whether `configDir` is a directory now (a launcher may point `CLAUDE_CONFIG_DIR` at a
  directory `claude` will create). It is `false` for a pool and, for `source: "config-dir"`, when
  the value is relative, missing or not a directory; it is `true` otherwise.
- `candidates` is the ordered list of accounts the binding allows: the entries of a marker list;
  `[account]` for a single-name binding, a claim, env, config-dir and default; `[]` for a pool or a
  foreign directory. `account` is always the first entry.
- `applied` is `false` only for the `ENV_NOT_APPLIED` result above.
- `globalConfig` is the effective global config path (A1) for the config home that `claude` will
  use: the account's for every source except `config-dir`, where it is derived from the value as
  given. It is `null` for a pool and for a relative `CLAUDE_CONFIG_DIR`.
- `launchEnv` is the B1 delta for `account`; `null` for a pool or a foreign directory. It is
  always complete: a hook exports all of it and never `CLAUDE_MULTI_ACCOUNT` alone.
- `overriddenBy` lists, in this fixed order, those that apply: `CLAUDE_CODE_OAUTH_TOKEN`,
  `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
  `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_PROFILE`, `CLAUDE_SECURESTORAGE_CONFIG_DIR`,
  `CLAUDE_CODE_CUSTOM_OAUTH_URL`, `apiKeyHelper`. A variable applies when it is set to a non-empty
  value in `env`, or in the `env` object of `<config home>/settings.json` (string values), each
  listed once. The three `CLAUDE_CODE_USE_*` variables count only when truthy (trimmed,
  case-insensitive `1`, `true`, `yes`, `on`). `CLAUDE_SECURESTORAGE_CONFIG_DIR` counts when
  defined, even empty, and `CLAUDE_CODE_CUSTOM_OAUTH_URL` when non-empty, in `env` only.
  `apiKeyHelper` applies when `settings.json` sets a non-empty string. An unparseable
  `settings.json` is ignored. For a foreign directory the settings file is inside the given value;
  for a pool nothing is read.
- `warnings` holds codes; for a resolved named account whose name is reserved it includes
  `RESERVED_NAME`.

### Error and warning codes

Errors carry `code`, a human `message` and, where relevant, `path`. A warning is an object
`{code, message, path?}`; conformance compares warnings by `code` only.

| Code | Kind | `path` | When |
|---|---|---|---|
| `INVALID_NAME` | error | none | A name fails the grammar, or `default` where only a named account is allowed (B7) |
| `RESERVED_NAME` | error on create, warning on discovery and resolve | none | A2 |
| `ACCOUNT_NOT_FOUND` | error | `$HOME/.claude-<name>` for env and gates; the marker file for a marker binding; the claimed directory for a claim | Env or binding names an undiscovered account |
| `ACCOUNT_UNAVAILABLE` | error | the account entry | Account entry is dangling or unreadable |
| `ACCOUNT_EXISTS` | error | the entry | `create` or `adopt` on an existing entry |
| `ENV_CONFLICT` | error | none | Step 1.3 and 1.5 |
| `MARKER_INVALID` | error | the marker | Marker parsing |
| `CLAIM_CONFLICT` | error | the walked directory | Step 2.2 |
| `SPEC_FILE_INVALID` | error | the spec file | A3 |
| `INVALID_SESSION_ID` | error | none | B4 |
| `SAME_ACCOUNT` | error | none | B4 |
| `SESSION_NOT_FOUND` | error | none | B4 |
| `SESSION_LIVE` | error | none | B4, B7: a live session, or an unknown one without `force` |
| `SESSION_EXISTS` | error | none | B4 |
| `DESTINATION_BLOCKED` | error | the destination parent | B4 step 6 |
| `STATE_FILE_INVALID` | error | the state file | B5 |
| `INVALID_ENTRY` | error | none | B5 |
| `SLOT_UNSUPPORTED` | error | none | B7 |
| `SLOT_STATE` | error | none | B7 |
| `SLOT_CONFLICT` | error | `~/.claude/.claude.json` | B7 |
| `SLOT_TARGET_INVALID` | error | the offending file | B7 |
| `LOCK_BUSY` | error | the lock | A3 file safety rules |
| `IO_ERROR` | error | the path | Any unexpected filesystem error |
| `EMPTY_ENV` | warning | | Step 0 |
| `ENV_NOT_APPLIED` | warning | | Step 1.5 |
| `NON_CANONICAL_CONFIG_DIR` | warning | | Step 1 mapping, any `reason` |
| `NOT_A_DIRECTORY` | warning | the entry | Discovery |
| `MARKER_IGNORED_IN_REPO` | warning | | Step 2 |
| `CANDIDATE_UNAVAILABLE` | warning | the entry's account path | Step 2, a later marker list entry that is not an `ok` account |

## A5. Why this and not the alternatives

- **A config file listing arbitrary folder paths.** Every tool must find and parse the file before
  it can do anything, a name means nothing without it, and the file needs a home. The natural home,
  `~/.claude`, is the very directory being abstracted over, so any other location makes the scheme
  feel like a tool rather than part of Claude Code. Symlinks give the same flexibility with no file.
- **A base-directory setting** that moves all accounts at once. Every tool must see the same
  setting, and it cannot place one account differently from the rest.
- **Swapping credentials in place in one `~/.claude`** (what cswap and CCSwitcher do). Only one
  account can be live at a time, per-directory accounts need the tool as a wrapper, history,
  settings and projects are shared whether wanted or not, and the tool must defend against refresh
  token rotation on every switch (cswap holds Claude Code's own lockfiles and classifies every live
  credential before backing it up). Making plain `claude` follow a switch without rewriting
  credentials is possible only where the login lives in a file; B7 offers exactly that and no
  more.

---

# Part B: building blocks (optional)

Helpers so tool builders do not each reimplement the fiddly parts. None is required for
conformance, and none imposes a workflow. The libraries do no network I/O. Every Part B operation
that takes an account name applies the **account gate**: `INVALID_NAME` for a bad name, then
`ACCOUNT_NOT_FOUND` and `ACCOUNT_UNAVAILABLE` for a name that is not an `ok` account (`default` is
always present).

## B1. Env and paths

`env(name)` returns the delta to launch as an account:

- named account: set `CLAUDE_CONFIG_DIR` to the canonical path and `CLAUDE_MULTI_ACCOUNT` to the
  name;
- `default`: unset `CLAUDE_CONFIG_DIR`, set `CLAUDE_MULTI_ACCOUNT=default`;
- always: unset `CLAUDE_SECURESTORAGE_CONFIG_DIR` and `CLAUDE_MULTI_ACCOUNT_SOURCE`; a shell hook
  then sets `CLAUDE_MULTI_ACCOUNT_SOURCE=hook` itself.

`unset` is sorted bytewise without duplicates. A shell hook or launcher applies the whole delta,
never `CLAUDE_MULTI_ACCOUNT` alone, since `claude` ignores that variable (A4 step 1.5).

It does not touch the login-replacing variables unless called with `clearAuthOverrides`, which
also unsets `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY` and
`ANTHROPIC_PROFILE`. It reports what remains as A4's `overriddenBy` does; a key set in the
account's `settings.json` stays reported because an env delta cannot clear it. `env` is a pure
function: it does not look for the account on disk and ignores reservation.

`credentialLocations(name, platform)` returns the ordered list of places Claude Code looks:

- Linux: `[{file: "<config home>/.credentials.json"}]`.
- macOS: `[{keychain: {service, account}}, {file: ...}]`. `service` per A2 with the OAuth suffix;
  `account` is `$USER` if set and non-empty, else the OS user name (the process wrapper reads it
  from the OS user database, the passwd entry on POSIX, not from the environment), replaced by
  `claude-code-user` if absent or if it fails `^[a-zA-Z0-9._-]+$`.
- Windows: `[{file: ...}]`, or `[{credentialManager: {}}, {file: ...}]` when Credential Manager
  is in use (the target name is not yet verified, so the item carries no fields).

## B2. Identity and usage

`identity(name)` reads `oauthAccount` from the account's global config file (A1) and returns
`{email, orgName, orgUuid, organizationType, billingType, userRateLimitTier,
organizationRateLimitTier}` (from `emailAddress`, `organizationName`, `organizationUuid` and the
other four by their own names; a missing key is `null`). It returns `null` when there is no file,
it cannot be parsed, or there is no `oauthAccount` object. No credential is read, so a status line
never triggers a keychain prompt on macOS.

`usage(name)` reads `cachedUsageUtilization` from the same file and returns
`{fetchedAt, data, windows, stale}`. Claude Code writes it as
`{fetchedAtMs, accountUuid?, utilization: {five_hour: {utilization, resets_at}, seven_day: ...,
seven_day_opus: ...}}`. `data` is the object verbatim. `fetchedAt` is its `fetchedAtMs` as RFC 3339
UTC with exactly three fractional digits (`null` if absent). `windows` maps each key of
`data.utilization` whose value is an object to `{utilization, resetsAt}`: `utilization` is the number
(percent) or `null`, `resetsAt` is the `resets_at` string as given or `null`; keys with non-object
values are left out, and `windows` is `{}` without a `utilization` object. `stale` is `true` when
there is no numeric `fetchedAtMs`, when the age at the caller's `now` is negative or more than one
hour (3 600 000 ms; exactly one hour is fresh), or when the cache's `accountUuid` differs from the
global config's `oauthAccount.accountUuid` (both absent counts as equal). That is Claude Code's own
rule for ignoring the cache. `usage` returns `null` when the object is absent. A stale cache is still
returned, so a caller can show it marked as old. Claude Code writes the cache at most once a minute
and only when it fetches usage, so it can lag a live session; a limit that must be caught promptly
should also use the status line payload's rate limit fields, which this spec does not read.

Both take **either a name or a resolution** (the result of `resolve()`), and then read that
resolution's `globalConfig`. A status line MUST pass the resolution, because for
`CLAUDE_CONFIG_DIR=$HOME/.claude` Claude Code uses `~/.claude/.claude.json` and the name `default`
would read `~/.claude.json`. A resolution with no `globalConfig` (a pool, a relative directory)
gives `null`.

`credentials(name)` reads `<config home>/.credentials.json` only (never a keychain) and returns
`{source: "file", path, accessToken, expiresAt, expired, scopes, subscriptionType, rateLimitTier}`
from the `claudeAiOauth` object. **The refresh token is never returned.** `expiresAt` is RFC 3339
UTC with three fractional digits (`null` if the file has none), and `expired` is `expiresAt <= now`
with the caller's clock (`false` when there is no expiry); it reports an expired token rather than
failing. It returns `null` when the file is absent, unparseable, a link (Claude Code opens it with
`O_NOFOLLOW`), or has no `claudeAiOauth` object with a non-empty string `accessToken`. **Tools
MUST NOT refresh tokens:** the refresh token rotates, and a refresh outside Claude Code logs Claude
Code out. To get a fresh token, run `claude` (for example `claude auth status`) under that account.

## B3. Live sessions

`liveSessions(name)` reads `<config home>/sessions/<pid>.json`. Only canonical file names count:
`^[1-9][0-9]{0,9}\.json$` with ASCII digits (so `String(pid)` equals the stem; `0123.json` and
non-ASCII digits are ignored). A file that is not a JSON object is skipped. Each record yields
`{pid, sessionId, status}` sorted by `pid`, where `pid` comes from the file name and `sessionId`
from the record (`null` if absent).

`status` is decided as follows. If the record has a `pidDomain` that differs from the caller's, it
is `unknown`; a record without `pidDomain` is in the caller's domain. Otherwise, if the pid
definitely does not exist (`kill(pid, 0)` gives `ESRCH`, or the platform's equivalent), it is
`dead`. If the lookup of the process itself fails (an error, a timeout, a missing tool, as opposed
to a definite "no such process"), it is `unknown`, never `dead`: Claude Code treats an unreadable
current start marker as the same process. If the process exists, the record's start marker is
compared with the process's: `procStartFt` if the record has one (Windows), else `procStart`; equal is
`live`, different is `dead` (the pid was reused). A record with neither marker whose pid exists
cannot be proved dead and is `unknown`. `unknown` is never dead.

The caller's `pidDomain` and the process start marker MUST be computed exactly as Claude Code
computes them, byte for byte:

- `pidDomain`: on Linux and WSL `linux:<trim(/etc/machine-id)>:<readlink(/proc/self/ns/pid)>`, for
  example `linux:11111111111111111111111111111111:pid:[1234567890]`. A part that cannot be read is
  the empty string, never a substitute: without a machine id the domain is
  `linux::pid:[1234567890]`, and with neither it is `linux::`. On Windows
  `linux:<lower-cased host name>`; on any other platform (macOS) the literal `linux`.
- `procStart`: on Linux the string of field 22 (`starttime`) of `/proc/<pid>/stat`, parsed after
  the last `)` because the command name may contain spaces and parentheses; elsewhere the trimmed
  output of `ps -o lstart= -p <pid>` run with `LC_ALL=C` and `TZ=UTC` (spacing inside the string is
  kept exactly). On Windows the record carries `procStartFt` instead (the process creation time as
  a FILETIME string).

`sessionOfPid(name, pid)` returns the `sessionId` that `sessions/<pid>.json` records, or `null` (no
file, not a JSON object, no non-empty string `sessionId`, or a pid below 1). Liveness is not checked;
use `liveSessions` for that. Claude Code updates the record's `sessionId` when the conversation
changes (`/clear`, resume) and deletes the file when it exits, so a launcher that knows its child's
pid can follow the child's current conversation instead of guessing from transcript times.

Using the host name as the domain is wrong: every record Claude Code writes would be `unknown`.
The process table and the caller's domain are inputs behind an interface so conformance can fake
them.

Claude Code does not register every process: teammate agents, some child sessions and parked spare
processes write no record, and a gated storage backend may keep records outside `sessions/`. So B3
is best effort: it can prove that a session is live, not that none is.

## B4. Session handover

`handoverSession(id, from, to, {overwrite, force})` copies a conversation so `claude --resume <id>`
works under another account. Copy, never move. Checks run in this order.

1. `id` MUST match `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` (Claude Code ids are UUIDs), else
   `INVALID_SESSION_ID`. The grammar excludes `.` and separators, so an id cannot climb out of the
   account. As defence in depth every location computed from it MUST also stay inside the config
   home after normalisation, and locations are deduplicated before use.
2. The account gate for `from`, then `to`.
3. `from` and `to` that are the same account (the same name, or an alias group, B7's `default` and
   slot account included) are `SAME_ACCOUNT`; otherwise `overwrite` would delete the source.
4. The locations are `projects/<slug>/<id>.jsonl`, `projects/<slug>/<id>/` (`subagents/`,
   `tool-results/`), `file-history/<id>/`, `session-env/<id>/` and `tasks/<id>/`, those that exist
   by `lstat`. Their parent directories (`projects`, `projects/<slug>`, `file-history`,
   `session-env`, `tasks`) must be real directories by `lstat`: Claude Code refuses symlinked
   subdirectories of the config home, so a parent that is a link (or any other non-directory) is
   never a session location. Nothing under it is read from the source, and a source parent that is
   a link has its relative path listed in `skipped`. Nothing is ever written through a link in the
   destination (step 6). The source slugs are the real
   directories under `projects/` of `from`. If no source location is a regular file or a
   directory: `SESSION_NOT_FOUND`.
5. `SESSION_LIVE` while B3 reports a session with this id in `from` as `live`, or as `unknown`
   unless `force` is set, since the copy would be torn. `force` overrides `unknown` only, never
   `live`. The message says which of the two it was.
6. `DESTINATION_BLOCKED` (path: the offending destination parent) if a source location needs a
   parent in `to` (`projects`, `projects/<slug>`, `file-history`, `session-env` or `tasks`) that
   exists and is not a real directory. Nothing can be written there, and a handover that returns
   success with the transcript missing would make `claude --resume` fail, so it is an error,
   whether or not `overwrite` is set. A destination parent that is a link and has no source location
   to receive is ignored.
7. `SESSION_EXISTS` if any location of the id exists in `to` (a link at the location counts),
   unless `overwrite`. The check covers the five location kinds under the union of the real
   (non-link) project slugs of `from` and of `to`, so the same id under another project in `to`
   counts, and `overwrite` removes all of those. Locations under a linked parent in `to` are not
   checked or removed.

The copy takes regular files and directories only, decided by `lstat`. Links, FIFOs and devices
are never followed or copied; they are listed in `skipped`, as are linked parent directories (4). File modes are kept, new directories
are 0700, and `from` is never touched. The result is `{copied, skipped}`: relative paths from the
config home, `/` separated, sorted bytewise, `copied` listing files only. Source files are read
with `O_NOFOLLOW` and `O_NONBLOCK` so a swapped-in link or FIFO cannot redirect or hang the copy.

A failure must not lose data. The copy is built under temporary names next to each destination
location and swapped in; with `overwrite` the old destination is removed only after its
replacement is complete. A failed copy (an unreadable file, for example) is `IO_ERROR` and leaves
the destination as it was, with no temporary files. After a successful copy the two transcripts
diverge; neither is updated from the other.

`projectSlug(cwd)` is Claude Code's folder name for a working directory under `projects/`: every
UTF-16 code unit of `cwd` outside `[a-zA-Z0-9]` becomes `-` (so an astral character gives two
hyphens), and when the result is longer than 200 characters it is cut to 200 and followed by `-` and
the base 36 text of `abs(h)`, where `h` is a signed 32-bit hash of the original `cwd`
(`h = (h * 31 + codeUnit) mod 2^32` over its UTF-16 code units, starting at 0, read as signed). The
string is used exactly as given: no normalisation. (Claude Code can override the folder through an
internal setting; this spec does not.) `sessionsFor(name, cwd)` lists the session ids of that project
in an account, newest first: the regular files (by `lstat`) named `<id>.jsonl` directly in
`projects/<projectSlug(cwd)>/` whose `<id>` fits the session id grammar, as
`[{id, mtime}]` with `mtime` as RFC 3339 UTC with three fractional digits, ties broken by id
bytewise. `projects` and the slug folder must be real directories (the linked-parent rule above),
else the list is empty.

Claude Code handles the account change itself: on resume it appends a `credential_org` record for
the new org. It may warn that thinking blocks from another org cannot be reused; whether it does
depends on the mode and model.

## B5. Availability state

`.multi-account-state.json` in the account dir:

```json
{
  "version": 1,
  "limits": [
    { "window": "seven_day", "model": "opus", "until": "2026-10-09T14:00:00Z",
      "reason": "rate_limit", "updatedBy": "my-swapper", "updatedAt": "2026-10-06T20:01:00Z" }
  ]
}
```

- One entry per `(window, model)`; `model` is `null` (or absent) for a window covering all models.
  `until` is an RFC 3339 instant with upper-case `T` and `Z` or a numeric offset, and optional
  fractional seconds (`2026-10-09T14:00:00Z`, `2026-10-09T16:00:00+02:00`); instants are always
  compared as instants. `updatedAt` is written as UTC with whole seconds.
- `markLimited(name, entry)` and `clearLimited(name, window, model)` read, merge and write under
  the A3 lock. An `entry` needs a non-empty string `window`, a `model` that is `null` or a
  non-empty string, a valid `until`, and string `reason` and `updatedBy` if present; anything else
  is `INVALID_ENTRY` (checked after the account gate). Merging keeps the new entry for a key when
  its `until` is equal or later, and the old one otherwise, then drops entries whose `until <= now`.
  An entry for a new key is appended. A past `until` in the new entry is dropped too.
- Everything else is preserved verbatim: other top-level keys, entries written by other tools
  (with their own keys, or without `reason` or `updatedBy`), entries that are not objects, and
  entries whose `until` cannot be read are carried through untouched.
- A state file that is present but not understood is **never overwritten**: unparseable, not a
  UTF-8 JSON object, `version` other than `1`, `limits` present but not an array, nested deeper
  than 100 levels, not a regular file, or unreadable. Writes fail with `STATE_FILE_INVALID`. A file
  that is missing, or a link to a missing target, is empty. `clearLimited` on a missing file writes
  nothing and returns `{limits: []}`. A file without `limits` is an empty list.
- `available(name, now, {model})` is true when no entry applying to `model` has `until > now`. An
  entry applies when its `model` is null or equals the given `model`; with no `model` only entries
  with a null model apply. Reads treat any file they do not understand as empty, and ignore
  entries without a usable `until`.
- `limits(name)` returns the entries a read understands, in file order, past ones included, each as
  `{window, model, until, reason, updatedBy, updatedAt}` (`until` as stored; `model` null when absent;
  the others `null` when absent or not strings). Entries that are not objects, lack a string
  `window` or lack a readable `until` are left out. A file that is missing or not understood gives
  `[]`.
- `availableAt(name, now, {model})` returns the instant the account is next available, or `null`
  when it is available now: the latest `until` among the entries that apply to `model` (as in
  `available`) and are after `now`. It is formatted as UTC `YYYY-MM-DDTHH:MM:SSZ`, with `.fff`
  (milliseconds, finer digits truncated) added only when the instant has non-zero milliseconds.
  `null` also means "no limit known": a file that is not understood.
- Results are `{limits}` (the written list), `{available}`, `{limits}` for `limits`, and
  `{availableAt}`.

## B6. Pools and ordered candidates

An account joins a pool with `"pool": "<pool>"` and optional `"priority": <int>` (default 0) in its
`.multi-account.json` (A3). An account is in at most one pool. Members are `default` and the `ok`
accounts whose spec file names the pool, counting each alias group once through its
representative (A2), so `default` is a member only when it is not an alias of a named account.
`pick(pool, now, {model})` returns the available member with the highest priority, ties broken by
name bytewise (`default` is just a name here). `next(pool, current, now, {model})` returns the next
available member after `current` in that order, wrapping; the candidates after `current` come
first, then the ones up to and including `current`, so when only `current` is available it is
returned. A `current` that is not a member starts from the top. Both return `null` when no member is
available. A bad pool name is `INVALID_NAME`, and an invalid spec file in any `ok` account (`default`
first, then names), whether or not it names the pool, is `SPEC_FILE_INVALID`. Availability is B5's.

`poolMembers(pool)` returns the member names in the order `pick` uses (priority descending, then
name bytewise), ignoring availability, with the same errors as `pick`. An alias group is listed once,
under its representative.

A marker list (A4) gives a project its own preference order, which pools cannot, since priority
there belongs to the account. Two helpers work on any ordered list, normally the `candidates` of a
resolution:

- `pickFrom(candidates, now, {model})` returns the first available candidate, or `null`.
- `nextFrom(candidates, current, now, {model})` returns the next available candidate after
  `current`, wrapping, with the same rules as `next`; `null` if none. An alias group is one account
  (A2): `current` is matched to the first candidate that is the same account (so `default`, while
  the slot holds `work`, is `work`), candidates that are the same account as `current` are skipped
  until last, and a `current` that matches no candidate starts from the top.

Every candidate name is validated first, so an invalid name is `INVALID_NAME` even after an available
one. A candidate that is undiscovered, dangling or unreadable is not an error but is never
available: it is skipped. An empty list gives `null`. Pools are kept as they are.

## B7. Active slot (platform-gated)

For users who want plain `claude` (and anything else that assumes `~/.claude`) to follow a switch.
The slot is `~/.claude` as a link to an account dir plus `~/.claude.json` as a link to that
account's `.claude.json`. Switching re-points the links; no credential is touched, so A1 holds.
This works only where the login lives in a file inside the config dir, hence the gate.

`slot()` returns `{state, name}` and reports one of:

| State | Meaning |
|---|---|
| `unmanaged` | `~/.claude` is a real directory, or does not exist |
| `managed` (with `name`) | `~/.claude` links to `~/.claude-<name>` (a name that is not `default`; the account dir may itself be a link) and `~/.claude.json` is a link whose target is exactly `~/.claude-<name>/.claude.json` (that target may not exist yet) |
| `broken` | Anything else: `~/.claude` a file or a link to somewhere else, a missing or dangling account dir, a missing `~/.claude.json` link or one pointing elsewhere, a `.claude.json` in the account that is itself a link or not a file (a chain), or `.credentials.json` in the account being a link |
| `unsupported` | The login would not follow the link: `platform` is `darwin` (keychain), or Windows with Credential Manager in use (A1), or Windows where the process cannot create file symlinks |

The Windows path of this block (junctions, remove-then-create, the symlink probe) is specified but
has not been run on a real Windows host. Relative link targets are resolved against `$HOME`. `unsupported` takes precedence. In that state
`adopt` and `activate` refuse with `SLOT_UNSUPPORTED` and never rewrite credentials; the user still
has all of Part A and can run accounts side by side. `canCreateSymlinks` is an input of the
library; the process wrapper sets it by creating and removing a file symlink in `$HOME`.

`adopt` and `activate` take a **named account only**: `default` (or any invalid name) is
`INVALID_NAME`. Both return the recomputed `slot()`. Both run under `~/.claude-slot.lock` (A3 lock
rules) and refuse with `SESSION_LIVE` while B3 reports a live session, or an unknown one unless
`force` is set, in the account whose directory they are about to move or leave. Because B3 is best
effort, this narrows the window; it does not close it.

- `adopt(name, {force})` turns an `unmanaged` slot into a managed one: moves `~/.claude` to
  `~/.claude-<name>` and `~/.claude.json` into it, then creates both links. If `~/.claude` does not
  exist it creates the account directory (mode 0700) instead. Checks in order: `SLOT_UNSUPPORTED`,
  `INVALID_NAME`, `RESERVED_NAME`, `SLOT_STATE` (the slot is not `unmanaged`), `ACCOUNT_EXISTS`,
  `SLOT_CONFLICT` (both `~/.claude.json` and `~/.claude/.claude.json` exist, and one would replace
  the other), `SLOT_TARGET_INVALID` (a `~/.claude.json` or `~/.claude/.claude.json` that is not a
  regular file, or a linked `~/.claude/.credentials.json`, since the result would be `broken`), then
  the lock and the session check. It MUST verify that links can be created before moving anything
  (a failed probe is `SLOT_UNSUPPORTED` on Windows and `IO_ERROR` elsewhere) and roll back every
  step if a later one fails. Without a `~/.claude.json` the link is created
  dangling, which is `managed`.
- `activate(name, {force})` re-points a managed slot. Checks in order: `SLOT_UNSUPPORTED`,
  `INVALID_NAME`, the account gate for the target, `SLOT_STATE` (the slot is not `managed`),
  `SLOT_TARGET_INVALID` (the target's `.credentials.json` is a link, or its `.claude.json` is not a
  regular file), then the lock and the session check on the current slot account. It replaces
  `~/.claude.json` first and `~/.claude` second. Where renames can replace a link, each is created
  under a temp name and renamed over the old one; each rename is atomic, the pair is not, so a
  `claude` started in the moment between them sees the new global config with the old directory.
  On Windows a junction is a directory entry that a rename cannot replace, so `~/.claude` is
  removed and created again (a short gap in which it does not exist, under the lock and refused
  while sessions are live). Activating the account already in the slot is a normal success.
- While managed, `default` is an alias of the slot account (A2): the slot account represents the
  group and `default` carries `aliasOf: "<name>"`. Launching the slot account directly with
  `CLAUDE_CONFIG_DIR` uses the same `.credentials.json` and `.claude.json`, so there is still one
  login. Because claims, pools and mapping use the representative, a binding to the slot account
  by name stays stable when the slot moves.
- The paths Claude Code hard-codes to `~/.claude` (A1) live in whichever account is in the slot,
  so device keys and consent state change with each switch.

---

# Conformance

Data driven. `conformance/cases/*.json` each describe:

- `platform` (`linux`, `darwin`, `win32`) and `caseInsensitive` (bool);
- a fake filesystem: dirs, files (text or base64 for bytes that are not UTF-8), symlinks,
  junctions, dangling links, FIFOs, with modes and with explicit inode identity where two paths
  must be the same directory;
- `env`, `cwd`, `home`, options, a fixed `now`, a process table and the caller's pid domain;
- an operation and the expected result, or the expected error code and path.

Every library runs every case, and `conformance/run.sh` fails on any divergence. Part A cases are
mandatory; Part B cases apply to the blocks a library ships. Filesystem, keychain and process-table
access sit behind interfaces the harness fakes, so every platform's cases run on Linux CI. Libraries
take `{env, cwd, home, platform}` as inputs (A4), which is what makes this possible. Junction
detection differs per language (Go 1.23 reports `ModeIrregular`, Python before 3.12 needs
`is_junction`), so the fake layer, not the host OS, decides what a junction is. The fake
filesystem refuses a rename over a Windows junction, as Windows does. Lock contention is tested
with an immediate `LOCK_BUSY` (the clock never advances); real retry policies are not.

# Claude Code behaviour the spec relies on

Verified on 2.1.282 (macOS arm64, 2026-09-25) and 2.1.292 (Linux x86-64, 2026-10-06 and 2026-10-07).

- Config home formula and verbatim handling of `CLAUDE_CONFIG_DIR` (A1). `claude` reads only
  `CLAUDE_CONFIG_DIR`; it sets `CLAUDECODE=1` for its child processes.
- macOS keychain service `Claude Code${OAUTH_FILE_SUFFIX}-credentials`, plus
  `-<sha256(config home)[:8]>` only when `CLAUDE_CONFIG_DIR` is set; account `$USER` with the
  fallback above.
- Linux credential storage is the plaintext file only; the store selector is fixed to `"file"`.
  `CLAUDE_SECURESTORAGE_CONFIG_DIR` defined-but-empty selects `~/.claude`.
- `.credentials.json` is opened with `O_NOFOLLOW`; `.claude.json` is written through a symlink,
  one hop, atomically at the target.
- `$HOME/.claude.json` vs `<config home>/.claude.json` asymmetry (including
  `CLAUDE_CONFIG_DIR=$HOME/.claude` using `~/.claude/.claude.json`), the `-custom-oauth` suffix, and
  legacy `.config.json` precedence.
- Hard-coded `homedir()/.claude` paths listed in A1.
- Session registry `sessions/<pid>.json` with `pid`, `sessionId` (which changes when the
  conversation changes), `procStart` or `procStartFt`, `pidDomain` and `kind`; Claude Code's own
  liveness test is `kill(pid, 0)` plus the start marker. The `pidDomain` and `procStart` formulas
  in B3 are read from the Linux build (2.1.292) and checked against live files there; the macOS and
  Windows variants are read from the same code and not run. Not every process is registered (B3).
- Transcripts record `credential_org`. The login can also be replaced by `ANTHROPIC_AUTH_TOKEN`,
  the `CLAUDE_CODE_USE_*` variables and `ANTHROPIC_PROFILE` (A1).
- The cached usage shape and its rules (written at most every 60 s, ignored when older than one hour or
  for another account), the `sessionId` field of `sessions/<pid>.json`, and the project folder rule
  of B4 (`replace(/[^a-zA-Z0-9]/g, "-")`, 200 character limit, hash suffix) are read from the 2.1.292
  bundle; the session fields are also seen in live files.
- Cleanup tolerates a symlinked config root but refuses symlinked subdirectories, which supports
  relocation by link and rules out linking subdirectories between accounts.

Known caveats, not relied on:

- Some SDK and resume paths trim `CLAUDE_CONFIG_DIR`, so "never trimmed" is not universal.
  Canonical paths have nothing to trim.
- Some background-daemon behaviour is disabled when `CLAUDE_CONFIG_DIR` is set, so named accounts
  can behave slightly differently from `default`.
- `claude --cloud` refuses to sync a project inside or linked from the config dir; do not relocate
  an account into a project tree.
- `ANTHROPIC_CONFIG_DIR` is not a switch for Claude Code's own state. If it or `ANTHROPIC_PROFILE`
  ever becomes a config-dir switch, this spec should follow it.

# Changelog

**v0.2.3 (draft)**

- No change to the spec text. The libraries moved to `go/`, `typescript/` and `python/`, and the npm
  and PyPI packages are named `claude-code-multi-account-core`.

**v0.2.2 (draft)**

- B4: a destination parent that is a link and would receive a location is `DESTINATION_BLOCKED`
  (an error, not a success with nothing copied); new helpers `projectSlug` and `sessionsFor`.
- A3: `specFile`, `updateSpecFile`, `claim`, `unclaim`. B2: `usage` gains `windows` and `stale`
  (the cache shape is now stated as written by Claude Code). B3: `sessionOfPid`. B5: `limits`,
  `availableAt`. B6: `poolMembers`.
- Case format: file `mtime` may carry milliseconds.

**v0.2.1 (draft)**

- B3: a failed process lookup is `unknown`, never `dead`; `pidDomain` parts that cannot be read are
  empty strings (`linux::pid:[...]`), the literal `linux` only off Linux and Windows.
- B4: a parent directory of a session location that is a link is never a location (not read, not
  written through), reported in `skipped`; `SESSION_EXISTS` and `overwrite` cover the union of the
  real project slugs of both accounts.
- B6: `nextFrom` treats an alias group as one account. Marker lists: only the first entry must exist;
  later unavailable entries give `CANDIDATE_UNAVAILABLE`; `pickFrom` and `nextFrom` skip candidates
  that are not usable accounts instead of failing.
- B7: a failed link probe is `IO_ERROR` off Windows. A2: NFC tables must be bundled, a runtime
  warning is not enough. A4: warning object shape, list separators are space or tab, launchers told
  an account use `env`.

**v0.2 (draft)**

- A1: global config rule for `CLAUDE_CONFIG_DIR=$HOME/.claude`, empty
  `CLAUDE_SECURESTORAGE_CONFIG_DIR`, the full list of login-replacing variables and settings,
  scope note for project and managed settings, config sharing out of scope.
- A2: alias representative is the first named account (`default` carries `aliasOf`); `list()` shape;
  `create` details; ASCII fold; NFC pinned to Unicode 16.0; junction definition.
- A3: strict UTF-8 and depth limit; `priority` range; `~\` on Windows; lazy spec file reads; lock
  named after the path as given, retry policy left to the implementation but bounded, `LOCK_BUSY`
  also for a lost takeover race; `IO_ERROR`; `os.replace`.
- A4: `CLAUDE_MULTI_ACCOUNT` alone is `applied: false` with `ENV_NOT_APPLIED`, or `ENV_CONFLICT`
  inside `claude` (`CLAUDECODE=1`); agreeing variables on a missing account report the account;
  ordered marker lists with `candidates`; new result fields `applied`, `candidates`, `globalConfig`;
  extended `overriddenBy`; strict UTF-8 markers; `ignoreHookEnv` scope; explicit pool result; error
  `path` column; new codes.
- B1: hooks apply the whole `launchEnv`; wider `clearAuthOverrides`; user name source.
- B2: `identity` and `usage` accept a resolution; `credentials` result defined, no refresh token.
- B3: exact `pidDomain` and `procStart`/`procStartFt` formulas, canonical file names, `unknown` for
  records without a start marker, best effort note.
- B4: session id grammar and `INVALID_SESSION_ID`, `SAME_ACCOUNT`, `unknown` blocks unless `force`,
  regular files only with a `skipped` list, no data loss on failure.
- B5: verbatim preservation, `STATE_FILE_INVALID`, `INVALID_ENTRY`, instants with offsets.
- B6: pool members use the representative; `pickFrom` and `nextFrom` for ordered lists.
- B7: missing `~/.claude` is `unmanaged`; relocated accounts and dangling `.claude.json` links are
  `managed`; `adopt` and `activate` take a named account only, return `slot()`, refuse on live or
  unknown sessions, validate the target, and `adopt` has a conflict check, a lock and rollback;
  Windows remove-then-create.
