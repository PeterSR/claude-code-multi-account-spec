package multiaccount

import (
	"crypto/sha256"
	"encoding/hex"
)

// KeychainItem names a macOS keychain item.
type KeychainItem struct {
	Service string `json:"service"`
	Account string `json:"account"`
}

// CredentialManagerItem marks Windows Credential Manager as a credential store. The target name
// is not yet verified, so it carries nothing.
type CredentialManagerItem struct{}

// CredentialLocation is one place Claude Code looks for the login. Exactly one field is set.
type CredentialLocation struct {
	File              string                 `json:"file,omitempty"`
	Keychain          *KeychainItem          `json:"keychain,omitempty"`
	CredentialManager *CredentialManagerItem `json:"credentialManager,omitempty"`
}

// CredentialLocationsResult is the result of CredentialLocations.
type CredentialLocationsResult struct {
	Locations []CredentialLocation `json:"locations"`
}

const userNameFallback = "claude-code-user"

func validKeychainAccount(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c >= 'a' && c <= 'z', c >= 'A' && c <= 'Z', c >= '0' && c <= '9', c == '.', c == '_', c == '-':
		default:
			return false
		}
	}
	return true
}

// credmanInUse reports whether Windows Credential Manager holds the login: forced by
// CLAUDE_CODE_FORCE_WINDOWS_CREDMAN=1, or cached in the given global config file.
func (w *world) credmanInUse(globalConfig string) bool {
	if w.env["CLAUDE_CODE_FORCE_WINDOWS_CREDMAN"] == "1" {
		return true
	}
	if globalConfig == "" {
		return false
	}
	if d, ok := w.readJSONObject(globalConfig); ok {
		if g, ok := d["cachedGrowthBookFeatures"].(map[string]any); ok {
			return g["tengu_windows_credman"] == true
		}
	}
	return false
}

// CredentialLocations returns the ordered places Claude Code looks for an account's login (B1).
// It is pure apart from reading the global config on Windows to detect Credential Manager.
func CredentialLocations(in Inputs, name string) (res *CredentialLocationsResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if err := w.checkName(name); err != nil {
		return nil, err
	}
	ch := w.configHome(name)
	file := CredentialLocation{File: w.p.join(ch, ".credentials.json")}
	locs := []CredentialLocation{file}
	switch in.Platform {
	case PlatformDarwin:
		svc := "Claude Code" + w.suffix() + "-credentials"
		if name != DefaultName {
			sum := sha256.Sum256([]byte(ch))
			svc += "-" + hex.EncodeToString(sum[:])[:8]
		}
		acct := w.env["USER"]
		if acct == "" {
			acct = in.UserName
		}
		if !validKeychainAccount(acct) {
			acct = userNameFallback
		}
		locs = []CredentialLocation{{Keychain: &KeychainItem{Service: svc, Account: acct}}, file}
	case PlatformWin32:
		if w.credmanInUse(w.globalConfigPath(name)) {
			locs = []CredentialLocation{{CredentialManager: &CredentialManagerItem{}}, file}
		}
	}
	return &CredentialLocationsResult{Locations: locs}, nil
}
