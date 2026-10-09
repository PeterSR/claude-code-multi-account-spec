package multiaccount

import "strings"

// Platform names used by the spec.
const (
	PlatformLinux  = "linux"
	PlatformDarwin = "darwin"
	PlatformWin32  = "win32"
)

// pathFlavor implements the Node path.posix / path.win32 subset the spec uses.
type pathFlavor struct{ win bool }

func flavorFor(platform string) pathFlavor { return pathFlavor{win: platform == PlatformWin32} }

func (p pathFlavor) sep() string {
	if p.win {
		return `\`
	}
	return "/"
}

func (p pathFlavor) isSep(c byte) bool { return c == '/' || (p.win && c == '\\') }

func (p pathFlavor) splitComps(s string) []string {
	var out []string
	start := 0
	for i := 0; i <= len(s); i++ {
		if i == len(s) || p.isSep(s[i]) {
			if i > start {
				out = append(out, s[start:i])
			}
			start = i + 1
		}
	}
	return out
}

// split returns the root prefix ("" for a relative path) and the non-empty components.
func (p pathFlavor) split(s string) (root string, comps []string) {
	if p.win {
		if len(s) >= 3 && isLetter(s[0]) && s[1] == ':' && p.isSep(s[2]) {
			return s[:2] + `\`, p.splitComps(s[3:])
		}
		return "", p.splitComps(s)
	}
	if strings.HasPrefix(s, "/") {
		return "/", p.splitComps(s)
	}
	return "", p.splitComps(s)
}

func isLetter(c byte) bool { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') }

// isAbs reports whether s is absolute in this flavour (win32: a drive letter, colon, separator).
func (p pathFlavor) isAbs(s string) bool {
	root, _ := p.split(s)
	return root != ""
}

// normalize drops empty and "." components and resolves "..", staying at the root.
func (p pathFlavor) normalize(s string) string {
	root, comps := p.split(s)
	out := make([]string, 0, len(comps))
	for _, c := range comps {
		switch c {
		case ".":
		case "..":
			if len(out) > 0 && out[len(out)-1] != ".." {
				out = out[:len(out)-1]
			} else if root == "" {
				out = append(out, "..")
			}
		default:
			out = append(out, c)
		}
	}
	if root == "" {
		if len(out) == 0 {
			return "."
		}
		return strings.Join(out, p.sep())
	}
	return root + strings.Join(out, p.sep())
}

// join is normalize of the parts joined with the separator.
func (p pathFlavor) join(parts ...string) string { return p.normalize(strings.Join(parts, p.sep())) }

// parent returns the parent of a normalised path, and false at a root or for an empty path.
func (p pathFlavor) parent(s string) (string, bool) {
	root, comps := p.split(s)
	if len(comps) == 0 {
		return "", false
	}
	return root + strings.Join(comps[:len(comps)-1], p.sep()), true
}

// dirname is the parent, or the path itself at a root.
func (p pathFlavor) dirname(s string) string {
	s = p.normalize(s)
	if par, ok := p.parent(s); ok {
		return par
	}
	return s
}

// fold is ASCII lower-casing, the only case folding the spec uses.
func fold(s string) string {
	for i := 0; i < len(s); i++ {
		if s[i] >= 'A' && s[i] <= 'Z' {
			b := []byte(s)
			for j := i; j < len(b); j++ {
				if b[j] >= 'A' && b[j] <= 'Z' {
					b[j] += 32
				}
			}
			return string(b)
		}
	}
	return s
}

// ValidName reports whether name fully matches [a-z0-9][a-z0-9_-]{0,31}. Pool names use the same grammar.
func ValidName(name string) bool {
	if len(name) == 0 || len(name) > 32 {
		return false
	}
	for i := 0; i < len(name); i++ {
		c := name[i]
		switch {
		case c >= 'a' && c <= 'z', c >= '0' && c <= '9':
		case i > 0 && (c == '_' || c == '-'):
		default:
			return false
		}
	}
	return true
}
