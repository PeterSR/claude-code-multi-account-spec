from gen_lib import *
from gen_a import wl, wd, ww, W_
import hashlib, datetime


def cpok(d):
    d.setdefault('skipped', [])
    return ok(d)

MA = 'CLAUDE_MULTI_ACCOUNT'
CC = 'CLAUDE_CONFIG_DIR'
LS = 'CLAUDE_MULTI_ACCOUNT_SOURCE'
SS = 'CLAUDE_SECURESTORAGE_CONFIG_DIR'
ENVTOK = 'CLAUDE_CODE_OAUTH_TOKEN'
APIK = 'ANTHROPIC_API_KEY'
CLEARED = sorted(['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_PROFILE', 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK',
                  'CLAUDE_CODE_USE_FOUNDRY', 'CLAUDE_CODE_USE_VERTEX'])


def h8(s):
    return hashlib.sha256(s.encode()).hexdigest()[:8]


# ================= B1 env
mk('b1-env-named', 'env delta for a named account', 'B1', op('env', name='work'),
   ok({'set': {CC: '/home/p/.claude-work', MA: 'work'}, 'unset': [LS, SS], 'overriddenBy': []}))
mk('b1-env-default', 'default: unset CLAUDE_CONFIG_DIR, never set it', ['B1', 'A2 Canonical path'], op('env', name='default'),
   ok({'set': {MA: 'default'}, 'unset': [CC, LS, SS], 'overriddenBy': []}))
mk('b1-env-win32', 'win32 canonical path in the delta', 'B1', op('env', name='work'),
   ok({'set': {CC: 'C:\\Users\\p\\.claude-work', MA: 'work'}, 'unset': [LS, SS], 'overriddenBy': []}), plat='win32')
mk('b1-env-pure-no-account-needed', 'env does not look for the account on disk', 'B1', op('env', name='ghost'),
   ok({'set': {CC: '/home/p/.claude-ghost', MA: 'ghost'}, 'unset': [LS, SS], 'overriddenBy': []}))
mk('b1-env-reserved-name-ok', 'env is a pure function and ignores reservation', 'B1', op('env', name='profiles'),
   ok({'set': {CC: '/home/p/.claude-profiles', MA: 'profiles'}, 'unset': [LS, SS], 'overriddenBy': []}))
mk('b1-env-invalid-name', 'invalid name', 'B1', op('env', name='Work'), err('INVALID_NAME', None))
mk('b1-env-reports-auth-overrides', 'auth overrides are reported, not touched', 'B1',
   op('env', name='work'),
   ok({'set': {CC: '/home/p/.claude-work', MA: 'work'}, 'unset': [LS, SS], 'overriddenBy': [ENVTOK, APIK]}),
   env={ENVTOK: 't', APIK: 'k'})
mk('b1-env-clear-auth-overrides', 'clearAuthOverrides unsets both and stops reporting them', 'B1',
   op('env', name='work', clearAuthOverrides=True),
   ok({'set': {CC: '/home/p/.claude-work', MA: 'work'}, 'unset': CLEARED + [LS, SS], 'overriddenBy': []}),
   env={ENVTOK: 't', APIK: 'k'})
mk('b1-env-clear-auth-overrides-default', 'clearAuthOverrides for default', 'B1',
   op('env', name='default', clearAuthOverrides=True),
   ok({'set': {MA: 'default'}, 'unset': sorted(CLEARED + [CC, LS, SS]), 'overriddenBy': []}))
mk('b1-env-securestorage-reported-and-unset', 'SECURESTORAGE is unset by the delta and still reported', 'B1',
   op('env', name='work'),
   ok({'set': {CC: '/home/p/.claude-work', MA: 'work'}, 'unset': [LS, SS], 'overriddenBy': [SS]}), env={SS: '/elsewhere'})
mk('b1-env-api-key-helper-reported', 'apiKeyHelper from settings.json is reported', 'B1',
   op('env', name='work'),
   ok({'set': {CC: '/home/p/.claude-work', MA: 'work'}, 'unset': [LS, SS], 'overriddenBy': ['apiKeyHelper']}),
   fs={'/home/p/.claude-work/settings.json': F('{"apiKeyHelper": "/bin/k"}')})
