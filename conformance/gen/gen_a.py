from gen_lib import *

W_ = {p: W(p) for p in ('linux', 'darwin', 'win32')}
wl, wd, ww = W_['linux'], W_['darwin'], W_['win32']


def dacc(w, hs=False, hg=False, se=None, alias=None):
    return dict(name='default', configDir=w('.claude'), state='ok', hasSpecFile=hs, hasGlobalConfig=hg,
                aliasOf=alias, specError=se, warnings=[])


def nacc(w, name, state='ok', hs=False, hg=False, alias=None, se=None, warn=None):
    return dict(name=name, configDir=w('.claude-' + name), state=state, hasSpecFile=hs, hasGlobalConfig=hg,
                aliasOf=alias, specError=se, warnings=warn or [])


def disc(accounts, conflicts=None, warnings=None):
    return ok({'accounts': accounts, 'conflicts': conflicts or [], 'warnings': warnings or []})


# ---------------- A2 canonical path
mk('a2-canonical-basic', 'canonical path of a named account on linux', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': '/home/p/.claude-work'}))
mk('a2-canonical-darwin', 'canonical path on darwin', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': '/Users/p/.claude-work'}), plat='darwin')
mk('a2-canonical-win32', 'canonical path on win32 uses backslashes', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': 'C:\\Users\\p\\.claude-work'}), plat='win32')
mk('a2-canonical-home-trailing-sep', 'duplicate and trailing separators in home are collapsed', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': '/home/p/.claude-work'}), home='/home/p//', nohome=True)
mk('a2-canonical-home-dotdot', 'home with .. is normalised lexically, symlinks never resolved', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': '/home/q/.claude-work'}), home='/home/p/../q', nohome=True)
mk('a2-canonical-win32-forward-slash-home', 'win32 home written with forward slashes and trailing slash', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': 'C:\\Users\\p\\.claude-work'}), plat='win32', home='C:/Users/p/', nohome=True)
mk('a2-canonical-win32-drive-case-kept', 'win32 keeps the drive letter case as given', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': 'c:\\Users\\p\\.claude-work'}), plat='win32', home='c:\\Users\\p', nohome=True)
mk('a2-canonical-nfc', 'canonical path is NFC normalised (home given in NFD)', ['A2 Canonical path', 'A1'],
   op('canonical_path', name='work'), ok({'path': '/home/jos\u00e9/.claude-work'}), home='/home/jose\u0301', nohome=True)
mk('a2-canonical-default', 'canonical path of default is $HOME/.claude', ['A2 Storage', 'A4 Result'],
   op('canonical_path', name='default'), ok({'path': '/home/p/.claude'}))
mk('a2-canonical-reserved-is-pure', 'canonical_path does not apply reservation', 'A2 Names',
   op('canonical_path', name='profiles'), ok({'path': '/home/p/.claude-profiles'}))
mk('a2-canonical-no-symlink-resolution', 'a link at the canonical path is not resolved', 'A2 Canonical path',
   op('canonical_path', name='work'), ok({'path': '/home/p/.claude-work'}),
   fs={'/home/p/.claude-work': L('/data/work'), '/data/work': D()})

# names
names_ok = [('a2-name-valid-32-chars', 'a' * 32), ('a2-name-valid-digit-first', '1x_y-z'), ('a2-name-valid-single', 'x')]
for id, n in names_ok:
    mk(id, 'valid name %r' % n, 'A2 Names', op('canonical_path', name=n), ok({'path': '/home/p/.claude-' + n}))
names_bad = [('a2-name-invalid-33-chars', 'a' * 33), ('a2-name-invalid-uppercase', 'Work'), ('a2-name-invalid-empty', ''),
             ('a2-name-invalid-leading-hyphen', '-x'), ('a2-name-invalid-leading-underscore', '_x'),
             ('a2-name-invalid-dot', 'a.b'), ('a2-name-invalid-space', 'a b'), ('a2-name-invalid-trailing-newline', 'work\n'),
             ('a2-name-invalid-slash', 'a/b'), ('a2-name-invalid-non-ascii', 'caf\u00e9')]
for id, n in names_bad:
    mk(id, 'invalid name %r' % n, 'A2 Names', op('canonical_path', name=n), err('INVALID_NAME', None))

# ---------------- A2 discovery
mk('a2-discover-empty-home', 'no account dirs: only default is listed', 'A2 Discovery',
   op('discover'), disc([dacc(wl)]))
mk('a2-discover-missing-home', 'home missing entirely: only default is listed', 'A2 Discovery',
   op('discover'), disc([dacc(wl)]), nohome=True)
mk('a2-discover-sorted', 'accounts are listed default first then by name bytewise', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, '1b'), nacc(wl, 'a_b'), nacc(wl, 'personal'), nacc(wl, 'work')]),
   fs=acct(wl, 'work', 'personal', 'a_b', '1b'))
mk('a2-discover-default-dir-present', 'default with a real ~/.claude dir', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'work')]), fs={'/home/p/.claude': D(), **acct(wl, 'work')})
mk('a2-discover-symlink-to-dir', 'link to a directory is an account', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'work')]),
   fs={'/home/p/.claude-work': L('/data/work'), '/data/work': D()})
