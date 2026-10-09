# Conformance format

[SPEC.md](../SPEC.md) (draft v0.2) is the authority. This file fixes the harness details SPEC.md
leaves to the suite (case syntax, fake filesystem, runner protocol, exact result shapes) so that
three libraries (Go, TypeScript, Python) can be held to byte-identical behaviour. Anything still
ambiguous is listed in [SPEC-GAPS.md](SPEC-GAPS.md). If a case and this file disagree, the case is
a bug; fix the case.

Layout:

- `conformance/cases/*.json` one case per file, prefix = spec section (`a2-`, `a3-`, `a4-`, `b1-` ...).
- `conformance/run.sh` runs every case against every available runner and compares.
- `conformance/validate_cases.py` checks that every case file is well formed.
- `conformance/gen/` holds the tables the case files are generated from, and `reference_runner.py`,
  a single-file runner used only to cross-check the cases. It is not one of the three libraries.
- `spec/reserved.json` is read by runners from `$CCMA_REPO_ROOT/spec/reserved.json` (run.sh sets it
  to the absolute repo root; when unset use the working directory) unless the case carries its own
  `reserved` list.

## 1. Runner protocol

Each library ships a runner executable. Run from the repo root:

| Lang | Command | Must exist |
|---|---|---|
| Go | `go run ./go/cmd/conformance-runner` | `go/cmd/conformance-runner/` |
| TypeScript | `node typescript/dist/conformance-runner.js` | that file |
| Python | `uv run --project python python -m claude_code_multi_account.conformance_runner` | a `conformance_runner.py` under `python/` |

run.sh runs every runner with the repo root as working directory. For speed it builds the Go runner
once (`go build`) instead of calling `go run` per case. The runner reads ONE case JSON document on stdin, builds the fake world from it, runs the op, and
writes ONE JSON object on stdout, then exits 0. A non-zero exit, empty stdout or invalid JSON is a
failure. Output:

```
{"result": <value>}
{"error": {"code": "<CODE>", "path": "<path or null>", "message": "<free text>"}}
```

plus `"fs": {...}` (a full dump, section 3.6) for every write op, on success AND on error. Write ops
are `create`, `handover_session`, `mark_limited`, `clear_limited`, `adopt`, `activate`,
`update_spec_file`, `claim`, `unclaim`. Read ops
MUST NOT change the fs and need not dump it.

The runner MUST NOT touch the real filesystem, the real clock, the real process table or the real
environment. Everything comes from the case. The library under test is called through its normal
public API with the fake FS, fake process table and fixed clock injected through the same
interfaces SPEC.md requires.

### Comparison rules (implemented in run.sh)

1. Actual output and `expect` are compared after canonical key sort (object key order never matters;
   array order does, unless stated below).
2. Numbers compare by numeric value (`3` equals `3.0`).
3. Any array stored under a key named `warnings`, at any depth, is compared as a sorted list of
   `code` strings. Elements may be strings or objects with `code`; only the code counts. Expected
   values in cases are written as plain code strings.
4. For errors only `code` is compared, plus `path` if (and only if) the expected error has a `path`
   key. An expected `"path": null` means the actual path must be null or absent. `message` is never
   compared.
5. `expectFs` (write ops): see 3.7.
6. For error cases the actual output must not contain `result`; for result cases not `error`.
7. After any write op, the dumped fs must contain no path whose last component contains `.tmp.` and
   no path ending in `.lock`, except paths the case's `expectFs` lists. A leftover temp file or lock
   is a failure.

## 2. Case file

```json
{
  "id": "a4-marker-basic",
  "description": "one sentence",
  "spec": ["A4 step 2.1", "A4 Marker parsing"],
  "platform": "linux",
  "caseInsensitive": false,
  "home": "/home/p",
  "cwd": "/home/p/proj",
  "env": {"CLAUDE_MULTI_ACCOUNT": "work"},
  "options": {},
  "now": "2026-10-06T12:00:00Z",
  "reserved": null,
  "fs": {},
  "processes": {},
  "callerPidDomain": "host-1",
  "op": {"name": "resolve", "args": {}},
  "expect": {"result": {}},
  "expectFs": {}
}
```

Required: `id` (equals the file name without `.json`), `description`, `spec` (non-empty list of
strings), `platform`, `caseInsensitive`, `home`, `cwd`, `env`, `options`, `now`, `fs`, `op`, `expect`.
Optional: `processes` (default `{}`), `callerPidDomain` (default `"host-1"`), `reserved` (default
null = use `spec/reserved.json`; else a list of names that replaces it for this case), `expectFs`.

- `platform`: `linux`, `darwin` or `win32`. Selects path flavour (posix or win32) and nothing else;
  `caseInsensitive` independently selects the filesystem's case behaviour (3.4).
- `home`, `cwd`: absolute paths in the platform's flavour. `home` is the `home` input (A4), used as
  given (not normalised by the runner; the library normalises through `join`).
- `env`: string to string map, the whole environment. Nothing else is visible to the library.
- `options`: A4 options `trustRepoMarkers` (bool), `ignoreHookEnv` (bool), `ceilingDirs` (list of
  absolute paths), plus two harness inputs: `canCreateSymlinks` (bool, default true; false models
  Windows without symlink permission, B7) and `userName` (string, the OS user name used by
  `credential_locations` when `env.USER` is unset, default none).
- `now`: RFC 3339 UTC, whole seconds. The fixed clock. The clock never advances.
- `processes`: process table, pid (decimal string) to `{"pidDomain": "<string>", "procStart": "<string>"?,
  "procStartFt": "<string>"?, "lookupError": true?}`. A pid absent from the table does not exist
  (a definite "no such process"); an entry with `lookupError: true` models a lookup that failed (error
  or timeout) and has no start markers. `callerPidDomain` is the
  caller's own domain.
- `op.args`: per-op, section 5.

### Paths