mk('b1-env-custom-oauth-reported', 'custom oauth URL is reported', 'B1',
   op('env', name='work'),
   ok({'set': {CC: '/home/p/.claude-work', MA: 'work'}, 'unset': [LS, SS], 'overriddenBy': ['CLAUDE_CODE_CUSTOM_OAUTH_URL']}),
   env={'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'https://x.test'})

# credential_locations
def cf(w, n):
    return {'file': (w('.claude') if n == 'default' else w('.claude-' + n)) + w.sep + '.credentials.json'}

def loc(id, desc, name, locs, plat='linux', **kw):
    mk(id, desc, ['B1', 'A1', 'A2 Canonical path'], op('credential_locations', name=name), ok({'locations': locs}), plat=plat, **kw)

loc('b1-cred-linux-named', 'linux: file only', 'work', [cf(wl, 'work')])
loc('b1-cred-linux-default', 'linux default', 'default', [cf(wl, 'default')])
loc('b1-cred-linux-ignores-keychain-env', 'linux ignores Windows credman variable', 'work', [cf(wl, 'work')],
    env={'CLAUDE_CODE_FORCE_WINDOWS_CREDMAN': '1'})
loc('b1-cred-darwin-named', 'darwin: hashed keychain item then file', 'work',
    [{'keychain': {'service': 'Claude Code-credentials-' + h8('/Users/p/.claude-work'), 'account': 'user'}}, cf(wd, 'work')],
    plat='darwin', env={'USER': 'user'})
loc('b1-cred-darwin-default', 'darwin default: unsuffixed item', 'default',
    [{'keychain': {'service': 'Claude Code-credentials', 'account': 'user'}}, cf(wd, 'default')], plat='darwin', env={'USER': 'user'})
loc('b1-cred-darwin-custom-oauth', 'darwin: custom oauth suffix in the service', 'work',
    [{'keychain': {'service': 'Claude Code-custom-oauth-credentials-' + h8('/Users/p/.claude-work'), 'account': 'user'}}, cf(wd, 'work')],
    plat='darwin', env={'USER': 'user', 'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'https://x.test'})
loc('b1-cred-darwin-custom-oauth-default', 'darwin default with custom oauth suffix', 'default',
    [{'keychain': {'service': 'Claude Code-custom-oauth-credentials', 'account': 'user'}}, cf(wd, 'default')],
    plat='darwin', env={'USER': 'user', 'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'x'})
loc('b1-cred-darwin-hash-follows-config-home', 'the hash input is the canonical path (NFC), so a different home hashes differently', 'work',
    [{'keychain': {'service': 'Claude Code-credentials-' + h8('/Users/q/.claude-work'), 'account': 'user'}},
     {'file': '/Users/q/.claude-work/.credentials.json'}], plat='darwin', env={'USER': 'user'}, home='/Users/q')
loc('b1-cred-darwin-bad-user-fallback', 'user name failing the pattern becomes claude-code-user', 'work',
    [{'keychain': {'service': 'Claude Code-credentials-' + h8('/Users/p/.claude-work'), 'account': 'claude-code-user'}}, cf(wd, 'work')],
    plat='darwin', env={'USER': 'bad user'})
loc('b1-cred-darwin-username-option', 'with USER unset the OS user name input is used', 'work',
    [{'keychain': {'service': 'Claude Code-credentials-' + h8('/Users/p/.claude-work'), 'account': 'osuser.1'}}, cf(wd, 'work')],
    plat='darwin', opts={'userName': 'osuser.1'})
loc('b1-cred-darwin-empty-user-uses-option', 'empty USER counts as unset', 'work',
    [{'keychain': {'service': 'Claude Code-credentials-' + h8('/Users/p/.claude-work'), 'account': 'osuser'}}, cf(wd, 'work')],
    plat='darwin', env={'USER': ''}, opts={'userName': 'osuser'})
loc('b1-cred-darwin-no-user-at-all', 'no USER and no user name: fallback', 'work',
    [{'keychain': {'service': 'Claude Code-credentials-' + h8('/Users/p/.claude-work'), 'account': 'claude-code-user'}}, cf(wd, 'work')],
    plat='darwin')
loc('b1-cred-win32-file', 'win32 default: file only', 'work', [cf(ww, 'work')], plat='win32')
loc('b1-cred-win32-credman-env', 'FORCE_WINDOWS_CREDMAN=1 puts Credential Manager first', 'work',
    [{'credentialManager': {}}, cf(ww, 'work')], plat='win32', env={'CLAUDE_CODE_FORCE_WINDOWS_CREDMAN': '1'})
loc('b1-cred-win32-credman-env-not-1', 'only the value 1 enables it', 'work', [cf(ww, 'work')], plat='win32',
    env={'CLAUDE_CODE_FORCE_WINDOWS_CREDMAN': '0'})
loc('b1-cred-win32-credman-flag', 'cached GrowthBook flag in the account global config', 'work',
    [{'credentialManager': {}}, cf(ww, 'work')], plat='win32',
    fs={'C:\\Users\\p\\.claude-work\\.claude.json': F(jd({'cachedGrowthBookFeatures': {'tengu_windows_credman': True}}))})
loc('b1-cred-win32-credman-flag-false', 'flag present but false', 'work', [cf(ww, 'work')], plat='win32',
    fs={'C:\\Users\\p\\.claude-work\\.claude.json': F(jd({'cachedGrowthBookFeatures': {'tengu_windows_credman': False}}))})
loc('b1-cred-win32-credman-flag-default-account', 'default reads the flag from $HOME/.claude.json', 'default',
    [{'credentialManager': {}}, cf(ww, 'default')], plat='win32',
    fs={'C:\\Users\\p\\.claude.json': F(jd({'cachedGrowthBookFeatures': {'tengu_windows_credman': True}}))})
mk('b1-cred-invalid-name', 'invalid name', 'B1', op('credential_locations', name='A'), err('INVALID_NAME', None))

# ================= B2 identity / usage
OA = {'emailAddress': 'a@b.c', 'organizationName': 'Acme', 'organizationUuid': 'org-1', 'organizationType': 'claude_max',
      'billingType': 'stripe_subscription', 'userRateLimitTier': 'default_claude_max_5x', 'organizationRateLimitTier': 'default_claude_max_5x',
      'accountUuid': 'acc-1'}
IDENT = {'email': 'a@b.c', 'orgName': 'Acme', 'orgUuid': 'org-1', 'organizationType': 'claude_max', 'billingType': 'stripe_subscription',
         'userRateLimitTier': 'default_claude_max_5x', 'organizationRateLimitTier': 'default_claude_max_5x'}
GC = '/home/p/.claude-work/.claude.json'
mk('b2-identity-basic', 'oauthAccount fields from the account global config', 'B2', op('identity', name='work'), ok(IDENT),
   fs={GC: F(jd({'oauthAccount': OA, 'other': 1}))})
mk('b2-identity-default-uses-home-json', 'default reads $HOME/.claude.json', ['B2', 'A1'], op('identity', name='default'), ok(IDENT),
   fs={'/home/p/.claude.json': F(jd({'oauthAccount': OA})), '/home/p/.claude/.claude.json': F(jd({'oauthAccount': {'emailAddress': 'wrong'}}))})
mk('b2-identity-legacy-config-wins', 'legacy .config.json takes precedence', ['B2', 'A1'], op('identity', name='work'),
   ok({**IDENT, 'email': 'legacy@b.c'}),
   fs={GC: F(jd({'oauthAccount': OA})), '/home/p/.claude-work/.config.json': F(jd({'oauthAccount': {**OA, 'emailAddress': 'legacy@b.c'}}))})
mk('b2-identity-custom-oauth-file', 'with a custom oauth URL the suffixed file is read', ['B2', 'A1'], op('identity', name='work'), ok(IDENT),
   env={'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'https://x.test'},
   fs={GC: F(jd({'oauthAccount': {'emailAddress': 'plain'}})), '/home/p/.claude-work/.claude-custom-oauth.json': F(jd({'oauthAccount': OA}))})
mk('b2-identity-missing-keys-null', 'missing keys are null', 'B2', op('identity', name='work'),
   ok({**{k: None for k in IDENT}, 'email': 'a@b.c'}), fs={GC: F(jd({'oauthAccount': {'emailAddress': 'a@b.c'}}))})
mk('b2-identity-no-oauth-account', 'no oauthAccount: null', 'B2', op('identity', name='work'), ok(None), fs={GC: F('{}')})
mk('b2-identity-no-file', 'no global config: null', 'B2', op('identity', name='work'), ok(None), fs=acct(wl, 'work'))
mk('b2-identity-bad-json', 'unparseable global config: null', 'B2', op('identity', name='work'), ok(None), fs={GC: F('{bad')})
mk('b2-identity-oauth-not-object', 'oauthAccount that is not an object: null', 'B2', op('identity', name='work'), ok(None),
   fs={GC: F(jd({'oauthAccount': 'x'}))})
mk('b2-identity-link-account', 'account dir behind a link', 'B2', op('identity', name='work'), ok(IDENT),
   fs={'/home/p/.claude-work': L('/data/w'), '/data/w/.claude.json': F(jd({'oauthAccount': OA}))})
mk('b2-identity-account-not-found', 'unknown account', 'B2', op('identity', name='work'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'))
mk('b2-identity-account-unavailable', 'dangling account', 'B2', op('identity', name='work'), err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-work'),
   fs={'/home/p/.claude-work': L('/mnt/gone')})
mk('b2-identity-invalid-name', 'invalid name', 'B2', op('identity', name='W'), err('INVALID_NAME', None))
mk('b2-identity-win32', 'win32 path', 'B2', op('identity', name='work'), ok(IDENT), plat='win32',
   fs={'C:\\Users\\p\\.claude-work\\.claude.json': F(jd({'oauthAccount': OA}))})

FRESH = 1791287400000  # 10 minutes before NOW
CU = {'utilization': {'five_hour': {'utilization': 42.5, 'resets_at': '2026-10-06T15:00:00Z'}, 'seven_day': {'utilization': 10, 'resets_at': '2026-10-09T14:00:00Z'},
      'seven_day_opus': {'utilization': 80.25, 'resets_at': '2026-10-09T14:00:00Z'}}, 'fetchedAtMs': FRESH, 'accountUuid': 'acc-1'}
WIN = {'five_hour': {'utilization': 42.5, 'resetsAt': '2026-10-06T15:00:00Z'}, 'seven_day': {'utilization': 10, 'resetsAt': '2026-10-09T14:00:00Z'},
       'seven_day_opus': {'utilization': 80.25, 'resetsAt': '2026-10-09T14:00:00Z'}}
def uexp(fetched, data, windows, stale):
    return ok({'fetchedAt': fetched, 'data': data, 'windows': windows, 'stale': stale})
def iso_ms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (ms % 1000)
mk('b2-usage-basic', 'cached usage with fetchedAt', 'B2', op('usage', name='work'),
   uexp(iso_ms(FRESH), CU, WIN, False), fs={GC: F(jd({'oauthAccount': OA, 'cachedUsageUtilization': CU}))})
CU2 = dict(CU, fetchedAtMs=FRESH + 123)
mk('b2-usage-milliseconds', 'fetchedAt keeps three fractional digits', 'B2', op('usage', name='work'),
   uexp(iso_ms(FRESH + 123), CU2, WIN, False), fs={GC: F(jd({'oauthAccount': OA, 'cachedUsageUtilization': CU2}))})
CU3 = {k: v for k, v in CU.items() if k != 'fetchedAtMs'}
mk('b2-usage-no-fetched-at', 'no fetchedAtMs: fetchedAt null', 'B2', op('usage', name='work'),
   uexp(None, CU3, WIN, True), fs={GC: F(jd({'cachedUsageUtilization': CU3}))})
mk('b2-usage-absent', 'no cachedUsageUtilization: null', 'B2', op('usage', name='work'), ok(None), fs={GC: F('{}')})
mk('b2-usage-default', 'default reads $HOME/.claude.json', 'B2', op('usage', name='default'),
   uexp(iso_ms(FRESH), CU, WIN, False), fs={'/home/p/.claude.json': F(jd({'oauthAccount': OA, 'cachedUsageUtilization': CU}))})
mk('b2-usage-not-object', 'cachedUsageUtilization not an object: null', 'B2', op('usage', name='work'), ok(None),
   fs={GC: F(jd({'cachedUsageUtilization': 5}))})
mk('b2-usage-account-not-found', 'unknown account', 'B2', op('usage', name='nope'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))

# ================= B3 live sessions
SD = '/home/p/.claude-work/sessions/'
def sess(pid, sid='s-%d', start='T1', dom='host-1', **kw):
    d = {'pid': pid, 'sessionId': sid % pid if '%' in sid else sid, 'procStart': start}
    if dom is not None:
        d['pidDomain'] = dom
    d.update(kw)
    return F(jd(d))
def ls(id, desc, files, procs, expect, domain=None, name='work', **kw):
    fsd = {SD + k: v for k, v in files.items()}
    fsd.update(kw.pop('fs', {}))
    mk(id, desc, 'B3', op('live_sessions', name=name), ok({'sessions': expect}), fs=fsd, processes=procs, domain=domain, **kw)

ls('b3-live', 'pid exists and procStart matches', {'101.json': sess(101)}, {'101': {'procStart': 'T1', 'pidDomain': 'host-1'}},
   [{'pid': 101, 'sessionId': 's-101', 'status': 'live'}])
ls('b3-dead-start-mismatch', 'pid reused: procStart differs', {'101.json': sess(101)}, {'101': {'procStart': 'T2', 'pidDomain': 'host-1'}},
   [{'pid': 101, 'sessionId': 's-101', 'status': 'dead'}])
ls('b3-dead-no-process', 'pid not in the table', {'101.json': sess(101)}, {},
   [{'pid': 101, 'sessionId': 's-101', 'status': 'dead'}])
ls('b3-unknown-other-domain', 'a different pidDomain is unknown, never dead', {'101.json': sess(101, dom='container-9')}, {},
   [{'pid': 101, 'sessionId': 's-101', 'status': 'unknown'}])
ls('b3-unknown-even-if-pid-matches', 'domain check comes first', {'101.json': sess(101, dom='container-9')},
   {'101': {'procStart': 'T1', 'pidDomain': 'host-1'}}, [{'pid': 101, 'sessionId': 's-101', 'status': 'unknown'}])
ls('b3-caller-domain-input', 'the caller domain is an input', {'101.json': sess(101, dom='wsl-1')},
   {'101': {'procStart': 'T1', 'pidDomain': 'wsl-1'}}, [{'pid': 101, 'sessionId': 's-101', 'status': 'live'}], domain='wsl-1')
ls('b3-no-domain-in-file-is-same-domain', 'a file without pidDomain is treated as the caller domain', {'101.json': sess(101, dom=None)},
   {'101': {'procStart': 'T1', 'pidDomain': 'host-1'}}, [{'pid': 101, 'sessionId': 's-101', 'status': 'live'}])
ls('b3-sorted-numerically', 'sorted by numeric pid', {'100.json': sess(100), '9.json': sess(9), '10.json': sess(10)},
   {'10': {'procStart': 'T1', 'pidDomain': 'host-1'}},
   [{'pid': 9, 'sessionId': 's-9', 'status': 'dead'}, {'pid': 10, 'sessionId': 's-10', 'status': 'live'}, {'pid': 100, 'sessionId': 's-100', 'status': 'dead'}])
ls('b3-ignores-odd-files', 'only <digits>.json files that parse to objects count',
   {'5.json': sess(5), 'abc.json': sess(6), '7.json.bak': sess(7), 'x8.json': sess(8), '9.txt': sess(9), '11.json': F('{bad'), '12.json': F('[1]')},
   {}, [{'pid': 5, 'sessionId': 's-5', 'status': 'dead'}])
ls('b3-missing-session-id', 'sessionId missing: null', {'5.json': F(jd({'pid': 5, 'procStart': 'T1', 'pidDomain': 'host-1'}))},
   {'5': {'procStart': 'T1', 'pidDomain': 'host-1'}}, [{'pid': 5, 'sessionId': None, 'status': 'live'}])
mk('b3-no-sessions-dir', 'no sessions directory', 'B3', op('live_sessions', name='work'), ok({'sessions': []}), fs=acct(wl, 'work'))
mk('b3-default-account', 'default sessions live in ~/.claude/sessions', 'B3', op('live_sessions', name='default'),
   ok({'sessions': [{'pid': 7, 'sessionId': 's-7', 'status': 'live'}]}), fs={'/home/p/.claude/sessions/7.json': sess(7)},
   processes={'7': {'procStart': 'T1', 'pidDomain': 'host-1'}})
mk('b3-account-not-found', 'unknown account', 'B3', op('live_sessions', name='nope'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))
mk('b3-win32', 'win32 session registry', 'B3', op('live_sessions', name='work'), ok({'sessions': [{'pid': 4, 'sessionId': 's-4', 'status': 'live'}]}),
   plat='win32', fs={'C:\\Users\\p\\.claude-work\\sessions\\4.json': sess(4)}, processes={'4': {'procStart': 'T1', 'pidDomain': 'host-1'}})

# ================= B4 handover
A = '/home/p/.claude-a'
B = '/home/p/.claude-b'
SID = 'sess-1'
def src_files(root=A, id_=SID):
    return {
        root + '/projects/-home-p-x/%s.jsonl' % id_: F('line1\nline2\n', mode='0600'),
        root + '/projects/-home-p-x/%s/subagents/a.jsonl' % id_: F('sub', mode='0600'),
        root + '/projects/-home-p-x/%s/tool-results/r.txt' % id_: F('res', mode='0644'),
        root + '/file-history/%s/v1' % id_: F('hist', mode='0600'),
        root + '/session-env/%s/env.sh' % id_: F('export A=1', mode='0600'),
        root + '/tasks/%s/t.json' % id_: F('{}', mode='0600'),
        root + '/projects/-home-p-x/other.jsonl': F('not this one'),
        root + '/projects/-home-p-y': D(),
        root + '/tasks/other-id/t.json': F('{}'),
    }
FULL_COPIED = ['file-history/sess-1/v1', 'projects/-home-p-x/sess-1.jsonl', 'projects/-home-p-x/sess-1/subagents/a.jsonl',
               'projects/-home-p-x/sess-1/tool-results/r.txt', 'session-env/sess-1/env.sh', 'tasks/sess-1/t.json']
HO = op('handover_session', id=SID, **{'from': 'a', 'to': 'b'})
BASE = {A: D(), B: D()}
mk('b4-handover-full-copy', 'all five locations are copied, nothing else, source untouched', 'B4', HO, cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files()},
   expectFs={B + '/projects': {'type': 'dir', 'mode': '0700'}, B + '/projects/-home-p-x': {'type': 'dir', 'mode': '0700'},
             B + '/projects/-home-p-x/sess-1.jsonl': {'type': 'file', 'content': 'line1\nline2\n', 'mode': '0600'},
             B + '/projects/-home-p-x/sess-1/subagents/a.jsonl': {'type': 'file', 'content': 'sub', 'mode': '0600'},
             B + '/projects/-home-p-x/sess-1/tool-results/r.txt': {'type': 'file', 'content': 'res', 'mode': '0644'},
             B + '/projects/-home-p-x/sess-1/tool-results': {'type': 'dir', 'mode': '0700'},
             B + '/file-history/sess-1/v1': {'type': 'file', 'content': 'hist'},
             B + '/session-env/sess-1/env.sh': {'type': 'file', 'content': 'export A=1'},
             B + '/tasks/sess-1/t.json': {'type': 'file', 'content': '{}'},
             B + '/projects/-home-p-x/other.jsonl': None, B + '/tasks/other-id': None, B + '/projects/-home-p-y': None,
             A + '/projects/-home-p-x/sess-1.jsonl': {'type': 'file', 'content': 'line1\nline2\n'},
             A + '/tasks/sess-1/t.json': {'type': 'file'}})
mk('b4-handover-partial', 'only the locations that exist are copied', 'B4', HO, cpok({'copied': ['projects/-home-p-x/sess-1.jsonl']}),
   fs={**BASE, A + '/projects/-home-p-x/sess-1.jsonl': F('t')},
   expectFs={B + '/projects/-home-p-x/sess-1.jsonl': {'type': 'file', 'content': 't'}, B + '/tasks': None, B + '/file-history': None})
mk('b4-handover-two-slugs', 'the same id under two project slugs is copied under both', 'B4', HO,
   cpok({'copied': ['projects/-s1/sess-1.jsonl', 'projects/-s2/sess-1.jsonl']}),
   fs={**BASE, A + '/projects/-s1/sess-1.jsonl': F('1'), A + '/projects/-s2/sess-1.jsonl': F('2')},
   expectFs={B + '/projects/-s1/sess-1.jsonl': {'content': '1'}, B + '/projects/-s2/sess-1.jsonl': {'content': '2'}})
mk('b4-handover-session-not-found', 'nothing for that id in the source', 'B4', HO, err('SESSION_NOT_FOUND', None),
   fs={**BASE, A + '/tasks/other/t.json': F('{}')}, expectFs={B + '/tasks': None})
mk('b4-handover-from-default', 'from the default account', 'B4', op('handover_session', id=SID, **{'from': 'default', 'to': 'b'}),
   cpok({'copied': ['tasks/sess-1/t.json']}), fs={'/home/p/.claude/tasks/sess-1/t.json': F('{}'), B: D()},
   expectFs={B + '/tasks/sess-1/t.json': {'type': 'file'}})
mk('b4-handover-to-default', 'to the default account', 'B4', op('handover_session', id=SID, **{'from': 'a', 'to': 'default'}),
   cpok({'copied': ['tasks/sess-1/t.json']}), fs={A + '/tasks/sess-1/t.json': F('{}')},
   expectFs={'/home/p/.claude/tasks/sess-1/t.json': {'type': 'file'}})
LIVE_FILES = {A + '/sessions/200.json': sess(200, sid=SID)}
LIVE_PROCS = {'200': {'procStart': 'T1', 'pidDomain': 'host-1'}}
mk('b4-handover-live-refused', 'a live session in the source blocks the copy', 'B4', HO, err('SESSION_LIVE', None),
   fs={**BASE, **src_files(), **LIVE_FILES}, processes=LIVE_PROCS, expectFs={B + '/projects': None, B + '/tasks': None})
mk('b4-handover-live-beats-exists', 'SESSION_LIVE is checked before SESSION_EXISTS', 'B4', HO, err('SESSION_LIVE', None),
   fs={**BASE, **src_files(), **LIVE_FILES, B + '/tasks/sess-1/t.json': F('old')}, processes=LIVE_PROCS)
mk('b4-handover-dead-session-ok', 'a dead session file does not block', 'B4', HO, cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), **LIVE_FILES}, processes={'200': {'procStart': 'OTHER', 'pidDomain': 'host-1'}})
mk('b4-handover-unknown-domain-refused', 'an unknown session (other pid domain) blocks like a live one', 'B4', HO, err('SESSION_LIVE', None),
   fs={**BASE, **src_files(), A + '/sessions/200.json': sess(200, sid=SID, dom='other-host')}, processes=LIVE_PROCS,
   expectFs={B + '/projects': None, B + '/tasks': None})
mk('b4-handover-unknown-domain-force-ok', 'force lets an unknown session through', 'B4',
   op('handover_session', id=SID, force=True, **{'from': 'a', 'to': 'b'}), cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), A + '/sessions/200.json': sess(200, sid=SID, dom='other-host')}, processes=LIVE_PROCS)
mk('b4-handover-other-live-session-ok', 'a live session with another id does not block', 'B4', HO, cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), A + '/sessions/200.json': sess(200, sid='another')}, processes=LIVE_PROCS)
mk('b4-handover-live-in-target-ok', 'only the source account is checked', 'B4', HO, cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), B + '/sessions/200.json': sess(200, sid=SID)}, processes=LIVE_PROCS)
mk('b4-handover-exists', 'destination already has the transcript', 'B4', HO, err('SESSION_EXISTS', None),
   fs={**BASE, **src_files(), B + '/projects/-home-p-x/sess-1.jsonl': F('old')},
   expectFs={B + '/projects/-home-p-x/sess-1.jsonl': {'content': 'old'}, B + '/tasks': None})