mk('a2-discover-relative-symlink', 'link with a relative target resolves against the link directory', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'work')]),
   fs={'/home/p/.claude-work': L('../data/work'), '/home/data/work': D()})
mk('a2-discover-dangling', 'link to a missing target is listed as dangling', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'gone', state='dangling')]),
   fs={'/home/p/.claude-gone': L('/mnt/usb/gone')})
mk('a2-discover-unreadable', 'link whose stat fails with EACCES is listed as unreadable', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'locked', state='unreadable')]),
   fs={'/home/p/.claude-locked': L('/mnt/locked/work', unreadable=True)})
mk('a2-discover-file-not-account', 'regular file named like an account gives NOT_A_DIRECTORY', 'A2 Discovery',
   op('discover'), disc([dacc(wl)], warnings=['NOT_A_DIRECTORY']),
   fs={'/home/p/.claude-notes': F('hi')})
mk('a2-discover-link-to-file', 'link to a non-directory gives NOT_A_DIRECTORY', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'real')], warnings=['NOT_A_DIRECTORY']),
   fs={'/home/p/.claude-odd': L('/data/file.txt'), '/data/file.txt': F('x'), **acct(wl, 'real')})
mk('a2-discover-marker-file-in-home', '~/.claude-account as a file is a marker, not an account', ['A2 Discovery', 'A4 Marker parsing'],
   op('discover'), disc([dacc(wl)], warnings=['NOT_A_DIRECTORY']),
   fs={'/home/p/.claude-account': F('work\n')})
mk('a2-discover-ignores-non-matching', 'entries not matching the name grammar exactly are ignored silently', 'A2 Discovery',
   op('discover'), disc([dacc(wl, hg=True), nacc(wl, 'work')]),
   fs={'/home/p/.claude-Work': D(), '/home/p/.claude-': D(), '/home/p/.claude-a.b': D(), '/home/p/.claude.json': F('{}'),
       '/home/p/.claude': D(), '/home/p/.claudex-y': D(), '/home/p/.claude-work': D()})
mk('a2-discover-case-exact-darwin', 'on a case-insensitive fs .claude-Work is not discovered as work', ['A2 Discovery'],
   op('discover'), disc([dacc(wd)]), plat='darwin', ci=True, fs={'/Users/p/.claude-Work': D()})
