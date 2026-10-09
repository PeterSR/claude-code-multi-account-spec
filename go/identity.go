package multiaccount

import (
	"encoding/json"
	"reflect"
	"time"
)

// IdentityInfo is the oauthAccount of an account's global config file (B2).
type IdentityInfo struct {
	Email                     *string `json:"email"`
	OrgName                   *string `json:"orgName"`
	OrgUUID                   *string `json:"orgUuid"`
	OrganizationType          *string `json:"organizationType"`
	BillingType               *string `json:"billingType"`
	UserRateLimitTier         *string `json:"userRateLimitTier"`
	OrganizationRateLimitTier *string `json:"organizationRateLimitTier"`
}

func strField(m map[string]any, k string) *string {
	if s, ok := m[k].(string); ok {
		return &s
	}
	return nil
}

// globalConfigOf gates name and returns its effective global config file.
func (w *world) globalConfigOf(name string) (string, error) {
	if _, err := w.gate(name); err != nil {
		return "", err
	}
	return w.globalConfigPath(name), nil
}

func (w *world) identityAt(gc string) *IdentityInfo {
	if gc == "" {
		return nil
	}
	d, ok := w.readJSONObject(gc)
	if !ok {
		return nil
	}
	o, ok := d["oauthAccount"].(map[string]any)
	if !ok {
		return nil
	}
	return &IdentityInfo{
		Email: strField(o, "emailAddress"), OrgName: strField(o, "organizationName"),
		OrgUUID: strField(o, "organizationUuid"), OrganizationType: strField(o, "organizationType"),
		BillingType: strField(o, "billingType"), UserRateLimitTier: strField(o, "userRateLimitTier"),
		OrganizationRateLimitTier: strField(o, "organizationRateLimitTier"),
	}
}

// Identity reads oauthAccount from the account's global config file (A1). It returns nil when
// there is no data. No credential is read, so a status line never triggers a keychain prompt.
func Identity(in Inputs, name string) (info *IdentityInfo, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	gc, err := w.globalConfigOf(name)
	if err != nil {
		return nil, err
	}
	return w.identityAt(gc), nil
}

// IdentityFor is Identity for a resolution: it reads the resolution's GlobalConfig, which differs
// from the account's own file for a config-dir result such as CLAUDE_CONFIG_DIR=$HOME/.claude. A
// status line should use it. A resolution without a global config (a pool, a relative directory)
// gives nil.
func IdentityFor(in Inputs, r *Resolution) (info *IdentityInfo, err error) {
	defer func() { err = ioErr(err) }()
	if r == nil || r.GlobalConfig == nil {
		return nil, nil
	}
	return newWorld(in).identityAt(*r.GlobalConfig), nil
}

// UsageWindow is one rate-limit window of the usage cache.
type UsageWindow struct {
	Utilization *float64 `json:"utilization"`
	ResetsAt    *string  `json:"resetsAt"`
}

// UsageInfo is the cachedUsageUtilization of an account's global config file (B2).
type UsageInfo struct {
	// FetchedAt is fetchedAtMs as RFC 3339 UTC with milliseconds, nil if the cache has no number.
	FetchedAt *string `json:"fetchedAt"`
	// Data is the cachedUsageUtilization object verbatim.
	Data json.RawMessage `json:"data"`
	// Windows holds each object under data.utilization, by key; empty when there is none.
	Windows map[string]UsageWindow `json:"windows"`
	// Stale says the cache should not be trusted: no fetch time, a fetch time in the future or more
	// than an hour old, or an accountUuid that is not the logged-in account's.
	Stale bool `json:"stale"`
}