- linux, darwin: posix. Separator `/`. Root `/`.
- win32: separator `\`; roots are drive roots `C:\`. Input paths may use `/`; the library must
  treat `/` and `\` as separators and produce `\`. UNC and `\\?\` are out of scope. A path is
  absolute on win32 only if it is `<letter>:` followed by a separator. `\x` and `C:x` are not.

**normalize(p)**, the Node `path.normalize` subset used everywhere: split on separators, drop empty
and `.` components, resolve `..` by popping (at the root it stays at the root), join with the
platform separator after the root prefix, no trailing separator except on a bare root. Win32 keeps
the drive letter case as given. `join(a, b...)` is normalize of the components concatenated with
the separator. `dirname`, `basename` are the obvious ones. `nfc(s)` is Unicode NFC. Canonical
path is `nfc(join(home, ".claude-" + name))`. A relative path is never absolute and never matches
an account.

**fold(s)** for case-insensitive comparison is ASCII lower-casing only (`A-Z` to `a-z`). Non-ASCII
characters compare exactly.

**Name grammar** is a full match (not a search, no trailing-newline allowance) of
`[a-z0-9][a-z0-9_-]{0,31}`. A pool name has the same grammar. In Python use `re.fullmatch`.

## 3. The fake filesystem

### 3.1 Case syntax

`fs` is a flat map from absolute path (platform flavour, already normalised: no `.` `..`, no
duplicate or trailing separators) to an entry object. Entry fields:

| Field | Applies to | Meaning |
|---|---|---|
| `type` | all | `dir`, `file`, `symlink`, `junction` (win32 only), `fifo`, `device` |
| `content` | file | UTF-8 text. Default `""`. Size is its UTF-8 byte length |
| `contentBase64` | file | The bytes, base64, for content that is not valid UTF-8. Exclusive with `content` |
| `mode` | all | octal string, e.g. `"0700"`. Defaults: dir `0755`, file `0644`, symlink and junction `0777`, others `0644`. Metadata only, never enforced |
| `target` | symlink, junction | link text, stored verbatim. Absolute, or relative to the directory containing the link |
| `inode` | dir, file | integer 1..999. Entries with the same `inode` and `dev` are the same object (3.2) |
| `dev` | dir, file | integer, default 1 |
| `unreadable` | any | true makes access fail with EACCES, see 3.5 |
| `mtime` | any | RFC 3339 UTC with up to three fractional digits, default `now`. Used by lock staleness and `sessions_for` |

Every ancestor of a key that is not itself a key exists implicitly as a plain `dir` (mode `0755`).
Every root that appears as the prefix of a key exists. A key whose ancestor is a non-dir, or whose
ancestor path passes through a link, is an invalid case (validate_cases.py rejects it). Links in
`fs` are only ever reached through lookup, never through key paths.

### 3.2 In-memory model

A tree of nodes. A dir node has `children`: name to node. A file node has bytes. A link node has a
`target`. Every non-link node has `(dev, ino)`. Load order: keys sorted by (component count
ascending, then bytewise). For each key, find the parent node literally (explicit or implicit
ancestors, no link following), create the node (reusing the existing node when `inode`+`dev` were
seen before), then insert it into the parent under its name. Auto inodes are 1000, 1001, ... in
load order. Two dir keys with the same `inode` share one node, so their children are the union of
the entries keyed under either path (a bind mount). Roots are separate nodes, one per root prefix
(compared with fold when `caseInsensitive`).

### 3.3 Operations the runner's FS must offer

All paths are normalised first. Every operation resolves its path by the walk in 3.4 and fails with
one of ENOENT, ENOTDIR, EACCES, ELOOP, EEXIST, EINVAL, EISDIR, ENOTEMPTY.

- `lstat(p)`: like `stat` but does not follow a link in the last component. Returns
  `{type, dev, ino, size, mode, mtime}` where `type` is `dir`, `file`, `symlink`, `junction`, `fifo`
  or `device`. A junction reports `junction`, never `symlink`.
- `stat(p)`: follows links in every component including the last. Max 40 link hops per call, the
  41st is ELOOP. Never returns a link type. A link whose target does not exist is ENOENT. A link
  with `unreadable: true` is EACCES on `stat` (and fine on `lstat`).
- `readlink(p)`: the stored `target` of a symlink or junction, else EINVAL.
- `readdir(p)`: follows links for `p`. Returns names in stored case, sorted bytewise ascending.
  EACCES if the dir is `unreadable`. ENOTDIR if not a dir.
- `realpath(p)`: follows every link, returns the absolute path made of the stored-case names of the
  nodes actually reached, with the same errors and hop limit as `stat`.
- `open(p, flags)` and `read`: flags are `RDONLY`, `NOFOLLOW` (fail with ELOOP if the last component
  is a symlink or junction), `NONBLOCK`, `CREAT_EXCL_WRONLY`. Opening a directory for reading is
  EISDIR. A file with `unreadable: true` is EACCES on open. A fifo opens with `NONBLOCK` and then
  has no data (read returns 0 bytes); the library must never read it anyway (A4 marker parsing).
  `read(h, cap)` returns at most `cap` bytes. Content is compared and sized as UTF-8 bytes.
- `mkdir(p, mode)`: EEXIST if `lstat(p)` would succeed. Parent must be an existing dir. New dir has
  the given mode and `mtime = now`.
- `write`: `open(p, CREAT_EXCL_WRONLY, mode)` creates a file (EEXIST if present), `write(h, bytes)`
  fills it, `fsync` is a no-op.
- `rename(a, b)`: moves node `a` (any type, a dir takes its subtree) to `b`. `b` may exist only if
  both are non-dirs (replaced) or both dirs and `b` empty. On win32 a rename where `a` or `b` is a
  `junction` and `b` exists fails with EEXIST, as Windows cannot replace a directory entry. Parent of `b` must exist. The moved node
  keeps its `(dev, ino)`; a replaced node disappears. A write that creates a temp file and renames
  it over the target leaves the target with the temp file's mode and a new inode.
- `symlink(target, p, kind)`: creates a link node. `kind` is `file` or `dir`. On win32 `dir` creates
  a `junction` node, `file` a `symlink` node; elsewhere always `symlink`. EEXIST if present. The
  target text is stored verbatim; it need not exist.
- `rmdir(p)`: removes an empty dir (ENOTEMPTY otherwise), or a `junction` (the link, never its target). On any
  other non-dir it is ENOTDIR. `unlink(p)`: removes a non-dir that is not a junction.

### 3.4 Path lookup, links, case

Lookup of an absolute path: start at the root node for its prefix (ENOENT if that root is not in
the fs; `cwd`'s root and `home`'s root always exist). Process components left to right. For each
component: `.` is skipped; `..` pops to the parent (stays at a root); otherwise the current node
must be a dir (ENOTDIR) that is not `unreadable` (EACCES), and the child is looked up by name
(ENOENT). When `caseInsensitive` the lookup compares `fold(name)`; the stored name is kept and
returned by `readdir` and `realpath`. When not `caseInsensitive` names compare exactly. If the child
is a link and it is not the last component (or it is last and the operation follows), count a hop
(ELOOP past 40), then splice its `target` in front of the remaining components: an absolute target
restarts at that target's root; a relative target continues from the directory that contained the
link. On win32 targets and paths accept both separators.

`unreadable: true` on a dir: `lstat` and `stat` of the dir itself succeed, but `readdir` and the
lookup of any child inside it fail with EACCES. On a file: `lstat`/`stat` succeed, `open` fails
with EACCES. On a link: `lstat` succeeds, `stat` fails with EACCES.

Two names that differ only by case in one dir are an invalid case when `caseInsensitive`.

### 3.5 Identity

Two paths are the same directory when `stat` of both succeeds and gives equal `(dev, ino)`. This is
the only identity test (A2 aliases, A4 claims). Link following happens in `stat`, so a link to a
directory has the directory's identity.

### 3.6 Dump format (runner output `fs`)

Same shape as the case `fs`: a flat map, one key per path reachable through the tree (not through
links), including implicit dirs and roots' children, with fields `type`, `mode` (always present,
four octal digits as a string), `content` (files; `contentBase64` instead when the bytes are not
valid UTF-8), `target` (links). `inode`, `dev` and `mtime` are
not required in the dump. Keys use the platform's separator and are normalised. A dir key appears
once per path it is reached by.

### 3.7 expectFs

A map path to either `null` (the path must not exist in the dump) or an object that is a subset
check: every field given must equal the dump's field. Allowed fields: `type`, `mode`, `content`,
`target`, and `contentJson` (the dump's `content` is parsed as JSON and deep compared with the
given value, key order irrelevant). Paths not listed are not checked, except for rule 7 above.

## 4. Fixed behaviours shared by every op

- **Account gate** (ops that take an account `name` and read or write inside it): validate grammar
  (`INVALID_NAME`), then `default` is always present; otherwise the account must be discovered
  (`ACCOUNT_NOT_FOUND`, path = `join(home, ".claude-"+name)`), and not dangling or unreadable
  (`ACCOUNT_UNAVAILABLE`, same path). Pure ops (`canonical_path`, `env`, `credential_locations`) do
  not gate.
- **Config home** of an account: `default` is `join(home, ".claude")`, a named account is its
  canonical path. All reads inside an account go through that path (links followed by the FS).
- **Global config file** of an account (A1): if `<config home>/.config.json` exists (`stat` ok and a
  file) it is that. Otherwise `.claude<suffix>.json` where suffix is `-custom-oauth` when
  `env.CLAUDE_CODE_CUSTOM_OAUTH_URL` is set and non-empty, else empty; for `default` it sits in
  `home`, for others in the config home. For a `CLAUDE_CONFIG_DIR` value `V` (resolve, source
  `config-dir`), the same rule with `V` as the config home (`join(V, ...)`, not NFC normalised); a
  relative `V` has none.
- **Reading JSON files**: read the whole file as UTF-8 (strictly, invalid bytes fail), parse. A
  missing file, a non-file, a read error or a parse failure all count as "no data" for B2 reads
  (result `null`), and as invalid for spec files (A3). Spec files and state files are also invalid
  when nested deeper than 100 levels (the top-level object is level 1).
- **Time**: instants are compared as instants. `now` is only whole seconds. When this suite writes
  a time it uses `YYYY-MM-DDTHH:MM:SSZ`, except `usage.fetchedAt` and `credentials.expiresAt`, which are
  `YYYY-MM-DDTHH:MM:SS.mmmZ`. An **RFC 3339 instant** (B5 `until`) matches
  `YYYY-MM-DDTHH:MM:SS(.f{1,9})?(Z|+HH:MM|-HH:MM)` with upper-case `T` and `Z`, a real calendar
  date, hour 0 to 23, minute and second 0 to 59 (no leap second), offset hour 0 to 23 and minute
  0 to 59.
- **Locks and atomic writes** (A3 file safety rules) as used by `create`, `mark_limited`,
  `clear_limited` and the slot ops. `lock(file)`: `mkdir <file>.lock` (mode 0700). If it exists and
  its `mtime` is more than 10 seconds before `now`, `rmdir` it and `mkdir` once more; any other
  `EEXIST`, including a lost race on that second `mkdir`, fails with error code `LOCK_BUSY` (path =
  the lock). The fake clock never advances, so there is no waiting: the suite pins immediate
  `LOCK_BUSY`, while real implementations MAY retry a bounded number of times first. The lock is
  named after the path as the spec names it (`<file>.lock`), not after a link target. Under the
  lock, if `<file>` is a symlink, `readlink` once and write to that target (relative targets resolve
  against the link's directory); the link stays. Write `<target>.tmp.<pid>.<12 hex>` with
  `CREAT_EXCL_WRONLY`, mode `0600`, then `rename` over the target. Finally `rmdir` the lock. The lock is
  released on error too. Every successfully written file ends with mode `0600`. Written JSON text
  format is free (tests parse it) but must be one JSON document.
- **Unexpected filesystem errors** that no rule above names are `IO_ERROR` (path = the path
  involved when known, else null).
- **Session liveness** (shared by `live_sessions`, `handover_session`, `adopt`, `activate`):
  a block means `SESSION_LIVE`. A session blocks when its status is `live`, or `unknown` and the
  op's `force` is not true. `force` never overrides `live`.
- **Reserved names**: the list from `spec/reserved.json` (`names[].name`) or the case's `reserved`.

## 5. Operations

Common inputs for every op come from the case top level: `platform`, `caseInsensitive`, `home`,
`cwd`, `env`, `options`, `now`, `processes`, `callerPidDomain`, `fs`. Results are JSON values.
Unless noted, strings that are paths use the platform separator.

### Part A

**`canonical_path`** args `{name}`. Result `{"path": "<nfc(join(home, '.claude-'+name))>"}`. For
`default` the path is `nfc(join(home, ".claude"))`. Fails `INVALID_NAME` if the name fails the
grammar and is not `default`. Reserved names are allowed (pure function). Never touches the fs.

**`discover`** args `{}`. This is `list()`. Result:

```
{"accounts": [Account...], "conflicts": [Conflict...], "warnings": [Warning...]}
```

`accounts[0]` is always `default`, then discovered named accounts sorted bytewise by name.
Account:

```
{"name", "configDir", "state": "ok"|"dangling"|"unreadable", "hasSpecFile": bool,
 "hasGlobalConfig": bool, "aliasOf": string|null,
 "specError": null | {"code": "SPEC_FILE_INVALID", "path": "<spec file path>"},
 "warnings": [Warning...]}
