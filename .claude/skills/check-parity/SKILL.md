---
name: check-parity
description: Verify the Go, TypeScript and Python libraries pass the shared conformance cases and match each other and PARITY.md. Use after changing SPEC.md, a case file, or any library, and before merging such a change.
---

# check-parity

Confirm the three libraries agree with [`SPEC.md`](../../../SPEC.md), with the cases in
[`conformance/cases`](../../../conformance/cases), and with each other. Format and comparison rules
are in [`conformance/FORMAT.md`](../../../conformance/FORMAT.md); the capability list is
[`PARITY.md`](../../../PARITY.md).

Run these and report a concise PASS/FAIL table:

1. **Case files are well formed**
   ```sh
   python3 conformance/validate_cases.py
   ```

2. **Per-language unit tests** (only for libraries that exist)
   ```sh
   (cd go && go vet ./... && go test ./...)
   (cd typescript && npm run build && npm test)
   uv run --project python pytest
   ```

3. **Cross-library conformance** (builds and runs the Go, TypeScript and Python runners on every case)
   ```sh
   bash conformance/run.sh
   ```
   A `FAIL` for any runner, or a `DIVERGE` marker, is a **parity break**, never a flake. Narrow with
   `--runner go|ts|py` or `--case 'a4-*'` while investigating. A runner reported as skipped means it is missing or has not been built; investigate it and
   do not count it as a pass.

4. **API-surface audit** - open [`PARITY.md`](../../../PARITY.md) and confirm every row exists in
   `go`, `typescript` and `python` under the listed name. A capability in one
   library but missing in another is a parity break. If the spec gained an op, it must appear in the
   spec, `conformance/FORMAT.md`, `conformance/gen/`, the cases, `validate_cases.py`, all three
   libraries and the parity matrix.

5. **Spec gaps** - if the change relied on a reading listed in
   [`conformance/SPEC-GAPS.md`](../../../conformance/SPEC-GAPS.md), check whether the spec now says
   it and remove or update the entry.

Report: per-step PASS/FAIL, and for any failure the specific runner, case id and the assertion that
broke. Do not declare parity green unless steps 1 to 4 all pass and no runner was skipped.
