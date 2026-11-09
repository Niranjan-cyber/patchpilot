# #48 engineering handoff (Phase 5): final, C

Status at 2026-11-07 ~22:45 UTC. Only the demo-laptop items (§7, §4 limits) are open. Nothing here claims a run or a PR that didn't happen.

## 1. Changes implemented
| Change | Where | State |
|---|---|---|
| A timed-out sandbox step's log is never empty: partial bytes decoded, explicit time-limit line, "printed nothing" when there was no output (#43 follow-up) | PR #49 | **merged** (`26d0609`) |
| Intake assessment layer, contracts v0.4: `IssueAssessment`, `Outcome.ASSESSMENT_ONLY`, G0 `blocked`, the model as classifier with a code decision, overridable intake warnings | PR #50 (`c48-intake`) | **ready**, out of draft per the human; the human merges |
| A's 5 confirmed review bugs on #50 (save-only could queue a job; model-only or keyword-only hard blocks; accepted warnings recorded as passed; post-commit save racing the worker) | `cd85eae` in #50 | done, with tests |
| A's second review: copy fallback, saved-assessment wording, finished event in the create transaction, limits comment, fail-closed 422 | branch `c48-followups`, stacked on #50 | PR open against `c48-intake`; **retarget to main after #50 merges** |
| §7 third-party validation | §7 below | 2 VERIFIED_FIX (msoffcrypto #108, mcstatus #1237); 2 PRs published, both closed |

## 2. Files modified
- **Backend:**
  - `backend/github/assess.py` (new);
  - `backend/github/reader.py`, `backend/api/main.py`, `backend/api/approval.py`, `backend/publisher/job.py`;
  - `backend/db.py`, `backend/report.py`, `backend/contracts/models.py`.
- **Config and docs:** `config/limits.toml` (new key and comments only), `docs/contracts.md`.
- **Web:** `web/src/components.tsx`, `IssueCheck.tsx`, `App.tsx`, `Eval.tsx`, plus the generated `contracts.{ts,schema.json}`.
- **Fixtures and tests:**
  - `scripts/make_fixtures.py` and `fixtures/runs/assessment_only/`; other fixtures gain only `"assessment": null`;
  - `tests/test_assess.py`, `tests/test_assessment_runs.py` (new); `tests/test_github_reader.py`; `tests/e2e/issue-check.spec.ts`.
- The `messages.md` and `LEARNING.md` entries are on main.

## 3. Contract changes (v0.4, accepted by the human on 2026-11-07; text in #50)
- `Outcome.ASSESSMENT_ONLY`. **No new EndReason and no new status.**
- §1.2 row 0: G0 = **blocked** → ASSESSMENT_ONLY. G0 = failed still means "accepted warning".
- `IssueAssessment` (§2.1) on `IssueCheck` and `RunView`, with a mapping table covering every decision: G0, job or not, Outcome · EndReason, warning code.
- **Classification:**
  - The model extracts the type.
  - A non-bug hard block needs the model **and** labels/text to agree.
  - A one-sided disagreement, or no model answer, → HUMAN_DECISION (accepted by the human).
- **Unknown is never READY:** this covers the type, Python compatibility, the linked-PR lookup, the test runner and the base commit.
- `POST /api/runs` gains `assessment_only` ("Save the assessment report" never queues a job).
- `assess_llm_tokens_per_day = 120_000`: counted, inside the global budget, and uses no run slot.
- #41's G3 "import error the issue names" text is carried over word for word. #41 can close; that's the human's call.
- Exact diff: `docs/handoff/48-contract-diff.md`.

## 4. Reliability issues
| Reported | Finding | State |
|---|---|---|
| Setup `INSTALL_EXIT=1` / 452 s | `pip install -U` stalled on the index (203 s) | Fixed on 10-30 (`-U` dropped); setup 51 s. **Re-check on the demo laptop** |
| Run a863ee86 TRIAGE_ONLY | Evidence IDs cited without `sha256:` | Fixed on 10-30 (`full_ids()`), 2 regression tests |
| #43 empty evidence on timeout | `TimeoutExpired` bytes dropped; a no-output timeout stayed `""` | **#49 merged**, 4 regression tests |
| `limits.toml` 1_560_000 | Main: `global_llm_tokens_per_day = 2_500_000`; `account_runs_per_day` is 20 on the demo laptop (uncommitted) | **The human's call on the demo laptop.** Not changed by C |

## 5. Tests run (C's laptop, real runs of the suite)
- `pytest`:
  - main at the start: 352 passed;
  - after #49: 355 passed;
  - #50 at `cd85eae`: 403 passed (A's clean worktree: 397 passed, 6 skipped);
  - `c48-followups`: **405 passed**.
- `tsc --noEmit`: clean.
- Not run by C:
  - Playwright e2e (GitHub's anonymous rate limit);
  - any live LLM or sandbox run (no `.env` on C's laptop);
  - third-party code (blocked on C's laptop).

## 6. Capabilities preserved
- **Unchanged:** worker, graph, checkpoints, lease/heartbeat, sandbox (beyond #49), agents, gates G1–G6, SupplyGuard, Revise, Reviewer, fresh-container verify, the approval hashes, the publisher's write path and `llm_gateway`.
- **Kept, with tests:**
  - existing G0 warnings and `continue_despite`;
  - `REPO_FORBIDS_AI` as a permanent blocker, also on ASSESSMENT_ONLY runs and listed in `decision_reasons`;
  - STOPPED handling;
  - a G0-blocked run gets no job, so it can never reach the Fixer, and `decide_outcome` row 0 is a safety net if one ever did.

## 7. Third-party validation (demo laptop, 2026-11-08; details in `LEARNING.md` and `messages.md`)
| Issue | Run | Outcome | Published |
|---|---|---|---|
| tabulate #494 | 8340439b | FIX_NEEDS_ATTENTION (G1 inconclusive for pyproject-only, fixed since in #63; Reviewer flagged scope) | no |
| msoffcrypto-tool #108 | 3e1efde6 rev 2 | **VERIFIED_FIX**, G1 clean (poetry.lock), after one Revise (the hidden variant caught a partial fix) | draft #109, closed at the reporter's request (they had offered to send their own PR) |
| py-mine/mcstatus #1237 | 462e8e6a rev 1 | **VERIFIED_FIX**, after one Revise (the Reviewer caught that `ip_address()` rejects hostnames) | #1238, closed by the maintainer unreviewed: "too much vibe-coding" |
| inflect, toolz, boltons, more-itertools, rich (5 repos) | various | test-only (all had others' PRs); found 3 PatchPilot bugs, fixed in #60–#62 | no |

What these runs changed:
- the publisher asks on the issue first (#68, human decision 2026-11-09) and writes a shorter PR body (#66);
- the repo's own linters now run on the change (#67);
- renamed repos are followed (#65);
- **still open:** Revise can't change the reproduction test (proposal in `messages.md`, needs everyone's agreement).

## 8. Known limitations (deferred by the human, 2026-11-07)
- ASSESSMENT_ONLY rows have no per-owner cap, and limit checks run after `_check()`.
- The assessor cap isn't atomic. Timed-out calls finish in the background (still counted), and late results aren't cached.
- `tests/e2e/issue-check.spec.ts` ticks consent if it's present.
- `needs_info` keeps the strict rule (all of expected, actual and repro missing).
- The reviewer's open question: should an accepted `base_unknown`, or `unclear_type` from `model_unavailable`, record G0 as "inconclusive" instead of "failed"?
- Body regexes ("docs", "how do I") turn some docs-citing bug reports into `unclear_type`. That's the safe direction, but noisy.
- If the model is unavailable, every runnable issue becomes HUMAN_DECISION (one checkbox).
- The decision wording is duplicated in `assess.py` and `components.tsx`.
- The showcase (Vercel) wasn't rebuilt.

## 9. Defer until after the hackathon
- Languages other than Python + pip + pytest.
- Model-extracted `environment_requirements`.
- Serving the decision wording from the API.
- A per-visitor cap on `/api/issues/check`.
- A web unit-test runner (the copy fallback is type-checked only).
