"""Cases added for spec v0.2 (audit 2026-10-07 and owner decisions)."""
from gen_lib import *
from gen_a import wl, wd, ww, W_, dacc, nacc, disc
from gen_a4 import res, mp, pm, pr, cl, WORK, WP, WORKM, P1, REPO, RM, GIT
from gen_b import (FRESH, uexp, WIN, CU, sess, managed, unmanaged, AC, AD, M2, stored, state, E1, E2, SP, FUT, OLD, poolspec, lim, TEAM, A, B, SID, BASE,
                   src_files, FULL_COPIED, HO, SD, MA, CC, LS, SS, ENVTOK, APIK, CLEARED, GC, OA, IDENT, cpok)
import datetime

NOWDT = datetime.datetime(2026, 10, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)


def ms(dt):
    return int(dt.timestamp() * 1000)


def iso_ms(m):
    return datetime.datetime.fromtimestamp(m / 1000, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (m % 1000)


# ================= A2 / A3
mk('a2-discover-alias-rep-is-first-named', 'in a group of default and two named links the first named account in name order represents it', ['A2 Relocation'],
   op('discover'), disc([dacc(wl, alias='abc'), nacc(wl, 'abc'), nacc(wl, 'zed', alias='abc')]),
   fs={'/home/p/.claude': L('/home/p/.claude-zed'), '/home/p/.claude-zed': D(), '/home/p/.claude-abc': L('/home/p/.claude-zed')})


def spec_case2(id, desc, entry, valid, hs=True, w=wl, plat='linux', sec='A3'):
    d = w('.claude-work')
    p = d + w.sep + '.multi-account.json'
    se = None if valid else {'code': 'SPEC_FILE_INVALID', 'path': p}
    mk(id, desc, sec, op('discover'), disc([dacc(w), nacc(w, 'work', hs=hs, se=se)]), plat=plat, fs={p: entry})


spec_case2('a3-spec-invalid-utf8', 'a spec file with invalid UTF-8 is invalid', FB(b'{"version": 1, "label": "caf\xe9"}'), False)
spec_case2('a3-spec-utf8-multibyte-valid', 'valid multibyte UTF-8 is fine', FB('{"version": 1, "label": "caf\u00e9"}'.encode('utf-8')), True)
spec_case2('a3-spec-priority-integer-valued-float', 'priority 2.0 is an integer value', F('{"version": 1, "priority": 2.0}'), True)
spec_case2('a3-spec-priority-max-safe', 'priority 2^53-1 is the largest allowed', F('{"version": 1, "priority": 9007199254740991}'), True)
spec_case2('a3-spec-priority-min-safe', 'priority -(2^53-1) is the smallest allowed', F('{"version": 1, "priority": -9007199254740991}'), True)
spec_case2('a3-spec-priority-2pow53', 'priority 2^53 is out of range', F('{"version": 1, "priority": 9007199254740992}'), False)
spec_case2('a3-spec-priority-fraction', 'priority 1.5 is not an integer', F('{"version": 1, "priority": 1.5}'), False)
spec_case2('a3-spec-priority-string', 'priority must be a number', F('{"version": 1, "priority": "1"}'), False)
spec_case2('a3-spec-priority-bool', 'priority true is not a number', F('{"version": 1, "priority": true}'), False)
spec_case2('a3-spec-priority-overflow', 'priority 1e400 overflows and is invalid', F('{"version": 1, "priority": 1e400}'), False)
spec_case2('a3-spec-depth-100-valid', 'JSON nested 100 levels deep is accepted', F('{"version": 1, "x": ' + '[' * 99 + ']' * 99 + '}'), True)
spec_case2('a3-spec-depth-101-invalid', 'JSON nested 101 levels deep is invalid', F('{"version": 1, "x": ' + '[' * 100 + ']' * 100 + '}'), False)
spec_case2('a3-spec-win32-tilde-backslash-valid', 'win32 accepts ~\\ claims', F(spec(directories=['~\\dev'])), True, w=ww, plat='win32')
spec_case2('a3-spec-linux-tilde-backslash-invalid', 'on linux ~\\dev is a relative path', F(spec(directories=['~\\dev'])), False)

# ================= A4 env
CLAUDE = {'CLAUDECODE': '1'}
res('a4-env-only-multi-not-applied-outside-claude', 'only CLAUDE_MULTI_ACCOUNT names a named account and nothing applied it', 'A4 Step 1.3',
    ok(rr(wl, 'work', 'env', applied=False, warnings=['ENV_NOT_APPLIED'])), env={MA: 'work'}, fs=WORK)
res('a4-env-only-multi-claudecode-other-value', 'CLAUDECODE must be exactly 1 to mean inside claude', 'A4 Step 1.3',
    ok(rr(wl, 'work', 'env', applied=False, warnings=['ENV_NOT_APPLIED'])), env={MA: 'work', 'CLAUDECODE': '0'}, fs=WORK)
res('a4-env-only-multi-inside-claude-conflict', 'inside claude the variable alone is a conflict, claude runs as default', 'A4 Step 1.3',
    err('ENV_CONFLICT', None), env={MA: 'work', **CLAUDE}, fs=WORK)
res('a4-env-only-multi-default-inside-claude-ok', 'MULTI=default agrees with an unset CLAUDE_CONFIG_DIR', 'A4 Step 1.3',
    ok(rr(wl, 'default', 'env')), env={MA: 'default', **CLAUDE})
res('a4-env-only-multi-inside-claude-missing-account', 'a missing account is reported before the conflict', 'A4 Step 1.3',
    err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), env={MA: 'work', **CLAUDE})
res('a4-env-only-multi-alias-of-default-is-applied', 'the slot account is the same directory as default, so it counts as applied', ['A4 Step 1.3', 'B7'],
    ok(rr(wl, 'work', 'env', applied=True)), env={MA: 'work', **CLAUDE}, fs=managed(wl))
res('a4-env-both-set-agree-inside-claude', 'both variables agree: applied, no conflict', 'A4 Step 1.2',
    ok(rr(wl, 'work', 'config-dir')), env={CC: '/home/p/.claude-work', MA: 'work', **CLAUDE}, fs=WORK)
res('a4-env-both-set-dangling-account', 'both vars agree on a dangling account: ACCOUNT_UNAVAILABLE, not a conflict', 'A4 Step 1.2',
    err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-work'), env={CC: '/home/p/.claude-work', MA: 'work'}, fs={'/home/p/.claude-work': L('/mnt/gone')})
res('a4-env-both-set-normalised-undiscovered', 'the agreement test normalises the config dir first', 'A4 Step 1.2',
    err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), env={CC: '/home/p/.claude-work/', MA: 'work'})
res('a4-env-both-set-slot-alias-agree', 'default and the slot account are one account, so they do not conflict', ['A4 Step 1.2', 'B7'],
    ok(rr(wl, 'work', 'config-dir')), env={CC: '/home/p/.claude-work', MA: 'default'}, fs=managed(wl))
res('a4-env-both-set-undiscovered-different-dir-conflicts', 'a foreign directory plus a missing account is a conflict', 'A4 Step 1.2',
    err('ENV_CONFLICT', None), env={CC: '/opt/x', MA: 'work'})

# globalConfig
res('a4-global-config-legacy-config-json', 'a legacy .config.json in the config dir is the global config', ['A1', 'A4 Result'],
    ok(rr(wl, 'work', 'config-dir', globalConfig='/home/p/.claude-work/.config.json')), env={CC: '/home/p/.claude-work'},
    fs={'/home/p/.claude-work/.config.json': F('{}')})
