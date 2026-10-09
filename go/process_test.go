//go:build !windows

package multiaccount

import (
	"os"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestProcStatStartTime(t *testing.T) {
	// the command name holds spaces and parentheses; starttime is field 22
	line := "1234 (a (weird) cmd) S 1 1234 1234 0 -1 4194304 100 0 0 0 1 2 0 0 20 0 1 0 12345678 1000 100 18446744073709551615"
	got, ok := procStatStartTime(line)
	if !ok || got != "12345678" {
		t.Errorf("procStatStartTime = %q, %v", got, ok)
	}
	if _, ok := procStatStartTime("garbage"); ok {
		t.Error("garbage parsed")
	}
}

func TestOSProcessTableLinux(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	pt := OSProcessTable{}
	if d := pt.PidDomain(); !strings.HasPrefix(d, "linux:") || strings.Count(d, ":") < 2 {
		t.Errorf("PidDomain = %q", d)
	}
	p, st := pt.Lookup(os.Getpid())
	if st != ProcFound || p.Start == nil || *p.Start == "" {
		t.Fatalf("Lookup(self) = %+v, %v", p, st)
	}
	if _, st := pt.Lookup(1 << 30); st != ProcNone {
		t.Error("nonexistent pid exists")
	}
}

func TestFromProcess(t *testing.T) {
	in, err := FromProcess()
	if err != nil {
		t.Fatal(err)
	}
	if in.FS == nil || in.Clock == nil || in.Processes == nil || in.Cwd == "" || in.Home == "" || in.LockWait == 0 {
		t.Errorf("incomplete inputs: %+v", in)
	}
	if runtime.GOOS == "linux" && (in.Platform != PlatformLinux || in.CaseInsensitive) {
		t.Errorf("platform = %q ci=%v", in.Platform, in.CaseInsensitive)
	}
}

func TestLiveSessionAgainstRealProcess(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("linux only")
	}
	home := resolved(t, t.TempDir())
	pt := OSProcessTable{}
	self, _ := pt.Lookup(os.Getpid())
	dir := home + "/.claude/sessions"
	if err := os.MkdirAll(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	rec := func(pid string, start string) {
		doc := `{"sessionId":"s","procStart":"` + start + `","pidDomain":"` + pt.PidDomain() + `"}`
		if err := os.WriteFile(dir+"/"+pid+".json", []byte(doc), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	pid := itoa(os.Getpid())
	rec(pid, *self.Start)
	rec("999999999", "1")
	in := Inputs{Env: map[string]string{}, Cwd: home, Home: home, Platform: PlatformLinux, FS: OSFS{}, Clock: SystemClock{}, Processes: pt}
	res, err := LiveSessions(in, "default")
	if err != nil || len(res.Sessions) != 2 {
		t.Fatalf("%+v %v", res, err)
	}
	if res.Sessions[0].Status != SessionLive || res.Sessions[1].Status != SessionDead {
		t.Errorf("statuses = %+v", res.Sessions)
	}
	rec(pid, "reused")
	res, _ = LiveSessions(in, "default")
	if res.Sessions[0].Status != SessionDead {
		t.Errorf("pid reuse not detected: %+v", res.Sessions)
	}
}

func itoa(n int) string { return fmtInt(n) }

func fmtInt(n int) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for ; n > 0; n /= 10 {
		b = append([]byte{byte('0' + n%10)}, b...)
	}
	return string(b)
}

func TestCanonicalPidFile(t *testing.T) {
	ok := map[string]int{"1.json": 1, "4242.json": 4242, "4294967295.json": 4294967295}
	for n, want := range ok {
		if got, good := canonicalPidFile(n); !good || got != want {
			t.Errorf("%s: %d %v", n, got, good)
		}
	}
	for _, n := range []string{"0123.json", "0.json", "١٢.json", "99999999999999999999.json", "1e3.json", ".json", "12.txt"} {
		if _, good := canonicalPidFile(n); good {
			t.Errorf("%q accepted", n)
		}
	}
}

func TestParseInstant(t *testing.T) {
	for _, s := range []string{"2026-10-09T14:00:00Z", "2026-10-09T16:00:00+02:00", "2026-10-09T14:00:00.5Z"} {
		if _, ok := parseInstant(s); !ok {
			t.Errorf("%q rejected", s)
		}
	}
	for _, s := range []string{"tomorrow", "2026-10-09t14:00:00Z", "2026-02-30T00:00:00Z", "2026-10-09T24:00:00Z", "2026-10-09T23:59:60Z", "2026-10-09T14:00:00z", "2026-10-09"} {
		if _, ok := parseInstant(s); ok {
			t.Errorf("%q accepted", s)
		}
	}
}

type sleepClock struct {
	now   time.Time
	slept time.Duration
}

func (c *sleepClock) Now() time.Time        { return c.now }
func (c *sleepClock) Sleep(d time.Duration) { c.slept += d }

func TestLockRetryIsBoundedAndUsesClock(t *testing.T) {
	now := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	m := NewMemFS(PlatformLinux, false, now)
	_ = m.Load(map[string]MemEntry{"/home/p/.claude-work/.multi-account-state.json.lock": {Type: TypeDir}})
	clk := &sleepClock{now: now}
	in := Inputs{Env: map[string]string{}, Cwd: "/home/p", Home: "/home/p", Platform: PlatformLinux, FS: m, Clock: clk, LockWait: time.Second}
	_, err := MarkLimited(in, "work", LimitEntry{Window: "w", Until: time.Date(2026, 10, 9, 14, 0, 0, 0, time.UTC)})
	if e, ok := err.(*Error); !ok || e.Code != CodeLockBusy {
		t.Fatalf("err = %v", err)
	}
	if clk.slept < time.Second || clk.slept > 2*time.Second {
		t.Errorf("slept %v", clk.slept)
	}
}

func TestInvalidUTF8MarkerAndSpec(t *testing.T) {
	now := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	m := NewMemFS(PlatformLinux, false, now)
	_ = m.Load(map[string]MemEntry{
		"/home/p/.claude-work":         {Type: TypeDir},
		"/home/p/proj/.claude-account": {Type: TypeFile, ContentBase64: "IyBjYWYphQp3b3JrCg=="}, // "# caf\xa9\nwork\n"
	})
	if _, err := ParseMarker(m, "/home/p/proj/.claude-account"); err == nil || err.(*Error).Code != CodeMarkerInvalid {
		t.Errorf("marker err = %v", err)
	}
}
