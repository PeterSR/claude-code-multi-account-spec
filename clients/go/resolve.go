package multiaccount

// Sources of a resolution.
const (
	SourceEnv        = "env"
	SourceConfigDir  = "config-dir"
	SourceMarkerFile = "marker-file"
	SourceClaim      = "claim"
	SourceDefault    = "default"
)

// Names the spec defines.
const (
	EnvConfigDir    = "CLAUDE_CONFIG_DIR"
	EnvMultiAccount = "CLAUDE_MULTI_ACCOUNT"
	EnvSource       = "CLAUDE_MULTI_ACCOUNT_SOURCE"
	MarkerFileName  = ".claude-account"
	SpecFileName    = ".multi-account.json"
	StateFileName   = ".multi-account-state.json"
	sourceHookValue = "hook"
)

// Resolution is the result of Resolve (A4 Result). Nullable fields are pointers.
type Resolution struct {
	Account        *string    `json:"account"`
	Pool           *string    `json:"pool"`
	ConfigDir      *string    `json:"configDir"`
	Canonical      bool       `json:"canonical"`
	Reason         *string    `json:"reason"`
	Source         string     `json:"source"`
	MatchedPath    *string    `json:"matchedPath"`
	Exists         bool       `json:"exists"`
	AliasOf        *string    `json:"aliasOf"`
	Candidates     []string   `json:"candidates"`
	Applied        bool       `json:"applied"`
	GlobalConfig   *string    `json:"globalConfig"`
	LaunchEnv      *LaunchEnv `json:"launchEnv"`
	OverriddenBy   []string   `json:"overriddenBy"`
	IgnoredMarkers []string   `json:"ignoredMarkers"`
	Warnings       []Warning  `json:"warnings"`
}

// Resolve decides which account applies (A4): the environment first, then the directory walk
// from cwd (marker files and claims), then default.
func Resolve(in Inputs, opts ResolveOptions) (res *Resolution, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	var warnings []Warning
	env := map[string]string{}
	for k, v := range in.Env {
		env[k] = v
	}
	for _, k := range []string{EnvConfigDir, EnvMultiAccount, EnvSource} {
		if v, ok := env[k]; ok && v == "" {
			delete(env, k)
			warnings = append(warnings, warn(WarnEmptyEnv, ""))
		}
	}
	if opts.IgnoreHookEnv && env[EnvSource] == sourceHookValue {
		delete(env, EnvMultiAccount)
		delete(env, EnvConfigDir)
	}
	w.env = env
	m, hasM := env[EnvMultiAccount]
	v, hasV := env[EnvConfigDir]
	if hasM && !ValidName(m) {
		return nil, newError(CodeInvalidName, "", "invalid %s %q", EnvMultiAccount, m)
	}
	if hasV {
		mp := w.mapConfigDir(v)
		if hasM && !(mp.account != "" && w.sameAccount(mp.account, m)) {
			if m != DefaultName && w.p.isAbs(v) && nfc(w.p.normalize(v)) == w.canon(m) {
				if _, err := w.gate(m); err != nil {
					return nil, err
				}
			}
			return nil, newError(CodeEnvConflict, "", "%s=%q conflicts with %s=%q", EnvMultiAccount, m, EnvConfigDir, v)
		}
		return w.resolveConfigDir(v, mp, warnings)
	}
	if hasM {
		r, err := w.resolveAccount(m, SourceEnv, "", warnings, nil, "", nil)
		if err != nil {
			return nil, err
		}
		if !w.sameAccount(m, DefaultName) {
			if env["CLAUDECODE"] == "1" {
				return nil, newError(CodeEnvConflict, "", "%s=%q was not applied: claude ignores it and %s is unset", EnvMultiAccount, m, EnvConfigDir)
			}
			r.Applied = false
			r.Warnings = append(r.Warnings, warn(WarnEnvNotApplied, ""))
		}
		return r, nil
	}
	return w.walk(opts, warnings)
}

func (w *world) resolveConfigDir(v string, mp mapping, warnings []Warning) (*Resolution, error) {
	exists := false
	var gc *string
	if w.p.isAbs(v) {
		if fi, err := w.fs.Stat(v); err == nil && fi.Type == TypeDir {
			exists = true
		}
		gc = strp(w.globalConfigForHome(v))
	}
	if !mp.canonical {
		warnings = append(warnings, warn(WarnNonCanonicalConfigDir, ""))
	}
	if mp.account == "" {
		return &Resolution{
			ConfigDir: strp(v), Reason: strp(ReasonForeign), Source: SourceConfigDir, Exists: exists,
			Candidates: []string{}, Applied: true, GlobalConfig: gc,
			OverriddenBy: w.overriddenBy(v, false), IgnoredMarkers: []string{}, Warnings: nonNil(warnings),
		}, nil
	}
	r, err := w.resolveAccount(mp.account, SourceConfigDir, "", nil, nil, "", nil)
	if err != nil {
		return nil, err
	}
	r.ConfigDir, r.Canonical, r.Reason, r.Exists, r.GlobalConfig = strp(v), mp.canonical, optStr(mp.reason), exists, gc
	r.Warnings = nonNil(append(warnings, r.Warnings...))
	r.OverriddenBy = w.overriddenBy(v, false)
	return r, nil
}

func nonNil[T any](s []T) []T {
	if s == nil {
		return []T{}
	}
	return s
}