res('a4-global-config-custom-oauth-suffix', 'the custom oauth suffix names the global config', ['A1', 'A4 Result'],
    ok(rr(wl, 'work', 'config-dir', globalConfig='/home/p/.claude-work/.claude-custom-oauth.json', overriddenBy=['CLAUDE_CODE_CUSTOM_OAUTH_URL'])),
    env={CC: '/home/p/.claude-work', 'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'https://x.test'}, fs=WORK)
res('a4-global-config-default-account', 'default without CLAUDE_CONFIG_DIR uses $HOME/.claude.json', 'A4 Result',
    ok(rr(wl, 'default', 'default')), fs={})
res('a4-global-config-pool-is-null', 'a pool binding has no global config', 'A4 Result',
    ok(rr(wl, None, 'marker-file', P1, pool='team', configDir=None, canonical=False, exists=False, launchEnv=None)),
    cwd='/home/p/proj', fs={P1: F('@team\n')})

# overriddenBy
def ob(id, desc, env, expect, fs=None, clear=False):
    res(id, desc, 'A4 Result', ok(rr(wl, 'work', 'config-dir', overriddenBy=expect)), env={CC: '/home/p/.claude-work', **env}, fs=fs or WORK)

ob('a4-overridden-by-auth-token', 'ANTHROPIC_AUTH_TOKEN replaces the login', {'ANTHROPIC_AUTH_TOKEN': 't'}, ['ANTHROPIC_AUTH_TOKEN'])
ob('a4-overridden-by-use-bedrock', 'CLAUDE_CODE_USE_BEDROCK=1', {'CLAUDE_CODE_USE_BEDROCK': '1'}, ['CLAUDE_CODE_USE_BEDROCK'])
ob('a4-overridden-by-use-vertex-true', 'CLAUDE_CODE_USE_VERTEX=true (case-insensitive)', {'CLAUDE_CODE_USE_VERTEX': 'TRUE'}, ['CLAUDE_CODE_USE_VERTEX'])
ob('a4-overridden-by-use-foundry-yes', 'CLAUDE_CODE_USE_FOUNDRY=yes', {'CLAUDE_CODE_USE_FOUNDRY': 'yes'}, ['CLAUDE_CODE_USE_FOUNDRY'])
ob('a4-overridden-by-use-bedrock-falsy', 'CLAUDE_CODE_USE_BEDROCK=0 does not count', {'CLAUDE_CODE_USE_BEDROCK': '0'}, [])
ob('a4-overridden-by-profile', 'ANTHROPIC_PROFILE selects a federation profile', {'ANTHROPIC_PROFILE': 'dev'}, ['ANTHROPIC_PROFILE'])
ob('a4-overridden-by-profile-config-dir-alone', 'ANTHROPIC_CONFIG_DIR alone does not replace the login', {'ANTHROPIC_CONFIG_DIR': '/x'}, [])
ob('a4-overridden-by-securestorage-empty', 'an empty CLAUDE_SECURESTORAGE_CONFIG_DIR still counts (claude then reads ~/.claude)', {'CLAUDE_SECURESTORAGE_CONFIG_DIR': ''},
   ['CLAUDE_SECURESTORAGE_CONFIG_DIR'])
ob('a4-overridden-by-settings-env-api-key', 'ANTHROPIC_API_KEY set in the account settings.json env block', {}, ['ANTHROPIC_API_KEY'],
   fs={'/home/p/.claude-work/settings.json': F('{"env": {"ANTHROPIC_API_KEY": "k"}}')})
ob('a4-overridden-by-settings-env-empty-ignored', 'an empty value in the settings env block does not count', {}, [],
   fs={'/home/p/.claude-work/settings.json': F('{"env": {"ANTHROPIC_API_KEY": ""}}')})
ob('a4-overridden-by-env-and-settings-once', 'a variable set in both places is listed once', {'ANTHROPIC_API_KEY': 'k'}, ['ANTHROPIC_API_KEY'],
   fs={'/home/p/.claude-work/settings.json': F('{"env": {"ANTHROPIC_API_KEY": "k"}}')})
ob('a4-overridden-by-full-order', 'every source together, in the fixed order', {
    'CLAUDE_CODE_OAUTH_TOKEN': 'a', 'ANTHROPIC_API_KEY': 'b', 'ANTHROPIC_AUTH_TOKEN': 'c', 'CLAUDE_CODE_USE_BEDROCK': '1',
    'CLAUDE_CODE_USE_VERTEX': '1', 'CLAUDE_CODE_USE_FOUNDRY': '1', 'ANTHROPIC_PROFILE': 'p', 'CLAUDE_SECURESTORAGE_CONFIG_DIR': '/s'},
   ['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX',
    'CLAUDE_CODE_USE_FOUNDRY', 'ANTHROPIC_PROFILE', 'CLAUDE_SECURESTORAGE_CONFIG_DIR', 'apiKeyHelper'],
   fs={'/home/p/.claude-work/settings.json': F('{"apiKeyHelper": "x"}')})

# ================= A4 aliases
SLOT = managed(wl)
res('a4-marker-default-in-alias-group', 'a marker naming default while default is the slot: default, carrying aliasOf', ['A2 Relocation', 'A4 Step 2.1'],
    ok(rr(wl, 'default', 'marker-file', P1, aliasOf='work')), cwd='/home/p/proj', fs={**SLOT, P1: F('default\n')})
res('a4-marker-named-slot-account-is-stable', 'a marker naming the slot account gets its own config dir, not default', ['A2 Relocation', 'A4 Step 2.1'],
    ok(rr(wl, 'work', 'marker-file', P1)), cwd='/home/p/proj', fs={**SLOT, P1: F('work\n')})
res('a4-claim-named-slot-account-binds-by-name', 'a claim of the slot account launches it by name, not as default', ['A2 Relocation', 'A4 Step 2.2'],
    ok(rr(wl, 'work', 'claim', '/home/p/dev')), cwd='/home/p/dev/x', fs={**SLOT, **cl(wl, 'work', '~/dev'), '/home/p/dev/x': D()})
res('a4-claim-alias-two-named-first-represents', 'two named links to one dir: the first name claims, no conflict', ['A2 Relocation', 'A4 Step 2.2'],
    ok(rr(wl, 'a', 'claim', '/home/p/dev')), cwd='/home/p/dev',
    fs={'/home/p/.claude-a': D(), '/home/p/.claude-b': L('/home/p/.claude-a'), **cl(wl, 'a', '~/dev'), '/home/p/dev': D()})

# ================= A4 ordered lists
def pl(id, desc, content, expect, **kw):
    pm(id, desc, content, expect, **kw)

pl('a4-marker-list-two', 'two names', F('work, personal\n'), pr('list', 'work', cands=['work', 'personal']))
pl('a4-marker-list-no-spaces', 'no spaces around the comma', F('work,personal\n'), pr('list', 'work', cands=['work', 'personal']))
pl('a4-marker-list-loose-spaces', 'spaces and tabs around entries', F('  work \t,  personal ,x\n'), pr('list', 'work', cands=['work', 'personal', 'x']))
pl('a4-marker-list-with-default', 'default is allowed in a list', F('work, default\n'), pr('list', 'work', cands=['work', 'default']))
pl('a4-marker-list-default-first', 'default first', F('default,work\n'), pr('list', 'default', cands=['default', 'work']))
pl('a4-marker-list-after-comment', 'comments and blank lines are skipped first', F('# order\n\nwork, personal\n'), pr('list', 'work', cands=['work', 'personal']))
pl('a4-marker-list-extra-lines-ignored', 'later lines are ignored', F('work, personal\nnonsense here\n'), pr('list', 'work', cands=['work', 'personal']))
pl('a4-marker-list-crlf', 'CRLF line ending', F('work, personal\r\n'), pr('list', 'work', cands=['work', 'personal']))
pl('a4-marker-list-invalid-duplicate', 'duplicates are invalid', F('work, work\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-pool-entry', '@pool is not allowed in a list', F('work, @team\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-pool-first', '@pool first is not allowed either', F('@team, work\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-uppercase', 'every entry must be a valid name', F('work, Personal\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-trailing-comma', 'a trailing comma leaves an empty entry', F('work, personal,\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-leading-comma', 'a leading comma leaves an empty entry', F(',work\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-empty-entry', 'an empty entry in the middle', F('work,,personal\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-single-with-comma', 'one name plus a comma is not a list', F('work,\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-inner-space', 'a space inside an entry', F('work personal, x\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-invalid-trailing-comment', 'no trailing comment on the target line', F('work, personal # x\n'), err('MARKER_INVALID', P1))
pl('a4-marker-list-reserved-names-parse', 'reservation is not checked when parsing', F('profiles, work\n'), pr('list', 'profiles', cands=['profiles', 'work']))
pl('a4-marker-parse-invalid-utf8', 'invalid UTF-8 in a marker', FB(b'work # caf\xe9\n'), err('MARKER_INVALID', P1))
pl('a4-marker-parse-invalid-utf8-comment-line', 'invalid UTF-8 in a comment line still invalidates the file', FB(b'# caf\xe9\nwork\n'), err('MARKER_INVALID', P1))
pl('a4-marker-parse-valid-multibyte-comment', 'valid multibyte UTF-8 in a comment is fine', FB('# caf\u00e9\nwork\n'.encode('utf-8')), pr('account', 'work'))

LM = {'/home/p/proj/.claude-account': F('work, personal\n')}
res('a4-marker-list-resolve', 'a list binds the first entry and reports the full order', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work', 'personal'])), cwd='/home/p/proj', fs={**LM, **WP})
res('a4-marker-list-resolve-default-first', 'default first: launchEnv is for default', 'A4 Step 2.1',
    ok(rr(wl, 'default', 'marker-file', P1, candidates=['default', 'work'])), cwd='/home/p/proj', fs={P1: F('default, work\n'), **WORK})
res('a4-marker-list-resolve-default-second', 'default second: launchEnv is for the first', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work', 'default'])), cwd='/home/p/proj', fs={P1: F('work, default\n'), **WORK})
res('a4-marker-list-second-missing', 'a missing later entry does not fail: warning, candidates keep the list', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work', 'personal'], warnings=['CANDIDATE_UNAVAILABLE'])), cwd='/home/p/proj', fs={**LM, **WORK})
res('a4-marker-list-first-missing', 'a missing first entry is ACCOUNT_NOT_FOUND with the marker path', 'A4 Step 2.1',
    err('ACCOUNT_NOT_FOUND', P1), cwd='/home/p/proj', fs={**LM, **acct(wl, 'personal')})
res('a4-marker-list-entry-dangling', 'a dangling later entry gives a warning, not an error', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work', 'personal'], warnings=['CANDIDATE_UNAVAILABLE'])), cwd='/home/p/proj', fs={**LM, **WORK, '/home/p/.claude-personal': L('/mnt/gone')})
res('a4-marker-list-first-dangling', 'a dangling first entry is ACCOUNT_UNAVAILABLE', 'A4 Step 2.1',
    err('ACCOUNT_UNAVAILABLE', '/home/p/.claude-work'), cwd='/home/p/proj', fs={**LM, **acct(wl, 'personal'), '/home/p/.claude-work': L('/mnt/gone')})
res('a4-marker-list-entry-unreadable', 'an unreadable later entry gives a warning', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work', 'personal'], warnings=['CANDIDATE_UNAVAILABLE'])), cwd='/home/p/proj', fs={**LM, **WORK, '/home/p/.claude-personal': L('/mnt/x', unreadable=True)})
res('a4-marker-list-two-unavailable', 'one warning per unavailable entry', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work', 'a', 'b'], warnings=['CANDIDATE_UNAVAILABLE', 'CANDIDATE_UNAVAILABLE'])), cwd='/home/p/proj',
    fs={P1: F('work, a, b'), **WORK})
res('a4-marker-list-default-first-later-missing', 'default first, a later entry missing', 'A4 Step 2.1',
    ok(rr(wl, 'default', 'marker-file', P1, candidates=['default', 'ghost'], warnings=['CANDIDATE_UNAVAILABLE'])), cwd='/home/p/proj', fs={P1: F('default, ghost')})
res('a4-marker-list-missing-no-fallback', 'a missing first entry never falls back to a parent marker', 'A4 Step 2.1',
    err('ACCOUNT_NOT_FOUND', P1), cwd='/home/p/proj', fs={P1: F('ghost, work'), **WORK, '/home/p/.claude-account': F('work')})
res('a4-marker-list-invalid-no-fallback', 'an invalid list never falls back to a parent marker', 'A4 Step 2.1',
    err('MARKER_INVALID', P1), cwd='/home/p/proj', fs={P1: F('work, work'), '/home/p/.claude-account': F('work'), **WORK})
res('a4-marker-list-in-git-tree-ignored', 'a list marker in a git working tree is ignored like any marker', 'A4 Markers in git working trees',
    ok(rr(wl, 'default', 'default', ignoredMarkers=[RM], warnings=['MARKER_IGNORED_IN_REPO'])), cwd=REPO, fs={**GIT, RM: F('work, personal\n'), **WP})
res('a4-marker-list-in-git-tree-trusted', 'with trustRepoMarkers the list binds', 'A4 Markers in git working trees',
    ok(rr(wl, 'work', 'marker-file', RM, candidates=['work', 'personal'])), cwd=REPO, opts={'trustRepoMarkers': True}, fs={**GIT, RM: F('work, personal\n'), **WP})
res('a4-marker-list-env-beats-list', 'env selection beats a list marker, candidates is the env account', 'A4 Step 1',
    ok(rr(wl, 'personal', 'config-dir')), env={CC: '/home/p/.claude-personal'}, cwd='/home/p/proj', fs={**LM, **WP})
res('a4-marker-single-name-candidates', 'a single name has one candidate', 'A4 Step 2.1',
    ok(rr(wl, 'work', 'marker-file', P1, candidates=['work'])), cwd='/home/p/proj', fs={**WORKM, **WORK})
res('a4-marker-list-reserved-first-warns', 'reserved first entry resolves with RESERVED_NAME', 'A4 Step 2.1',
    ok(rr(wl, 'profiles', 'marker-file', P1, candidates=['profiles', 'work'], warnings=['RESERVED_NAME'])), cwd='/home/p/proj',
    fs={P1: F('profiles, work'), **acct(wl, 'profiles', 'work')})
res('a4-marker-invalid-utf8-resolve', 'an invalid UTF-8 marker is MARKER_INVALID through resolve', 'A4 Marker parsing',
    err('MARKER_INVALID', P1), cwd='/home/p/proj', fs={P1: FB(b'# caf\xe9\nwork\n'), **WORK})
res('a4-claim-win32-tilde-backslash', 'win32 claim written ~\\dev', 'A3',
    ok(rr(ww, 'work', 'claim', 'C:\\Users\\p\\dev')), plat='win32', cwd='C:\\Users\\p\\dev',
    fs={**cl(ww, 'work', '~\\dev'), 'C:\\Users\\p\\dev': D()})

# ================= B1
def envcase(id, desc, name, env, set_, unset, ob_, fs=None, clear=False):
    mk(id, desc, 'B1', op('env', name=name, **({'clearAuthOverrides': True} if clear else {})),
       ok({'set': set_, 'unset': unset, 'overriddenBy': ob_}), env=env, fs=fs)

W_SET = {CC: '/home/p/.claude-work', MA: 'work'}
envcase('b1-env-reports-more-auth-vars', 'the newer login replacements are reported', 'work',
        {'ANTHROPIC_AUTH_TOKEN': 't', 'CLAUDE_CODE_USE_BEDROCK': '1', 'ANTHROPIC_PROFILE': 'p'}, W_SET, [LS, SS],
        ['ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK', 'ANTHROPIC_PROFILE'])
envcase('b1-env-clear-auth-overrides-all', 'clearAuthOverrides unsets every login replacement and stops reporting them', 'work',
        {'ANTHROPIC_AUTH_TOKEN': 't', 'CLAUDE_CODE_USE_VERTEX': '1', 'CLAUDE_CODE_USE_FOUNDRY': '1', 'ANTHROPIC_PROFILE': 'p', ENVTOK: 'x', APIK: 'y',
         'CLAUDE_CODE_USE_BEDROCK': '1'},
        W_SET, sorted(CLEARED + [LS, SS]), [], clear=True)
envcase('b1-env-securestorage-empty-reported', 'an empty SECURESTORAGE variable is still reported', 'work', {SS: ''}, W_SET, [LS, SS], [SS])
envcase('b1-env-use-bedrock-falsy-not-reported', 'a falsy CLAUDE_CODE_USE_BEDROCK is not reported', 'work', {'CLAUDE_CODE_USE_BEDROCK': 'off'}, W_SET, [LS, SS], [])
envcase('b1-env-settings-env-key-survives-clear', 'a key from the settings env block cannot be cleared by the delta', 'work', {APIK: 'k'}, W_SET,
        sorted(CLEARED + [LS, SS]), [APIK], clear=True, fs={'/home/p/.claude-work/settings.json': F('{"env": {"ANTHROPIC_API_KEY": "k"}}')})

# ================= B2 identity from resolve, credentials
def ident_resolve(id, desc, env, fs, expect, cwd=None, op_name='identity', plat='linux'):
    mk(id, desc, ['B2', 'A4 Result'], op(op_name, resolve=True), expect, env=env, fs=fs, cwd=cwd, plat=plat)

ident_resolve('b2-identity-resolve-config-dir-home-claude', 'CLAUDE_CONFIG_DIR=$HOME/.claude reads ~/.claude/.claude.json, not ~/.claude.json', {CC: '/home/p/.claude'},
              {'/home/p/.claude.json': F(jd({'oauthAccount': {'emailAddress': 'wrong'}})), '/home/p/.claude/.claude.json': F(jd({'oauthAccount': OA}))}, ok(IDENT))
ident_resolve('b2-identity-resolve-config-dir-home-claude-no-global', 'the same setup with no ~/.claude/.claude.json has no data', {CC: '/home/p/.claude'},
              {'/home/p/.claude.json': F(jd({'oauthAccount': OA})), '/home/p/.claude': D()}, ok(None))
ident_resolve('b2-identity-resolve-named', 'a named account via env', {CC: '/home/p/.claude-work'}, {GC: F(jd({'oauthAccount': OA}))}, ok(IDENT))
ident_resolve('b2-identity-resolve-default', 'plain default reads ~/.claude.json', {}, {'/home/p/.claude.json': F(jd({'oauthAccount': OA}))}, ok(IDENT))
ident_resolve('b2-identity-resolve-foreign-dir', 'a foreign config dir reads its own .claude.json', {CC: '/opt/x'}, {'/opt/x/.claude.json': F(jd({'oauthAccount': OA}))}, ok(IDENT))
ident_resolve('b2-identity-resolve-relative-dir-null', 'a relative config dir has no global config path', {CC: 'rel'}, {}, ok(None))
ident_resolve('b2-identity-resolve-pool-null', 'a pool binding has no global config', {}, {'/home/p/proj/.claude-account': F('@team')}, ok(None), cwd='/home/p/proj')
ident_resolve('b2-identity-resolve-error-propagates', 'a resolve error is returned as is', {CC: '/home/p/.claude-work', MA: 'personal'}, WP, err('ENV_CONFLICT', None))
CUV = {'utilization': {'five_hour': {'utilization': 1, 'resets_at': '2026-10-06T15:00:00Z'}}, 'fetchedAtMs': FRESH}
ident_resolve('b2-usage-resolve-config-dir-home-claude', 'usage follows the same global config', {CC: '/home/p/.claude'},
              {'/home/p/.claude/.claude.json': F(jd({'cachedUsageUtilization': CUV})), '/home/p/.claude.json': F('{}')},
              uexp(iso_ms(FRESH), CUV, {'five_hour': {'utilization': 1, 'resetsAt': '2026-10-06T15:00:00Z'}}, False), op_name='usage')

CRED_FILE = '/home/p/.claude-work/.credentials.json'
FUT_MS = ms(NOWDT + datetime.timedelta(hours=5))
CREDS = {'claudeAiOauth': {'accessToken': 'at-1', 'refreshToken': 'rt-SECRET', 'expiresAt': FUT_MS, 'scopes': ['user:inference', 'user:profile'],
                           'subscriptionType': 'max', 'rateLimitTier': 'default_claude_max_5x'}}
def cr(id, desc, fs, expect, name='work', **kw):
    mk(id, desc, 'B2', op('credentials', name=name), expect, fs=fs, **kw)

CRES = {'source': 'file', 'path': CRED_FILE, 'accessToken': 'at-1', 'expiresAt': iso_ms(FUT_MS), 'expired': False,
        'scopes': ['user:inference', 'user:profile'], 'subscriptionType': 'max', 'rateLimitTier': 'default_claude_max_5x'}
cr('b2-credentials-basic', 'a valid token, never the refresh token', {CRED_FILE: F(jd(CREDS))}, ok(CRES))
cr('b2-credentials-expired', 'expiresAt in the past', {CRED_FILE: F(jd({'claudeAiOauth': dict(CREDS['claudeAiOauth'], expiresAt=ms(NOWDT) - 1000)}))},
   ok(dict(CRES, expired=True, expiresAt=iso_ms(ms(NOWDT) - 1000))))
cr('b2-credentials-expires-now', 'expiresAt equal to now is expired', {CRED_FILE: F(jd({'claudeAiOauth': dict(CREDS['claudeAiOauth'], expiresAt=ms(NOWDT))}))},
   ok(dict(CRES, expired=True, expiresAt=iso_ms(ms(NOWDT)))))
cr('b2-credentials-no-expiry', 'no expiresAt: not expired, expiresAt null', {CRED_FILE: F(jd({'claudeAiOauth': {'accessToken': 'at-1'}}))},
   ok({'source': 'file', 'path': CRED_FILE, 'accessToken': 'at-1', 'expiresAt': None, 'expired': False, 'scopes': [], 'subscriptionType': None, 'rateLimitTier': None}))
cr('b2-credentials-no-file', 'no credentials file: null', acct(wl, 'work'), ok(None))
cr('b2-credentials-bad-json', 'unparseable file: null', {CRED_FILE: F('{x')}, ok(None))
cr('b2-credentials-no-oauth', 'no claudeAiOauth object: null', {CRED_FILE: F('{}')}, ok(None))
cr('b2-credentials-no-access-token', 'no accessToken: null', {CRED_FILE: F(jd({'claudeAiOauth': {'refreshToken': 'r'}}))}, ok(None))
cr('b2-credentials-file-is-link', 'a link at .credentials.json is unreadable to claude, so null', {CRED_FILE: L('/data/c.json'), '/data/c.json': F(jd(CREDS))}, ok(None))
cr('b2-credentials-dir-is-link', 'a link on the account directory is fine', {'/home/p/.claude-work': L('/data/w'), '/data/w/.credentials.json': F(jd(CREDS))},
   ok(CRES))
cr('b2-credentials-default', 'default reads ~/.claude/.credentials.json', {'/home/p/.claude/.credentials.json': F(jd(CREDS))},
   ok(dict(CRES, path='/home/p/.claude/.credentials.json')), name='default')
cr('b2-credentials-darwin-reads-file-only', 'the keychain is never read, the fallback file is', {'/Users/p/.claude-work/.credentials.json': F(jd(CREDS))},
   ok(dict(CRES, path='/Users/p/.claude-work/.credentials.json')), plat='darwin')
cr('b2-credentials-not-found', 'unknown account', {}, err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'))
cr('b2-credentials-invalid-name', 'invalid name', {}, err('INVALID_NAME', None), name='W')

# ================= B3
# Process identifiers and markers below are synthetic.
DOM = 'linux:11111111111111111111111111111111:pid:[1234567890]'
UUID1 = '11111111-1111-4111-8111-111111111111'
def crec(pid, dom=DOM, start='12345678', **kw):
    d = {'pid': pid, 'sessionId': UUID1, 'cwd': '/home/p/proj', 'startedAt': 1759752000000, 'version': '2.1.292', 'kind': 'interactive',
         'entrypoint': 'cli', 'status': 'idle', 'updatedAt': 1759752100000}
    if dom is not None:
        d['pidDomain'] = dom
    if start is not None:
        d['procStart'] = start
    d.update(kw)
    return F(jd(d))

def csl(id, desc, files, procs, expect, domain=DOM, plat='linux', **kw):
    root = W_[plat]('.claude-work', 'sessions') + W_[plat].sep
    mk(id, desc, 'B3', op('live_sessions', name='work'), ok({'sessions': expect}), plat=plat,
       fs={root + k: v for k, v in files.items()}, processes=procs, domain=domain, **kw)

LV = [{'pid': 4242, 'sessionId': UUID1, 'status': 'live'}]
csl('b3-claude-linux-live', 'a record shaped like Claude Code writes on Linux', {'4242.json': crec(4242)}, {'4242': {'procStart': '12345678', 'pidDomain': DOM}}, LV)
csl('b3-claude-linux-start-mismatch-dead', 'pid reuse: field 22 differs', {'4242.json': crec(4242)}, {'4242': {'procStart': '12345679', 'pidDomain': DOM}},
    [{'pid': 4242, 'sessionId': UUID1, 'status': 'dead'}])
csl('b3-claude-linux-other-pid-namespace-unknown', 'same machine, other pid namespace: unknown', {'4242.json': crec(4242, dom='linux:11111111111111111111111111111111:pid:[1234567891]')},
    {'4242': {'procStart': '12345678', 'pidDomain': DOM}}, [{'pid': 4242, 'sessionId': UUID1, 'status': 'unknown'}])
csl('b3-claude-record-vs-hostname-domain-unknown', 'a caller that uses the host name as its domain sees every record as unknown', {'4242.json': crec(4242)},
    {'4242': {'procStart': '12345678', 'pidDomain': 'myhost'}}, [{'pid': 4242, 'sessionId': UUID1, 'status': 'unknown'}], domain='myhost')
csl('b3-claude-darwin-lstart-live', 'darwin: ps lstart string and the literal domain linux', {'77.json': crec(77, dom='linux', start='Tue Oct  6 11:00:00 2026')},
    {'77': {'procStart': 'Tue Oct  6 11:00:00 2026', 'pidDomain': 'linux'}}, [{'pid': 77, 'sessionId': UUID1, 'status': 'live'}], domain='linux', plat='darwin')
csl('b3-claude-darwin-lstart-whitespace-matters', 'the lstart string is compared exactly', {'77.json': crec(77, dom='linux', start='Tue Oct  6 11:00:00 2026')},
    {'77': {'procStart': 'Tue Oct 6 11:00:00 2026', 'pidDomain': 'linux'}}, [{'pid': 77, 'sessionId': UUID1, 'status': 'dead'}], domain='linux', plat='darwin')
csl('b3-claude-win32-filetime-live', 'win32: procStartFt instead of procStart, domain linux:<host>', {'9.json': crec(9, dom='linux:example-host', start=None, procStartFt='133737000000000000')},
    {'9': {'procStartFt': '133737000000000000', 'pidDomain': 'linux:example-host'}}, [{'pid': 9, 'sessionId': UUID1, 'status': 'live'}], domain='linux:example-host', plat='win32')
csl('b3-claude-win32-filetime-mismatch-dead', 'win32: a different creation time is another process', {'9.json': crec(9, dom='linux:example-host', start=None, procStartFt='133737000000000000')},
    {'9': {'procStartFt': '133737000000000001', 'pidDomain': 'linux:example-host'}}, [{'pid': 9, 'sessionId': UUID1, 'status': 'dead'}], domain='linux:example-host', plat='win32')
csl('b3-record-without-start-pid-exists-unknown', 'no procStart and no procStartFt but the pid exists: cannot prove it dead', {'5.json': crec(5, dom=None, start=None)},
    {'5': {'procStart': 'T1', 'pidDomain': 'host-1'}}, [{'pid': 5, 'sessionId': UUID1, 'status': 'unknown'}], domain='host-1')
csl('b3-record-without-start-no-pid-dead', 'no start fields and no such pid: dead', {'5.json': crec(5, dom=None, start=None)}, {},
    [{'pid': 5, 'sessionId': UUID1, 'status': 'dead'}], domain='host-1')
csl('b3-pid-file-names-canonical-only', 'only canonical decimal pid file names count', {
    '123.json': sess(123), '0123.json': sess(123), '\u0661\u0662.json': sess(12), '99999999999999999999.json': sess(1), '0.json': sess(1),
    '12345678901.json': sess(1), '1234567890.json': sess(1234567890), '+5.json': sess(5), '1e3.json': sess(1000)}, {},
    [{'pid': 123, 'sessionId': 's-123', 'status': 'dead'}, {'pid': 1234567890, 'sessionId': 's-1234567890', 'status': 'dead'}], domain='host-1')

# ================= B4
def ho(id, desc, expect, args=None, **kw):
    a = {'id': SID, 'from': 'a', 'to': 'b'}
    a.update(args or {})
    a = {k: v for k, v in a.items()}
    mk(id, desc, 'B4', op('handover_session', **a), expect, **kw)

BAD_IDS = [('dotdot', '..'), ('dotdot-slash', '../x'), ('dotdot-credentials', '../.credentials.json'), ('slash', 'a/b'), ('backslash', 'a\\b'),
           ('dot', '.'), ('empty', ''), ('absolute', '/etc/passwd'), ('leading-dot', '.hidden'), ('inner-dot', 'a.b'), ('space', 'a b'),
           ('newline', 'abc\n'), ('too-long', 'a' * 129), ('leading-hyphen', '-x'), ('non-ascii', 'caf\u00e9'), ('drive', 'C:x')]
CREDS_A = {A + '/.credentials.json': F('wc'), B + '/.credentials.json': F('pc')}
for nm, bad in BAD_IDS:
    ho('b4-handover-invalid-id-' + nm, 'session id %r is INVALID_SESSION_ID' % bad, err('INVALID_SESSION_ID', None), {'id': bad, 'overwrite': True},
       fs={**BASE, **src_files(), **CREDS_A}, expectFs={B + '/.credentials.json': {'type': 'file', 'content': 'pc'}, A + '/.credentials.json': {'type': 'file', 'content': 'wc'}})
ho('b4-handover-invalid-id-beats-invalid-account', 'the id is checked before the accounts', err('INVALID_SESSION_ID', None), {'id': '..', 'from': 'A'})
ho('b4-handover-id-128-chars-ok', 'a 128 character id is allowed', cpok({'copied': ['tasks/' + 'a' * 128 + '/t.json']}), {'id': 'a' * 128},
   fs={**BASE, A + '/tasks/' + 'a' * 128 + '/t.json': F('{}')})
ho('b4-handover-id-uuid-ok', 'a uuid id', cpok({'copied': ['tasks/%s/t.json' % UUID1]}), {'id': UUID1}, fs={**BASE, A + '/tasks/%s/t.json' % UUID1: F('{}')})
ho('b4-handover-id-underscore-hyphen-ok', 'underscore and hyphen are allowed after the first character', cpok({'copied': ['tasks/a_b-c/t.json']}), {'id': 'a_b-c'},
   fs={**BASE, A + '/tasks/a_b-c/t.json': F('{}')})
ho('b4-handover-same-account', 'from equal to is SAME_ACCOUNT, nothing is deleted', err('SAME_ACCOUNT', None), {'to': 'a', 'overwrite': True},
   fs={**BASE, **src_files()}, expectFs={A + '/tasks/sess-1/t.json': {'type': 'file', 'content': '{}'}})
ho('b4-handover-same-directory-via-alias', 'two names for one directory are the same account', err('SAME_ACCOUNT', None), {'overwrite': True},
   fs={A: D(), B: L(A), **src_files()}, expectFs={A + '/tasks/sess-1/t.json': {'type': 'file'}})
ho('b4-handover-default-and-slot-account-same', 'default and the slot account are the same account', err('SAME_ACCOUNT', None),
   {'from': 'default', 'to': 'work', 'overwrite': True}, fs={**managed(wl), '/home/p/.claude-work/tasks/sess-1/t.json': F('{}')})

SE = A + '/session-env/sess-1/'
ho('b4-handover-skips-links-and-special-files', 'only regular files and directories are copied; the rest is listed in skipped',
   ok({'copied': ['session-env/sess-1/env.sh', 'session-env/sess-1/sub/inner.txt'],
       'skipped': ['session-env/sess-1/dev', 'session-env/sess-1/dirlink', 'session-env/sess-1/fifo', 'session-env/sess-1/key', 'session-env/sess-1/sub/up']}),
   fs={**BASE, SE + 'env.sh': F('x'), SE + 'key': L('/home/p/.ssh/id_ed25519'), '/home/p/.ssh/id_ed25519': F('SECRET'), SE + 'dirlink': L('/home/p/.ssh'),
       SE + 'fifo': X(), SE + 'dev': DEV(), SE + 'sub/inner.txt': F('i'), SE + 'sub/up': L('../env.sh')},
   expectFs={B + '/session-env/sess-1/key': None, B + '/session-env/sess-1/dirlink': None, B + '/session-env/sess-1/fifo': None,
             B + '/session-env/sess-1/dev': None, B + '/session-env/sess-1/sub/up': None, B + '/session-env/sess-1/env.sh': {'type': 'file', 'content': 'x'}})
ho('b4-handover-top-level-link-only-not-found', 'a link where a session location should be does not count as the session', err('SESSION_NOT_FOUND', None),
   fs={**BASE, A + '/file-history/sess-1': L('/data/h'), '/data/h/v1': F('h')}, expectFs={B + '/file-history': None})
ho('b4-handover-top-level-link-skipped-with-others', 'a linked location is skipped and reported while real ones are copied',
   cpok({'copied': ['projects/-s1/sess-1.jsonl'], 'skipped': ['tasks/sess-1']}),
   fs={**BASE, A + '/projects/-s1/sess-1.jsonl': F('t'), A + '/tasks/sess-1': L('/data/t'), '/data/t/t.json': F('{}')},
   expectFs={B + '/tasks': None})
ho('b4-handover-overwrite-replaces-destination-link', 'overwrite removes a link at the destination and does not touch its target',
   cpok({'copied': ['tasks/sess-1/t.json']}), {'overwrite': True},
   fs={**BASE, A + '/tasks/sess-1/t.json': F('new'), B + '/tasks/sess-1': L('/data/x'), '/data/x/keep': F('keep')},
   expectFs={B + '/tasks/sess-1': {'type': 'dir'}, B + '/tasks/sess-1/t.json': {'content': 'new'}, '/data/x/keep': {'content': 'keep'}})
ho('b4-handover-exists-counts-links', 'a link at the destination counts as existing', err('SESSION_EXISTS', None),
   fs={**BASE, A + '/tasks/sess-1/t.json': F('new'), B + '/tasks/sess-1': L('/data/x')})
ho('b4-handover-unreadable-source-io-error', 'a file that cannot be read gives IO_ERROR and leaves the destination without a partial copy', err('IO_ERROR', A + '/tasks/sess-1/t.json'),
   fs={**BASE, A + '/projects/-s1/sess-1.jsonl': F('t'), A + '/tasks/sess-1/t.json': F('{}', unreadable=True)},
   expectFs={B + '/projects': None, B + '/tasks': None})
ho('b4-handover-overwrite-failure-keeps-destination', 'with overwrite a failed copy leaves the old destination intact', err('IO_ERROR', A + '/tasks/sess-1/t.json'), {'overwrite': True},
   fs={**BASE, A + '/projects/-s1/sess-1.jsonl': F('new'), A + '/tasks/sess-1/t.json': F('{}', unreadable=True), B + '/tasks/sess-1/old.json': F('old')},
   expectFs={B + '/tasks/sess-1/old.json': {'type': 'file', 'content': 'old'}, B + '/projects': None})
ho('b4-handover-unknown-no-start-refused', 'a record without start fields whose pid exists blocks', err('SESSION_LIVE', None),
   fs={**BASE, **src_files(), A + '/sessions/200.json': crec(200, dom=None, start=None, sessionId=SID)}, processes={'200': {'procStart': 'x', 'pidDomain': 'host-1'}})
ho('b4-handover-live-not-forceable', 'force never overrides a live session', err('SESSION_LIVE', None), {'force': True},
   fs={**BASE, **src_files(), **{A + '/sessions/200.json': sess(200, sid=SID)}}, processes={'200': {'procStart': 'T1', 'pidDomain': 'host-1'}})
ho('b4-handover-claude-record-live-refused', 'a Claude-shaped live record blocks', err('SESSION_LIVE', None),
   fs={**BASE, **src_files(), A + '/sessions/4242.json': crec(4242, sessionId=SID)}, processes={'4242': {'procStart': '12345678', 'pidDomain': DOM}}, domain=DOM)
ho('b4-handover-claude-record-dead-ok', 'a Claude-shaped record of a dead process does not block', cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), A + '/sessions/4242.json': crec(4242, sessionId=SID)}, processes={}, domain=DOM)
ho('b4-handover-claude-record-other-session-ok', 'a live Claude record for another session id does not block', cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), A + '/sessions/4242.json': crec(4242, sessionId='another')}, processes={'4242': {'procStart': '12345678', 'pidDomain': DOM}}, domain=DOM)
ho('b4-handover-unknown-other-session-ok', 'an unknown record for another session id does not block', cpok({'copied': FULL_COPIED}),
   fs={**BASE, **src_files(), A + '/sessions/200.json': sess(200, sid='another', dom='other-host')})

# ================= B5
def mkl(id, desc, expect, entry=None, fs=None, **kw):
    mk(id, desc, 'B5', op('mark_limited', name='work', entry=entry or E1), expect, fs=fs, **kw)

CLEAN = {SP + '.lock': None}
mkl('b5-mark-version-2-refused', 'a state file with another version is never overwritten', err('STATE_FILE_INVALID', SP),
    fs={SP: F(jd({'version': 2, 'limits': []}))}, expectFs={SP: {'contentJson': {'version': 2, 'limits': []}}, SP + '.lock': None})
mkl('b5-mark-version-missing-refused', 'a state file without version is refused', err('STATE_FILE_INVALID', SP), fs={SP: F(jd({'limits': []}))})
mkl('b5-mark-limits-not-array-refused', 'limits that is not an array is refused', err('STATE_FILE_INVALID', SP), fs={SP: F(jd({'version': 1, 'limits': {}}))})
mkl('b5-mark-top-level-array-refused', 'a top-level array is refused', err('STATE_FILE_INVALID', SP), fs={SP: F('[]')})
mkl('b5-mark-state-is-directory-refused', 'a directory in place of the file is refused', err('STATE_FILE_INVALID', SP), fs={SP: D()})
mkl('b5-mark-state-unreadable-refused', 'an unreadable state file is refused', err('STATE_FILE_INVALID', SP), fs={SP: F(jd({'version': 1}), unreadable=True)})
mkl('b5-mark-state-without-limits-key', 'version 1 without a limits key is an empty list', ok({'limits': [stored(E1)]}), fs={SP: F(jd({'version': 1}))})
mkl('b5-mark-dangling-state-link-is-fresh', 'a link whose target is missing counts as no file and is written through', ok({'limits': [stored(E1)]}),
    fs={SP: L('/data/state.json'), '/data': D()}, expectFs={SP: {'type': 'symlink'}, '/data/state.json': {'type': 'file', 'contentJson': {'version': 1, 'limits': [stored(E1)]}}})
FOREIGN = {'window': 'weekly', 'model': None, 'until': FUT, 'note': 'from another tool'}
mkl('b5-mark-preserves-foreign-entries-verbatim', 'entries written by others keep every key; nothing is added or removed', ok({'limits': [FOREIGN, 'junk', stored(E1)]}),
    fs={SP: F(jd({'version': 1, 'limits': [FOREIGN, 'junk']}))},
    expectFs={SP: {'contentJson': {'version': 1, 'limits': [FOREIGN, 'junk', stored(E1)]}}})
mkl('b5-mark-keeps-entry-with-unparseable-until', 'an entry whose until cannot be read is kept as it is', ok({'limits': [{'window': 'x', 'until': 'soon'}, stored(E1)]}),
    fs={SP: F(jd({'version': 1, 'limits': [{'window': 'x', 'until': 'soon'}]}))})
mkl('b5-mark-offset-until-compared-as-instant', 'an offset until is an instant: 15:00+02:00 is earlier than 14:00Z', ok({'limits': [stored(E1, by='old', at=OLD)]}),
    entry=dict(E1, until='2026-10-09T15:00:00+02:00', updatedBy='new'), fs={SP: state(stored(E1, by='old', at=OLD))})
mkl('b5-mark-offset-until-stored-as-given', 'a later offset until replaces and is stored as given', ok({'limits': [stored(dict(E1, until='2026-10-09T17:00:00+02:00'))]}),
    entry=dict(E1, until='2026-10-09T17:00:00+02:00'), fs={SP: state(stored(E1, by='old', at=OLD))})
mkl('b5-mark-fractional-until-ok', 'fractional seconds are allowed', ok({'limits': [stored(dict(E1, until='2026-10-09T14:00:00.5Z'))]}),
    entry=dict(E1, until='2026-10-09T14:00:00.5Z'), fs=acct(wl, 'work'))
for nm, until in [('word', 'tomorrow'), ('lower-z', '2026-10-09T14:00:00z'), ('lower-t', '2026-10-09t14:00:00Z'), ('space', '2026-10-09 14:00:00Z'),
                  ('no-zone', '2026-10-09T14:00:00'), ('month-13', '2026-13-09T14:00:00Z'), ('feb-30', '2026-02-30T14:00:00Z'), ('hour-24', '2026-10-09T24:00:00Z'),
                  ('date-only', '2026-10-09'), ('bad-offset', '2026-10-09T14:00:00+25:00'), ('empty', ''), ('leap-second', '2026-10-09T14:00:60Z')]:
    mkl('b5-mark-invalid-until-' + nm, 'until %r is INVALID_ENTRY' % until, err('INVALID_ENTRY', None), entry=dict(E1, until=until), fs=acct(wl, 'work'),
        expectFs={SP: None, SP + '.lock': None})
mkl('b5-mark-invalid-window-empty', 'an empty window', err('INVALID_ENTRY', None), entry=dict(E1, window=''), fs=acct(wl, 'work'))
mkl('b5-mark-invalid-model-empty', 'an empty model string (use null)', err('INVALID_ENTRY', None), entry=dict(E1, model=''), fs=acct(wl, 'work'))
mkl('b5-mark-invalid-until-not-string', 'until must be a string', err('INVALID_ENTRY', None), entry=dict(E1, until=5), fs=acct(wl, 'work'))
mkl('b5-mark-invalid-entry-checked-after-account', 'the account gate comes before entry validation', err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), entry=dict(E1, until='x'))
mkl('b5-mark-symlink-lock-named-after-link', 'the lock is named after the path as given, not the link target', err('LOCK_BUSY', SP + '.lock'),
    fs={SP: L('/data/state.json'), '/data/state.json': state(), SP + '.lock': D()}, expectFs={SP + '.lock': {'type': 'dir'}})
mkl('b5-mark-symlink-target-lock-does-not-block', 'a lock next to the link target is not our lock', ok({'limits': [stored(E1)]}),
    fs={SP: L('/data/state.json'), '/data/state.json': state(), '/data/state.json.lock': D()}, expectFs={'/data/state.json.lock': {'type': 'dir'}, SP + '.lock': None})
mk('b5-clear-unparseable-refused', 'clear on an unparseable state file is refused', 'B5', op('clear_limited', name='work', window='seven_day', model='opus'),
   err('STATE_FILE_INVALID', SP), fs={SP: F('nope')}, expectFs={SP: {'content': 'nope'}, SP + '.lock': None})
mk('b5-clear-version-2-refused', 'clear on a version 2 file is refused', 'B5', op('clear_limited', name='work', window='seven_day', model='opus'),
   err('STATE_FILE_INVALID', SP), fs={SP: F(jd({'version': 2, 'limits': []}))}, expectFs={SP: {'contentJson': {'version': 2, 'limits': []}}})
mk('b5-clear-keeps-foreign-entries', 'clear removes only the named key and keeps other entries verbatim', 'B5', op('clear_limited', name='work', window='seven_day', model='opus'),
   ok({'limits': [FOREIGN]}), fs={SP: F(jd({'version': 1, 'limits': [FOREIGN, stored(E1, at=OLD)]}))})

def avl(id, desc, content, expect, model=None, **kw):
    a = {'name': 'work'}
    if model:
        a['model'] = model
    mk(id, desc, 'B5', op('available', **a), ok({'available': expect}), fs={SP: content}, **kw)

avl('b5-available-version-2-reads-as-empty', 'reads treat a file they do not understand as empty', F(jd({'version': 2, 'limits': [stored(E2)]})), True)
avl('b5-available-limits-not-array', 'limits that is not an array reads as empty', F(jd({'version': 1, 'limits': 'x'})), True)
avl('b5-available-ignores-malformed-entries', 'junk and entries without a usable until are ignored', F(jd({'version': 1, 'limits': ['x', {'window': 'a'}, {'until': 'soon', 'model': None}, stored(E2)]})), False)
avl('b5-available-offset-until', 'an offset until is an instant', F(jd({'version': 1, 'limits': [dict(E2, until='2026-10-06T23:00:00+09:00')]})), False)
avl('b5-available-offset-until-past', 'an offset until in the past', F(jd({'version': 1, 'limits': [dict(E2, until='2026-10-06T20:00:00+09:00', model='opus')]})), True, model='sonnet')
avl('b5-available-offset-until-equals-now', 'until equal to now by another offset is not > now', F(jd({'version': 1, 'limits': [dict(E2, until='2026-10-06T14:00:00+02:00')]})), True)
avl('b5-available-entry-without-model-key-applies-to-all', 'a missing model key is the all-models key', F(jd({'version': 1, 'limits': [{'window': 'w', 'until': FUT}]})), False, model='opus')

# ================= B6
def pf(id, desc, cands, expect, name='pick_from', fs=None, **args):
    mk(id, desc, 'B6', op(name, candidates=cands, **args), ok({'account': expect}) if not isinstance(expect, dict) else expect,
       fs={**acct(wl, 'a', 'b', 'c'), **(fs or {})})

pf('b6-pick-from-first', 'the first candidate when it is available', ['b', 'a', 'c'], 'b')
pf('b6-pick-from-skips-limited', 'a limited candidate is skipped, order is the list order', ['b', 'a', 'c'], 'a', fs=lim('b'))
pf('b6-pick-from-all-limited', 'null when every candidate is limited', ['a', 'b'], None, fs={**lim('a'), **lim('b')})
pf('b6-pick-from-empty', 'an empty list gives null', [], None)
pf('b6-pick-from-model-aware', 'limited for opus only: still first for sonnet', ['a', 'b'], 'a', fs=lim('a', model='opus'), model='sonnet')
pf('b6-pick-from-model-aware-opus', 'limited for opus: skipped when opus is asked', ['a', 'b'], 'b', fs=lim('a', model='opus'), model='opus')
pf('b6-pick-from-expired-limit', 'an expired limit does not count', ['a', 'b'], 'a', fs=lim('a', until=OLD))
pf('b6-pick-from-default', 'default is a candidate like any other', ['default', 'a'], 'default')
pf('b6-pick-from-default-limited', 'default limited via ~/.claude state', ['default', 'a'], 'a',
   fs={'/home/p/.claude/.multi-account-state.json': state({'window': 'w', 'model': None, 'until': FUT})})
pf('b6-pick-from-invalid-name', 'every candidate is validated', ['a', 'B'], err('INVALID_NAME', None), fs=None)
pf('b6-pick-from-missing-account', 'a missing candidate is skipped as unavailable', ['ghost', 'a'], 'a')
pf('b6-pick-from-dangling-account', 'a dangling candidate is skipped as unavailable', ['gone', 'a'], 'a', fs={'/home/p/.claude-gone': L('/mnt/gone')})
pf('b6-pick-from-only-missing', 'only unavailable candidates: null', ['ghost'], None)
pf('b6-pick-from-missing-after-available', 'a missing candidate after an available one is no error', ['a', 'ghost'], 'a')
pf('b6-pick-from-duplicates-allowed', 'duplicates in a caller list are not an error', ['a', 'a', 'b'], 'b', fs=lim('a'))
pf('b6-next-from-after-current', 'the next available after current', ['a', 'b', 'c'], 'b', name='next_from', current='a')
pf('b6-next-from-wraps', 'wraps from the last to the first', ['a', 'b', 'c'], 'a', name='next_from', current='c')
pf('b6-next-from-skips-limited', 'skips limited candidates', ['a', 'b', 'c'], 'c', name='next_from', current='a', fs=lim('b'))
pf('b6-next-from-current-limited', 'current itself may be limited', ['a', 'b', 'c'], 'b', name='next_from', current='a', fs=lim('a'))
pf('b6-next-from-only-current-available', 'when only current is available, current is returned', ['a', 'b', 'c'], 'b', name='next_from', current='b', fs={**lim('a'), **lim('c')})
pf('b6-next-from-none-available', 'null when nothing is available', ['a', 'b'], None, name='next_from', current='a', fs={**lim('a'), **lim('b')})
pf('b6-next-from-current-not-listed', 'a current outside the list starts from the top', ['b', 'c'], 'b', name='next_from', current='a')
pf('b6-next-from-model-aware', 'model-aware', ['a', 'b', 'c'], 'c', name='next_from', current='a', model='opus', fs=lim('b', model='opus'))
pf('b6-next-from-empty', 'empty list: null', [], None, name='next_from', current='a')
pf('b6-next-from-invalid-name', 'invalid candidate', ['a', 'X'], err('INVALID_NAME', None), name='next_from', current='a')
pf('b6-next-from-missing-account', 'a missing candidate is skipped', ['a', 'ghost', 'b'], 'b', name='next_from', current='a')
pf('b6-next-from-missing-wraps-to-current', 'only current is usable: current is returned', ['a', 'ghost'], 'a', name='next_from', current='a')

SLOTPOOL = {**managed(wl), '/home/p/.claude-work/.multi-account.json': F(jd({'version': 1, 'pool': 'p'}))}
mk('b6-pick-alias-named-represents', 'default is the slot alias of work: the named account is the member, default is not', 'B6', op('pick', pool='p'),
   ok({'account': 'work'}), fs=SLOTPOOL)
mk('b6-next-alias-named-represents', 'next sees one member for the group', 'B6', op('next', pool='p', current='work'), ok({'account': 'work'}), fs=SLOTPOOL)
def prio(id, desc, p1, p2, expect, invalid=None):
    fsd = {**poolspec('a', 'p', 0), '/home/p/.claude-b/.multi-account.json': F('{"version": 1, "pool": "p", "priority": %s}' % p2),
           '/home/p/.claude-a/.multi-account.json': F('{"version": 1, "pool": "p", "priority": %s}' % p1)}
    mk(id, desc, ['B6', 'A3'], op('pick', pool='p'), expect if invalid else ok({'account': expect}), fs=fsd)
prio('b6-pick-priority-max-safe-beats-next', 'priorities near 2^53 compare exactly', 9007199254740990, 9007199254740991, 'b')
prio('b6-pick-priority-2pow53-invalid', 'priority 2^53 makes the spec file invalid', 0, 9007199254740992,
     err('SPEC_FILE_INVALID', '/home/p/.claude-b/.multi-account.json'), invalid=True)
prio('b6-pick-priority-fraction-invalid', 'a fractional priority makes the spec file invalid', 0, 1.5,
     err('SPEC_FILE_INVALID', '/home/p/.claude-b/.multi-account.json'), invalid=True)
prio('b6-pick-priority-overflow-invalid', 'priority 1e400 makes the spec file invalid', 0, '1e400',
     err('SPEC_FILE_INVALID', '/home/p/.claude-b/.multi-account.json'), invalid=True)

# ================= B7
mk('b7-slot-broken-link-to-claude-default', '~/.claude linked to ~/.claude-default is not a slot account', 'B7', op('slot'), ok({'state': 'broken', 'name': None}),
   fs=managed(wl, 'default'))
mk('b7-slot-broken-claude-json-target-is-dir', 'the .claude.json target must be a file', 'B7', op('slot'), ok({'state': 'broken', 'name': None}),
   fs={k: v for k, v in managed(wl).items() if k != '/home/p/.claude-work/.claude.json'} | {'/home/p/.claude-work/.claude.json': D()})
mk('b7-slot-managed-no-claude-json-in-account', 'both links in place and the account has no .claude.json yet', 'B7', op('slot'), ok({'state': 'managed', 'name': 'work'}),
   fs={'/home/p/.claude': L('/home/p/.claude-work'), '/home/p/.claude.json': L('/home/p/.claude-work/.claude.json'), '/home/p/.claude-work': D()})
mk('b7-slot-unmanaged-claude-unreadable-dir', 'a real but unreadable ~/.claude directory is unmanaged', 'B7', op('slot'), ok({'state': 'unmanaged', 'name': None}),
   fs={'/home/p/.claude': D(unreadable=True)})

CR_FILES = {'/home/p/.claude/.credentials.json': F('cred')}
mk('b7-adopt-default-invalid-name', 'default cannot be adopted into', 'B7', AD('default'), err('INVALID_NAME', None), fs=unmanaged(wl), expectFs={'/home/p/.claude': {'type': 'dir'}})
mk('b7-adopt-no-global-json', 'adopt without ~/.claude.json links to the future file and reports managed', 'B7', AD(), ok({'state': 'managed', 'name': 'work'}),
   fs={'/home/p/.claude': D(), **CR_FILES},
   expectFs={'/home/p/.claude-work/.credentials.json': {'content': 'cred'}, '/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'},
             '/home/p/.claude.json': {'type': 'symlink', 'target': '/home/p/.claude-work/.claude.json'}, '/home/p/.claude-slot.lock': None})
mk('b7-adopt-missing-claude-dir', 'with no ~/.claude at all adopt creates the account directory', 'B7', AD(), ok({'state': 'managed', 'name': 'work'}), fs={},
   expectFs={'/home/p/.claude-work': {'type': 'dir', 'mode': '0700'}, '/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'},
             '/home/p/.claude.json': {'type': 'symlink', 'target': '/home/p/.claude-work/.claude.json'}})
mk('b7-adopt-missing-claude-dir-moves-global-json', 'no ~/.claude but a ~/.claude.json: the file is moved in', 'B7', AD(), ok({'state': 'managed', 'name': 'work'}),
   fs={'/home/p/.claude.json': F('{"a":1}')}, expectFs={'/home/p/.claude-work/.claude.json': {'type': 'file', 'content': '{"a":1}'}})
mk('b7-adopt-conflict-inner-claude-json', 'both ~/.claude.json and ~/.claude/.claude.json exist: refuse, change nothing', 'B7', AD(),
   err('SLOT_CONFLICT', '/home/p/.claude/.claude.json'), fs=unmanaged(wl, extra={'/home/p/.claude/.claude.json': F('{"inner":1}')}),
   expectFs={'/home/p/.claude/.claude.json': {'content': '{"inner":1}'}, '/home/p/.claude.json': {'content': '{"a":1}'}, '/home/p/.claude-work': None, '/home/p/.claude-slot.lock': None})
mk('b7-adopt-inner-claude-json-only-ok', 'only the inner .claude.json exists: it stays and the link points at it', 'B7', AD(), ok({'state': 'managed', 'name': 'work'}),
   fs={'/home/p/.claude/.claude.json': F('{"inner":1}')}, expectFs={'/home/p/.claude-work/.claude.json': {'content': '{"inner":1}'}})
mk('b7-adopt-global-json-is-symlink-refused', '~/.claude.json that is a link would make a chain', 'B7', AD(), err('SLOT_TARGET_INVALID', '/home/p/.claude.json'),
   fs={'/home/p/.claude': D(), '/home/p/.claude.json': L('/data/dot.json'), '/data/dot.json': F('{}')}, expectFs={'/home/p/.claude': {'type': 'dir'}, '/home/p/.claude-work': None})
mk('b7-adopt-credentials-link-refused', 'a linked .credentials.json would make the slot broken', 'B7', AD(), err('SLOT_TARGET_INVALID', '/home/p/.claude/.credentials.json'),
   fs={'/home/p/.claude/.credentials.json': L('/data/c'), '/data/c': F('c')}, expectFs={'/home/p/.claude-work': None})
ADS = {'/home/p/.claude/sessions/55.json': sess(55, sid='live-default')}
mk('b7-adopt-live-session-refused', 'a live session in ~/.claude blocks adopt', 'B7', AD(), err('SESSION_LIVE', None), fs=unmanaged(wl, extra=ADS),
   processes={'55': {'procStart': 'T1', 'pidDomain': 'host-1'}}, expectFs={'/home/p/.claude': {'type': 'dir'}, '/home/p/.claude-work': None, '/home/p/.claude-slot.lock': None})
mk('b7-adopt-unknown-session-refused', 'an unknown session blocks adopt', 'B7', AD(), err('SESSION_LIVE', None),
   fs=unmanaged(wl, extra={'/home/p/.claude/sessions/55.json': sess(55, dom='other-host')}), expectFs={'/home/p/.claude': {'type': 'dir'}})
mk('b7-adopt-unknown-session-force-ok', 'force lets an unknown session through', 'B7', op('adopt', name='work', force=True), ok({'state': 'managed', 'name': 'work'}),
   fs=unmanaged(wl, extra={'/home/p/.claude/sessions/55.json': sess(55, dom='other-host')}), expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})
mk('b7-adopt-live-not-forceable', 'force never overrides a live session', 'B7', op('adopt', name='work', force=True), err('SESSION_LIVE', None),
   fs=unmanaged(wl, extra=ADS), processes={'55': {'procStart': 'T1', 'pidDomain': 'host-1'}})
mk('b7-adopt-dead-session-ok', 'a dead session does not block', 'B7', AD(), ok({'state': 'managed', 'name': 'work'}), fs=unmanaged(wl, extra=ADS),
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})
mk('b7-adopt-claude-record-live-refused', 'a Claude-shaped live record blocks adopt', 'B7', AD(), err('SESSION_LIVE', None),
   fs=unmanaged(wl, extra={'/home/p/.claude/sessions/4242.json': crec(4242)}), processes={'4242': {'procStart': '12345678', 'pidDomain': DOM}}, domain=DOM)
mk('b7-adopt-lock-busy', 'a fresh slot lock blocks adopt', 'B7', AD(), err('LOCK_BUSY', '/home/p/.claude-slot.lock'),
   fs=unmanaged(wl, extra={'/home/p/.claude-slot.lock': D()}), expectFs={'/home/p/.claude': {'type': 'dir'}, '/home/p/.claude-slot.lock': {'type': 'dir'}})
mk('b7-adopt-stale-lock-ok', 'a stale slot lock is taken over by adopt', 'B7', AD(), ok({'state': 'managed', 'name': 'work'}),
   fs=unmanaged(wl, extra={'/home/p/.claude-slot.lock': D(mtime='2026-10-06T11:00:00Z')}), expectFs={'/home/p/.claude-slot.lock': None})

mk('b7-activate-default-invalid-name', 'activate takes a named account only', 'B7', AC('default'), err('INVALID_NAME', None), fs=M2,
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})
mk('b7-activate-relocated-account', 'a relocated target (its dir is a link) is accepted', 'B7', AC('personal'), ok({'state': 'managed', 'name': 'personal'}),
   fs={**M2, '/home/p/.claude-personal': L('/data/p'), '/data/p/.claude.json': F('{}'), '/data/p/.credentials.json': F('pc')} if False else
      {**{k: v for k, v in M2.items() if not k.startswith('/home/p/.claude-personal')}, '/home/p/.claude-personal': L('/data/p'), '/data/p/.claude.json': F('{}')})
mk('b7-activate-account-without-claude-json', 'a target without .claude.json gets a dangling link and is managed', 'B7', AC('personal'),
   ok({'state': 'managed', 'name': 'personal'}), fs={**{k: v for k, v in M2.items() if k != '/home/p/.claude-personal/.claude.json'}, '/home/p/.claude-personal': D()},
   expectFs={'/home/p/.claude.json': {'type': 'symlink', 'target': '/home/p/.claude-personal/.claude.json'}})
mk('b7-activate-credentials-link-refused', 'a target with a linked .credentials.json is refused', 'B7', AC('personal'),
   err('SLOT_TARGET_INVALID', '/home/p/.claude-personal/.credentials.json'),
   fs={**{k: v for k, v in M2.items() if k != '/home/p/.claude-personal/.credentials.json'}, '/home/p/.claude-personal/.credentials.json': L('/data/c'), '/data/c': F('c')},
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}, '/home/p/.claude-slot.lock': None})
mk('b7-activate-claude-json-link-refused', 'a target whose .claude.json is a link would make a chain', 'B7', AC('personal'),
   err('SLOT_TARGET_INVALID', '/home/p/.claude-personal/.claude.json'),
   fs={**{k: v for k, v in M2.items() if k != '/home/p/.claude-personal/.claude.json'}, '/home/p/.claude-personal/.claude.json': L('/data/j'), '/data/j': F('{}')},
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}})
mk('b7-activate-claude-record-live-refused', 'a Claude-shaped live record in the slot account blocks', 'B7', AC('personal'), err('SESSION_LIVE', None),
   fs={**M2, '/home/p/.claude-work/sessions/4242.json': crec(4242)}, processes={'4242': {'procStart': '12345678', 'pidDomain': DOM}}, domain=DOM,
   expectFs={'/home/p/.claude': {'type': 'symlink', 'target': '/home/p/.claude-work'}, '/home/p/.claude-slot.lock': None})
mk('b7-activate-live-not-forceable', 'force never overrides a live session', 'B7', op('activate', name='personal', force=True), err('SESSION_LIVE', None),
   fs={**M2, **{'/home/p/.claude-work/sessions/300.json': sess(300)}}, processes={'300': {'procStart': 'T1', 'pidDomain': 'host-1'}})
mk('b7-activate-unknown-no-start-refused', 'a record without start fields whose pid exists blocks', 'B7', AC('personal'), err('SESSION_LIVE', None),
   fs={**M2, '/home/p/.claude-work/sessions/300.json': crec(300, dom=None, start=None)}, processes={'300': {'procStart': 'x', 'pidDomain': 'host-1'}})
mk('b7-activate-win32-remove-then-create', 'win32 replaces the junction by removing and re-creating it, the file link by rename', 'B7', AC('personal'),
   ok({'state': 'managed', 'name': 'personal'}), plat='win32',
   fs=managed(ww, extra={'C:\\Users\\p\\.claude-personal\\.claude.json': F('{}')}),
   expectFs={'C:\\Users\\p\\.claude': {'type': 'junction', 'target': 'C:\\Users\\p\\.claude-personal'},
             'C:\\Users\\p\\.claude.json': {'type': 'symlink', 'target': 'C:\\Users\\p\\.claude-personal\\.claude.json'}, 'C:\\Users\\p\\.claude-slot.lock': None})
mk('b7-discover-alias-two-named-and-default', 'with default in the slot and a second link to the account, the first name represents the group', ['B7', 'A2 Relocation'],
   op('discover'), disc([dacc(wl, hg=True, alias='abc'), nacc(wl, 'abc', hg=True), nacc(wl, 'work', hg=True, alias='abc')]),
   fs={**managed(wl), '/home/p/.claude-abc': L('/home/p/.claude-work')})


# ================= v0.2.1
# B4: linked parents, union of slugs
ho('b4-handover-exists-other-project-in-destination', 'the same id under another project in the destination counts as existing', err('SESSION_EXISTS', None),
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('a'), B + '/projects/-y/sess-1.jsonl': F('b')},
   expectFs={B + '/projects/-x': None, B + '/projects/-y/sess-1.jsonl': {'content': 'b'}})
ho('b4-handover-overwrite-other-project-in-destination', 'overwrite removes the id under every destination project, then copies', cpok({'copied': ['projects/-x/sess-1.jsonl']}), {'overwrite': True},
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('a'), B + '/projects/-y/sess-1.jsonl': F('b'), B + '/projects/-y/keep.jsonl': F('k')},
   expectFs={B + '/projects/-x/sess-1.jsonl': {'content': 'a'}, B + '/projects/-y/sess-1.jsonl': None, B + '/projects/-y/keep.jsonl': {'content': 'k'}})
ho('b4-handover-source-linked-project-skipped', 'a linked source project folder is not read and is reported in skipped', cpok({'copied': ['tasks/sess-1/t.json'], 'skipped': ['projects/-x']}),
   fs={**BASE, A + '/projects/-x': L('/data/x'), '/data/x/sess-1.jsonl': F('secret'), A + '/tasks/sess-1/t.json': F('{}')},
   expectFs={B + '/projects': None, B + '/tasks/sess-1/t.json': {'type': 'file'}})
ho('b4-handover-source-linked-project-only-not-found', 'only a linked project folder holds the id: SESSION_NOT_FOUND', err('SESSION_NOT_FOUND', None),
   fs={**BASE, A + '/projects/-x': L('/data/x'), '/data/x/sess-1.jsonl': F('secret')}, expectFs={B + '/projects': None})
ho('b4-handover-source-linked-tasks-dir-skipped', 'a linked tasks directory is skipped as a whole', cpok({'copied': ['file-history/sess-1/v1'], 'skipped': ['tasks']}),
   fs={**BASE, A + '/file-history/sess-1/v1': F('h'), A + '/tasks': L('/data/t'), '/data/t/sess-1/t.json': F('{}')}, expectFs={B + '/tasks': None})
ho('b4-handover-destination-linked-project-not-written', 'a linked destination project folder blocks the handover, nothing is written through', err('DESTINATION_BLOCKED', B + '/projects/-x'),
   {'overwrite': True},
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('new'), A + '/tasks/sess-1/t.json': F('{}'), B + '/projects/-x': L('/data/x'), '/data/x/sess-1.jsonl': F('outside')},
   expectFs={'/data/x/sess-1.jsonl': {'content': 'outside'}, B + '/projects/-x': {'type': 'symlink', 'target': '/data/x'}, B + '/tasks': None})