```

Algorithm: `readdir(home)` (if it fails, the named list is empty). For each stored name `n` that
starts with `.claude-` and whose remainder fully matches the grammar with exact case: `lstat`
the entry, then `stat` it.

- lstat is dir, or lstat is link and stat gives a dir: state `ok`.
- lstat is link and stat fails ENOENT or ELOOP: `dangling`. Stat fails EACCES: `unreadable`.
- stat gives a non-dir (file, fifo, device): not an account. Top-level warning
  `{"code":"NOT_A_DIRECTORY","path":"<entry path>"}`, entry omitted from `accounts`.
- lstat itself fails (EACCES etc.): `unreadable`.
- A listed account whose name is reserved gets account-level warning `{"code":"RESERVED_NAME"}`.
  `default` never gets it.

Top-level `warnings` holds only `NOT_A_DIRECTORY` entries. Entries whose name does not match the
grammar exactly (for example `.claude-Work`, `.claude-`, `.claude-a.b`) are ignored silently.

`default` is always listed with state `ok`, even if `~/.claude` is missing (then both `has*` are
false).

`hasSpecFile`: `lstat(<config home>/.multi-account.json)` succeeds and `stat` gives a regular file.
`hasGlobalConfig`: the effective global config file of section 4 exists as a regular file after
`stat`. Both are false when the account is not `ok`.

`aliasOf`: among accounts with state `ok`, group by `stat` identity of the config home. In a group
the representative is the first named member in name order; `default` is the representative only
when it is alone (a group of just `default`). Every member other than the representative gets
`aliasOf` = the representative's name; the representative gets null.

Spec file: `<config home>/.multi-account.json`. Absent (lstat ENOENT or ENOTDIR) means no spec file.
Present means: `stat` must give a regular file (a dir, a dangling link, an EACCES error, ELOOP are
all invalid), the content must be valid UTF-8 and parse as a JSON object nested at most 100 levels,
`version` must be the number 1, `priority` if present must be a number with an integer value
between -(2^53-1) and 2^53-1 (`2.0` is fine; `1.5`, `1e400`, strings and booleans are invalid),
`directories` if present must be an array of strings each of which is a valid claim. A valid claim
is an absolute path (section 2, Paths) or a string starting with `~/` (on win32 also `~\`), then
`join(home, rest)`; bare `~/` is `home`. `~`, `~user/...` and relative strings are invalid. Invalid
yields `specError` (and the account is otherwise listed normally). `label`, `createdAt`, `pool` and
unknown keys are not validated.

`conflicts`: for the accounts with state `ok`, valid spec, and only the representative of each alias
group, expand each claim (`~/` against home, then normalize), `stat` it (missing or error: ignored)
and group claims by identity. A group claimed by two or more distinct accounts is a conflict
`{"path": "<expanded claim of the first account in order>", "accounts": [names in order]}`
(order: `default` then names). Conflicts sorted by `path` bytewise.

**`resolve`** args `{}`. Implements A4 with these fixed details. Result:

```
{"account": str|null, "pool": str|null, "configDir": str|null, "canonical": bool,
 "reason": null|"not-normalized"|"case-mismatch"|"default-via-config-dir"|"resolved-target"|"foreign",
 "source": "env"|"config-dir"|"marker-file"|"claim"|"default",
 "matchedPath": str|null, "exists": bool, "aliasOf": str|null,
 "candidates": [str...], "applied": bool, "globalConfig": str|null,
 "launchEnv": null|{"set": {..}, "unset": [..]}, "overriddenBy": [..],
 "ignoredMarkers": [paths], "warnings": [codes]}
