## Phase 0 assessment (C session, read-only, no product files changed)

Checked against `main` at `1442b07` (2026-11-08). Full backend suite: **352 passed** (run locally just now).

### 1. Already implemented
- Full pipeline: G0 intake (`backend/github/reader.py`) → LangGraph worker with SqliteSaver checkpoints, lease + heartbeat → PREFLIGHT/G1 SupplyGuard → SETUP/G2 → BASELINE → REPRODUCE/G3 → DIAGNOSE → FIX/G4 (+ Revise) → VERIFY/G5 (2/2 fresh containers, baseline regressions, hidden variant) → REVIEW/G6 → `decide_outcome()`.
- Hash-bound approval (`canonical_diff`/`diff_hash`/`evidence_hash`, `stale_checks` fail closed), publisher as sole write-token holder, quota pause + provider chain, user stop, guided pauses, Explore, Ask-why, bisect/variant extras, static showcase.

### 2. Working (verified)
- Tests: 352 pass. Real runs from 10-30: tinycalc #2 run `2ef051bc` VERIFIED_FIX + published; tinycalc PRs #4–#6 exist.
- G0 already has: closed / assigned / linked_pr / lookup_failed as **overridable** `continue_despite` warnings; `REPO_FORBIDS_AI` as a **permanent** publish blocker; PR-link and private-repo rejections; `base_sha` pinned at intake.

### 3. Broken or incomplete vs. the #48 requirements
- **Non-Python / no-tests repos are a hard 422** (`backend/api/main.py:126`), no run, no persisted assessment. → needs `UNSUPPORTED` assessment.
- **No issue-type classification at all.** Every issue that passes G0 goes straight into the fix pipeline, including feature requests and docs issues. The only "not a bug" heuristic is in Explore (`backend/github/explore.py:11`, `NOT_RUNNABLE` regex), not in intake. → needs `ASSESSMENT_ONLY` / `HUMAN_DECISION`.
- **No missing-information check** beyond `expected_actual()` regex; no draft-comment flow. → needs `NEEDS_INFORMATION`.
- No `IssueAssessment` structure; G0 results live in `IssueSpec.checks` + `gates["G0"]` only.
- Contracts PR #41 (v0.3: G0 `unclear_bug` warning) is still open with 1/3 approvals. It overlaps §3.3, so I propose folding it into the new contract change rather than landing two G0 edits.

### 4. Changed since the 10-30 handoff (verify, don't redo)
- #43 empty timeout log: **fixed** (#46, `docker.run(log_path=…)`, `backend/sandbox/docker.py:69`, also wired into baseline + G5). Test: `tests/test_sandbox_docker.py`.
- a863ee86 TRIAGE_ONLY: **fixed** (5dca09a, `full_ids()` at `backend/gates/diff_policy.py:108`, 2 regression tests). Cause: Investigator cited evidence IDs without `sha256:`; the stop was correct under the old check, wrong in spirit.
- Setup stall / `INSTALL_EXIT=1` slowness: **fixed** (`-U` dropped, `backend/sandbox/steps.py:127`; setup 4–8 min → 51 s). I have not re-run a live install since; that needs the demo laptop (this machine has Docker but no `.env`/LLM keys).
- `config/limits.toml`: `global_llm_tokens_per_day = 2_500_000` (comment says back to `1_560_000` for the demo). **Not changing it without the human.**

### 5. Changes that are genuinely needed
1. Intake assessment layer (§3/§4): deterministic `handling_decision` in code, persisted on the run. **Needs a contract change → proposal in the next comment.**
2. UI: S-01 shows the assessment report + draft comment for NEEDS_INFORMATION; Run page renders ASSESSMENT_ONLY runs.
3. Phase 1 is mostly done. **One gap left in #43:** when a step times out and neither the host capture nor the log file has any output, `docker.run` still returns `""` (`backend/sandbox/docker.py:68-73`; `tests/test_sandbox_docker.py:26` even pins "stays empty"), so an empty artifact can still be saved as evidence. Fix: on timeout always append an explicit `[stopped: hit the time limit after N s; the tool printed nothing]` line. Small PR, A to review (sandbox path). Then a live re-run on the demo laptop.
4. Third-party validation run (§7): needs the demo laptop + the human's approval of the diff.

**Not needed:** new agents, new DB, new status system, language expansion, anything in G1–G6.
