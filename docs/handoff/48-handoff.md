# #48 engineering handoff (Phase 5): DRAFT, kept current by C

Status at 2026-11-08 ~20:00 UTC. Items marked **PENDING** need the team or the human. Nothing here claims a run or a PR that didn't happen.

## 1. Changes implemented
| Change | Where | State |
|---|---|---|
| A timed-out sandbox step's log is never empty: partial bytes decoded, explicit time-limit line, "printed nothing" when there was no output (#43 follow-up) | PR #49 | **merged** (`26d0609`) |
| Intake assessment layer, contracts v0.4: `IssueAssessment`, `Outcome.ASSESSMENT_ONLY`, G0 `blocked`, model-extracted issue type with a code decision, new overridable warnings | draft PR #50, branch `c48-intake` | **PENDING** review by A, B and the human |
| §7 third-party candidate: tabulate #494 | `docs/handoff/48-section7-candidates.md` | **PENDING** run on the demo laptop |

## 2. Files modified (PR #50)
- **Backend:**
  - `backend/github/assess.py` (new);
  - `backend/github/reader.py`, `backend/api/main.py`, `backend/db.py`, `backend/report.py`;
  - `backend/contracts/models.py`.
- **Config and docs:** `config/limits.toml`, `docs/contracts.md`.
- **Web:** `web/src/components.tsx`, `web/src/IssueCheck.tsx`, `web/src/App.tsx`, `web/src/Eval.tsx`, plus the generated `web/src/contracts.{ts,schema.json}`.
- **Fixtures and tests:**
  - `scripts/make_fixtures.py` and `fixtures/runs/assessment_only/`; other fixtures gain only `"assessment": null`;
  - `tests/test_assess.py`, `tests/test_assessment_runs.py` (new); `tests/test_github_reader.py`; `tests/e2e/issue-check.spec.ts`.

## 3. Contract changes (v0.4, PROPOSED)
- One new `Outcome.ASSESSMENT_ONLY`. **No new EndReason and no new status.**
- §1.2 row 0: G0 = blocked → ASSESSMENT_ONLY. G0 = failed keeps meaning "accepted warning".
- `IssueAssessment` (§2.1) on `IssueCheck` and `RunView`, plus the full mapping table.
- `assess_llm_tokens_per_day = 120_000` (§6).
- #41's G3 "import error the issue names" text, carried over word for word.
- Exact diff: `docs/handoff/48-contract-diff.md`.

## 4. Reliability issues
| Reported | Finding | Fix |
|---|---|---|
| Setup `INSTALL_EXIT=1` / 452 s | `pip install -U` stalled on the index (203 s) on Docker's network | Fixed on 10-30 (`-U` dropped, `steps.py:127`); setup 51 s. Not re-run since (no `.env` on C's laptop) |
| Run a863ee86 TRIAGE_ONLY | Investigator cited evidence IDs without `sha256:` | Fixed on 10-30 (`full_ids()`, 5dca09a), 2 regression tests |
| #43 empty evidence on timeout | (a) #46 recovered a redirected log file; (b) **still open until #49:** Python's `TimeoutExpired` carries **bytes**, which were dropped, and a no-output timeout stayed `""` | #49 merged, 4 regression tests |
| `limits.toml` 1_560_000 | Main has `2_500_000` (human-approved for the debug day) and `account_runs_per_day` 20 locally | **PENDING, the human's call.** Not changed |

## 5. Tests run (C's laptop, real runs of the suite)
- `pytest`:
  - main at the start: **352 passed**;
  - after #49: **355 passed**;
  - `c48-intake` now: **395 passed** (about 26 s).
- `tsc --noEmit`: clean.
- Not run here: Playwright e2e (GitHub's anonymous rate limit, no token) and any live LLM or sandbox run (no `.env`).
- Real issues through the local API, before the model step existed:
  - tinycalc #1 → ALREADY_ADDRESSED;
  - facebook/react → UNSUPPORTED;
  - pallets/click #3840 → HUMAN_DECISION (`other_os`);
  - click #3652 → HUMAN_DECISION.

## 6. Capabilities preserved
- **No file changed in:** `backend/worker/`, `backend/sandbox/` (beyond #49), `backend/agents/`, `backend/gates/`, `backend/publisher/`, `backend/api/approval.py`, `backend/llm_gateway.py`.
- **Kept, with tests:**
  - G0's existing warnings and `continue_despite`;
  - `REPO_FORBIDS_AI` as a permanent blocker, also listed in `decision_reasons`;
  - STOPPED handling;
  - a G0-blocked run gets no job, so it can never reach the Fixer, and `decide_outcome` row 0 is a safety net if one ever did.

## 7. Third-party validation evidence
**PENDING.** Run tabulate #494 on the demo laptop; the human approves the diff; draft PR to our fork. Record the run ID, outcome and PR URL here.

## 8. Known limitations
- Issue type depends on one model call. If the model is unavailable, every possible bug becomes HUMAN_DECISION (one checkbox), never READY.
- `needs_info` uses the strict rule (all three of expected, actual and repro missing) until the human picks.
- `other_os` and the "reporter unsure" phrases are regexes, which is why they're warnings and not blocks.
- `test_framework` is the runner we verify with (pytest, which also runs unittest suites). It is not a parsed project setting.
- `DECISION` wording is duplicated in `assess.py` and `components.tsx` (marked as a shortcut).
- The showcase (Vercel) wasn't rebuilt.

## 9. Defer until after the hackathon
- Languages other than Python + pip + pytest (out of scope by decision).
- Model-extracted `environment_requirements`.
- Serving the decision wording from the API instead of duplicating it.
- Per-session limits on the free `/api/issues/check` endpoint. The model cost is capped globally, but not per visitor.
