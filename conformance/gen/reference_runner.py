#!/usr/bin/env python3
"""Reference runner for case authors, NOT one of the three libraries.

It implements conformance/FORMAT.md in one file so that the hand written expected values in
conformance/cases can be cross-checked: every case must pass here. Run it with
  conformance/run.sh --cmd "python3 conformance/gen/reference_runner.py" --runner none
"""
import sys, json, re, hashlib, unicodedata, datetime, os, base64

NAME_RE = re.compile(r'[a-z0-9][a-z0-9_-]{0,31}')
SESSION_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}')
PID_FILE_RE = re.compile(r'([1-9][0-9]{0,9})\.json')
RFC3339_RE = re.compile(r'(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(\.\d{1,9})?(Z|[+-]\d\d:\d\d)')
MAX_INT = 2 ** 53 - 1
MAX_DEPTH = 100
LINKS = ('symlink', 'junction')


class Err(Exception):
    def __init__(self, code, path=None):
        self.code, self.path = code, path


class FsErr(Exception):
    def __init__(self, code):
        self.code = code


def valid_name(n):
    return isinstance(n, str) and NAME_RE.fullmatch(n) is not None


def fold(s):
    return ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in s)


def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_ts(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))


class Path:
    def __init__(self, platform):
        self.win = platform == 'win32'
        self.sep = '\\' if self.win else '/'

    def split(self, p):
        """returns (root or None, comps)"""
        if self.win:
            m = re.match(r'^([A-Za-z]):[\\/]', p)
            if m:
                return m.group(1) + ':\\', [c for c in re.split(r'[\\/]+', p[3:]) if c != '']
            return None, [c for c in re.split(r'[\\/]+', p) if c != '']
        if p.startswith('/'):
            return '/', [c for c in p.split('/') if c != '']
        return None, [c for c in p.split('/') if c != '']

    def is_abs(self, p):
        return self.split(p)[0] is not None

    def norm(self, p):
        root, comps = self.split(p)
        out = []
        for c in comps:
            if c == '.':
                continue
            if c == '..':
                if out and out[-1] != '..':
                    out.pop()
                elif root is None:
                    out.append('..')
                continue
            out.append(c)
        if root is None:
            return self.sep.join(out) or '.'
        return root + self.sep.join(out)

    def join(self, *parts):
        return self.norm(self.sep.join(parts))

    def dirname(self, p):
        root, comps = self.split(self.norm(p))
        if not comps:
            return root
        return root + self.sep.join(comps[:-1])

    def basename(self, p):
        root, comps = self.split(p)
        return comps[-1] if comps else ''

    def parent(self, p):
        root, comps = self.split(p)
        if not comps:
            return None
        return root + self.sep.join(comps[:-1])


class Node:
    def __init__(self, type, **kw):
        self.type = type
        self.children = {} if type == 'dir' else None
        self.content = b''
        self.target = None
        self.dev = 1
        self.ino = 0
        self.mode = '0644'
        self.mtime = None
        self.unreadable = False
        self.__dict__.update(kw)


class Fs:
    def __init__(self, case):
        self.P = Path(case['platform'])
        self.ci = case['caseInsensitive']
        self.now = parse_ts(case['now'])
        self.roots = {}
        self.auto = 1000
        self.byino = {}
        fsd = case['fs']
        # roots
        keys = list(fsd.keys())
        for extra in (case['home'], case['cwd']):
            r, _ = self.P.split(extra)
            self.root(r)
        for k in keys:
            r, _ = self.P.split(k)
            self.root(r)

        def depth(k):
            return len(self.P.split(k)[1])
        for k in sorted(keys, key=lambda k: (depth(k), k)):
            self.load(k, fsd[k])

    def rk(self, r):
        return fold(r) if self.ci else r

    def root(self, r):
        k = self.rk(r)
        if k not in self.roots:
            n = Node('dir', mode='0755', mtime=self.now, ino=self.newino())
            n.rname = r
            self.roots[k] = n
        return self.roots[k]

    def newino(self):
        self.auto += 1
        return self.auto - 1

    def child(self, d, name):
        if self.ci:
            for k, v in d.children.items():
                if fold(k) == fold(name):
                    return k, v
            return None, None
        v = d.children.get(name)
        return (name, v) if v else (None, None)

    def ensure_dir(self, path):
        r, comps = self.P.split(path)
        cur = self.root(r)
        for c in comps:
            k, v = self.child(cur, c)
            if v is None:
                v = Node('dir', mode='0755', mtime=self.now, ino=self.newino())
                cur.children[c] = v
            assert v.type == 'dir', path
            cur = v
        return cur

    def load(self, key, e):
        t = e['type']
        parent = self.ensure_dir(self.P.parent(key))
        name = self.P.split(key)[1][-1]
        mt = parse_ts(e['mtime']) if 'mtime' in e else self.now
        defaults = {'dir': '0755', 'file': '0644', 'symlink': '0777', 'junction': '0777'}
        mode = e.get('mode', defaults.get(t, '0644'))
        if 'inode' in e:
            ik = (e.get('dev', 1), e['inode'])
            if ik in self.byino:
                n = self.byino[ik]
                parent.children[name] = n
                return
        n = Node(t, mode=mode, mtime=mt, dev=e.get('dev', 1), unreadable=e.get('unreadable', False))
        if 'inode' in e:
            n.ino = e['inode']
            self.byino[(n.dev, n.ino)] = n
        else:
            n.ino = self.newino()
        if t == 'file':
            if 'contentBase64' in e:
                n.content = base64.b64decode(e['contentBase64'])
            else:
                n.content = e.get('content', '').encode('utf-8')
        if t in LINKS:
            n.target = e['target']
        if name in parent.children:
            # implicit dir replaced by explicit
            old = parent.children[name]
            if old.type == 'dir' and t == 'dir':
                n.children = old.children
        parent.children[name] = n

    def walk(self, path, follow_last=True):
        root, comps = self.P.split(path)
        if root is None:
            raise FsErr('ENOENT')
        k = self.rk(root)
        if k not in self.roots:
            raise FsErr('ENOENT')
        stack = [(self.roots[k].rname, self.roots[k])]
        queue = list(comps)
        hops = 0
        while queue:
            c = queue.pop(0)
            if c in ('', '.'):
                continue
            if c == '..':
                if len(stack) > 1:
                    stack.pop()
                continue
            cur = stack[-1][1]
            if cur.type != 'dir':
                raise FsErr('ENOTDIR')
            if cur.unreadable:
                raise FsErr('EACCES')
            name, ch = self.child(cur, c)
            if ch is None:
                raise FsErr('ENOENT')
            if ch.type in LINKS and (queue or follow_last):
                hops += 1
                if hops > 40:
                    raise FsErr('ELOOP')
                if ch.unreadable:
                    raise FsErr('EACCES')
                r2, c2 = self.P.split(ch.target)
                if r2 is not None:
                    k2 = self.rk(r2)
                    if k2 not in self.roots:
                        raise FsErr('ENOENT')
                    stack = [(self.roots[k2].rname, self.roots[k2])]
                queue = list(c2) + queue
                continue
            stack.append((name, ch))
        return stack

    def lstat(self, p):
        return self.walk(p, False)[-1][1]

    def stat(self, p):
        return self.walk(p, True)[-1][1]

    def realpath(self, p):
        st = self.walk(p, True)
        return st[0][0] + self.P.sep.join(n for n, _ in st[1:])

    def readdir(self, p):
        n = self.stat(p)
        if n.type != 'dir':
            raise FsErr('ENOTDIR')
        if n.unreadable:
            raise FsErr('EACCES')
        return sorted(n.children.keys())

    def readlink(self, p):
        n = self.lstat(p)
        if n.type not in LINKS:
            raise FsErr('EINVAL')
        return n.target

    def read(self, p, cap):
        n = self.stat(p)
        if n.type == 'dir':
            raise FsErr('EISDIR')
        if n.unreadable:
            raise FsErr('EACCES')
        return n.content[:cap]

    def parent_name(self, p):
        p = self.P.norm(p)
        par = self.P.parent(p)
        pn = self.stat(par)
        if pn.type != 'dir':
            raise FsErr('ENOTDIR')
        return pn, self.P.split(p)[1][-1]

    def mkdir(self, p, mode):
        try:
            self.lstat(p)
            raise FsErr('EEXIST')
        except FsErr as e:
            if e.code != 'ENOENT':
                raise
        pn, name = self.parent_name(p)
        pn.children[name] = Node('dir', mode=mode, mtime=self.now, ino=self.newino())

    def create_file(self, p, data, mode):
        try:
            self.lstat(p)
            raise FsErr('EEXIST')
        except FsErr as e:
            if e.code != 'ENOENT':
                raise
        pn, name = self.parent_name(p)
        pn.children[name] = Node('file', mode=mode, mtime=self.now, ino=self.newino(), content=data)

    def symlink(self, target, p, kind):
        try:
            self.lstat(p)
            raise FsErr('EEXIST')
        except FsErr as e:
            if e.code != 'ENOENT':
                raise
        pn, name = self.parent_name(p)
        t = 'junction' if (self.P.win and kind == 'dir') else 'symlink'
        pn.children[name] = Node(t, mode='0777', mtime=self.now, ino=self.newino(), target=target)

    def rename(self, a, b):
        apn, an = self.parent_name(a)
        k, node = self.child(apn, an)
        if node is None:
            raise FsErr('ENOENT')
        bpn, bn = self.parent_name(b)
        bk, ex = self.child(bpn, bn)
        if ex is not None:
            if self.P.win and (ex.type == 'junction' or node.type == 'junction'):
                raise FsErr('EEXIST')
            if (ex.type == 'dir') != (node.type == 'dir'):
                raise FsErr('EEXIST')
            if ex.type == 'dir' and ex.children:
                raise FsErr('ENOTEMPTY')
            del bpn.children[bk]
        del apn.children[k]
        bpn.children[bn] = node

    def rmdir(self, p):
        pn, name = self.parent_name(p)
        k, n = self.child(pn, name)
        if n is None:
            raise FsErr('ENOENT')
        if n.type == 'junction':
            del pn.children[k]
            return
        if n.type != 'dir':
            raise FsErr('ENOTDIR')
        if n.children:
            raise FsErr('ENOTEMPTY')
        del pn.children[k]

    def dump(self):
        out = {}

        def rec(path, n):
            e = {'type': n.type, 'mode': n.mode}
            if n.type == 'file':
                try:
                    e['content'] = n.content.decode('utf-8')
                except UnicodeDecodeError:
                    e['contentBase64'] = base64.b64encode(n.content).decode('ascii')
            if n.type in LINKS:
                e['target'] = n.target
            out[path] = e
            if n.type == 'dir':
                for k, v in n.children.items():
                    rec(self.P.join(path, k) if path else k, v)
        for r in self.roots.values():
            for k, v in r.children.items():
                rec(r.rname + k, v)
        return out


