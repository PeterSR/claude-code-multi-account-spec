package multiaccount

import (
	"strings"
)

// SpecFile returns the account's validated .multi-account.json object verbatim (A3), nil when
// there is no file, and SPEC_FILE_INVALID (path: the file) when it is invalid.
func SpecFile(in Inputs, name string) (doc map[string]any, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	a, err := w.gate(name)
	if err != nil {
		return nil, err
	}
	sp := w.readSpec(a)
	if sp.invalid {
		return nil, newError(CodeSpecFileInvalid, sp.path, "invalid spec file")
	}
	if !sp.present {
		return nil, nil
	}
	return sp.data, nil
}

// readSpecForWrite reads the spec file fresh under the lock: absent is {"version": 1}.
func (w *world) readSpecForWrite(a *acct) (doc map[string]any, present bool, path string, err error) {
	sp := w.readSpec(a)
	if sp.invalid {
		return nil, false, sp.path, newError(CodeSpecFileInvalid, sp.path, "invalid spec file")
	}
	if !sp.present {
		return map[string]any{"version": float64(1)}, false, sp.path, nil
	}
	return sp.data, true, sp.path, nil
}

// writeSpecDoc validates the document as a spec file (INVALID_ENTRY otherwise), writes it under
// the held lock and returns it as decoded back.
func (w *world) writeSpecDoc(path string, doc map[string]any) (map[string]any, error) {
	b, err := marshalPlain(doc)
	if err != nil {
		return nil, newError(CodeInvalidEntry, "", "document cannot be encoded: %v", err)
	}
	v, ok := decodeJSON(b)
	if !ok {
		return nil, newError(CodeInvalidEntry, "", "document is not valid JSON")
	}
	out, ok := w.validSpecDoc(v)
	if !ok {
		return nil, newError(CodeInvalidEntry, "", "the result is not a valid spec file")
	}
	if err := w.writeUnderLock(path, b); err != nil {
		return nil, err
	}
	return out, nil
}

// UpdateSpecFile merges keys into the account's spec file (A3), under its lock: a nil value in
// patch deletes the key, any other sets it. A missing file starts as {"version": 1}; an invalid one
// is SPEC_FILE_INVALID; a result that is not a valid spec file is INVALID_ENTRY and nothing is
// written. It returns the new object.
func UpdateSpecFile(in Inputs, name string, patch map[string]any) (doc map[string]any, err error) {
	return UpdateSpecFileValue(in, name, patch)
}

// UpdateSpecFileValue is UpdateSpecFile for a patch of unknown shape, such as decoded JSON: a
// patch that is not an object is INVALID_ENTRY (after the account gate).
func UpdateSpecFileValue(in Inputs, name string, patch any) (doc map[string]any, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	a, err := w.gate(name)
	if err != nil {
		return nil, err
	}
	p, ok := patch.(map[string]any)
	if !ok {
		return nil, newError(CodeInvalidEntry, "", "patch must be an object")
	}
	path := w.p.join(a.dir, SpecFileName)
	return w.lockedSpec(path, func() (map[string]any, error) {
		cur, _, path, err := w.readSpecForWrite(a)
		if err != nil {
			return nil, err
		}
		next := make(map[string]any, len(cur)+len(p))
		for k, v := range cur {
			next[k] = v
		}
		for k, v := range p {
			if v == nil {
				delete(next, k)
			} else {
				next[k] = v
			}
		}
		return w.writeSpecDoc(path, next)
	})
}

func (w *world) lockedSpec(path string, fn func() (map[string]any, error)) (map[string]any, error) {
	lock := path + ".lock"
	if err := w.lock(lock); err != nil {
		return nil, err
	}
	defer w.unlock(lock)
	return fn()
}

// ClaimResult is the result of Claim and Unclaim: the directories claims afterwards.
type ClaimResult struct {
	Directories []string `json:"directories"`
}

// expandDir expands a claim directory argument (absolute, or ~/ and on Windows ~\) and gives its
// stored form: "~/" for home, "~/<rest>" below home, else the expanded path.
func (w *world) expandDir(dir string) (e, stored string, ok bool) {
	e, ok = w.expandClaim(dir)
	if !ok {
		return "", "", false
	}
	home := w.p.normalize(w.in.Home)
	cmp := func(s string) string {
		if w.in.CaseInsensitive {
			return fold(s)
		}
		return s
	}
	switch {
	case cmp(e) == cmp(home):
		return e, "~/", true
	case strings.HasPrefix(cmp(e), cmp(home)+w.p.sep()) || (strings.HasSuffix(home, w.p.sep()) && strings.HasPrefix(cmp(e), cmp(home))):
		rest := e[len(strings.TrimSuffix(home, w.p.sep())):]
		rest = strings.TrimPrefix(rest, w.p.sep())
		return e, "~/" + strings.ReplaceAll(rest, w.p.sep(), "/"), true
	}
	return e, e, true
}