mk('a2-discover-reserved-warning', 'reserved names that exist are listed with RESERVED_NAME', 'A2 Names',
   op('discover'),
   disc([dacc(wl), nacc(wl, 'account', warn=['RESERVED_NAME']), nacc(wl, 'profiles', warn=['RESERVED_NAME']),
         nacc(wl, 'swap-backup', warn=['RESERVED_NAME']), nacc(wl, 'work')]),
   fs=acct(wl, 'account', 'profiles', 'swap-backup', 'work'))
mk('a2-discover-reserved-later', 'a name reserved later is still discovered with a warning (case reserved list)', 'A2 Names',
   op('discover'), disc([dacc(wl), nacc(wl, 'legacy', warn=['RESERVED_NAME']), nacc(wl, 'work')]),
   fs=acct(wl, 'legacy', 'work'), reserved=['default', 'legacy'])
mk('a2-discover-has-spec-and-global', 'hasSpecFile and hasGlobalConfig facts', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'bare'), nacc(wl, 'full', hs=True, hg=True), nacc(wl, 'gc', hg=True)]),
   fs={'/home/p/.claude-bare': D(), '/home/p/.claude-full/.multi-account.json': F(spec()),
       '/home/p/.claude-full/.claude.json': F('{}'), '/home/p/.claude-gc/.claude.json': F('{}')})
mk('a2-discover-legacy-config-json', 'legacy .config.json counts as a global config', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'old', hg=True)]),
   fs={'/home/p/.claude-old/.config.json': F('{}')})
mk('a2-discover-default-global-in-home', 'default global config is $HOME/.claude.json', ['A1', 'A2 Discovery'],
   op('discover'), disc([dacc(wl, hg=True), nacc(wl, 'work')]),
   fs={'/home/p/.claude.json': F('{}'), '/home/p/.claude': D(), **acct(wl, 'work')})
mk('a2-discover-default-global-inside-dir-ignored', 'default has no global config just because ~/.claude/.claude.json exists', ['A1', 'A2 Discovery'],
   op('discover'), disc([dacc(wl)]), fs={'/home/p/.claude/.claude.json': F('{}')})
mk('a2-discover-custom-oauth-suffix', 'CLAUDE_CODE_CUSTOM_OAUTH_URL changes the global config name', 'A1',
   op('discover'), disc([dacc(wl), nacc(wl, 'a'), nacc(wl, 'b', hg=True)]),
   env={'CLAUDE_CODE_CUSTOM_OAUTH_URL': 'https://example.test'},
   fs={'/home/p/.claude-a/.claude.json': F('{}'), '/home/p/.claude-b/.claude-custom-oauth.json': F('{}')})
mk('a2-discover-alias-symlink', 'two names for one directory: the later name carries aliasOf', 'A2 Relocation',
   op('discover'), disc([dacc(wl), nacc(wl, 'a'), nacc(wl, 'b', alias='a')]),
   fs={'/home/p/.claude-a': D(), '/home/p/.claude-b': L('/home/p/.claude-a')})
mk('a2-discover-alias-named-represents-default', 'default linked to a named account: the named account represents the group, default carries aliasOf', ['A2 Relocation', 'B7'],
   op('discover'), disc([dacc(wl, alias='work'), nacc(wl, 'work')]),
   fs={'/home/p/.claude': L('/home/p/.claude-work'), '/home/p/.claude-work': D()})
mk('a2-discover-alias-inode', 'same device and inode makes an alias without any link', 'A2 Relocation',
   op('discover'), disc([dacc(wl), nacc(wl, 'x'), nacc(wl, 'y', alias='x')]),
   fs={'/home/p/.claude-x': D(inode=5), '/home/p/.claude-y': D(inode=5)})
mk('a2-discover-alias-three', 'three names for one directory all point at the first', 'A2 Relocation',
   op('discover'), disc([dacc(wl), nacc(wl, 'a'), nacc(wl, 'b', alias='a'), nacc(wl, 'c', alias='a')]),
   fs={'/home/p/.claude-a': D(), '/home/p/.claude-b': L('/home/p/.claude-a'), '/home/p/.claude-c': L('/home/p/.claude-b')})