ho('b4-handover-destination-linked-project-not-existing', 'a linked destination project folder is DESTINATION_BLOCKED, not SESSION_EXISTS and not success', err('DESTINATION_BLOCKED', B + '/projects/-x'),
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('new'), A + '/tasks/sess-1/t.json': F('{}'), B + '/projects/-x': L('/data/x'), '/data/x/sess-1.jsonl': F('outside')})
ho('b4-handover-destination-linked-tasks-dir', 'a linked destination tasks directory blocks the handover', err('DESTINATION_BLOCKED', B + '/tasks'),
   fs={**BASE, A + '/file-history/sess-1/v1': F('h'), A + '/tasks/sess-1/t.json': F('{}'), B + '/tasks': L('/data/t'), '/data/t': D()},
   expectFs={'/data/t/sess-1': None, B + '/file-history': None})

# B3: lookup errors, empty domain parts
csl('b3-lookup-error-is-unknown', 'a process lookup that failed is unknown, never dead', {'4242.json': crec(4242)}, {'4242': {'pidDomain': DOM, 'lookupError': True}},
    [{'pid': 4242, 'sessionId': UUID1, 'status': 'unknown'}])
csl('b3-lookup-error-other-domain-still-unknown', 'a foreign domain is unknown whatever the lookup says', {'4242.json': crec(4242, dom='other')}, {'4242': {'pidDomain': DOM, 'lookupError': True}},
    [{'pid': 4242, 'sessionId': UUID1, 'status': 'unknown'}])