mk('b4-handover-exists-other-location', 'any one of the five locations counts as existing', 'B4', HO, err('SESSION_EXISTS', None),
   fs={**BASE, **src_files(), B + '/tasks/sess-1/old.json': F('old')}, expectFs={B + '/projects': None})
mk('b4-handover-overwrite', 'overwrite clears the destination locations then copies', 'B4',
   op('handover_session', id=SID, overwrite=True, **{'from': 'a', 'to': 'b'}), cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), B + '/tasks/sess-1/stale.json': F('stale'), B + '/projects/-home-p-x/sess-1.jsonl': F('old'),
       B + '/projects/-home-p-x/keep.jsonl': F('keep')},
   expectFs={B + '/tasks/sess-1/stale.json': None, B + '/projects/-home-p-x/sess-1.jsonl': {'content': 'line1\nline2\n'},
             B + '/projects/-home-p-x/keep.jsonl': {'content': 'keep'}, B + '/tasks/sess-1/t.json': {'content': '{}'}})
mk('b4-handover-to-not-found', 'destination account missing', 'B4', HO, err('ACCOUNT_NOT_FOUND', B), fs={A: D(), **src_files()})
mk('b4-handover-from-not-found', 'source account missing', 'B4', HO, err('ACCOUNT_NOT_FOUND', A), fs={B: D()})
mk('b4-handover-from-checked-first', 'both missing: the source is reported', 'B4', HO, err('ACCOUNT_NOT_FOUND', A))
mk('b4-handover-invalid-name', 'invalid account name', 'B4', op('handover_session', id=SID, **{'from': 'A', 'to': 'b'}), err('INVALID_NAME', None))
mk('b4-handover-win32', 'win32 copy', 'B4', op('handover_session', id=SID, **{'from': 'a', 'to': 'b'}),
   cpok({'copied': ['projects/-s1/sess-1.jsonl']}), plat='win32',
   fs={'C:\\Users\\p\\.claude-a\\projects\\-s1\\sess-1.jsonl': F('x'), 'C:\\Users\\p\\.claude-b': D()},
   expectFs={'C:\\Users\\p\\.claude-b\\projects\\-s1\\sess-1.jsonl': {'type': 'file', 'content': 'x'}})

