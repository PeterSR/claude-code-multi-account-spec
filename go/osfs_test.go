//go:build !windows

package multiaccount

import (
	"io"
	"os"
	"path/filepath"
	"reflect"
	"syscall"
	"testing"
)

func write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestOSFSLinksAndIdentity(t *testing.T) {
	dir := t.TempDir()
	fsys := OSFS{}
	real := filepath.Join(dir, "real")
	if err := os.Mkdir(real, 0o755); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "link")
	if err := fsys.Symlink(real, link, LinkDir); err != nil {
		t.Fatal(err)
	}
	if err := fsys.Symlink(filepath.Join(dir, "missing"), filepath.Join(dir, "dangling"), LinkDir); err != nil {
		t.Fatal(err)
	}

	l, err := fsys.Lstat(link)
	if err != nil || l.Type != TypeSymlink {
		t.Fatalf("Lstat(link) = %+v, %v; want symlink", l, err)
	}
	s, err := fsys.Stat(link)
	if err != nil || s.Type != TypeDir {
		t.Fatalf("Stat(link) = %+v, %v; want dir", s, err)
	}
	r, _ := fsys.Stat(real)
	if !s.Same(r) {
		t.Errorf("link and target should share identity: %+v vs %+v", s, r)
	}
	if _, err := fsys.Stat(filepath.Join(dir, "dangling")); ErrnoOf(err) != ENOENT {
		t.Errorf("Stat(dangling) error = %v, want ENOENT", err)
	}
	if tgt, err := fsys.Readlink(link); err != nil || tgt != real {
		t.Errorf("Readlink = %q, %v", tgt, err)
	}
	if _, err := fsys.Readlink(real); ErrnoOf(err) != EINVAL {
		t.Errorf("Readlink(non-link) error = %v, want EINVAL", err)
	}
	if rp, err := fsys.Realpath(link); err != nil || rp != resolved(t, real) {
		t.Errorf("Realpath = %q, %v; want %q", rp, err, resolved(t, real))
	}
}

func resolved(t *testing.T, p string) string {
	t.Helper()
	r, err := filepath.EvalSymlinks(p)
	if err != nil {
		t.Fatal(err)
	}
	return r
}

func TestOSFSLinkLoopIsELOOP(t *testing.T) {
	dir := t.TempDir()
	a, b := filepath.Join(dir, "a"), filepath.Join(dir, "b")
	_ = os.Symlink(b, a)
	_ = os.Symlink(a, b)
	if _, err := (OSFS{}).Stat(a); ErrnoOf(err) != ELOOP {
		t.Errorf("Stat(loop) error = %v, want ELOOP", err)
	}
	if _, err := (OSFS{}).Realpath(a); ErrnoOf(err) != ELOOP {
		t.Errorf("Realpath(loop) error = %v, want ELOOP", err)
	}
}

func TestOSFSReadDirSorted(t *testing.T) {
	dir := t.TempDir()
	for _, n := range []string{"b", "a", "B", ".claude-x"} {
		write(t, filepath.Join(dir, n), "")
	}
	got, err := (OSFS{}).ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{".claude-x", "B", "a", "b"}; !reflect.DeepEqual(got, want) {
		t.Errorf("ReadDir = %v, want %v", got, want)
	}
	if _, err := (OSFS{}).ReadDir(filepath.Join(dir, "a")); ErrnoOf(err) != ENOTDIR {
		t.Errorf("ReadDir(file) error = %v, want ENOTDIR", err)
	}
}

func TestOSFSOpenNoFollow(t *testing.T) {
	dir := t.TempDir()
	fsys := OSFS{}
	target := filepath.Join(dir, "real.json")
	write(t, target, "secret")
	link := filepath.Join(dir, ".credentials.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if _, err := fsys.Open(link, OpenRead|OpenNoFollow, 0); ErrnoOf(err) != ELOOP {
		t.Errorf("Open(link, NoFollow) error = %v, want ELOOP", err)
	}
	f, err := fsys.Open(link, OpenRead, 0)
	if err != nil {
		t.Fatalf("Open(link) without NoFollow: %v", err)
	}
	b, _ := io.ReadAll(f)
	f.Close()
	if string(b) != "secret" {
		t.Errorf("read %q", b)
	}
	if _, err := fsys.Open(dir, OpenRead, 0); err == nil {
		// opening works on Linux, reading a directory must fail with EISDIR
		f, _ := fsys.Open(dir, OpenRead, 0)
		if _, err := f.Read(make([]byte, 1)); ErrnoOf(err) != EISDIR {
			t.Errorf("Read(dir) error = %v, want EISDIR", err)
		}
		f.Close()
	}
}

