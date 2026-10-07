# Open spec gaps

All gaps from the first suite are resolved and folded into [SPEC.md](../SPEC.md) (draft v0.2.1), which
is sufficient on its own. What is left:

## Owner calls

1. **Read ops and the filesystem.** Requiring every runner to dump the fs on read ops, so `run.sh`
   can check they change nothing, needs a change in all three runners.
2. **More reserved names.** `claude-code-router` and `claude-squad` are not in `spec/reserved.json`
   until checked.
3. **Core lock wait default.** Python's core waits 0 unless set, TS waits up to 2000 ms when the clock
   has `sleep`; the wrappers agree (2 s). Pick one core default.

## Unverified facts

4. The macOS and Windows `pidDomain` and `procStart` formulas, and `procStartFt` (a FILETIME string),
   were read from the Linux 2.1.292 bundle. On Windows Claude Code does not compare two numeric
   markers exactly (it treats values on opposite sides of 3e17 as the same process, probably a
   two-unit tolerance); the spec compares exactly.
5. The Windows Credential Manager target name is unknown, so the item carries no fields.
6. The Windows part of B7 (junctions, remove-then-create, symlink probe) has not run on Windows.
7. `credentials.expired` has no safety margin; Claude Code refreshes early, so a caller wanting margin
   compares `expiresAt` itself.

## Not expressible in the case format

8. Real lock retry and lost stale-takeover races (a fake clock whose `sleep` advances time would
   make retry testable), failure injection (`adopt` rollback, a failed temp-sibling swap), the link
   probe failing (`IO_ERROR` off Windows, `SLOT_UNSUPPORTED` on it), `O_NONBLOCK` and `O_NOFOLLOW`
   source opens, unreadable `machine-id` or pid namespace inputs to the process wrapper, and
   bundled Unicode 16.0 tables on older runtimes. They need library unit tests.

## Added in v0.2.2

9. Not run on other platforms: the project folder rule and the cache and session fields were read from the
   Linux 2.1.292 bundle and live Linux files. Claude Code can override the project folder through an
   internal setting; the spec ignores it.
10. `usage` reads the cache only. Claude Code's status line payload carries live `rate_limits`, which this
    spec does not read (the library sees no status line payload).
11. `claim` compares a missing directory by normalised path only; two different spellings that become the
    same directory later are not seen as a conflict until both exist.
