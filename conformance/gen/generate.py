#!/usr/bin/env python3
"""Regenerate conformance/cases/*.json from the hand written case tables in this directory.

The case files are the contract; this generator only exists so a spec change can be applied to many
cases at once. After running it, run conformance/validate_cases.py and
`conformance/run.sh --cmd "python3 conformance/gen/reference_runner.py" --runner none`.
"""
import os
import re
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_lib
import gen_a, gen_a4, gen_b, gen_v2  # noqa: F401  (importing registers the cases)

gen_lib.write_all()
counts = collections.Counter(re.match(r'([a-z]\d)', k).group(1) for k in gen_lib.CASES)
print(len(gen_lib.CASES), 'cases', dict(sorted(counts.items())))
