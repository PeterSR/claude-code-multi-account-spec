//go:build !windows

package multiaccount

// procStartFt exists only on Windows.
func procStartFt(int) (string, LookupState) { return "", ProcError }
