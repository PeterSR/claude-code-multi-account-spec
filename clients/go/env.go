package multiaccount

import (
	"slices"
	"sort"
	"strings"
)

// LaunchEnv is the env delta to launch an account with. Launch with this, never with
// CLAUDE_CONFIG_DIR=$configDir, and apply all of it, never CLAUDE_MULTI_ACCOUNT alone.
type LaunchEnv struct {
	Set   map[string]string `json:"set"`
	Unset []string          `json:"unset"`
}

// EnvOptions are the options of Env.
type EnvOptions struct {
	// ClearAuthOverrides also unsets the variables that replace the login (authClearable).
	ClearAuthOverrides bool
}

// EnvResult is the result of Env: the launch delta plus what still overrides the login.
type EnvResult struct {
	LaunchEnv
	OverriddenBy []string `json:"overriddenBy"`
}

// authClearable are the variables that replace the login and that clearAuthOverrides unsets, in
// the fixed order overriddenBy reports them.
var authClearable = []string{
	"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
	"CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_PROFILE",
}

var truthyOnlyVars = []string{"CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"}

const (
	envSecureStorage = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
	envCustomOAuth   = "CLAUDE_CODE_CUSTOM_OAUTH_URL"
)

func (w *world) launchEnv(name string, clear bool) LaunchEnv {
	set := map[string]string{EnvMultiAccount: name}
	unset := map[string]bool{EnvSource: true, envSecureStorage: true}
	if name == DefaultName {
		unset[EnvConfigDir] = true
	} else {
		set[EnvConfigDir] = w.canon(name)
	}
	if clear {
		for _, k := range authClearable {
			unset[k] = true
		}
	}
	out := make([]string, 0, len(unset))
	for k := range unset {
		out = append(out, k)
	}
	sort.Strings(out)
	return LaunchEnv{Set: set, Unset: out}
}

// settingsEnv reads the string values of the env object and the apiKeyHelper of a settings.json
// in the config home cfg. An unparseable file gives nothing.
func (w *world) settingsEnv(cfg string) (env map[string]string, helper bool) {
	env = map[string]string{}
	if cfg == "" || !w.p.isAbs(cfg) {
		return env, false
	}
	d, ok := w.readJSONObject(w.p.join(cfg, "settings.json"))
	if !ok {
		return env, false
	}
	if e, ok := d["env"].(map[string]any); ok {
		for k, v := range e {
			if s, ok := v.(string); ok {
				env[k] = s
			}
		}
	}
	h, _ := d["apiKeyHelper"].(string)
	return env, h != ""
}

func authVarApplies(src map[string]string, k string) bool {
	v, ok := src[k]
	if !ok {
		return false
	}
	if slices.Contains(truthyOnlyVars, k) {
		switch strings.ToLower(strings.TrimSpace(v)) {
		case "1", "true", "yes", "on":
			return true
		}
		return false
	}
	return v != ""
}

// overriddenBy lists what replaces the account's login (A4 overriddenBy), in a fixed order. cfg is
// the config home whose settings.json is consulted; empty skips it. clear drops the variables
// that clearAuthOverrides unsets from the process env, but not those set in settings.json.
func (w *world) overriddenBy(cfg string, clear bool) []string {
	senv, helper := w.settingsEnv(cfg)
	out := []string{}
	for _, k := range authClearable {
		if (!clear && authVarApplies(w.env, k)) || authVarApplies(senv, k) {
			out = append(out, k)
		}
	}
	if _, ok := w.env[envSecureStorage]; ok {
		out = append(out, envSecureStorage)
	}
	if w.env[envCustomOAuth] != "" {
		out = append(out, envCustomOAuth)
	}
	if helper {
		out = append(out, "apiKeyHelper")
	}
	return out
}

// Env returns the launch delta for an account (B1). It is pure apart from reading the account's
// settings.json for what still overrides the login, and does not gate on the account existing.
func Env(in Inputs, name string, opts EnvOptions) (res *EnvResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if err := w.checkName(name); err != nil {
		return nil, err
	}
	return &EnvResult{LaunchEnv: w.launchEnv(name, opts.ClearAuthOverrides), OverriddenBy: w.overriddenBy(w.configHome(name), opts.ClearAuthOverrides)}, nil
}
