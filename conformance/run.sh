#!/usr/bin/env bash
# Cross-library conformance: run every case in conformance/cases against each available runner
# (Go, TypeScript, Python), compare with the expected output, and compare runners with each other.
# Any failure or divergence is a parity break and gives a non-zero exit.
#
# Usage: conformance/run.sh [--runner go|ts|py]... [--case <glob>] [--cmd "<runner command>"] [-j N] [-v]
#   --runner   limit to one runner (repeatable). Default: every runner that exists.
#   --case     only cases whose id matches this glob (against the id, e.g. 'a4-*'). Default: all.
#   --cmd      run an extra runner given as a shell command (reported as "custom").
#   -j N       parallel jobs (default 8).
#   -v         print the expected/actual detail of every failure (default: first 20).
#   --require-all  fail if any of the go, ts or py runners is missing or fails to build (for CI).
# Runner protocol and comparison rules: conformance/FORMAT.md.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

want=()
case_glob='*'
custom=''
jobs=8
verbose=0
require_all=0
missing=0
while [ $# -gt 0 ]; do
  case "$1" in
    --runner) want+=("$2"); shift 2 ;;
    --case) case_glob="$2"; shift 2 ;;
    --cmd) custom="$2"; shift 2 ;;
    -j) jobs="$2"; shift 2 ;;
    -v) verbose=1; shift ;;
    --require-all) require_all=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

