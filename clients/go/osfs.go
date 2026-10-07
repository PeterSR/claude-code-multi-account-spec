package multiaccount

import (
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
)

// OSFS is the [FS] implementation backed by the real operating system.
//
// Link following and the 40 hop limit are the OS's own. On Windows a junction (a mount point
// reparse point; other reparse points are not junctions) is reported as [TypeJunction], a
// directory [LinkDir] link is created as a real junction, and OpenNoFollow is emulated with an
// Lstat check because the OS has no O_NOFOLLOW. Windows cannot rename over a junction, so callers
// remove it first.
type OSFS struct{}

func toErrno(err error) Errno {
	if err == nil {
		return ""
	}
	var en Errno
	if errors.As(err, &en) {
		return en
	}
	var sys syscall.Errno
	if errors.As(err, &sys) {
		switch {
		case errors.Is(sys, syscall.ENOENT):
			return ENOENT
		case errors.Is(sys, syscall.ENOTDIR):
			return ENOTDIR
		case errors.Is(sys, syscall.EACCES), errors.Is(sys, syscall.EPERM):
			return EACCES
		case errors.Is(sys, syscall.ELOOP):
			return ELOOP
		case errors.Is(sys, syscall.EEXIST):
			return EEXIST
		case errors.Is(sys, syscall.EINVAL):
			return EINVAL
		case errors.Is(sys, syscall.EISDIR):
			return EISDIR
		case errors.Is(sys, syscall.ENOTEMPTY):
			return ENOTEMPTY
		}
	}
	switch {
	case errors.Is(err, fs.ErrNotExist):
		return ENOENT
	case errors.Is(err, fs.ErrExist):
		return EEXIST
	case errors.Is(err, fs.ErrPermission):
		return EACCES
	case strings.Contains(err.Error(), "too many links"):
		return ELOOP
	}
	return EIO
}

func osErr(op, path string, err error) error {
	if err == nil {
		return nil
	}
	return fsErr(op, path, toErrno(err))
}

func fileInfoOf(fi os.FileInfo, path string, followed bool) (FileInfo, error) {
	out := FileInfo{Size: fi.Size(), Mode: uint32(fi.Mode().Perm()), Mtime: fi.ModTime()}
	m := fi.Mode()
	switch {
	case m&os.ModeSymlink != 0:
		out.Type = TypeSymlink
	case m&os.ModeIrregular != 0 && isJunction(path):
		out.Type = TypeJunction
	case m.IsDir():
		out.Type = TypeDir
	case m&os.ModeNamedPipe != 0:
		out.Type = TypeFifo
	case m&(os.ModeDevice|os.ModeCharDevice) != 0:
		out.Type = TypeDevice
	default:
		out.Type = TypeFile
	}
	var err error
	out.Dev, out.Ino, err = identityOf(fi, path, followed)
	return out, err
}

// Lstat implements [FS].
func (OSFS) Lstat(path string) (FileInfo, error) {
	fi, err := os.Lstat(path)
	if err != nil {
		return FileInfo{}, osErr("lstat", path, err)
	}
	out, err := fileInfoOf(fi, path, false)
	return out, osErr("lstat", path, err)
}

// Stat implements [FS].
func (OSFS) Stat(path string) (FileInfo, error) {
	fi, err := os.Stat(path)
	if err != nil {
		return FileInfo{}, osErr("stat", path, err)
	}
	out, err := fileInfoOf(fi, path, true)
	return out, osErr("stat", path, err)
}

// Readlink implements [FS].
func (OSFS) Readlink(path string) (string, error) {
	t, err := os.Readlink(path)
	return t, osErr("readlink", path, err)
}

// ReadDir implements [FS].
func (OSFS) ReadDir(path string) ([]string, error) {
	des, err := os.ReadDir(path)
	if err != nil {
		return nil, osErr("readdir", path, err)
	}
	names := make([]string, len(des))
	for i, d := range des {
		names[i] = d.Name()
	}
	sort.Strings(names)
	return names, nil
}

// Realpath implements [FS].
func (OSFS) Realpath(path string) (string, error) {
	p, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", osErr("realpath", path, err)
	}
	p, err = filepath.Abs(p)
	return p, osErr("realpath", path, err)
}

// Open implements [FS].
func (o OSFS) Open(path string, flags OpenFlag, mode uint32) (File, error) {
	var f int
	switch {
	case flags&OpenCreateExcl != 0:
		f = os.O_WRONLY | os.O_CREATE | os.O_EXCL
	default:
		f = os.O_RDONLY
	}
	if flags&OpenNoFollow != 0 {
		if fi, err := (OSFS{}).Lstat(path); err == nil && fi.Type.IsLink() {
			return nil, fsErr("open", path, ELOOP)
		}
		f |= sysNoFollow
	}
	if flags&OpenNonBlock != 0 {
		f |= sysNonBlock
	}
	h, err := os.OpenFile(path, f, fs.FileMode(mode))
	if err != nil {
		return nil, osErr("open", path, err)
	}
	return &osFile{h}, nil
}

type osFile struct{ f *os.File }

func (o *osFile) Read(p []byte) (int, error) {
	n, err := o.f.Read(p)
	if err != nil && err != io.EOF {
		return n, osErr("read", o.f.Name(), err)
	}
	return n, err
}
func (o *osFile) Write(p []byte) (int, error) {
	n, err := o.f.Write(p)
	return n, osErr("write", o.f.Name(), err)
}
func (o *osFile) Sync() error  { return osErr("fsync", o.f.Name(), o.f.Sync()) }
func (o *osFile) Close() error { return osErr("close", o.f.Name(), o.f.Close()) }

// Mkdir implements [FS]. The mode is applied exactly, not reduced by the umask.
func (OSFS) Mkdir(path string, mode uint32) error {
	if err := os.Mkdir(path, fs.FileMode(mode)); err != nil {
		return osErr("mkdir", path, err)
	}
	return osErr("chmod", path, os.Chmod(path, fs.FileMode(mode)))
}

// Rename implements [FS].
func (OSFS) Rename(oldPath, newPath string) error {
	return osErr("rename", oldPath, os.Rename(oldPath, newPath))
}

// Symlink implements [FS].
func (OSFS) Symlink(target, path string, kind LinkKind) error {
	return osErr("symlink", path, symlinkOS(target, path, kind))
}

// Rmdir implements [FS]. It removes an empty directory, or a junction (the link, never its target).
func (o OSFS) Rmdir(path string) error {
	fi, err := o.Lstat(path)
	if err != nil {
		return err
	}
	if fi.Type != TypeDir && fi.Type != TypeJunction {
		return fsErr("rmdir", path, ENOTDIR)
	}
	return osErr("rmdir", path, os.Remove(path))
}

// Unlink implements [FS]. It removes anything that is not a directory or a junction.
func (o OSFS) Unlink(path string) error {
	fi, err := o.Lstat(path)
	if err != nil {
		return err
	}
	if fi.Type == TypeDir || fi.Type == TypeJunction {
		return fsErr("unlink", path, EISDIR)
	}
	return osErr("unlink", path, os.Remove(path))
}