```

Step 0: for each of `CLAUDE_CONFIG_DIR`, `CLAUDE_MULTI_ACCOUNT`, `CLAUDE_MULTI_ACCOUNT_SOURCE`, in that
order, an empty value is treated as unset and adds one `EMPTY_ENV` warning (so two empty vars give
two warnings). Other variables are not checked for emptiness (`CLAUDE_SECURESTORAGE_CONFIG_DIR` counts
as set even when empty, see `overriddenBy`). Then `ignoreHookEnv` and `CLAUDE_MULTI_ACCOUNT_SOURCE ==
"hook"` unsets the other two.

Step 1 (M = `CLAUDE_MULTI_ACCOUNT`, V = `CLAUDE_CONFIG_DIR`):

1. M set and failing the grammar: `INVALID_NAME` immediately, before anything else (even if V is set).
2. V set: map it per `map_config_dir`.
3. Both set. They agree when the mapped account is not null and is the same account as M (same name,
   or both `ok` members of one alias group). If they do not agree: when M is not `default`, V is
   absolute and `nfc(normalize(V))` equals `canonical_path(M)`, run the account gate for M
   (`ACCOUNT_NOT_FOUND` path `join(home,".claude-"+M)`, or `ACCOUNT_UNAVAILABLE`); if that passes or
   the condition does not hold, `ENV_CONFLICT` (path null). When they agree, continue as "V set".
4. V set (alone or agreeing): `source: "config-dir"`, `configDir` = V verbatim, `canonical` and
   `reason` from the mapping, `exists` = `stat(V)` is a dir (false for a relative V, or on error),
   `globalConfig` from V (section 4), `matchedPath` null.
5. Only M set: the account gate for M (`default` is the default account; else `ACCOUNT_NOT_FOUND`
   path `join(home,".claude-"+M)`, `ACCOUNT_UNAVAILABLE`). `source: "env"`. If M is `default` or in
   `default`'s alias group: `applied` true. Otherwise: if `env.CLAUDECODE == "1"` then `ENV_CONFLICT`
   (path null); else `applied` false and the warning `ENV_NOT_APPLIED` is added.

Step 2 (no env selection): the walk, "The walk" below. Step 3: `account "default"`, `source "default"`.

Result fields by source:

- `env`, `marker-file`, `claim`, `default`: `canonical: true`, `reason: null`, `exists: true`,
  `configDir` is the account's canonical path (`join(home,".claude")` for default), `applied: true`
  (except step 1.5). `matchedPath`: marker path, or the claimed directory (the walk level's
  directory path, not the claim string), else null. `globalConfig` is the account's effective global
  config file (section 4).
- `candidates`: for a marker list the entries in order; `[account]` for a single name, claim, env,
  config-dir and default; `[]` for a pool and for a foreign config dir. `account` is `candidates[0]`
  whenever it is non-empty.
- Pool binding: `account: null`, `pool: "<pool>"`, `configDir: null`, `canonical: false`, `reason:
  null`, `exists: false`, `aliasOf: null`, `launchEnv: null`, `globalConfig: null`, `applied: true`,
  `source` `marker-file`, `matchedPath` the marker.
- Foreign config dir: `account: null`, `launchEnv: null`, `aliasOf: null`.
- `launchEnv` for an account is `env(name)` (below) with `set`/`unset` only. `overriddenBy` as
  `env` below, from the case env and the settings file at `<configDir>/settings.json` (for
  config-dir: `<V>/settings.json`; for a pool: none).
- `aliasOf`: as `discover`, for the resolved account (so `default` in a group with a named account
  reports the representative, and the representative reports null).
- Warnings: `EMPTY_ENV`, `NON_CANONICAL_CONFIG_DIR` (any mapping result with `canonical: false`,
  including foreign), `MARKER_IGNORED_IN_REPO` (one per ignored marker), `ENV_NOT_APPLIED`, `CANDIDATE_UNAVAILABLE` (one per unavailable later list entry; the warning's path
  is that entry's account path, compared by code only), and
  `RESERVED_NAME` when the resolved account is a named account whose name is reserved.
  `NOT_A_DIRECTORY` is never emitted by `resolve`.

**`map_config_dir`** args `{"value": "<V>"}`. The A4 mapping table on its own. Result
`{"account": str|null, "canonical": bool, "reason": ..., "warnings": [codes]}`. Candidates are
`default` and the discovered accounts with state `ok` (the `default` candidate only for rows 4 and
5). Rows in order, first match wins:

1. `V` equals (exact string) a discovered ok named account's canonical path: `canonical true`.
2. `n = nfc(normalize(V))` equals a named account's canonical path: `not-normalized`.
3. `caseInsensitive` and `fold(n)` equals `fold(canonical path)`: `case-mismatch`.
4. `n` equals `join(home, ".claude")` exactly: account `default`, `default-via-config-dir`.
5. `realpath(V)` succeeds and equals `realpath` of the config home of a candidate (named accounts
   in name order, then `default`): that account, `resolved-target`.
6. `account null`, `foreign`.

A relative `V` (not absolute in the platform's sense) skips rows 2 to 5 and is `foreign`. Warnings
are `["NON_CANONICAL_CONFIG_DIR"]` when `canonical` is false, else `[]`.

**`parse_marker`** args `{"path": "<marker file path>"}`. Result
`{"kind": "none"|"account"|"default"|"pool"|"list", "name": str|null, "pool": str|null,
"candidates": [str...]}`. `candidates` is `[]` for `none` and `pool`, `[name]` for `account` and
`default`, and the entries for `list` (where `name` is the first entry). Algorithm (A4): `lstat`;
ENOENT or ENOTDIR or EACCES: `none`. `stat` (follow): fails: `none` (dangling). A dir: `none`. Not
a regular file (fifo, device): `MARKER_INVALID` without opening. Regular: open `RDONLY|NONBLOCK`
(error such as EACCES: `MARKER_INVALID`), read at most 1025 bytes; more than 1024 bytes:
`MARKER_INVALID`. Decode UTF-8 strictly (invalid bytes: `MARKER_INVALID`, anywhere in the file),
strip one leading U+FEFF, split on `\n`, strip one trailing `\r` per line, trim each line (ASCII
space, tab, CR, VT, FF), skip empty lines and lines whose first character is `#`. The first
remaining line must be: a grammar-valid name (`account`), the literal `default` (`default`), `@`
plus a grammar-valid pool name (`pool`), or a list (below); else `MARKER_INVALID`. No remaining
line: `MARKER_INVALID`. Errors carry `path` = the marker path. Later lines are ignored. Never touches
anything else.

