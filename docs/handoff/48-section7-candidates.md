# #48 §7: third-party validation run, candidate issues (C, 2026-11-08)

Goal: one full PatchPilot run on an unfamiliar public Python repo, then the human approves the diff and a **draft PR goes to our fork only**. This page is only the shortlist. **Nothing has been run or posted.** Running a third-party repo's code from this laptop was blocked; reproduction belongs to PatchPilot's own sandbox on the demo laptop.

## Pick: astanin/python-tabulate #494 "Short headers silently drop columns from ragged tables"
- https://github.com/astanin/python-tabulate/issues/494, opened 2026-11-02 against current master (`268615a5`). No comments, nobody assigned, no PR mentions it (checked 2026-11-08).
- **Clear expected vs actual, 2-line repro:**
  ```python
  from tabulate import tabulate
  tabulate([["a"], ["b", "KEEP"]], headers=["tail"])   # "KEEP" missing; without headers it is kept
  ```
- **Still relevant (read on master):** `_normalize_tabular_data` pads headers using `len(rows[0])` only (`tabulate/__init__.py:1609`), so columns after a short first row are cut. A likely small fix is to pad to the widest row. That gives a small diff in one source file, which is good for G4.
- **Supported:** Python, `pyproject.toml`, `test/` + `tox.ini` (pytest), pure Python with no compiled deps, 2.6k stars, PRs merged this week. Linux-neutral.
- Things to know:
  - The issue author offered the maintainer a paid fix. Our PR goes to **our fork** as a draft, per §7, so it doesn't compete upstream.
  - There's no CONTRIBUTING.md. PatchPilot's own policy check runs on the README.

## Rejected (and why), useful demo material for the assessment layer
| Issue | Why not | What PatchPilot should say |
|---|---|---|
| more-itertools #1268 (`seekable(maxlen=0)`) | Still open, but **already fixed** by merged PR #1294 | A real example of "lookups can be wrong": the open-issue check alone would call it fixable |
| michelcaradec/mdtable #3 (CSV IndexError) | Clear bug, but the repo has **no tests** | `UNSUPPORTED` (`unsupported:no_tests`), a good live demo of the new assessment card |
| dateutil #942, #905 | Behaviour argued against the RFC by maintainers; no agreed expected behaviour | Should land as `HUMAN_DECISION` at best |
| arrow #1153 | Expected behaviour (LMT offsets for year 0001), per the last comment | Not a bug |
| arrow #1136 | A design choice (naive vs absolute DST difference) | Not a clear bug |

## How to run it (demo laptop)
1. Paste the tabulate #494 URL on S-01 and read the assessment card. Expected: READY or HUMAN_DECISION, depending on the model's extraction.
2. Run, then check G3 fails 2/2, G5 passes 2/2 in fresh containers, and no baseline test regresses.
3. **The human** reviews the exact diff and evidence and approves. Then publish the draft PR to our fork.
4. Record the run ID, issue URL, outcome and PR URL in the #48 handoff.
