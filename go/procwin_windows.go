//go:build windows

package multiaccount

import (
	"strconv"
	"syscall"
)

// procStartFt returns the creation time of a process as the decimal string of its 64-bit
// FILETIME (100 ns ticks since 1601). The exact text Claude Code stores in procStartFt on Windows
// was not verified, only that it is a FILETIME string.
func procStartFt(pid int) (string, LookupState) {
	const processQueryLimitedInformation = 0x1000
	h, err := syscall.OpenProcess(processQueryLimitedInformation, false, uint32(pid))
	if err != nil {
		if errno, ok := err.(syscall.Errno); ok && errno == 87 { // ERROR_INVALID_PARAMETER
			return "", ProcNone
		}
		return "", ProcError
	}
	defer syscall.CloseHandle(h)
	var created, exit, kernel, user syscall.Filetime
	if err := syscall.GetProcessTimes(h, &created, &exit, &kernel, &user); err != nil {
		return "", ProcError
	}
	ft := uint64(created.HighDateTime)<<32 | uint64(created.LowDateTime)
	return strconv.FormatUint(ft, 10), ProcFound
}
