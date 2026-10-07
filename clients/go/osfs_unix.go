//go:build !windows

package multiaccount

import (
	"os"
	"syscall"
)

const (
	sysNoFollow = syscall.O_NOFOLLOW
	sysNonBlock = syscall.O_NONBLOCK
)

func isJunction(string) bool { return false }

func identityOf(fi os.FileInfo, _ string, _ bool) (dev, ino uint64, err error) {
	if st, ok := fi.Sys().(*syscall.Stat_t); ok {
		return uint64(st.Dev), uint64(st.Ino), nil
	}
	return 0, 0, EIO
}

func symlinkOS(target, path string, _ LinkKind) error { return os.Symlink(target, path) }