// resolveAccount builds the result for a binding to a named account or default. bindPath is the
// path reported in ACCOUNT_NOT_FOUND (the marker file or claimed directory). candidates defaults
// to [name].
func (w *world) resolveAccount(name, source, matched string, warnings []Warning, ignored []string, bindPath string, candidates []string) (*Resolution, error) {
	a, err := w.gateAt(name, bindPath)
	if err != nil {
		return nil, err
	}
	cfg := w.configHome(name)
	ws := append([]Warning{}, warnings...)
	if name != DefaultName && w.isReserved(name) {
		ws = append(ws, warn(WarnReservedName, ""))
	}
	if candidates == nil {
		candidates = []string{name}
	}
	le := w.launchEnv(name, false)
	return &Resolution{
		Account: strp(name), ConfigDir: strp(cfg), Canonical: true, Source: source,
		MatchedPath: optStr(matched), Exists: true, AliasOf: optStr(a.aliasOf()),
		Candidates: candidates, Applied: true, GlobalConfig: strp(w.globalConfigPath(name)), LaunchEnv: &le,
		OverriddenBy: w.overriddenBy(cfg, false), IgnoredMarkers: nonNil(ignored), Warnings: ws,
	}, nil
}

// bind binds a marker: the first entry must exist (the gate), later entries that are not usable
// accounts only add a CANDIDATE_UNAVAILABLE warning. The first entry is launched.
func (w *world) bind(names []string, source, matched string, warnings []Warning, ignored []string, bindPath string) (*Resolution, error) {
	if _, err := w.gateAt(names[0], bindPath); err != nil {
		return nil, err
	}
	ws := append([]Warning{}, warnings...)
	for _, n := range names[1:] {
		if !w.usable(n) {
			ws = append(ws, warn(WarnCandidateUnavailable, w.entryPath(n)))
		}
	}
	return w.resolveAccount(names[0], source, matched, ws, ignored, bindPath, append([]string{}, names...))
}

// usable reports whether name is default or a discovered ok account.
func (w *world) usable(name string) bool {
	if name == DefaultName {
		return true
	}
	a := w.account(name)
	return a != nil && a.state == StateOK
}

// walk is A4 step 2 and step 3.
func (w *world) walk(opts ResolveOptions, warnings []Warning) (*Resolution, error) {
	var levels []string
	ceil := make([]string, len(opts.CeilingDirs))
	for i, c := range opts.CeilingDirs {
		ceil[i] = w.p.normalize(c)
	}
	for cur := w.p.normalize(w.in.Cwd); ; {
		levels = append(levels, cur)
		stop := false
		for _, c := range ceil {
			if cur == c || (w.in.CaseInsensitive && fold(cur) == fold(c)) {
				stop = true
			}
		}
		par, ok := w.p.parent(cur)
		if stop || !ok {
			break
		}
		cur = par
	}
	git := make([]bool, len(levels))
	for i, d := range levels {
		_, err := w.fs.Lstat(w.p.join(d, ".git"))
		git[i] = err == nil
	}
	inGitTree := func(i int) bool {
		for _, g := range git[i:] {
			if g {
				return true
			}
		}
		return false
	}
	var ignored []string
	claimsLoaded := false
	var claimants []*acct
	for i, d := range levels {
		mp := w.p.join(d, MarkerFileName)
		candidate := false
		if _, err := w.fs.Lstat(mp); err == nil {
			if fi, err := w.fs.Stat(mp); err == nil {
				candidate = fi.Type != TypeDir
			}
		}
		if candidate && !opts.TrustRepoMarkers && inGitTree(i) {
			ignored = append(ignored, mp)
			warnings = append(warnings, warn(WarnMarkerIgnoredInRepo, mp))
		} else {
			m, err := parseMarker(w.fs, mp)
			if err != nil {
				return nil, err
			}
			switch m.Kind {
			case MarkerAccount, MarkerDefault, MarkerList:
				return w.bind(m.Candidates, SourceMarkerFile, mp, warnings, ignored, mp)
			case MarkerPool:
				return &Resolution{
					Pool: m.Pool, Source: SourceMarkerFile, MatchedPath: strp(mp), Candidates: []string{}, Applied: true,
					OverriddenBy: w.overriddenBy("", false), IgnoredMarkers: nonNil(ignored), Warnings: nonNil(warnings),
				}, nil
			}
		}
		if !claimsLoaded {
			claimsLoaded = true
			for _, a := range w.listAccounts() {
				if a.state != StateOK {
					continue
				}
				if sp := w.spec(a); sp.invalid {
					return nil, newError(CodeSpecFileInvalid, sp.path, "invalid spec file")
				}
			}
			claimants = w.primaries()
		}
		var hit []string
		if ls, err := w.fs.Stat(d); err == nil {
			for _, a := range claimants {
				sp := w.spec(a)
				if !sp.present || sp.invalid {
					continue
				}
				for _, e := range w.claims(sp) {
					if s, err := w.fs.Stat(e); err == nil && s.Same(ls) {
						hit = append(hit, a.name)
						break
					}
				}
			}
		}
		if len(hit) > 1 {
			return nil, newError(CodeClaimConflict, d, "directory claimed by %v", hit)
		}
		if len(hit) == 1 {
			return w.resolveAccount(hit[0], SourceClaim, d, warnings, ignored, d, nil)
		}
	}
	return w.resolveAccount(DefaultName, SourceDefault, "", warnings, ignored, "", nil)
}