csl('b3-no-machine-id-domain-live', 'a caller without a machine id has the domain linux::pid:[...] and matches Claude Code records', {'4242.json': crec(4242, dom='linux::pid:[1234567890]')},
    {'4242': {'procStart': '12345678', 'pidDomain': 'linux::pid:[1234567890]'}}, LV, domain='linux::pid:[1234567890]')
csl('b3-literal-linux-domain-differs-from-empty-parts', 'the literal linux is not the domain of a record written on Linux', {'4242.json': crec(4242, dom='linux::pid:[1234567890]')},
    {'4242': {'procStart': '12345678', 'pidDomain': 'linux'}}, [{'pid': 4242, 'sessionId': UUID1, 'status': 'unknown'}], domain='linux')
mk('b4-handover-lookup-error-refused', 'a lookup error in the source counts as unknown and blocks', 'B4', HO, err('SESSION_LIVE', None),
   fs={**BASE, **src_files(), A + '/sessions/4242.json': crec(4242, sessionId=SID)}, processes={'4242': {'pidDomain': DOM, 'lookupError': True}}, domain=DOM)
mk('b7-activate-lookup-error-refused', 'a lookup error in the slot account blocks activate', 'B7', AC('personal'), err('SESSION_LIVE', None),
   fs={**M2, '/home/p/.claude-work/sessions/4242.json': crec(4242)}, processes={'4242': {'pidDomain': DOM, 'lookupError': True}}, domain=DOM)

