#!/usr/bin/env python3
"""Self-check for conformance/cases/*.json. Stdlib only. Exit 1 on any problem.

Checks that every case parses, has the required fields (conformance/FORMAT.md section 2), uses known
op names and argument keys, has a well formed fake filesystem, and contains no em dash.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, 'cases')

REQUIRED = ['id', 'description', 'spec', 'platform', 'caseInsensitive', 'home', 'cwd', 'env', 'options', 'now', 'fs', 'op', 'expect']
OPTIONAL = ['processes', 'callerPidDomain', 'reserved', 'expectFs']
OPS = {
    'canonical_path': {'name'},
    'discover': set(),
    'resolve': set(),
    'map_config_dir': {'value'},
    'parse_marker': {'path'},
    'create': {'name'},
    'env': {'name', 'clearAuthOverrides'},
    'credential_locations': {'name'},
    'identity': {'name', 'resolve'},
    'usage': {'name', 'resolve'},
    'limits': {'name'}, 'available_at': {'name', 'model'}, 'spec_file': {'name'}, 'update_spec_file': {'name', 'patch'},
    'claim': {'name', 'dir'}, 'unclaim': {'name', 'dir'}, 'pool_members': {'pool'}, 'session_of_pid': {'name', 'pid'},
    'project_slug': {'cwd'}, 'sessions_for': {'name', 'cwd'},
    'credentials': {'name'},
    'live_sessions': {'name'},
    'handover_session': {'id', 'from', 'to', 'overwrite', 'force'},
    'mark_limited': {'name', 'entry'},
    'clear_limited': {'name', 'window', 'model'},
    'available': {'name', 'model'},
    'pick': {'pool', 'model'},
    'next': {'pool', 'current', 'model'},
    'pick_from': {'candidates', 'model'},
    'next_from': {'candidates', 'current', 'model'},
    'slot': set(),
    'adopt': {'name', 'force'},
    'activate': {'name', 'force'},
}
OP_REQUIRED = {
    'canonical_path': {'name'}, 'map_config_dir': {'value'}, 'parse_marker': {'path'}, 'create': {'name'},
    'env': {'name'}, 'credential_locations': {'name'}, 'credentials': {'name'}, 'pick_from': {'candidates'}, 'next_from': {'candidates', 'current'},
    'limits': {'name'}, 'available_at': {'name'}, 'spec_file': {'name'}, 'update_spec_file': {'name', 'patch'}, 'claim': {'name', 'dir'},
    'unclaim': {'name', 'dir'}, 'pool_members': {'pool'}, 'session_of_pid': {'name', 'pid'}, 'project_slug': {'cwd'}, 'sessions_for': {'name', 'cwd'},
    'live_sessions': {'name'}, 'handover_session': {'id', 'from', 'to'}, 'mark_limited': {'name', 'entry'},
    'clear_limited': {'name', 'window', 'model'}, 'available': {'name'}, 'pick': {'pool'}, 'next': {'pool', 'current'},
    'adopt': {'name'}, 'activate': {'name'},
}
WRITE_OPS = {'create', 'handover_session', 'mark_limited', 'clear_limited', 'adopt', 'activate', 'update_spec_file', 'claim', 'unclaim'}
OPTIONS_KEYS = {'trustRepoMarkers', 'ignoreHookEnv', 'ceilingDirs', 'canCreateSymlinks', 'userName'}
ERROR_CODES = {'DESTINATION_BLOCKED', 'INVALID_SESSION_ID', 'SAME_ACCOUNT', 'SLOT_CONFLICT', 'SLOT_TARGET_INVALID', 'STATE_FILE_INVALID', 'INVALID_ENTRY', 'IO_ERROR',
    'INVALID_NAME', 'RESERVED_NAME', 'ACCOUNT_NOT_FOUND', 'ACCOUNT_UNAVAILABLE', 'ACCOUNT_EXISTS', 'ENV_CONFLICT',
    'MARKER_INVALID', 'CLAIM_CONFLICT', 'SPEC_FILE_INVALID', 'SESSION_LIVE', 'SESSION_EXISTS', 'SLOT_UNSUPPORTED',
    'SESSION_NOT_FOUND', 'SLOT_STATE', 'LOCK_BUSY',
}
WARNING_CODES = {'CANDIDATE_UNAVAILABLE', 'ENV_NOT_APPLIED', 'EMPTY_ENV', 'NON_CANONICAL_CONFIG_DIR', 'NOT_A_DIRECTORY', 'MARKER_IGNORED_IN_REPO', 'RESERVED_NAME'}
ENTRY_TYPES = {'dir', 'file', 'symlink', 'junction', 'fifo', 'device'}
ENTRY_FIELDS = {'type', 'content', 'contentBase64', 'mode', 'target', 'inode', 'dev', 'unreadable', 'mtime'}
EXPECTFS_FIELDS = {'type', 'mode', 'content', 'target', 'contentJson'}
RFC3339 = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
RFC3339_FRAC = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,3})?Z$')
EM_DASH = '\u2014'


def split(plat, p):
    if plat == 'win32':
        m = re.match(r'^([A-Za-z]):\\', p)
        if not m:
            return None, None
        rest = p[3:]
        return m.group(1).upper() + ':', [c for c in rest.split('\\') if c != ''] if rest else []
    if not p.startswith('/'):
        return None, None
    return '/', [c for c in p.split('/') if c != '']


def is_normal(plat, p):
    root, comps = split(plat, p)
    if root is None:
        return False
    if '..' in comps or '.' in comps:
        return False
    sep = '\\' if plat == 'win32' else '/'
    if plat == 'win32' and '/' in p:
        return False
    if '//' in p or '\\\\' in p:
        return False
    if len(comps) > 0 and p.endswith(sep):
        return False
    return True


def check_case(path, problems):
    name = os.path.basename(path)
    cid = name[:-5]

    def bad(msg):
        problems.append('%s: %s' % (name, msg))

    with open(path, encoding='utf-8') as fh:
        raw = fh.read()
    if EM_DASH in raw:
        bad('contains an em dash')
    try:
        c = json.loads(raw)
    except Exception as e:
        bad('does not parse: %s' % e)
        return None
    if not isinstance(c, dict):
        bad('top level is not an object')
        return None
    for k in REQUIRED:
        if k not in c:
            bad('missing field %s' % k)
    for k in c:
        if k not in REQUIRED and k not in OPTIONAL:
            bad('unknown field %s' % k)
    if any(k not in c for k in REQUIRED):
        return c
    if c['id'] != cid:
        bad('id %r does not match file name' % c['id'])
    if not re.match(r'^(a[2-4]|b[1-7])-[a-z0-9-]+$', cid):
        bad('id must look like a2-... a4-... b1-... (lowercase, hyphens)')
    if not isinstance(c['description'], str) or not c['description']:
        bad('description must be a non-empty string')
    if not (isinstance(c['spec'], list) and c['spec'] and all(isinstance(s, str) and s for s in c['spec'])):
        bad('spec must be a non-empty list of strings')
    plat = c['platform']
    if plat not in ('linux', 'darwin', 'win32'):
        bad('platform must be linux, darwin or win32')
        return c
    if not isinstance(c['caseInsensitive'], bool):
        bad('caseInsensitive must be a bool')
    for k in ('home', 'cwd'):
        if not (isinstance(c[k], str) and split(plat, c[k].replace('/', '\\') if plat == 'win32' else c[k])[0] is not None):
            bad('%s must be an absolute %s path' % (k, plat))
    if not (isinstance(c['env'], dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in c['env'].items())):
        bad('env must map strings to strings')
    o = c['options']
    if not isinstance(o, dict) or set(o) - OPTIONS_KEYS:
        bad('options has unknown keys: %s' % (sorted(set(o) - OPTIONS_KEYS) if isinstance(o, dict) else o))
    elif 'ceilingDirs' in o and not (isinstance(o['ceilingDirs'], list) and all(isinstance(x, str) for x in o['ceilingDirs'])):
        bad('ceilingDirs must be a list of strings')
    if not (isinstance(c['now'], str) and RFC3339.match(c['now'])):
        bad('now must be RFC 3339 UTC with whole seconds, e.g. 2026-10-06T12:00:00Z')
    if 'reserved' in c and not (c['reserved'] is None or (isinstance(c['reserved'], list) and all(isinstance(x, str) for x in c['reserved']))):
        bad('reserved must be null or a list of names')
    if 'callerPidDomain' in c and not isinstance(c['callerPidDomain'], str):
        bad('callerPidDomain must be a string')
    for pid, pr in c.get('processes', {}).items():
        if not (pid.isdigit() and isinstance(pr, dict) and 'pidDomain' in pr and set(pr) <= {'procStart', 'procStartFt', 'pidDomain', 'lookupError'}):
            bad('processes entries must be pid -> {pidDomain, procStart?, procStartFt?, lookupError?}')

    # filesystem
    fs = c['fs']
    if not isinstance(fs, dict):
        bad('fs must be an object')
        fs = {}
    seen_inodes = {}
    for p, e in fs.items():
        if not is_normal(plat, p):
            bad('fs key %r is not an absolute normalised %s path' % (p, plat))
            continue
        if not isinstance(e, dict):
            bad('fs entry %r is not an object' % p)
            continue
        unknown = set(e) - ENTRY_FIELDS
        if unknown:
            bad('fs entry %r has unknown fields %s' % (p, sorted(unknown)))
        t = e.get('type')
        if t not in ENTRY_TYPES:
            bad('fs entry %r has bad type %r' % (p, t))
            continue
        if t == 'junction' and plat != 'win32':
            bad('junction only exists on win32 (%r)' % p)
        if t in ('symlink', 'junction') and not isinstance(e.get('target'), str):
            bad('link %r needs a string target' % p)
        if t not in ('symlink', 'junction') and 'target' in e:
            bad('%r: target only for links' % p)
        if ('content' in e or 'contentBase64' in e) and t != 'file':
            bad('%r: content only for files' % p)
        if 'content' in e and 'contentBase64' in e:
            bad('%r: content and contentBase64 are exclusive' % p)
        if 'content' in e and not isinstance(e['content'], str):
            bad('%r: content must be a string' % p)
        if 'mode' in e and not re.match(r'^0[0-7]{3}$', str(e['mode'])):
            bad('%r: mode must look like "0700"' % p)
        if 'inode' in e:
            if t not in ('dir', 'file') or not (isinstance(e['inode'], int) and 1 <= e['inode'] <= 999):
                bad('%r: inode must be 1..999 on a dir or file' % p)
            else:
                key = (e.get('dev', 1), e['inode'])
                if key in seen_inodes and seen_inodes[key] != t:
                    bad('%r: shared inode with different type' % p)
                seen_inodes[key] = t
        if 'mtime' in e and not RFC3339_FRAC.match(str(e['mtime'])):
            bad('%r: mtime must be RFC 3339 UTC (up to 3 fractional digits)' % p)
        if e.get('unreadable') not in (None, True, False):
            bad('%r: unreadable must be a bool' % p)
        # ancestors that are keys must be dirs
        root, comps = split(plat, p)
        sep = '\\' if plat == 'win32' else '/'
        for i in range(1, len(comps)):
            anc = (root + sep if plat == 'win32' else '/') + sep.join(comps[:i])
            if anc in fs and fs[anc].get('type') != 'dir':
                bad('%r lies below %r which is not a dir (keys must not go through links)' % (p, anc))
    if c['caseInsensitive']:
        by = {}
        for p in fs:
            k = re.sub(r'[A-Z]', lambda m: m.group(0).lower(), p)
            if k in by and by[k] != p and fs[p].get('inode') is None:
                bad('case-insensitive collision between %r and %r' % (by[k], p))
            by[k] = p

    # op
    opd = c['op']
    if not (isinstance(opd, dict) and set(opd) == {'name', 'args'} and isinstance(opd['args'], dict)):
        bad('op must be {name, args}')
    else:
        n = opd['name']
        if n not in OPS:
            bad('unknown op %r' % n)
        else:
            extra = set(opd['args']) - OPS[n]
            if extra:
                bad('op %s has unknown args %s' % (n, sorted(extra)))
            missing = OP_REQUIRED.get(n, set()) - set(opd['args'])
            if missing:
                bad('op %s misses args %s' % (n, sorted(missing)))
    # expect
    ex = c['expect']
    if not isinstance(ex, dict) or len(ex) != 1 or next(iter(ex)) not in ('result', 'error'):
        bad('expect must be exactly one of {result} or {error}')
    elif 'error' in ex:
        e = ex['error']
        if not (isinstance(e, dict) and set(e) <= {'code', 'path'} and 'code' in e):
            bad('expect.error must be {code, path?}')
        elif e['code'] not in ERROR_CODES:
            bad('unknown error code %r' % e['code'])
        elif e.get('path') is not None and not isinstance(e['path'], str):
            bad('error path must be a string or null')
    else:
        def walk(x, key=None):
            if isinstance(x, dict):
                for k, v in x.items():
                    walk(v, k)
            elif isinstance(x, list):
                if key == 'warnings':
                    for w in x:
                        if w not in WARNING_CODES:
                            bad('unknown warning code %r' % (w,))
                for v in x:
                    walk(v)
        walk(ex['result'])
    # expectFs
    if 'expectFs' in c:
        if opd.get('name') not in WRITE_OPS:
            bad('expectFs only applies to write ops')
        for p, w in c['expectFs'].items():
            if not is_normal(plat, p):
                bad('expectFs key %r is not a normalised %s path' % (p, plat))
            if w is not None and not (isinstance(w, dict) and set(w) <= EXPECTFS_FIELDS):
                bad('expectFs[%r] must be null or an object with fields %s' % (p, sorted(EXPECTFS_FIELDS)))
    elif opd.get('name') in WRITE_OPS and 'result' in ex:
        bad('write op with a result must have expectFs')
    return c


def main():
    files = sorted(glob.glob(os.path.join(CASES, '*.json')))
    if not files:
        print('no case files in %s' % CASES)
        return 1
    problems = []
    counts = {}
    for f in files:
        c = check_case(f, problems)
        prefix = os.path.basename(f).split('-')[0]
        counts[prefix] = counts.get(prefix, 0) + 1
    for name in ('FORMAT.md', 'SPEC-GAPS.md', 'run.sh', 'validate_cases.py'):
        p = os.path.join(HERE, name)
        if os.path.exists(p) and EM_DASH in open(p, encoding='utf-8').read():
            problems.append('%s contains an em dash' % name)
    for p in problems:
        print('PROBLEM ' + p)
    print('%d case files: %s' % (len(files), ', '.join('%s=%d' % kv for kv in sorted(counts.items()))))
    print('validate_cases: %s' % ('FAILED, %d problem(s)' % len(problems) if problems else 'OK'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