mk('a2-discover-same-inode-different-dev', 'equal inode on a different device is not an alias', 'A2 Relocation',
   op('discover'), disc([dacc(wl), nacc(wl, 'x'), nacc(wl, 'y')]),
   fs={'/home/p/.claude-x': D(inode=5), '/home/p/.claude-y': D(inode=5, dev=2)})
mk('a2-discover-junction-win32', 'win32 junction to a directory is an account', 'A2 Relocation',
   op('discover'), disc([dacc(ww), nacc(ww, 'work')]), plat='win32',
   fs={'C:\\Users\\p\\.claude-work': J('D:\\data\\work'), 'D:\\data\\work': D()})
mk('a2-discover-junction-dangling-win32', 'win32 junction whose target is gone is dangling', 'A2 Discovery',
   op('discover'), disc([dacc(ww), nacc(ww, 'work', state='dangling')]), plat='win32',
   fs={'C:\\Users\\p\\.claude-work': J('E:\\gone')})
mk('a2-discover-win32-stored-case', 'win32: only the stored-case spelling counts', 'A2 Discovery',
   op('discover'), disc([dacc(ww), nacc(ww, 'work')]), plat='win32',
   fs={'C:\\Users\\p\\.claude-work': D(), 'C:\\Users\\p\\.CLAUDE-other': D()})
# link chains and hop limit
def chain(n_links):
    fsd = {'/home/p/.claude-chain': L('/home/p/hop/1')}
    for i in range(1, n_links - 1):
        fsd['/home/p/hop/%d' % i] = L('/home/p/hop/%d' % (i + 1))
    last = n_links - 1
    fsd['/home/p/hop/%d' % last] = L('/home/p/hop/end') if last >= 1 else None
    fsd['/home/p/hop/end'] = D()
    return {k: v for k, v in fsd.items() if v}
mk('a2-discover-chain-40-hops', 'a chain of 40 links still resolves', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'chain')]), fs=chain(40))
mk('a2-discover-chain-41-hops', 'the 41st hop is ELOOP, reported as dangling', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'chain', state='dangling')]), fs=chain(41))
mk('a2-discover-link-loop', 'a link cycle is ELOOP, reported as dangling', 'A2 Discovery',
   op('discover'), disc([dacc(wl), nacc(wl, 'loop', state='dangling'), nacc(wl, 'loop2', state='dangling')]),
   fs={'/home/p/.claude-loop': L('/home/p/.claude-loop2'), '/home/p/.claude-loop2': L('/home/p/.claude-loop')})
mk('a2-discover-ci-darwin-link-case', 'case-insensitive fs: a link target spelled in other case still resolves', 'A2 Discovery',
   op('discover'), disc([dacc(wd), nacc(wd, 'work')]), plat='darwin',
   fs={'/Users/p/.claude-work': L('/DATA/Work'), '/data/work': D()})

# ---------------- A2 create
cspec = {'version': 1, 'createdAt': NOW}
mk('a2-create-basic', 'create makes the dir 0700 and a minimal spec file 0600', ['A2 Create', 'A3'],
   op('create', name='work'), ok({'name': 'work', 'configDir': '/home/p/.claude-work'}),
   expectFs={'/home/p/.claude-work': {'type': 'dir', 'mode': '0700'},
             '/home/p/.claude-work/.multi-account.json': {'type': 'file', 'mode': '0600', 'contentJson': cspec},
             '/home/p/.claude-work/.multi-account.json.lock': None})
mk('a2-create-darwin', 'create on darwin', 'A2 Create',
   op('create', name='work'), ok({'name': 'work', 'configDir': '/Users/p/.claude-work'}), plat='darwin',
   expectFs={'/Users/p/.claude-work': {'type': 'dir', 'mode': '0700'},
             '/Users/p/.claude-work/.multi-account.json': {'type': 'file', 'mode': '0600', 'contentJson': cspec}})
