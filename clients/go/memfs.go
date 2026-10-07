package multiaccount

import (
	"encoding/base64"
	"fmt"
	"io"
	"sort"
	"strconv"
	"time"
	"unicode/utf8"
)

// MemEntry describes one entry of an in-memory filesystem, using the field names of the
// conformance case files. Every ancestor of a loaded path that is not itself an entry exists
// implicitly as a plain directory.
type MemEntry struct {
	Type    FileType `json:"type"`
	Content string   `json:"content,omitempty"`
	// ContentBase64 holds bytes that are not valid UTF-8. It excludes Content.
	ContentBase64 string    `json:"contentBase64,omitempty"`
	Mode          string    `json:"mode,omitempty"` // octal, e.g. "0700"
	Target        string    `json:"target,omitempty"`
	Inode         int       `json:"inode,omitempty"` // 1..999; entries with equal inode and dev are one object
	Dev           int       `json:"dev,omitempty"`   // default 1
	Unreadable    bool      `json:"unreadable,omitempty"`
	Mtime         time.Time `json:"mtime,omitzero"` // default: the clock given to NewMemFS
}

// MemDump is one entry of [MemFS.Dump].
type MemDump struct {
	Type    FileType `json:"type"`
	Mode    string   `json:"mode"`
	Content *string  `json:"content,omitempty"`
	// ContentBase64 replaces Content when the bytes are not valid UTF-8.
	ContentBase64 *string `json:"contentBase64,omitempty"`
	Target        *string `json:"target,omitempty"`
}

type memNode struct {
	typ        FileType
	children   map[string]*memNode
	content    []byte
	target     string
	dev, ino   uint64
	mode       uint32
	mtime      time.Time
	unreadable bool
}

type memFrame struct {
	name string
	n    *memNode
}

// MemFS is the in-memory fake filesystem of the conformance format (FORMAT.md section 3).
// It is not safe for concurrent use.
type MemFS struct {
	p     pathFlavor
	ci    bool
	now   time.Time
	roots map[string]*memNode // keyed by (folded when case insensitive) root prefix
	rname map[string]string   // stored root prefix
	auto  uint64
	byIno map[[2]uint64]*memNode
}

// NewMemFS returns an empty filesystem for platform (path flavour), case behaviour and a fixed
// clock used for new mtimes.
func NewMemFS(platform string, caseInsensitive bool, now time.Time) *MemFS {
	return &MemFS{
		p: flavorFor(platform), ci: caseInsensitive, now: now,
		roots: map[string]*memNode{}, rname: map[string]string{},
		auto: 1000, byIno: map[[2]uint64]*memNode{},
	}
}

func (m *MemFS) rk(r string) string {
	if m.ci {
		return fold(r)
	}
	return r
}

func (m *MemFS) newIno() uint64 { m.auto++; return m.auto - 1 }

// EnsureRoot makes sure the root of an absolute path exists.
func (m *MemFS) EnsureRoot(path string) {
	r, _ := m.p.split(path)
	if r != "" {
		m.root(r)
	}
}

func (m *MemFS) root(r string) *memNode {
	k := m.rk(r)
	if n, ok := m.roots[k]; ok {
		return n
	}
	n := &memNode{typ: TypeDir, children: map[string]*memNode{}, mode: 0o755, mtime: m.now, dev: 1, ino: m.newIno()}
	m.roots[k] = n
	m.rname[k] = r
	return n
}

func (m *MemFS) child(d *memNode, name string) (string, *memNode) {
	if m.ci {
		f := fold(name)
		for k, v := range d.children {
			if fold(k) == f {
				return k, v
			}
		}
		return "", nil
	}
	if v, ok := d.children[name]; ok {
		return name, v
	}
	return "", nil
}

func (m *MemFS) ensureDir(path string) (*memNode, error) {
	r, comps := m.p.split(path)
	cur := m.root(r)
	for _, c := range comps {
		_, v := m.child(cur, c)
		if v == nil {
			v = &memNode{typ: TypeDir, children: map[string]*memNode{}, mode: 0o755, mtime: m.now, dev: 1, ino: m.newIno()}
			cur.children[c] = v
		}
		if v.typ != TypeDir {
			return nil, fmt.Errorf("memfs: %s: ancestor is not a directory", path)
		}
		cur = v
	}
	return cur, nil
}