A line containing a comma is a list: split on `,`, trim each part with the same whitespace set.
Every part must be a grammar-valid name or the literal `default` (so an empty part, `@pool` or
anything else is invalid) and there must be no duplicates; else `MARKER_INVALID`. A line with a
comma always has two or more parts, so `work,` is invalid (empty second part).

**`create`** args `{name}`. Write op. Order of checks: `INVALID_NAME`, `RESERVED_NAME`, then
`ACCOUNT_EXISTS` if `lstat(join(home,".claude-"+name))` succeeds (any type, a dangling link
counts; on a case-insensitive fs a differently-cased entry counts), path = that path. Then
`mkdir` it mode `0700`, then atomic-write (section 4) `<dir>/.multi-account.json` with exactly the
JSON `{"version": 1, "createdAt": "<now>"}`. Result `{"name": name, "configDir": "<canonical path>"}`.
Error `path` for `INVALID_NAME` and `RESERVED_NAME` is null.

### The walk (A4 step 2)

1. `start = normalize(cwd)`. Levels: `start`, then each parent up to the root. If `ceilingDirs` is
   set, normalise each entry; a level whose directory equals (with `fold` when `caseInsensitive`) a
   ceiling entry is the last level.
2. `git[i]` = `lstat(<level i>/.git)` succeeds (any type; errors count as false).
3. A marker at level `i` is ignored in a git tree iff `trustRepoMarkers` is false and `git[j]` is true
   for some level `j >= i` within the walked levels (the level itself or any ancestor level the
   walk covers; the ceiling cuts the lookahead).
4. At each level from nearest: look at the entry `<level>/.claude-account`. If `lstat` fails: no
   marker. If it is a candidate marker (anything that `stat` shows as a non-directory: regular
   file, fifo, device; a dangling link and a directory are not candidates) and the level is in a
   git tree per 3 (and not trusted): append its path to `ignoredMarkers`, add warning
   `MARKER_IGNORED_IN_REPO`, do not read it, and go on to claims at this level. Otherwise run
   `parse_marker` on it; `none` falls through to claims; an error aborts the resolve; a result
   binds (`marker-file`).
5. Claims: load every account's spec file once (first time claims are needed), in order `default`
   then names, over discovered accounts with state `ok`. The first invalid spec file aborts with
   `SPEC_FILE_INVALID`, path = that spec file. Claims are not consulted if a marker bound at an
   earlier step, so an invalid spec file elsewhere is then invisible. Only the representative of
   each alias group claims. An account claims the level directory when `stat(<expanded claim>)` and
   `stat(<level dir>)` both succeed with equal `(dev, ino)`. One claimant binds (`claim`); two or
   more distinct claimants abort with `CLAIM_CONFLICT`, path = the level directory.
6. A binding target: every entry is looked up as in Step 1.5, in list order (`ACCOUNT_NOT_FOUND` path
   = the marker file path, or the level directory for a claim; `ACCOUNT_UNAVAILABLE` path = the
   account entry path); `default` is the default account; `@pool` is a pool result. A list binds its
   first entry, with `candidates` the whole list as written. Only the first entry is looked up as above;
   each later entry that is not a discovered `ok` account (undiscovered, dangling, unreadable) adds one
   `CANDIDATE_UNAVAILABLE` warning and no error.
7. No binding at any level: step 3.

### Part B

**`env`** args `{name, clearAuthOverrides?}`. Pure. Result `{"set": {..}, "unset": [..],
"overriddenBy": [..]}`. Named: `set` is `CLAUDE_CONFIG_DIR` = canonical path and
`CLAUDE_MULTI_ACCOUNT` = name. `default`: no `CLAUDE_CONFIG_DIR` in `set`; `CLAUDE_MULTI_ACCOUNT`
= `default`; `CLAUDE_CONFIG_DIR` is in `unset`. Always in `unset`: `CLAUDE_MULTI_ACCOUNT_SOURCE`,
`CLAUDE_SECURESTORAGE_CONFIG_DIR`. With `clearAuthOverrides`: also `CLAUDE_CODE_OAUTH_TOKEN`,
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
`CLAUDE_CODE_USE_FOUNDRY` and `ANTHROPIC_PROFILE`. `unset` is sorted bytewise ascending, no
duplicates. `INVALID_NAME` for a bad name. `overriddenBy`: the following, in this fixed order, those that
apply: `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_PROFILE`
(each if its value in `env` is non-empty, for the three `USE_*` truthy, i.e. trimmed lower-case
`1`, `true`, `yes` or `on`, and the variable is not cleared; or if the same holds for a string value
under `env` in `<config home>/settings.json`, which clearing does not remove), then
`CLAUDE_SECURESTORAGE_CONFIG_DIR` (if present in `env`, even empty), `CLAUDE_CODE_CUSTOM_OAUTH_URL`
(if non-empty in `env`), `apiKeyHelper` (if `<config home>/settings.json` parses as a JSON object
whose `apiKeyHelper` is a non-empty string). Each name at most once.