mk('a2-create-win32', 'create on win32', 'A2 Create',
   op('create', name='work'), ok({'name': 'work', 'configDir': 'C:\\Users\\p\\.claude-work'}), plat='win32',
   expectFs={'C:\\Users\\p\\.claude-work': {'type': 'dir', 'mode': '0700'},
             'C:\\Users\\p\\.claude-work\\.multi-account.json': {'type': 'file', 'mode': '0600', 'contentJson': cspec}})
mk('a2-create-invalid-name', 'invalid name', 'A2 Create',
   op('create', name='Work'), err('INVALID_NAME', None), expectFs={'/home/p/.claude-Work': None, '/home/p/.claude-work': None})
mk('a2-create-invalid-before-reserved', 'grammar is checked before the reserved list', 'A2 Create',
   op('create', name='Default'), err('INVALID_NAME', None))
for n in ('default', 'account', 'swap-backup', 'profiles'):
    mk('a2-create-reserved-' + n, 'create refuses reserved name %s' % n, ['A2 Names', 'A2 Create'],
       op('create', name=n), err('RESERVED_NAME', None), expectFs={'/home/p/.claude-' + n: None})
mk('a2-create-reserved-later-list', 'reservation uses the case-supplied list', 'A2 Names',
   op('create', name='legacy'), err('RESERVED_NAME', None), reserved=['default', 'legacy'])
mk('a2-create-exists-dir', 'create on an existing dir', 'A2 Create',
   op('create', name='work'), err('ACCOUNT_EXISTS', '/home/p/.claude-work'), fs=acct(wl, 'work'))
mk('a2-create-exists-file', 'create on an existing non-directory entry', 'A2 Create',
   op('create', name='work'), err('ACCOUNT_EXISTS', '/home/p/.claude-work'), fs={'/home/p/.claude-work': F('x')})
mk('a2-create-exists-dangling', 'create on a dangling link', 'A2 Create',
   op('create', name='work'), err('ACCOUNT_EXISTS', '/home/p/.claude-work'), fs={'/home/p/.claude-work': L('/mnt/gone')})
mk('a2-create-exists-case-variant-ci', 'case-insensitive fs: .claude-Work blocks create(work)', 'A2 Create',
   op('create', name='work'), err('ACCOUNT_EXISTS', '/Users/p/.claude-work'), plat='darwin', fs={'/Users/p/.claude-Work': D()})
mk('a2-create-case-variant-cs-ok', 'case-sensitive fs: .claude-Work does not block create(work)', 'A2 Create',
   op('create', name='work'), ok({'name': 'work', 'configDir': '/home/p/.claude-work'}), fs={'/home/p/.claude-Work': D()},
   expectFs={'/home/p/.claude-work': {'type': 'dir', 'mode': '0700'}, '/home/p/.claude-Work': {'type': 'dir'}})
mk('a2-create-then-not-reserved-other', 'a legal sibling name is created next to existing accounts', 'A2 Create',
   op('create', name='personal'), ok({'name': 'personal', 'configDir': '/home/p/.claude-personal'}), fs=acct(wl, 'work'),
   expectFs={'/home/p/.claude-personal/.multi-account.json': {'type': 'file', 'contentJson': cspec}, '/home/p/.claude-work': {'type': 'dir'}})

# ---------------- A3 spec file validity (via discover)
def spec_case(id, desc, entry, valid, hs, w=wl, plat='linux', extra=None, sec='A3'):
    d = w('.claude-work')
    p = d + w.sep + '.multi-account.json'
    fsd = {p: entry}
    fsd.update(extra or {})
    se = None if valid else {'code': 'SPEC_FILE_INVALID', 'path': p}
    mk(id, desc, sec, op('discover'), disc([dacc(w), nacc(w, 'work', hs=hs, se=se)]), plat=plat, fs=fsd)