# B6: alias-aware lists
def pfa(id, desc, cands, expect, name='next_from', fs=None, **args):
    mk(id, desc, ['B6', 'A2 Relocation'], op(name, candidates=cands, **args), ok({'account': expect}), fs={**managed(wl), **acct(wl, 'personal'), **(fs or {})})
pfa('b6-next-from-alias-current-default', 'with the slot on work, current default is work: the next one is personal', ['work', 'personal'], 'personal', current='default')
pfa('b6-next-from-alias-current-default-second', 'current default matches the second candidate', ['personal', 'work'], 'personal', current='default')
pfa('b6-next-from-alias-current-default-only-self', 'when only the same account is available, it is returned', ['work', 'personal'], 'work', current='default', fs=lim('personal'))
pfa('b6-next-from-alias-skips-own-aliases', 'a candidate that is the same account as current is skipped', ['work', 'default', 'personal'], 'personal', current='work')
pfa('b6-next-from-alias-current-listed-as-default', 'the list names default and current is work', ['default', 'personal'], 'personal', current='work')
pfa('b6-pick-from-alias-limited-through-link', 'default shares the slot account state, so a limited work makes default unavailable', ['default', 'personal'], 'personal', name='pick_from',
    fs=lim('work'))


# ================= v0.2.2: S7 and new ops
ho('b4-handover-destination-linked-projects-dir', 'a linked destination projects directory blocks', err('DESTINATION_BLOCKED', B + '/projects'),
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('a'), B + '/projects': L('/data/p'), '/data/p': D()}, expectFs={'/data/p/-x': None})
ho('b4-handover-destination-linked-unrelated-parent-ok', 'a linked destination parent with nothing to write there does not block and is not reported', cpok({'copied': ['tasks/sess-1/t.json']}),
   fs={**BASE, A + '/tasks/sess-1/t.json': F('{}'), B + '/session-env': L('/data/e'), '/data/e': D()})