**`credential_locations`** args `{name}`. Pure. Result `{"locations": [...]}` of items
`{"file": path}`, `{"keychain": {"service", "account"}}`, `{"credentialManager": {}}`. `file` is
`<config home>/.credentials.json`.

- linux: `[file]`.
- darwin: `[keychain, file]`. `service` = `"Claude Code" + suffix + "-credentials"` for `default`;
  for a named account that plus `"-" + first 8 lowercase hex of sha256(utf8(config home))` where
  config home is the canonical path. `account` = `env.USER` if set and non-empty, else
  `options.userName` if set, else `claude-code-user`; replaced by `claude-code-user` if it does not
  fully match `[a-zA-Z0-9._-]+`. (`options.userName` stands for the OS user database entry the process
  wrapper reads.)
- win32: `[file]`, or `[credentialManager, file]` when Credential Manager is in use: `env.CLAUDE_CODE_FORCE_WINDOWS_CREDMAN == "1"`,
  or the account's global config (section 4) parses with `cachedGrowthBookFeatures.tengu_windows_credman === true`.

`suffix` is `-custom-oauth` when `env.CLAUDE_CODE_CUSTOM_OAUTH_URL` is set and non-empty.

**`identity`** args `{name}` or `{"resolve": true}`. With a name: account gate, then reads
`oauthAccount` from that account's global config. With `resolve: true`: runs `resolve` (its errors
are the result) and reads its `globalConfig`; a null `globalConfig` gives `null` and no gate runs.
Result `null` when there is no data or no `oauthAccount` object, else
`{"email", "orgName", "orgUuid", "organizationType", "billingType", "userRateLimitTier",
"organizationRateLimitTier"}` from `oauthAccount` keys `emailAddress`, `organizationName`,
`organizationUuid`, and the other four by the same name; a missing key is `null`.

**`usage`** args `{name}` or `{"resolve": true}` (as `identity`). Reads `cachedUsageUtilization` from
the global config. Result `null` when absent or not an object, else `{"fetchedAt": <string|null>,
"data": <the object verbatim>, "windows": {...}, "stale": bool}`. `fetchedAt` is `fetchedAtMs` (a number inside the object) as an RFC
3339 UTC string with exactly three fractional digits, `null` if `fetchedAtMs` is not a number.
`windows`: for each key of `data.utilization` (if that is an object) whose value is an object,
`{"utilization": <number or null>, "resetsAt": <string or null>}` from that value's `utilization`
(a number that is not a boolean) and `resets_at` (a string, kept as given); `{}` otherwise.
`stale` is true when `fetchedAtMs` is not a number (not a boolean), or `age = now - fetchedAtMs`
(milliseconds) is below 0 or above 3600000, or `data.accountUuid` (absent counts as undefined) is not
equal to the global config's `oauthAccount.accountUuid` (absent, or `oauthAccount` not an object, counts
as undefined).

**`credentials`** args `{name}`. Account gate. Reads `<config home>/.credentials.json` (never a keychain).
If `lstat` of the file shows a link: `null`. Otherwise read it as JSON; `null` when absent, unparseable
or not an object, or when `claudeAiOauth` is not an object with a non-empty string `accessToken`. Result
`{"source": "file", "path": <the file>, "accessToken", "expiresAt": <string|null>, "expired": bool,
"scopes": [strings], "subscriptionType": <string|null>, "rateLimitTier": <string|null>}`. `expiresAt`
is the number `expiresAt` (milliseconds since the epoch) as RFC 3339 UTC with three fractional digits,
else `null`; `expired` is `expiresAt <= now`, false when `expiresAt` is null. `scopes` keeps the string
elements of an array and is `[]` otherwise. No refresh token appears anywhere in the result.

**`live_sessions`** args `{name}`. Account gate. Lists `<config home>/sessions`, takes files whose
name fully matches `[1-9][0-9]{0,9}\.json` (ASCII digits), parses each (a file that is not a JSON
object is skipped). Result `{"sessions": [{"pid": int, "sessionId": str|null, "status":
"live"|"dead"|"unknown"}]}` sorted by pid ascending. `pid` is the number from the file name.
`sessionId` is the file's `sessionId` if a string, else null. Status: if the file's `pidDomain` is
present and differs from `callerPidDomain`: `unknown`; else if `processes[pid]` does not exist:
`dead`; else if the file's `procStartFt` is a non-empty string: `live` if it equals the process's
`procStartFt`, else `dead`; else if the file's `procStart` is a string: `live` if it equals the
process's `procStart`, else `dead`; else (the pid exists but the file has no start marker):
`unknown`. An entry with `lookupError: true` gives `unknown` (checked after the domain test and after
the absent-pid test, before any marker comparison). A missing `sessions` dir gives an empty list.

**`handover_session`** args `{id, from, to, overwrite?, force?}`. Write op. Order of checks:

1. `id` must fully match `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`: else `INVALID_SESSION_ID`.
2. Gate `from`, then `to`.
3. `from` equals `to`, or both are `ok` members of one alias group: `SAME_ACCOUNT`.
4. Parents: `projects`, each `projects/<slug>`, `file-history`, `session-env`, `tasks`. A parent that exists
   (`lstat`) and is not a plain `dir` (a link, a file) is never a location: nothing under it is read in
   `from` or written in `to`, and its relative path (`projects/<slug>`, `tasks`, ...) goes into `skipped`
   (for `from` only; a destination parent that is a link is handled in step 6). Source slugs: the
   plain-dir slugs of `from`. Source locations in `from`, by `lstat` (any type): `projects/<slug>/<id>.jsonl`
   and `projects/<slug>/<id>` for each source slug, `file-history/<id>`, `session-env/<id>`, `tasks/<id>`
   under plain-dir parents. If none is a regular file or a dir: `SESSION_NOT_FOUND`.
5. `SESSION_LIVE` if `live_sessions(from)` has a session with `sessionId == id` that blocks (section
   4).
6. For each source location, in list order, check the destination parents it needs in this order:
   `projects` then `projects/<slug>`, or `file-history`, `session-env`, `tasks`. A parent that
   exists (`lstat`) and is not a plain `dir` (link, file) fails with `DESTINATION_BLOCKED`, path =
   that destination parent. This is before `SESSION_EXISTS`, after `SESSION_LIVE`, and independent of
   `overwrite`. A destination parent that is a link but needed by no source location is ignored and
   not reported.
7. Destination locations: the five kinds under the union of the plain-dir slugs of `from` and of `to`
   (slugs that are links in `to` excluded), by `lstat` (a link at the location counts). If any exists
   and not `overwrite`: `SESSION_EXISTS`.
8. Plan the copy by walking every source location with `lstat` (links are never followed): a
   directory is walked in `readdir` order, a regular file is read and kept with its mode, anything
   else (symlink, junction, fifo, device) is recorded in `skipped` and not copied. A read error
   anywhere is `IO_ERROR` (path = the path that failed) and nothing at the destination has been
   changed.
