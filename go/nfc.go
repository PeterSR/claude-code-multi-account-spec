package multiaccount

import "sort"

const (
	hangulSBase  = 0xAC00
	hangulLBase  = 0x1100
	hangulVBase  = 0x1161
	hangulTBase  = 0x11A7
	hangulLCount = 19
	hangulVCount = 21
	hangulTCount = 28
	hangulNCount = hangulVCount * hangulTCount
	hangulSCount = hangulLCount * hangulNCount
)

func isASCII(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] >= 0x80 {
			return false
		}
	}
	return true
}

func decomposeRune(r rune, out []rune) []rune {
	if r >= hangulSBase && r < hangulSBase+hangulSCount {
		s := r - hangulSBase
		out = append(out, hangulLBase+s/hangulNCount, hangulVBase+(s%hangulNCount)/hangulTCount)
		if t := s % hangulTCount; t != 0 {
			out = append(out, hangulTBase+t)
		}
		return out
	}
	if d, ok := nfcDecomp[r]; ok {
		for _, x := range d {
			out = decomposeRune(x, out)
		}
		return out
	}
	return append(out, r)
}

func composePair(a, b rune) (rune, bool) {
	if a >= hangulLBase && a < hangulLBase+hangulLCount && b >= hangulVBase && b < hangulVBase+hangulVCount {
		return hangulSBase + ((a-hangulLBase)*hangulVCount+(b-hangulVBase))*hangulTCount, true
	}
	if a >= hangulSBase && a < hangulSBase+hangulSCount && (a-hangulSBase)%hangulTCount == 0 &&
		b > hangulTBase && b < hangulTBase+hangulTCount {
		return a + (b - hangulTBase), true
	}
	c, ok := nfcComp[[2]rune{a, b}]
	return c, ok
}

// nfc returns s in Unicode Normalization Form C. Invalid UTF-8 bytes become U+FFFD.
func nfc(s string) string {
	if isASCII(s) {
		return s
	}
	var d []rune
	for _, r := range s {
		d = decomposeRune(r, d)
	}
	// canonical ordering: stable sort of each run of non-starters by combining class
	for i := 0; i < len(d); {
		if nfcCCC[d[i]] == 0 {
			i++
			continue
		}
		j := i
		for j < len(d) && nfcCCC[d[j]] != 0 {
			j++
		}
		run := d[i:j]
		sort.SliceStable(run, func(a, b int) bool { return nfcCCC[run[a]] < nfcCCC[run[b]] })
		i = j
	}
	// canonical composition
	out := make([]rune, 0, len(d))
	starter := -1
	last := 0 // combining class of the last rune in out
	for _, r := range d {
		c := int(nfcCCC[r])
		if starter >= 0 {
			blocked := len(out)-1 != starter && last >= c
			if !blocked {
				if p, ok := composePair(out[starter], r); ok {
					out[starter] = p
					continue
				}
			}
		}
		if c == 0 {
			starter = len(out)
		}
		last = c
		out = append(out, r)
	}
	return string(out)
}