func (w *world) usageAt(gc string) *UsageInfo {
	if gc == "" {
		return nil
	}
	d, ok := w.readJSONObject(gc)
	if !ok {
		return nil
	}
	u, ok := d["cachedUsageUtilization"].(map[string]any)
	if !ok {
		return nil
	}
	raw, err := marshalPlain(u)
	if err != nil {
		return nil
	}
	out := &UsageInfo{Data: raw, Windows: map[string]UsageWindow{}}
	ms, hasMs := numberValue(u["fetchedAtMs"])
	if hasMs {
		out.FetchedAt = strp(formatMillis(ms))
		age := float64(w.now.UnixMilli()) - ms
		out.Stale = age < 0 || age > 3600000
	} else {
		out.Stale = true
	}
	if util, ok := u["utilization"].(map[string]any); ok {
		for k, v := range util {
			m, ok := v.(map[string]any)
			if !ok {
				continue
			}
			uw := UsageWindow{ResetsAt: strField(m, "resets_at")}
			if f, ok := numberValue(m["utilization"]); ok {
				uw.Utilization = &f
			}
			out.Windows[k] = uw
		}
	}
	var want any
	wantSet := false
	if o, ok := d["oauthAccount"].(map[string]any); ok {
		want, wantSet = o["accountUuid"]
	}
	got, gotSet := u["accountUuid"]
	if gotSet != wantSet || !reflect.DeepEqual(got, want) {
		out.Stale = true
	}
	return out
}

func formatMillis(ms float64) string {
	return time.UnixMilli(int64(ms)).UTC().Format("2006-01-02T15:04:05.000Z")
}

// Usage reads cachedUsageUtilization. It is as fresh as Claude Code last made it, and Stale says
// whether to trust it. It returns nil when absent. It needs Inputs.Clock.
func Usage(in Inputs, name string) (info *UsageInfo, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	gc, err := w.globalConfigOf(name)
	if err != nil {
		return nil, err
	}
	if err := w.needClock(); err != nil {
		return nil, err
	}
	return w.usageAt(gc), nil
}

// UsageFor is Usage for a resolution (see [IdentityFor]).
func UsageFor(in Inputs, r *Resolution) (info *UsageInfo, err error) {
	defer func() { err = ioErr(err) }()
	if r == nil || r.GlobalConfig == nil {
		return nil, nil
	}
	w := newWorld(in)
	if err := w.needClock(); err != nil {
		return nil, err
	}
	return w.usageAt(*r.GlobalConfig), nil
}

// StoredCredentials is the stored OAuth token of an account, read-only (B2). The refresh token is
// deliberately never exposed: it rotates, and a refresh outside Claude Code logs Claude Code out.
type StoredCredentials struct {
	Source           string   `json:"source"`
	Path             string   `json:"path"`
	AccessToken      string   `json:"accessToken"`
	ExpiresAt        *string  `json:"expiresAt"`
	Expired          bool     `json:"expired"`
	Scopes           []string `json:"scopes"`
	SubscriptionType *string  `json:"subscriptionType"`
	RateLimitTier    *string  `json:"rateLimitTier"`
}

// Credentials reads <config home>/.credentials.json only, never a keychain or Credential Manager.
// A link there counts as absent, as Claude Code opens it with O_NOFOLLOW. It returns nil when the
// file is absent, a link, unparseable, or has no claudeAiOauth object with a non-empty string
// accessToken. An expired token is reported with Expired set, never refreshed. It needs
// Inputs.Clock for Expired.
func Credentials(in Inputs, name string) (res *StoredCredentials, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if _, err := w.gate(name); err != nil {
		return nil, err
	}
	if err := w.needClock(); err != nil {
		return nil, err
	}
	p := w.p.join(w.configHome(name), ".credentials.json")
	if l, err := w.fs.Lstat(p); err != nil || l.Type.IsLink() {
		return nil, nil
	}
	b, ok := w.readFileFlags(p, OpenRead|OpenNoFollow|OpenNonBlock)
	if !ok {
		return nil, nil
	}
	v, ok := decodeJSON(b)
	if !ok {
		return nil, nil
	}
	doc, _ := v.(map[string]any)
	o, ok := doc["claudeAiOauth"].(map[string]any)
	if !ok {
		return nil, nil
	}
	tok, ok := o["accessToken"].(string)
	if !ok || tok == "" {
		return nil, nil
	}
	out := &StoredCredentials{
		Source: "file", Path: p, AccessToken: tok, Scopes: []string{},
		SubscriptionType: strField(o, "subscriptionType"), RateLimitTier: strField(o, "rateLimitTier"),
	}
	if ms, ok := numberValue(o["expiresAt"]); ok {
		out.ExpiresAt = strp(formatMillis(ms))
		out.Expired = !time.UnixMilli(int64(ms)).After(w.now)
	}
	if sc, ok := o["scopes"].([]any); ok {
		for _, x := range sc {
			if s, ok := x.(string); ok {
				out.Scopes = append(out.Scopes, s)
			}
		}
	}
	return out, nil
}