AUTH_CLEARABLE = ['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK',
                  'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY', 'ANTHROPIC_PROFILE']
TRUTHY_VARS = ('CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY')
TRUTHY = ('1', 'true', 'yes', 'on')


def parse_rfc3339(s):
    """Returns an aware UTC datetime, or None when s is not a valid RFC 3339 instant (upper-case T and Z)."""
    if not isinstance(s, str):
        return None
    m = RFC3339_RE.fullmatch(s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(m.group(i)) for i in range(1, 7))
    if se > 59 or h > 23 or mi > 59:
        return None
    frac = m.group(7)
    us = int((frac[1:] + '000000')[:6]) if frac else 0
    z = m.group(8)
    off = datetime.timedelta(0)
    if z != 'Z':
        oh, om = int(z[1:3]), int(z[4:6])
        if oh > 23 or om > 59:
            return None
        off = datetime.timedelta(hours=oh, minutes=om)
        if z[0] == '-':
            off = -off
    try:
        dt = datetime.datetime(y, mo, d, h, mi, se, us, tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
    return dt - off


def json_depth(x):
    best = 0
    stack = [(x, 1)]
    while stack:
        v, d = stack.pop()
        if isinstance(v, dict):
            best = max(best, d)
            stack.extend((c, d + 1) for c in v.values())
        elif isinstance(v, list):
            best = max(best, d)
            stack.extend((c, d + 1) for c in v)
    return best


class Lib:
    def __init__(self, case):
        self.c = case
        self.P = Path(case['platform'])
        self.fs = Fs(case)
        self.home = case['home']
        self.env = dict(case['env'])
        self.opts = case.get('options', {})
        self.platform = case['platform']
        self.now = parse_ts(case['now'])
        res = case.get('reserved')
        if res is None:
            res = [n['name'] for n in json.load(open(os.path.join(os.environ.get('CCMA_REPO_ROOT', '.'), 'spec', 'reserved.json')))['names']]
        self.reserved = res
        self._acc = None

    # --- helpers
    def canon(self, name):
        return unicodedata.normalize('NFC', self.P.join(self.home, '.claude-' + name))

    def cfg_home(self, name):
        return self.P.join(self.home, '.claude') if name == 'default' else self.canon(name)

    def accounts(self):
        if self._acc is not None:
            return self._acc
        accs = []
        warnings = []
        d = {'name': 'default', 'dir': self.cfg_home('default'), 'state': 'ok'}
        accs.append(d)
        try:
            names = self.fs.readdir(self.home)
        except FsErr:
            names = []
        for n in names:
            if not n.startswith('.claude-'):
                continue
            nm = n[len('.claude-'):]
            if not valid_name(nm):
                continue
            path = self.P.join(self.home, n)
            try:
                l = self.fs.lstat(path)
            except FsErr:
                accs.append({'name': nm, 'dir': self.canon(nm), 'state': 'unreadable'})
                continue
            try:
                s = self.fs.stat(path)
            except FsErr as e:
                st = 'unreadable' if e.code == 'EACCES' else 'dangling'
                if l.type in LINKS:
                    accs.append({'name': nm, 'dir': self.canon(nm), 'state': st})
                continue
            if s.type != 'dir':
                warnings.append({'code': 'NOT_A_DIRECTORY', 'path': path})
                continue
            accs.append({'name': nm, 'dir': self.canon(nm), 'state': 'ok'})
        # identity + alias groups: the representative is the first named member, default only when alone
        groups = {}
        for a in accs:
            a['ident'] = None
            a['group'] = None
            a['rep'] = None
            if a['state'] == 'ok':
                try:
                    s = self.fs.stat(a['dir'])
                    a['ident'] = (s.dev, s.ino)
                    groups.setdefault(a['ident'], []).append(a)
                except FsErr:
                    pass
        for g in groups.values():
            named = [m for m in g if m['name'] != 'default']
            rep = named[0] if named else g[0]
            for m in g:
                m['group'] = g
                m['rep'] = rep
        for a in accs:
            a['aliasOf'] = a['rep']['name'] if a['rep'] is not None and a['rep'] is not a else None
        self._acc = accs
        self._warn = warnings
        return accs

    def acc(self, name):
        for a in self.accounts():
            if a['name'] == name:
                return a
        return None

    def same_account(self, x, y):
        if x == y:
            return True
        a, b = self.acc(x), self.acc(y)
        return a is not None and b is not None and a['group'] is not None and a['group'] is b['group']

    def gate(self, name, bind_path=None):
        if not valid_name(name):
            raise Err('INVALID_NAME')
        if name == 'default':
            return self.acc('default')
        p = self.P.join(self.home, '.claude-' + name)
        a = self.acc(name)
        if a is None:
            raise Err('ACCOUNT_NOT_FOUND', bind_path or p)
        if a['state'] != 'ok':
            raise Err('ACCOUNT_UNAVAILABLE', p)
        return a

    def is_reg(self, p):
        try:
            return self.fs.stat(p).type == 'file'
        except FsErr:
            return False

    def read_json(self, p):
        try:
            n = self.fs.stat(p)
            if n.type != 'file' or n.unreadable:
                return None
            return json.loads(n.content.decode('utf-8'))
        except (FsErr, ValueError, RecursionError):
            return None

    def suffix(self):
        return '-custom-oauth' if self.env.get('CLAUDE_CODE_CUSTOM_OAUTH_URL') else ''

    def gc_for_home(self, ch):
        legacy = self.P.join(ch, '.config.json')
        if self.is_reg(legacy):
            return legacy
        return self.P.join(ch, '.claude' + self.suffix() + '.json')

    def global_config(self, name):
        ch = self.cfg_home(name)
        legacy = self.P.join(ch, '.config.json')
        if self.is_reg(legacy):
            return legacy
        base = '.claude' + self.suffix() + '.json'
        return self.P.join(self.home if name == 'default' else ch, base)

    # --- spec file
    def spec(self, a):
        """returns ('none',None) | ('invalid',path) | ('ok',data)"""
        p = self.P.join(a['dir'], '.multi-account.json')
        try:
            self.fs.lstat(p)
        except FsErr as e:
            if e.code in ('ENOENT', 'ENOTDIR'):
                return 'none', None
            return 'invalid', p
        try:
            n = self.fs.stat(p)
            if n.type != 'file' or n.unreadable:
                return 'invalid', p
            data = json.loads(n.content.decode('utf-8'))
        except (FsErr, ValueError, RecursionError):
            return 'invalid', p
        if not isinstance(data, dict) or json_depth(data) > MAX_DEPTH:
            return 'invalid', p
        v = data.get('version')
        if isinstance(v, bool) or v != 1:
            return 'invalid', p
        if 'priority' in data:
            pr = data['priority']
            if isinstance(pr, bool) or not isinstance(pr, (int, float)):
                return 'invalid', p
            if isinstance(pr, float) and not (pr == pr and pr not in (float('inf'), float('-inf')) and pr.is_integer()):
                return 'invalid', p
            if abs(pr) > MAX_INT:
                return 'invalid', p
        if 'directories' in data:
            ds = data['directories']
            if not isinstance(ds, list):
                return 'invalid', p
            for x in ds:
                if self.expand_claim(x) is None:
                    return 'invalid', p
        return 'ok', data

    def expand_claim(self, x):
        if not isinstance(x, str):
            return None
        if self.P.is_abs(x):
            return self.P.norm(x)
        if x.startswith('~/') or (self.platform == 'win32' and x.startswith('~\\')):
            return self.P.join(self.home, x[2:])
        return None

    def primaries(self):
        return [a for a in self.accounts() if a['state'] == 'ok' and (a['rep'] is None or a['rep'] is a)]

    # --- ops
    def op_canonical_path(self, args):
        n = args['name']
        if n != 'default' and not valid_name(n):
            raise Err('INVALID_NAME')
        return {'path': self.cfg_home('default') if n == 'default' else self.canon(n)}

    def op_discover(self, args):
        accs = self.accounts()
        out = []
        for a in accs:
            ok = a['state'] == 'ok'
            hs = False
            hg = False
            se = None
            if ok:
                sp = self.P.join(a['dir'], '.multi-account.json')
                hs = self.is_reg(sp)
                hg = self.is_reg(self.global_config(a['name']))
                st, info = self.spec(a)
                if st == 'invalid':
                    se = {'code': 'SPEC_FILE_INVALID', 'path': info}
            w = []
            if a['name'] != 'default' and a['name'] in self.reserved:
                w.append({'code': 'RESERVED_NAME'})
            out.append({'name': a['name'], 'configDir': a['dir'], 'state': a['state'], 'hasSpecFile': hs,
                        'hasGlobalConfig': hg, 'aliasOf': a['aliasOf'], 'specError': se, 'warnings': w})
        claims = {}
        for a in self.primaries():
            st, d = self.spec(a)
            if st != 'ok':
                continue
            for x in d.get('directories', []):
                e = self.expand_claim(x)
                try:
                    s = self.fs.stat(e)
                except FsErr:
                    continue
                lst = claims.setdefault((s.dev, s.ino), [])
                if not any(n == a['name'] for _, n in lst):
                    lst.append((e, a['name']))
        conf = []
        for lst in claims.values():
            if len({n for _, n in lst}) >= 2:
                conf.append({'path': lst[0][0], 'accounts': [n for _, n in lst]})
        conf.sort(key=lambda c: c['path'])
        return {'accounts': out, 'conflicts': conf, 'warnings': list(self._warn)}

    def map_config_dir(self, v):
        accs = self.accounts()
        named = [a for a in accs if a['name'] != 'default' and a['state'] == 'ok']
        for a in named:
            if v == a['dir']:
                return a['name'], True, None
        if self.P.is_abs(v):
            n = unicodedata.normalize('NFC', self.P.norm(v))
            for a in named:
                if n == a['dir']:
                    return a['name'], False, 'not-normalized'
            if self.c['caseInsensitive']:
                for a in named:
                    if fold(n) == fold(a['dir']):
                        return a['name'], False, 'case-mismatch'
            if n == self.cfg_home('default'):
                return 'default', False, 'default-via-config-dir'
            try:
                rv = self.fs.realpath(v)
                # named accounts first (in name order), default last
                for a in named + [accs[0]]:
                    if a['state'] != 'ok':
                        continue
                    try:
                        if self.fs.realpath(a['dir']) == rv:
                            return a['name'], False, 'resolved-target'
                    except FsErr:
                        pass
            except FsErr:
                pass
        return None, False, 'foreign'

    def op_map_config_dir(self, args):
        a, c, r = self.map_config_dir(args['value'])
        return {'account': a, 'canonical': c, 'reason': r,
                'warnings': [] if c else ['NON_CANONICAL_CONFIG_DIR']}

    def parse_marker(self, p):
        none = {'kind': 'none', 'name': None, 'pool': None, 'candidates': []}
        try:
            self.fs.lstat(p)
            n = self.fs.stat(p)
        except FsErr:
            return none
        if n.type == 'dir':
            return none
        if n.type != 'file':
            raise Err('MARKER_INVALID', p)
        try:
            data = self.fs.read(p, 1025)
        except FsErr:
            raise Err('MARKER_INVALID', p)
        if len(data) > 1024:
            raise Err('MARKER_INVALID', p)
        try:
            txt = data.decode('utf-8')
        except UnicodeDecodeError:
            raise Err('MARKER_INVALID', p)
        if txt.startswith('﻿'):
            txt = txt[1:]
        WS = ' \t\r\x0b\x0c'
        for line in txt.split('\n'):
            if line.endswith('\r'):
                line = line[:-1]
            line = line.strip(WS)
            if line == '' or line.startswith('#'):
                continue
            if ',' in line:
                parts = [x.strip(WS) for x in line.split(',')]
                for x in parts:
                    if not (x == 'default' or valid_name(x)):
                        raise Err('MARKER_INVALID', p)
                if len(set(parts)) != len(parts):
                    raise Err('MARKER_INVALID', p)
                return {'kind': 'list', 'name': parts[0], 'pool': None, 'candidates': parts}
            if line == 'default':
                return {'kind': 'default', 'name': 'default', 'pool': None, 'candidates': ['default']}
            if line.startswith('@') and valid_name(line[1:]):
                return {'kind': 'pool', 'name': None, 'pool': line[1:], 'candidates': []}
            if valid_name(line):
                return {'kind': 'account', 'name': line, 'pool': None, 'candidates': [line]}
            raise Err('MARKER_INVALID', p)
        raise Err('MARKER_INVALID', p)

    def op_parse_marker(self, args):
        return self.parse_marker(args['path'])

    def env_delta(self, name, clear=False):
        s = {'CLAUDE_MULTI_ACCOUNT': name}
        u = {'CLAUDE_MULTI_ACCOUNT_SOURCE', 'CLAUDE_SECURESTORAGE_CONFIG_DIR'}
        if name == 'default':
            u.add('CLAUDE_CONFIG_DIR')
        else:
            s['CLAUDE_CONFIG_DIR'] = self.canon(name)
        if clear:
            u |= set(AUTH_CLEARABLE)
        return {'set': s, 'unset': sorted(u)}

    def settings_env(self, cfg):
        if cfg is None:
            return {}, None
        d = self.read_json(self.P.join(cfg, 'settings.json'))
        if not isinstance(d, dict):
            return {}, None
        e = d.get('env')
        e = {k: v for k, v in e.items() if isinstance(v, str)} if isinstance(e, dict) else {}
        h = d.get('apiKeyHelper')
        return e, (h if isinstance(h, str) and h else None)

    def overridden(self, cfg, clear=False):
        senv, helper = self.settings_env(cfg)

        def counts(src, k):
            if k not in src:
                return False
            v = src[k]
            if k in TRUTHY_VARS:
                return v.strip().lower() in TRUTHY
            return v != ''
        out = []
        for k in AUTH_CLEARABLE:
            if (not clear and counts(self.env, k)) or counts(senv, k):
                out.append(k)
        if 'CLAUDE_SECURESTORAGE_CONFIG_DIR' in self.env:
            out.append('CLAUDE_SECURESTORAGE_CONFIG_DIR')
        if self.env.get('CLAUDE_CODE_CUSTOM_OAUTH_URL'):
            out.append('CLAUDE_CODE_CUSTOM_OAUTH_URL')
        if helper:
            out.append('apiKeyHelper')
        return out

    def op_env(self, args):
        n = args['name']
        if n != 'default' and not valid_name(n):
            raise Err('INVALID_NAME')
        clear = bool(args.get('clearAuthOverrides'))
        d = self.env_delta(n, clear)
        d['overriddenBy'] = self.overridden(self.cfg_home(n), clear)
        return d

    def op_credential_locations(self, args):
        n = args['name']
        if n != 'default' and not valid_name(n):
            raise Err('INVALID_NAME')
        ch = self.cfg_home(n)
        f = {'file': self.P.join(ch, '.credentials.json')}
        if self.platform == 'linux':
            return {'locations': [f]}
        if self.platform == 'darwin':
            svc = 'Claude Code' + self.suffix() + '-credentials'
            if n != 'default':
                svc += '-' + hashlib.sha256(ch.encode()).hexdigest()[:8]
            acct = self.env.get('USER') or self.opts.get('userName') or 'claude-code-user'
            if not re.fullmatch(r'[a-zA-Z0-9._-]+', acct):
                acct = 'claude-code-user'
            return {'locations': [{'keychain': {'service': svc, 'account': acct}}, f]}
        if self.credman(self.global_config(n)):
            return {'locations': [{'credentialManager': {}}, f]}
        return {'locations': [f]}

    def credman(self, gc):
        if self.env.get('CLAUDE_CODE_FORCE_WINDOWS_CREDMAN') == '1':
            return True
        d = self.read_json(gc)
        if isinstance(d, dict):
            g = d.get('cachedGrowthBookFeatures')
            if isinstance(g, dict) and g.get('tengu_windows_credman') is True:
                return True
        return False

    def gc_target(self, args):
        """B2 reads take a name, or {resolve: true} to use the globalConfig of resolve()."""
        if args.get('resolve'):
            r = self.op_resolve({})
            return r['globalConfig']
        self.gate(args['name'])
        return self.global_config(args['name'])

    def op_identity(self, args):
        gc = self.gc_target(args)
        d = self.read_json(gc) if gc else None
        if not isinstance(d, dict) or not isinstance(d.get('oauthAccount'), dict):
            return None
        o = d['oauthAccount']
        return {'email': o.get('emailAddress'), 'orgName': o.get('organizationName'),
                'orgUuid': o.get('organizationUuid'), 'organizationType': o.get('organizationType'),
                'billingType': o.get('billingType'), 'userRateLimitTier': o.get('userRateLimitTier'),
                'organizationRateLimitTier': o.get('organizationRateLimitTier')}

    def op_usage(self, args):
        gc = self.gc_target(args)
        d = self.read_json(gc) if gc else None
        if not isinstance(d, dict) or not isinstance(d.get('cachedUsageUtilization'), dict):
            return None
        u = d['cachedUsageUtilization']
        ms = u.get('fetchedAtMs')
        fa = None
        if isinstance(ms, (int, float)) and not isinstance(ms, bool):
            dt = datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)
            fa = dt.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (int(ms) % 1000)
        return {'fetchedAt': fa, 'data': u, 'windows': self.usage_windows(u), 'stale': self.usage_stale(u, d)}

    @staticmethod
    def usage_windows(u):
        w = {}
        inner = u.get('utilization')
        if isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, dict):
                    pc = v.get('utilization')
                    ra = v.get('resets_at')
                    w[k] = {'utilization': pc if isinstance(pc, (int, float)) and not isinstance(pc, bool) else None,
                            'resetsAt': ra if isinstance(ra, str) else None}
        return w

    def usage_stale(self, u, gc):
        ms = u.get('fetchedAtMs')
        if not isinstance(ms, (int, float)) or isinstance(ms, bool):
            return True
        age = self.now.timestamp() * 1000 - ms
        if age < 0 or age > 3600000:
            return True
        oa = gc.get('oauthAccount') if isinstance(gc, dict) else None
        mine = oa.get('accountUuid') if isinstance(oa, dict) else None
        return u.get('accountUuid') != mine

    def op_credentials(self, args):
        name = args['name']
        self.gate(name)
        p = self.P.join(self.cfg_home(name), '.credentials.json')
        try:
            if self.fs.lstat(p).type in LINKS:
                return None
        except FsErr:
            return None
        d = self.read_json(p)
        o = d.get('claudeAiOauth') if isinstance(d, dict) else None
        if not isinstance(o, dict) or not isinstance(o.get('accessToken'), str) or o['accessToken'] == '':
            return None
        ms = o.get('expiresAt')
        exp = None
        expired = False
        if isinstance(ms, (int, float)) and not isinstance(ms, bool):
            dt = datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)
            exp = dt.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (int(ms) % 1000)
            expired = dt <= self.now
        sc = o.get('scopes')
        sc = [x for x in sc if isinstance(x, str)] if isinstance(sc, list) else []
        st = o.get('subscriptionType')
        rl = o.get('rateLimitTier')
        return {'source': 'file', 'path': p, 'accessToken': o['accessToken'], 'expiresAt': exp, 'expired': expired,
                'scopes': sc, 'subscriptionType': st if isinstance(st, str) else None,
                'rateLimitTier': rl if isinstance(rl, str) else None}

    def sessions(self, name):
        ch = self.cfg_home(name)
        sd = self.P.join(ch, 'sessions')
        try:
            names = self.fs.readdir(sd)
        except FsErr:
            return []
        caller = self.c.get('callerPidDomain', 'host-1')
        out = []
        for n in names:
            m = PID_FILE_RE.fullmatch(n)
            if not m:
                continue
            d = self.read_json(self.P.join(sd, n))
            if not isinstance(d, dict):
                continue
            pid = int(m.group(1))
            dom = d.get('pidDomain')
            if dom is not None and dom != caller:
                stt = 'unknown'
            else:
                pr = self.c.get('processes', {}).get(str(pid))
                ft, ps = d.get('procStartFt'), d.get('procStart')
                if pr is None:
                    stt = 'dead'
                elif pr.get('lookupError') is True:
                    stt = 'unknown'
                elif isinstance(ft, str) and ft != '':
                    stt = 'live' if pr.get('procStartFt') == ft else 'dead'
                elif isinstance(ps, str):
                    stt = 'live' if pr.get('procStart') == ps else 'dead'
                else:
                    stt = 'unknown'
            sid = d.get('sessionId')
            out.append({'pid': pid, 'sessionId': sid if isinstance(sid, str) else None, 'status': stt})
        out.sort(key=lambda s: s['pid'])
        return out

    def op_live_sessions(self, args):
        self.gate(args['name'])
        return {'sessions': self.sessions(args['name'])}

    def blocked_by_sessions(self, sessions, force, match=None):
        for x in sessions:
            if match is not None and x['sessionId'] != match:
                continue
            if x['status'] == 'live' or (x['status'] == 'unknown' and not force):
                raise Err('SESSION_LIVE')

    # locks and atomic write
    def take_lock(self, lock):
        try:
            self.fs.mkdir(lock, '0700')
            return
        except FsErr as e:
            if e.code != 'EEXIST':
                raise
        n = self.fs.lstat(lock)
        if (self.now - n.mtime).total_seconds() > 10:
            self.fs.rmdir(lock)
            try:
                self.fs.mkdir(lock, '0700')
                return
            except FsErr as e:
                if e.code != 'EEXIST':
                    raise
        raise Err('LOCK_BUSY', lock)

    def write_file(self, path, text):
        """Atomic write of path (one hop through a link). The caller holds the lock."""
        target = path
        try:
            l = self.fs.lstat(path)
            if l.type in LINKS:
                t = self.fs.readlink(path)
                target = t if self.P.is_abs(t) else self.P.join(self.P.dirname(path), t)
        except FsErr:
            pass
        tmp = target + '.tmp.1234.abcdef012345'
        self.fs.create_file(tmp, text.encode('utf-8'), '0600')
        self.fs.rename(tmp, target)

    def locked_write(self, path, fn):
        """lock, fn() returns the text to write (or None for no write), write, unlock."""
        lock = path + '.lock'
        self.take_lock(lock)
        try:
            text = fn()
            if text is not None:
                self.write_file(path, text)
        finally:
            self.fs.rmdir(lock)

    def op_create(self, args):
        n = args['name']
        if not valid_name(n):
            raise Err('INVALID_NAME')
        if n in self.reserved:
            raise Err('RESERVED_NAME')
        p = self.P.join(self.home, '.claude-' + n)
        try:
            self.fs.lstat(p)
            raise Err('ACCOUNT_EXISTS', p)
        except FsErr:
            pass
        self.fs.mkdir(p, '0700')
        self.locked_write(self.P.join(p, '.multi-account.json'),
                          lambda: json.dumps({'version': 1, 'createdAt': iso(self.now)}))
        return {'name': n, 'configDir': self.canon(n)}

    # state file
    def state_path(self, name):
        return self.P.join(self.cfg_home(name), '.multi-account-state.json')

    def read_state(self, name):
        """For reads: anything not understood is an empty state."""
        d = self.read_json(self.state_path(name))
        if not self.state_ok(d):
            return {'version': 1, 'limits': []}
        d.setdefault('limits', [])
        return d

    @staticmethod
    def state_ok(d):
        return (isinstance(d, dict) and not isinstance(d.get('version'), bool) and d.get('version') == 1
                and ('limits' not in d or isinstance(d['limits'], list)) and json_depth(d) <= MAX_DEPTH)

    def read_state_for_write(self, name):
        sp = self.state_path(name)
        try:
            n = self.fs.stat(sp)
        except FsErr as e:
            if e.code in ('ENOENT', 'ENOTDIR'):
                return {'version': 1, 'limits': []}
            raise Err('STATE_FILE_INVALID', sp)
        try:
            if n.type != 'file' or n.unreadable:
                raise ValueError
            d = json.loads(n.content.decode('utf-8'))
        except (ValueError, RecursionError):
            raise Err('STATE_FILE_INVALID', sp)
        if not self.state_ok(d):
            raise Err('STATE_FILE_INVALID', sp)
        d.setdefault('limits', [])
        return d

    @staticmethod
    def entry_key(x):
        if isinstance(x, dict) and isinstance(x.get('window'), str):
            return (x['window'], x.get('model'))
        return None

    def entry_until(self, x):
        return parse_rfc3339(x.get('until')) if isinstance(x, dict) else None

    def valid_entry(self, e):
        if not isinstance(e, dict):
            return False
        if not isinstance(e.get('window'), str) or e['window'] == '':
            return False
        m = e.get('model')
        if m is not None and (not isinstance(m, str) or m == ''):
            return False
        if parse_rfc3339(e.get('until')) is None:
            return False
        for k in ('reason', 'updatedBy'):
            if k in e and not isinstance(e[k], str):
                return False
        return True

    def drop_past(self, lim):
        out = []
        for x in lim:
            u = self.entry_until(x)
            if u is not None and u <= self.now:
                continue
            out.append(x)
        return out

    def op_mark_limited(self, args):
        name = args['name']
        self.gate(name)
        e = dict(args['entry'])
        if not self.valid_entry(e):
            raise Err('INVALID_ENTRY')
        e['updatedAt'] = iso(self.now)
        e.setdefault('model', None)
        sp = self.state_path(name)
        box = {}

        def fn():
            st = self.read_state_for_write(name)
            lim = st['limits']
            k = self.entry_key(e)
            for i, o in enumerate(lim):
                if self.entry_key(o) == k:
                    ou = self.entry_until(o)
                    if ou is None or parse_rfc3339(e['until']) >= ou:
                        lim[i] = e
                    break
            else:
                lim.append(e)
            st['limits'] = self.drop_past(lim)
            box['st'] = st
            return json.dumps(st)
        self.locked_write(sp, fn)
        return {'limits': box['st']['limits']}

    def op_clear_limited(self, args):
        name = args['name']
        self.gate(name)
        sp = self.state_path(name)
        try:
            self.fs.lstat(sp)
        except FsErr:
            return {'limits': []}
        box = {}

        def fn():
            st = self.read_state_for_write(name)
            k = (args['window'], args.get('model'))
            st['limits'] = self.drop_past([x for x in st['limits'] if self.entry_key(x) != k])
            box['st'] = st
            return json.dumps(st)
        self.locked_write(sp, fn)
        return {'limits': box['st']['limits']}

    def is_available(self, name, model):
        st = self.read_state(name)
        for x in st['limits']:
            if not isinstance(x, dict):
                continue
            m = x.get('model')
            if m is None or (model is not None and m == model):
                u = self.entry_until(x)
                if u is not None and u > self.now:
                    return False
        return True

    def op_available(self, args):
        self.gate(args['name'])
        return {'available': self.is_available(args['name'], args.get('model'))}

    def members(self, pool):
        if not valid_name(pool):
            raise Err('INVALID_NAME')
        specs = {}
        for a in self.accounts():
            if a['state'] != 'ok':
                continue
            st, d = self.spec(a)
            if st == 'invalid':
                raise Err('SPEC_FILE_INVALID', d)
            specs[a['name']] = d
        out = []
        for a in self.primaries():
            d = specs.get(a['name'])
            if isinstance(d, dict) and d.get('pool') == pool:
                out.append((-int(d.get('priority', 0)), a['name']))
        out.sort()
        return [n for _, n in out]

    def first_available(self, cands, model):
        for n in cands:
            if self.usable(n) and self.is_available(n, model):
                return {'account': n}
        return {'account': None}

    def next_of(self, m, cur, model):
        pos = next((i for i, n in enumerate(m) if self.same_account(n, cur)), None)
        if pos is None:
            cands = m
        else:
            cands = [n for n in m[pos + 1:] + m[:pos] if not self.same_account(n, cur)] + [m[pos]]
        return self.first_available(cands, model)

    def op_pick(self, args):
        return self.first_available(self.members(args['pool']), args.get('model'))

    def op_next(self, args):
        return self.next_of(self.members(args['pool']), args['current'], args.get('model'))

    def usable(self, n):
        if n == 'default':
            return True
        a = self.acc(n)
        return a is not None and a['state'] == 'ok'

    def gate_all(self, cands):
        for n in cands:
            if not valid_name(n):
                raise Err('INVALID_NAME')

    def op_pick_from(self, args):
        self.gate_all(args['candidates'])
        return self.first_available(args['candidates'], args.get('model'))

    def op_next_from(self, args):
        self.gate_all(args['candidates'])
        return self.next_of(args['candidates'], args['current'], args.get('model'))

    def op_limits(self, args):
        self.gate(args['name'])
        out = []
        for x in self.read_state(args['name'])['limits']:
            if not isinstance(x, dict) or not isinstance(x.get('window'), str) or self.entry_until(x) is None:
                continue
            m = x.get('model')
            out.append({'window': x['window'], 'model': m if isinstance(m, str) else None, 'until': x['until'],
                        'reason': x['reason'] if isinstance(x.get('reason'), str) else None,
                        'updatedBy': x['updatedBy'] if isinstance(x.get('updatedBy'), str) else None,
                        'updatedAt': x['updatedAt'] if isinstance(x.get('updatedAt'), str) else None})
        return {'limits': out}

    def fmt_instant(self, dt):
        ms = dt.microsecond // 1000
        base = dt.strftime('%Y-%m-%dT%H:%M:%S')
        return base + ('.%03dZ' % ms if ms else 'Z')

    def op_available_at(self, args):
        self.gate(args['name'])
        model = args.get('model')
        best = None
        for x in self.read_state(args['name'])['limits']:
            if not isinstance(x, dict):
                continue
            m = x.get('model')
            if m is None or (model is not None and m == model):
                u = self.entry_until(x)
                if u is not None and u > self.now and (best is None or u > best):
                    best = u
        return {'availableAt': self.fmt_instant(best) if best else None}

    def op_pool_members(self, args):
        return {'members': self.members(args['pool'])}

    def op_session_of_pid(self, args):
        self.gate(args['name'])
        pid = args['pid']
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            return {'sessionId': None}
        d = self.read_json(self.P.join(self.cfg_home(args['name']), 'sessions', '%d.json' % pid))
        sid = d.get('sessionId') if isinstance(d, dict) else None
        return {'sessionId': sid if isinstance(sid, str) and sid != '' else None}

    @staticmethod
    def slug_of(cwd):
        units = cwd.encode('utf-16-le')
        cu = [units[i] | (units[i + 1] << 8) for i in range(0, len(units), 2)]
        out = ''.join(chr(c) if (48 <= c <= 57 or 65 <= c <= 90 or 97 <= c <= 122) else '-' for c in cu)
        if len(out) <= 200:
            return out
        h = 0
        for c in cu:
            h = ((h << 5) - h + c) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
        n, digs = abs(h), '0123456789abcdefghijklmnopqrstuvwxyz'
        t = ''
        while True:
            t = digs[n % 36] + t
            n //= 36
            if n == 0:
                break
        return out[:200] + '-' + t

    def op_project_slug(self, args):
        return {'slug': self.slug_of(args['cwd'])}

    def op_sessions_for(self, args):
        name = args['name']
        self.gate(name)
        P, fs = self.P, self.fs
        d = P.join(self.cfg_home(name), 'projects', self.slug_of(args['cwd']))
        try:
            for par in (P.join(self.cfg_home(name), 'projects'), d):
                if fs.lstat(par).type != 'dir':
                    return {'sessions': []}
            names = fs.readdir(d)
        except FsErr:
            return {'sessions': []}
        out = []
        for n in names:
            if not n.endswith('.jsonl') or SESSION_ID_RE.fullmatch(n[:-6]) is None:
                continue
            try:
                st = fs.lstat(P.join(d, n))
            except FsErr:
                continue
            if st.type != 'file':
                continue
            dt = st.mtime
            out.append((dt, n[:-6]))
        out.sort(key=lambda x: (-x[0].timestamp(), x[1]))
        return {'sessions': [{'id': i, 'mtime': dt.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (dt.microsecond // 1000)} for dt, i in out]}

    # spec file read and update
    def spec_account(self, name):
        a = self.gate(name)
        return a

    def op_spec_file(self, args):
        a = self.spec_account(args['name'])
        st, d = self.spec(a)
        if st == 'invalid':
            raise Err('SPEC_FILE_INVALID', d)
        return d if st == 'ok' else None

    def validate_spec_obj(self, a, d):
        """Would the library accept this object as a spec file? Same rules as spec()."""
        if not isinstance(d, dict) or json_depth(d) > MAX_DEPTH:
            return False
        v = d.get('version')
        if isinstance(v, bool) or v != 1:
            return False
        if 'priority' in d:
            pr = d['priority']
            if isinstance(pr, bool) or not isinstance(pr, (int, float)):
                return False
            if isinstance(pr, float) and not (pr == pr and pr not in (float('inf'), float('-inf')) and pr.is_integer()):
                return False
            if abs(pr) > MAX_INT:
                return False
        if 'directories' in d:
            if not isinstance(d['directories'], list) or any(self.expand_claim(x) is None for x in d['directories']):
                return False
        return True

    def write_spec(self, a, mutate):
        """Locked read, mutate(current dict) -> (new dict or None for no write), write. Returns the final object."""
        sp = self.P.join(a['dir'], '.multi-account.json')
        box = {}

        def fn():
            st, d = self.spec(a)
            if st == 'invalid':
                raise Err('SPEC_FILE_INVALID', d)
            cur = d if st == 'ok' else {'version': 1}
            new = mutate(cur)
            if new is None:
                box['res'] = d if st == 'ok' else None
                return None
            if not self.validate_spec_obj(a, new):
                raise Err('INVALID_ENTRY')
            box['res'] = new
            return json.dumps(new)
        self.locked_write(sp, fn)
        return box['res']

    def op_update_spec_file(self, args):
        a = self.spec_account(args['name'])
        patch = args['patch']
        if not isinstance(patch, dict):
            raise Err('INVALID_ENTRY')

        def mutate(cur):
            new = dict(cur)
            for k, v in patch.items():
                if v is None:
                    new.pop(k, None)
                else:
                    new[k] = v
            return new
        return self.write_spec(a, mutate)

    def claim_form(self, dirv):
        if not isinstance(dirv, str):
            raise Err('INVALID_ENTRY')
        e = self.expand_claim(dirv)
        if e is None:
            raise Err('INVALID_ENTRY')
        home = self.P.norm(self.home)
        if e == home:
            return '~/', e
        pre = home.rstrip(self.P.sep) + self.P.sep
        if (fold(e) if self.c['caseInsensitive'] else e).startswith(fold(pre) if self.c['caseInsensitive'] else pre):
            return '~/' + e[len(pre):].replace('\\', '/'), e
        return e, e

    def same_dir(self, x, y):
        try:
            a, b = self.fs.stat(x), self.fs.stat(y)
            return (a.dev, a.ino) == (b.dev, b.ino)
        except FsErr:
            pass
        if self.c['caseInsensitive']:
            return fold(x) == fold(y)
        return x == y

    def op_claim(self, args):
        a = self.spec_account(args['name'])
        stored, e = self.claim_form(args['dir'])
        for o in self.primaries():
            if self.same_account(o['name'], a['name']):
                continue
            st, d = self.spec(o)
            if st == 'invalid':
                raise Err('SPEC_FILE_INVALID', d)
            if st != 'ok':
                continue
            for x in d.get('directories', []):
                if self.same_dir(self.expand_claim(x), e):
                    raise Err('CLAIM_CONFLICT', e)

        def mutate(cur):
            ds = list(cur.get('directories', []))
            if any(self.same_dir(self.expand_claim(x), e) for x in ds):
                return None if 'directories' in cur else dict(cur, directories=ds)
            ds.append(stored)
            return dict(cur, directories=ds)
        r = self.write_spec(a, mutate)
        return {'directories': list(r.get('directories', [])) if r else []}

    def op_unclaim(self, args):
        a = self.spec_account(args['name'])
        stored, e = self.claim_form(args['dir'])

        def mutate(cur):
            ds = list(cur.get('directories', []))
            keep = [x for x in ds if not self.same_dir(self.expand_claim(x), e)]
            if len(keep) == len(ds):
                return None
            return dict(cur, directories=keep)
        r = self.write_spec(a, mutate)
        return {'directories': list(r.get('directories', [])) if r else []}

    # slot
    def slot(self):
        P, fs = self.P, self.fs
        L = P.join(self.home, '.claude')
        J = P.join(self.home, '.claude.json')
        unsup = self.platform == 'darwin'
        if self.platform == 'win32':
            if self.credman(J) or self.opts.get('canCreateSymlinks', True) is False:
                unsup = True
        if unsup:
            return {'state': 'unsupported', 'name': None}
        try:
            l = fs.lstat(L)
        except FsErr as e:
            if e.code in ('ENOENT', 'ENOTDIR'):
                return {'state': 'unmanaged', 'name': None}
            return {'state': 'broken', 'name': None}
        if l.type == 'dir':
            return {'state': 'unmanaged', 'name': None}
        broken = {'state': 'broken', 'name': None}
        if l.type in LINKS:
            tg = l.target
            t = P.norm(tg) if P.is_abs(tg) else P.join(self.home, tg)
            m = re.fullmatch(re.escape(P.join(self.home, '.claude-')) + r'(.*)', t)
            if m and valid_name(m.group(1)) and m.group(1) != 'default' and P.join(self.home, '.claude-' + m.group(1)) == t:
                try:
                    if fs.stat(t).type != 'dir':
                        return broken
                    jl = fs.lstat(J)
                    if jl.type != 'symlink':
                        return broken
                    jt = P.norm(jl.target) if P.is_abs(jl.target) else P.join(self.home, jl.target)
                    if jt != P.join(t, '.claude.json'):
                        return broken
                    try:
                        if fs.lstat(jt).type != 'file':
                            return broken
                    except FsErr as e:
                        if e.code not in ('ENOENT', 'ENOTDIR'):
                            return broken
                    try:
                        if fs.lstat(P.join(t, '.credentials.json')).type in LINKS:
                            return broken
                    except FsErr:
                        pass
                except FsErr:
                    return broken
                return {'state': 'managed', 'name': m.group(1)}
        return broken

    def op_slot(self, args):
        return self.slot()

    def slot_name_ok(self, n):
        if not isinstance(n, str) or not valid_name(n) or n == 'default':
            raise Err('INVALID_NAME')

    def lstat_or_none(self, p):
        try:
            return self.fs.lstat(p)
        except FsErr as e:
            if e.code in ('ENOENT', 'ENOTDIR'):
                return None
            raise

    def op_adopt(self, args):
        n = args['name']
        force = bool(args.get('force'))
        s = self.slot()
        if s['state'] == 'unsupported':
            raise Err('SLOT_UNSUPPORTED')
        self.slot_name_ok(n)
        if n in self.reserved:
            raise Err('RESERVED_NAME')
        if s['state'] != 'unmanaged':
            raise Err('SLOT_STATE')
        P = self.P
        A = P.join(self.home, '.claude-' + n)
        try:
            self.fs.lstat(A)
            raise Err('ACCOUNT_EXISTS', A)
        except FsErr:
            pass
        L = P.join(self.home, '.claude')
        J = P.join(self.home, '.claude.json')
        have_l = self.lstat_or_none(L) is not None
        jn = self.lstat_or_none(J)
        inner = self.lstat_or_none(P.join(L, '.claude.json')) if have_l else None
        if jn is not None and inner is not None:
            raise Err('SLOT_CONFLICT', P.join(L, '.claude.json'))
        if jn is not None and jn.type != 'file':
            raise Err('SLOT_TARGET_INVALID', J)
        if jn is None and inner is not None and inner.type != 'file':
            raise Err('SLOT_TARGET_INVALID', P.join(L, '.claude.json'))
        cr = self.lstat_or_none(P.join(L, '.credentials.json')) if have_l else None
        if cr is not None and cr.type in LINKS:
            raise Err('SLOT_TARGET_INVALID', P.join(L, '.credentials.json'))
        lock = P.join(self.home, '.claude-slot.lock')
        self.take_lock(lock)
        try:
            self.blocked_by_sessions(self.sessions('default'), force)
            if have_l:
                self.fs.rename(L, A)
            else:
                self.fs.mkdir(A, '0700')
            if jn is not None:
                self.fs.rename(J, P.join(A, '.claude.json'))
            self.fs.symlink(A, L, 'dir')
            self.fs.symlink(P.join(A, '.claude.json'), J, 'file')
        finally:
            self.fs.rmdir(lock)
        return self.slot()

    def op_activate(self, args):
        n = args['name']
        force = bool(args.get('force'))
        s = self.slot()
        if s['state'] == 'unsupported':
            raise Err('SLOT_UNSUPPORTED')
        self.slot_name_ok(n)
        self.gate(n)
        if s['state'] != 'managed':
            raise Err('SLOT_STATE')
        P = self.P
        A = P.join(self.home, '.claude-' + n)
        for f in ('.credentials.json', '.claude.json'):
            x = self.lstat_or_none(P.join(A, f))
            if x is not None and (x.type in LINKS if f == '.credentials.json' else x.type != 'file'):
                raise Err('SLOT_TARGET_INVALID', P.join(A, f))
        lock = P.join(self.home, '.claude-slot.lock')
        self.take_lock(lock)
        try:
            self.blocked_by_sessions(self.sessions(s['name']), force)
            L = P.join(self.home, '.claude')
            J = P.join(self.home, '.claude.json')
            tj = J + '.tmp.1.abcdef012345'
            self.fs.symlink(P.join(A, '.claude.json'), tj, 'file')
            self.fs.rename(tj, J)
            if self.P.win:
                # a junction cannot be replaced by a rename: remove, then create (not atomic)
                self.fs.rmdir(L)
                self.fs.symlink(A, L, 'dir')
            else:
                tl = L + '.tmp.1.abcdef012345'
                self.fs.symlink(A, tl, 'dir')
                self.fs.rename(tl, L)
        finally:
            self.fs.rmdir(lock)
        return self.slot()

    def op_handover_session(self, args):
        id_, fr, to = args['id'], args['from'], args['to']
        force = bool(args.get('force'))
        if not isinstance(id_, str) or SESSION_ID_RE.fullmatch(id_) is None:
            raise Err('INVALID_SESSION_ID')
        self.gate(fr)
        self.gate(to)
        P, fs = self.P, self.fs
        src, dst = self.cfg_home(fr), self.cfg_home(to)
        if fr == to or self.same_account(fr, to):
            raise Err('SAME_ACCOUNT')

        skipped_parents = set()

        def real_dir(path, rel, record):
            try:
                n = fs.lstat(path)
            except FsErr as e:
                if e.code in ('ENOENT', 'ENOTDIR'):
                    return False
                raise Err('IO_ERROR', path)
            if n.type == 'dir':
                return True
            if record:
                skipped_parents.add(rel)
            return False

        def slugs_of(root, record):
            pd = P.join(root, 'projects')
            if not real_dir(pd, 'projects', record):
                return []
            out = []
            for sl_ in fs.readdir(pd):
                if real_dir(P.join(pd, sl_), 'projects/' + sl_, record):
                    out.append(sl_)
            return out

        def locs(root, slugs, record):
            out = []
            for s_ in slugs:
                out.append('projects/%s/%s.jsonl' % (s_, id_))
                out.append('projects/%s/%s' % (s_, id_))
            for d in ('file-history', 'session-env', 'tasks'):
                if real_dir(P.join(root, d), d, record):
                    out.append('%s/%s' % (d, id_))
            res = []
            for r in out:
                try:
                    n = fs.lstat(P.join(root, *r.split('/')))
                    res.append((r, n.type))
                except FsErr:
                    pass
            return res
        src_slugs = slugs_of(src, True)
        dst_slugs = slugs_of(dst, False)
        dst_all = set()
        pd_dst = P.join(dst, 'projects')
        try:
            for x in fs.readdir(pd_dst):
                dst_all.add(x)
        except FsErr:
            pass
        union = sorted(set(src_slugs) | set(dst_slugs))
        writable = list(src_slugs)
        sl = [(r, t) for r, t in locs(src, src_slugs, True) if not r.startswith('projects/') or r.split('/')[1] in writable or True]
        if not any(t in ('file', 'dir') for _, t in sl):
            raise Err('SESSION_NOT_FOUND')
        self.blocked_by_sessions(self.sessions(fr), force, match=id_)
        for r, _ in sl:
            chain = ['projects', '/'.join(r.split('/')[:2])] if r.startswith('projects/') else [r.split('/')[0]]
            for par in chain:
                dp = P.join(dst, *par.split('/'))
                try:
                    pn = fs.lstat(dp)
                except FsErr as e:
                    if e.code in ('ENOENT', 'ENOTDIR'):
                        continue
                    raise Err('IO_ERROR', dp)
                if pn.type != 'dir':
                    raise Err('DESTINATION_BLOCKED', dp)
        dl = locs(dst, union, False)
        dl = [(r, t) for r, t in dl if not r.startswith('projects/') or r.split('/')[1] in dst_slugs]
        if dl and not args.get('overwrite'):
            raise Err('SESSION_EXISTS')

        # plan: read everything first, so a read error changes nothing
        copied, skipped, dirs, files = [], [], [], []

        def plan(rel):
            sp = P.join(src, *rel.split('/'))
            try:
                n = fs.lstat(sp)
                if n.type == 'dir':
                    dirs.append(rel)
                    for c in fs.readdir(sp):
                        plan(rel + '/' + c)
                elif n.type == 'file':
                    files.append((rel, fs.read(sp, 1 << 30), n.mode))
                    copied.append(rel)
                else:
                    skipped.append(rel)
            except FsErr:
                raise Err('IO_ERROR', sp)
        for r, _ in sl:
            if r.startswith('projects/') and r.split('/')[1] not in writable:
                continue
            if not r.startswith('projects/') and r.split('/')[0] in skipped_parents:
                continue
            plan(r)

        def rm(path):
            n = fs.lstat(path)
            if n.type == 'dir':
                for c in fs.readdir(path):
                    rm(P.join(path, c))
                fs.rmdir(path)
            elif n.type == 'junction':
                fs.rmdir(path)
            else:
                pn, nm = fs.parent_name(path)
                del pn.children[nm]
        for r, _ in dl:
            rm(P.join(dst, *r.split('/')))

        def exists(path):
            try:
                fs.lstat(path)
                return True
            except FsErr:
                return False

        def mkdirs(path):
            if not exists(path):
                mkdirs(P.parent(path))
                fs.mkdir(path, '0700')
        for rel in dirs:
            mkdirs(P.join(dst, *rel.split('/')))
        for rel, data, mode in files:
            dp = P.join(dst, *rel.split('/'))
            mkdirs(P.parent(dp))
            fs.create_file(dp, data, mode)
        return {'copied': sorted(copied), 'skipped': sorted(set(skipped) | skipped_parents)}

    # resolve
    def resolve_account(self, name, source, matched, warnings, ignored, bind_path=None, candidates=None):
        P = self.P
        a = self.gate(name, bind_path)
        cfg = self.cfg_home(name)
        w = list(warnings)
        if name != 'default' and name in self.reserved:
            w.append('RESERVED_NAME')
        return {'account': name, 'pool': None, 'configDir': cfg, 'canonical': True, 'reason': None,
                'source': source, 'matchedPath': matched, 'exists': True, 'aliasOf': a['aliasOf'],
                'launchEnv': self.env_delta(name), 'overriddenBy': self.overridden(cfg),
                'ignoredMarkers': ignored, 'warnings': w, 'applied': True,
                'candidates': candidates if candidates is not None else [name],
                'globalConfig': self.global_config(name)}

    def op_resolve(self, args):
        P = self.P
        warnings = []
        env = dict(self.env)
        for k in ('CLAUDE_CONFIG_DIR', 'CLAUDE_MULTI_ACCOUNT', 'CLAUDE_MULTI_ACCOUNT_SOURCE'):
            if env.get(k) == '':
                del env[k]
                warnings.append('EMPTY_ENV')
        if self.opts.get('ignoreHookEnv') and env.get('CLAUDE_MULTI_ACCOUNT_SOURCE') == 'hook':
            env.pop('CLAUDE_MULTI_ACCOUNT', None)
            env.pop('CLAUDE_CONFIG_DIR', None)
        self.env = env
        M, V = env.get('CLAUDE_MULTI_ACCOUNT'), env.get('CLAUDE_CONFIG_DIR')
        if M is not None and not valid_name(M):
            raise Err('INVALID_NAME')
        if V is not None:
            acc, canon, reason = self.map_config_dir(V)
            if M is not None and not (acc is not None and self.same_account(acc, M)):
                if M != 'default' and P.is_abs(V) and unicodedata.normalize('NFC', P.norm(V)) == self.canon(M):
                    self.gate(M)
                raise Err('ENV_CONFLICT')
            w = list(warnings)
            if not canon:
                w.append('NON_CANONICAL_CONFIG_DIR')
            try:
                ex = P.is_abs(V) and self.fs.stat(V).type == 'dir'
            except FsErr:
                ex = False
            gc = self.gc_for_home(V) if P.is_abs(V) else None
            if acc is None:
                return {'account': None, 'pool': None, 'configDir': V, 'canonical': False, 'reason': 'foreign',
                        'source': 'config-dir', 'matchedPath': None, 'exists': ex, 'aliasOf': None,
                        'launchEnv': None, 'overriddenBy': self.overridden(V), 'ignoredMarkers': [],
                        'warnings': w, 'applied': True, 'candidates': [], 'globalConfig': gc}
            r = self.resolve_account(acc, 'config-dir', None, [], [])
            r.update({'configDir': V, 'canonical': canon, 'reason': reason, 'exists': ex,
                      'warnings': w + [x for x in r['warnings']], 'globalConfig': gc})
            r['overriddenBy'] = self.overridden(V)
            return r
        if M is not None:
            r = self.resolve_account(M, 'env', None, warnings, [])
            if not self.same_account(M, 'default'):
                if env.get('CLAUDECODE') == '1':
                    raise Err('ENV_CONFLICT')
                r['applied'] = False
                r['warnings'] = r['warnings'] + ['ENV_NOT_APPLIED']
            return r
        return self.walk(warnings)

    def bind(self, names, source, matched, warnings, ignored, bind_path):
        self.gate(names[0], bind_path)
        extra = [] if self.usable(names[0]) else []
        for n in names[1:]:
            if not self.usable(n):
                extra.append('CANDIDATE_UNAVAILABLE')
        return self.resolve_account(names[0], source, matched, list(warnings) + extra, ignored, bind_path, candidates=list(names))

    def walk(self, warnings):
        P, fs = self.P, self.fs
        start = P.norm(self.c['cwd'])
        levels = []
        cur = start
        ceil = [P.norm(x) for x in self.opts.get('ceilingDirs', [])]
        while True:
            levels.append(cur)
            if any((fold(cur) == fold(c)) if self.c['caseInsensitive'] else cur == c for c in ceil):
                break
            par = P.parent(cur)
            if par is None:
                break
            cur = par
        git = []
        for d in levels:
            try:
                fs.lstat(P.join(d, '.git'))
                git.append(True)
            except FsErr:
                git.append(False)
        trust = self.opts.get('trustRepoMarkers', False)
        ignored = []
        loaded = None
        for i, d in enumerate(levels):
            mp = P.join(d, '.claude-account')
            cand = False
            try:
                fs.lstat(mp)
                try:
                    cand = fs.stat(mp).type != 'dir'
                except FsErr:
                    cand = False
            except FsErr:
                pass
            if cand and not trust and any(git[i:]):
                ignored.append(mp)
                warnings = warnings + ['MARKER_IGNORED_IN_REPO']
            else:
                m = self.parse_marker(mp)
                if m['kind'] in ('account', 'default', 'list'):
                    return self.bind(m['candidates'], 'marker-file', mp, warnings, ignored, mp)
                if m['kind'] == 'pool':
                    return {'account': None, 'pool': m['pool'], 'configDir': None, 'canonical': False,
                            'reason': None, 'source': 'marker-file', 'matchedPath': mp, 'exists': False,
                            'aliasOf': None, 'launchEnv': None, 'overriddenBy': self.overridden(None),
                            'ignoredMarkers': ignored, 'warnings': warnings, 'applied': True,
                            'candidates': [], 'globalConfig': None}
            # claims
            if loaded is None:
                for a in self.accounts():
                    if a['state'] != 'ok':
                        continue
                    st, dd = self.spec(a)
                    if st == 'invalid':
                        raise Err('SPEC_FILE_INVALID', dd)
                loaded = self.primaries()
            try:
                ls = fs.stat(d)
            except FsErr:
                ls = None
            claimants = []
            if ls is not None:
                for a in loaded:
                    st, dd = self.spec(a)
                    if st != 'ok':
                        continue
                    for x in dd.get('directories', []):
                        e = self.expand_claim(x)
                        try:
                            s = fs.stat(e)
                        except FsErr:
                            continue
                        if (s.dev, s.ino) == (ls.dev, ls.ino):
                            claimants.append(a['name'])
                            break
            if len(claimants) > 1:
                raise Err('CLAIM_CONFLICT', d)
            if claimants:
                return self.resolve_account(claimants[0], 'claim', d, warnings, ignored, d)
        return self.resolve_account('default', 'default', None, warnings, ignored)


WRITE_OPS = ('create', 'handover_session', 'mark_limited', 'clear_limited', 'adopt', 'activate', 'update_spec_file', 'claim', 'unclaim')


def main():
    case = json.load(sys.stdin)
    lib = Lib(case)
    op = case['op']
    out = {}
    try:
        res = getattr(lib, 'op_' + op['name'])(op.get('args', {}))
        out['result'] = res
    except Err as e:
        out['error'] = {'code': e.code, 'path': e.path, 'message': e.code}
    except FsErr as e:
        out['error'] = {'code': 'IO_ERROR', 'path': None, 'message': e.code}
    if op['name'] in WRITE_OPS:
        out['fs'] = lib.fs.dump()
    print(json.dumps(out))


if __name__ == '__main__':
    main()
