// Command conformance-runner reads one conformance case (conformance/FORMAT.md) on stdin, builds
// the fake world from it, runs the op through the public API and writes one JSON object to stdout.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"

	ma "github.com/PeterSR/claude-code-multi-account-spec/clients/go"
)

type testCase struct {
	Platform        string                 `json:"platform"`
	CaseInsensitive bool                   `json:"caseInsensitive"`
	Home            string                 `json:"home"`
	Cwd             string                 `json:"cwd"`
	Env             map[string]string      `json:"env"`
	Options         caseOptions            `json:"options"`
	Now             time.Time              `json:"now"`
	Reserved        *[]string              `json:"reserved"`
	FS              map[string]ma.MemEntry `json:"fs"`
	Processes       map[string]procEntry   `json:"processes"`
	CallerPidDomain *string                `json:"callerPidDomain"`
	Op              struct {
		Name string          `json:"name"`
		Args json.RawMessage `json:"args"`
	} `json:"op"`
}

type caseOptions struct {
	TrustRepoMarkers  bool     `json:"trustRepoMarkers"`
	IgnoreHookEnv     bool     `json:"ignoreHookEnv"`
	CeilingDirs       []string `json:"ceilingDirs"`
	CanCreateSymlinks *bool    `json:"canCreateSymlinks"`
	UserName          string   `json:"userName"`
}

type procEntry struct {
	ProcStart   *string `json:"procStart"`
	ProcStartFt *string `json:"procStartFt"`
	PidDomain   string  `json:"pidDomain"`
	LookupError bool    `json:"lookupError"`
}

type fakeProcs struct {
	domain string
	table  map[string]procEntry
}

func (f fakeProcs) PidDomain() string { return f.domain }
func (f fakeProcs) Lookup(pid int) (ma.ProcessInfo, ma.LookupState) {
	e, ok := f.table[strconv.Itoa(pid)]
	switch {
	case !ok:
		return ma.ProcessInfo{}, ma.ProcNone
	case e.LookupError:
		return ma.ProcessInfo{}, ma.ProcError
	}
	return ma.ProcessInfo{Start: e.ProcStart, StartFt: e.ProcStartFt}, ma.ProcFound
}

var writeOps = map[string]bool{"create": true, "handover_session": true, "mark_limited": true, "clear_limited": true, "adopt": true, "activate": true, "update_spec_file": true, "claim": true, "unclaim": true}