# ================= B5 availability
SP = '/home/p/.claude-work/.multi-account-state.json'
E1 = {'window': 'seven_day', 'model': 'opus', 'until': '2026-10-09T14:00:00Z', 'reason': 'rate_limit', 'updatedBy': 'my-swapper'}
def stored(e, by=None, at=NOW):
    d = dict(e)
    d['updatedAt'] = at
    if by:
        d['updatedBy'] = by
    return d
def state(*limits, **extra):
    return F(jd({'version': 1, 'limits': list(limits), **extra}), mode='0600')
OLD = '2026-10-01T00:00:00Z'
ML = lambda e, **kw: op('mark_limited', name='work', entry=e)

mk('b5-mark-new-file', 'first mark creates the state file', 'B5', ML(E1), ok({'limits': [stored(E1)]}), fs=acct(wl, 'work'),
   expectFs={SP: {'type': 'file', 'mode': '0600', 'contentJson': {'version': 1, 'limits': [stored(E1)]}}, SP + '.lock': None})
mk('b5-mark-later-until-wins', 'same key: the later until replaces', 'B5', ML(E1), ok({'limits': [stored(E1)]}),
   fs={SP: state(stored(dict(E1, until='2026-10-08T00:00:00Z'), by='old', at=OLD))},
   expectFs={SP: {'contentJson': {'version': 1, 'limits': [stored(E1)]}}})
mk('b5-mark-earlier-until-keeps-old', 'same key: an earlier until is ignored', 'B5', ML(dict(E1, until='2026-10-08T00:00:00Z', updatedBy='new')),
   ok({'limits': [stored(E1, by='old', at=OLD)]}), fs={SP: state(stored(E1, by='old', at=OLD))},
   expectFs={SP: {'contentJson': {'version': 1, 'limits': [stored(E1, by='old', at=OLD)]}}})
mk('b5-mark-equal-until-replaces', 'same key and equal until: the new entry replaces', 'B5', ML(dict(E1, updatedBy='new')),
   ok({'limits': [stored(E1, by='new')]}), fs={SP: state(stored(E1, by='old', at=OLD))})
mk('b5-mark-instants-not-strings', 'until is compared as an instant, not as text', 'B5',
   ML(dict(E1, until='2026-10-09T14:00:00Z', updatedBy='new')), ok({'limits': [stored(E1, by='new')]}),
   fs={SP: state(stored(dict(E1, until='2026-10-09T09:59:59Z'), by='old', at=OLD))})
mk('b5-mark-drops-past-entries', 'entries whose until is past are dropped on write', 'B5', ML(E1),
   ok({'limits': [stored(E1)]}), fs={SP: state(stored(dict(E1, window='five_hour', model=None, until='2026-10-05T00:00:00Z'), at=OLD))},
   expectFs={SP: {'contentJson': {'version': 1, 'limits': [stored(E1)]}}})
