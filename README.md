# Claude Code multi account spec

A draft standard and Go, TypeScript and Python libraries for storing and addressing multiple
Claude Code accounts on one machine. The spec and libraries are version 0.2.3. This project
provides libraries, not an account switching CLI.

- [SPEC.md](SPEC.md): account storage, addressing and optional building blocks.
- [spec/reserved.json](spec/reserved.json): reserved account names.
- [go/](go), [typescript/](typescript), [python/](python): the three libraries.
- [conformance/FORMAT.md](conformance/FORMAT.md): shared case format and runner protocol.
- [PARITY.md](PARITY.md): library API parity; [SPEC-GAPS.md](conformance/SPEC-GAPS.md): open questions.

Install a library:

```sh
go get github.com/PeterSR/claude-code-multi-account-spec/go@v0.2.3
npm install claude-code-multi-account-core
pip install claude-code-multi-account-core   # import claude_code_multi_account
```

To develop, use Go 1.25 or newer, Node.js 22 or newer, Python 3.10 or newer, and uv. Install the
TypeScript development dependencies with `npm ci` in `typescript`; uv installs the
Python development dependencies when running the tests. From the repository root:

```sh
(cd typescript && npm run build && npm test)
(cd go && go vet ./... && go test ./...)
(cd python && uv run pytest -q)
python3 conformance/validate_cases.py
conformance/run.sh --require-all
```

The conformance suite requires Bash and Python 3, builds the Go runner, and uses the built
TypeScript runner and the Python environment. Its summary must list all three runners passing
every case with no divergence; `--require-all` makes a missing runner a failure.

MIT licensed, see [LICENSE](LICENSE).

This is an independent project and is not affiliated with Anthropic. The spec is a draft;
macOS and Windows behavior has conformance coverage but still needs native runtime validation.
