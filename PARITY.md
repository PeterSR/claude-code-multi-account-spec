# Library parity matrix

Every library covers the full behaviour of [SPEC.md](SPEC.md). Method names are idiomatic per
language; **behaviour** must be identical and is enforced by the conformance suite
([`conformance/`](conformance), format in [`conformance/FORMAT.md`](conformance/FORMAT.md)). Any new
op or behaviour lands in the spec, the case files, and **all three libraries** in the same change.

Go package `multiaccount` (`go`), TypeScript package `claude-code-multi-account-core`
(`typescript`), Python distribution `claude-code-multi-account-core` with import name
`claude_code_multi_account` (`python`). Part A is mandatory in every library. Part B ops
apply to the blocks a library ships, but all three ship the same blocks.

Names below record the current library APIs; the libraries must match this table.

## Inputs and seams

| Capability | Go | TypeScript | Python |
|---|---|---|---|
| inputs `{env, cwd, home, platform}` | `Inputs{Env,Cwd,Home,Platform}` | `Inputs` object | `Inputs(env, cwd, home, platform)` |
| options `{trustRepoMarkers, ignoreHookEnv, ceilingDirs}` | `ResolveOptions` | `ResolveOptions` | `ResolveOptions` |
| filesystem seam (FORMAT.md 3.3) | `FS` interface | `Fs` interface | `Fs` protocol |
| process table seam (B3) | `ProcessTable` interface | `ProcessTable` interface | `ProcessTable` protocol |
| clock seam | `Clock` interface | `Clock` interface | `Clock` protocol |
| real-process convenience wrapper (never used by the core). Must fill `callerPidDomain` and the process table with Claude Code's `pidDomain` and `procStart`/`procStartFt` formulas (SPEC B3), `canCreateSymlinks` by probing, and `userName` from the OS user database | `FromProcess()` | `fromProcess()` | `from_process()` |
| reserved names (reads `spec/reserved.json`, embedded at build) | `ReservedNames()` | `reservedNames()` | `reserved_names()` |
| conformance runner | `cmd/conformance-runner` | `src/conformance-runner.ts` (built to `dist/`) | `conformance_runner.py` |

## Operations

| Capability | Case `op` | Spec | Go | TypeScript | Python |
|---|---|---|---|---|---|
| canonical path | `canonical_path` | A2 | `CanonicalPath(in, name)` | `canonicalPath(home, name, platform)` | `canonical_path(home, name, platform)` |
| list accounts | `discover` | A2 | `List(in)` | `list(in)` | `list_accounts(in)` |
| resolve | `resolve` | A4 | `Resolve(in, opts)` | `resolve(in, opts)` | `resolve(in, opts)` |
| map a config dir value | `map_config_dir` | A4 step 1 | `MapConfigDir(in, v)` | `mapConfigDir(in, v)` | `map_config_dir(in, v)` |
| parse a marker file | `parse_marker` | A4 marker parsing | `ParseMarker(fs, path)` | `parseMarker(fs, path)` | `parse_marker(fs, path)` |
| create an account | `create` | A2 | `Create(in, name)` | `create(in, name)` | `create(in, name)` |
| launch env delta | `env` | B1 | `Env(in, name, opts)` | `env(in, name, opts)` | `env(in, name, opts)` |
| credential locations | `credential_locations` | B1 | `CredentialLocations(in, name)` | `credentialLocations(in, name)` | `credential_locations(in, name)` |
| stored credentials (read only, no refresh token) | `credentials` | B2 | `Credentials(in, name)` | `credentials(in, name)` | `credentials(in, name)` |
| identity by name | `identity` | B2 | `Identity(in, name)` | `identity(in, name)` | `identity(in, name)` |
| identity of a resolution (`{resolve: true}`) | `identity` | B2 | `IdentityFor(in, res)` | `identityFor(in, res)` | `identity_for(in, res)` |
| cached usage by name (adds `windows`, `stale`) | `usage` | B2 | `Usage(in, name)` | `usage(in, name)` | `usage(in, name)` |
| cached usage of a resolution | `usage` | B2 | `UsageFor(in, res)` | `usageFor(in, res)` | `usage_for(in, res)` |
| live sessions | `live_sessions` | B3 | `LiveSessions(in, name)` | `liveSessions(in, name)` | `live_sessions(in, name)` |
| session handover (`overwrite`, `force`; result `copied` and `skipped`) | `handover_session` | B4 | `HandoverSession(in, id, from, to, opts)` | `handoverSession(in, id, from, to, opts)` | `handover_session(in, id, from, to, overwrite=False, force=False)` |
| mark limited | `mark_limited` | B5 | `MarkLimited(in, name, entry)` | `markLimited(in, name, entry)` | `mark_limited(in, name, entry)` |
| clear limited | `clear_limited` | B5 | `ClearLimited(in, name, window, model)` | `clearLimited(in, name, window, model)` | `clear_limited(in, name, window, model)` |
| available | `available` | B5 | `Available(in, name, now, model)` | `available(in, name, now, {model})` | `available(in, name, now, model=None)` |
| pick from pool | `pick` | B6 | `Pick(in, pool, now, model)` | `pick(in, pool, now, {model})` | `pick(in, pool, now, model=None)` |
| next in pool | `next` | B6 | `Next(in, pool, current, now, model)` | `next(in, pool, current, now, {model})` | `next_in_pool(in, pool, current, now, model=None)` |
| first available of an ordered list | `pick_from` | B6 | `PickFrom(in, candidates, now, model)` | `pickFrom(in, candidates, now, {model})` | `pick_from(in, candidates, now, model=None)` |
| next available of an ordered list, wrapping | `next_from` | B6 | `NextFrom(in, candidates, current, now, model)` | `nextFrom(in, candidates, current, now, {model})` | `next_from(in, candidates, current, now, model=None)` |
| limits of an account | `limits` | B5 | `Limits(in, name)` | `limits(in, name)` | `limits(in, name)` |
| when an account is next available | `available_at` | B5 | `AvailableAt(in, name, now, model)` | `availableAt(in, name, now, {model})` | `available_at(in, name, now, model=None)` |
| pool members in pick order | `pool_members` | B6 | `PoolMembers(in, pool)` | `poolMembers(in, pool)` | `pool_members(in, pool)` |
| session id of a pid | `session_of_pid` | B3 | `SessionOfPid(in, name, pid)` | `sessionOfPid(in, name, pid)` | `session_of_pid(in, name, pid)` |
| project folder name of a cwd (pure) | `project_slug` | B4 | `ProjectSlug(cwd)` | `projectSlug(cwd)` | `project_slug(cwd)` |
| sessions of a project, newest first | `sessions_for` | B4 | `SessionsFor(in, name, cwd)` | `sessionsFor(in, name, cwd)` | `sessions_for(in, name, cwd)` |
| read the validated spec file | `spec_file` | A3 | `SpecFile(in, name)` | `specFile(in, name)` | `spec_file(in, name)` |
| merge keys into the spec file | `update_spec_file` | A3 | `UpdateSpecFile(in, name, patch)` | `updateSpecFile(in, name, patch)` | `update_spec_file(in, name, patch)` |
| claim a directory | `claim` | A3 | `Claim(in, name, dir)` | `claim(in, name, dir)` | `claim(in, name, dir)` |
| release a directory | `unclaim` | A3 | `Unclaim(in, name, dir)` | `unclaim(in, name, dir)` | `unclaim(in, name, dir)` |
| slot state | `slot` | B7 | `Slot(in)` | `slot(in)` | `slot(in)` |
| adopt slot (`force`; named account only) | `adopt` | B7 | `Adopt(in, name, opts)` | `adopt(in, name, opts)` | `adopt(in, name, force=False)` |
| activate slot (`force`; named account only) | `activate` | B7 | `Activate(in, name, opts)` | `activate(in, name, opts)` | `activate(in, name, force=False)` |