mk('b5-mark-drops-until-equal-now', 'until == now is already past', 'B5', ML(E1), ok({'limits': [stored(E1)]}),
   fs={SP: state(stored(dict(E1, window='five_hour', model=None, until=NOW), at=OLD))})
mk('b5-mark-new-entry-already-past', 'a new entry that is already past is dropped', 'B5', ML(dict(E1, until='2026-10-06T11:59:59Z')),
   ok({'limits': []}), fs=acct(wl, 'work'), expectFs={SP: {'contentJson': {'version': 1, 'limits': []}}})
mk('b5-mark-model-null-is-its-own-key', 'a null-model entry and a model entry coexist, appended in order', 'B5',
   ML(dict(E1, model=None)), ok({'limits': [stored(E1, by='old', at=OLD), stored(dict(E1, model=None))]}),
   fs={SP: state(stored(E1, by='old', at=OLD))})
mk('b5-mark-different-window-is-its-own-key', 'a different window is a different key', 'B5', ML(dict(E1, window='five_hour')),
   ok({'limits': [stored(E1, by='old', at=OLD), stored(dict(E1, window='five_hour'))]}), fs={SP: state(stored(E1, by='old', at=OLD))})
mk('b5-mark-preserves-other-keys', 'unknown top-level keys survive', 'B5', ML(E1),
   ok({'limits': [stored(E1)]}), fs={SP: state(extra_key={'a': [1, 2]})},
   expectFs={SP: {'contentJson': {'version': 1, 'limits': [stored(E1)], 'extra_key': {'a': [1, 2]}}}})
mk('b5-mark-unparseable-state-refused', 'an unparseable state file is never overwritten', 'B5', ML(E1), err('STATE_FILE_INVALID', SP),
   fs={SP: F('{garbage')}, expectFs={SP: {'type': 'file', 'content': '{garbage'}, SP + '.lock': None})
mk('b5-mark-default-account', 'default keeps state in ~/.claude', 'B5', op('mark_limited', name='default', entry=E1), ok({'limits': [stored(E1)]}),
   fs={'/home/p/.claude': D()}, expectFs={'/home/p/.claude/.multi-account-state.json': {'type': 'file', 'mode': '0600'}})
mk('b5-mark-symlink-state-file-one-hop', 'a linked state file is written through, the link stays', ['B5', 'A3 File safety rules'], ML(E1),
   ok({'limits': [stored(E1)]}), fs={SP: L('/data/state.json'), '/data/state.json': state()},
   expectFs={SP: {'type': 'symlink', 'target': '/data/state.json'},
             '/data/state.json': {'type': 'file', 'mode': '0600', 'contentJson': {'version': 1, 'limits': [stored(E1)]}}})
mk('b5-mark-symlink-state-file-relative', 'a relative link target resolves against the link directory', ['B5', 'A3 File safety rules'], ML(E1),
   ok({'limits': [stored(E1)]}), fs={SP: L('../shared/state.json'), '/home/p/shared/state.json': state()},
   expectFs={SP: {'type': 'symlink', 'target': '../shared/state.json'},
             '/home/p/shared/state.json': {'contentJson': {'version': 1, 'limits': [stored(E1)]}}})
mk('b5-mark-stale-lock-removed', 'a lock older than 10 s is stale and is taken over', ['B5', 'A3 File safety rules'], ML(E1),
   ok({'limits': [stored(E1)]}), fs={SP + '.lock': D(mtime='2026-10-06T11:59:00Z')}, expectFs={SP + '.lock': None, SP: {'type': 'file'}})
mk('b5-mark-lock-11s-is-stale', 'a lock 11 s old is stale', 'A3 File safety rules', ML(E1),
   ok({'limits': [stored(E1)]}), fs={SP + '.lock': D(mtime='2026-10-06T11:59:49Z')}, expectFs={SP + '.lock': None})
mk('b5-mark-lock-10s-is-not-stale', 'a lock exactly 10 s old is not older than 10 s', 'A3 File safety rules', ML(E1),
   err('LOCK_BUSY', SP + '.lock'), fs={SP + '.lock': D(mtime='2026-10-06T11:59:50Z')},
   expectFs={SP + '.lock': {'type': 'dir'}, SP: None})
mk('b5-mark-fresh-lock-busy', 'a fresh lock held by someone else', 'A3 File safety rules', ML(E1),
   err('LOCK_BUSY', SP + '.lock'), fs={SP + '.lock': D()}, expectFs={SP + '.lock': {'type': 'dir'}, SP: None})
mk('b5-mark-account-not-found', 'unknown account', 'B5', op('mark_limited', name='nope', entry=E1), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))
mk('b5-mark-win32', 'win32 paths', 'B5', ML(E1), ok({'limits': [stored(E1)]}), plat='win32', fs=acct(ww, 'work'),
   expectFs={'C:\\Users\\p\\.claude-work\\.multi-account-state.json': {'type': 'file', 'mode': '0600', 'contentJson': {'version': 1, 'limits': [stored(E1)]}}})

E2 = {'window': 'five_hour', 'model': None, 'until': '2026-10-06T18:00:00Z', 'reason': 'rate_limit', 'updatedBy': 'x'}
CL = lambda w, m: op('clear_limited', name='work', window=w, model=m)
mk('b5-clear-removes-key', 'clear one (window, model)', 'B5', CL('seven_day', 'opus'), ok({'limits': [stored(E2, at=OLD)]}),
   fs={SP: state(stored(E1, at=OLD), stored(E2, at=OLD))},
   expectFs={SP: {'contentJson': {'version': 1, 'limits': [stored(E2, at=OLD)]}, 'mode': '0600'}})
mk('b5-clear-null-model-key', 'model null clears the all-models entry only', 'B5', CL('five_hour', None),
   ok({'limits': [stored(dict(E2, model='opus'), at=OLD)]}), fs={SP: state(stored(E2, at=OLD), stored(dict(E2, model='opus'), at=OLD))})
mk('b5-clear-unknown-key', 'clearing a key that is not there changes nothing else', 'B5', CL('seven_day', 'sonnet'),
   ok({'limits': [stored(E1, at=OLD)]}), fs={SP: state(stored(E1, at=OLD))})
mk('b5-clear-drops-past', 'past entries are dropped by the same merge', 'B5', CL('seven_day', 'opus'),
   ok({'limits': []}), fs={SP: state(stored(E1, at=OLD), stored(dict(E2, until='2026-10-01T00:00:00Z'), at=OLD))})
mk('b5-clear-no-file-no-write', 'no state file: result empty and nothing is created', 'B5', CL('seven_day', 'opus'),
   ok({'limits': []}), fs=acct(wl, 'work'), expectFs={SP: None, SP + '.lock': None})
mk('b5-clear-account-not-found', 'unknown account', 'B5', op('clear_limited', name='nope', window='x', model=None), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))

AV = lambda **k: op('available', name='work', **k)
def av(id, desc, limits, expect, model=None, **kw):
    a = AV(model=model) if model else AV()
    mk(id, desc, 'B5', a, ok({'available': expect}), fs={SP: state(*limits)} if limits is not None else acct(wl, 'work'), **kw)
FUT = '2026-10-09T14:00:00Z'
av('b5-available-no-file', 'no state file means available', None, True)
av('b5-available-empty-list', 'empty list', [], True)
av('b5-available-limited-model', 'limited for the asked model', [stored(E1)], False, model='opus')
av('b5-available-other-model', 'limited for opus only, sonnet asked', [stored(E1)], True, model='sonnet')
av('b5-available-all-models-entry', 'a null-model entry applies to every model', [stored(E2)], False, model='sonnet')
av('b5-available-no-model-given-all-models-entry', 'no model asked, null-model entry still applies', [stored(E2)], False)
av('b5-available-no-model-given-ignores-model-entries', 'no model asked: model-specific entries do not apply', [stored(E1)], True)
av('b5-available-expired', 'until in the past', [stored(dict(E1, until='2026-10-06T11:59:59Z'))], True, model='opus')
av('b5-available-until-equals-now', 'until == now is not > now', [stored(dict(E1, until=NOW))], True, model='opus')
av('b5-available-one-of-many', 'any applying future entry blocks', [stored(dict(E1, until=OLD)), stored(E2)], False, model='opus')
av('b5-available-unparseable-file', 'unparseable state counts as no state', None, True)
mk('b5-available-unparseable-state-file', 'garbage in the state file counts as no state', 'B5', AV(), ok({'available': True}), fs={SP: F('{{')})
mk('b5-available-account-not-found', 'unknown account', 'B5', op('available', name='nope'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))
mk('b5-available-default', 'default reads ~/.claude state', 'B5', op('available', name='default', model='opus'), ok({'available': False}),
   fs={'/home/p/.claude/.multi-account-state.json': state(stored(E1))})

