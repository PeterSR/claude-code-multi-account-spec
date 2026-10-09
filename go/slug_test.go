package multiaccount

import (
	"strings"
	"testing"
	"time"
)

func TestProjectSlug(t *testing.T) {
	if got := ProjectSlug("/home/p/my proj"); got != "-home-p-my-proj" {
		t.Errorf("slug = %q", got)
	}
	long := "/" + strings.Repeat("a", 250)
	got := ProjectSlug(long)
	if !strings.HasPrefix(got, "-"+strings.Repeat("a", 199)+"-") || len(got) <= 201 {
		t.Errorf("long slug = %q", got)
	}
}

func TestMarkLimitedKeepsOffset(t *testing.T) {
	now := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	m := NewMemFS(PlatformLinux, false, now)
	_ = m.Load(map[string]MemEntry{"/home/p/.claude-work": {Type: TypeDir}})
	in := Inputs{Env: map[string]string{}, Cwd: "/home/p", Home: "/home/p", Platform: PlatformLinux, FS: m, Clock: FixedClock(now)}
	until, _ := ParseInstant("2026-10-09T17:00:00+02:00")
	res, err := MarkLimited(in, "work", LimitEntry{Window: "w", Until: until})
	if err != nil || len(res.Limits) != 1 || res.Limits[0].(map[string]any)["until"] != "2026-10-09T17:00:00+02:00" {
		t.Fatalf("%+v %v", res, err)
	}
	if _, err := MarkLimited(in, "work", LimitEntry{}); err == nil || err.(*Error).Code != CodeInvalidEntry {
		t.Errorf("err = %v", err)
	}
}