ho('b4-handover-destination-blocked-beats-exists', 'DESTINATION_BLOCKED is reported before SESSION_EXISTS', err('DESTINATION_BLOCKED', B + '/projects/-x'),
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('a'), A + '/tasks/sess-1/t.json': F('{}'), B + '/projects/-x': L('/data/x'), B + '/tasks/sess-1/t.json': F('old')})
ho('b4-handover-destination-blocked-after-live', 'SESSION_LIVE comes before DESTINATION_BLOCKED', err('SESSION_LIVE', None),
   fs={**BASE, A + '/projects/-x/sess-1.jsonl': F('a'), B + '/projects/-x': L('/data/x'), A + '/sessions/200.json': sess(200, sid=SID)},
   processes={'200': {'procStart': 'T1', 'pidDomain': 'host-1'}})
ho('b4-handover-destination-file-parent-blocked', 'a regular file where a destination parent should be blocks too', err('DESTINATION_BLOCKED', B + '/tasks'),
   fs={**BASE, A + '/tasks/sess-1/t.json': F('{}'), B + '/tasks': F('x')})

# ---- B5 limits, available_at
def stl(extra=None):
    return {SP: state(*extra)}
LIM1 = stored(E1, at=OLD)
mk('b5-limits-basic', 'limits returns the parsed entries as stored, past ones included', 'B5', op('limits', name='work'),
   ok({'limits': [{'window': 'seven_day', 'model': 'opus', 'until': '2026-10-09T14:00:00Z', 'reason': 'rate_limit', 'updatedBy': 'my-swapper', 'updatedAt': OLD},
                  {'window': 'five_hour', 'model': None, 'until': OLD, 'reason': None, 'updatedBy': None, 'updatedAt': None}]}),
   fs={SP: state(LIM1, {'window': 'five_hour', 'until': OLD})})
mk('b5-limits-no-file', 'no state file: empty list', 'B5', op('limits', name='work'), ok({'limits': []}), fs=acct(wl, 'work'))
mk('b5-limits-unparseable', 'a state file that is not understood reads as empty', 'B5', op('limits', name='work'), ok({'limits': []}), fs={SP: F('{x')})
mk('b5-limits-skips-malformed', 'junk and entries without a window or a readable until are left out', 'B5', op('limits', name='work'),
   ok({'limits': [{'window': 'w', 'model': None, 'until': FUT, 'reason': None, 'updatedBy': None, 'updatedAt': None}]}),
   fs={SP: F(jd({'version': 1, 'limits': ['x', {'until': FUT}, {'window': 'a', 'until': 'soon'}, {'window': 'w', 'until': FUT}]}))})
mk('b5-limits-default', 'default reads ~/.claude', 'B5', op('limits', name='default'),
   ok({'limits': [{'window': 'seven_day', 'model': 'opus', 'until': '2026-10-09T14:00:00Z', 'reason': 'rate_limit', 'updatedBy': 'my-swapper', 'updatedAt': OLD}]}),
   fs={'/home/p/.claude/.multi-account-state.json': state(LIM1)})
mk('b5-limits-account-not-found', 'unknown account', 'B5', op('limits', name='nope'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))
def aa(id, desc, limits, expect, model=None):
    a = {'name': 'work'}
    if model:
        a['model'] = model
    mk(id, desc, 'B5', op('available_at', **a), ok({'availableAt': expect}), fs={SP: state(*limits)} if limits is not None else acct(wl, 'work'))
aa('b5-available-at-free', 'no limits: null', None, None)
aa('b5-available-at-limited', 'the until of the applying entry', [stored(E2)], '2026-10-06T18:00:00Z', model='opus')
aa('b5-available-at-latest-wins', 'the latest until among applying entries', [stored(E2), stored(E1)], '2026-10-09T14:00:00Z', model='opus')
aa('b5-available-at-other-model-free', 'an entry for another model does not apply', [stored(E1)], None, model='sonnet')
aa('b5-available-at-no-model-ignores-model-entries', 'with no model only all-models entries apply', [stored(E1)], None)
aa('b5-available-at-past-ignored', 'a past until does not count', [stored(dict(E1, until=OLD))], None, model='opus')
aa('b5-available-at-equal-now-free', 'until equal to now is free', [stored(dict(E1, until=NOW))], None, model='opus')
aa('b5-available-at-offset-normalised-to-utc', 'an offset until is returned as UTC', [stored(dict(E1, until='2026-10-09T16:00:00+02:00'))], '2026-10-09T14:00:00Z', model='opus')
aa('b5-available-at-fraction', 'milliseconds are kept when non-zero, finer digits are truncated', [stored(dict(E1, until='2026-10-09T14:00:00.123456Z'))], '2026-10-09T14:00:00.123Z', model='opus')
aa('b5-available-at-unparseable-file-free', 'a file not understood is null', [], None)
mk('b5-available-at-garbage-file', 'garbage state file: null', 'B5', op('available_at', name='work'), ok({'availableAt': None}), fs={SP: F('{{')})
mk('b5-available-at-account-not-found', 'unknown account', 'B5', op('available_at', name='nope'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))

# ---- B6 pool_members
mk('b6-pool-members-order', 'members in pick order: priority descending then name', 'B6', op('pool_members', pool='team'), ok({'members': ['b', 'c', 'a']}), fs=TEAM)
mk('b6-pool-members-includes-limited', 'availability is not applied', 'B6', op('pool_members', pool='team'), ok({'members': ['b', 'c', 'a']}), fs={**TEAM, **lim('b')})
mk('b6-pool-members-empty', 'unknown pool: empty', 'B6', op('pool_members', pool='nobody'), ok({'members': []}), fs=TEAM)
mk('b6-pool-members-alias-once', 'an alias group is one member, the named representative', 'B6', op('pool_members', pool='p'), ok({'members': ['work']}), fs=SLOTPOOL)
mk('b6-pool-members-invalid-pool', 'bad pool name', 'B6', op('pool_members', pool='Team'), err('INVALID_NAME', None))
mk('b6-pool-members-invalid-spec', 'an invalid spec file anywhere', 'B6', op('pool_members', pool='team'), err('SPEC_FILE_INVALID', '/home/p/.claude-bad/.multi-account.json'),
   fs={**TEAM, '/home/p/.claude-bad/.multi-account.json': F('{')})

