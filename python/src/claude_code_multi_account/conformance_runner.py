"""Conformance runner: reads one case on stdin, writes one JSON object on stdout.

Run as `python -m claude_code_multi_account.conformance_runner`. It builds the fake world from the
case (in-memory filesystem, fixed clock, fake process table) and calls the public API.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from . import (
    FixedClock,
    LimitEntry,
    Resolution,
    Inputs,
    MemoryFs,
    MultiAccountError,
    ProcessInfo,
    ResolveOptions,
    activate,
    adopt,
    available,
    available_at,
    canonical_path,
    claim,
    credentials,
    clear_limited,
    create,
    credential_locations,
    env,
    handover_session,
    identity,
    identity_for,
    limits,
    pool_members,
    project_slug,
    session_of_pid,
    sessions_for,
    spec_file,
    unclaim,
    update_spec_file,
    usage_for,
    list_accounts,
    live_sessions,
    map_config_dir,
    mark_limited,
    next_from,
    next_in_pool,
    pick_from,
    parse_marker,
    pick,
    reserved_names,
    resolve,
    slot,
    usage,
)
from .models import jsonable
from .timeutil import parse_time

WRITE_OPS = {"update_spec_file", "claim", "unclaim", "create", "handover_session", "mark_limited", "clear_limited", "adopt", "activate"}


class _FakeProcessTable:
    def __init__(self, table: Mapping[str, Mapping[str, str]]) -> None:
        self._table = table

    def lookup(self, pid: int) -> ProcessInfo | None:
        row = self._table.get(str(pid))
        if row is None:
            return None
        return ProcessInfo(row["pidDomain"], row.get("procStart"), row.get("procStartFt"), bool(row.get("lookupError")))


def _reserved(case: Mapping[str, Any]) -> tuple[str, ...]:
    if case.get("reserved") is not None:
        return tuple(case["reserved"])
    root = os.environ.get("CCMA_REPO_ROOT") or "."
    return reserved_names(Path(root) / "spec" / "reserved.json")


def _build(case: Mapping[str, Any]) -> tuple[Inputs, MemoryFs]:
    now = parse_time(case["now"])
    opts = case.get("options", {})
    fs = MemoryFs(
        case["fs"],
        platform=case["platform"],
        case_insensitive=case["caseInsensitive"],
        now=now,
        extra_roots=[case["home"], case["cwd"]],
    )
    inp = Inputs(
        env=case["env"],
        cwd=case["cwd"],
        home=case["home"],
        platform=case["platform"],
        fs=fs,
        clock=FixedClock(now),
        processes=_FakeProcessTable(case.get("processes", {})),
        caller_pid_domain=case.get("callerPidDomain", "host-1"),
        reserved=_reserved(case),
        user_name=opts.get("userName"),
        can_create_symlinks=opts.get("canCreateSymlinks", True),
        case_insensitive=case["caseInsensitive"],
    )
    return inp, fs


def _entry(e: Mapping[str, Any]) -> LimitEntry:
    return LimitEntry(e.get("window"), e.get("model"), e.get("until"), e.get("reason"), e.get("updatedBy"))  # type: ignore[arg-type]


def _run_op(inp: Inputs, case: Mapping[str, Any]) -> Any:
    op = case["op"]["name"]
    args = case["op"].get("args", {})
    o = case.get("options", {})
    options = ResolveOptions(
        trust_repo_markers=bool(o.get("trustRepoMarkers", False)),
        ignore_hook_env=bool(o.get("ignoreHookEnv", False)),
        ceiling_dirs=tuple(o.get("ceilingDirs", [])),
    )
    ops: dict[str, Callable[[], Any]] = {
        "canonical_path": lambda: {"path": canonical_path(inp.home, args["name"], inp.platform)},
        "discover": lambda: list_accounts(inp),
        "resolve": lambda: resolve(inp, options),
        "map_config_dir": lambda: map_config_dir(inp, args["value"]),
        "parse_marker": lambda: parse_marker(inp.fs, args["path"]),
        "create": lambda: create(inp, args["name"]),
        "env": lambda: env(inp, args["name"], bool(args.get("clearAuthOverrides"))),
        "credential_locations": lambda: {"locations": credential_locations(inp, args["name"])},
        "identity": lambda: identity_for(inp, resolve(inp, options)) if args.get("resolve") else identity(inp, args["name"]),
        "usage": lambda: usage_for(inp, resolve(inp, options)) if args.get("resolve") else usage(inp, args["name"]),
        "limits": lambda: limits(inp, args["name"]),
        "available_at": lambda: {"availableAt": available_at(inp, args["name"], args.get("model"))},
        "pool_members": lambda: {"members": pool_members(inp, args["pool"])},
        "session_of_pid": lambda: {"sessionId": session_of_pid(inp, args["name"], args["pid"])},
        "project_slug": lambda: {"slug": project_slug(args["cwd"])},
        "sessions_for": lambda: {"sessions": sessions_for(inp, args["name"], args["cwd"])},
        "spec_file": lambda: spec_file(inp, args["name"]),
        "update_spec_file": lambda: update_spec_file(inp, args["name"], args["patch"]),
        "claim": lambda: claim(inp, args["name"], args["dir"]),
        "unclaim": lambda: unclaim(inp, args["name"], args["dir"]),
        "credentials": lambda: credentials(inp, args["name"]),
        "pick_from": lambda: {"account": pick_from(inp, args["candidates"], args.get("model"))},
        "next_from": lambda: {
            "account": next_from(inp, args["candidates"], args["current"], args.get("model"))
        },
        "handover_session": lambda: handover_session(
            inp, args["id"], args["from"], args["to"], bool(args.get("overwrite")), bool(args.get("force"))
        ),
        "mark_limited": lambda: mark_limited(inp, args["name"], _entry(args["entry"])),
        "clear_limited": lambda: clear_limited(inp, args["name"], args["window"], args.get("model")),
        "available": lambda: {"available": available(inp, args["name"], args.get("model"))},
        "pick": lambda: {"account": pick(inp, args["pool"], args.get("model"))},
        "next": lambda: {"account": next_in_pool(inp, args["pool"], args["current"], args.get("model"))},
        "slot": lambda: slot(inp),
        "adopt": lambda: adopt(inp, args["name"], bool(args.get("force"))),
        "activate": lambda: activate(inp, args["name"], bool(args.get("force"))),
        "live_sessions": lambda: {"sessions": live_sessions(inp, args["name"])},
    }
    if op not in ops:
        raise NotImplementedError(f"op {op!r} is not implemented")
    return ops[op]()


def main() -> int:
    case = json.load(sys.stdin)
    inp, fs = _build(case)
    out: dict[str, Any] = {}
    try:
        out["result"] = jsonable(_run_op(inp, case))
    except MultiAccountError as e:
        out["error"] = {"code": e.code, "path": e.path, "message": e.message}
    if case["op"]["name"] in WRITE_OPS:
        out["fs"] = fs.dump()
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
