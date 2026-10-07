package multiaccount

import "strings"

// Slot states (B7).
const (
	SlotUnmanaged   = "unmanaged"
	SlotManaged     = "managed"
	SlotBroken      = "broken"
	SlotUnsupported = "unsupported"
)

// SlotInfo is the result of Slot, Adopt and Activate. Name is set only for a managed slot.
type SlotInfo struct {
	State string  `json:"state"`
	Name  *string `json:"name"`
}

// SlotOptions are the options of Adopt and Activate.
type SlotOptions struct {
	// Force proceeds although B3 reports an unknown session. It never overrides a live one.
	Force bool
}

func (w *world) slotPaths() (l, j string) {
	return w.p.join(w.in.Home, ".claude"), w.p.join(w.in.Home, ".claude.json")
}

// linkTarget resolves a link's stored target: absolute as is, relative against $HOME.
func (w *world) linkTarget(target string) string {
	if w.p.isAbs(target) {
		return w.p.normalize(target)
	}
	return w.p.join(w.in.Home, target)
}

func (w *world) slot() SlotInfo {
	l, j := w.slotPaths()
	if w.in.Platform == PlatformDarwin ||
		(w.in.Platform == PlatformWin32 && (w.credmanInUse(j) || w.in.NoFileSymlinks)) {
		return SlotInfo{State: SlotUnsupported}
	}
	broken := SlotInfo{State: SlotBroken}
	li, err := w.fs.Lstat(l)
	if err != nil {
		if isErrno(err, ENOENT, ENOTDIR) {
			return SlotInfo{State: SlotUnmanaged}
		}
		return broken
	}
	if li.Type == TypeDir {
		return SlotInfo{State: SlotUnmanaged}
	}
	if !li.Type.IsLink() {
		return broken
	}
	tg, err := w.fs.Readlink(l)
	if err != nil {
		return broken
	}
	t := w.linkTarget(tg)
	name, ok := strings.CutPrefix(t, w.p.join(w.in.Home, ".claude-"))
	if !ok || !ValidName(name) || name == DefaultName || w.p.join(w.in.Home, ".claude-"+name) != t {
		return broken
	}
	if ti, err := w.fs.Stat(t); err != nil || ti.Type != TypeDir {
		return broken
	}
	ji, err := w.fs.Lstat(j)
	if err != nil || ji.Type != TypeSymlink {
		return broken
	}
	jt, err := w.fs.Readlink(j)
	if err != nil {
		return broken
	}
	want := w.p.join(t, ".claude.json")
	jt = w.linkTarget(jt)
	if jt != want {
		return broken
	}
	if fi, err := w.fs.Lstat(jt); err != nil {
		if !isErrno(err, ENOENT, ENOTDIR) {
			return broken
		}
	} else if fi.Type != TypeFile {
		return broken
	}
	if ci, err := w.fs.Lstat(w.p.join(t, ".credentials.json")); err == nil && ci.Type.IsLink() {
		return broken
	}
	return SlotInfo{State: SlotManaged, Name: strp(name)}
}

// Slot reports the state of the active slot, ~/.claude and ~/.claude.json as links (B7).
func Slot(in Inputs) (res *SlotInfo, err error) {
	defer func() { err = ioErr(err) }()
	s := newWorld(in).slot()
	return &s, nil
}

// lstatOrNil is Lstat where a missing entry is (nil, nil).
func (w *world) lstatOrNil(path string) (*FileInfo, error) {
	fi, err := w.fs.Lstat(path)
	if err != nil {
		if isErrno(err, ENOENT, ENOTDIR) {
			return nil, nil
		}
		return nil, err
	}
	return &fi, nil
}

// probeSymlinks checks that links can be created, before anything is moved.
func (w *world) probeSymlinks() error {
	p := w.p.join(w.in.Home, ".claude-slot-probe.tmp."+w.tempSuffix())
	if err := w.fs.Symlink("probe-target", p, LinkFile); err != nil {
		if w.p.win {
			return newError(CodeSlotUnsupported, p, "cannot create symlinks: %v", err)
		}
		return &Error{Code: CodeIOError, Path: p, Message: "cannot create symlinks: " + err.Error(), cause: err}
	}
	return w.fs.Unlink(p)
}

