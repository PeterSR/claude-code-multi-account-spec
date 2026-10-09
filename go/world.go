package multiaccount

import (
	"bytes"
	"encoding/json"
	"io"
	"math"
	"slices"
	"strconv"
	"time"
	"unicode/utf8"
)

// Account states of a discovered entry.
const (
	StateOK         = "ok"
	StateDangling   = "dangling"
	StateUnreadable = "unreadable"
)

// DefaultName is the account that lives at $HOME/.claude.
const DefaultName = "default"

// maxJSONDepth is the nesting limit of spec and state files (the top-level object is level 1).
const maxJSONDepth = 100

// world is the per-call view of Inputs with memoised discovery.
type world struct {
	in       Inputs
	p        pathFlavor
	fs       FS
	env      map[string]string
	reserved []string
	hasClock bool
	now      time.Time

	listed bool
	accts  []*acct
	warns  []Warning
	specs  map[string]*specResult
}

func newWorld(in Inputs) *world {
	w := &world{in: in, p: flavorFor(in.Platform), fs: in.FS, env: in.Env, reserved: in.Reserved, specs: map[string]*specResult{}}
	if w.env == nil {
		w.env = map[string]string{}
	}
	if w.reserved == nil {
		w.reserved = ReservedNames()
	}
	if in.Clock != nil {
		w.hasClock = true
		w.now = in.Clock.Now()
	}
	return w
}

// needClock fails with ErrNoClock when the inputs carry no clock.
func (w *world) needClock() error {
	if !w.hasClock {
		return ErrNoClock
	}
	return nil
}

func (w *world) isReserved(name string) bool { return slices.Contains(w.reserved, name) }

// canon is the canonical path of a named account: nfc(join(home, ".claude-" + name)).
func (w *world) canon(name string) string { return nfc(w.p.join(w.in.Home, ".claude-"+name)) }

// entryPath is the (non NFC) path of an account entry under home, used in error paths.
func (w *world) entryPath(name string) string { return w.p.join(w.in.Home, ".claude-"+name) }

// configHome of an account: $HOME/.claude for default, else the canonical path.
func (w *world) configHome(name string) string {
	if name == DefaultName {
		return w.p.join(w.in.Home, ".claude")
	}
	return w.canon(name)
}

func (w *world) suffix() string {
	if w.env["CLAUDE_CODE_CUSTOM_OAUTH_URL"] != "" {
		return "-custom-oauth"
	}
	return ""
}

func (w *world) isRegular(path string) bool {
	fi, err := w.fs.Stat(path)
	return err == nil && fi.Type == TypeFile
}

// readFileFlags reads a whole regular file (after Stat follows links). ok is false on any failure.
func (w *world) readFileFlags(path string, flags OpenFlag) ([]byte, bool) {
	fi, err := w.fs.Stat(path)
	if err != nil || fi.Type != TypeFile {
		return nil, false
	}
	f, err := w.fs.Open(path, flags, 0)
	if err != nil {
		return nil, false
	}
	defer f.Close()
	b, err := io.ReadAll(f)
	if err != nil {
		return nil, false
	}
	return b, true
}

func (w *world) readFile(path string) ([]byte, bool) { return w.readFileFlags(path, OpenRead) }

// decodeJSON parses one strict UTF-8 JSON document. Numbers stay [json.Number].
func decodeJSON(b []byte) (any, bool) {
	if !utf8.Valid(b) {
		return nil, false
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	var v any
	if dec.Decode(&v) != nil {
		return nil, false
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, false
	}
	return v, true
}

// jsonDepth is the nesting depth of v; the top-level container is level 1.
func jsonDepth(v any) int {
	best := 0
	var rec func(x any, d int)
	rec = func(x any, d int) {
		if d > best {
			best = d
		}
		if d > maxJSONDepth+1 {
			return
		}
		switch t := x.(type) {
		case map[string]any:
			for _, c := range t {
				rec(c, d+1)
			}
		case []any:
			for _, c := range t {
				rec(c, d+1)
			}
		}
	}
	switch v.(type) {
	case map[string]any, []any:
		rec(v, 1)
	}
	return best
}

// readJSONObject reads a strict UTF-8 JSON object file; any failure or a non-object is "no data".
func (w *world) readJSONObject(path string) (map[string]any, bool) {
	b, ok := w.readFile(path)
	if !ok {
		return nil, false
	}
	v, ok := decodeJSON(b)
	if !ok {
		return nil, false
	}
	m, ok := v.(map[string]any)
	return m, ok
}

// numberValue converts a decoded JSON value to a float64 when it is a number.
func numberValue(v any) (float64, bool) {
	n, ok := v.(json.Number)
	if !ok {
		return 0, false
	}
	f, err := strconv.ParseFloat(string(n), 64)
	if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
		return 0, false
	}
	return f, true
}

// marshalPlain marshals without HTML escaping.
func marshalPlain(v any) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return bytes.TrimRight(buf.Bytes(), "\n"), nil
}

// globalConfigForHome is the effective global config file of a config home (A1): a legacy
// <home>/.config.json if it is a regular file, else .claude<suffix>.json inside it.
func (w *world) globalConfigForHome(ch string) string {
	legacy := w.p.join(ch, ".config.json")
	if w.isRegular(legacy) {
		return legacy
	}
	return w.p.join(ch, ".claude"+w.suffix()+".json")
}

// globalConfigPath is the effective global config file of an account: for default it sits in
// $HOME (with the legacy file taking precedence inside ~/.claude), for others in the config home.
func (w *world) globalConfigPath(name string) string {
	ch := w.configHome(name)
	legacy := w.p.join(ch, ".config.json")
	if w.isRegular(legacy) {
		return legacy
	}
	base := ".claude" + w.suffix() + ".json"
	if name == DefaultName {
		return w.p.join(w.in.Home, base)
	}
	return w.p.join(ch, base)
}

// gate validates an account name for ops that read or write inside the account.
func (w *world) gate(name string) (*acct, error) { return w.gateAt(name, "") }

// gateAt is gate with the path reported in ACCOUNT_NOT_FOUND (a marker file or claimed directory).
func (w *world) gateAt(name, bindPath string) (*acct, error) {
	if !ValidName(name) {
		return nil, newError(CodeInvalidName, "", "invalid account name %q", name)
	}
	if name == DefaultName {
		return w.account(DefaultName), nil
	}
	p := w.entryPath(name)
	a := w.account(name)
	if a == nil {
		if bindPath != "" {
			p = bindPath
		}
		return nil, newError(CodeAccountNotFound, p, "account %q not found", name)
	}
	if a.state != StateOK {
		return nil, newError(CodeAccountUnavailable, w.entryPath(name), "account %q is %s", name, a.state)
	}
	return a, nil
}

func (w *world) checkName(name string) error {
	if !ValidName(name) {
		return newError(CodeInvalidName, "", "invalid account name %q", name)
	}
	return nil
}

// checkSlotName accepts a valid name other than default (B7).
func (w *world) checkSlotName(name string) error {
	if !ValidName(name) || name == DefaultName {
		return newError(CodeInvalidName, "", "a named account is required, got %q", name)
	}
	return nil
}
