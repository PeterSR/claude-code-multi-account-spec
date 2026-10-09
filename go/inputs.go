package multiaccount

import (
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

// Clock is the clock seam.
type Clock interface{ Now() time.Time }

// Sleeper is an optional extension of [Clock]. When the clock implements it, lock retries wait
// through it, so a fake clock stays deterministic. A clock without it never waits.
type Sleeper interface{ Sleep(d time.Duration) }

// ClockFunc adapts a function to [Clock].
type ClockFunc func() time.Time

// Now implements [Clock].
func (f ClockFunc) Now() time.Time { return f() }

// FixedClock is a clock that always returns the same instant. It never sleeps.
type FixedClock time.Time

// Now implements [Clock].
func (c FixedClock) Now() time.Time { return time.Time(c) }

// SystemClock is the real clock.
type SystemClock struct{}

// Now implements [Clock].
func (SystemClock) Now() time.Time { return time.Now() }

// Sleep implements [Sleeper].
func (SystemClock) Sleep(d time.Duration) { time.Sleep(d) }

// ErrNoClock is returned by operations that need the time when [Inputs.Clock] is nil. The library
// never falls back to the real clock.
var ErrNoClock = errors.New("multiaccount: Inputs.Clock is required for this operation")

// ProcessInfo is what the process table knows about a running process. A nil field means the
// platform has no such start marker for it.
type ProcessInfo struct {
	// Start is the procStart marker (field 22 of /proc/<pid>/stat on Linux, ps lstart elsewhere).
	Start *string
	// StartFt is the procStartFt marker (the creation FILETIME on Windows).
	StartFt *string
}

// LookupState is the outcome of a process lookup.
type LookupState int

// Lookup outcomes.
const (
	ProcFound LookupState = iota
	ProcNone
	ProcError
)

// ProcessTable is the process table seam used by B3.
type ProcessTable interface {
	// PidDomain names the pid namespace of the caller, as Claude Code computes it (B3).
	PidDomain() string
	// Lookup returns the start markers of a process. ProcNone is a definite "no such process";
	// ProcError means the lookup itself failed (error or timeout), which B3 reports as unknown.
	Lookup(pid int) (ProcessInfo, LookupState)
}

// Inputs is everything the library knows about the world. The core reads nothing else; in
// particular it never looks at process globals or the real clock. [FromProcess] fills it from the
// running process.
type Inputs struct {
	// Env is the whole environment.
	Env map[string]string
	// Cwd is the absolute working directory. Use the physical one (realpath), never $PWD.
	Cwd string
	// Home is the home directory, used as given (joins normalise it).
	Home string
	// Platform is "linux", "darwin" or "win32". It selects the path flavour.
	Platform string
	// CaseInsensitive says whether the filesystem compares names case-insensitively.
	CaseInsensitive bool
	// FS is the filesystem. Required.
	FS FS
	// Clock supplies "now". Operations that need the time fail with [ErrNoClock] when it is nil.
	Clock Clock
	// Processes is the process table for B3. Nil means no process exists and the pid domain is "".
	Processes ProcessTable
	// Reserved overrides the reserved names. Nil means [ReservedNames].
	Reserved []string
	// UserName is the OS user name, used on macOS when $USER is unset (credential locations).
	UserName string
	// NoFileSymlinks models a platform where the process cannot create file symlinks (Windows
	// without the privilege). It makes the slot (B7) unsupported there. [FromProcess] probes it.
	NoFileSymlinks bool
	// LockWait bounds how long a held lock is retried before LOCK_BUSY. Zero means no retry. The
	// wait goes through the clock when it implements [Sleeper], so without one nothing waits.
	LockWait time.Duration
	// TempSuffix returns the "<pid>.<12 hex>" part of temp file names. Nil means the process id
	// and random bytes. Tests can set it to make writes deterministic.
	TempSuffix func() string
}

// ResolveOptions are the A4 options.
type ResolveOptions struct {
	// TrustRepoMarkers honours .claude-account files inside git working trees.
	TrustRepoMarkers bool
	// IgnoreHookEnv drops the env selection when CLAUDE_MULTI_ACCOUNT_SOURCE is "hook".
	IgnoreHookEnv bool
	// CeilingDirs stops the directory walk after any of these directories.
	CeilingDirs []string
}

//go:embed reserved.json
var reservedJSON []byte

// ReservedNames returns the reserved account names of spec/reserved.json, embedded at build.
func ReservedNames() []string {
	names, err := ParseReserved(reservedJSON)
	if err != nil {
		panic("multiaccount: embedded reserved.json: " + err.Error())
	}
	return names
}

// ParseReserved reads the names out of a spec/reserved.json document.
func ParseReserved(data []byte) ([]string, error) {
	var doc struct {
		Names []struct {
			Name string `json:"name"`
		} `json:"names"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("reserved names: %w", err)
	}
	out := make([]string, 0, len(doc.Names))
	for _, n := range doc.Names {
		out = append(out, n.Name)
	}
	return out, nil
}
