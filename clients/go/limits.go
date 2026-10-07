package multiaccount

import (
	"regexp"
	"strconv"
	"time"
)

// LimitsResult is the result of MarkLimited and ClearLimited: the limits as written. Entries are
// kept exactly as read (entries written by other tools keep their own keys), so they are generic
// JSON values.
type LimitsResult struct {
	Limits []any `json:"limits"`
}

// AvailableResult is the result of Available.
type AvailableResult struct {
	Available bool `json:"available"`
}

var rfc3339 = regexp.MustCompile(`^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})$`)

// parseInstant parses an RFC 3339 instant with upper-case T and Z or a numeric offset, optional
// fractional seconds, a real calendar date, hour 0 to 23, minute and second 0 to 59 (no leap
// second) and offset hour 0 to 23 and minute 0 to 59.
func parseInstant(s string) (time.Time, bool) {
	m := rfc3339.FindStringSubmatch(s)
	if m == nil {
		return time.Time{}, false
	}
	n := func(i int) int { v, _ := strconv.Atoi(m[i]); return v }
	y, mo, d, h, mi, se := n(1), n(2), n(3), n(4), n(5), n(6)
	if h > 23 || mi > 59 || se > 59 {
		return time.Time{}, false
	}
	nsec := 0
	if f := m[7]; f != "" {
		nsec, _ = strconv.Atoi((f[1:] + "000000000")[:9])
	}
	off := 0
	if z := m[8]; z != "Z" {
		oh, _ := strconv.Atoi(z[1:3])
		om, _ := strconv.Atoi(z[4:6])
		if oh > 23 || om > 59 {
			return time.Time{}, false
		}
		off = oh*3600 + om*60
		if z[0] == '-' {
			off = -off
		}
	}
	t := time.Date(y, time.Month(mo), d, h, mi, se, nsec, time.UTC)
	if t.Year() != y || int(t.Month()) != mo || t.Day() != d {
		return time.Time{}, false // not a real calendar date
	}
	// the same instant, shown with the offset it was written with
	return t.Add(-time.Duration(off) * time.Second).In(time.FixedZone("", off)), true
}

// ParseInstant parses an RFC 3339 instant as B5 requires: upper-case T and Z or a numeric offset,
// optional fractional seconds, a real calendar date, no leap second. The result keeps the offset
// it was written with.
func ParseInstant(s string) (time.Time, bool) { return parseInstant(s) }

func (w *world) statePath(name string) string {
	return w.p.join(w.configHome(name), StateFileName)
}

// stateDoc checks a decoded state document: an object, version 1, limits absent or an array, not
// nested deeper than 100 levels.
func stateDoc(v any, ok bool) (map[string]any, bool) {
	if !ok || jsonDepth(v) > maxJSONDepth {
		return nil, false
	}
	d, isObj := v.(map[string]any)
	if !isObj {
		return nil, false
	}
	if ver, ok := numberValue(d["version"]); !ok || ver != 1 {
		return nil, false
	}
	if l, has := d["limits"]; has {
		if _, ok := l.([]any); !ok {
			return nil, false
		}
	}
	return d, true
}

func limitsOf(d map[string]any) []any {
	l, _ := d["limits"].([]any)
	return l
}

// readState is for reads: anything not understood is an empty state.
func (w *world) readState(name string) []any {
	b, ok := w.readFile(w.statePath(name))
	if !ok {
		return nil
	}
	v, ok := decodeJSON(b)
	d, ok := stateDoc(v, ok)
	if !ok {
		return nil
	}
	return limitsOf(d)
}

// readStateForWrite is for writes: a missing file (or a link to a missing target) is empty, a file
// that is present but not understood is STATE_FILE_INVALID.
func (w *world) readStateForWrite(name string) (map[string]any, error) {
	sp := w.statePath(name)
	invalid := newError(CodeStateFileInvalid, sp, "state file is not understood and will not be overwritten")
	fi, err := w.fs.Stat(sp)
	if err != nil {
		if isErrno(err, ENOENT, ENOTDIR) {
			return map[string]any{"version": 1, "limits": []any{}}, nil
		}
		return nil, invalid
	}
	if fi.Type != TypeFile {
		return nil, invalid
	}
	b, ok := w.readFile(sp)
	if !ok {
		return nil, invalid
	}
	v, ok := decodeJSON(b)
	d, ok := stateDoc(v, ok)
	if !ok {
		return nil, invalid
	}
	if _, has := d["limits"]; !has {
		d["limits"] = []any{}
	}
	return d, nil
}

