package multiaccount

import "encoding/json"

// CreateResult is the result of Create.
type CreateResult struct {
	Name      string `json:"name"`
	ConfigDir string `json:"configDir"`
}

// Create makes $HOME/.claude-<name> (mode 0700) and writes a minimal .multi-account.json (A2).
// It fails with INVALID_NAME, RESERVED_NAME or ACCOUNT_EXISTS. Logging in is left to claude.
func Create(in Inputs, name string) (res *CreateResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if err := w.needClock(); err != nil {
		return nil, err
	}
	if err := w.checkName(name); err != nil {
		return nil, err
	}
	if w.isReserved(name) {
		return nil, newError(CodeReservedName, "", "account name %q is reserved", name)
	}
	p := w.entryPath(name)
	if _, err := w.fs.Lstat(p); err == nil {
		return nil, newError(CodeAccountExists, p, "account %q exists", name)
	}
	if err := w.fs.Mkdir(p, 0o700); err != nil {
		return nil, err
	}
	doc, _ := json.Marshal(map[string]any{"version": 1, "createdAt": w.now.UTC().Format("2006-01-02T15:04:05Z")})
	if err := w.atomicWrite(w.p.join(p, SpecFileName), doc); err != nil {
		return nil, err
	}
	return &CreateResult{Name: name, ConfigDir: w.canon(name)}, nil
}