# ---- B3 session_of_pid
def sop(id, desc, pid, expect, fs=None, name='work'):
    mk(id, desc, 'B3', op('session_of_pid', name=name, pid=pid), ok({'sessionId': expect}), fs=fs if fs is not None else acct(wl, name))
sop('b3-session-of-pid-basic', 'the sessionId of sessions/<pid>.json', 4242, UUID1, fs={'/home/p/.claude-work/sessions/4242.json': crec(4242)})
sop('b3-session-of-pid-follows-record', 'the record is read as it is now (the id changes on /clear)', 4242, 'new-id', fs={'/home/p/.claude-work/sessions/4242.json': crec(4242, sessionId='new-id')})
sop('b3-session-of-pid-dead-pid-still-reported', 'liveness is not checked', 4242, UUID1, fs={'/home/p/.claude-work/sessions/4242.json': crec(4242)})
sop('b3-session-of-pid-no-file', 'no record: null', 4242, None)
sop('b3-session-of-pid-no-session-id', 'a record without sessionId: null', 4242, None, fs={'/home/p/.claude-work/sessions/4242.json': F(jd({'pid': 4242}))})
sop('b3-session-of-pid-bad-json', 'not an object: null', 4242, None, fs={'/home/p/.claude-work/sessions/4242.json': F('[1]')})
sop('b3-session-of-pid-invalid-pid', 'a pid below 1 is null', 0, None, fs={'/home/p/.claude-work/sessions/0.json': crec(1)})
sop('b3-session-of-pid-default', 'default reads ~/.claude/sessions', 7, UUID1, fs={'/home/p/.claude/sessions/7.json': crec(7)}, name='default')
mk('b3-session-of-pid-account-not-found', 'unknown account', 'B3', op('session_of_pid', name='nope', pid=1), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))

# ---- B4 project_slug, sessions_for
def slug(id, desc, cwd, expect):
    mk(id, desc, 'B4', op('project_slug', cwd=cwd), ok({'slug': expect}))
slug('b4-project-slug-posix', 'every character outside [a-zA-Z0-9] becomes a hyphen', '/home/user/dev/my_proj.v2', '-home-user-dev-my-proj-v2')
slug('b4-project-slug-root', 'the root', '/', '-')
slug('b4-project-slug-win32', 'a Windows path', 'C:\\Users\\p\\proj', 'C--Users-p-proj')
slug('b4-project-slug-non-ascii', 'one hyphen per UTF-16 code unit: a BMP character is one', '/home/caf\u00e9', '-home-caf-')
slug('b4-project-slug-astral', 'an astral character is two UTF-16 code units, so two hyphens', '/home/\U0001F600x', '-home---x')
slug('b4-project-slug-200-chars', 'exactly 200 characters stay as they are', '/' + 'a' * 199, '-' + 'a' * 199)
LONG = '/' + 'a' * 200
def h36(s):
    import struct
    cu = struct.unpack('<%dH' % (len(s.encode('utf-16-le')) // 2), s.encode('utf-16-le'))
    h = 0
    for c in cu:
        h = ((h << 5) - h + c) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 1 << 32
    n, t = abs(h), ''
    while True:
        t = '0123456789abcdefghijklmnopqrstuvwxyz'[n % 36] + t
        n //= 36
        if n == 0:
            return t
slug('b4-project-slug-201-chars-hashed', 'longer than 200: the first 200 characters, a hyphen and the base 36 hash of the original path', LONG, '-' + 'a' * 199 + '-' + h36(LONG))
LONG2 = '/home/' + 'x/' * 150
slug('b4-project-slug-long-with-separators', 'the hash is of the original, not the slugged, string', LONG2, __import__('re').sub(r'[^a-zA-Z0-9]', '-', LONG2)[:200] + '-' + h36(LONG2))
slug('b4-project-slug-hash-uses-utf16', 'the hash runs over UTF-16 code units', '/' + '\U0001F600' * 120, '-' + '-' * 199 + '-' + h36('/' + '\U0001F600' * 120))
slug('b4-project-slug-not-normalised', 'the cwd is used exactly as given', '/home/p//proj/', '-home-p--proj-')

PJ = '/home/p/.claude-work/projects/-home-p-proj/'
def sf(id, desc, files, expect, cwd='/home/p/proj', fs_extra=None, name='work'):
    mk(id, desc, 'B4', op('sessions_for', name=name, cwd=cwd), ok({'sessions': expect}), fs={**files, **(fs_extra or {})})
sf('b4-sessions-for-newest-first', 'transcripts of the project, newest first, with mtimes', {
    PJ + 'old-1.jsonl': F('a', mtime='2026-10-01T10:00:00Z'), PJ + 'new-2.jsonl': F('b', mtime='2026-10-05T10:00:00.250Z'), PJ + 'mid-3.jsonl': F('c', mtime='2026-10-03T10:00:00Z')},
   [{'id': 'new-2', 'mtime': '2026-10-05T10:00:00.250Z'}, {'id': 'mid-3', 'mtime': '2026-10-03T10:00:00.000Z'}, {'id': 'old-1', 'mtime': '2026-10-01T10:00:00.000Z'}])
sf('b4-sessions-for-tie-by-id', 'equal mtimes sort by id bytewise', {PJ + 'b.jsonl': F('x', mtime='2026-10-01T10:00:00Z'), PJ + 'a.jsonl': F('x', mtime='2026-10-01T10:00:00Z')},
   [{'id': 'a', 'mtime': '2026-10-01T10:00:00.000Z'}, {'id': 'b', 'mtime': '2026-10-01T10:00:00.000Z'}])
sf('b4-sessions-for-ignores-other-files', 'only <id>.jsonl regular files with a valid id', {
    PJ + 'ok-1.jsonl': F('x', mtime='2026-10-01T10:00:00Z'), PJ + 'notes.txt': F('x'), PJ + 'bad.id.jsonl': F('x'), PJ + '.hidden.jsonl': F('x'), PJ + 'dir-1': D(),
    PJ + 'dir-1/inner.jsonl': F('x'), PJ + 'linked.jsonl': L('/data/l.jsonl'), '/data/l.jsonl': F('x'), PJ + 'sub.jsonl': D()},
   [{'id': 'ok-1', 'mtime': '2026-10-01T10:00:00.000Z'}])
sf('b4-sessions-for-other-project-not-listed', 'another project folder is not read', {'/home/p/.claude-work/projects/-home-p-other/x-1.jsonl': F('x')}, [])
sf('b4-sessions-for-no-projects', 'no projects directory', {'/home/p/.claude-work': D()}, [])
sf('b4-sessions-for-linked-slug-empty', 'a project folder that is a link is never a location', {'/home/p/.claude-work/projects/-home-p-proj': L('/data/p'), '/data/p/x-1.jsonl': F('x')}, [])
sf('b4-sessions-for-linked-projects-dir-empty', 'a linked projects directory is never a location', {'/home/p/.claude-work/projects': L('/data/pp'), '/data/pp/-home-p-proj/x-1.jsonl': F('x')}, [])
sf('b4-sessions-for-default', 'default reads ~/.claude/projects', {'/home/p/.claude/projects/-home-p-proj/d-1.jsonl': F('x', mtime='2026-10-01T10:00:00Z')},
   [{'id': 'd-1', 'mtime': '2026-10-01T10:00:00.000Z'}], name='default')
sf('b4-sessions-for-hashed-slug', 'a long cwd uses the hashed folder name', {'/home/p/.claude-work/projects/' + '-' + 'a' * 199 + '-' + h36(LONG) + '/h-1.jsonl': F('x', mtime='2026-10-01T10:00:00Z')},
   [{'id': 'h-1', 'mtime': '2026-10-01T10:00:00.000Z'}], cwd=LONG)
sf('b4-sessions-for-win32-style-cwd', 'the slug of a Windows cwd', {'/home/p/.claude-work/projects/C--src-r/w-1.jsonl': F('x', mtime='2026-10-01T10:00:00Z')},
   [{'id': 'w-1', 'mtime': '2026-10-01T10:00:00.000Z'}], cwd='C:\\src\\r')
mk('b4-sessions-for-account-not-found', 'unknown account', 'B4', op('sessions_for', name='nope', cwd='/x'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))

# ---- B2 usage windows and stale
UW = {'utilization': {'five_hour': {'utilization': 5, 'resets_at': '2026-10-06T15:00:00Z'}, 'seven_day': {'utilization': None, 'resets_at': None}, 'junk': 3,
                      'seven_day_opus': {'utilization': '9', 'resets_at': 7}}}
def usg(id, desc, cache, expect, oauth=None, **kw):
    gcd = {'cachedUsageUtilization': cache}
    if oauth is not None:
        gcd['oauthAccount'] = oauth
    mk(id, desc, 'B2', op('usage', name='work'), ok(expect), fs={GC: F(jd(gcd))}, **kw)
usg('b2-usage-windows-parsed', 'windows from the utilization object: numbers and strings kept, anything else null, non-objects left out',
    dict(UW, fetchedAtMs=FRESH), {'fetchedAt': iso_ms(FRESH), 'data': dict(UW, fetchedAtMs=FRESH),
    'windows': {'five_hour': {'utilization': 5, 'resetsAt': '2026-10-06T15:00:00Z'}, 'seven_day': {'utilization': None, 'resetsAt': None},
                'seven_day_opus': {'utilization': None, 'resetsAt': None}}, 'stale': False})
usg('b2-usage-no-utilization-object', 'a cache without a utilization object has no windows', {'fetchedAtMs': FRESH}, {'fetchedAt': iso_ms(FRESH), 'data': {'fetchedAtMs': FRESH}, 'windows': {}, 'stale': False})
def stale_case(id, desc, ms_, stale, uuid_cache=None, oauth=None):
    c = {'utilization': {}, 'fetchedAtMs': ms_}
    if uuid_cache is not None:
        c['accountUuid'] = uuid_cache
    usg(id, desc, c, {'fetchedAt': iso_ms(ms_), 'data': c, 'windows': {}, 'stale': stale}, oauth=oauth)
NOWMS = FRESH + 600000
stale_case('b2-usage-stale-exactly-one-hour', 'an age of exactly one hour is still fresh', NOWMS - 3600000, False)
stale_case('b2-usage-stale-one-hour-and-a-millisecond', 'older than one hour is stale', NOWMS - 3600001, True)
stale_case('b2-usage-stale-future-fetch', 'a fetch time in the future is stale (Claude Code ignores a negative age)', NOWMS + 1, True)
stale_case('b2-usage-stale-now', 'fetched now is fresh', NOWMS, False)
stale_case('b2-usage-stale-uuid-match', 'matching accountUuid is fresh', FRESH, False, uuid_cache='acc-1', oauth=OA)
stale_case('b2-usage-stale-uuid-mismatch', 'a cache for another account is stale', FRESH, True, uuid_cache='acc-2', oauth=OA)
stale_case('b2-usage-stale-uuid-in-cache-only', 'a cache with accountUuid but no oauthAccount is stale', FRESH, True, uuid_cache='acc-1')
stale_case('b2-usage-stale-uuid-in-oauth-only', 'an oauthAccount uuid the cache lacks is stale', FRESH, True, oauth=OA)
stale_case('b2-usage-stale-no-uuid-anywhere', 'neither side has a uuid: fresh', FRESH, False)
mk('b2-usage-resolve-includes-windows', 'a resolution gives the same windows and stale', 'B2', op('usage', resolve=True),
   ok({'fetchedAt': iso_ms(FRESH), 'data': CUV, 'windows': {'five_hour': {'utilization': 1, 'resetsAt': '2026-10-06T15:00:00Z'}}, 'stale': False}),
   fs={'/home/p/.claude.json': F(jd({'cachedUsageUtilization': CUV}))})

# ---- A3 spec_file, update_spec_file, claim, unclaim
SPW = '/home/p/.claude-work/.multi-account.json'
def sfc(id, desc, entry, expect):
    mk(id, desc, 'A3', op('spec_file', name='work'), expect, fs={SPW: entry} if entry is not None else acct(wl, 'work'))
sfc('a3-spec-file-read', 'the validated object verbatim, unknown keys included', F(spec(label='W', pool='p', priority=2, directories=['~/dev'], extra={'a': 1})),
    ok({'version': 1, 'label': 'W', 'pool': 'p', 'priority': 2, 'directories': ['~/dev'], 'extra': {'a': 1}}))
sfc('a3-spec-file-absent', 'no file: null', None, ok(None))
sfc('a3-spec-file-invalid', 'an invalid file is SPEC_FILE_INVALID', F('{'), err('SPEC_FILE_INVALID', SPW))
sfc('a3-spec-file-invalid-priority', 'a priority the library rejects', F(spec(priority=1.5)), err('SPEC_FILE_INVALID', SPW))
sfc('a3-spec-file-invalid-utf8', 'invalid UTF-8', FB(b'{"version": 1, "label": "caf\xe9"}'), err('SPEC_FILE_INVALID', SPW))
mk('a3-spec-file-via-link-target', 'the same with a target present', 'A3', op('spec_file', name='work'), ok({'version': 1}), fs={SPW: L('/data/s.json'), '/data/s.json': F(spec())})
mk('a3-spec-file-default', 'default reads ~/.claude', 'A3', op('spec_file', name='default'), ok({'version': 1, 'label': 'd'}), fs={'/home/p/.claude/.multi-account.json': F(spec(label='d'))})
mk('a3-spec-file-account-not-found', 'unknown account', 'A3', op('spec_file', name='nope'), err('ACCOUNT_NOT_FOUND', '/home/p/.claude-nope'))
mk('a3-spec-file-invalid-name', 'bad name', 'A3', op('spec_file', name='W'), err('INVALID_NAME', None))

def usf(id, desc, patch, expect, fs, expectFs=None, name='work', **kw):
    mk(id, desc, 'A3', op('update_spec_file', name=name, patch=patch), expect, fs=fs, expectFs=expectFs if expectFs is not None else {SPW + '.lock': None}, **kw)
usf('a3-update-spec-file-merge', 'top-level keys are merged, unknown keys kept, mode 0600', {'label': 'New', 'pool': 'p'}, ok({'version': 1, 'label': 'New', 'pool': 'p', 'extra': [1]}),
    {SPW: F(spec(label='Old', extra=[1]))}, {SPW: {'type': 'file', 'mode': '0600', 'contentJson': {'version': 1, 'label': 'New', 'pool': 'p', 'extra': [1]}}, SPW + '.lock': None})
usf('a3-update-spec-file-null-removes', 'a null value removes the key', {'label': None}, ok({'version': 1}), {SPW: F(spec(label='x'))}, {SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-creates', 'no file yet: created with version 1', {'label': 'L'}, ok({'version': 1, 'label': 'L'}), acct(wl, 'work'),
    {SPW: {'type': 'file', 'mode': '0600', 'contentJson': {'version': 1, 'label': 'L'}}, SPW + '.lock': None})
usf('a3-update-spec-file-empty-patch-creates', 'an empty patch on a missing file still creates it', {}, ok({'version': 1}), acct(wl, 'work'), {SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-through-link', 'a linked spec file is written through, the link stays', {'label': 'L'}, ok({'version': 1, 'label': 'L'}),
    {SPW: L('/data/s.json'), '/data/s.json': F(spec())}, {SPW: {'type': 'symlink', 'target': '/data/s.json'}, '/data/s.json': {'contentJson': {'version': 1, 'label': 'L'}}, SPW + '.lock': None})
usf('a3-update-spec-file-refuses-invalid-existing', 'an existing invalid file is never overwritten', {'label': 'L'}, err('SPEC_FILE_INVALID', SPW), {SPW: F('{nope')},
    {SPW: {'content': '{nope'}, SPW + '.lock': None})
usf('a3-update-spec-file-refuses-bad-priority', 'a patch the library would reject is refused and nothing is written', {'priority': 1.5}, err('INVALID_ENTRY', None),
    {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1}}, SPW + '.lock': None})
usf('a3-update-spec-file-refuses-bad-version', 'version other than 1', {'version': 2}, err('INVALID_ENTRY', None), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-refuses-removing-version', 'removing version', {'version': None}, err('INVALID_ENTRY', None), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-refuses-bad-directories', 'an invalid claim string', {'directories': ['rel/x']}, err('INVALID_ENTRY', None), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-refuses-too-deep', 'nested deeper than 100 levels', {'x': __import__('json').loads('[' * 100 + ']' * 100)}, err('INVALID_ENTRY', None), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-patch-not-object', 'the patch must be an object', ['x'], err('INVALID_ENTRY', None), {SPW: F(spec())})
usf('a3-update-spec-file-lock-busy', 'a fresh lock', {'label': 'L'}, err('LOCK_BUSY', SPW + '.lock'), {SPW: F(spec()), SPW + '.lock': D()}, {SPW + '.lock': {'type': 'dir'}, SPW: {'contentJson': {'version': 1}}})
usf('a3-update-spec-file-default', 'default writes ~/.claude/.multi-account.json', {'label': 'D'}, ok({'version': 1, 'label': 'D'}), {'/home/p/.claude': D()},
    {'/home/p/.claude/.multi-account.json': {'contentJson': {'version': 1, 'label': 'D'}, 'mode': '0600'}}, name='default')
usf('a3-update-spec-file-account-not-found', 'unknown account', {}, err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), {}, {})
usf('a3-update-spec-file-win32', 'win32 path', {'label': 'L'}, ok({'version': 1, 'label': 'L'}), acct(ww, 'work'),
    {'C:\\Users\\p\\.claude-work\\.multi-account.json': {'contentJson': {'version': 1, 'label': 'L'}, 'mode': '0600'}}, plat='win32')

def clm(id, desc, op_name, dir_, expect, fs, expectFs, name='work', **kw):
    mk(id, desc, 'A3', op(op_name, name=name, dir=dir_), expect, fs=fs, expectFs=expectFs, **kw)
CLEAN2 = {SPW + '.lock': None}
clm('a3-claim-under-home-stored-with-tilde', 'an absolute directory under home is stored as ~/...', 'claim', '/home/p/dev/personal', ok({'directories': ['~/dev/personal']}),
    {SPW: F(spec()), '/home/p/dev/personal': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['~/dev/personal']}, 'mode': '0600'}, **CLEAN2})
