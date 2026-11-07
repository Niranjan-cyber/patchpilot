# #48 §3.4: DECISION request: handling decisions → Outcome/EndReason (contracts v0.4 proposal)

Author: C. Status: **proposal, not applied.** `docs/contracts.md` and `backend/contracts/` are untouched until A, B and C agree in messages.md (COORDINATION rule 4).

## TL;DR
- **One new `Outcome`: `ASSESSMENT_ONLY`.** **No new `EndReason`** (an assessment ends `completed`). No new run status.
- `handling_decision` is a **field of the assessment**, not a status. Four of the six decisions need no outcome at all, because they already map onto G0's existing **overridable warning** mechanism (`continue_despite`).
- The decision is made by **code** (`decide_handling()`), from labels, text signals, repo checks and the existing G0 checks. A model may fill in descriptive fields only; it can never turn a decision into `READY` on its own.
- Folds in the G0 half of open PR #41 (`unclear_bug` → becomes `unclear_type`), so G0 isn't edited twice.

## 1. Mapping

| handling_decision | When (first match, code only) | Run? | Outcome / EndReason | Overridable? |
|---|---|---|---|---|
| `UNSUPPORTED` | G0 `python` = failed, or `tests_found` = failed (today's 422 `UNSUPPORTED_REPO`) | finished run, **no job** | `ASSESSMENT_ONLY` / `completed`, G0 = `failed` (`unsupported:not_python` \| `unsupported:no_tests`) | no |
| `ASSESSMENT_ONLY` | `issue_type` ∈ feature, enhancement, docs, refactor, maintenance, build_ci, test_failure, question, other | finished run, **no job** | `ASSESSMENT_ONLY` / `completed`, G0 = `failed` (`not_a_bug:<type>`) | no |
| `HUMAN_DECISION` | `issue_type` = unknown, or label and text disagree (e.g. `bug` label + "feature request" text) | only with `unclear_type` in `continue_despite` | normal §1.2 | **yes**, warning `unclear_type` (replaces #41's `unclear_bug`) |
| `NEEDS_INFORMATION` | bug/regression, but **no** expected behaviour **and** no error/traceback/repro snippet in the issue | only with `needs_info` in `continue_despite` | normal §1.2 | **yes**, warning `needs_info`; S-01 shows what's missing + a draft comment (never auto-posted) |
| `ALREADY_ADDRESSED` | linked open PR (today's `linked_pr`) | only with `linked_pr` accepted | normal §1.2 | **yes**, unchanged |
| `READY` | bug/regression, compatible, required fields present | yes | normal §1.2 | — |

- `closed`, `assigned`, `lookup_failed` keep today's behaviour (warnings). A closed issue reports `ALREADY_ADDRESSED` as its label, same override.
- `REPO_FORBIDS_AI` stays a **permanent publish blocker** (unchanged, not overridable).
- Precedence for the label when several apply: UNSUPPORTED > ASSESSMENT_ONLY > HUMAN_DECISION > NEEDS_INFORMATION > ALREADY_ADDRESSED > READY. `decision_reasons` lists **every** code that fired.
- **Unknown is never READY:** any required field (`issue_type`, `compatibility_status`) that is `unknown` makes the decision HUMAN_DECISION at best.

### Why `ASSESSMENT_ONLY` runs instead of today's 422
The brief needs a persisted, shareable assessment report (My runs, report.md) and an honest end state instead of an error toast. A finished run with no job does that with no new machinery. These runs **don't count** toward the daily run limits (nothing executes; the check endpoint is already free).

**Alternative (zero contract change):** keep "no run is created" and only show the assessment on S-01 with a download. Cheaper, but nothing is persisted and the brief asks for the assessment to live with the run. I recommend the new outcome.

## 2. Contract diff (text)

§1 Enums
```diff
 class Outcome(str, Enum):
     VERIFIED_FIX = "VERIFIED_FIX"; FIX_NEEDS_ATTENTION = "FIX_NEEDS_ATTENTION"
     TRIAGE_ONLY = "TRIAGE_ONLY"; CANNOT_REPRODUCE = "CANNOT_REPRODUCE"
     ENV_FAILED = "ENV_FAILED"; BLOCKED = "BLOCKED"; STOPPED = "STOPPED"; SYSTEM_ERROR = "SYSTEM_ERROR"
+    ASSESSMENT_ONLY = "ASSESSMENT_ONLY"   # G0 failed: assessed, nothing executed (§1.1)
```

§1.1 G0 row
```diff
-| **G0 Eligibility** | … | … | any of: closed, assigned, linked open PR → run only if the user sent the code in `continue_despite` (recorded) | a lookup failed → run only with `continue_despite` | — | PREFLIGHT. Private / non-Python / no tests → **no run is created** (API error `UNSUPPORTED_REPO`). …
+| **G0 Eligibility** | IssueSpec, repo record, timeline, file listing, labels | issue open · repo public · Python project · tests found · unassigned · no linked open PR · issue_type ∈ {bug, regression} · required info present | warnings closed, assigned, linked_pr, unclear_type, needs_info → run only with the code in `continue_despite` (recorded) | lookup failed → run only with `continue_despite` | non-Python / no tests / not a bug → **finished run, no job**, outcome `ASSESSMENT_ONLY` | PREFLIGHT. Private repo or PR link → API error, no run. `handling_decision` is decided by code (§2 `IssueAssessment`). AI policy "forbidden" → `REPO_FORBIDS_AI` blocker (unchanged) |
```

§1.2 outcome rule: new row 0, before row 1
```diff
+| 0 | G0 = failed | `ASSESSMENT_ONLY` |
```
Readiness: `ASSESSMENT_ONLY → "Assessment only: no fix attempted"`. `status_after_analysis` → FINISHED (it's not publishable; `OUTCOME_NOT_VERIFIED` added as for every non-fix outcome).

§1.3: `(create) | G0 failed | FINISHED (ASSESSMENT_ONLY, completed)`. No job row is written.

§2 Run state
```diff
+class IssueAssessment(BaseModel):
+    schema_version: Literal[1] = 1
+    issue_type: Literal["bug","regression","feature","enhancement","docs","refactor","maintenance",
+                        "build_ci","test_failure","question","other","unknown"]
+    issue_type_source: Literal["label","text","model","none"]   # provenance
+    issue_status: Literal["open","closed"]
+    problem_summary: str | None = None            # model-extracted, may be null; never used to decide
+    acceptance_conditions: list[str] = []
+    missing_information: list[str] = []           # codes: no_expected, no_actual, no_repro, no_version
+    reproduction_information: str | None = None
+    existing_resolution: list[int] | None = None  # linked open PR numbers; None = lookup failed
+    build_system: Literal["pip","setuptools","poetry","uv","hatch","pdm","unknown"] = "unknown"
+    test_framework: Literal["pytest","unittest","unknown"] = "unknown"
+    environment_requirements: list[str] = []      # e.g. "python>=3.10" from pyproject, if readable
+    compatibility_status: Literal["supported","unsupported","unknown"]
+    handling_decision: Literal["READY","NEEDS_INFORMATION","UNSUPPORTED","ALREADY_ADDRESSED",
+                               "HUMAN_DECISION","ASSESSMENT_ONLY"]
+    decision_reasons: list[str]                   # every rule that fired, e.g. ["not_a_bug:feature"]
+    draft_comment: str | None = None              # NEEDS_INFORMATION only; never posted by PatchPilot
+
 class RunView(BaseModel):
     …
+    assessment: IssueAssessment | None = None     # None for runs created before v0.4
```
Not duplicated on purpose (already in the contract): `issue_url`/`repository`/`issue_number`/`expected`/`actual` → `IssueSpec`; `language` → `IssueCheck.language`; `contribution_policy` → `RunView.policy` (`RepoPolicy`); `base_sha` → `RunView.base_sha`.

§4 API
```diff
-| POST | `/api/issues/check` | `{url}` → `IssueCheck` (…). No run is created |
+| POST | `/api/issues/check` | `{url}` → `IssueCheck` + `assessment` (…). No run is created |
-| POST | `/api/runs` | `{issue_url, continue_despite}` → `RunView`; … |
+| POST | `/api/runs` | `{issue_url, continue_despite}` → `RunView`; UNSUPPORTED / ASSESSMENT_ONLY → 201 with a FINISHED run (no job, not counted toward limits) instead of 422 `UNSUPPORTED_REPO` |
```

## 3. Where the model fits (§3.3)
- Classification is **code first**: labels (`bug`, `regression`, `enhancement`, `documentation`, …) → text signals (traceback, `Error:`, expected/actual, "regression", "used to work"; and the `NOT_RUNNABLE` regex already in `backend/github/explore.py:11`).
- **Open question for A/B:** an optional single extraction call through `llm_gateway` at check time (≤3k tokens, cached per issue `updated_at`, charged to the global budget) to fill `problem_summary` / `acceptance_conditions` / `missing_information` and a *suggested* `issue_type`. A model-only "bug" with no code-detected bug signal → `HUMAN_DECISION`, never READY. If you'd rather keep the check endpoint LLM-free for the demo, everything above still works with model fields left null.

## 4. Affected surfaces
- `backend/contracts/models.py`: `Outcome`, `READINESS`, `decide_outcome` row 0, `IssueAssessment`, `RunView.assessment`.
- `docs/contracts.md` §1, §1.1, §1.2, §1.3, §2, §4 (+ version bump).
- `web/src/contracts.ts`: `Outcome` union + `IssueAssessment` type.
- `backend/github/reader.py` + new pure `backend/github/assess.py` (`classify()`, `decide_handling()`); `backend/api/main.py` `create_run` (finished run, no job) and `/api/issues/check`; `backend/db.py` `create_run(..., job=False)` and `owner_counts` excluding ASSESSMENT_ONLY.
- Worker / graph: **no change** (no job is ever written for G0-failed runs; `decide_outcome` row 0 is also a safety net if one is).
- `backend/report.py`: an assessment-only report section.
- UI: `IssueCheck.tsx` (assessment card, needs_info + unclear_type warnings, draft comment with Copy), Run page / `ProofPanel` / `VerdictNote` / `ReadinessBadge` for ASSESSMENT_ONLY.
- `fixtures/runs/assessment_only.json` (+ `scripts/make_fixtures.py`), `scripts/build_showcase.py` picks it up.
- Tests: `tests/test_outcome_rules.py` (row 0), new `tests/test_assess.py` (the 10 intake cases in brief §8), `tests/test_api*` (201 instead of 422), fixture contract tests.

## 5. Asks
1. **A, B, C:** agree / object to the new `ASSESSMENT_ONLY` outcome (vs. the zero-change alternative).
2. **A, B:** model extraction at check time: yes (capped) or code-only for now?
3. **A:** close #41 in favour of this, or land #41 first and I rebase?