// entryKey is the (window, model) key of an entry. Entries that are not objects, lack a string
// window or carry a model that is neither null nor a string have no key and never match.
func entryKey(x any) (window string, model *string, ok bool) {
	m, isObj := x.(map[string]any)
	if !isObj {
		return "", nil, false
	}
	window, ok = m["window"].(string)
	if !ok {
		return "", nil, false
	}
	switch mv := m["model"].(type) {
	case nil:
		return window, nil, true
	case string:
		return window, &mv, true
	}
	return "", nil, false
}

func sameKey(w1 string, m1 *string, w2 string, m2 *string) bool {
	if w1 != w2 || (m1 == nil) != (m2 == nil) {
		return false
	}
	return m1 == nil || *m1 == *m2
}

func entryUntil(x any) (time.Time, bool) {
	m, ok := x.(map[string]any)
	if !ok {
		return time.Time{}, false
	}
	s, ok := m["until"].(string)
	if !ok {
		return time.Time{}, false
	}
	return parseInstant(s)
}

func validEntry(e map[string]any) bool {
	if s, ok := e["window"].(string); !ok || s == "" {
		return false
	}
	if mv, has := e["model"]; has && mv != nil {
		if s, ok := mv.(string); !ok || s == "" {
			return false
		}
	}
	if s, ok := e["until"].(string); !ok {
		return false
	} else if _, ok := parseInstant(s); !ok {
		return false
	}
	for _, k := range []string{"reason", "updatedBy"} {
		if v, has := e[k]; has {
			if _, ok := v.(string); !ok {
				return false
			}
		}
	}
	return true
}

// dropPast removes entries whose readable until is at or before now.
func (w *world) dropPast(limits []any) []any {
	out := []any{}
	for _, x := range limits {
		if u, ok := entryUntil(x); ok && !u.After(w.now) {
			continue
		}
		out = append(out, x)
	}
	return out
}

// lockedStateWrite runs fn under the state file lock; fn returns the document to write.
func (w *world) lockedStateWrite(name string, fn func(doc map[string]any) ([]any, error)) ([]any, error) {
	sp := w.statePath(name)
	lock := sp + ".lock"
	if err := w.lock(lock); err != nil {
		return nil, err
	}
	defer w.unlock(lock)
	doc, err := w.readStateForWrite(name)
	if err != nil {
		return nil, err
	}
	limits, err := fn(doc)
	if err != nil {
		return nil, err
	}
	doc["version"] = 1
	doc["limits"] = limits
	b, err := marshalPlain(doc)
	if err != nil {
		return nil, err
	}
	if err := w.writeUnderLock(sp, b); err != nil {
		return nil, err
	}
	return limits, nil
}

// LimitEntry is the entry MarkLimited records. Model is nil for a window covering all models.
// Until keeps the offset it carries when written (RFC 3339, UTC as Z). Empty Reason and UpdatedBy
// are left out of the file.
type LimitEntry struct {
	Window    string
	Model     *string
	Until     time.Time
	Reason    string
	UpdatedBy string
}

// MarkLimited records a limit (B5) under the A3 lock: read, merge, write, holding the lock across
// all three. An empty Window, an empty non-nil Model or a zero Until is INVALID_ENTRY (checked
// after the account gate). Merging keeps the new entry for a key when its until is equal or later and drops
// entries already past. Everything else in the file is preserved as read, and a state file that is
// present but not understood is never overwritten (STATE_FILE_INVALID). updatedAt is set to the
// clock's now.
func MarkLimited(in Inputs, name string, entry LimitEntry) (res *LimitsResult, err error) {
	m := map[string]any{"window": entry.Window, "model": nil, "until": ""}
	if entry.Model != nil {
		m["model"] = *entry.Model
	}
	if !entry.Until.IsZero() {
		m["until"] = entry.Until.Format(time.RFC3339Nano)
	}
	if entry.Reason != "" {
		m["reason"] = entry.Reason
	}
	if entry.UpdatedBy != "" {
		m["updatedBy"] = entry.UpdatedBy
	}
	return markLimited(in, name, m)
}

func markLimited(in Inputs, name string, entry map[string]any) (res *LimitsResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	if !validEntry(entry) {
		return nil, newError(CodeInvalidEntry, "", "invalid limit entry")
	}
	if err := w.needClock(); err != nil {
		return nil, err
	}
	e := make(map[string]any, len(entry)+2)
	for k, v := range entry {
		e[k] = v
	}
	e["updatedAt"] = w.now.UTC().Format("2006-01-02T15:04:05Z")
	if _, has := e["model"]; !has {
		e["model"] = nil
	}
	ew, em, _ := entryKey(e)
	nu, _ := parseInstant(e["until"].(string))
	limits, err := w.lockedStateWrite(name, func(doc map[string]any) ([]any, error) {
		lim := limitsOf(doc)
		merged := false
		for i, o := range lim {
			if ow, om, ok := entryKey(o); ok && sameKey(ew, em, ow, om) {
				if ou, ok := entryUntil(o); !ok || !nu.Before(ou) {
					lim[i] = e
				}
				merged = true
				break
			}
		}
		if !merged {
			lim = append(lim, e)
		}
		return w.dropPast(lim), nil
	})
	if err != nil {
		return nil, err
	}
	return &LimitsResult{Limits: limits}, nil
}