func main() {
	var c testCase
	if err := json.NewDecoder(os.Stdin).Decode(&c); err != nil {
		fmt.Fprintln(os.Stderr, "bad case:", err)
		os.Exit(2)
	}
	fsys := ma.NewMemFS(c.Platform, c.CaseInsensitive, c.Now)
	fsys.EnsureRoot(c.Home)
	fsys.EnsureRoot(c.Cwd)
	if err := fsys.Load(c.FS); err != nil {
		fmt.Fprintln(os.Stderr, "bad fs:", err)
		os.Exit(2)
	}
	domain := "host-1"
	if c.CallerPidDomain != nil {
		domain = *c.CallerPidDomain
	}
	var reserved []string
	if c.Reserved != nil {
		reserved = *c.Reserved
	} else {
		root := os.Getenv("CCMA_REPO_ROOT")
		if root == "" {
			root = "."
		}
		if b, err := os.ReadFile(filepath.Join(root, "spec", "reserved.json")); err == nil {
			reserved, _ = ma.ParseReserved(b)
		}
	}
	in := ma.Inputs{
		Env: c.Env, Cwd: c.Cwd, Home: c.Home, Platform: c.Platform, CaseInsensitive: c.CaseInsensitive,
		FS: fsys, Clock: ma.FixedClock(c.Now), Processes: fakeProcs{domain, c.Processes},
		Reserved: reserved, UserName: c.Options.UserName,
		NoFileSymlinks: c.Options.CanCreateSymlinks != nil && !*c.Options.CanCreateSymlinks,
		TempSuffix:     func() string { return "1234.abcdef012345" },
	}
	opts := ma.ResolveOptions{TrustRepoMarkers: c.Options.TrustRepoMarkers, IgnoreHookEnv: c.Options.IgnoreHookEnv, CeilingDirs: c.Options.CeilingDirs}

	res, err := run(in, opts, c.Now, c.Op.Name, c.Op.Args)
	out := map[string]any{}
	if err != nil {
		var e *ma.Error
		if !errors.As(err, &e) {
			e = &ma.Error{Code: "INTERNAL", Message: err.Error()}
		}
		var path any
		if e.Path != "" {
			path = e.Path
		}
		out["error"] = map[string]any{"code": e.Code, "path": path, "message": e.Message}
	} else {
		out["result"] = res
	}
	if writeOps[c.Op.Name] {
		out["fs"] = fsys.Dump()
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(in ma.Inputs, opts ma.ResolveOptions, now time.Time, op string, raw json.RawMessage) (any, error) {
	var a struct {
		Name               string         `json:"name"`
		Path               string         `json:"path"`
		Value              string         `json:"value"`
		ClearAuthOverrides bool           `json:"clearAuthOverrides"`
		ID                 string         `json:"id"`
		From               string         `json:"from"`
		To                 string         `json:"to"`
		Overwrite          bool           `json:"overwrite"`
		Force              bool           `json:"force"`
		Entry              map[string]any `json:"entry"`
		Window             string         `json:"window"`
		Model              *string        `json:"model"`
		Pool               string         `json:"pool"`
		Current            string         `json:"current"`
		Candidates         []string       `json:"candidates"`
		Resolve            bool           `json:"resolve"`
		Pid                any            `json:"pid"`
		Cwd                string         `json:"cwd"`
		Dir                string         `json:"dir"`
		Patch              any            `json:"patch"`
	}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &a); err != nil {
			return nil, err
		}
	}
	model := ""
	if a.Model != nil {
		model = *a.Model
	}
	switch op {
	case "canonical_path":
		p, err := ma.CanonicalPath(in, a.Name)
		if err != nil {
			return nil, err
		}
		return map[string]string{"path": p}, nil
	case "discover":
		return ma.List(in)
	case "resolve":
		return ma.Resolve(in, opts)
	case "map_config_dir":
		return ma.MapConfigDir(in, a.Value)
	case "parse_marker":
		return ma.ParseMarker(in.FS, a.Path)
	case "create":
		return ma.Create(in, a.Name)
	case "env":
		return ma.Env(in, a.Name, ma.EnvOptions{ClearAuthOverrides: a.ClearAuthOverrides})
	case "credential_locations":
		return ma.CredentialLocations(in, a.Name)
	case "identity", "usage":
		if a.Resolve {
			r, err := ma.Resolve(in, opts)
			if err != nil {
				return nil, err
			}
			if op == "identity" {
				return ma.IdentityFor(in, r)
			}
			return ma.UsageFor(in, r)
		}
		if op == "identity" {
			return ma.Identity(in, a.Name)
		}
		return ma.Usage(in, a.Name)
	case "credentials":
		return ma.Credentials(in, a.Name)
	case "live_sessions":
		return ma.LiveSessions(in, a.Name)
	case "handover_session":
		return ma.HandoverSession(in, a.ID, a.From, a.To, ma.HandoverOptions{Overwrite: a.Overwrite, Force: a.Force})
	case "mark_limited":
		return ma.MarkLimited(in, a.Name, limitEntry(a.Entry))
	case "clear_limited":
		return ma.ClearLimited(in, a.Name, a.Window, a.Model)
	case "available":
		return ma.Available(in, a.Name, now, model)
	case "pick":
		return ma.Pick(in, a.Pool, now, model)
	case "next":
		return ma.Next(in, a.Pool, a.Current, now, model)
	case "pick_from":
		return ma.PickFrom(in, a.Candidates, now, model)
	case "next_from":
		return ma.NextFrom(in, a.Candidates, a.Current, now, model)
	case "limits":
		return ma.Limits(in, a.Name)
	case "available_at":
		return ma.AvailableAt(in, a.Name, now, model)
	case "pool_members":
		return ma.PoolMembers(in, a.Pool)
	case "session_of_pid":
		pid := 0
		if f, ok := a.Pid.(float64); ok && f == float64(int(f)) {
			pid = int(f)
		}
		return ma.SessionOfPid(in, a.Name, pid)
	case "project_slug":
		return map[string]string{"slug": ma.ProjectSlug(a.Cwd)}, nil
	case "sessions_for":
		return ma.SessionsFor(in, a.Name, a.Cwd)
	case "spec_file":
		return ma.SpecFile(in, a.Name)
	case "update_spec_file":
		return ma.UpdateSpecFileValue(in, a.Name, a.Patch)
	case "claim":
		return ma.Claim(in, a.Name, a.Dir)
	case "unclaim":
		return ma.Unclaim(in, a.Name, a.Dir)
	case "slot":
		return ma.Slot(in)
	case "adopt":
		return ma.Adopt(in, a.Name, ma.SlotOptions{Force: a.Force})
	case "activate":
		return ma.Activate(in, a.Name, ma.SlotOptions{Force: a.Force})
	}
	return nil, &ma.Error{Code: "UNSUPPORTED_OP", Message: "op not implemented: " + op}
}

// limitEntry converts a case's entry to the typed LimitEntry. An entry that cannot be converted
// (wrong types, an until that is not an RFC 3339 instant) becomes an entry with an empty window,
// which the library rejects as INVALID_ENTRY after the account gate.
func limitEntry(e map[string]any) ma.LimitEntry {
	bad := ma.LimitEntry{}
	win, ok := e["window"].(string)
	if !ok {
		return bad
	}
	out := ma.LimitEntry{Window: win}
	switch mv := e["model"].(type) {
	case nil:
	case string:
		out.Model = &mv
	default:
		return bad
	}
	us, ok := e["until"].(string)
	if !ok {
		return bad
	}
	if out.Until, ok = ma.ParseInstant(us); !ok {
		return bad
	}
	for k, dst := range map[string]*string{"reason": &out.Reason, "updatedBy": &out.UpdatedBy} {
		if v, has := e[k]; has {
			s, ok := v.(string)
			if !ok {
				return bad
			}
			*dst = s
		}
	}
	return out
}