// Load adds entries. Keys are absolute, normalised paths. Entries load in order of component
// count, then bytewise, so a parent always loads before its children.
func (m *MemFS) Load(entries map[string]MemEntry) error {
	keys := make([]string, 0, len(entries))
	for k := range entries {
		keys = append(keys, k)
	}
	depth := func(k string) int { _, c := m.p.split(k); return len(c) }
	sort.Slice(keys, func(i, j int) bool {
		di, dj := depth(keys[i]), depth(keys[j])
		if di != dj {
			return di < dj
		}
		return keys[i] < keys[j]
	})
	for _, k := range keys {
		if r, _ := m.p.split(k); r == "" {
			return fmt.Errorf("memfs: %q is not absolute", k)
		}
		m.EnsureRoot(k)
	}
	for _, k := range keys {
		if err := m.load(k, entries[k]); err != nil {
			return err
		}
	}
	return nil
}

func (m *MemFS) load(key string, e MemEntry) error {
	par, ok := m.p.parent(key)
	if !ok {
		return fmt.Errorf("memfs: %q has no parent", key)
	}
	parent, err := m.ensureDir(par)
	if err != nil {
		return err
	}
	_, comps := m.p.split(key)
	name := comps[len(comps)-1]
	dev := uint64(1)
	if e.Dev != 0 {
		dev = uint64(e.Dev)
	}
	if e.Inode != 0 {
		if n, ok := m.byIno[[2]uint64{dev, uint64(e.Inode)}]; ok {
			parent.children[name] = n
			return nil
		}
	}
	mode := defaultMode(e.Type)
	if e.Mode != "" {
		v, err := strconv.ParseUint(e.Mode, 8, 32)
		if err != nil {
			return fmt.Errorf("memfs: %s: bad mode %q", key, e.Mode)
		}
		mode = uint32(v)
	}
	mt := e.Mtime
	if mt.IsZero() {
		mt = m.now
	}
	n := &memNode{typ: e.Type, mode: mode, mtime: mt, dev: dev, unreadable: e.Unreadable}
	if e.Inode != 0 {
		n.ino = uint64(e.Inode)
		m.byIno[[2]uint64{dev, n.ino}] = n
	} else {
		n.ino = m.newIno()
	}
	switch e.Type {
	case TypeDir:
		n.children = map[string]*memNode{}
	case TypeFile:
		if e.ContentBase64 != "" {
			b, err := base64.StdEncoding.DecodeString(e.ContentBase64)
			if err != nil {
				return fmt.Errorf("memfs: %s: bad contentBase64: %v", key, err)
			}
			n.content = b
		} else {
			n.content = []byte(e.Content)
		}
	case TypeSymlink, TypeJunction:
		n.target = e.Target
	}
	if old, ok := parent.children[name]; ok && old.typ == TypeDir && e.Type == TypeDir {
		n.children = old.children // an implicit directory made explicit
	}
	parent.children[name] = n
	return nil
}

func defaultMode(t FileType) uint32 {
	switch t {
	case TypeDir:
		return 0o755
	case TypeSymlink, TypeJunction:
		return 0o777
	}
	return 0o644
}

// walk implements the path lookup of FORMAT.md 3.4 and returns the frames from the root.
func (m *MemFS) walk(op, path string, followLast bool) ([]memFrame, error) {
	root, comps := m.p.split(path)
	if root == "" {
		return nil, fsErr(op, path, ENOENT)
	}
	k := m.rk(root)
	rn, ok := m.roots[k]
	if !ok {
		return nil, fsErr(op, path, ENOENT)
	}
	stack := []memFrame{{m.rname[k], rn}}
	queue := append([]string(nil), comps...)
	hops := 0
	for len(queue) > 0 {
		c := queue[0]
		queue = queue[1:]
		if c == "" || c == "." {
			continue
		}
		if c == ".." {
			if len(stack) > 1 {
				stack = stack[:len(stack)-1]
			}
			continue
		}
		cur := stack[len(stack)-1].n
		if cur.typ != TypeDir {
			return nil, fsErr(op, path, ENOTDIR)
		}
		if cur.unreadable {
			return nil, fsErr(op, path, EACCES)
		}
		name, ch := m.child(cur, c)
		if ch == nil {
			return nil, fsErr(op, path, ENOENT)
		}
		if ch.typ.IsLink() && (len(queue) > 0 || followLast) {
			hops++
			if hops > 40 {
				return nil, fsErr(op, path, ELOOP)
			}
			if ch.unreadable {
				return nil, fsErr(op, path, EACCES)
			}
			r2, c2 := m.p.split(ch.target)
			if r2 != "" {
				k2 := m.rk(r2)
				rn2, ok := m.roots[k2]
				if !ok {
					return nil, fsErr(op, path, ENOENT)
				}
				stack = []memFrame{{m.rname[k2], rn2}}
			}
			queue = append(append([]string(nil), c2...), queue...)
			continue
		}
		stack = append(stack, memFrame{name, ch})
	}
	return stack, nil
}