// Adopt turns an unmanaged slot into a managed one: it moves ~/.claude to ~/.claude-<name> (or
// creates that directory when ~/.claude does not exist) and ~/.claude.json into it, then creates
// both links (B7). It runs under ~/.claude-slot.lock, refuses while default has a live (or
// unknown, unless forced) session, verifies that links can be created before moving anything and
// rolls every step back if a later one fails. No credential is rewritten. It returns the
// recomputed slot.
func Adopt(in Inputs, name string, opts SlotOptions) (res *SlotInfo, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	s := w.slot()
	if s.State == SlotUnsupported {
		return nil, newError(CodeSlotUnsupported, "", "the login does not follow a link on this platform")
	}
	if err := w.checkSlotName(name); err != nil {
		return nil, err
	}
	if w.isReserved(name) {
		return nil, newError(CodeReservedName, "", "account name %q is reserved", name)
	}
	if s.State != SlotUnmanaged {
		return nil, newError(CodeSlotState, "", "slot is %s, want %s", s.State, SlotUnmanaged)
	}
	a := w.entryPath(name)
	if _, err := w.fs.Lstat(a); err == nil {
		return nil, newError(CodeAccountExists, a, "account %q exists", name)
	}
	l, j := w.slotPaths()
	li, err := w.lstatOrNil(l)
	if err != nil {
		return nil, err
	}
	ji, err := w.lstatOrNil(j)
	if err != nil {
		return nil, err
	}
	inner := w.p.join(l, ".claude.json")
	var ii *FileInfo
	if li != nil {
		if ii, err = w.lstatOrNil(inner); err != nil {
			return nil, err
		}
	}
	if ji != nil && ii != nil {
		return nil, newError(CodeSlotConflict, inner, "both %s and %s exist", j, inner)
	}
	if ji != nil && ji.Type != TypeFile {
		return nil, newError(CodeSlotTargetInvalid, j, "%s is not a regular file", j)
	}
	if ji == nil && ii != nil && ii.Type != TypeFile {
		return nil, newError(CodeSlotTargetInvalid, inner, "%s is not a regular file", inner)
	}
	if li != nil {
		cred := w.p.join(l, ".credentials.json")
		if ci, err := w.lstatOrNil(cred); err != nil {
			return nil, err
		} else if ci != nil && ci.Type.IsLink() {
			return nil, newError(CodeSlotTargetInvalid, cred, "%s is a link", cred)
		}
	}
	lock := w.p.join(w.in.Home, ".claude-slot.lock")
	if err := w.lock(lock); err != nil {
		return nil, err
	}
	defer w.unlock(lock)
	if err := blockedBy(w.sessions(DefaultName), opts.Force, nil); err != nil {
		return nil, err
	}
	if err := w.probeSymlinks(); err != nil {
		return nil, err
	}
	aj := w.p.join(a, ".claude.json")
	var undo []func()
	rollback := func() {
		for i := len(undo) - 1; i >= 0; i-- {
			undo[i]()
		}
	}
	fail := func(err error) (*SlotInfo, error) { rollback(); return nil, err }
	if li != nil {
		if err := w.fs.Rename(l, a); err != nil {
			return fail(err)
		}
		undo = append(undo, func() { _ = w.fs.Rename(a, l) })
	} else {
		if err := w.fs.Mkdir(a, 0o700); err != nil {
			return fail(err)
		}
		undo = append(undo, func() { _ = w.fs.Rmdir(a) })
	}
	if ji != nil {
		if err := w.fs.Rename(j, aj); err != nil {
			return fail(err)
		}
		undo = append(undo, func() { _ = w.fs.Rename(aj, j) })
	}
	if err := w.fs.Symlink(a, l, LinkDir); err != nil {
		return fail(err)
	}
	undo = append(undo, func() { _ = w.removeLink(l) })
	if err := w.fs.Symlink(aj, j, LinkFile); err != nil {
		return fail(err)
	}
	r := w.slot()
	return &r, nil
}

// removeLink removes a symlink or junction, never its target.
func (w *world) removeLink(path string) error {
	if fi, err := w.fs.Lstat(path); err == nil && fi.Type == TypeJunction {
		return w.fs.Rmdir(path)
	}
	return w.fs.Unlink(path)
}

// Activate re-points a managed slot at account name (B7). Under ~/.claude-slot.lock it refuses
// while the current slot account has a live (or unknown, unless forced) session, then replaces
// ~/.claude.json first and ~/.claude second. Where renames can replace a link each link is created
// under a temp name and renamed over the old one. On Windows a junction cannot be replaced by a
// rename, so ~/.claude is removed and created again, which leaves a short gap in which it does
// not exist. It returns the recomputed slot.
func Activate(in Inputs, name string, opts SlotOptions) (res *SlotInfo, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	s := w.slot()
	if s.State == SlotUnsupported {
		return nil, newError(CodeSlotUnsupported, "", "the login does not follow a link on this platform")
	}
	if err := w.checkSlotName(name); err != nil {
		return nil, err
	}
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	if s.State != SlotManaged {
		return nil, newError(CodeSlotState, "", "slot is %s, want %s", s.State, SlotManaged)
	}
	a := w.configHome(name)
	cred := w.p.join(a, ".credentials.json")
	if ci, err := w.lstatOrNil(cred); err != nil {
		return nil, err
	} else if ci != nil && ci.Type.IsLink() {
		return nil, newError(CodeSlotTargetInvalid, cred, "%s is a link", cred)
	}
	aj := w.p.join(a, ".claude.json")
	if ci, err := w.lstatOrNil(aj); err != nil {
		return nil, err
	} else if ci != nil && ci.Type != TypeFile {
		return nil, newError(CodeSlotTargetInvalid, aj, "%s is not a regular file", aj)
	}
	lock := w.p.join(w.in.Home, ".claude-slot.lock")
	if err := w.lock(lock); err != nil {
		return nil, err
	}
	defer w.unlock(lock)
	if err := blockedBy(w.sessions(*s.Name), opts.Force, nil); err != nil {
		return nil, err
	}
	l, j := w.slotPaths()
	if err := w.replaceLink(aj, j, LinkFile, false); err != nil {
		return nil, err
	}
	if err := w.replaceLink(a, l, LinkDir, w.p.win); err != nil {
		return nil, err
	}
	r := w.slot()
	return &r, nil
}

// replaceLink points path at target. By default a fresh link is created under a temp name and
// renamed over path. With removeFirst (a Windows junction) path is removed and created again; if
// the create fails the old link is restored.
func (w *world) replaceLink(target, path string, kind LinkKind, removeFirst bool) error {
	if removeFirst {
		old, _ := w.fs.Readlink(path)
		if err := w.removeLink(path); err != nil {
			return err
		}
		if err := w.fs.Symlink(target, path, kind); err != nil {
			if old != "" {
				_ = w.fs.Symlink(old, path, kind)
			}
			return err
		}
		return nil
	}
	tmp := path + ".tmp." + w.tempSuffix()
	if err := w.fs.Symlink(target, tmp, kind); err != nil {
		return err
	}
	if err := w.fs.Rename(tmp, path); err != nil {
		_ = w.removeLink(tmp)
		return err
	}
	return nil
}
