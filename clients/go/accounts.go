package multiaccount

import (
	"io"
	"math"
	"sort"
	"strings"
)

// CanonicalPath returns the canonical config dir of account name: nfc(join(home, ".claude-"+name)),
// or $HOME/.claude for "default". It is a pure function: symlinks are never resolved, reserved
// names are allowed and the filesystem is not touched.
//
// Only in.Home and in.Platform are used.
func CanonicalPath(in Inputs, name string) (string, error) {
	if name != DefaultName && !ValidName(name) {
		return "", newError(CodeInvalidName, "", "invalid account name %q", name)
	}
	w := &world{in: in, p: flavorFor(in.Platform)}
	return w.configHome(name), nil
}

// SpecError reports an invalid .multi-account.json.
type SpecError struct {
	Code string `json:"code"`
	Path string `json:"path"`
}

// Account is one entry of List.
type Account struct {
	Name            string     `json:"name"`
	ConfigDir       string     `json:"configDir"`
	State           string     `json:"state"`
	HasSpecFile     bool       `json:"hasSpecFile"`
	HasGlobalConfig bool       `json:"hasGlobalConfig"`
	AliasOf         *string    `json:"aliasOf"`
	SpecError       *SpecError `json:"specError"`
	Warnings        []Warning  `json:"warnings"`
}

// Conflict is a directory claimed by two or more accounts.
type Conflict struct {
	Path     string   `json:"path"`
	Accounts []string `json:"accounts"`
}

// ListResult is the result of List.
type ListResult struct {
	Accounts  []Account  `json:"accounts"`
	Conflicts []Conflict `json:"conflicts"`
	Warnings  []Warning  `json:"warnings"`
}

func strp(s string) *string { return &s }

func optStr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// acct is a discovered account.
type acct struct {
	name, dir, state string
	ident            FileInfo
	hasIdent         bool
	group            []*acct // alias group (ok accounts with one identity), nil without identity
	rep              *acct   // alias representative, nil without identity
}

// aliasOf is the representative's name when a is not the representative, else "".
func (a *acct) aliasOf() string {
	if a.rep != nil && a.rep != a {
		return a.rep.name
	}
	return ""
}

// listAccounts discovers accounts once per world.
func (w *world) listAccounts() []*acct {
	if w.listed {
		return w.accts
	}
	w.listed = true
	w.warns = []Warning{}
	w.accts = []*acct{{name: DefaultName, dir: w.configHome(DefaultName), state: StateOK}}
	names, err := w.fs.ReadDir(w.in.Home)
	if err != nil {
		names = nil
	}
	for _, n := range names {
		if !strings.HasPrefix(n, ".claude-") {
			continue
		}
		nm := n[len(".claude-"):]
		if !ValidName(nm) {
			continue
		}
		path := w.p.join(w.in.Home, n)
		l, err := w.fs.Lstat(path)
		if err != nil {
			w.accts = append(w.accts, &acct{name: nm, dir: w.canon(nm), state: StateUnreadable})
			continue
		}
		s, err := w.fs.Stat(path)
		if err != nil {
			if l.Type.IsLink() {
				st := StateDangling
				if ErrnoOf(err) == EACCES {
					st = StateUnreadable
				}
				w.accts = append(w.accts, &acct{name: nm, dir: w.canon(nm), state: st})
			}
			continue
		}
		if s.Type != TypeDir {
			w.warns = append(w.warns, warn(WarnNotADirectory, path))
			continue
		}
		w.accts = append(w.accts, &acct{name: nm, dir: w.canon(nm), state: StateOK})
	}
	var groups [][]*acct
	index := map[[2]uint64]int{}
	for _, a := range w.accts {
		if a.state != StateOK {
			continue
		}
		s, err := w.fs.Stat(a.dir)
		if err != nil {
			continue // an identity that cannot be determined never forms an alias
		}
		a.ident, a.hasIdent = s, true
		k := [2]uint64{s.Dev, s.Ino}
		if i, ok := index[k]; ok {
			groups[i] = append(groups[i], a)
		} else {
			index[k] = len(groups)
			groups = append(groups, []*acct{a})
		}
	}
	for _, g := range groups {
		// the representative is the first named member; default only when it is alone
		rep := g[0]
		for _, m := range g {
			if m.name != DefaultName {
				rep = m
				break
			}
		}
		for _, m := range g {
			m.group, m.rep = g, rep
		}
	}
	return w.accts
}

