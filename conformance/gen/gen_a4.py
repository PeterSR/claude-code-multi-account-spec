from gen_lib import *
from gen_a import wl, wd, ww, W_

M = '.claude-account'
CC = 'CLAUDE_CONFIG_DIR'
MA = 'CLAUDE_MULTI_ACCOUNT'
SRC = 'CLAUDE_MULTI_ACCOUNT_SOURCE'
NCD = 'NON_CANONICAL_CONFIG_DIR'


def mp(d, w=wl):
    return d + w.sep + M


def res(id, desc, spec_, expect, **kw):
    return mk(id, desc, spec_, op('resolve'), expect, **kw)


WORK = acct(wl, 'work')
WP = acct(wl, 'work', 'personal')

# ================= Step 0
res('a4-env-empty-multi-account', 'empty CLAUDE_MULTI_ACCOUNT is unset with EMPTY_ENV', 'A4 Step 0',
    ok(rr(wl, 'default', 'default', warnings=['EMPTY_ENV'])), env={MA: ''})
res('a4-env-empty-config-dir', 'empty CLAUDE_CONFIG_DIR is unset with EMPTY_ENV', 'A4 Step 0',
    ok(rr(wl, 'default', 'default', warnings=['EMPTY_ENV'])), env={CC: ''})
res('a4-env-empty-both', 'two empty vars give two warnings', 'A4 Step 0',
    ok(rr(wl, 'default', 'default', warnings=['EMPTY_ENV', 'EMPTY_ENV'])), env={CC: '', MA: ''})
res('a4-env-empty-config-dir-with-multi', 'empty config dir does not conflict with a real selection', 'A4 Step 0',
    ok(rr(wl, 'work', 'env', warnings=['EMPTY_ENV'])), env={CC: '', MA: 'work'}, fs=WORK)
res('a4-env-empty-multi-falls-to-marker', 'empty selection var lets the directory binding apply', 'A4 Step 0',
    ok(rr(wl, 'work', 'marker-file', '/home/p/proj/.claude-account', warnings=['EMPTY_ENV'])),
    env={MA: ''}, cwd='/home/p/proj', fs={'/home/p/proj/.claude-account': F('work\n'), **WORK})
res('a4-env-empty-api-key-not-override', 'empty override vars are unset, without a warning', ['A4 Step 0', 'A4 Result'],
    ok(rr(wl, 'default', 'default')), env={'ANTHROPIC_API_KEY': '', 'CLAUDE_CODE_OAUTH_TOKEN': ''})
res('a4-ignore-hook-env-marker-wins', 'ignoreHookEnv with SOURCE=hook drops the earlier export so the marker applies', 'A4 Step 0',
    ok(rr(wl, 'personal', 'marker-file', '/home/p/proj/.claude-account')),
    env={MA: 'work', SRC: 'hook'}, opts={'ignoreHookEnv': True}, cwd='/home/p/proj',
    fs={'/home/p/proj/.claude-account': F('personal\n'), **WP})
res('a4-ignore-hook-env-off', 'without ignoreHookEnv the hook export is obeyed', 'A4 Step 0',
    ok(rr(wl, 'work', 'env')), env={MA: 'work', SRC: 'hook'}, cwd='/home/p/proj',
    fs={'/home/p/proj/.claude-account': F('personal\n'), **WP})
res('a4-ignore-hook-env-other-source', 'ignoreHookEnv only applies when SOURCE is exactly hook', 'A4 Step 0',
    ok(rr(wl, 'work', 'env')), env={MA: 'work', SRC: 'user'}, opts={'ignoreHookEnv': True}, fs=WORK)
res('a4-ignore-hook-env-drops-config-dir', 'ignoreHookEnv also drops CLAUDE_CONFIG_DIR', 'A4 Step 0',
    ok(rr(wl, 'default', 'default')), env={MA: 'work', CC: '/home/p/.claude-work', SRC: 'hook'},
    opts={'ignoreHookEnv': True}, fs=WORK)
res('a4-ignore-hook-env-foreign-dropped', 'a foreign config dir exported by a hook is dropped without warning', 'A4 Step 0',
    ok(rr(wl, 'default', 'default')), env={CC: '/opt/x', SRC: 'hook'}, opts={'ignoreHookEnv': True})

# ================= Step 1 env
res('a4-env-multi-account', 'CLAUDE_MULTI_ACCOUNT alone names the account', 'A4 Step 1.3',
    ok(rr(wl, 'work', 'env')), env={MA: 'work'}, fs=WORK)
res('a4-env-multi-account-default', 'CLAUDE_MULTI_ACCOUNT=default', 'A4 Step 1.3',
    ok(rr(wl, 'default', 'env')), env={MA: 'default'})
res('a4-env-multi-account-link-not-resolved', 'a linked account dir keeps its link path as configDir', ['A2 Relocation', 'A4 Result'],
    ok(rr(wl, 'work', 'env')), env={MA: 'work'}, fs={'/home/p/.claude-work': L('/data/w'), '/data/w': D()})
res('a4-env-multi-account-reserved-existing', 'reserved but existing account resolves with RESERVED_NAME', ['A2 Names', 'A4 Step 1.3'],
    ok(rr(wl, 'profiles', 'env', warnings=['RESERVED_NAME'])), env={MA: 'profiles'}, fs=acct(wl, 'profiles'))
res('a4-env-multi-account-invalid', 'uppercase name is INVALID_NAME', 'A4 Step 1.3',
    err('INVALID_NAME', None), env={MA: 'Work'}, fs=WORK)
res('a4-env-multi-account-not-found', 'undiscovered account', 'A4 Step 1.3',
    err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), env={MA: 'work'})
res('a4-env-multi-account-dangling', 'dangling account is ACCOUNT_UNAVAILABLE', 'A4 Step 1.3',
    err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-work'), env={MA: 'work'}, fs={'/home/p/.claude-work': L('/mnt/gone')})
res('a4-env-multi-account-unreadable', 'unreadable account is ACCOUNT_UNAVAILABLE', 'A4 Step 1.3',
    err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-work'), env={MA: 'work'},
    fs={'/home/p/.claude-work': L('/mnt/locked/w', unreadable=True)})
res('a4-env-multi-account-is-file', 'a regular file is not an account', ['A2 Discovery', 'A4 Step 1.3'],
    err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), env={MA: 'work'}, fs={'/home/p/.claude-work': F('x')})
res('a4-env-multi-account-case-variant-ci', 'case-insensitive fs: .claude-Work is not found as work', ['A2 Discovery', 'A4 Step 1.3'],
    err('ACCOUNT_NOT_FOUND', '/Users/p/.claude-work'), plat='darwin', env={MA: 'work'}, fs={'/Users/p/.claude-Work': D()})
res('a4-env-config-dir-canonical', 'canonical CLAUDE_CONFIG_DIR is config-dir source, canonical', 'A4 Step 1.1',
    ok(rr(wl, 'work', 'config-dir')), env={CC: '/home/p/.claude-work'}, fs=WORK)
res('a4-env-config-dir-and-multi-agree', 'both set and agreeing', 'A4 Step 1.2',
    ok(rr(wl, 'work', 'config-dir')), env={CC: '/home/p/.claude-work', MA: 'work'}, fs=WORK)
res('a4-env-config-dir-multi-default-agree', 'MULTI=default agrees with CONFIG_DIR=$HOME/.claude', 'A4 Step 1.2',
    ok(rr(wl, 'default', 'config-dir', configDir='/home/p/.claude', canonical=False, reason='default-via-config-dir', warnings=[NCD])),
    env={CC: '/home/p/.claude', MA: 'default'}, fs={'/home/p/.claude': D()})
