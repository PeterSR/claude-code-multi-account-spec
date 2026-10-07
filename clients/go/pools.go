package multiaccount

import (
	"slices"
	"sort"
	"time"
)

// PickResult is the result of Pick, Next, PickFrom and NextFrom. Account is nil when none is
// available.
type PickResult struct {
	Account *string `json:"account"`
}

// members returns the pool's members in order: priority descending, then name bytewise. Members
// are default and the ok accounts with a valid spec naming the pool, each alias group counted once
// through its representative. An invalid spec file anywhere is SPEC_FILE_INVALID.
func (w *world) members(pool string) ([]string, error) {
	if !ValidName(pool) {
		return nil, newError(CodeInvalidName, "", "invalid pool name %q", pool)
	}
	for _, a := range w.listAccounts() {
		if a.state == StateOK {
			if sp := w.spec(a); sp.invalid {
				return nil, newError(CodeSpecFileInvalid, sp.path, "invalid spec file")
			}
		}
	}
	type member struct {
		name string
		prio int64
	}
	var ms []member
	for _, a := range w.primaries() {
		sp := w.spec(a)
		if !sp.present || sp.data["pool"] != pool {
			continue
		}
		var prio int64
		if p, has := sp.data["priority"]; has {
			prio, _ = specPriority(p)
		}
		ms = append(ms, member{a.name, prio})
	}
	sort.SliceStable(ms, func(i, j int) bool {
		if ms[i].prio != ms[j].prio {
			return ms[i].prio > ms[j].prio
		}
		return ms[i].name < ms[j].name
	})
	out := make([]string, len(ms))
	for i, m := range ms {
		out[i] = m.name
	}
	return out, nil
}

func (w *world) firstAvailable(cands []string, now time.Time, model string) *PickResult {
	for _, n := range cands {
		if w.isAvailable(n, now, model) {
			return &PickResult{Account: strp(n)}
		}
	}
	return &PickResult{}
}

// nextOf orders the candidates after current first, then those up to and including it, wrapping;
// a current outside the list starts from the top.
func (w *world) nextOf(list []string, current string, now time.Time, model string) *PickResult {
	cands := list
	if i := slices.Index(list, current); i >= 0 {
		cands = append(append([]string{}, list[i+1:]...), list[:i+1]...)
	}
	return w.firstAvailable(cands, now, model)
}

// Pick returns the available pool member with the highest priority, ties broken by name (B6).
func Pick(in Inputs, pool string, now time.Time, model string) (res *PickResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	m, err := w.members(pool)
	if err != nil {
		return nil, err
	}
	return w.firstAvailable(m, now, model), nil
}

// Next returns the next available member after current in pick order, wrapping (B6). It returns
// current itself when it is the only available member, and starts from the top when current is not
// a member.
func Next(in Inputs, pool, current string, now time.Time, model string) (res *PickResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	m, err := w.members(pool)
	if err != nil {
		return nil, err
	}
	return w.nextOf(m, current, now, model), nil
}

// checkNames validates every candidate name (INVALID_NAME). A candidate that is not default or an
// ok account is never available and is skipped by the pick functions, with no error.
func (w *world) checkNames(candidates []string) error {
	for _, n := range candidates {
		if err := w.checkName(n); err != nil {
			return err
		}
	}
	return nil
}

func (w *world) firstUsableAvailable(cands []string, now time.Time, model string) *PickResult {
	for _, n := range cands {
		if w.usable(n) && w.isAvailable(n, now, model) {
			return &PickResult{Account: strp(n)}
		}
	}
	return &PickResult{}
}

// PickFrom returns the first available candidate of an ordered list, normally the Candidates of a
// resolution (B6). Names are validated (INVALID_NAME); candidates that are not usable accounts are
// skipped. An empty list gives nil.
func PickFrom(in Inputs, candidates []string, now time.Time, model string) (res *PickResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if err := w.checkNames(candidates); err != nil {
		return nil, err
	}
	return w.firstUsableAvailable(candidates, now, model), nil
}

// NextFrom returns the next available candidate after current in the list, wrapping (B6). An alias
// group is one account: the position is the first candidate that is the same account as current,
// the candidates after it come first, then those before it, each skipping any that are the same
// account as current, and finally the candidate at the position itself. Without a match all
// candidates are tried in order. Unusable candidates are skipped.
func NextFrom(in Inputs, candidates []string, current string, now time.Time, model string) (res *PickResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if err := w.checkNames(candidates); err != nil {
		return nil, err
	}
	pos := -1
	for i, c := range candidates {
		if w.sameAccount(c, current) {
			pos = i
			break
		}
	}
	if pos < 0 {
		return w.firstUsableAvailable(candidates, now, model), nil
	}
	var order []string
	for _, c := range append(append([]string{}, candidates[pos+1:]...), candidates[:pos]...) {
		if !w.sameAccount(c, current) {
			order = append(order, c)
		}
	}
	order = append(order, candidates[pos])
	return w.firstUsableAvailable(order, now, model), nil
}

// PoolMembersResult is the result of PoolMembers.
type PoolMembersResult struct {
	Members []string `json:"members"`
}

// PoolMembers lists the members of a pool in pick order, without availability (B6). Errors are
// those of [Pick].
func PoolMembers(in Inputs, pool string) (res *PoolMembersResult, err error) {
	defer func() { err = ioErr(err) }()
	m, err := newWorld(in).members(pool)
	if err != nil {
		return nil, err
	}
	return &PoolMembersResult{Members: nonNil(m)}, nil
}