wanted() {
  [ ${#want[@]} -eq 0 ] && return 0
  local w
  for w in "${want[@]}"; do [ "$w" = "$1" ] && return 0; done
  return 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CCMA_REPO_ROOT="$ROOT"

runners=()   # name=command
if [ -n "$custom" ]; then
  runners+=("custom=$custom")
fi

if wanted go; then
  if [ -d clients/go/cmd/conformance-runner ]; then
    if [ -f clients/go/go.mod ]; then
      (cd clients/go && go build -o "$TMP/ccma-go" ./cmd/conformance-runner)
    else
      go build -o "$TMP/ccma-go" ./clients/go/cmd/conformance-runner
    fi
    if [ -x "$TMP/ccma-go" ]; then runners+=("go=$TMP/ccma-go"); else echo "NOTICE go: build failed"; missing=1; fi
  else
    echo "NOTICE go: runner not found (clients/go/cmd/conformance-runner), skipped"; missing=1
  fi
fi
if wanted ts; then
  if [ -f clients/typescript/dist/conformance-runner.js ]; then
    runners+=("ts=node clients/typescript/dist/conformance-runner.js")
  else
    echo "NOTICE ts: runner not found (clients/typescript/dist/conformance-runner.js), skipped"; missing=1
  fi
fi
if wanted py; then
  if [ -n "$(find clients/python -name conformance_runner.py -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null | head -n1)" ]; then
    runners+=("py=uv run --project clients/python python -m claude_code_multi_account.conformance_runner")
  else
    echo "NOTICE py: runner not found (conformance_runner.py under clients/python), skipped"; missing=1
  fi
fi

if [ "$require_all" = 1 ] && [ "$missing" = 1 ]; then
  echo "conformance: --require-all set and a runner is missing, failing"
  exit 1
fi

if [ ${#runners[@]} -eq 0 ]; then
  echo "conformance: no runner available, nothing was checked"
  exit 1
fi

python3 - "$ROOT" "$case_glob" "$jobs" "$verbose" "${runners[@]}" <<'PY'
import sys, os, json, glob, fnmatch, subprocess, concurrent.futures as cf

root, case_glob, jobs, verbose = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4] == '1'
runners = [a.split('=', 1) for a in sys.argv[5:]]
names = [n for n, _ in runners]

files = sorted(glob.glob(os.path.join(root, 'conformance', 'cases', '*.json')))
cases = []
for f in files:
    cid = os.path.basename(f)[:-5]
    if fnmatch.fnmatch(cid, case_glob):
        with open(f, encoding='utf-8') as fh:
            cases.append(json.load(fh))
if not cases:
    print('conformance: no cases match %r' % case_glob)
    sys.exit(1)


def num(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, float) and x == int(x):
        return int(x)
    return x


def norm(x, key=None):
    """Comparison normal form (FORMAT.md rules 1 to 3)."""
    if isinstance(x, dict):
        return {k: norm(v, k) for k, v in x.items()}
    if isinstance(x, list):
        if key == 'warnings':
            return sorted(w['code'] if isinstance(w, dict) else w for w in x)
        return [norm(v) for v in x]
    return num(x)


def dumps(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def short(x, n=700):
    s = dumps(x)
    return s if len(s) <= n else s[:n] + '...'


def content_form(c):
    try:
        return json.loads(c)
    except Exception:
        return c


def fs_form(fs):
    out = {}
    for p, e in sorted(fs.items()):
        d = {k: e[k] for k in ('type', 'mode', 'target') if k in e}
        if 'content' in e:
            d['content'] = content_form(e['content'])
        out[p] = d
    return out


WRITE_OPS = {'create', 'handover_session', 'mark_limited', 'clear_limited', 'adopt', 'activate', 'update_spec_file', 'claim', 'unclaim'}


def check(case, out):
    """Returns list of problems (empty = pass)."""
    bad = []
    exp = case['expect']
    if 'result' in exp:
        if 'error' in out:
            bad.append('expected a result, got error %s' % short(out['error']))
        elif 'result' not in out:
            bad.append('output has neither result nor error')
        elif dumps(norm(out['result'])) != dumps(norm(exp['result'])):
            bad.append('result differs\n      expected: %s\n      actual:   %s' % (short(norm(exp['result'])), short(norm(out['result']))))
    else:
        ee = exp['error']
        if 'result' in out:
            bad.append('expected error %s, got a result %s' % (ee['code'], short(out['result'], 300)))
        elif 'error' not in out:
            bad.append('output has neither result nor error')
        else:
            ae = out['error']
            if ae.get('code') != ee['code']:
                bad.append('error code: expected %s, got %s' % (ee['code'], ae.get('code')))
            elif 'path' in ee and (ae.get('path') or None) != (ee['path'] or None):
                bad.append('error path: expected %r, got %r' % (ee['path'], ae.get('path')))
    if case['op']['name'] in WRITE_OPS:
        fs = out.get('fs')
        if not isinstance(fs, dict):
            bad.append('write op output has no fs dump')
        else:
            efs = case.get('expectFs', {})
            for p, want in efs.items():
                have = fs.get(p)
                if want is None:
                    if have is not None:
                        bad.append('fs: %s must not exist' % p)
                    continue
                if have is None:
                    bad.append('fs: %s missing' % p)
                    continue
                for k, v in want.items():
                    if k == 'contentJson':
                        try:
                            got = json.loads(have.get('content', ''))
                        except Exception:
                            bad.append('fs: %s content is not JSON' % p)
                            continue
                        if dumps(norm(got)) != dumps(norm(v)):
                            bad.append('fs: %s JSON differs\n      expected: %s\n      actual:   %s' % (p, short(norm(v), 400), short(norm(got), 400)))
                    elif have.get(k) != v:
                        bad.append('fs: %s %s expected %r, got %r' % (p, k, v, have.get(k)))
            for p in fs:
                last = p.replace('\\', '/').rsplit('/', 1)[-1]
                if (('.tmp.' in last) or last.endswith('.lock')) and p not in efs:
                    bad.append('fs: leftover temp or lock %s' % p)
    return bad


def run_one(rname, cmd, case):
    try:
        r = subprocess.run(cmd, shell=True, input=json.dumps(case), capture_output=True, text=True, timeout=60, cwd=root)
    except subprocess.TimeoutExpired:
        return None, ['timeout after 60 s']
    if r.returncode != 0:
        return None, ['runner exit %d: %s' % (r.returncode, (r.stderr or r.stdout).strip()[:400])]
    try:
        out = json.loads(r.stdout)
    except Exception:
        return None, ['stdout is not one JSON document: %r' % r.stdout[:200]]
    if not isinstance(out, dict):
        return None, ['stdout JSON is not an object']
    return out, check(case, out)


def signature(case, out):
    """What two runners must agree on, independent of the expected value."""
    if out is None:
        return None
    s = {}
    if 'result' in out:
        s['result'] = norm(out['result'])
    if 'error' in out:
        e = out['error']
        s['error'] = {'code': e.get('code'), 'path': e.get('path') or None}
    if case['op']['name'] in WRITE_OPS and isinstance(out.get('fs'), dict):
        s['fs'] = fs_form(out['fs'])
    return dumps(s)


tasks = [(r, c, case) for case in cases for r, c in runners]
results = {}
with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
    futs = {ex.submit(run_one, r, c, case): (r, case['id']) for r, c, case in tasks}
    for f in cf.as_completed(futs):
        results[futs[f]] = f.result()

W = max(len(c['id']) for c in cases)
print('%-*s  %s' % (W, 'case', '  '.join('%-6s' % n for n in names)))
fails = {n: 0 for n in names}
diverge = []
details = []
for case in cases:
    cid = case['id']
    cells = []
    sigs = {}
    for n in names:
        out, bad = results[(n, cid)]
        cells.append('PASS' if not bad else 'FAIL')
        if bad:
            fails[n] += 1
            details.append((cid, n, bad))
        sigs[n] = signature(case, out)
    div = len(names) > 1 and len(set(sigs.values())) > 1
    if div:
        diverge.append(cid)
    print('%-*s  %s%s' % (W, cid, '  '.join('%-6s' % c for c in cells), '  DIVERGE' if div else ''))

print()
shown = details if verbose else details[:20]
for cid, n, bad in shown:
    print('FAIL [%s] %s' % (n, cid))
    for b in bad[:6]:
        print('    ' + b)
if len(details) > len(shown):
    print('... %d more failures (use -v)' % (len(details) - len(shown)))
if diverge:
    print('\nDIVERGENCE between runners on %d case(s): %s' % (len(diverge), ', '.join(diverge[:30])))

print('\nparity summary (%d cases)' % len(cases))
for n in names:
    print('  %-7s %d pass, %d fail' % (n, len(cases) - fails[n], fails[n]))
total_fail = sum(fails.values())
if total_fail == 0 and not diverge:
    print('conformance: ALL RUNNERS PASS' + (' (single runner, no cross-check)' if len(names) == 1 else ', NO DIVERGENCE'))
    sys.exit(0)
print('conformance: PARITY BREAK')
sys.exit(1)
PY