9. With `overwrite`, remove every existing destination location (a link is unlinked, its target
   untouched). Create the planned directories with mode `0700` and the files with their mode. Never
   touch `from`.

Result `{"copied": [relative file paths, `/` separated, relative to the config home, sorted
bytewise], "skipped": [relative paths of skipped entries, sorted bytewise]}` (`copied` is files
only).

**`mark_limited`** args `{name, entry}` with `entry = {"window", "model", "until", "reason",
"updatedBy"}` (`model` may be null). Write op. Account gate, then entry validation (`INVALID_ENTRY`,
path null): `window` a non-empty string, `model` null or a non-empty string, `until` an RFC 3339
instant (section 4), `reason` and `updatedBy` strings if present. State file
`<config home>/.multi-account-state.json`. Under the lock (section 4) read the file: if `stat`
fails with ENOENT or ENOTDIR (also a link with a missing target) the state is
`{"version":1,"limits":[]}`; any other failure to read, a non-file, invalid UTF-8, unparseable or too
deeply nested JSON, a non-object, `version` that is not the number 1, or `limits` present but not an
array: `STATE_FILE_INVALID` (path = the state file, lock released, nothing written). A missing
`limits` is `[]`. The entry gets `updatedAt` = `now` and a null `model` if absent. Merge: key is
`(window, model)` (a missing model is null; entries that are not objects or lack a string `window`
have no key and never match); if an existing entry has the key, the new one replaces it when `new.until
>= old.until` (instants; an old entry with an unreadable `until` is replaced), otherwise the old one
stays; a new key is appended. Then drop every entry whose readable `until <= now`. All other entries
and keys are written back exactly as read. Write `{"version":1,"limits":[...]}` preserving other
top-level keys. Result `{"limits": [...]}` (the written list).

**`clear_limited`** args `{name, window, model}` (`model` may be null). Write op. Account gate.
If `lstat` of the state file fails: no write, result `{"limits": []}`. Else the same locked
read-merge-write with the same `STATE_FILE_INVALID` rule: remove the entries with that key, drop
entries whose readable `until <= now`, write, result `{"limits": [...]}`.

**`available`** args `{name, model?}`. Account gate. Result `{"available": bool}`. Entries from
the state file; a file that is missing or not understood (any condition of `mark_limited` that gives
`STATE_FILE_INVALID`) has none. Entries that are not objects or have no readable `until` are ignored.
An entry applies when its `model` is null or absent or equals the given `model`; with no `model` given
only entries whose `model` is null or absent apply. Available iff no applying entry has `until > now`.

**`pick`** args `{pool, model?}`. Result `{"account": str|null}`. `INVALID_NAME` for a bad pool
name. Members: `default` and the discovered ok accounts whose spec file is valid and has
`"pool": "<pool>"`. An invalid spec file in any ok account (default first, then names) is
`SPEC_FILE_INVALID` (path = the spec file), whether or not it names the pool. Alias group
duplicates are not members (only the representative of each group counts). Priority is the spec's
integer `priority`, default 0. Order: priority descending, then name bytewise ascending (`default` is just
a name here). Result is the first member that is available (B5 with `now` and `model`), else null.

**`next`** args `{pool, current, model?}`. Result `{"account": str|null}`. Members and order as
`pick`. Candidates are the members after `current` in order, then the members up to and including
`current`. If `current` is not a member, candidates are all members in order. Result is the first
available candidate, else null.

**`pick_from`** args `{candidates: [names], model?}`. Result `{"account": str|null}`. Every candidate
name is validated first (`INVALID_NAME`); a candidate that is not `default` or an `ok` account
(undiscovered, dangling, unreadable) is never available and is skipped, no error. Result is the first available candidate (B5 with `now` and `model`), else
null; an empty list gives null. Duplicates are not an error.

**`next_from`** args `{candidates, current, model?}`. Result `{"account": str|null}`. Gate as
`pick_from` (unavailable candidates are skipped, also in the final step). An alias group is one account: `pos` is the first candidate that is the same account as
`current` (same name, or members of one alias group). Candidates are those after `pos`, then those
before `pos`, each skipping any that are the same account as `current`, then the candidate at `pos`;
if no candidate matches `current`, all of them in order. Result is the first
available, else null.

**`limits`** args `{name}`. Account gate. Entries of the state file read as `available` reads it (a
file that is missing or not understood has none). Result `{"limits": [...]}` in file order: for each
entry that is an object with a string `window` and a readable `until`: `{"window", "model": <string or
null>, "until": <as stored>, "reason": <string or null>, "updatedBy": <string or null>, "updatedAt":
<string or null>}`. Past entries are included. Read op: nothing is written.

**`available_at`** args `{name, model?}`. Account gate. Entries and the applying rule as `available`.
Result `{"availableAt": <string|null>}`: `null` when no applying entry has `until > now`, else the latest
such `until` as UTC `YYYY-MM-DDTHH:MM:SSZ`, with `.fff` (milliseconds, truncated) added only when the
instant has non-zero milliseconds.

**`pool_members`** args `{pool}`. Result `{"members": [names]}`: the members of `pick`, in `pick`
order, without availability. Same errors as `pick` (`INVALID_NAME`, `SPEC_FILE_INVALID`).

**`session_of_pid`** args `{name, pid}`. Account gate. Result `{"sessionId": <string|null>}`: the string
`sessionId` of `<config home>/sessions/<pid>.json` if it parses to an object and the string is
non-empty, else `null`. A `pid` that is not an integer of at least 1 gives `null`. No liveness check.

**`project_slug`** args `{cwd}`. Pure; no account, no fs. Result `{"slug": str}`: each UTF-16 code unit
of `cwd` that is not `[A-Za-z0-9]` becomes `-`; if the result is longer than 200 characters it is
the first 200 characters, `-`, and the base 36 (lower-case digits) text of `abs(h)` where `h` starts
at 0 and for each UTF-16 code unit `c` of the ORIGINAL `cwd` becomes `(h * 31 + c)` wrapped to a signed
32-bit integer.

**`sessions_for`** args `{name, cwd}`. Account gate. `d = <config home>/projects/<project_slug(cwd)>`.
`projects` and `d` must be plain dirs by `lstat`, else the list is empty (so is a missing or unreadable
one). Entries of `readdir(d)` named `<id>.jsonl` with `<id>` fitting the session id grammar and
`lstat` giving a regular file (not a link) are listed. Result `{"sessions": [{"id", "mtime"}]}`,
`mtime` the file's mtime as UTC with exactly three fractional digits, sorted by mtime descending then
id ascending bytewise.

**`spec_file`** args `{name}`. Account gate. Result: the spec file object verbatim if valid (A3 rules
as in `discover`), `null` if absent, else error `SPEC_FILE_INVALID` (path = the file).