func (m *MemFS) info(n *memNode) FileInfo {
	return FileInfo{Type: n.typ, Dev: n.dev, Ino: n.ino, Size: int64(len(n.content)), Mode: n.mode, Mtime: n.mtime}
}

// Lstat implements [FS].
func (m *MemFS) Lstat(path string) (FileInfo, error) {
	st, err := m.walk("lstat", path, false)
	if err != nil {
		return FileInfo{}, err
	}
	return m.info(st[len(st)-1].n), nil
}

// Stat implements [FS].
func (m *MemFS) Stat(path string) (FileInfo, error) {
	st, err := m.walk("stat", path, true)
	if err != nil {
		return FileInfo{}, err
	}
	return m.info(st[len(st)-1].n), nil
}

// Readlink implements [FS].
func (m *MemFS) Readlink(path string) (string, error) {
	st, err := m.walk("readlink", path, false)
	if err != nil {
		return "", err
	}
	n := st[len(st)-1].n
	if !n.typ.IsLink() {
		return "", fsErr("readlink", path, EINVAL)
	}
	return n.target, nil
}

// ReadDir implements [FS].
func (m *MemFS) ReadDir(path string) ([]string, error) {
	st, err := m.walk("readdir", path, true)
	if err != nil {
		return nil, err
	}
	n := st[len(st)-1].n
	if n.typ != TypeDir {
		return nil, fsErr("readdir", path, ENOTDIR)
	}
	if n.unreadable {
		return nil, fsErr("readdir", path, EACCES)
	}
	names := make([]string, 0, len(n.children))
	for k := range n.children {
		names = append(names, k)
	}
	sort.Strings(names)
	return names, nil
}

// Realpath implements [FS].
func (m *MemFS) Realpath(path string) (string, error) {
	st, err := m.walk("realpath", path, true)
	if err != nil {
		return "", err
	}
	names := make([]string, 0, len(st)-1)
	for _, f := range st[1:] {
		names = append(names, f.name)
	}
	out := st[0].name
	for i, n := range names {
		if i > 0 {
			out += m.p.sep()
		}
		out += n
	}
	return out, nil
}

type memFile struct {
	n     *memNode
	off   int
	write bool
}

func (f *memFile) Read(p []byte) (int, error) {
	if f.write || f.off >= len(f.n.content) {
		return 0, io.EOF
	}
	c := copy(p, f.n.content[f.off:])
	f.off += c
	return c, nil
}

func (f *memFile) Write(p []byte) (int, error) {
	if !f.write {
		return 0, fsErr("write", "", EINVAL)
	}
	f.n.content = append(f.n.content, p...)
	return len(p), nil
}

func (f *memFile) Sync() error  { return nil }
func (f *memFile) Close() error { return nil }

// Open implements [FS].
func (m *MemFS) Open(path string, flags OpenFlag, mode uint32) (File, error) {
	if flags&OpenCreateExcl != 0 {
		pn, name, err := m.parentOf("open", path)
		if err != nil {
			return nil, err
		}
		if _, err := m.Lstat(path); err == nil {
			return nil, fsErr("open", path, EEXIST)
		} else if ErrnoOf(err) != ENOENT {
			return nil, err
		}
		n := &memNode{typ: TypeFile, mode: mode, mtime: m.now, dev: 1, ino: m.newIno()}
		pn.children[name] = n
		return &memFile{n: n, write: true}, nil
	}
	st, err := m.walk("open", path, flags&OpenNoFollow == 0)
	if err != nil {
		return nil, err
	}
	n := st[len(st)-1].n
	switch {
	case n.typ.IsLink():
		return nil, fsErr("open", path, ELOOP)
	case n.typ == TypeDir:
		return nil, fsErr("open", path, EISDIR)
	case n.unreadable:
		return nil, fsErr("open", path, EACCES)
	}
	return &memFile{n: n}, nil
}

func (m *MemFS) parentOf(op, path string) (*memNode, string, error) {
	path = m.p.normalize(path)
	par, ok := m.p.parent(path)
	if !ok {
		return nil, "", fsErr(op, path, EINVAL)
	}
	st, err := m.walk(op, par, true)
	if err != nil {
		return nil, "", err
	}
	pn := st[len(st)-1].n
	if pn.typ != TypeDir {
		return nil, "", fsErr(op, path, ENOTDIR)
	}
	_, comps := m.p.split(path)
	return pn, comps[len(comps)-1], nil
}

