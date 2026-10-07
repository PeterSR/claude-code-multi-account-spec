// Package multiaccount implements the claude-code-multi-account spec: where Claude Code
// accounts live on disk (Part A) and optional building blocks for tools (Part B).
//
// The library takes everything as explicit inputs ([Inputs]): the environment, the working
// directory, the home directory, the platform and a filesystem. It never reads process globals;
// [FromProcess] is the one convenience constructor that fills them from the running process.
//
// Part B blocks: B1 (env, credential locations), B2 (identity, usage and read-only
// credentials), B3 (live sessions), B4 (session handover), B5 (availability state), B6 (pools)
// and B7 (active slot). The package does no network I/O, never
// rewrites credentials and never refreshes tokens.
package multiaccount

//go:generate cp ../../spec/reserved.json reserved.json
//go:generate sh -c "python3 tools/gen_nfc.py > nfc_tables.go && gofmt -w nfc_tables.go"