# ================= B6 pools
def poolspec(name, pool=None, prio=None, **kw):
    d = {'version': 1}
    if pool is not None:
        d['pool'] = pool
    if prio is not None:
        d['priority'] = prio
    d.update(kw)
    return {'/home/p/.claude-%s/.multi-account.json' % name: F(jd(d))}
def lim(name, until=FUT, model=None, window='five_hour'):
    return {'/home/p/.claude-%s/.multi-account-state.json' % name: state(
        {'window': window, 'model': model, 'until': until, 'reason': 'rate_limit', 'updatedBy': 'x', 'updatedAt': OLD})}
TEAM = {**poolspec('a', 'team', 1), **poolspec('b', 'team', 5), **poolspec('c', 'team', 5), **poolspec('d', 'other', 9)}
def pk(id, desc, fs, expect, name='pick', **args):
    mk(id, desc, 'B6', op(name, **args), ok({'account': expect}), fs=fs)
pk('b6-pick-highest-priority', 'highest priority wins, ties by name', TEAM, 'b', pool='team')
pk('b6-pick-other-pool', 'a different pool', TEAM, 'd', pool='other')
pk('b6-pick-skips-limited', 'a limited member is skipped', {**TEAM, **lim('b')}, 'c', pool='team')
pk('b6-pick-skips-two', 'two limited members', {**TEAM, **lim('b'), **lim('c')}, 'a', pool='team')
pk('b6-pick-all-limited', 'no member available: null', {**TEAM, **lim('a'), **lim('b'), **lim('c')}, None, pool='team')
pk('b6-pick-expired-limit-ignored', 'an expired limit does not count', {**TEAM, **lim('b', until=OLD)}, 'b', pool='team')
pk('b6-pick-model-aware', 'limited for opus only: still picked for sonnet', {**TEAM, **lim('b', model='opus')}, 'b', pool='team', model='sonnet')
pk('b6-pick-model-aware-opus', 'limited for opus: skipped when opus is asked', {**TEAM, **lim('b', model='opus')}, 'c', pool='team', model='opus')
pk('b6-pick-default-priority-zero', 'missing priority is 0, ties by name', {**poolspec('z', 'p'), **poolspec('m', 'p')}, 'm', pool='p')
pk('b6-pick-negative-priority', 'negative priority sorts after 0', {**poolspec('a', 'p', -1), **poolspec('b', 'p')}, 'b', pool='p')
pk('b6-pick-no-members', 'unknown pool', TEAM, None, pool='nobody')
pk('b6-pick-default-account-member', 'default may be a pool member and sorts by name', {**poolspec('x', 'p'), '/home/p/.claude/.multi-account.json': F(jd({'version': 1, 'pool': 'p'}))}, 'default', pool='p')
pk('b6-pick-priority-beats-name', 'a higher priority beats an earlier name', {**poolspec('a', 'p', 0), **poolspec('z', 'p', 3)}, 'z', pool='p')
pk('b6-pick-dangling-member-skipped', 'a dangling account is not a member', {**poolspec('a', 'p'), '/home/p/.claude-b': L('/mnt/gone')}, 'a', pool='p')
pk('b6-pick-alias-counts-once', 'aliases are one member', {'/home/p/.claude-a/.multi-account.json': F(jd({'version': 1, 'pool': 'p'})), '/home/p/.claude-b': L('/home/p/.claude-a')}, 'a', pool='p')
mk('b6-pick-invalid-pool-name', 'pool name uses the account grammar', 'B6', op('pick', pool='Team'), err('INVALID_NAME', None))
mk('b6-pick-invalid-spec-file-anywhere', 'an invalid spec file fails pool selection even for other pools', 'B6', op('pick', pool='team'),
   err('SPEC_FILE_INVALID', '/home/p/.claude-bad/.multi-account.json'), fs={**TEAM, '/home/p/.claude-bad/.multi-account.json': F('{')})
pk('b6-next-after-current', 'next member after current in pick order', TEAM, 'c', name='next', pool='team', current='b')
pk('b6-next-continues', 'from c goes to a', TEAM, 'a', name='next', pool='team', current='c')
pk('b6-next-wraps', 'wraps from the last to the first', TEAM, 'b', name='next', pool='team', current='a')
pk('b6-next-skips-limited', 'skips limited members', {**TEAM, **lim('c')}, 'a', name='next', pool='team', current='b')
pk('b6-next-only-current-available', 'when only current is available, current is returned', {**TEAM, **lim('a'), **lim('c')}, 'b', name='next', pool='team', current='b')
pk('b6-next-none-available', 'null when nothing is available', {**TEAM, **lim('a'), **lim('b'), **lim('c')}, None, name='next', pool='team', current='b')
pk('b6-next-current-limited', 'current itself may be limited', {**TEAM, **lim('b')}, 'c', name='next', pool='team', current='b')
pk('b6-next-current-not-member', 'a current outside the pool starts from the top', TEAM, 'b', name='next', pool='team', current='d')
pk('b6-next-model-aware', 'model-aware', {**TEAM, **lim('c', model='opus')}, 'a', name='next', pool='team', current='b', model='opus')
pk('b6-next-alias-excluded', 'alias of a member is not a member', {'/home/p/.claude-a/.multi-account.json': F(jd({'version': 1, 'pool': 'p'})), '/home/p/.claude-b': L('/home/p/.claude-a'), **poolspec('c', 'p', -1)}, 'c', name='next', pool='p', current='a')
mk('b6-next-invalid-pool', 'invalid pool name', 'B6', op('next', pool='A b', current='x'), err('INVALID_NAME', None))
mk('b6-pick-win32', 'win32 pool', 'B6', op('pick', pool='p'), ok({'account': 'b'}), plat='win32',
   fs={'C:\\Users\\p\\.claude-a\\.multi-account.json': F(jd({'version': 1, 'pool': 'p'})),
       'C:\\Users\\p\\.claude-b\\.multi-account.json': F(jd({'version': 1, 'pool': 'p', 'priority': 2}))})

# ================= B7 slot
def managed(w, name='work', extra=None, rel=False):
    h = w.h
    a = w('.claude-' + name)
    fsd = {w('.claude'): (J if w.win else L)(('.claude-' + name) if rel else a) if not (w.win and rel) else J(a),
           w('.claude.json'): L(('.claude-' + name + w.sep + '.claude.json') if rel else a + w.sep + '.claude.json'),
           a: D(), a + w.sep + '.claude.json': F('{}')}
    fsd.update(extra or {})
    return fsd
def unmanaged(w, extra=None):
    d = {w('.claude'): D(), w('.claude', '.credentials.json'): F('cred'), w('.claude.json'): F('{"a":1}')}
    d.update(extra or {})
    return d
def sl(id, desc, state_, name=None, fs=None, plat='linux', **kw):
    mk(id, desc, 'B7', op('slot'), ok({'state': state_, 'name': name}), plat=plat, fs=fs, **kw)

sl('b7-slot-unmanaged', '~/.claude is a real directory', 'unmanaged', fs=unmanaged(wl))
sl('b7-slot-unmanaged-no-global-json', 'real directory, no ~/.claude.json', 'unmanaged', fs={'/home/p/.claude': D()})
sl('b7-slot-managed', 'both links point at the same account', 'managed', 'work', fs=managed(wl))
sl('b7-slot-managed-relative-links', 'relative link targets resolve against the home dir', 'managed', 'work', fs=managed(wl, rel=True))
sl('b7-slot-managed-credentials-regular-file', 'a regular .credentials.json is fine', 'managed', 'work',
   fs=managed(wl, extra={'/home/p/.claude-work/.credentials.json': F('c')}))