func (m *MemFS) mustNotExist(op, path string) error {
	if _, err := m.Lstat(path); err == nil {
		return fsErr(op, path, EEXIST)
	} else if ErrnoOf(err) != ENOENT {
		return err
	}
	return nil
}

// Mkdir implements [FS].
func (m *MemFS) Mkdir(path string, mode uint32) error {
	if err := m.mustNotExist("mkdir", path); err != nil {
		return err
	}
	pn, name, err := m.parentOf("mkdir", path)
	if err != nil {
		return err
	}
	pn.children[name] = &memNode{typ: TypeDir, children: map[string]*memNode{}, mode: mode, mtime: m.now, dev: 1, ino: m.newIno()}
	return nil
}

// Symlink implements [FS]. On win32 a directory link is a junction.
func (m *MemFS) Symlink(target, path string, kind LinkKind) error {
	if err := m.mustNotExist("symlink", path); err != nil {
		return err
	}
	pn, name, err := m.parentOf("symlink", path)
	if err != nil {
		return err
	}
	t := TypeSymlink
	if m.p.win && kind == LinkDir {
		t = TypeJunction
	}
	pn.children[name] = &memNode{typ: t, mode: 0o777, mtime: m.now, dev: 1, ino: m.newIno(), target: target}
	return nil
}

// Rename implements [FS].
func (m *MemFS) Rename(oldPath, newPath string) error {
	apn, an, err := m.parentOf("rename", oldPath)
	if err != nil {
		return err
	}
	ak, node := m.child(apn, an)
	if node == nil {
		return fsErr("rename", oldPath, ENOENT)
	}
	bpn, bn, err := m.parentOf("rename", newPath)
	if err != nil {
		return err
	}
	if bk, ex := m.child(bpn, bn); ex != nil {
		if m.p.win && (ex.typ == TypeJunction || node.typ == TypeJunction) {
			return fsErr("rename", newPath, EEXIST) // Windows cannot replace a directory entry
		}
		if (ex.typ == TypeDir) != (node.typ == TypeDir) {
			return fsErr("rename", newPath, EEXIST)
		}
		if ex.typ == TypeDir && len(ex.children) > 0 {
			return fsErr("rename", newPath, ENOTEMPTY)
		}
		delete(bpn.children, bk)
	}
	delete(apn.children, ak)
	bpn.children[bn] = node
	return nil
}

func (m *MemFS) remove(op, path string, wantDir bool) error {
	pn, name, err := m.parentOf(op, path)
	if err != nil {
		return err
	}
	k, n := m.child(pn, name)
	if n == nil {
		return fsErr(op, path, ENOENT)
	}
	if wantDir && n.typ == TypeJunction {
		// rmdir on a junction removes the link, never its target
	} else if wantDir {
		if n.typ != TypeDir {
			return fsErr(op, path, ENOTDIR)
		}
		if len(n.children) > 0 {
			return fsErr(op, path, ENOTEMPTY)
		}
	} else if n.typ == TypeDir || n.typ == TypeJunction {
		return fsErr(op, path, EISDIR)
	}
	delete(pn.children, k)
	return nil
}

// Rmdir implements [FS].
func (m *MemFS) Rmdir(path string) error { return m.remove("rmdir", path, true) }

// Unlink implements [FS].
func (m *MemFS) Unlink(path string) error { return m.remove("unlink", path, false) }

// Dump returns every path reachable through the tree (not through links), in the shape of the
// conformance `fs` dump.
func (m *MemFS) Dump() map[string]MemDump {
	out := map[string]MemDump{}
	var rec func(path string, n *memNode)
	rec = func(path string, n *memNode) {
		d := MemDump{Type: n.typ, Mode: fmt.Sprintf("%04o", n.mode)}
		switch {
		case n.typ == TypeFile:
			if utf8.Valid(n.content) {
				s := string(n.content)
				d.Content = &s
			} else {
				s := base64.StdEncoding.EncodeToString(n.content)
				d.ContentBase64 = &s
			}
		case n.typ.IsLink():
			t := n.target
			d.Target = &t
		}
		out[path] = d
		if n.typ == TypeDir {
			for k, v := range n.children {
				rec(m.p.join(path, k), v)
			}
		}
	}
	for k, r := range m.roots {
		for name, v := range r.children {
			rec(m.rname[k]+name, v)
		}
	}
	return out
}
