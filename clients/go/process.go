package multiaccount

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// FromProcess fills [Inputs] from the running process: its environment, physical working
// directory, home directory (Node's os.homedir rules: $HOME if set and non-empty, else the
// password database; %USERPROFILE% on Windows), platform, user name from the OS user database,
// the real filesystem, clock and process table. On Windows it also probes whether file symlinks
// can be created. It also sets a short lock retry. It is the only place the library reads process
// globals.
func FromProcess() (Inputs, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return Inputs{}, err
	}
	if real, err := filepath.EvalSymlinks(cwd); err == nil {
		cwd = real
	}
	platform := PlatformLinux
	switch runtime.GOOS {
	case "darwin":
		platform = PlatformDarwin
	case "windows":
		platform = PlatformWin32
	}
	env := map[string]string{}
	for _, kv := range os.Environ() {
		if k, v, ok := strings.Cut(kv, "="); ok && k != "" {
			env[k] = v
		}
	}
	home := env["HOME"]
	if platform == PlatformWin32 {
		home = env["USERPROFILE"]
	}
	userName := ""
	if u, err := user.Current(); err == nil {
		userName = u.Username
		if home == "" {
			home = u.HomeDir
		}
	}
	if home == "" {
		return Inputs{}, os.ErrNotExist
	}
	in := Inputs{
		Env: env, Cwd: cwd, Home: home, Platform: platform,
		CaseInsensitive: platform != PlatformLinux,
		FS:              OSFS{}, Clock: SystemClock{}, Processes: OSProcessTable{},
		UserName: userName, LockWait: 2 * time.Second,
	}
	if platform == PlatformWin32 {
		in.NoFileSymlinks = !canCreateFileSymlink(home)
	}
	return in, nil
}

// canCreateFileSymlink creates and removes a file symlink in dir.
func canCreateFileSymlink(dir string) bool {
	probe := filepath.Join(dir, ".claude-symlink-probe.tmp."+strconv.Itoa(os.Getpid()))
	_ = os.Remove(probe)
	if err := os.Symlink("probe-target", probe); err != nil {
		return false
	}
	_ = os.Remove(probe)
	return true
}

// OSProcessTable reads the real process table and computes the pid domain and process start
// markers exactly as Claude Code does (SPEC B3).
type OSProcessTable struct{}

// PidDomain returns "linux:<trim(/etc/machine-id)>:<readlink(/proc/self/ns/pid)>" on Linux and
// WSL (an unreadable part is empty, as in Claude Code), "linux:<lower-cased host name>" on
// Windows and the literal "linux" otherwise.
func (OSProcessTable) PidDomain() string {
	switch runtime.GOOS {
	case "windows":
		h, _ := os.Hostname()
		return "linux:" + strings.ToLower(h)
	case "linux":
		id, _ := os.ReadFile("/etc/machine-id")
		ns, _ := os.Readlink("/proc/self/ns/pid")
		return "linux:" + strings.TrimSpace(string(id)) + ":" + ns
	}
	return "linux"
}

// Lookup implements [ProcessTable]. Linux: field 22 of /proc/<pid>/stat. Windows: the creation
// FILETIME as procStartFt. Elsewhere: `ps -o lstart= -p <pid>` with LC_ALL=C and TZ=UTC, trimmed.
// A missing process is ProcNone; a read error, timeout or unparseable output is ProcError.
func (OSProcessTable) Lookup(pid int) (ProcessInfo, LookupState) {
	switch runtime.GOOS {
	case "windows":
		ft, st := procStartFt(pid)
		if st != ProcFound {
			return ProcessInfo{}, st
		}
		return ProcessInfo{StartFt: &ft}, ProcFound
	case "linux":
		b, err := os.ReadFile("/proc/" + strconv.Itoa(pid) + "/stat")
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) || errors.Is(err, syscall.ESRCH) {
				return ProcessInfo{}, ProcNone
			}
			return ProcessInfo{}, ProcError
		}
		s, ok := procStatStartTime(string(b))
		if !ok {
			return ProcessInfo{}, ProcError
		}
		return ProcessInfo{Start: &s}, ProcFound
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "ps", "-o", "lstart=", "-p", strconv.Itoa(pid))
	cmd.Env = append(os.Environ(), "LC_ALL=C", "TZ=UTC")
	out, err := cmd.Output()
	s := strings.TrimSpace(string(out))
	if err != nil {
		var ee *exec.ExitError
		if errors.As(err, &ee) && ee.ExitCode() == 1 && s == "" && ctx.Err() == nil {
			return ProcessInfo{}, ProcNone
		}
		return ProcessInfo{}, ProcError
	}
	if s == "" {
		return ProcessInfo{}, ProcNone
	}
	return ProcessInfo{Start: &s}, ProcFound
}

// procStatStartTime returns field 22 (starttime) of a /proc/<pid>/stat line. The command name is
// parenthesised and may contain spaces and parentheses, so fields count from after the last ")".
func procStatStartTime(stat string) (string, bool) {
	i := strings.LastIndexByte(stat, ')')
	if i < 0 {
		return "", false
	}
	// after ")" the first field is the state (field 3), so starttime (field 22) is index 19
	f := strings.Fields(stat[i+1:])
	if len(f) < 20 {
		return "", false
	}
	return f[19], true
}
