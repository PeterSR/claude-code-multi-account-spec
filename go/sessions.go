package multiaccount

import (
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"
)

// Session statuses reported by LiveSessions.
const (
	SessionLive    = "live"
	SessionDead    = "dead"
	SessionUnknown = "unknown"
)

// Session is one entry of <config home>/sessions/<pid>.json.
type Session struct {
	PID       int     `json:"pid"`
	SessionID *string `json:"sessionId"`
	Status    string  `json:"status"`
}

// LiveSessionsResult is the result of LiveSessions.
type LiveSessionsResult struct {
	Sessions []Session `json:"sessions"`
}

// canonicalPidFile reports the pid of a session file name: ^[1-9][0-9]{0,9}\.json$ with ASCII
// digits, so that String(pid) equals the stem, as Claude Code requires.
func canonicalPidFile(name string) (int, bool) {
	stem, ok := strings.CutSuffix(name, ".json")
	if !ok || len(stem) == 0 || len(stem) > 10 || stem[0] == '0' {
		return 0, false
	}
	for i := 0; i < len(stem); i++ {
		if stem[i] < '0' || stem[i] > '9' {
			return 0, false
		}
	}
	pid, err := strconv.Atoi(stem)
	return pid, err == nil
}

func (w *world) sessions(name string) []Session {
	dir := w.p.join(w.configHome(name), "sessions")
	out := []Session{}
	names, err := w.fs.ReadDir(dir)
	if err != nil {
		return out
	}
	for _, n := range names {
		pid, ok := canonicalPidFile(n)
		if !ok {
			continue
		}
		d, ok := w.readJSONObject(w.p.join(dir, n))
		if !ok {
			continue
		}
		out = append(out, Session{PID: pid, SessionID: strField(d, "sessionId"), Status: w.sessionStatus(pid, d)})
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].PID < out[j].PID })
	return out
}

// sessionStatus decides a record's status (B3): a differing pidDomain is unknown; else a missing
// process is dead; else the start marker (procStartFt if the record has one, else procStart)
// decides live or dead; a record with no marker whose pid exists is unknown.
func (w *world) sessionStatus(pid int, d map[string]any) string {
	caller := ""
	if w.in.Processes != nil {
		caller = w.in.Processes.PidDomain()
	}
	if dom, present := d["pidDomain"]; present && dom != nil {
		if s, ok := dom.(string); !ok || s != caller {
			return SessionUnknown
		}
	}
	if w.in.Processes == nil {
		return SessionDead
	}
	p, st := w.in.Processes.Lookup(pid)
	switch st {
	case ProcNone:
		return SessionDead
	case ProcError:
		return SessionUnknown // Claude Code treats an unreadable start marker as the same process
	}
	if ft, ok := d["procStartFt"].(string); ok && ft != "" {
		return liveIf(p.StartFt != nil && *p.StartFt == ft)
	}
	if ps, ok := d["procStart"].(string); ok {
		return liveIf(p.Start != nil && *p.Start == ps)
	}
	return SessionUnknown
}

func liveIf(b bool) string {
	if b {
		return SessionLive
	}
	return SessionDead
}

// blockedBy returns an error when a session of sessions blocks: it is live, or unknown and force
// is unset. When id is non-nil only that session id counts.
func blockedBy(sessions []Session, force bool, id *string) error {
	for _, s := range sessions {
		if id != nil && (s.SessionID == nil || *s.SessionID != *id) {
			continue
		}
		switch {
		case s.Status == SessionLive:
			return newError(CodeSessionLive, "", "session with pid %d is live", s.PID)
		case s.Status == SessionUnknown && !force:
			return newError(CodeSessionLive, "", "session with pid %d is unknown (another pid domain or no start marker); pass force to override", s.PID)
		}
	}
	return nil
}

// LiveSessions lists <config home>/sessions/<pid>.json (B3). Only canonical file names count. A
// session is live when the pid exists and its start marker matches, which survives pid reuse. An
// entry whose pidDomain differs from the caller's, or that has no start marker, is unknown, never
// dead. A missing pidDomain means the caller's own. B3 is best effort: Claude Code does not
// register every process.
func LiveSessions(in Inputs, name string) (res *LiveSessionsResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	return &LiveSessionsResult{Sessions: w.sessions(name)}, nil
}

