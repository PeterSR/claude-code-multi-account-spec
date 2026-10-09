//go:build windows

package multiaccount

import (
	"encoding/binary"
	"os"
	"path/filepath"
	"syscall"
	"unicode/utf16"
)

const (
	sysNoFollow = 0 // emulated with an Lstat check in OSFS.Open
	sysNonBlock = 0

	ioReparseTagMountPoint = 0xA0000003
	fsctlSetReparsePoint   = 0x000900A4
	fileAttributeReparse   = 0x400
)

// isJunction reports whether path is a directory junction: a directory reparse point whose tag is
// IO_REPARSE_TAG_MOUNT_POINT. Other reparse points (OneDrive placeholders, for example) are not.
func isJunction(path string) bool {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return false
	}
	var data syscall.Win32finddata
	h, err := syscall.FindFirstFile(p, &data)
	if err != nil {
		return false
	}
	_ = syscall.FindClose(h)
	return data.FileAttributes&fileAttributeReparse != 0 &&
		data.FileAttributes&syscall.FILE_ATTRIBUTE_DIRECTORY != 0 &&
		data.Reserved0 == ioReparseTagMountPoint
}

// identityOf returns the volume serial number and file index of the object path names, following
// the link when followed is set. A failure is an error, never (0, 0), so two inaccessible
// directories never compare equal.
func identityOf(_ os.FileInfo, path string, followed bool) (dev, ino uint64, err error) {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return 0, 0, err
	}
	flags := uint32(syscall.FILE_FLAG_BACKUP_SEMANTICS)
	if !followed {
		flags |= syscall.FILE_FLAG_OPEN_REPARSE_POINT
	}
	h, err := syscall.CreateFile(p, 0, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, flags, 0)
	if err != nil {
		return 0, 0, err
	}
	defer syscall.CloseHandle(h)
	var fi syscall.ByHandleFileInformation
	if err := syscall.GetFileInformationByHandle(h, &fi); err != nil {
		return 0, 0, err
	}
	return uint64(fi.VolumeSerialNumber), uint64(fi.FileIndexHigh)<<32 | uint64(fi.FileIndexLow), nil
}

// symlinkOS creates a file symlink (which needs the symlink privilege or developer mode) or, for a
// directory, a real junction.
func symlinkOS(target, path string, kind LinkKind) error {
	if kind == LinkDir {
		return createJunction(target, path)
	}
	return os.Symlink(target, path)
}

// createJunction creates the directory path and turns it into a mount point reparse point to
// target (made absolute against the link's directory when relative). It removes the directory
// again when setting the reparse data fails.
func createJunction(target, link string) error {
	if !filepath.IsAbs(target) {
		target = filepath.Join(filepath.Dir(link), target)
	}
	target = filepath.Clean(target)
	buf := mountPointBuffer(target)

	lp, err := syscall.UTF16PtrFromString(link)
	if err != nil {
		return err
	}
	if err := syscall.CreateDirectory(lp, nil); err != nil {
		return err
	}
	const genericWrite = 0x40000000
	h, err := syscall.CreateFile(lp, genericWrite, 0, nil, syscall.OPEN_EXISTING,
		syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if err != nil {
		_ = syscall.RemoveDirectory(lp)
		return err
	}
	defer syscall.CloseHandle(h)
	var returned uint32
	if err := syscall.DeviceIoControl(h, fsctlSetReparsePoint, &buf[0], uint32(len(buf)), nil, 0, &returned, nil); err != nil {
		_ = syscall.CloseHandle(h)
		_ = syscall.RemoveDirectory(lp)
		return err
	}
	return nil
}

// mountPointBuffer builds a REPARSE_DATA_BUFFER for IO_REPARSE_TAG_MOUNT_POINT.
func mountPointBuffer(target string) []byte {
	sub := utf16.Encode([]rune(`\??\` + target))
	print := utf16.Encode([]rune(target))
	subBytes, printBytes := len(sub)*2, len(print)*2
	// header (tag, data length, reserved) + 4 offsets/lengths + two NUL terminated strings
	dataLen := 8 + subBytes + 2 + printBytes + 2
	buf := make([]byte, 8+dataLen)
	le := binary.LittleEndian
	le.PutUint32(buf[0:], ioReparseTagMountPoint)
	le.PutUint16(buf[4:], uint16(dataLen))
	le.PutUint16(buf[8:], 0)                   // SubstituteNameOffset
	le.PutUint16(buf[10:], uint16(subBytes))   // SubstituteNameLength
	le.PutUint16(buf[12:], uint16(subBytes+2)) // PrintNameOffset
	le.PutUint16(buf[14:], uint16(printBytes)) // PrintNameLength
	off := 16
	for _, c := range sub {
		le.PutUint16(buf[off:], c)
		off += 2
	}
	off += 2
	for _, c := range print {
		le.PutUint16(buf[off:], c)
		off += 2
	}
	return buf
}
