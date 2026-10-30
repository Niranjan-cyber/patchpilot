#!/usr/bin/env bash
# Human-run (Claude may not create public repos): publishes the tinycalc demo repo with its 3 planted-bug issues.
set -euo pipefail
cd "$(dirname "$0")/../data/tinycalc"
gh repo create Niranjan-cyber/tinycalc --public --source . --push
R=Niranjan-cyber/tinycalc
gh issue create -R $R -t "divide(x, 0) returns 0 instead of raising ZeroDivisionError" -b $'`tinycalc.divide(1, 0)` returns `0`.\n\n**Expected:** `ZeroDivisionError`, like Python\'s `/`. A silent 0 hides bad input.\n\n```python\nfrom tinycalc import divide\ndivide(1, 0)  # -> 0\n```'
gh issue create -R $R -t "mean([]) returns 0 instead of raising ValueError" -b $'`tinycalc.mean([])` returns `0`.\n\n**Expected:** `ValueError` (the mean of no values is undefined, as in `statistics.mean`).\n\n```python\nfrom tinycalc import mean\nmean([])  # -> 0\n```'
gh issue create -R $R -t 'parse_number("1,000") crashes with ValueError' -b $'The docstring says `parse_number` accepts "1,000", but:\n\n```python\nfrom tinycalc import parse_number\nparse_number("1,000")\n# ValueError: invalid literal for int() with base 10: \'1,000\'\n```\n\n**Expected:** `1000`.'
gh issue list -R $R
