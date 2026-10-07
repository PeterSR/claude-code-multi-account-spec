package multiaccount

import (
	"crypto/rand"
	"encoding/hex"
	"os"
	"strconv"
	"time"
)

const (
	lockStaleAfter = 10 * time.Second
	lockPoll       = 50 * time.Millisecond
)

func (w *world) tempSuffix() string {
	if w.in.TempSuffix != nil {
		return w.in.TempSuffix()
	}
	var b [6]byte
	_, _ = rand.Read(b[:])
	return strconv.Itoa(os.Getpid()) + "." + hex.EncodeToString(b[:])
}

// tryLock takes a proper-lockfile compatible lock once: mkdir <path>. A lock more than 10 s old is
// stale and is taken over by removing it and trying mkdir once more. Anything else that holds the
// lock, including a lost takeover race, is LOCK_BUSY.
func (w *world) tryLock(path string) error {
	err := w.fs.Mkdir(path, 0o700)
	if err == nil {
		return nil
	}
	if ErrnoOf(err) != EEXIST {
		return err
	}
	busy := newError(CodeLockBusy, path, "lock is held")
	fi, serr := w.fs.Lstat(path)
	if serr != nil || w.in.Clock.Now().Sub(fi.Mtime) <= lockStaleAfter {
		return busy
	}
	if err := w.fs.Rmdir(path); err != nil && ErrnoOf(err) != ENOENT {
		return err
	}
	if err := w.fs.Mkdir(path, 0o700); err != nil {
		if ErrnoOf(err) == EEXIST {
			return busy
		}
		return err
	}
	return nil
}

// lock takes the lock, retrying a held lock for at most Inputs.LockWait through the clock's
// [Sleeper], then gives up with LOCK_BUSY.
func (w *world) lock(path string) error {
	if err := w.needClock(); err != nil {
		return err
	}
	sleeper, _ := w.in.Clock.(Sleeper)
	var waited time.Duration
	for {
		err := w.tryLock(path)
		if err == nil {
			return nil
		}
		if e, ok := err.(*Error); !ok || e.Code != CodeLockBusy || sleeper == nil || waited >= w.in.LockWait {
			return err
		}
		sleeper.Sleep(lockPoll)
		waited += lockPoll
	}
}

func (w *world) unlock(path string) { _ = w.fs.Rmdir(path) }

// atomicWrite writes data to path under <path>.lock following the A3 file safety rules.
func (w *world) atomicWrite(path string, data []byte) error {
	lock := path + ".lock"
	if err := w.lock(lock); err != nil {
		return err
	}
	defer w.unlock(lock)
	return w.writeUnderLock(path, data)
}

// writeUnderLock writes path while the caller holds its lock: a symlink is followed one hop and
// the link kept (a link with a missing target is written through), the data goes to a temp file
// created with O_EXCL (mode 0600) in the target's directory, is synced and renamed over the
// target. The temp file is removed on error.
func (w *world) writeUnderLock(path string, data []byte) error {
	target := path
	if l, err := w.fs.Lstat(path); err == nil && l.Type.IsLink() {
		t, err := w.fs.Readlink(path)
		if err != nil {
			return err
		}
		if w.p.isAbs(t) {
			target = w.p.normalize(t)
		} else {
			target = w.p.join(w.p.dirname(path), t)
		}
	}
	tmp := target + ".tmp." + w.tempSuffix()
	f, err := w.fs.Open(tmp, OpenCreateExcl, 0o600)
	if err != nil {
		return err
	}
	if _, err = f.Write(data); err == nil {
		err = f.Sync()
	}
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	if err == nil {
		err = w.fs.Rename(tmp, target)
	}
	if err != nil {
		_ = w.fs.Unlink(tmp)
	}
	return err
}