// ClearLimited removes the limit for (window, model) and drops entries already past (B5). With no
// state file nothing is written. model nil means a window covering all models.
func ClearLimited(in Inputs, name, window string, model *string) (res *LimitsResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	if _, err := w.fs.Lstat(w.statePath(name)); err != nil {
		return &LimitsResult{Limits: []any{}}, nil
	}
	if err := w.needClock(); err != nil {
		return nil, err
	}
	limits, err := w.lockedStateWrite(name, func(doc map[string]any) ([]any, error) {
		kept := []any{}
		for _, x := range limitsOf(doc) {
			if xw, xm, ok := entryKey(x); ok && sameKey(xw, xm, window, model) {
				continue
			}
			kept = append(kept, x)
		}
		return w.dropPast(kept), nil
	})
	if err != nil {
		return nil, err
	}
	return &LimitsResult{Limits: limits}, nil
}

// isAvailable is B5 availability: model is "" for all-models limits only.
func (w *world) isAvailable(name string, now time.Time, model string) bool {
	for _, x := range w.readState(name) {
		if !appliesTo(x, model) {
			continue
		}
		if u, ok := entryUntil(x); ok && u.After(now) {
			return false
		}
	}
	return true
}

// Available reports whether no limit applying to model runs past now (B5). A limit applies when
// its model is null or equals model; with an empty model only all-models limits apply. A state
// file that is not understood counts as empty.
func Available(in Inputs, name string, now time.Time, model string) (res *AvailableResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	return &AvailableResult{Available: w.isAvailable(name, now, model)}, nil
}

// LimitInfo is one entry of Limits: the state file entry as stored, with missing strings as nil.
type LimitInfo struct {
	Window    string  `json:"window"`
	Model     *string `json:"model"`
	Until     string  `json:"until"`
	Reason    *string `json:"reason"`
	UpdatedBy *string `json:"updatedBy"`
	UpdatedAt *string `json:"updatedAt"`
}

// LimitsListResult is the result of Limits.
type LimitsListResult struct {
	Limits []LimitInfo `json:"limits"`
}

// Limits lists the entries of the account's state file in file order, past ones included (B5). Only
// entries that are objects with a string window and a readable until are listed. A state file that
// is missing or not understood has none. Nothing is written.
func Limits(in Inputs, name string) (res *LimitsListResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	out := []LimitInfo{}
	for _, x := range w.readState(name) {
		m, ok := x.(map[string]any)
		if !ok {
			continue
		}
		win, ok := m["window"].(string)
		if !ok {
			continue
		}
		until, ok := m["until"].(string)
		if _, good := parseInstant(until); !ok || !good {
			continue
		}
		out = append(out, LimitInfo{Window: win, Model: strField(m, "model"), Until: until,
			Reason: strField(m, "reason"), UpdatedBy: strField(m, "updatedBy"), UpdatedAt: strField(m, "updatedAt")})
	}
	return &LimitsListResult{Limits: out}, nil
}

// AvailableAtResult is the result of AvailableAt. AvailableAt is nil when the account is available
// now, else the latest applying until as UTC, with milliseconds only when non-zero.
type AvailableAtResult struct {
	AvailableAt *string `json:"availableAt"`
}

// AvailableAt reports when the account is next available for model (B5): nil when no applying
// entry has until after now, else the latest such until. Entries apply as in [Available].
func AvailableAt(in Inputs, name string, now time.Time, model string) (res *AvailableAtResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	var latest time.Time
	found := false
	for _, x := range w.readState(name) {
		if !appliesTo(x, model) {
			continue
		}
		if u, ok := entryUntil(x); ok && u.After(now) && (!found || u.After(latest)) {
			latest, found = u, true
		}
	}
	out := &AvailableAtResult{}
	if found {
		u := latest.UTC()
		layout := "2006-01-02T15:04:05Z"
		if u.Nanosecond()/1e6 != 0 {
			layout = "2006-01-02T15:04:05.000Z"
			u = u.Truncate(time.Millisecond)
		}
		out.AvailableAt = strp(u.Format(layout))
	}
	return out, nil
}

// appliesTo reports whether a state entry applies to model ("" means all-models limits only).
func appliesTo(x any, model string) bool {
	m, ok := x.(map[string]any)
	if !ok {
		return false
	}
	if mv := m["model"]; mv != nil {
		s, ok := mv.(string)
		return ok && model != "" && s == model
	}
	return true
}