Go note: `MarkLimited` takes a typed `LimitEntry` (`Window string`, `Model *string`, `Until time.Time`,
`Reason`, `UpdatedBy string`) instead of a map; the runner converts the case's entry. `until` is written as
RFC 3339 UTC. Where PARITY names `...For(in, res)`, TypeScript and Python may also keep accepting a resolution in
`identity`/`usage`.

Errors are one type per language carrying `code`, `message`, `path` (`Error`, `MultiAccountError`,
`MultiAccountError`). `code` strings are the spec's, identical in all three, and every unexpected
filesystem error surfaces as `IO_ERROR`, never as a raw platform error. Results use the field
names of the case files (`configDir`, `launchEnv`, `aliasOf`, ...) in each language's JSON mapping
(Go struct tags, TS object keys, Python dataclass fields in snake_case, serialised back to the
camelCase names by the conformance runner).

New result fields since spec v0.1: `resolve` returns `applied`, `candidates` and `globalConfig`; `handover_session`
returns `skipped`; the marker parser returns `candidates` and kind `list`; process table entries may carry
`procStartFt` or `lookupError` (a failed lookup, status `unknown`); the case format allows `contentBase64` file entries. `resolve` warnings include `CANDIDATE_UNAVAILABLE`; `pick_from`/`next_from` skip unusable candidates; `usage` returns `windows` and `stale`; `DESTINATION_BLOCKED` is a new error; file `mtime` may carry
milliseconds; `limits`, `available_at`, `pool_members`, `session_of_pid`, `project_slug`, `sessions_for`, `spec_file`,
`update_spec_file`, `claim` and `unclaim` are new suite ops. `credentials` is now a suite op and
never returns the refresh token.

## Rules

- **Behaviour parity is the contract; naming is idiomatic.** A capability missing in one library is a parity break.
- **Everything is an explicit input.** The core never reads process globals, the real clock, the real filesystem or the real process table; only the `from_process` wrapper does.
- **Constants and data come from the spec**, never re-derived per library: error and warning codes, `spec/reserved.json`, the name grammar (full match), the env variable names.
- **Empty lists are `[]`**, never null or nil, at every result surface (`warnings`, `overriddenBy`, `ignoredMarkers`, `unset`, `accounts`, `limits`, `copied`, `skipped`, `candidates`, `sessions`).
- **No network I/O, no credential rewriting, no token refresh** in any library.
- **Lock retry is the library's choice but must be bounded**; giving up is `LOCK_BUSY` (the suite pins the immediate form).
- **NFC is Unicode 16.0** in every library, with bundled tables (SPEC A2); a runtime warning does not suffice.
- Run [`/check-parity`](.claude/skills/check-parity/SKILL.md) (or `conformance/run.sh`) before merging any change that touches a library, the spec or the cases.