// SessionOfPidResult is the result of SessionOfPid.
type SessionOfPidResult struct {
	SessionID *string `json:"sessionId"`
}

// SessionOfPid returns the sessionId recorded for a pid in <config home>/sessions/<pid>.json, or
// nil when there is no such record, it is not an object, or the id is not a non-empty string (B3).
// A pid below 1 gives nil. No liveness check is made.
func SessionOfPid(in Inputs, name string, pid int) (res *SessionOfPidResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	out := &SessionOfPidResult{}
	if pid < 1 {
		return out, nil
	}
	d, ok := w.readJSONObject(w.p.join(w.configHome(name), "sessions", strconv.Itoa(pid)+".json"))
	if ok {
		if s, ok := d["sessionId"].(string); ok && s != "" {
			out.SessionID = &s
		}
	}
	return out, nil
}

// ProjectSession is one entry of SessionsFor.
type ProjectSession struct {
	ID    string `json:"id"`
	Mtime string `json:"mtime"`
}

// SessionsForResult is the result of SessionsFor.
type SessionsForResult struct {
	Sessions []ProjectSession `json:"sessions"`
}

// ProjectSlug is Claude Code's project folder name for a working directory: every UTF-16 code unit
// that is not [A-Za-z0-9] becomes "-"; a result longer than 200 characters is cut to 200, then "-"
// and the base 36 text of abs(h), where h is the 32-bit signed hash h = h*31 + c over the UTF-16
// code units of the original cwd. It is pure.
func ProjectSlug(cwd string) string {
	units := utf16.Encode([]rune(cwd))
	var b strings.Builder
	for _, u := range units {
		if (u >= 'a' && u <= 'z') || (u >= 'A' && u <= 'Z') || (u >= '0' && u <= '9') {
			b.WriteByte(byte(u))
		} else {
			b.WriteByte('-')
		}
	}
	s := b.String()
	if len(s) <= 200 {
		return s
	}
	var h int32
	for _, u := range units {
		h = h*31 + int32(u)
	}
	abs := int64(h)
	if abs < 0 {
		abs = -abs
	}
	return s[:200] + "-" + strconv.FormatInt(abs, 36)
}

// SessionsFor lists the session transcripts of a working directory, newest first (B4): the
// <id>.jsonl regular files (not links) with a valid session id inside
// <config home>/projects/<ProjectSlug(cwd)>. Both folders must be plain directories, else the list
// is empty. Mtime is UTC with milliseconds.
func SessionsFor(in Inputs, name, cwd string) (res *SessionsForResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	out := &SessionsForResult{Sessions: []ProjectSession{}}
	root := w.configHome(name)
	type entry struct {
		id string
		t  time.Time
	}
	var found []entry
	projects := w.p.join(root, "projects")
	d := w.p.join(projects, ProjectSlug(cwd))
	for _, p := range []string{projects, d} {
		if fi, err := w.fs.Lstat(p); err != nil || fi.Type != TypeDir {
			return out, nil
		}
	}
	names, err := w.fs.ReadDir(d)
	if err != nil {
		return out, nil
	}
	for _, n := range names {
		id, ok := strings.CutSuffix(n, ".jsonl")
		if !ok || !sessionIDPattern.MatchString(id) {
			continue
		}
		if fi, err := w.fs.Lstat(w.p.join(d, n)); err == nil && fi.Type == TypeFile {
			found = append(found, entry{id, fi.Mtime})
		}
	}
	sort.SliceStable(found, func(i, j int) bool {
		if !found[i].t.Equal(found[j].t) {
			return found[i].t.After(found[j].t)
		}
		return found[i].id < found[j].id
	})
	for _, e := range found {
		out.Sessions = append(out.Sessions, ProjectSession{ID: e.id, Mtime: e.t.UTC().Format("2006-01-02T15:04:05.000Z")})
	}
	return out, nil
}