sl('b7-slot-managed-reserved-name', 'a reserved name can be in the slot', 'managed', 'profiles', fs=managed(wl, 'profiles'))
sl('b7-slot-managed-win32', 'win32 junction plus file symlink', 'managed', 'work', plat='win32', fs=managed(ww))
sl('b7-slot-unmanaged-missing-claude', 'no ~/.claude at all is unmanaged', 'unmanaged', fs={})
sl('b7-slot-broken-claude-is-file', '~/.claude is a regular file', 'broken', fs={'/home/p/.claude': F('x')})
sl('b7-slot-broken-link-without-json-link', '~/.claude linked but ~/.claude.json is a plain file', 'broken',
   fs=managed(wl, extra={'/home/p/.claude.json': F('{}')}))
sl('b7-slot-broken-json-link-missing', '~/.claude linked, no ~/.claude.json', 'broken',
   fs={k: v for k, v in managed(wl).items() if k != '/home/p/.claude.json'})
sl('b7-slot-broken-different-accounts', 'links point at different accounts', 'broken',
   fs=managed(wl, extra={'/home/p/.claude.json': L('/home/p/.claude-personal/.claude.json'), '/home/p/.claude-personal/.claude.json': F('{}')}))
sl('b7-slot-broken-dangling-dir-link', '~/.claude points at a missing account', 'broken',
   fs={'/home/p/.claude': L('/home/p/.claude-gone'), '/home/p/.claude.json': L('/home/p/.claude-gone/.claude.json')})
sl('b7-slot-managed-dangling-json-link', 'a dangling ~/.claude.json link with the right target is managed (Claude Code creates it through the link)', 'managed', 'work',
   fs={k: v for k, v in managed(wl).items() if k != '/home/p/.claude-work/.claude.json'})
sl('b7-slot-managed-relocated-account', 'a relocated account (its dir is a link) can be in the slot', 'managed', 'work',
   fs={'/home/p/.claude': L('/home/p/.claude-work'), '/home/p/.claude.json': L('/home/p/.claude-work/.claude.json'),
       '/home/p/.claude-work': L('/data/w'), '/data/w/.claude.json': F('{}')})
sl('b7-slot-broken-chain-json', '.claude.json links to a link', 'broken',
   fs=managed(wl, extra={'/home/p/.claude-work/.claude.json': L('/data/real.json'), '/data/real.json': F('{}')}))
sl('b7-slot-broken-credentials-link', '.credentials.json in the target is a link', 'broken',
   fs=managed(wl, extra={'/home/p/.claude-work/.credentials.json': L('/data/c.json'), '/data/c.json': F('{}')}))
sl('b7-slot-broken-link-outside-home-naming', '~/.claude links to a dir that is not ~/.claude-<name>', 'broken',
   fs={'/home/p/.claude': L('/data/x'), '/data/x': D(), '/home/p/.claude.json': L('/data/x/.claude.json'), '/data/x/.claude.json': F('{}')})
sl('b7-slot-broken-invalid-account-name', 'the target name must be grammar valid', 'broken', fs=managed(wl, 'Work'))
sl('b7-slot-broken-json-link-wrong-target', '.claude.json links somewhere else', 'broken',
   fs=managed(wl, extra={'/home/p/.claude.json': L('/data/other.json'), '/data/other.json': F('{}')}))
sl('b7-slot-unsupported-darwin-unmanaged', 'darwin is unsupported', 'unsupported', plat='darwin', fs=unmanaged(wd))
sl('b7-slot-unsupported-darwin-managed-layout', 'unsupported beats managed', 'unsupported', plat='darwin', fs=managed(wd))
sl('b7-slot-unsupported-darwin-nothing', 'unsupported beats broken', 'unsupported', plat='darwin', fs={})
sl('b7-slot-unsupported-win32-credman-env', 'win32 with FORCE_WINDOWS_CREDMAN=1', 'unsupported', plat='win32', fs=unmanaged(ww),
   env={'CLAUDE_CODE_FORCE_WINDOWS_CREDMAN': '1'})
sl('b7-slot-unsupported-win32-credman-flag', 'win32 with the GrowthBook flag cached in ~/.claude.json', 'unsupported', plat='win32',
   fs={**unmanaged(ww), 'C:\\Users\\p\\.claude.json': F(jd({'cachedGrowthBookFeatures': {'tengu_windows_credman': True}}))})
sl('b7-slot-unsupported-win32-no-symlink-permission', 'win32 without permission to create file symlinks', 'unsupported', plat='win32',
   fs=unmanaged(ww), opts={'canCreateSymlinks': False})
sl('b7-slot-win32-unmanaged-supported', 'win32 without credman and with symlink permission is supported', 'unmanaged', plat='win32', fs=unmanaged(ww),
   opts={'canCreateSymlinks': True})
sl('b7-slot-linux-ignores-credman-env', 'the Windows variable means nothing on linux', 'unmanaged', fs=unmanaged(wl),
   env={'CLAUDE_CODE_FORCE_WINDOWS_CREDMAN': '1'}, opts={'canCreateSymlinks': False})

# adopt
AD = lambda n='work': op('adopt', name=n)
mk('b7-adopt-linux', 'adopt moves ~/.claude and ~/.claude.json into the account and links back', 'B7', AD(),
   ok({'state': 'managed', 'name': 'work'}), fs=unmanaged(wl),
   expectFs={'/home/p/.claude-work': {'type': 'dir'}, '/home/p/.claude-work/.credentials.json': {'type': 'file', 'content': 'cred'},
             '/home/p/.claude-work/.claude.json': {'type': 'file', 'content': '{"a":1}'},
             '/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'},
             '/home/p/.claude.json': {'type': 'symlink', 'target': '/home/p/.claude-work/.claude.json'}})
mk('b7-adopt-win32', 'win32 adopt creates a junction for the directory and a file symlink', 'B7', AD(),
   ok({'state': 'managed', 'name': 'work'}), plat='win32', fs=unmanaged(ww),
   expectFs={'C:\\Users\\p\\.claude': {'type': 'junction', 'target': 'C:\\Users\\p\\.claude-work'},
             'C:\\Users\\p\\.claude.json': {'type': 'symlink', 'target': 'C:\\Users\\p\\.claude-work\\.claude.json'},
             'C:\\Users\\p\\.claude-work\\.credentials.json': {'type': 'file', 'content': 'cred'},
             'C:\\Users\\p\\.claude-work\\.claude.json': {'type': 'file', 'content': '{"a":1}'}})
mk('b7-adopt-unsupported-darwin', 'adopt refuses on darwin and changes nothing', 'B7', AD(), err('SLOT_UNSUPPORTED', None), plat='darwin',
   fs=unmanaged(wd), expectFs={'/Users/p/.claude': {'type': 'dir'}, '/Users/p/.claude-work': None, '/Users/p/.claude.json': {'type': 'file'}})
mk('b7-adopt-unsupported-beats-invalid-name', 'unsupported is checked first', 'B7', AD('Bad Name'), err('SLOT_UNSUPPORTED', None), plat='darwin', fs=unmanaged(wd))
mk('b7-adopt-win32-no-symlink-permission', 'win32 without symlink permission', 'B7', AD(), err('SLOT_UNSUPPORTED', None), plat='win32',
   fs=unmanaged(ww), opts={'canCreateSymlinks': False})
mk('b7-adopt-invalid-name', 'invalid name', 'B7', AD('Work'), err('INVALID_NAME', None), fs=unmanaged(wl))
for n in ('account', 'profiles', 'swap-backup'):
    mk('b7-adopt-reserved-' + n, 'reserved name %s' % n, 'B7', AD(n), err('RESERVED_NAME', None), fs=unmanaged(wl),
       expectFs={'/home/p/.claude': {'type': 'dir'}})
mk('b7-adopt-already-managed', 'adopt needs an unmanaged slot', 'B7', AD('personal'), err('SLOT_STATE', None), fs=managed(wl))
mk('b7-adopt-broken-slot', 'adopt refuses a broken slot', 'B7', AD(), err('SLOT_STATE', None), fs={'/home/p/.claude': F('x')})
mk('b7-adopt-account-exists', 'the target name must not exist', 'B7', AD(), err('ACCOUNT_EXISTS', '/home/p/.claude-work'),
   fs=unmanaged(wl, extra={'/home/p/.claude-work': D()}), expectFs={'/home/p/.claude': {'type': 'dir'}})
mk('b7-adopt-account-exists-dangling', 'a dangling link in the way counts as existing', 'B7', AD(), err('ACCOUNT_EXISTS', '/home/p/.claude-work'),
   fs=unmanaged(wl, extra={'/home/p/.claude-work': L('/mnt/gone')}))