res('a4-env-conflict-different-account', 'two named accounts disagree', 'A4 Step 1.2',
    err('ENV_CONFLICT', None), env={CC: '/home/p/.claude-work', MA: 'personal'}, fs=WP)
res('a4-env-conflict-foreign-dir', 'a foreign config dir never equals a named account', 'A4 Step 1.2',
    err('ENV_CONFLICT', None), env={CC: '/opt/x', MA: 'work'}, fs=WORK)
res('a4-env-conflict-default-vs-named', 'CONFIG_DIR=$HOME/.claude means default, MULTI=work disagrees', 'A4 Step 1.2',
    err('ENV_CONFLICT', None), env={CC: '/home/p/.claude', MA: 'work'}, fs={'/home/p/.claude': D(), **WORK})
res('a4-env-both-set-undiscovered-named-is-not-found', 'both vars agree on a missing account: report the missing account, not a conflict', 'A4 Step 1.2',
    err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), env={CC: '/home/p/.claude-work', MA: 'work'})
res('a4-env-conflict-after-normalisation', 'conflict is about accounts, not strings', 'A4 Step 1.2',
    err('ENV_CONFLICT', None), env={CC: '/home/p/.claude-work/', MA: 'personal'}, fs=WP)
res('a4-env-invalid-multi-beats-config-dir', 'an invalid CLAUDE_MULTI_ACCOUNT is INVALID_NAME even with a CONFIG_DIR', 'A4 Step 1.3',
    err('INVALID_NAME', None), env={CC: '/home/p/.claude-work', MA: 'Bad Name'}, fs=WORK)

# config-dir full results
res('a4-config-dir-not-normalized', 'trailing separator: same account, non canonical, warning', 'A4 Step 1 mapping',
    ok(rr(wl, 'work', 'config-dir', configDir='/home/p/.claude-work/', canonical=False, reason='not-normalized', warnings=[NCD])),
    env={CC: '/home/p/.claude-work/'}, fs=WORK)
res('a4-config-dir-default-via-config-dir', 'CONFIG_DIR=$HOME/.claude is default but flagged', ['A2 Canonical path', 'A4 Step 1 mapping'],
    ok(rr(wl, 'default', 'config-dir', configDir='/home/p/.claude', canonical=False, reason='default-via-config-dir', warnings=[NCD])),
    env={CC: '/home/p/.claude'}, fs={'/home/p/.claude': D()})
res('a4-config-dir-resolved-target', 'a link elsewhere to an account dir', 'A4 Step 1 mapping',
    ok(rr(wl, 'work', 'config-dir', configDir='/data/wlink', canonical=False, reason='resolved-target', warnings=[NCD])),
    env={CC: '/data/wlink'}, fs={'/data/wlink': L('/home/p/.claude-work'), **WORK})
res('a4-config-dir-foreign-existing', 'foreign dir is reported not rejected', 'A4 Step 1 mapping',
    ok(rr(wl, None, 'config-dir', configDir='/opt/other', canonical=False, reason='foreign', exists=True, launchEnv=None, warnings=[NCD])),
    env={CC: '/opt/other'}, fs={'/opt/other': D()})
res('a4-config-dir-foreign-missing', 'foreign dir that does not exist yet: exists false', ['A4 Step 1 mapping', 'A4 Result'],
    ok(rr(wl, None, 'config-dir', configDir='/opt/new', canonical=False, reason='foreign', exists=False, launchEnv=None, warnings=[NCD])),
    env={CC: '/opt/new'})
res('a4-config-dir-foreign-is-file', 'a file is not a directory: exists false', 'A4 Result',
    ok(rr(wl, None, 'config-dir', configDir='/opt/f', canonical=False, reason='foreign', exists=False, launchEnv=None, warnings=[NCD])),
    env={CC: '/opt/f'}, fs={'/opt/f': F('x')})
res('a4-config-dir-relative-is-foreign', 'a relative value never matches an account', 'A4 Step 1 mapping',
    ok(rr(wl, None, 'config-dir', configDir='rel/dir', canonical=False, reason='foreign', exists=False, launchEnv=None, warnings=[NCD])),
    env={CC: 'rel/dir'}, cwd='/home/p')
res('a4-config-dir-tilde-is-foreign', 'no ~ expansion: a literal ~ is a relative path', 'A1',
    ok(rr(wl, None, 'config-dir', configDir='~/.claude-work', canonical=False, reason='foreign', exists=False, launchEnv=None, warnings=[NCD])),
    env={CC: '~/.claude-work'}, fs=WORK)
res('a4-config-dir-source-keeps-value-verbatim', 'configDir for config-dir source is the value as given', 'A4 Result',
    ok(rr(wl, 'work', 'config-dir', configDir='/home/p//.claude-work', canonical=False, reason='not-normalized', warnings=[NCD])),
    env={CC: '/home/p//.claude-work'}, fs=WORK)
res('a4-config-dir-case-mismatch-darwin', 'darwin case-insensitive fs: case-mismatch', 'A4 Step 1 mapping',
    ok(rr(wd, 'work', 'config-dir', configDir='/Users/p/.Claude-Work', canonical=False, reason='case-mismatch', warnings=[NCD])),
    plat='darwin', env={CC: '/Users/p/.Claude-Work'}, fs=acct(wd, 'work'))
res('a4-config-dir-win32-case-mismatch', 'win32: drive and path case differences', 'A4 Step 1 mapping',
    ok(rr(ww, 'work', 'config-dir', configDir='c:\\users\\p\\.claude-work', canonical=False, reason='case-mismatch', warnings=[NCD])),
    plat='win32', env={CC: 'c:\\users\\p\\.claude-work'}, fs=acct(ww, 'work'))
res('a4-config-dir-win32-canonical', 'win32 canonical value', 'A4 Step 1 mapping',
    ok(rr(ww, 'work', 'config-dir')), plat='win32', env={CC: 'C:\\Users\\p\\.claude-work'}, fs=acct(ww, 'work'))

# map_config_dir table
def mp_case(id, desc, v, acc, canon, reason, plat='linux', fs=None, ci=None, home=None, sec='A4 Step 1 mapping'):
    w = W_[plat]
    mk(id, desc, sec, op('map_config_dir', value=v),
       ok({'account': acc, 'canonical': canon, 'reason': reason, 'warnings': [] if canon else [NCD]}),
       plat=plat, fs=fs if fs is not None else acct(w, 'work'), ci=ci, home=home)

mp_case('a4-map-canonical', 'row 1', '/home/p/.claude-work', 'work', True, None)
mp_case('a4-map-not-normalized-trailing-sep', 'row 2 trailing separator', '/home/p/.claude-work/', 'work', False, 'not-normalized')
mp_case('a4-map-not-normalized-double-sep', 'row 2 duplicate separator', '/home//p/.claude-work', 'work', False, 'not-normalized')
mp_case('a4-map-not-normalized-dot-segments', 'row 2 dot segments', '/home/p/./x/../.claude-work', 'work', False, 'not-normalized')
mp_case('a4-map-not-normalized-link-dotdot-is-lexical', 'row 2: .. is lexical, a link in front does not matter', '/home/p/linkdir/../.claude-work',
        'work', False, 'not-normalized', fs={'/home/p/linkdir': L('/data/deep/er'), '/data/deep/er': D(), **acct(wl, 'work')})