// sameDir reports whether two directories are the same: equal (dev, ino) after stat, or, when a
// stat fails, equal normalised paths (folded on a case-insensitive filesystem).
func (w *world) sameDir(a, b string) bool {
	sa, ea := w.fs.Stat(a)
	sb, eb := w.fs.Stat(b)
	if ea == nil && eb == nil {
		return sa.Same(sb)
	}
	a, b = w.p.normalize(a), w.p.normalize(b)
	if w.in.CaseInsensitive {
		a, b = fold(a), fold(b)
	}
	return a == b
}

func dirsOf(doc map[string]any) []string {
	out := []string{}
	if l, ok := doc["directories"].([]any); ok {
		for _, x := range l {
			if s, ok := x.(string); ok {
				out = append(out, s)
			}
		}
	}
	return out
}

// Claim adds a directory to the account's claims (A3), under the spec file's lock. dir must be
// absolute or start with ~/ (~\ on Windows), else INVALID_ENTRY. Another account that claims the
// same directory is CLAIM_CONFLICT (path: the directory), and an invalid spec file of another
// account SPEC_FILE_INVALID. A directory the account already claims changes nothing. The stored
// form is ~/<rest> below home. It returns the claims afterwards.
func Claim(in Inputs, name, dir string) (res *ClaimResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	a, err := w.gate(name)
	if err != nil {
		return nil, err
	}
	e, stored, ok := w.expandDir(dir)
	if !ok {
		return nil, newError(CodeInvalidEntry, "", "directory must be absolute or start with ~/")
	}
	for _, p := range w.primaries() {
		if p == a || p == a.rep {
			continue
		}
		sp := w.spec(p)
		if sp.invalid {
			return nil, newError(CodeSpecFileInvalid, sp.path, "invalid spec file")
		}
		if !sp.present {
			continue
		}
		for _, c := range w.claims(sp) {
			if w.sameDir(c, e) {
				return nil, newError(CodeClaimConflict, e, "%s is already claimed by %q", e, p.name)
			}
		}
	}
	path := w.p.join(a.dir, SpecFileName)
	var dirs []string
	_, err = w.lockedSpec(path, func() (map[string]any, error) {
		cur, present, path, err := w.readSpecForWrite(a)
		if err != nil {
			return nil, err
		}
		if present {
			for _, c := range w.claimsOfDoc(cur) {
				if w.sameDir(c, e) {
					dirs = dirsOf(cur)
					return cur, nil
				}
			}
		}
		next := make(map[string]any, len(cur)+1)
		for k, v := range cur {
			next[k] = v
		}
		next["directories"] = append(toAnyList(dirsOf(cur)), stored)
		out, err := w.writeSpecDoc(path, next)
		if err != nil {
			return nil, err
		}
		dirs = dirsOf(out)
		return out, nil
	})
	if err != nil {
		return nil, err
	}
	return &ClaimResult{Directories: nonNil(dirs)}, nil
}

func toAnyList(s []string) []any {
	out := make([]any, len(s))
	for i, x := range s {
		out[i] = x
	}
	return out
}

func (w *world) claimsOfDoc(doc map[string]any) []string {
	return w.claims(&specResult{data: doc})
}

// Unclaim removes every claim of the account that is the same directory as dir (A3), under the
// spec file's lock; it writes only when something was removed. It returns the claims afterwards.
func Unclaim(in Inputs, name, dir string) (res *ClaimResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	a, err := w.gate(name)
	if err != nil {
		return nil, err
	}
	e, _, ok := w.expandDir(dir)
	if !ok {
		return nil, newError(CodeInvalidEntry, "", "directory must be absolute or start with ~/")
	}
	path := w.p.join(a.dir, SpecFileName)
	dirs := []string{}
	_, err = w.lockedSpec(path, func() (map[string]any, error) {
		cur, present, path, err := w.readSpecForWrite(a)
		if err != nil {
			return nil, err
		}
		if !present {
			return cur, nil
		}
		kept := []any{}
		removed := false
		for _, s := range dirsOf(cur) {
			if x, ok := w.expandClaim(s); ok && w.sameDir(x, e) {
				removed = true
			} else {
				kept = append(kept, s)
			}
		}
		dirs = dirsOf(cur)
		if !removed {
			return cur, nil
		}
		next := make(map[string]any, len(cur))
		for k, v := range cur {
			next[k] = v
		}
		next["directories"] = kept
		out, err := w.writeSpecDoc(path, next)
		if err != nil {
			return nil, err
		}
		dirs = dirsOf(out)
		return out, nil
	})
	if err != nil {
		return nil, err
	}
	return &ClaimResult{Directories: nonNil(dirs)}, nil
}