spec_case('a3-spec-minimal', 'minimal valid spec file', F('{"version": 1}'), True, True)
spec_case('a3-spec-full-unknown-keys', 'unknown keys are fine, claims valid', F(spec(label="W", createdAt="2026-09-25T05:30:00Z", directories=["~/dev/x", "/abs/y"], a=1)), True, True)
spec_case('a3-spec-empty-directories', 'empty directories list is valid', F(spec(directories=[])), True, True)
spec_case('a3-spec-symlink-to-file', 'a link to a regular file is a valid spec file', L('/data/spec.json'), True, True, extra={'/data/spec.json': F(spec())})
spec_case('a3-spec-invalid-json', 'not JSON', F('{nope'), False, True)
spec_case('a3-spec-empty-file', 'empty file is not JSON', F(''), False, True)
spec_case('a3-spec-top-level-array', 'JSON but not an object', F('[1]'), False, True)
spec_case('a3-spec-version-2', 'version other than 1', F('{"version": 2}'), False, True)
spec_case('a3-spec-version-string', 'version "1" is not the number 1', F('{"version": "1"}'), False, True)
spec_case('a3-spec-version-missing', 'version missing', F('{"label": "x"}'), False, True)
spec_case('a3-spec-directories-not-array', 'directories must be an array', F(spec(directories='~/dev')), False, True)
spec_case('a3-spec-directories-relative', 'relative claim', F(spec(directories=['dev/x'])), False, True)
spec_case('a3-spec-directories-dot-relative', './x is relative', F(spec(directories=['./x'])), False, True)
spec_case('a3-spec-directories-tilde-user', '~user is invalid', F(spec(directories=['~bob/x'])), False, True)
spec_case('a3-spec-directories-tilde-alone', 'bare ~ is invalid (needs ~/)', F(spec(directories=['~'])), False, True)
spec_case('a3-spec-directories-non-string', 'non-string claim', F(spec(directories=['/ok', 1])), False, True)
spec_case('a3-spec-is-directory', 'a directory named .multi-account.json is invalid', D(), False, False)
spec_case('a3-spec-link-to-directory', 'link to a directory is not a regular file', L('/data/d'), False, False, extra={'/data/d': D()})
spec_case('a3-spec-dangling-link', 'dangling link is invalid, never skipped', L('/mnt/gone'), False, False)
spec_case('a3-spec-unreadable', 'unreadable spec file is invalid, never skipped', F(spec(), unreadable=True), False, True)
spec_case('a3-spec-win32-forward-slash-root-invalid', 'win32: /x has no drive so it is not absolute', F(spec(directories=['/x'])), False, True, w=ww, plat='win32')
spec_case('a3-spec-win32-drive-claim-valid', 'win32: drive absolute and ~/ claims are valid', F(spec(directories=['D:\\work', '~/dev'])), True, True, w=ww, plat='win32')
mk('a3-spec-default-valid', 'default may carry a spec file', 'A3',
   op('discover'), disc([dacc(wl, hs=True)]), fs={'/home/p/.claude/.multi-account.json': F(spec())})
mk('a3-spec-default-invalid', 'default spec file is checked like any other', 'A3',
   op('discover'),
   disc([dacc(wl, hs=True, se={'code': 'SPEC_FILE_INVALID', 'path': '/home/p/.claude/.multi-account.json'})]),
   fs={'/home/p/.claude/.multi-account.json': F('x')})
mk('a3-spec-invalid-reported-others-listed', 'an invalid spec file does not hide other accounts', 'A3',
   op('discover'),
   disc([dacc(wl), nacc(wl, 'a', hs=True, se={'code': 'SPEC_FILE_INVALID', 'path': '/home/p/.claude-a/.multi-account.json'}),
         nacc(wl, 'b', hs=True)]),
   fs={'/home/p/.claude-a/.multi-account.json': F('{'), '/home/p/.claude-b/.multi-account.json': F(spec())})