mp_case('a4-map-not-normalized-nfd', 'row 2: NFD spelling of the home dir', '/home/jose\u0301/.claude-work', 'work', False,
        'not-normalized', fs={'/home/jos\u00e9/.claude-work': D()}, home='/home/jos\u00e9')
mp_case('a4-map-case-mismatch-darwin', 'row 3 on a case-insensitive fs', '/Users/p/.CLAUDE-WORK', 'work', False, 'case-mismatch',
        plat='darwin')
mp_case('a4-map-case-mismatch-with-trailing-sep', 'row 3 after normalisation', '/Users/p/.Claude-Work/', 'work', False, 'case-mismatch',
        plat='darwin')
mp_case('a4-map-case-differs-on-case-sensitive-fs', 'no case folding on a case-sensitive fs: foreign', '/home/p/.CLAUDE-WORK', None, False,
        'foreign')
mp_case('a4-map-default-via-config-dir', 'row 4', '/home/p/.claude', 'default', False, 'default-via-config-dir')
mp_case('a4-map-default-via-config-dir-trailing', 'row 4 after normalisation', '/home/p/.claude/', 'default', False,
        'default-via-config-dir', fs={'/home/p/.claude': D()})
mp_case('a4-map-default-via-config-dir-without-dir', 'row 4 needs no existing ~/.claude', '/home/p/x/../.claude', 'default', False,
        'default-via-config-dir', fs={})
mp_case('a4-map-default-case-variant-ci-is-resolved-target', 'darwin: other-case ~/.claude has no row 3 for default, row 5 matches', '/Users/p/.CLAUDE',
        'default', False, 'resolved-target', plat='darwin', fs={'/Users/p/.claude': D()})
mp_case('a4-map-resolved-target-link-to-account', 'row 5: link to an account dir', '/data/wlink', 'work', False, 'resolved-target',
        fs={'/data/wlink': L('/home/p/.claude-work'), **acct(wl, 'work')})
mp_case('a4-map-resolved-target-account-is-link', 'row 5: the account dir is a link, V is the real target', '/data/real', 'work', False,
        'resolved-target', fs={'/home/p/.claude-work': L('/data/real'), '/data/real': D()})
mp_case('a4-map-resolved-target-named-first', 'row 5: named accounts are tried before default', '/data/shared', 'work', False,
        'resolved-target', fs={'/data/shared': D(), '/home/p/.claude': L('/data/shared'), '/home/p/.claude-work': L('/data/shared')})
mp_case('a4-map-row1-beats-row5', 'row 1 wins even when another path reaches the same dir', '/home/p/.claude-work', 'work', True, None,
        fs={'/home/p/.claude-work': L('/data/shared'), '/home/p/.claude': L('/data/shared'), '/data/shared': D()})
mp_case('a4-map-foreign', 'row 6', '/opt/elsewhere', None, False, 'foreign', fs={'/opt/elsewhere': D()})
mp_case('a4-map-foreign-missing', 'row 6, nothing on disk', '/opt/elsewhere', None, False, 'foreign')
mp_case('a4-map-foreign-relative', 'relative value', 'a/b', None, False, 'foreign')
mp_case('a4-map-dangling-account-not-a-candidate', 'a dangling account never matches', '/home/p/.claude-work', None, False, 'foreign',
        fs={'/home/p/.claude-work': L('/mnt/gone')})
mp_case('a4-map-undiscovered-canonical-path', 'canonical path of an account that does not exist is foreign', '/home/p/.claude-work', None, False,
        'foreign', fs={})
mp_case('a4-map-case-variant-dir-is-not-discovered-ci', 'darwin: .claude-Work on disk is not an account, so no row matches by name', '/Users/p/.claude-work',
        None, False, 'foreign', plat='darwin', fs={'/Users/p/.claude-Work': D()})
mp_case('a4-map-win32-canonical', 'win32 row 1', 'C:\\Users\\p\\.claude-work', 'work', True, None, plat='win32')
mp_case('a4-map-win32-forward-slashes', 'win32 row 2: forward slashes', 'C:/Users/p/.claude-work', 'work', False, 'not-normalized', plat='win32')
mp_case('a4-map-win32-trailing-backslash', 'win32 row 2: trailing separator', 'C:\\Users\\p\\.claude-work\\', 'work', False, 'not-normalized', plat='win32')
mp_case('a4-map-win32-dot-segments', 'win32 row 2: dot segments', 'C:\\Users\\p\\x\\..\\.claude-work', 'work', False, 'not-normalized', plat='win32')
mp_case('a4-map-win32-case-mismatch', 'win32 row 3 including the drive letter', 'c:\\users\\P\\.CLAUDE-work', 'work', False, 'case-mismatch', plat='win32')
mp_case('a4-map-win32-default-via-config-dir', 'win32 row 4', 'C:\\Users\\p\\.claude', 'default', False, 'default-via-config-dir', plat='win32')
mp_case('a4-map-win32-junction-resolved-target', 'win32 row 5: junction target', 'D:\\data\\work', 'work', False, 'resolved-target', plat='win32',
        fs={'C:\\Users\\p\\.claude-work': J('D:\\data\\work'), 'D:\\data\\work': D()})
mp_case('a4-map-win32-rooted-without-drive-is-relative', 'win32: \\x is not absolute', '\\Users\\p\\.claude-work', None, False, 'foreign', plat='win32')
mp_case('a4-map-win32-drive-relative-is-relative', 'win32: C:x is not absolute', 'C:Users\\p\\.claude-work', None, False, 'foreign', plat='win32')