func (w *world) account(name string) *acct {
	for _, a := range w.listAccounts() {
		if a.name == name {
			return a
		}
	}
	return nil
}

// sameAccount reports whether two names are one account: equal, or ok members of one alias group.
func (w *world) sameAccount(x, y string) bool {
	if x == y {
		return true
	}
	a, b := w.account(x), w.account(y)
	return a != nil && b != nil && a.group != nil && b.group != nil && a.rep == b.rep
}

// primaries are the ok accounts that count once per alias group (the representatives).
func (w *world) primaries() []*acct {
	var out []*acct
	for _, a := range w.listAccounts() {
		if a.state == StateOK && (a.rep == nil || a.rep == a) {
			out = append(out, a)
		}
	}
	return out
}

// specResult is the outcome of reading an account's .multi-account.json.
type specResult struct {
	present bool           // false: no spec file
	invalid bool           // present but invalid
	path    string         // spec file path
	data    map[string]any // valid content
}

func (w *world) expandClaim(x any) (string, bool) {
	s, ok := x.(string)
	if !ok {
		return "", false
	}
	if w.p.isAbs(s) {
		return w.p.normalize(s), true
	}
	if strings.HasPrefix(s, "~/") || (w.p.win && strings.HasPrefix(s, `~\`)) {
		return w.p.join(w.in.Home, s[2:]), true
	}
	return "", false
}

func (w *world) spec(a *acct) *specResult {
	if r, ok := w.specs[a.name]; ok {
		return r
	}
	r := w.readSpec(a)
	w.specs[a.name] = r
	return r
}

func (w *world) readSpec(a *acct) *specResult {
	p := w.p.join(a.dir, SpecFileName)
	invalid := &specResult{present: true, invalid: true, path: p}
	if _, err := w.fs.Lstat(p); err != nil {
		if isErrno(err, ENOENT, ENOTDIR) {
			return &specResult{path: p}
		}
		return invalid
	}
	fi, err := w.fs.Stat(p)
	if err != nil || fi.Type != TypeFile {
		return invalid
	}
	f, err := w.fs.Open(p, OpenRead, 0)
	if err != nil {
		return invalid
	}
	defer f.Close()
	b, err := io.ReadAll(f)
	if err != nil {
		return invalid
	}
	v, ok := decodeJSON(b)
	if !ok {
		return invalid
	}
	data, ok := w.validSpecDoc(v)
	if !ok {
		return invalid
	}
	return &specResult{present: true, path: p, data: data}
}

// validSpecDoc applies the A3 validity rules to a decoded document: an object nested at most 100
// levels, version 1, priority an integer within +-(2^53-1), directories an array of valid claims.
func (w *world) validSpecDoc(v any) (map[string]any, bool) {
	if jsonDepth(v) > maxJSONDepth {
		return nil, false
	}
	data, ok := v.(map[string]any)
	if !ok {
		return nil, false
	}
	if ver, ok := numberValue(data["version"]); !ok || ver != 1 {
		return nil, false
	}
	if pr, has := data["priority"]; has {
		if _, ok := specPriority(pr); !ok {
			return nil, false
		}
	}
	if ds, has := data["directories"]; has {
		list, ok := ds.([]any)
		if !ok {
			return nil, false
		}
		for _, x := range list {
			if _, ok := w.expandClaim(x); !ok {
				return nil, false
			}
		}
	}
	return data, true
}

// specPriority validates a spec file priority: a number with an integer value within +-(2^53-1).
func specPriority(v any) (int64, bool) {
	f, ok := numberValue(v)
	if !ok || f != math.Trunc(f) || math.Abs(f) > 1<<53-1 {
		return 0, false
	}
	return int64(f), true
}

// claims returns the expanded claim directories of a valid spec.
func (w *world) claims(r *specResult) []string {
	var out []string
	if list, ok := r.data["directories"].([]any); ok {
		for _, x := range list {
			if e, ok := w.expandClaim(x); ok {
				out = append(out, e)
			}
		}
	}
	return out
}

// List discovers the accounts under home (A2) and reports claim conflicts.
func List(in Inputs) (res *ListResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	accts := w.listAccounts()
	res = &ListResult{Accounts: []Account{}, Conflicts: []Conflict{}, Warnings: append([]Warning{}, w.warns...)}
	for _, a := range accts {
		acc := Account{Name: a.name, ConfigDir: a.dir, State: a.state, AliasOf: optStr(a.aliasOf()), Warnings: []Warning{}}
		if a.state == StateOK {
			acc.HasSpecFile = w.isRegular(w.p.join(a.dir, SpecFileName))
			acc.HasGlobalConfig = w.isRegular(w.globalConfigPath(a.name))
			if sp := w.spec(a); sp.invalid {
				acc.SpecError = &SpecError{Code: CodeSpecFileInvalid, Path: sp.path}
			}
		}
		if a.name != DefaultName && w.isReserved(a.name) {
			acc.Warnings = append(acc.Warnings, warn(WarnReservedName, ""))
		}
		res.Accounts = append(res.Accounts, acc)
	}
	type claim struct{ path, name string }
	var order [][2]uint64
	byIdent := map[[2]uint64][]claim{}
	for _, a := range w.primaries() {
		sp := w.spec(a)
		if !sp.present || sp.invalid {
			continue
		}
		for _, e := range w.claims(sp) {
			s, err := w.fs.Stat(e)
			if err != nil {
				continue
			}
			k := [2]uint64{s.Dev, s.Ino}
			lst, seen := byIdent[k]
			if !seen {
				order = append(order, k)
			}
			dup := false
			for _, c := range lst {
				dup = dup || c.name == a.name
			}
			if !dup {
				byIdent[k] = append(lst, claim{e, a.name})
			}
		}
	}
	for _, k := range order {
		lst := byIdent[k]
		if len(lst) < 2 {
			continue
		}
		c := Conflict{Path: lst[0].path}
		for _, x := range lst {
			c.Accounts = append(c.Accounts, x.name)
		}
		res.Conflicts = append(res.Conflicts, c)
	}
	sort.SliceStable(res.Conflicts, func(i, j int) bool { return res.Conflicts[i].Path < res.Conflicts[j].Path })
	return res, nil
}

// MapResult is the result of MapConfigDir.
type MapResult struct {
	Account   *string   `json:"account"`
	Canonical bool      `json:"canonical"`
	Reason    *string   `json:"reason"`
	Warnings  []Warning `json:"warnings"`
}

// Reasons a CLAUDE_CONFIG_DIR value is not canonical.
const (
	ReasonNotNormalized       = "not-normalized"
	ReasonCaseMismatch        = "case-mismatch"
	ReasonDefaultViaConfigDir = "default-via-config-dir"
	ReasonResolvedTarget      = "resolved-target"
	ReasonForeign             = "foreign"
)

type mapping struct {
	account   string // "" for foreign
	canonical bool
	reason    string // "" for canonical
}

func (w *world) mapConfigDir(v string) mapping {
	accts := w.listAccounts()
	var named []*acct
	for _, a := range accts {
		if a.name != DefaultName && a.state == StateOK {
			named = append(named, a)
		}
	}
	for _, a := range named {
		if v == a.dir {
			return mapping{a.name, true, ""}
		}
	}
	if w.p.isAbs(v) {
		n := nfc(w.p.normalize(v))
		for _, a := range named {
			if n == a.dir {
				return mapping{a.name, false, ReasonNotNormalized}
			}
		}
		if w.in.CaseInsensitive {
			for _, a := range named {
				if fold(n) == fold(a.dir) {
					return mapping{a.name, false, ReasonCaseMismatch}
				}
			}
		}
		if n == w.configHome(DefaultName) {
			return mapping{DefaultName, false, ReasonDefaultViaConfigDir}
		}
		if rv, err := w.fs.Realpath(v); err == nil {
			// named accounts first, in name order, then default
			for _, a := range append(append([]*acct{}, named...), accts[0]) {
				if a.state != StateOK {
					continue
				}
				if ra, err := w.fs.Realpath(a.dir); err == nil && ra == rv {
					return mapping{a.name, false, ReasonResolvedTarget}
				}
			}
		}
	}
	return mapping{"", false, ReasonForeign}
}

// MapConfigDir maps a CLAUDE_CONFIG_DIR value to an account (A4 step 1 table).
func MapConfigDir(in Inputs, value string) (res *MapResult, err error) {
	defer func() { err = ioErr(err) }()
	m := newWorld(in).mapConfigDir(value)
	res = &MapResult{Account: optStr(m.account), Canonical: m.canonical, Reason: optStr(m.reason), Warnings: []Warning{}}
	if !m.canonical {
		res.Warnings = append(res.Warnings, warn(WarnNonCanonicalConfigDir, ""))
	}
	return res, nil
}
