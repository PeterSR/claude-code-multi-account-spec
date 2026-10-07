"""Helpers for the case generator. Run conformance/gen/generate.py to rewrite conformance/cases/."""
import json, os, hashlib, base64, re

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cases')
NOW = '2026-10-06T12:00:00Z'
CASES = {}
UNSET = object()


class W:
    def __init__(self, plat):
        self.plat = plat
        self.win = plat == 'win32'
        self.sep = '\\' if self.win else '/'
        self.h = {'linux': '/home/p', 'darwin': '/Users/p', 'win32': 'C:\\Users\\p'}[plat]
        self.root = 'C:\\' if self.win else '/'

    def __call__(self, *parts):
        return self.h + ''.join(self.sep + p for p in parts)

    def r(self, *parts):
        return self.root + self.sep.join(parts)

    def j(self, base, *parts):
        return base + ''.join(self.sep + p for p in parts)


def D(**k):
    return dict(type='dir', **k)


def F(content='', **k):
    return dict(type='file', content=content, **k)


def L(t, **k):
    return dict(type='symlink', target=t, **k)


def J(t, **k):
    return dict(type='junction', target=t, **k)


def FB(b, **k):
    return dict(type='file', contentBase64=base64.b64encode(b).decode('ascii'), **k)


def X(**k):
    return dict(type='fifo', **k)


def DEV(**k):
    return dict(type='device', **k)


def ok(result):
    return {'result': result}


def err(code, path=UNSET):
    e = {'code': code}
    if path is not UNSET:
        e['path'] = path
    return {'error': e}


def mk(id, desc, spec, op, expect, plat='linux', ci=None, home=None, cwd=None, env=None, opts=None,
       fs=None, now=NOW, processes=None, domain=None, expectFs=None, reserved=None, nohome=False):
    assert id not in CASES, id
    w = W(plat)
    if ci is None:
        ci = plat != 'linux'
    home = home or w.h
    f = {}
    if not nohome:
        f[home] = D()
    f.update(fs or {})
    c = {'id': id, 'description': desc, 'spec': spec if isinstance(spec, list) else [spec],
         'platform': plat, 'caseInsensitive': ci, 'home': home, 'cwd': cwd or home,
         'env': env or {}, 'options': opts or {}, 'now': now, 'fs': f}
    if reserved is not None:
        c['reserved'] = reserved
    if processes is not None:
        c['processes'] = processes
    if domain is not None:
        c['callerPidDomain'] = domain
    c['op'] = op
    c['expect'] = expect
    if expectFs is None and 'result' in expect:
        n, a = op['name'], op['args']
        cfg = lambda nm: home + w.sep + ('.claude' if nm == 'default' else '.claude-' + nm)
        if n in ('mark_limited', 'clear_limited'):
            expectFs = {cfg(a['name']) + w.sep + '.multi-account-state.json':
                        {'type': 'file', 'mode': '0600', 'contentJson': {'version': 1, 'limits': expect['result']['limits']}}}
        elif n == 'handover_session':
            expectFs = {cfg(a['to']) + w.sep + rel.replace('/', w.sep): {'type': 'file'} for rel in expect['result']['copied']}
        elif n == 'activate':
            expectFs = {home + w.sep + '.claude': {'target': cfg(a['name'])},
                        home + w.sep + '.claude.json': {'target': cfg(a['name']) + w.sep + '.claude.json'}}
    if expectFs is not None:
        c['expectFs'] = expectFs
    CASES[id] = c
    return c


def op(_n, /, **args):
    return {'name': _n, 'args': args}


def jd(o):
    return json.dumps(o)


def spec(**k):
    d = {'version': 1}
    d.update(k)
    return jd(d)


def launch(w, name):
    if name == 'default':
        return {'set': {'CLAUDE_MULTI_ACCOUNT': 'default'},
                'unset': ['CLAUDE_CONFIG_DIR', 'CLAUDE_MULTI_ACCOUNT_SOURCE', 'CLAUDE_SECURESTORAGE_CONFIG_DIR']}
    return {'set': {'CLAUDE_CONFIG_DIR': w('.claude-' + name), 'CLAUDE_MULTI_ACCOUNT': name},
            'unset': ['CLAUDE_MULTI_ACCOUNT_SOURCE', 'CLAUDE_SECURESTORAGE_CONFIG_DIR']}


def gc_join(w, d):
    """globalConfig for a config-dir source: join(value, '.claude.json'), None for a relative value."""
    if w.win:
        if not re.match(r'^[A-Za-z]:[\\/]', d):
            return None
        d = re.sub(r'[\\/]+', lambda m: '\\', d).rstrip('\\')
    else:
        if not d.startswith('/'):
            return None
        d = re.sub(r'/+', '/', d).rstrip('/')
    return d + w.sep + '.claude.json'


def rr(w, account, source, matched=None, **over):
    cfg = w('.claude') if account == 'default' else w('.claude-' + (account or 'x'))
    if 'globalConfig' in over:
        gc = over['globalConfig']
    elif source == 'config-dir' and 'configDir' in over:
        gc = gc_join(w, over['configDir']) if over['configDir'] else None
    elif account is None:
        gc = None
    elif account == 'default':
        gc = w('.claude.json')
    else:
        gc = cfg + w.sep + '.claude.json'
    d = {'account': account, 'pool': None, 'configDir': cfg, 'canonical': True, 'reason': None,
         'source': source, 'matchedPath': matched, 'exists': True, 'aliasOf': None,
         'launchEnv': launch(w, account or 'x'), 'overriddenBy': [], 'ignoredMarkers': [], 'warnings': [],
         'applied': True, 'candidates': [account] if account else [], 'globalConfig': gc}
    # CLAUDE_MULTI_ACCOUNT alone naming a named account is not applied (outside claude)
    auto = source == 'env' and account not in (None, 'default') and 'applied' not in over
    d.update(over)
    if auto:
        d['applied'] = False
        d['warnings'] = list(d['warnings']) + ['ENV_NOT_APPLIED']
    return d


def acct(w, *names, **extra):
    d = {}
    for n in names:
        d[w('.claude-' + n)] = D()
    return d


def write_all():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith('.json'):
            os.remove(os.path.join(OUT, f))
    for id, c in CASES.items():
        with open(os.path.join(OUT, id + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(c, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