mk('b7-adopt-state-checked-before-exists', 'SLOT_STATE precedes ACCOUNT_EXISTS', 'B7', AD('work'), err('SLOT_STATE', None), fs=managed(wl))

# activate
AC = lambda n: op('activate', name=n)
M2 = managed(wl, extra={'/home/p/.claude-personal/.claude.json': F('{"p":1}'), '/home/p/.claude-personal/.credentials.json': F('pc'),
                         '/home/p/.claude-work/.credentials.json': F('wc')})
mk('b7-activate-linux', 'activate re-points both links, credentials untouched', 'B7', AC('personal'),
   ok({'state': 'managed', 'name': 'personal'}), fs=M2,
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-personal'},
             '/home/p/.claude.json': {'type': 'symlink', 'target': '/home/p/.claude-personal/.claude.json'},
             '/home/p/.claude-work/.credentials.json': {'type': 'file', 'content': 'wc'},
             '/home/p/.claude-personal/.credentials.json': {'type': 'file', 'content': 'pc'},
             '/home/p/.claude-slot.lock': None})
mk('b7-activate-win32', 'win32 activate re-creates the junction', 'B7', AC('personal'), ok({'state': 'managed', 'name': 'personal'}), plat='win32',
   fs=managed(ww, extra={'C:\\Users\\p\\.claude-personal\\.claude.json': F('{}')}),
   expectFs={'C:\\Users\\p\\.claude': {'type': 'junction', 'target': 'C:\\Users\\p\\.claude-personal'},
             'C:\\Users\\p\\.claude.json': {'type': 'symlink', 'target': 'C:\\Users\\p\\.claude-personal\\.claude.json'}})
mk('b7-activate-same-account', 'activating the current account is a normal success', 'B7', AC('work'), ok({'state': 'managed', 'name': 'work'}), fs=M2,
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})
mk('b7-activate-relative-links-become-absolute', 'new links use absolute targets', 'B7', AC('personal'), ok({'state': 'managed', 'name': 'personal'}),
   fs=managed(wl, rel=True, extra={'/home/p/.claude-personal/.claude.json': F('{}')}),
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-personal'}})
SESS = {'/home/p/.claude-work/sessions/300.json': sess(300, sid='live-one')}
mk('b7-activate-live-session-refused', 'a live session in the current slot account blocks activation', 'B7', AC('personal'),
   err('SESSION_LIVE', None), fs={**M2, **SESS}, processes={'300': {'procStart': 'T1', 'pidDomain': 'host-1'}},
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'},
             '/home/p/.claude.json': {'type': 'symlink', 'target': '/home/p/.claude-work/.claude.json'}, '/home/p/.claude-slot.lock': None})
mk('b7-activate-dead-session-ok', 'a dead session does not block', 'B7', AC('personal'), ok({'state': 'managed', 'name': 'personal'}),
   fs={**M2, **SESS}, processes={'300': {'procStart': 'OTHER', 'pidDomain': 'host-1'}})
mk('b7-activate-unknown-session-refused', 'a session from another pid domain blocks like a live one', 'B7', AC('personal'),
   err('SESSION_LIVE', None),
   fs={**M2, '/home/p/.claude-work/sessions/300.json': sess(300, dom='other-host')}, processes={'300': {'procStart': 'T1', 'pidDomain': 'host-1'}},
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}, '/home/p/.claude-slot.lock': None})
mk('b7-activate-unknown-session-force-ok', 'force lets an unknown session through', 'B7', op('activate', name='personal', force=True),
   ok({'state': 'managed', 'name': 'personal'}),
   fs={**M2, '/home/p/.claude-work/sessions/300.json': sess(300, dom='other-host')}, processes={'300': {'procStart': 'T1', 'pidDomain': 'host-1'}})
mk('b7-activate-live-in-target-ok', 'only the current slot account is checked', 'B7', AC('personal'), ok({'state': 'managed', 'name': 'personal'}),
   fs={**M2, '/home/p/.claude-personal/sessions/300.json': sess(300)}, processes={'300': {'procStart': 'T1', 'pidDomain': 'host-1'}})
mk('b7-activate-account-not-found', 'target account missing', 'B7', AC('ghost'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-ghost'), fs=M2,
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})
mk('b7-activate-account-dangling', 'target account dangling', 'B7', AC('ghost'), err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-ghost'),
   fs={**M2, '/home/p/.claude-ghost': L('/mnt/gone')})
mk('b7-activate-invalid-name', 'invalid name', 'B7', AC('Work'), err('INVALID_NAME', None), fs=M2)
mk('b7-activate-unmanaged-slot', 'activate needs a managed slot', 'B7', AC('personal'), err('SLOT_STATE', None),
   fs=unmanaged(wl, extra={'/home/p/.claude-personal/.claude.json': F('{}')}))
mk('b7-activate-broken-slot', 'activate refuses a broken slot', 'B7', AC('personal'), err('SLOT_STATE', None),
   fs={'/home/p/.claude': F('x'), '/home/p/.claude-personal/.claude.json': F('{}')})
mk('b7-activate-unsupported-darwin', 'darwin refuses and rewrites nothing', 'B7', AC('personal'), err('SLOT_UNSUPPORTED', None), plat='darwin',
   fs=managed(wd, extra={'/Users/p/.claude-personal/.claude.json': F('{}')}),
   expectFs={'/Users/p/.claude': {'type': 'symlink', 'target': '/Users/p/.claude-work'}})
mk('b7-activate-unsupported-beats-invalid-name', 'unsupported first', 'B7', AC('Bad'), err('SLOT_UNSUPPORTED', None), plat='darwin', fs=managed(wd))
mk('b7-activate-unsupported-win32-credman', 'win32 with Credential Manager refuses', 'B7', AC('personal'), err('SLOT_UNSUPPORTED', None), plat='win32',
   env={'CLAUDE_CODE_FORCE_WINDOWS_CREDMAN': '1'}, fs=managed(ww, extra={'C:\\Users\\p\\.claude-personal\\.claude.json': F('{}')}))
mk('b7-activate-stale-slot-lock', 'a stale slot lock is taken over', 'B7', AC('personal'), ok({'state': 'managed', 'name': 'personal'}),
   fs={**M2, '/home/p/.claude-slot.lock': D(mtime='2026-10-06T11:00:00Z')}, expectFs={'/home/p/.claude-slot.lock': None})
mk('b7-activate-slot-lock-busy', 'a fresh slot lock means someone else is switching', 'B7', AC('personal'), err('LOCK_BUSY', '/home/p/.claude-slot.lock'),
   fs={**M2, '/home/p/.claude-slot.lock': D()}, expectFs={'/home/p/.claude-slot.lock': {'type': 'dir'},
                                                          '/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})

# resolve aliasing with a managed slot
mk('b7-resolve-default-is-alias-of-slot', 'while managed, default reports the slot account as aliasOf', ['B7', 'A4 Result'], op('resolve'),
   ok(rr(wl, 'default', 'default', aliasOf='work')), fs=managed(wl))
mk('b7-resolve-slot-account-represents-group', 'the named account represents the group and has no aliasOf; it counts as applied because default is the same directory', ['B7', 'A2 Relocation'], op('resolve'),
   ok(rr(wl, 'work', 'env', applied=True)), env={MA: 'work'}, fs=managed(wl))
mk('b7-resolve-config-dir-slot-account', 'CLAUDE_CONFIG_DIR of the slot account is canonical and represents the group', ['B7', 'A4 Step 1'], op('resolve'),
   ok(rr(wl, 'work', 'config-dir')), env={CC: '/home/p/.claude-work'}, fs=managed(wl))
mk('b7-resolve-no-slot-no-alias', 'an unmanaged slot has no alias', ['B7', 'A4 Result'], op('resolve'),
   ok(rr(wl, 'default', 'default')), fs={**unmanaged(wl), **acct(wl, 'work')})
mk('b7-discover-managed-slot', 'discover while managed', ['B7', 'A2 Relocation'], op('discover'),
   ok({'accounts': [dict(name='default', configDir='/home/p/.claude', state='ok', hasSpecFile=False, hasGlobalConfig=True, aliasOf='work', specError=None, warnings=[]),
                    dict(name='work', configDir='/home/p/.claude-work', state='ok', hasSpecFile=False, hasGlobalConfig=True, aliasOf=None, specError=None, warnings=[])],
       'conflicts': [], 'warnings': []}), fs=managed(wl))
