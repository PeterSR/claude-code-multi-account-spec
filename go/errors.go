package multiaccount

import (
	"errors"
	"fmt"
)

// Error codes and warning codes, as named by the spec (A4 table).
const (
	CodeInvalidName        = "INVALID_NAME"
	CodeReservedName       = "RESERVED_NAME"
	CodeAccountNotFound    = "ACCOUNT_NOT_FOUND"
	CodeAccountUnavailable = "ACCOUNT_UNAVAILABLE"
	CodeAccountExists      = "ACCOUNT_EXISTS"
	CodeEnvConflict        = "ENV_CONFLICT"
	CodeMarkerInvalid      = "MARKER_INVALID"
	CodeClaimConflict      = "CLAIM_CONFLICT"
	CodeSpecFileInvalid    = "SPEC_FILE_INVALID"
	CodeInvalidSessionID   = "INVALID_SESSION_ID"
	CodeSameAccount        = "SAME_ACCOUNT"
	CodeSessionNotFound    = "SESSION_NOT_FOUND"
	CodeSessionLive        = "SESSION_LIVE"
	CodeSessionExists      = "SESSION_EXISTS"
	CodeStateFileInvalid   = "STATE_FILE_INVALID"
	CodeInvalidEntry       = "INVALID_ENTRY"
	CodeSlotUnsupported    = "SLOT_UNSUPPORTED"
	CodeSlotState          = "SLOT_STATE"
	CodeSlotConflict       = "SLOT_CONFLICT"
	CodeSlotTargetInvalid  = "SLOT_TARGET_INVALID"
	CodeDestinationBlocked = "DESTINATION_BLOCKED"
	CodeLockBusy           = "LOCK_BUSY"
	CodeIOError            = "IO_ERROR"

	WarnEmptyEnv              = "EMPTY_ENV"
	WarnEnvNotApplied         = "ENV_NOT_APPLIED"
	WarnNonCanonicalConfigDir = "NON_CANONICAL_CONFIG_DIR"
	WarnNotADirectory         = "NOT_A_DIRECTORY"
	WarnMarkerIgnoredInRepo   = "MARKER_IGNORED_IN_REPO"
	WarnReservedName          = "RESERVED_NAME"
	WarnCandidateUnavailable  = "CANDIDATE_UNAVAILABLE"
)

// Error is the one error type of the library. Path is empty when not relevant.
type Error struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Path    string `json:"path,omitempty"`
	cause   error
}

// Unwrap returns the underlying filesystem error of an IO_ERROR, if any.
func (e *Error) Unwrap() error { return e.cause }

func (e *Error) Error() string {
	if e.Path != "" {
		return fmt.Sprintf("%s: %s (%s)", e.Code, e.Message, e.Path)
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

func newError(code, path, format string, args ...any) *Error {
	return &Error{Code: code, Path: path, Message: fmt.Sprintf(format, args...)}
}

// Warning is a non-fatal finding: {code, message, path?}. Path is empty when not relevant.
type Warning struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Path    string `json:"path,omitempty"`
}

var warningMessages = map[string]string{
	WarnEmptyEnv:              "an environment variable is set to the empty string and treated as unset",
	WarnEnvNotApplied:         "CLAUDE_MULTI_ACCOUNT is set but claude ignores it without CLAUDE_CONFIG_DIR",
	WarnNonCanonicalConfigDir: "CLAUDE_CONFIG_DIR is not the canonical path of the account",
	WarnNotADirectory:         "entry is not a directory and is not an account",
	WarnMarkerIgnoredInRepo:   "marker file inside a git working tree ignored",
	WarnReservedName:          "account name is reserved",
	WarnCandidateUnavailable:  "a later marker list entry is not an usable account",
}

func warn(code, path string) Warning {
	return Warning{Code: code, Message: warningMessages[code], Path: path}
}

// ioErr turns an unexpected filesystem error into IO_ERROR with the failing path, so callers only
// ever see [*Error] from the library. Spec errors and programming errors pass through.
func ioErr(err error) error {
	if err == nil {
		return nil
	}
	var se *Error
	if errors.As(err, &se) {
		return err
	}
	var fe *FSError
	if errors.As(err, &fe) {
		return &Error{Code: CodeIOError, Path: fe.Path, Message: fe.Error(), cause: err}
	}
	var en Errno
	if errors.As(err, &en) {
		return &Error{Code: CodeIOError, Message: err.Error(), cause: err}
	}
	return err
}