clm('a3-claim-outside-home-stored-absolute', 'a directory outside home stays absolute', 'claim', '/srv/code', ok({'directories': ['/srv/code']}),
    {SPW: F(spec()), '/srv/code': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/code']}}})
clm('a3-claim-tilde-form-accepted', 'a ~/ argument is stored as ~/', 'claim', '~/dev', ok({'directories': ['~/dev']}), {SPW: F(spec()), '/home/p/dev': D()},
    {SPW: {'contentJson': {'version': 1, 'directories': ['~/dev']}}})
clm('a3-claim-home-itself', 'home itself is ~/', 'claim', '/home/p', ok({'directories': ['~/']}), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1, 'directories': ['~/']}}})
clm('a3-claim-normalises', 'the directory is lexically normalised first', 'claim', '/home/p/dev/../dev//x/', ok({'directories': ['~/dev/x']}), {SPW: F(spec())},
    {SPW: {'contentJson': {'version': 1, 'directories': ['~/dev/x']}}})
clm('a3-claim-appends-keeps-others', 'existing claims and unknown keys stay', 'claim', '/srv/b', ok({'directories': ['/srv/a', '/srv/b']}),
    {SPW: F(spec(directories=['/srv/a'], label='L')), '/srv/a': D(), '/srv/b': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a', '/srv/b'], 'label': 'L'}}})
clm('a3-claim-creates-spec-file', 'no spec file yet', 'claim', '/srv/a', ok({'directories': ['/srv/a']}), acct(wl, 'work'),
    {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a']}, 'mode': '0600'}})
clm('a3-claim-idempotent-same-spelling', 'claiming a directory the account already claims changes nothing', 'claim', '/srv/a', ok({'directories': ['/srv/a']}),
    {SPW: F(spec(directories=['/srv/a'])), '/srv/a': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a']}}})
clm('a3-claim-idempotent-by-identity', 'another spelling of the same directory is already claimed', 'claim', '/srv/a', ok({'directories': ['/srv/alink']}),
    {SPW: F(spec(directories=['/srv/alink'])), '/srv/alink': L('/srv/a'), '/srv/a': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/alink']}}})
clm('a3-claim-idempotent-no-file-write', 'an idempotent claim does not touch the file', 'claim', '/srv/a', ok({'directories': ['/srv/a']}),
    {SPW: F(spec(directories=['/srv/a'], x=1), mtime='2026-10-01T10:00:00Z'), '/srv/a': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a'], 'x': 1}}, SPW + '.lock': None})
OTHER = {'/home/p/.claude-personal/.multi-account.json': F(spec(directories=['/srv/a']))}
clm('a3-claim-conflict-other-account', 'another account claims the directory', 'claim', '/srv/a', err('CLAIM_CONFLICT', '/srv/a'),
    {SPW: F(spec()), **OTHER, '/srv/a': D()}, {SPW: {'contentJson': {'version': 1}}, SPW + '.lock': None})
clm('a3-claim-conflict-by-identity', 'the conflict is by identity: a link spelling clashes', 'claim', '/srv/alias', err('CLAIM_CONFLICT', '/srv/alias'),
    {SPW: F(spec()), **OTHER, '/srv/a': D(), '/srv/alias': L('/srv/a')}, {SPW: {'contentJson': {'version': 1}}})
clm('a3-claim-conflict-tilde-spelling', 'a ~/ claim by another account clashes with the absolute spelling', 'claim', '/home/p/dev', err('CLAIM_CONFLICT', '/home/p/dev'),
    {SPW: F(spec()), '/home/p/.claude-personal/.multi-account.json': F(spec(directories=['~/dev'])), '/home/p/dev': D()}, {SPW: {'contentJson': {'version': 1}}})
clm('a3-claim-missing-dir-conflicts-lexically', 'a directory that does not exist is compared by its normalised path', 'claim', '/srv/gone', err('CLAIM_CONFLICT', '/srv/gone'),
    {SPW: F(spec()), '/home/p/.claude-personal/.multi-account.json': F(spec(directories=['/srv/gone']))}, {SPW: {'contentJson': {'version': 1}}})
clm('a3-claim-missing-dir-allowed', 'a missing directory can be claimed', 'claim', '/srv/gone', ok({'directories': ['/srv/gone']}), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/gone']}}})
clm('a3-claim-other-invalid-spec-file', 'an invalid spec file in another account is reported', 'claim', '/srv/a', err('SPEC_FILE_INVALID', '/home/p/.claude-personal/.multi-account.json'),
    {SPW: F(spec()), '/home/p/.claude-personal/.multi-account.json': F('{')}, {SPW: {'contentJson': {'version': 1}}})
clm('a3-claim-own-invalid-spec-file', 'the account own invalid file is never overwritten', 'claim', '/srv/a', err('SPEC_FILE_INVALID', SPW), {SPW: F('{')}, {SPW: {'content': '{'}})
clm('a3-claim-relative-dir-invalid', 'a relative directory', 'claim', 'dev/x', err('INVALID_ENTRY', None), {SPW: F(spec())}, {SPW: {'contentJson': {'version': 1}}})
clm('a3-claim-tilde-user-invalid', '~user is invalid', 'claim', '~bob/x', err('INVALID_ENTRY', None), {SPW: F(spec())}, {})
clm('a3-claim-alias-of-same-account-no-conflict', 'default and the slot account are one account: no conflict between them', 'claim', '/srv/a', ok({'directories': ['/srv/a']}),
    {**managed(wl), '/home/p/.claude-work/.multi-account.json': F(spec(directories=['/srv/a'])), '/srv/a': D()}, {'/home/p/.claude-work/.multi-account.json': {'contentJson': {'version': 1, 'directories': ['/srv/a']}}}, name='default')
clm('a3-claim-via-default-writes-slot-account-file', 'claiming for default while the slot holds work writes work spec file', 'claim', '/srv/b', ok({'directories': ['/srv/b']}),
    {**managed(wl), '/srv/b': D()}, {'/home/p/.claude-work/.multi-account.json': {'contentJson': {'version': 1, 'directories': ['/srv/b']}}}, name='default')
clm('a3-claim-case-insensitive-conflict-darwin', 'on a case-insensitive filesystem a differently cased missing path conflicts', 'claim', '/Users/p/Proj', err('CLAIM_CONFLICT', '/Users/p/Proj'),
    {'/Users/p/.claude-work/.multi-account.json': F(spec()), '/Users/p/.claude-personal/.multi-account.json': F(spec(directories=['/Users/p/proj']))}, {}, plat='darwin')
clm('a3-claim-win32-stored-with-tilde', 'win32: under home is ~/ with forward slash', 'claim', 'C:\\Users\\p\\dev\\x', ok({'directories': ['~/dev/x']}),
    {'C:\\Users\\p\\.claude-work\\.multi-account.json': F(spec())}, {'C:\\Users\\p\\.claude-work\\.multi-account.json': {'contentJson': {'version': 1, 'directories': ['~/dev/x']}}}, plat='win32')
clm('a3-claim-account-not-found', 'unknown account', 'claim', '/srv/a', err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), {}, {})
clm('a3-claim-then-resolves-as-claim-form', 'the stored form is what resolve reads: ~/ entries are valid claims', 'claim', '/home/p/dev/a', ok({'directories': ['~/dev', '~/dev/a']}),
    {SPW: F(spec(directories=['~/dev'])), '/home/p/dev/a': D(), '/home/p/dev': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['~/dev', '~/dev/a']}}})

clm('a3-unclaim-removes', 'the claim is removed, other keys stay', 'unclaim', '/home/p/dev/personal', ok({'directories': ['/srv/a']}),
    {SPW: F(spec(directories=['~/dev/personal', '/srv/a'], label='L')), '/home/p/dev/personal': D(), '/srv/a': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a'], 'label': 'L'}, 'mode': '0600'}, **CLEAN2})
clm('a3-unclaim-by-identity', 'any spelling of the same directory is removed', 'unclaim', '/srv/a', ok({'directories': []}),
    {SPW: F(spec(directories=['/srv/alink'])), '/srv/alink': L('/srv/a'), '/srv/a': D()}, {SPW: {'contentJson': {'version': 1, 'directories': []}}})
clm('a3-unclaim-all-spellings', 'every matching entry is removed', 'unclaim', '/home/p/dev', ok({'directories': ['/srv/z']}),
    {SPW: F(spec(directories=['~/dev', '/home/p/dev', '/srv/z'])), '/home/p/dev': D(), '/srv/z': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/z']}}})
clm('a3-unclaim-not-claimed-no-write', 'not claimed: nothing is written', 'unclaim', '/srv/q', ok({'directories': ['/srv/a']}),
    {SPW: F(spec(directories=['/srv/a'], x=1)), '/srv/a': D()}, {SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a'], 'x': 1}}, SPW + '.lock': None})
clm('a3-unclaim-no-file', 'no spec file: empty list and nothing created', 'unclaim', '/srv/a', ok({'directories': []}), acct(wl, 'work'), {SPW: None, SPW + '.lock': None})
clm('a3-unclaim-own-invalid-file', 'an invalid spec file is refused', 'unclaim', '/srv/a', err('SPEC_FILE_INVALID', SPW), {SPW: F('{')}, {SPW: {'content': '{'}})
clm('a3-unclaim-relative-invalid', 'a relative directory', 'unclaim', 'x', err('INVALID_ENTRY', None), {SPW: F(spec())}, {})
clm('a3-unclaim-account-not-found', 'unknown account', 'unclaim', '/srv/a', err('ACCOUNT_NOT_FOUND', '/home/p/.claude-work'), {}, {})
clm('a3-unclaim-lock-busy', 'a fresh lock', 'unclaim', '/srv/a', err('LOCK_BUSY', SPW + '.lock'), {SPW: F(spec(directories=['/srv/a'])), SPW + '.lock': D(), '/srv/a': D()},
    {SPW + '.lock': {'type': 'dir'}, SPW: {'contentJson': {'version': 1, 'directories': ['/srv/a']}}})