**`update_spec_file`** args `{name, patch}`. Write op. Account gate. `patch` not an object:
`INVALID_ENTRY`. Under the lock on `<config home>/.multi-account.json` (section 4): read it (absent:
`{"version": 1}`; invalid: `SPEC_FILE_INVALID`, path = the file, nothing written); copy it, then for each
key of `patch`: a null value deletes the key, any other value sets it; if the result fails the spec file
validity rules (version number 1, `priority`, `directories` entries, depth 100) it is `INVALID_ENTRY`
(path null, nothing written, lock released). Write it atomically (one hop through a link). Result: the
new object.

**`claim`** args `{name, dir}`. Write op. Account gate. `dir` must be absolute or start with `~/` (on
win32 also `~\`), else `INVALID_ENTRY`; `e` = its expansion (`~/` against home, then normalised). Stored form:
`~/` if `e` is `home`, `~/<rest>` (with `/` separators) if `e` is below `home` (case-folded when
`caseInsensitive`), else `e`. Checks in order: for each other account that is the representative of an
alias group other than this account's group, in order `default` then names, with state `ok`: an invalid spec
file is `SPEC_FILE_INVALID`; an entry that is the same directory as `e` is `CLAIM_CONFLICT` (path = `e`).
"Same directory": `stat` of both succeeds and the `(dev, ino)` are equal; if either `stat` fails, the
normalised paths are equal (with `fold` when `caseInsensitive`). Then under the lock: read the
account's file (absent: `{"version": 1}`, invalid: `SPEC_FILE_INVALID`); if an existing entry is the same
directory as `e` nothing is written (the file is not created either), else the stored form is appended to
`directories` (created if missing) and the file is written; a result that fails validation is `INVALID_ENTRY`.
Result `{"directories": [...]}`: the list afterwards (`[]` if there is no file).

**`unclaim`** args `{name, dir}`. Write op. Account gate; `dir` as `claim`. Under the lock, read the
file (absent: no write, `{"directories": []}`; invalid: `SPEC_FILE_INVALID`). Remove every entry that is
the same directory as `e`; write only if something was removed. Result `{"directories": [...]}`: the
list afterwards.

**`slot`** args `{}`. Result `{"state": "unmanaged"|"managed"|"broken"|"unsupported", "name":
str|null}` (`name` only for `managed`). Let `L = join(home,".claude")`, `J = join(home,".claude.json")`.

1. `unsupported` if `platform` is `darwin`; or `win32` and Credential Manager is in use (rule in
   `credential_locations`, global config read from `J`, one hop, via `stat`); or `win32` and
   `options.canCreateSymlinks` is false. This beats everything below.
2. `lstat(L)` fails with ENOENT or ENOTDIR: `unmanaged`; any other failure: `broken`. `L` is a dir
   (not a link): `unmanaged`.
3. `L` is a symlink or junction: `t = normalize(target resolved against home if relative)`. It must
   equal `join(home, ".claude-" + name)` for a grammar-valid `name` other than `default` (reserved
   names are fine), and `stat(t)` must give a dir (a link to a dir, a relocated account, is fine;
   missing or a non-dir is `broken`). `lstat(J)` must be a `symlink` (not junction; missing is `broken`)
   whose resolved target equals `join(t, ".claude.json")`. `lstat` of that target: missing is fine (a
   dangling link, Claude Code creates the file through it), a regular `file` is fine, anything else
   (a link, a dir) is `broken`. If `t/.credentials.json` exists (`lstat` ok) it must not be a link. All
   hold: `managed` with `name`, else `broken`.
4. Anything else (`L` a file, fifo...): `broken`.

**`adopt`** args `{name, force?}`. Write op. Checks in order: slot `unsupported` gives
`SLOT_UNSUPPORTED`; `INVALID_NAME` (grammar, and `default`); `RESERVED_NAME`; slot state not
`unmanaged` gives `SLOT_STATE`; `ACCOUNT_EXISTS` if `lstat(join(home,".claude-"+name))` succeeds
(path = that); `SLOT_CONFLICT` if `J` exists (`lstat`) and `L/.claude.json` exists (path =
`L/.claude.json`); `SLOT_TARGET_INVALID` if `J` exists and is not a regular file (path `J`), or `J`
is absent and `L/.claude.json` exists and is not a regular file (path that file), or
`L/.credentials.json` is a link (path that file). Lock: `mkdir join(home, ".claude-slot.lock")` with
the stale rule of section 4 (`LOCK_BUSY`). Under it: `live_sessions("default")` blocks per section 4
(`SESSION_LIVE`, lock released). Then, with `A = join(home, ".claude-"+name)`: if `L` exists `rename(L,
A)`, else `mkdir(A, 0700)`; if `J` exists `rename(J, A/.claude.json)`; `symlink(A, L, dir)`;
`symlink(A/.claude.json, J, file)` (absolute targets). Then `rmdir` the lock. Result: the recomputed
`slot()`.

**`activate`** args `{name, force?}`. Write op. Checks in order: `SLOT_UNSUPPORTED`; `INVALID_NAME`
(grammar, and `default`); the account gate for the target (`ACCOUNT_NOT_FOUND` path = its path,
`ACCOUNT_UNAVAILABLE`); slot state not `managed` gives `SLOT_STATE`; `SLOT_TARGET_INVALID` if the
target's `.credentials.json` is a link or its `.claude.json` exists and is not a regular file (path
that file). Lock as `adopt`. Under it: the current slot account's (`slot().name`) `live_sessions`
block per section 4 (`SESSION_LIVE`, lock released). Then `symlink(A/.claude.json, J.tmp.<pid>.<hex>,
file)` and `rename` over `J`; then on linux and darwin `symlink(A, L.tmp.<pid>.<hex>, dir)` and `rename`
over `L` (temp names in `home`), on win32 `rmdir(L)` (removes the junction) and `symlink(A, L, dir)`.
Then `rmdir` the lock. Result: the recomputed `slot()`. Activating the name already in the slot is a
normal success.

## 6. Error codes

Spec codes (SPEC.md A4 table): `INVALID_NAME`, `RESERVED_NAME`, `ACCOUNT_NOT_FOUND`,
`ACCOUNT_UNAVAILABLE`, `ACCOUNT_EXISTS`, `ENV_CONFLICT`, `MARKER_INVALID`, `CLAIM_CONFLICT`,
`SPEC_FILE_INVALID`, `INVALID_SESSION_ID`, `SAME_ACCOUNT`, `SESSION_NOT_FOUND`, `SESSION_LIVE`,
`SESSION_EXISTS`, `STATE_FILE_INVALID`, `INVALID_ENTRY`, `SLOT_UNSUPPORTED`, `SLOT_STATE`,
`SLOT_CONFLICT`, `SLOT_TARGET_INVALID`, `DESTINATION_BLOCKED`, `LOCK_BUSY`, `IO_ERROR`. Warning codes: `EMPTY_ENV`,
`ENV_NOT_APPLIED`, `NON_CANONICAL_CONFIG_DIR`, `NOT_A_DIRECTORY`, `MARKER_IGNORED_IN_REPO`,
`CANDIDATE_UNAVAILABLE`, `RESERVED_NAME`.