# overriddenBy
res('a4-overridden-by-env-vars', 'all four override variables, in fixed order', 'A4 Result',
    ok(rr(wl, 'work', 'env', globalConfig='/home/p/.claude-work/.claude-custom-oauth.json',
          overriddenBy=['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'CLAUDE_SECURESTORAGE_CONFIG_DIR', 'CLAUDE_CODE_CUSTOM_OAUTH_URL'])),
    env={MA: 'work', 'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'https://x.test', 'CLAUDE_SECURESTORAGE_CONFIG_DIR': '/s', 'ANTHROPIC_API_KEY': 'k',
         'CLAUDE_CODE_OAUTH_TOKEN': 't'}, fs=WORK)
res('a4-overridden-by-api-key-helper', 'apiKeyHelper in the account settings.json', 'A4 Result',
    ok(rr(wl, 'work', 'env', overriddenBy=['apiKeyHelper'])), env={MA: 'work'},
    fs={'/home/p/.claude-work/settings.json': F('{"apiKeyHelper": "/bin/key"}')})
res('a4-overridden-by-api-key-helper-empty', 'empty apiKeyHelper does not count', 'A4 Result',
    ok(rr(wl, 'work', 'env')), env={MA: 'work'}, fs={'/home/p/.claude-work/settings.json': F('{"apiKeyHelper": ""}')})
res('a4-overridden-by-settings-unparseable', 'broken settings.json is ignored', 'A4 Result',
    ok(rr(wl, 'work', 'env')), env={MA: 'work'}, fs={'/home/p/.claude-work/settings.json': F('{oops')})
res('a4-overridden-by-default-settings', 'default reads ~/.claude/settings.json', 'A4 Result',
    ok(rr(wl, 'default', 'default', overriddenBy=['apiKeyHelper'])), fs={'/home/p/.claude/settings.json': F('{"apiKeyHelper": "x"}')})
res('a4-overridden-by-foreign-dir-settings', 'foreign dir: settings.json inside the given value', 'A4 Result',
    ok(rr(wl, None, 'config-dir', configDir='/opt/x', canonical=False, reason='foreign', exists=True, launchEnv=None,
          overriddenBy=['apiKeyHelper', ], warnings=[NCD])),
    env={CC: '/opt/x'}, fs={'/opt/x/settings.json': F('{"apiKeyHelper": "x"}')})
res('a4-overridden-by-mixed', 'env var and apiKeyHelper together', 'A4 Result',
    ok(rr(wl, 'work', 'config-dir', overriddenBy=['ANTHROPIC_API_KEY', 'apiKeyHelper'])), env={CC: '/home/p/.claude-work', 'ANTHROPIC_API_KEY': 'k'},
    fs={'/home/p/.claude-work/settings.json': F('{"apiKeyHelper": "x"}')})

# ================= parse_marker table
def pm(id, desc, entry, expect, plat='linux', fs_extra=None, sec='A4 Marker parsing', path=None, ci=None):
    w = W_[plat]
    p = path or mp(w('proj'), w)
    fsd = {p: entry} if entry is not None else {}
    fsd.update(fs_extra or {})
    mk(id, desc, sec, op('parse_marker', path=p), expect, plat=plat, fs=fsd, ci=ci)

def pr(kind, name=None, pool=None, cands=None):
    if cands is None:
        cands = [name] if kind in ('account', 'default') else []
    return ok({'kind': kind, 'name': name, 'pool': pool, 'candidates': cands})

P1 = '/home/p/proj/.claude-account'
pm('a4-marker-parse-basic', 'plain name with newline', F('work\n'), pr('account', 'work'))
pm('a4-marker-parse-no-trailing-newline', 'no newline', F('work'), pr('account', 'work'))
pm('a4-marker-parse-bom', 'leading BOM stripped', F('\ufeffwork\n'), pr('account', 'work'))
pm('a4-marker-parse-bom-then-comment', 'BOM before a comment line', F('\ufeff# c\nwork\n'), pr('account', 'work'))
pm('a4-marker-parse-crlf', 'CRLF line ending', F('work\r\n'), pr('account', 'work'))
pm('a4-marker-parse-crlf-comment-blank', 'CRLF with comment and blank lines', F('# c\r\n\r\nwork\r\n'), pr('account', 'work'))
pm('a4-marker-parse-comments-blank', 'comments and blank lines are skipped', F('# first\n\n   \n# second\nwork\n'), pr('account', 'work'))
pm('a4-marker-parse-trim', 'each line is trimmed', F('  \t work \t \n'), pr('account', 'work'))
pm('a4-marker-parse-indented-comment', 'a comment is recognised after trimming', F('   # c\nwork\n'), pr('account', 'work'))
pm('a4-marker-parse-extra-lines-ignored', 'only the first remaining line counts', F('work\nthis is not valid\n'), pr('account', 'work'))
pm('a4-marker-parse-default', 'default overrides', F('default\n'), pr('default', 'default'))
pm('a4-marker-parse-pool', '@pool', F('@team-a\n'), pr('pool', None, 'team-a'))
pm('a4-marker-parse-pool-after-comment', '@pool after a comment', F('# c\n@team\n'), pr('pool', None, 'team'))
pm('a4-marker-parse-name-32', 'longest valid name', F('a' * 32 + '\n'), pr('account', 'a' * 32))
pm('a4-marker-parse-reserved-name-parses', 'reservation is not checked when parsing', F('profiles\n'), pr('account', 'profiles'))
pm('a4-marker-parse-pool-named-default', '@default is a pool by grammar', F('@default\n'), pr('pool', None, 'default'))
pm('a4-marker-parse-invalid-uppercase', 'uppercase name', F('Work\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-invalid-name-33', 'name too long', F('a' * 33), err('MARKER_INVALID', P1))
pm('a4-marker-parse-invalid-trailing-text', 'trailing comment on the target line is not allowed', F('work # note\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-invalid-first-line-wins', 'invalid first line is not skipped', F('Bad\nwork\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-invalid-pool-uppercase', '@Pool', F('@Pool\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-invalid-pool-empty', 'bare @', F('@\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-invalid-default-uppercase', 'Default', F('Default\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-empty', 'empty file', F(''), err('MARKER_INVALID', P1))
pm('a4-marker-parse-only-comments', 'only comments', F('# a\n# b\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-only-bom', 'only a BOM', F('\ufeff'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-whitespace-only', 'only whitespace', F('  \n\t\n'), err('MARKER_INVALID', P1))
pm('a4-marker-parse-exactly-1024-bytes', '1024 bytes is allowed', F('work\n' + '#' * 1019), pr('account', 'work'))
pm('a4-marker-parse-1025-bytes', '1025 bytes is MARKER_INVALID', F('work\n' + '#' * 1020), err('MARKER_INVALID', P1))
pm('a4-marker-parse-size-counts-bytes', 'multibyte characters count as bytes', F('work\n#' + '\u00e9' * 510), err('MARKER_INVALID', P1))
pm('a4-marker-parse-bom-counts-toward-cap', 'the BOM is part of the 1024 bytes', F('\ufeffwork\n' + '#' * 1017), err('MARKER_INVALID', P1))
pm('a4-marker-parse-fifo', 'FIFO is invalid and not read', X(), err('MARKER_INVALID', P1))
pm('a4-marker-parse-device', 'device is invalid', DEV(), err('MARKER_INVALID', P1))
pm('a4-marker-parse-directory-ignored', 'a directory is ignored', D(), pr('none'))
pm('a4-marker-parse-absent', 'absent marker', None, pr('none'))
pm('a4-marker-parse-link-to-file', 'a link is followed', L('/data/m'), pr('account', 'work'), fs_extra={'/data/m': F('work\n')})
pm('a4-marker-parse-link-to-dir', 'a link to a directory is ignored', L('/data/d'), pr('none'), fs_extra={'/data/d': D()})
pm('a4-marker-parse-link-to-fifo', 'a link to a FIFO is invalid', L('/data/q'), err('MARKER_INVALID', P1), fs_extra={'/data/q': X()})
pm('a4-marker-parse-dangling-link', 'a dangling link counts as no marker', L('/mnt/gone'), pr('none'))
pm('a4-marker-parse-unreadable-file', 'a marker that cannot be opened is MARKER_INVALID', F('work', unreadable=True), err('MARKER_INVALID', P1))
pm('a4-marker-parse-unreadable-parent-dir', 'an unreadable parent means no marker', None, pr('none'),
   path='/home/p/locked/.claude-account', fs_extra={'/home/p/locked': D(unreadable=True)})
pm('a4-marker-parse-win32', 'win32 path and CRLF', F('work\r\n'), pr('account', 'work'), plat='win32')
pm('a4-marker-parse-win32-invalid', 'win32 invalid target keeps the path', F('Work'), err('MARKER_INVALID', 'C:\\Users\\p\\proj\\.claude-account'), plat='win32')

# ================= marker through resolve
WORKM = {'/home/p/proj/.claude-account': F('work\n')}
res('a4-default-nothing-matches', 'no env, no marker, no claim', 'A4 Step 3', ok(rr(wl, 'default', 'default')), fs={})
res('a4-default-with-dir', 'default with a real ~/.claude', 'A4 Step 3', ok(rr(wl, 'default', 'default')),
    fs={'/home/p/.claude': D(), **WORK})
res('a4-default-dir-missing-still-exists', 'default always exists', ['A2 Discovery', 'A4 Result'], ok(rr(wl, 'default', 'default', exists=True)))
res('a4-marker-at-cwd', 'marker in cwd', 'A4 Step 2.1', ok(rr(wl, 'work', 'marker-file', P1)), cwd='/home/p/proj', fs={**WORKM, **WORK})
res('a4-marker-in-parent', 'marker found by walking up', 'A4 Step 2', ok(rr(wl, 'work', 'marker-file', P1)),
    cwd='/home/p/proj/a/b', fs={**WORKM, **WORK, '/home/p/proj/a/b': D()})
res('a4-marker-in-home', 'marker in $HOME', 'A4 Step 2', ok(rr(wl, 'work', 'marker-file', '/home/p/.claude-account')),
    cwd='/home/p/x/y', fs={'/home/p/.claude-account': F('work'), **WORK, '/home/p/x/y': D()})
res('a4-marker-at-posix-root', 'the walk reaches the filesystem root', 'A4 Step 2', ok(rr(wl, 'work', 'marker-file', '/.claude-account')),
    cwd='/home/p', fs={'/.claude-account': F('work'), **WORK})
res('a4-marker-nearest-wins', 'nearest marker wins', 'A4 Step 2',
    ok(rr(wl, 'personal', 'marker-file', '/home/p/proj/a/.claude-account')), cwd='/home/p/proj/a/b',
    fs={'/home/p/proj/a/.claude-account': F('personal\n'), **WORKM, **WP, '/home/p/proj/a/b': D()})
res('a4-marker-default-overrides-parent', 'marker "default" overrides a marker further up', 'A4 Marker parsing',
    ok(rr(wl, 'default', 'marker-file', '/home/p/proj/a/.claude-account')), cwd='/home/p/proj/a',
    fs={'/home/p/proj/a/.claude-account': F('default\n'), **WORKM, **WORK})
res('a4-marker-default-overrides-claim', 'marker "default" overrides a claim further up', 'A4 Marker parsing',
    ok(rr(wl, 'default', 'marker-file', '/home/p/dev/proj/.claude-account')), cwd='/home/p/dev/proj',
    fs={'/home/p/dev/proj/.claude-account': F('default'), '/home/p/.claude-work/.multi-account.json': F(spec(directories=['~/dev']))})
res('a4-marker-directory-ignored', 'a directory named .claude-account is skipped, the walk continues', 'A4 Marker parsing',
    ok(rr(wl, 'work', 'marker-file', '/home/p/.claude-account')), cwd='/home/p/proj',
    fs={'/home/p/proj/.claude-account': D(), '/home/p/.claude-account': F('work'), **WORK})
res('a4-marker-directory-only-gives-default', 'only a directory marker: default', 'A4 Marker parsing',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/proj', fs={'/home/p/proj/.claude-account': D(), **WORK})
res('a4-marker-fifo-invalid', 'a FIFO marker is MARKER_INVALID', 'A4 Marker parsing', err('MARKER_INVALID', P1),
    cwd='/home/p/proj', fs={P1: X()})
res('a4-marker-invalid-no-fallback', 'an invalid marker never falls back to a parent marker', 'A4 Marker parsing',
    err('MARKER_INVALID', P1), cwd='/home/p/proj', fs={P1: F('Bad Name'), '/home/p/.claude-account': F('work'), **WORK})
res('a4-marker-oversized', 'oversized marker', 'A4 Marker parsing', err('MARKER_INVALID', P1), cwd='/home/p/proj',
    fs={P1: F('work\n' + '#' * 1020), **WORK})
res('a4-marker-unreadable-file', 'unreadable marker file', 'A4 Marker parsing', err('MARKER_INVALID', P1), cwd='/home/p/proj',
    fs={P1: F('work', unreadable=True), **WORK})
res('a4-marker-symlink-followed', 'a linked marker is read', 'A4 Marker parsing', ok(rr(wl, 'work', 'marker-file', P1)),
    cwd='/home/p/proj', fs={P1: L('/data/shared-marker'), '/data/shared-marker': F('work\n'), **WORK})
res('a4-marker-dangling-link-ignored', 'a dangling marker link is no marker', 'A4 Marker parsing', ok(rr(wl, 'default', 'default')),
    cwd='/home/p/proj', fs={P1: L('/mnt/gone')})
res('a4-marker-target-not-found', 'binding to a missing account names the marker path', 'A4 Step 2',
    err('ACCOUNT_NOT_FOUND', P1), cwd='/home/p/proj', fs=WORKM)
res('a4-marker-target-dangling-account', 'binding to a dangling account', 'A4 Step 2',
    err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-work'), cwd='/home/p/proj', fs={**WORKM, '/home/p/.claude-work': L('/mnt/gone')})
res('a4-marker-target-not-found-no-fallback', 'a missing account never falls back to a parent binding', 'A4 Step 2',
    err('ACCOUNT_NOT_FOUND', P1), cwd='/home/p/proj', fs={P1: F('ghost'), '/home/p/.claude-account': F('work'), **WORK})
res('a4-marker-target-reserved-existing', 'marker names a reserved but existing account', ['A2 Names', 'A4 Step 2'],
    ok(rr(wl, 'account', 'marker-file', P1, warnings=['RESERVED_NAME'])), cwd='/home/p/proj',
    fs={P1: F('account\n'), '/home/p/.claude-account': D()})
res('a4-marker-pool', 'pool binding in Part A: account null, pool set, no launchEnv', 'A4 Pools',
    ok(rr(wl, None, 'marker-file', P1, pool='team', configDir=None, canonical=False, exists=False, launchEnv=None)),
    cwd='/home/p/proj', fs={P1: F('@team\n')})
res('a4-marker-pool-needs-no-accounts', 'pool binding does not look at accounts', 'A4 Pools',
    ok(rr(wl, None, 'marker-file', '/home/p/.claude-account', pool='nothing-here', configDir=None, canonical=False, exists=False, launchEnv=None)),
    cwd='/home/p/x', fs={'/home/p/.claude-account': F('@nothing-here')})
res('a4-marker-env-beats-marker', 'env selection beats a directory marker', 'A4 Step 1',
    ok(rr(wl, 'personal', 'env')), env={MA: 'personal'}, cwd='/home/p/proj', fs={**WORKM, **WP})
res('a4-marker-config-dir-beats-marker', 'CLAUDE_CONFIG_DIR beats a directory marker', 'A4 Step 1',
    ok(rr(wl, 'personal', 'config-dir')), env={CC: '/home/p/.claude-personal'}, cwd='/home/p/proj', fs={**WORKM, **WP})
res('a4-cwd-lexically-normalised', 'cwd is normalised lexically before walking', 'A4 Step 2',
    ok(rr(wl, 'work', 'marker-file', P1)), cwd='/home/p/proj/sub/../', fs={**WORKM, **WORK, '/home/p/proj/sub': D()})
res('a4-marker-darwin-case-insensitive-cwd', 'matchedPath keeps the walked spelling', 'A4 Step 2',
    ok(rr(wd, 'work', 'marker-file', '/Users/p/Proj/.claude-account')), plat='darwin', cwd='/Users/p/Proj/src',
    fs={'/Users/p/proj/.claude-account': F('work\n'), '/Users/p/proj/src': D(), **acct(wd, 'work')})
res('a4-marker-win32-walk', 'win32 walk with backslashes', 'A4 Step 2',
    ok(rr(ww, 'work', 'marker-file', 'C:\\Users\\p\\proj\\.claude-account')), plat='win32', cwd='C:\\Users\\p\\proj\\src',
    fs={'C:\\Users\\p\\proj\\.claude-account': F('work\r\n'), 'C:\\Users\\p\\proj\\src': D(), **acct(ww, 'work')})
res('a4-marker-win32-forward-slash-cwd', 'win32 cwd with forward slashes', 'A4 Step 2',
    ok(rr(ww, 'work', 'marker-file', 'C:\\Users\\p\\proj\\.claude-account')), plat='win32', cwd='C:/Users/p/proj/src/',
    fs={'C:\\Users\\p\\proj\\.claude-account': F('work'), 'C:\\Users\\p\\proj\\src': D(), **acct(ww, 'work')})
res('a4-marker-win32-drive-root', 'win32 walk ends at the drive root', 'A4 Step 2',
    ok(rr(ww, 'work', 'marker-file', 'C:\\.claude-account')), plat='win32', cwd='C:\\Users\\p',
    fs={'C:\\.claude-account': F('work'), **acct(ww, 'work')})
res('a4-marker-win32-junction-account', 'win32: marker binds to a junction account, link path kept', ['A2 Relocation', 'A4 Step 2'],
    ok(rr(ww, 'work', 'marker-file', 'C:\\Users\\p\\proj\\.claude-account')), plat='win32', cwd='C:\\Users\\p\\proj',
    fs={'C:\\Users\\p\\proj\\.claude-account': F('work'), 'C:\\Users\\p\\.claude-work': J('D:\\data\\work'), 'D:\\data\\work': D()})
res('a4-reserved-name-in-env-existing', 'reserved but existing account via env', ['A2 Names'],
    ok(rr(wl, 'swap-backup', 'env', warnings=['RESERVED_NAME'])), env={MA: 'swap-backup'}, fs=acct(wl, 'swap-backup'))
res('a4-walk-unreadable-dir-no-error', 'a directory the walk cannot read counts as no marker', 'A4 Step 2',
    ok(rr(wl, 'work', 'marker-file', '/home/p/.claude-account')), cwd='/home/p/locked/sub',
    fs={'/home/p/locked': D(unreadable=True), '/home/p/.claude-account': F('work'), **WORK})

# ================= git working trees
REPO = '/home/p/dev/repo'
RM = REPO + '/.claude-account'
GIT = {REPO + '/.git': D()}
res('a4-git-marker-ignored-same-level', 'marker next to .git is ignored and listed', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO, fs={**GIT, RM: F('work\n'), **WORK})
res('a4-git-marker-ignored-in-subdir', 'marker below the repo root is ignored too', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[REPO + '/sub/.claude-account'], warnings=['MARKER_IGNORED_IN_REPO'])),
    cwd=REPO + '/sub/x', fs={**GIT, REPO + '/sub/.claude-account': F('work\n'), REPO + '/sub/x': D(), **WORK})
res('a4-git-marker-above-repo-honoured', 'a marker above the repo root is not in the working tree', 'A4 Markers in git working trees',
    ok(rr(wl, 'work', 'marker-file', '/home/p/dev/.claude-account')), cwd=REPO + '/sub',
    fs={**GIT, '/home/p/dev/.claude-account': F('work\n'), REPO + '/sub': D(), **WORK})
res('a4-git-ignored-then-parent-marker-binds', 'ignored marker listed, marker above the repo binds', 'A4 Markers in git working trees',
    ok(rr(wl, 'work', 'marker-file', '/home/p/dev/.claude-account', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO,
    fs={**GIT, RM: F('personal\n'), '/home/p/dev/.claude-account': F('work\n'), **WP})
res('a4-git-two-ignored-markers', 'every ignored marker on the way is listed, nearest first', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[REPO + '/sub/.claude-account', RM],
          warnings=['MARKER_IGNORED_IN_REPO', 'MARKER_IGNORED_IN_REPO'])), cwd=REPO + '/sub',
    fs={**GIT, REPO + '/sub/.claude-account': F('work'), RM: F('work'), **WORK})
res('a4-git-gitlink-file', '.git as a file (worktree or submodule) counts', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO,
    fs={REPO + '/.git': F('gitdir: /elsewhere\n'), RM: F('work\n'), **WORK})
res('a4-git-trust-repo-markers', 'trustRepoMarkers honours the marker', 'A4 Markers in git working trees',
    ok(rr(wl, 'work', 'marker-file', RM)), cwd=REPO, opts={'trustRepoMarkers': True}, fs={**GIT, RM: F('work\n'), **WORK})
res('a4-git-ignored-marker-not-parsed', 'an ignored marker is never read, so invalid content is no error', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO, fs={**GIT, RM: F('Not A Name')})
res('a4-git-ignored-fifo-marker', 'an ignored FIFO marker is never opened', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO, fs={**GIT, RM: X()})
res('a4-git-directory-marker-not-listed', 'a directory marker is ignored silently, not listed', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default')), cwd=REPO, fs={**GIT, RM: D()})
res('a4-git-claim-not-affected', 'claims bind inside a git tree; the ignored marker is still listed', 'A4 Markers in git working trees',
    ok(rr(wl, 'work', 'claim', REPO, ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO,
    fs={**GIT, RM: F('personal\n'), '/home/p/.claude-work/.multi-account.json': F(spec(directories=['~/dev/repo'])), **WP})
res('a4-git-ceiling-cuts-lookahead', 'a ceiling below the repo root hides the .git from the lookahead', 'A4 Step 2',
    ok(rr(wl, 'work', 'marker-file', REPO + '/sub/.claude-account')), cwd=REPO + '/sub', opts={'ceilingDirs': [REPO + '/sub']},
    fs={**GIT, REPO + '/sub/.claude-account': F('work\n'), **WORK})
res('a4-git-ceiling-at-repo-root', 'ceiling at the repo root still sees its .git', 'A4 Step 2',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO, opts={'ceilingDirs': [REPO]},
    fs={**GIT, RM: F('work\n'), **WORK})
res('a4-git-win32', 'win32 repo marker ignored', 'A4 Markers in git working trees',
    ok(rr(ww, 'default', 'default', ignoredMarkers=['C:\\src\\r\\.claude-account'], warnings=['MARKER_IGNORED_IN_REPO'])), plat='win32',
    cwd='C:\\src\\r\\pkg', fs={'C:\\src\\r\\.git': D(), 'C:\\src\\r\\.claude-account': F('work'), 'C:\\src\\r\\pkg': D(), **acct(ww, 'work')})

# ================= claims
def cl(w, name, *dirs, **kw):
    return {w('.claude-' + name, '.multi-account.json'): F(spec(directories=list(dirs), **kw))}

DEV = {'/home/p/dev/personal': D()}
res('a4-claim-basic', 'tilde claim binds a directory below it', 'A4 Step 2.2',
    ok(rr(wl, 'work', 'claim', '/home/p/dev/personal')), cwd='/home/p/dev/personal/x',
    fs={**cl(wl, 'work', '~/dev/personal'), '/home/p/dev/personal/x': D()})
res('a4-claim-at-cwd', 'claim on the cwd itself', 'A4 Step 2.2',
    ok(rr(wl, 'work', 'claim', '/home/p/dev/personal')), cwd='/home/p/dev/personal', fs={**cl(wl, 'work', '~/dev/personal'), **DEV})
res('a4-claim-absolute-path', 'absolute claim', 'A3',
    ok(rr(wl, 'work', 'claim', '/srv/code')), cwd='/srv/code/a', fs={**cl(wl, 'work', '/srv/code'), '/srv/code/a': D()})
res('a4-claim-tilde-home', 'a bare ~/ claims the home directory', 'A3',
    ok(rr(wl, 'work', 'claim', '/home/p')), cwd='/home/p/x', fs={**cl(wl, 'work', '~/'), '/home/p/x': D()})
res('a4-claim-nonexistent-ignored', 'claims that do not exist are ignored', 'A4 Step 2.2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/dev/x', fs={**cl(wl, 'work', '~/dev/nope', '/no/such'), '/home/p/dev/x': D()})
res('a4-claim-duplicate-spellings-same-account', 'one account claiming a directory twice is not a conflict', 'A4 Step 2.2',
    ok(rr(wl, 'work', 'claim', '/home/p/dev/personal')), cwd='/home/p/dev/personal', fs={**cl(wl, 'work', '~/dev/personal', '/home/p/dev/personal/'), **DEV})
res('a4-claim-via-link-claimed', 'a claim through a link matches by identity', 'A4 Step 2.2',
    ok(rr(wl, 'work', 'claim', '/srv/dev')), cwd='/srv/dev/x',
    fs={**cl(wl, 'work', '~/dev'), '/home/p/dev': L('/srv/dev'), '/srv/dev/x': D()})
res('a4-claim-via-link-cwd', 'a cwd under a link matches a claim on the real path', 'A4 Step 2.2',
    ok(rr(wl, 'work', 'claim', '/home/p/dev')), cwd='/home/p/dev/x',
    fs={**cl(wl, 'work', '/srv/dev'), '/home/p/dev': L('/srv/dev'), '/srv/dev/x': D()})
res('a4-claim-by-inode', 'two paths with the same device and inode are the same directory', 'A4 Step 2.2',
    ok(rr(wl, 'work', 'claim', '/mnt/bind/proj')), cwd='/mnt/bind/proj/x',
    fs={**cl(wl, 'work', '/home/p/proj'), '/home/p/proj': D(inode=7), '/mnt/bind/proj': D(inode=7), '/mnt/bind/proj/x': D()})
res('a4-claim-same-inode-other-device-no-match', 'device is part of the identity', 'A4 Step 2.2',
    ok(rr(wl, 'default', 'default')), cwd='/mnt/bind/proj',
    fs={**cl(wl, 'work', '/home/p/proj'), '/home/p/proj': D(inode=7), '/mnt/bind/proj': D(inode=7, dev=2)})
res('a4-claim-case-variant-darwin', 'case-insensitive fs: a claim spelled in other case matches', 'A4 Step 2.2',
    ok(rr(wd, 'work', 'claim', '/Users/p/dev/personal')), plat='darwin', cwd='/Users/p/dev/personal/x',
    fs={**cl(wd, 'work', '~/Dev/Personal'), '/Users/p/dev/personal/x': D()})
res('a4-claim-case-variant-linux-no-match', 'case-sensitive fs: other case is another (missing) directory', 'A4 Step 2.2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/dev/personal', fs={**cl(wl, 'work', '~/Dev/Personal'), **DEV})
res('a4-claim-win32-case-insensitive', 'win32 claim in other case', 'A4 Step 2.2',
    ok(rr(ww, 'work', 'claim', 'C:\\Users\\p\\dev')), plat='win32', cwd='C:\\Users\\p\\dev\\x',
    fs={**cl(ww, 'work', 'c:\\USERS\\p\\Dev'), 'C:\\Users\\p\\dev\\x': D()})
res('a4-claim-win32-tilde', 'win32 ~/ claim expands against home with backslashes', 'A3',
    ok(rr(ww, 'work', 'claim', 'C:\\Users\\p\\dev')), plat='win32', cwd='C:\\Users\\p\\dev',
    fs={**cl(ww, 'work', '~/dev'), 'C:\\Users\\p\\dev': D()})
res('a4-claim-win32-other-drive', 'win32 claim on another drive', 'A3',
    ok(rr(ww, 'work', 'claim', 'D:\\code')), plat='win32', cwd='D:\\code\\app',
    fs={**cl(ww, 'work', 'D:\\code'), 'D:\\code\\app': D()})
res('a4-claim-nearest-level-wins', 'the nearest claimed level wins', 'A4 Step 2',
    ok(rr(wl, 'personal', 'claim', '/home/p/dev/sub')), cwd='/home/p/dev/sub/x',
    fs={**cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '~/dev/sub'), '/home/p/dev/sub/x': D()})
res('a4-claim-default-account', 'default may claim directories', 'A3',
    ok(rr(wl, 'default', 'claim', '/home/p/dev')), cwd='/home/p/dev/x',
    fs={'/home/p/.claude/.multi-account.json': F(spec(directories=['~/dev'])), '/home/p/dev/x': D(), **WORK})
res('a4-claim-marker-beats-claim-same-level', 'at the same level the marker wins', 'A4 Step 2',
    ok(rr(wl, 'personal', 'marker-file', '/home/p/dev/.claude-account')), cwd='/home/p/dev/x',
    fs={'/home/p/dev/.claude-account': F('personal'), **cl(wl, 'work', '~/dev'), **WP, '/home/p/dev/x': D()})
res('a4-claim-nearer-claim-beats-parent-marker', 'a claim nearer than a marker wins', 'A4 Step 2',
    ok(rr(wl, 'personal', 'claim', '/home/p/dev/sub')), cwd='/home/p/dev/sub',
    fs={'/home/p/dev/.claude-account': F('work'), **cl(wl, 'personal', '~/dev/sub'), **WP, '/home/p/dev/sub': D()})
res('a4-claim-nearer-marker-beats-parent-claim', 'a marker nearer than a claim wins', 'A4 Step 2',
    ok(rr(wl, 'personal', 'marker-file', '/home/p/dev/sub/.claude-account')), cwd='/home/p/dev/sub',
    fs={'/home/p/dev/sub/.claude-account': F('personal'), **cl(wl, 'work', '~/dev'), **WP})
res('a4-claim-conflict-reached', 'two accounts claim the same directory and the walk reaches it', 'A4 Step 2.2',
    err('CLAIM_CONFLICT', '/home/p/dev'), cwd='/home/p/dev/x',
    fs={**cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '/home/p/dev'), '/home/p/dev/x': D()})
res('a4-claim-conflict-different-spellings', 'conflict is by identity: a link spelling clashes with the real path', 'A4 Step 2.2',
    err('CLAIM_CONFLICT', '/home/p/dev'), cwd='/home/p/dev',
    fs={**cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '/data/devlink'), '/data/devlink': L('/home/p/dev'), '/home/p/dev': D()})
res('a4-claim-conflict-not-reached-nearer-claim', 'a conflict above a nearer claim is never raised', 'A4 Step 2.2',
    ok(rr(wl, 'extra', 'claim', '/home/p/dev/sub')), cwd='/home/p/dev/sub/x',
    fs={**cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '~/dev'), **cl(wl, 'extra', '~/dev/sub'), '/home/p/dev/sub/x': D()})
res('a4-claim-conflict-not-reached-marker-same-level', 'a marker at the conflicted level wins before claims are looked at', 'A4 Step 2',
    ok(rr(wl, 'work', 'marker-file', '/home/p/dev/.claude-account')), cwd='/home/p/dev/x',
    fs={'/home/p/dev/.claude-account': F('work'), **cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '~/dev'), '/home/p/dev/x': D()})
res('a4-claim-conflict-not-reached-ceiling', 'a conflict above the ceiling is not reached', 'A4 Step 2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/dev/x', opts={'ceilingDirs': ['/home/p/dev/x']},
    fs={**cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '~/dev'), '/home/p/dev/x': D()})
res('a4-claim-conflict-not-reached-env', 'env selection never consults claims', 'A4 Step 1',
    ok(rr(wl, 'work', 'env')), env={MA: 'work'}, cwd='/home/p/dev',
    fs={**cl(wl, 'work', '~/dev'), **cl(wl, 'personal', '~/dev')})
res('a4-claim-alias-group-named-represents', 'aliases are one account and the named member claims: default and work (same dir) is no conflict', ['A2 Relocation', 'A4 Step 2.2'],
    ok(rr(wl, 'work', 'claim', '/home/p/dev')), cwd='/home/p/dev/x',
    fs={'/home/p/.claude': L('/home/p/.claude-work'), **cl(wl, 'work', '~/dev'), '/home/p/dev/x': D()})
res('a4-claim-unreadable-cwd-skipped', 'claims at a level the walk cannot stat are skipped', 'A4 Step 2',
    ok(rr(wl, 'work', 'claim', '/home/p')), cwd='/home/p/locked/sub',
    fs={**cl(wl, 'work', '~/'), '/home/p/locked': D(unreadable=True)})
res('a4-claim-dangling-account-has-no-claims', 'a dangling account contributes no claims and no error', 'A2 Discovery',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/dev', fs={'/home/p/.claude-gone': L('/mnt/gone'), '/home/p/dev': D()})
res('a4-claim-target-reserved-account', 'a claim by a reserved-name account resolves with RESERVED_NAME', 'A2 Names',
    ok(rr(wl, 'profiles', 'claim', '/home/p/dev', warnings=['RESERVED_NAME'])), cwd='/home/p/dev',
    fs={**cl(wl, 'profiles', '~/dev'), '/home/p/dev': D()})

# spec file invalid at resolve time
BAD = {'/home/p/.claude-bad/.multi-account.json': F('{nope')}
res('a4-spec-invalid-reached-by-walk', 'the walk needs claims, so an invalid spec file fails', 'A3',
    err('SPEC_FILE_INVALID', '/home/p/.claude-bad/.multi-account.json'), fs=BAD)
res('a4-spec-invalid-is-in-another-account', 'it does not matter which account owns the invalid file', 'A3',
    err('SPEC_FILE_INVALID', '/home/p/.claude-bad/.multi-account.json'), cwd='/home/p/proj', fs={**BAD, **WORK, '/home/p/proj': D()})
res('a4-spec-invalid-first-in-order', 'the first invalid file in name order is reported', 'A3',
    err('SPEC_FILE_INVALID', '/home/p/.claude-a/.multi-account.json'),
    fs={'/home/p/.claude-b/.multi-account.json': F('x'), '/home/p/.claude-a/.multi-account.json': F('x')})
res('a4-spec-invalid-default-first', 'default is checked before named accounts', 'A3',
    err('SPEC_FILE_INVALID', '/home/p/.claude/.multi-account.json'),
    fs={'/home/p/.claude-a/.multi-account.json': F('x'), '/home/p/.claude/.multi-account.json': F('x')})
res('a4-spec-invalid-not-consulted-when-marker-binds', 'a marker bound before claims are needed', 'A3',
    ok(rr(wl, 'work', 'marker-file', P1)), cwd='/home/p/proj', fs={**BAD, **WORKM, **WORK})
res('a4-spec-invalid-not-consulted-env', 'env selection never reads spec files', 'A3',
    ok(rr(wl, 'work', 'env')), env={MA: 'work'}, fs={**BAD, **WORK})
res('a4-spec-invalid-not-consulted-config-dir', 'CLAUDE_CONFIG_DIR never reads spec files', 'A3',
    ok(rr(wl, 'work', 'config-dir')), env={CC: '/home/p/.claude-work'}, fs={**BAD, **WORK})
res('a4-spec-invalid-after-ignored-repo-marker', 'an ignored repo marker does not bind, so claims are needed', 'A3',
    err('SPEC_FILE_INVALID', '/home/p/.claude-bad/.multi-account.json'), cwd=REPO, fs={**BAD, **GIT, RM: F('work')})
res('a4-spec-invalid-symlink-to-dir', 'a spec path that is a link to a directory is invalid', 'A3',
    err('SPEC_FILE_INVALID', '/home/p/.claude-bad/.multi-account.json'),
    fs={'/home/p/.claude-bad/.multi-account.json': L('/data/d'), '/data/d': D()})
res('a4-spec-unreadable-account-dir-link-not-consulted', 'an unreadable account has no readable spec and is skipped as unavailable', 'A2 Discovery',
    ok(rr(wl, 'default', 'default')), fs={'/home/p/.claude-locked': L('/mnt/x', unreadable=True)})

# ceilings
res('a4-ceiling-stops-walk', 'marker above the ceiling is not seen', 'A4 Step 2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/proj/sub', opts={'ceilingDirs': ['/home/p/proj']},
    fs={'/home/p/.claude-account': F('work'), '/home/p/proj/sub': D(), **WORK})
res('a4-ceiling-dir-itself-is-checked', 'the ceiling directory is the last level checked', 'A4 Step 2',
    ok(rr(wl, 'work', 'marker-file', P1)), cwd='/home/p/proj/sub', opts={'ceilingDirs': ['/home/p/proj']},
    fs={**WORKM, '/home/p/proj/sub': D(), **WORK})
res('a4-ceiling-claim-at-ceiling', 'a claim on the ceiling directory binds', 'A4 Step 2',
    ok(rr(wl, 'work', 'claim', '/home/p/dev')), cwd='/home/p/dev/x', opts={'ceilingDirs': ['/home/p/dev']},
    fs={**cl(wl, 'work', '~/dev'), '/home/p/dev/x': D()})
res('a4-ceiling-cwd-is-ceiling', 'cwd equal to the ceiling checks only cwd', 'A4 Step 2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/proj', opts={'ceilingDirs': ['/home/p/proj']},
    fs={'/home/p/.claude-account': F('work'), **WORK})
res('a4-ceiling-normalised', 'ceiling entries are normalised', 'A4 Step 2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/proj/sub', opts={'ceilingDirs': ['/home/p/./proj/']},
    fs={'/home/p/.claude-account': F('work'), '/home/p/proj/sub': D(), **WORK})
res('a4-ceiling-multiple-nearest-stops', 'with several ceilings the nearest one stops the walk', 'A4 Step 2',
    ok(rr(wl, 'default', 'default')), cwd='/home/p/proj/sub', opts={'ceilingDirs': ['/home/p', '/home/p/proj/sub']},
    fs={'/home/p/proj/.claude-account': F('work'), '/home/p/proj/sub': D(), **WORK})
res('a4-ceiling-case-sensitive-linux', 'on a case-sensitive fs a differently cased ceiling does not match', 'A4 Step 2',
    ok(rr(wl, 'work', 'marker-file', '/home/p/.claude-account')), cwd='/home/p/proj', opts={'ceilingDirs': ['/home/p/PROJ']},
    fs={'/home/p/.claude-account': F('work'), **WORK})
res('a4-ceiling-case-insensitive-darwin', 'on a case-insensitive fs the ceiling matches ignoring case', 'A4 Step 2',
    ok(rr(wd, 'default', 'default')), plat='darwin', cwd='/Users/p/proj/sub', opts={'ceilingDirs': ['/users/P/PROJ']},
    fs={'/Users/p/.claude-account': F('work'), '/Users/p/proj/sub': D(), **acct(wd, 'work')})
res('a4-ceiling-win32', 'win32 ceiling', 'A4 Step 2',
    ok(rr(ww, 'default', 'default')), plat='win32', cwd='C:\\Users\\p\\proj\\sub', opts={'ceilingDirs': ['c:/users/p/proj']},
    fs={'C:\\Users\\p\\.claude-account': F('work'), 'C:\\Users\\p\\proj\\sub': D(), **acct(ww, 'work')})
