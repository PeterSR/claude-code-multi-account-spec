package multiaccount

import (
	"io"
	"slices"
	"strings"
	"unicode/utf8"
)

// Marker kinds returned by ParseMarker.
const (
	MarkerNone    = "none"
	MarkerAccount = "account"
	MarkerDefault = "default"
	MarkerPool    = "pool"
	MarkerList    = "list"
)

// Marker is a parsed .claude-account file. Candidates is the ordered account list: empty for none
// and pool, one entry for account and default, the entries for list (Name is the first).
type Marker struct {
	Kind       string   `json:"kind"`
	Name       *string  `json:"name"`
	Pool       *string  `json:"pool"`
	Candidates []string `json:"candidates"`
}

const (
	markerMaxBytes = 1024
	markerTrim     = " \t\r\v\f"
	// utf8BOM is U+FEFF, stripped once from the start of a marker.
	utf8BOM = "\xef\xbb\xbf"
)

// ParseMarker parses a .claude-account file (A4 marker parsing). A missing file, an unreachable
// one, a dangling link or a directory is MarkerNone. A FIFO or device, an unreadable file, one over
// 1024 bytes, one that is not valid UTF-8, or one without a valid first line is MARKER_INVALID.
func ParseMarker(fs FS, path string) (m *Marker, err error) {
	defer func() { err = ioErr(err) }()
	r, err := parseMarker(fs, path)
	if err != nil {
		return nil, err
	}
	return &r, nil
}

func parseMarker(fsys FS, path string) (Marker, error) {
	none := Marker{Kind: MarkerNone, Candidates: []string{}}
	if _, err := fsys.Lstat(path); err != nil {
		return none, nil // ENOENT, ENOTDIR, EACCES: no marker
	}
	fi, err := fsys.Stat(path)
	if err != nil {
		return none, nil // dangling
	}
	switch fi.Type {
	case TypeDir:
		return none, nil
	case TypeFile:
	default:
		return none, newError(CodeMarkerInvalid, path, "marker is not a regular file")
	}
	f, err := fsys.Open(path, OpenRead|OpenNonBlock, 0)
	if err != nil {
		return none, newError(CodeMarkerInvalid, path, "cannot open marker: %v", err)
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, markerMaxBytes+1))
	if err != nil {
		return none, newError(CodeMarkerInvalid, path, "cannot read marker: %v", err)
	}
	if len(data) > markerMaxBytes {
		return none, newError(CodeMarkerInvalid, path, "marker is longer than %d bytes", markerMaxBytes)
	}
	if !utf8.Valid(data) {
		return none, newError(CodeMarkerInvalid, path, "marker is not valid UTF-8")
	}
	text := strings.TrimPrefix(string(data), utf8BOM)
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSuffix(line, "\r")
		line = strings.Trim(line, markerTrim)
		if line == "" || line[0] == '#' {
			continue
		}
		if strings.Contains(line, ",") {
			parts := strings.Split(line, ",")
			for i, x := range parts {
				x = strings.Trim(x, markerTrim)
				parts[i] = x
				if x != DefaultName && !ValidName(x) {
					return none, newError(CodeMarkerInvalid, path, "invalid marker list entry %q", x)
				}
			}
			for i, x := range parts {
				if slices.Index(parts, x) != i {
					return none, newError(CodeMarkerInvalid, path, "duplicate marker list entry %q", x)
				}
			}
			return Marker{Kind: MarkerList, Name: strp(parts[0]), Candidates: parts}, nil
		}
		switch {
		case line == DefaultName:
			return Marker{Kind: MarkerDefault, Name: strp(DefaultName), Candidates: []string{DefaultName}}, nil
		case line[0] == '@' && ValidName(line[1:]):
			return Marker{Kind: MarkerPool, Pool: strp(line[1:]), Candidates: []string{}}, nil
		case ValidName(line):
			return Marker{Kind: MarkerAccount, Name: strp(line), Candidates: []string{line}}, nil
		}
		return none, newError(CodeMarkerInvalid, path, "invalid marker target %q", line)
	}
	return none, newError(CodeMarkerInvalid, path, "marker has no target")
}
