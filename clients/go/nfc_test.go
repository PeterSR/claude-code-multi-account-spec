package multiaccount

import (
	"bytes"
	"os"
	"reflect"
	"testing"
)

func TestNFC(t *testing.T) {
	cases := map[string]string{
		"josé": "josé",
		"josé":  "josé",
		"plain": "plain",
		"ạ̇":   "ạ̇",
		"ạ̇":   "ạ̇", // reordered by combining class
		"각":   "각",  // Hangul jamo
		"Å":     "Å",  // singleton decomposition
		"Å":     "Å",
	}
	for in, want := range cases {
		if got := nfc(in); got != want {
			t.Errorf("nfc(%+q) = %+q, want %+q", in, got, want)
		}
	}
}

func TestEmbeddedReservedMatchesSpec(t *testing.T) {
	b, err := os.ReadFile("../../spec/reserved.json")
	if err != nil {
		t.Skip("spec/reserved.json not found:", err)
	}
	if !bytes.Equal(b, reservedJSON) {
		t.Error("reserved.json is stale: run go generate")
	}
	want, _ := ParseReserved(b)
	if got := ReservedNames(); !reflect.DeepEqual(got, want) {
		t.Errorf("ReservedNames() = %v, want %v", got, want)
	}
}
