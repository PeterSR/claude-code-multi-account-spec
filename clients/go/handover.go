package multiaccount

import (
	"io"
	"regexp"
	"slices"
	"sort"
	"strings"
)

// HandoverOptions are the options of HandoverSession.
type HandoverOptions struct {
	// Overwrite replaces a session that already exists in the destination account.
	Overwrite bool
	// Force proceeds although B3 reports an unknown session. It never overrides a live one.
	Force bool
}

// HandoverResult is the result of HandoverSession. Copied lists the files copied and Skipped the
// links, FIFOs and devices that were not, relative to the config home with "/" separators, sorted.
type HandoverResult struct {
	Copied  []string `json:"copied"`
	Skipped []string `json:"skipped"`
}

var sessionIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`)

type sessionLocation struct {
	rel string
	typ FileType
}

// layout is what the parents of the session locations of one account look like: the plain-dir
// slugs, and the parents that exist but are not plain directories (links, files), which are never
// locations and are reported in skipped.
type layout struct {
	slugs   []string
	blocked map[string]bool // relative paths: "projects", "projects/<slug>", "tasks", ...
}

var sessionKindDirs = []string{"file-history", "session-env", "tasks"}

func (w *world) layoutOf(root string) layout {
	l := layout{blocked: map[string]bool{}}
	plain := func(rel string) (exists, isPlain bool) {
		fi, err := w.fs.Lstat(w.relPath(root, rel))
		if err != nil {
			return false, false
		}
		return true, fi.Type == TypeDir
	}
	for _, k := range sessionKindDirs {
		if ex, ok := plain(k); ex && !ok {
			l.blocked[k] = true
		}
	}
	if ex, ok := plain("projects"); ex && !ok {
		l.blocked["projects"] = true
	} else if ok {
		names, _ := w.fs.ReadDir(w.relPath(root, "projects"))
		for _, n := range names {
			if ex, ok := plain("projects/" + n); ex && !ok {
				l.blocked["projects/"+n] = true
			} else if ok {
				l.slugs = append(l.slugs, n)
			}
		}
	}
	return l
}

// locationRels lists the five kinds of location for the given slugs.
func locationRels(slugs []string, id string) []string {
	var rel []string
	for _, s := range slugs {
		rel = append(rel, "projects/"+s+"/"+id+".jsonl", "projects/"+s+"/"+id)
	}
	return append(rel, "file-history/"+id, "session-env/"+id, "tasks/"+id)
}

func parentOf(rel string) string {
	i := strings.LastIndexByte(rel, '/')
	return rel[:i]
}

// existingLocations returns the locations that exist in root (by lstat), each checked to stay
// inside the config home.
func (w *world) existingLocations(root string, rels []string) []sessionLocation {
	seen := map[string]bool{}
	var out []sessionLocation
	for _, r := range rels {
		p := w.relPath(root, r)
		if seen[r] || !strings.HasPrefix(p, root+w.p.sep()) {
			continue
		}
		seen[r] = true
		if fi, err := w.fs.Lstat(p); err == nil {
			out = append(out, sessionLocation{r, fi.Type})
		}
	}
	return out
}

func (w *world) relPath(root, rel string) string {
	return w.p.join(append([]string{root}, strings.Split(rel, "/")...)...)
}

func (w *world) removeAll(path string) error {
	fi, err := w.fs.Lstat(path)
	if err != nil {
		return err
	}
	switch fi.Type {
	case TypeDir:
		names, err := w.fs.ReadDir(path)
		if err != nil {
			return err
		}
		for _, n := range names {
			if err := w.removeAll(w.p.join(path, n)); err != nil {
				return err
			}
		}
		return w.fs.Rmdir(path)
	case TypeJunction:
		return w.fs.Rmdir(path)
	}
	return w.fs.Unlink(path)
}

// mkdirAll creates path and missing ancestors with mode 0700.
func (w *world) mkdirAll(path string, created *[]string) error {
	if _, err := w.fs.Lstat(path); err == nil {
		return nil
	}
	if par, ok := w.p.parent(path); ok {
		if err := w.mkdirAll(par, created); err != nil {
			return err
		}
	}
	if err := w.fs.Mkdir(path, 0o700); err != nil {
		if ErrnoOf(err) == EEXIST {
			return nil
		}
		return err
	}
	*created = append(*created, path)
	return nil
}

// stage copies the source tree at rel to dstPath (a temporary name), recording copied and skipped
// entries. Only regular files and directories are copied, decided by lstat, and source files are
// opened with O_NOFOLLOW and O_NONBLOCK. Any failure is IO_ERROR naming the failing path.
func (w *world) stage(src, dstPath, rel string, copied, skipped *[]string) error {
	sp := w.relPath(src, rel)
	fi, err := w.fs.Lstat(sp)
	if err != nil {
		return ioPath(err, sp)
	}
	switch fi.Type {
	case TypeDir:
		if err := w.fs.Mkdir(dstPath, 0o700); err != nil {
			return ioPath(err, dstPath)
		}
		names, err := w.fs.ReadDir(sp)
		if err != nil {
			return ioPath(err, sp)
		}
		for _, n := range names {
			if err := w.stage(src, w.p.join(dstPath, n), rel+"/"+n, copied, skipped); err != nil {
				return err
			}
		}
	case TypeFile:
		in, err := w.fs.Open(sp, OpenRead|OpenNoFollow|OpenNonBlock, 0)
		if err != nil {
			return ioPath(err, sp)
		}
		defer in.Close()
		data, err := io.ReadAll(in)
		if err != nil {
			return ioPath(err, sp)
		}
		out, err := w.fs.Open(dstPath, OpenCreateExcl, fi.Mode)
		if err != nil {
			return ioPath(err, dstPath)
		}
		_, err = out.Write(data)
		if err == nil {
			err = out.Sync()
		}
		if cerr := out.Close(); err == nil {
			err = cerr
		}
		if err != nil {
			return ioPath(err, dstPath)
		}
		*copied = append(*copied, rel)
	default:
		*skipped = append(*skipped, rel)
	}
	return nil
}

// ioPath makes an IO_ERROR with the given path.
func ioPath(err error, path string) error {
	return &Error{Code: CodeIOError, Path: path, Message: err.Error(), cause: err}
}

// HandoverSession copies a conversation from one account to another so claude --resume works under
// the destination (B4). It copies, never moves, and never touches the source.
//
// Checks run in this order: the id grammar (INVALID_SESSION_ID), the account gate for from then to,
// SAME_ACCOUNT, SESSION_NOT_FOUND, SESSION_LIVE (a live session with this id in from, or an unknown
// one unless Force) and SESSION_EXISTS (unless Overwrite). Only regular files and directories are
// copied; everything else is listed in Skipped. Each destination location is built under a
// temporary name and swapped in, and with Overwrite the old one is removed only after its
// replacement is complete, so a failed copy (IO_ERROR) leaves the destination as it was.
func HandoverSession(in Inputs, id, from, to string, opts HandoverOptions) (res *HandoverResult, err error) {
	defer func() { err = ioErr(err) }()
	w := newWorld(in)
	if !sessionIDPattern.MatchString(id) {
		return nil, newError(CodeInvalidSessionID, "", "invalid session id %q", id)
	}
	if _, err := w.gate(from); err != nil {
		return nil, err
	}
	if _, err := w.gate(to); err != nil {
		return nil, err
	}
	if w.sameAccount(from, to) {
		return nil, newError(CodeSameAccount, "", "%q and %q are the same account", from, to)
	}
	src, dst := w.configHome(from), w.configHome(to)
	sl, dl := w.layoutOf(src), w.layoutOf(dst)
	blockedIn := func(l layout, rel string) bool {
		return l.blocked[rel] || l.blocked[parentOf(rel)] || (strings.HasPrefix(rel, "projects/") && l.blocked["projects"])
	}
	var srcLocs []sessionLocation
	for _, l := range w.existingLocations(src, locationRels(sl.slugs, id)) {
		if !blockedIn(sl, l.rel) {
			srcLocs = append(srcLocs, l)
		}
	}
	found := false
	for _, l := range srcLocs {
		found = found || l.typ == TypeFile || l.typ == TypeDir
	}
	if !found {
		return nil, newError(CodeSessionNotFound, "", "session %q not found in %q", id, from)
	}
	if err := blockedBy(w.sessions(from), opts.Force, &id); err != nil {
		return nil, err
	}
	// a destination parent that is a link (or file) and would receive a location is an error
	for _, l := range srcLocs {
		parents := []string{parentOf(l.rel)}
		if strings.HasPrefix(l.rel, "projects/") {
			parents = []string{"projects", parentOf(l.rel)}
		}
		for _, par := range parents {
			p := w.relPath(dst, par)
			if fi, err := w.fs.Lstat(p); err == nil && fi.Type != TypeDir {
				return nil, newError(CodeDestinationBlocked, p, "destination %s is not a plain directory", par)
			}
		}
	}
	var unionSlugs []string
	for _, x := range append(append([]string{}, sl.slugs...), dl.slugs...) {
		if !slices.Contains(unionSlugs, x) {
			unionSlugs = append(unionSlugs, x)
		}
	}
	var dstLocs []sessionLocation
	for _, l := range w.existingLocations(dst, locationRels(unionSlugs, id)) {
		if !blockedIn(dl, l.rel) {
			dstLocs = append(dstLocs, l)
		}
	}
	if len(dstLocs) > 0 && !opts.Overwrite {
		return nil, newError(CodeSessionExists, "", "session %q already exists in %q", id, to)
	}
	copied, skipped := []string{}, []string{}
	for _, l := range []layout{sl} {
		for k := range l.blocked {
			if !slices.Contains(skipped, k) {
				skipped = append(skipped, k)
			}
		}
	}
	type staged struct{ tmp, final, rel string }
	var stagedAll []staged
	var createdDirs []string
	cleanup := func() {
		for _, s := range stagedAll {
			_ = w.removeAll(s.tmp)
		}
		for i := len(createdDirs) - 1; i >= 0; i-- {
			_ = w.fs.Rmdir(createdDirs[i]) // only the parents this call made, and only if empty
		}
	}
	for _, l := range srcLocs {
		if l.typ != TypeFile && l.typ != TypeDir {
			skipped = append(skipped, l.rel)
			continue
		}
		final := w.relPath(dst, l.rel)
		tmp := final + ".tmp." + w.tempSuffix()
		if par, ok := w.p.parent(final); ok {
			if err := w.mkdirAll(par, &createdDirs); err != nil {
				cleanup()
				return nil, ioPath(err, par)
			}
		}
		stagedAll = append(stagedAll, staged{tmp, final, l.rel})
		if err := w.stage(src, tmp, l.rel, &copied, &skipped); err != nil {
			cleanup()
			return nil, err
		}
	}
	for _, s := range stagedAll {
		if _, err := w.fs.Lstat(s.final); err == nil {
			if err := w.removeAll(s.final); err != nil {
				cleanup()
				return nil, ioPath(err, s.final)
			}
		}
		if err := w.fs.Rename(s.tmp, s.final); err != nil {
			cleanup()
			return nil, ioPath(err, s.final)
		}
	}
	// with overwrite every existing destination location goes, also those that got no replacement
	// (the source had a link there, or nothing)
	if opts.Overwrite {
		for _, l := range dstLocs {
			if !slices.ContainsFunc(stagedAll, func(s staged) bool { return s.rel == l.rel }) {
				if err := w.removeAll(w.relPath(dst, l.rel)); err != nil {
					return nil, ioPath(err, w.relPath(dst, l.rel))
				}
			}
		}
	}
	sort.Strings(copied)
	sort.Strings(skipped)
	return &HandoverResult{Copied: copied, Skipped: skipped}, nil
}