func TestOSFSFifoOpensNonBlocking(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "fifo")
	if err := syscall.Mkfifo(p, 0o600); err != nil {
		t.Skip("mkfifo:", err)
	}
	fi, err := (OSFS{}).Stat(p)
	if err != nil || fi.Type != TypeFifo {
		t.Fatalf("Stat(fifo) = %+v, %v", fi, err)
	}
	f, err := (OSFS{}).Open(p, OpenRead|OpenNonBlock, 0)
	if err != nil {
		t.Fatalf("Open(fifo, NonBlock) blocked or failed: %v", err)
	}
	f.Close()
}

func TestOSFSCreateExclMkdirRenameRemove(t *testing.T) {
	dir := t.TempDir()
	fsys := OSFS{}
	d := filepath.Join(dir, "acct")
	if err := fsys.Mkdir(d, 0o700); err != nil {
		t.Fatal(err)
	}
	if fi, _ := fsys.Lstat(d); fi.Mode != 0o700 {
		t.Errorf("mode = %o, want 700", fi.Mode)
	}
	if err := fsys.Mkdir(d, 0o700); ErrnoOf(err) != EEXIST {
		t.Errorf("second Mkdir error = %v, want EEXIST", err)
	}
	tmp, dst := filepath.Join(d, "f.tmp.1.abc"), filepath.Join(d, "f")
	f, err := fsys.Open(tmp, OpenCreateExcl, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	f.Write([]byte("x"))
	f.Sync()
	f.Close()
	if _, err := fsys.Open(tmp, OpenCreateExcl, 0o600); ErrnoOf(err) != EEXIST {
		t.Errorf("second create error = %v, want EEXIST", err)
	}
	if err := fsys.Rename(tmp, dst); err != nil {
		t.Fatal(err)
	}
	if err := fsys.Rmdir(d); ErrnoOf(err) != ENOTEMPTY {
		t.Errorf("Rmdir(non-empty) error = %v, want ENOTEMPTY", err)
	}
	if err := fsys.Unlink(dst); err != nil {
		t.Fatal(err)
	}
	if err := fsys.Rmdir(d); err != nil {
		t.Fatal(err)
	}
}

// The library on the real filesystem: create an account, then find it.
func TestOSFSEndToEnd(t *testing.T) {
	home := resolved(t, t.TempDir())
	in := Inputs{Env: map[string]string{}, Cwd: home, Home: home, Platform: PlatformLinux, FS: OSFS{}, Clock: SystemClock{}}
	if _, err := Create(in, "work"); err != nil {
		t.Fatal(err)
	}
	if _, err := Create(in, "work"); err == nil || err.(*Error).Code != CodeAccountExists {
		t.Errorf("second Create error = %v", err)
	}
	l, err := List(in)
	if err != nil || len(l.Accounts) != 2 || !l.Accounts[1].HasSpecFile {
		t.Fatalf("List = %+v, %v", l, err)
	}
	in.Env = map[string]string{"CLAUDE_MULTI_ACCOUNT": "work"}
	r, err := Resolve(in, ResolveOptions{})
	if err != nil || *r.Account != "work" || *r.ConfigDir != filepath.Join(home, ".claude-work") {
		t.Fatalf("Resolve = %+v, %v", r, err)
	}
}

func TestOSFSIdentityErrorIsNotZero(t *testing.T) {
	// a failing stat must be an error, never a (0, 0) identity that equals another failure
	if _, err := (OSFS{}).Stat(filepath.Join(t.TempDir(), "missing")); err == nil {
		t.Fatal("expected error")
	}
}

func TestOSFSRmdirUnlinkTypes(t *testing.T) {
	dir := t.TempDir()
	f := filepath.Join(dir, "f")
	write(t, f, "x")
	if err := (OSFS{}).Rmdir(f); ErrnoOf(err) != ENOTDIR {
		t.Errorf("Rmdir(file) = %v", err)
	}
	if err := (OSFS{}).Unlink(dir); ErrnoOf(err) != EISDIR {
		t.Errorf("Unlink(dir) = %v", err)
	}
}

func TestIOErrorMapping(t *testing.T) {
	err := ioErr(fsErr("open", "/x", EIO))
	e, ok := err.(*Error)
	if !ok || e.Code != CodeIOError || e.Path != "/x" {
		t.Errorf("ioErr = %#v", err)
	}
}
