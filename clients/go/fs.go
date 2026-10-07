package multiaccount

import (
	"errors"
	"io/fs"
	"time"
)

// Errno is the error kind every FS implementation reports, so the library behaves the same on the
// in-memory fake and on the real filesystem.
type Errno string

// The errors the FS contract uses.
const (
	ENOENT    Errno = "ENOENT"
	ENOTDIR   Errno = "ENOTDIR"
	EACCES    Errno = "EACCES"
	ELOOP     Errno = "ELOOP"
	EEXIST    Errno = "EEXIST"
	EINVAL    Errno = "EINVAL"
	EISDIR    Errno = "EISDIR"
	ENOTEMPTY Errno = "ENOTEMPTY"
	EIO       Errno = "EIO"
)

func (e Errno) Error() string { return string(e) }

// Is lets errors.Is(err, fs.ErrNotExist) and friends work.
func (e Errno) Is(target error) bool {
	switch target {
	case fs.ErrNotExist:
		return e == ENOENT
	case fs.ErrExist:
		return e == EEXIST
	case fs.ErrPermission:
		return e == EACCES
	}
	return false
}

// FSError is an Errno with the operation and path that failed.
type FSError struct {
	Op   string
	Path string
	Err  Errno
}

func (e *FSError) Error() string { return e.Op + " " + e.Path + ": " + string(e.Err) }
func (e *FSError) Unwrap() error { return e.Err }

func fsErr(op, path string, e Errno) error { return &FSError{Op: op, Path: path, Err: e} }

// ErrnoOf returns the Errno inside err, or EIO when there is none.
func ErrnoOf(err error) Errno {
	var e Errno
	if errors.As(err, &e) {
		return e
	}
	return EIO
}

func isErrno(err error, codes ...Errno) bool {
	if err == nil {
		return false
	}
	got := ErrnoOf(err)
	for _, c := range codes {
		if got == c {
			return true
		}
	}
	return false
}

// FileType is the kind of a filesystem entry. A junction is reported as its own type, never as a
// symlink, so the host OS does not decide what a junction is.
type FileType string

// File types.
const (
	TypeDir      FileType = "dir"
	TypeFile     FileType = "file"
	TypeSymlink  FileType = "symlink"
	TypeJunction FileType = "junction"
	TypeFifo     FileType = "fifo"
	TypeDevice   FileType = "device"
)

// IsLink reports whether the type is a symlink or a junction.
func (t FileType) IsLink() bool { return t == TypeSymlink || t == TypeJunction }

// FileInfo is what Lstat and Stat return. (Dev, Ino) identify the object.
type FileInfo struct {
	Type  FileType
	Dev   uint64
	Ino   uint64
	Size  int64
	Mode  uint32
	Mtime time.Time
}

// Same reports whether two infos describe the same object.
func (a FileInfo) Same(b FileInfo) bool { return a.Dev == b.Dev && a.Ino == b.Ino }

// OpenFlag selects how Open opens a file.
type OpenFlag int

// Open flags. They combine with |.
const (
	OpenRead       OpenFlag = 1 << iota // read only
	OpenNoFollow                        // fail with ELOOP if the last component is a link
	OpenNonBlock                        // never block (matters for FIFOs)
	OpenCreateExcl                      // create write-only, EEXIST if present
)

// File is an open file.
type File interface {
	// Read reads up to len(p) bytes. It returns 0, io.EOF at the end.
	Read(p []byte) (int, error)
	Write(p []byte) (int, error)
	Sync() error
	Close() error
}

// LinkKind says what a new link points at (it matters on Windows).
type LinkKind int

// Link kinds.
const (
	LinkFile LinkKind = iota
	LinkDir
)

// FS is the filesystem seam. All paths are absolute in the platform's flavour. Errors carry an
// [Errno] (see [ErrnoOf]). Lstat does not follow a link in the last component; every other
// operation follows links as the OS would, except where noted.
type FS interface {
	Lstat(path string) (FileInfo, error)
	// Stat follows links in every component. The 41st hop is ELOOP.
	Stat(path string) (FileInfo, error)
	// Readlink returns the stored link text of a symlink or junction, else EINVAL.
	Readlink(path string) (string, error)
	// ReadDir returns the entry names in stored case, sorted bytewise ascending.
	ReadDir(path string) ([]string, error)
	// Realpath follows every link and returns the stored-case absolute path.
	Realpath(path string) (string, error)
	// Open opens a file. mode is used only when creating.
	Open(path string, flags OpenFlag, mode uint32) (File, error)
	Mkdir(path string, mode uint32) error
	Rename(oldPath, newPath string) error
	// Symlink creates a link at path holding target verbatim.
	Symlink(target, path string, kind LinkKind) error
	Rmdir(path string) error
	Unlink(path string) error
}
