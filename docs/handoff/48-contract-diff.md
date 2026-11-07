# #48 contracts v0.4: exact diff for review (A, B, C, the human)

Branch `c48-intake` vs `main`. Only these files define the contract; the mapping table is in `docs/contracts.md` §2.1.

```diff
diff --git a/backend/contracts/models.py b/backend/contracts/models.py
index fd8b4ae..ce73526 100644
--- a/backend/contracts/models.py
+++ b/backend/contracts/models.py
@@ -31,6 +31,7 @@ class Outcome(str, Enum):
     VERIFIED_FIX = "VERIFIED_FIX"; FIX_NEEDS_ATTENTION = "FIX_NEEDS_ATTENTION"
     TRIAGE_ONLY = "TRIAGE_ONLY"; CANNOT_REPRODUCE = "CANNOT_REPRODUCE"
     ENV_FAILED = "ENV_FAILED"; BLOCKED = "BLOCKED"; STOPPED = "STOPPED"; SYSTEM_ERROR = "SYSTEM_ERROR"
+    ASSESSMENT_ONLY = "ASSESSMENT_ONLY"   # G0 blocked: assessed, nothing executed (contracts v0.4, §1.1)
 
 
 class EndReason(str, Enum):
@@ -56,6 +57,7 @@ READINESS = {
     Outcome.FIX_NEEDS_ATTENTION: "Needs attention",
     Outcome.TRIAGE_ONLY: "Unable to verify a fix",
     Outcome.STOPPED: "Stopped, report so far",
+    Outcome.ASSESSMENT_ONLY: "Assessment only: no fix attempted",
 }
 
 
@@ -65,6 +67,30 @@ class Owner(BaseModel):
     account_id: int | None = None
 
 
+class IssueAssessment(BaseModel):
+    """#48 intake assessment (contracts v0.4 §2). handling_decision is decided by code (backend/github/assess.py), never a model;
+    it is a field, not a run status. Fields already in the contract (issue URL/number, expected/actual, language, policy,
+    base_sha) live on IssueSpec / IssueCheck / RunView and are not repeated here."""
+    schema_version: Literal[1] = 1
+    issue_type: Literal["bug", "regression", "feature", "enhancement", "docs", "refactor", "maintenance",
+                        "build_ci", "test_failure", "question", "other", "unknown"]
+    issue_type_source: Literal["label", "text", "model", "none"]
+    issue_status: Literal["open", "closed"]
+    problem_summary: str | None = None
+    acceptance_conditions: list[str] = []
+    missing_information: list[str] = []            # codes: no_expected, no_actual, no_repro
+    reproduction_information: str | None = None
+    existing_resolution: list[int] | None = None   # linked open PR numbers; None = lookup failed
+    build_system: Literal["pip", "setuptools", "poetry", "uv", "hatch", "pdm", "unknown"] = "unknown"
+    test_framework: Literal["pytest", "unittest", "unknown"] = "unknown"
+    environment_requirements: list[str] = []
+    compatibility_status: Literal["supported", "unsupported", "unknown"]
+    handling_decision: Literal["READY", "NEEDS_INFORMATION", "UNSUPPORTED", "ALREADY_ADDRESSED",
+                               "HUMAN_DECISION", "ASSESSMENT_ONLY"]
+    decision_reasons: list[str] = []
+    draft_comment: str | None = None               # NEEDS_INFORMATION only; PatchPilot never posts it
+
+
 class IssueSpec(BaseModel):
     html_url: str
     repo: str                      # owner/name
@@ -226,6 +252,7 @@ class RunView(BaseModel):
     readiness: str | None = None
     issue: IssueSpec
     base_sha: str
+    assessment: IssueAssessment | None = None   # None for runs created before v0.4
     policy: RepoPolicy = RepoPolicy()
     env: EnvProfile | None = None
     baseline: TestRun | None = None
@@ -290,6 +317,8 @@ def decide_outcome(gates: dict[str, CheckStatus], end_reason: EndReason, *, revi
                    readiness_capped: bool = False, diagnosis_valid: bool = False,
                    stopped_during_diagnose: bool = False) -> Outcome:
     g = lambda k: gates.get(k, CheckStatus.NOT_RUN)
+    if g("G0") == CheckStatus.BLOCKED:   # row 0 (v0.4): assessed only, nothing ran. (G0 "failed" = a warning the user accepted)
+        return Outcome.ASSESSMENT_ONLY
     if g("G1") == CheckStatus.BLOCKED:
         return Outcome.BLOCKED
     if g("G2") == CheckStatus.FAILED:
diff --git a/config/limits.toml b/config/limits.toml
index 065736f..dcc363c 100644
--- a/config/limits.toml
+++ b/config/limits.toml
@@ -6,6 +6,10 @@ global_concurrent_runs = 1    # 2 on a VM
 global_llm_tokens_per_day = 2_500_000   # human-approved 2026-10-30 for the debug day (11 runs used 1.56M, 30% on the retired local 7B); measured 260k/run. Back to 1_560_000 (×6 runs) for the demo. Never 0-as-unlimited.
 budget_measured_tokens_per_run = 260_000
 budget_measured_on = "2026-10-30"
+# #48 intake assessment: one capped model call per issue version (cached), role "assessor". Its own daily cap, separate
+# from the execution quotas above; still counted in global_llm_tokens_per_day. ~3k tokens/call -> ~40 new issues a day.
+# 0 = model extraction off (every issue is then at best HUMAN_DECISION or a keyword-clear ASSESSMENT_ONLY).
+assess_llm_tokens_per_day = 120_000
 run_llm_tokens = 400_000   # run 10 hit 300k at the start of FIX (260k measured to reach FIX in run 5; fix + review still to come)
 run_active_seconds = 1500
 setup_seconds = 480
diff --git a/docs/contracts.md b/docs/contracts.md
index 5a93c0a..54de799 100644
--- a/docs/contracts.md
+++ b/docs/contracts.md
@@ -1,4 +1,4 @@
-# PatchPilot: Shared Contracts (v0.2 draft)
+# PatchPilot: Shared Contracts (v0.4 PROPOSED, #48; not agreed yet)
 
 This file is the boundary between the four build lanes: **(1) sandbox + setup + baseline, (2) agent roles + gates, (3) GitHub reader/publisher + auth, (4) React UI + event polling.** Lanes build against these types and fixtures, not against each other's code.
 
@@ -31,6 +31,7 @@ class Outcome(str, Enum):              # set exactly once per revision, when tha
     ENV_FAILED = "ENV_FAILED"; BLOCKED = "BLOCKED"
     STOPPED = "STOPPED"                # ended (user or limit) before any outcome-defining evidence
     SYSTEM_ERROR = "SYSTEM_ERROR"      # our infrastructure failed before any outcome-defining evidence
+    ASSESSMENT_ONLY = "ASSESSMENT_ONLY"  # v0.4: G0 blocked (unsupported repo or not a bug); assessed, nothing executed
 
 class EndReason(str, Enum):            # why analysis stopped
     COMPLETED = "completed"; RETRIES_EXHAUSTED = "retries_exhausted"
@@ -53,20 +54,23 @@ Each gate is computed by code from recorded artifacts. Its `gate.result` event c
 
 | Gate | Input evidence | `passed` | `failed` | `inconclusive` | `blocked` | Next |
 |---|---|---|---|---|---|---|
-| **G0 Eligibility** | IssueSpec, repo record, timeline (cross-referenced PRs), file listing | issue open · repo public · Python project · tests found · unassigned · no linked open PR | any of: closed, assigned, linked open PR → run only if the user sent the code in `continue_despite` (recorded) | a lookup failed → run only with `continue_despite` | — | PREFLIGHT. Private / non-Python / no tests → **no run is created** (API error `UNSUPPORTED_REPO`). AI policy "forbidden" isn't a gate failure; it adds the `REPO_FORBIDS_AI` blocker |
+| **G0 Eligibility** | IssueSpec, repo record, timeline (cross-referenced PRs), file listing, labels | issue open · repo public · Python project · tests found · unassigned · no linked open PR · `issue_type` is bug or regression · enough information | any of: closed, assigned, linked open PR, `unclear_type`, `needs_info`, `other_os` → run only if the user sent the code in `continue_despite` (recorded; G0 = failed) | a lookup failed → run only with `continue_despite` | non-Python, no tests, or not a bug → G0 = **blocked**: a FINISHED run with **no job**, outcome `ASSESSMENT_ONLY` (v0.4; was API error `UNSUPPORTED_REPO`) | PREFLIGHT. Private repo or a PR link → API error, no run. `RunView.assessment.handling_decision` is decided by code (§2), never a model. AI policy "forbidden" isn't a gate failure; it adds the `REPO_FORBIDS_AI` blocker |
 | **G1 Pre-flight** | dependency files at `base_sha`, SupplyGuard report | no confirmed malicious or typosquatted package (CVEs listed as findings) | — | SupplyGuard error, lookup failure or unsupported format → continue, add `DEPS_INCONCLUSIVE` | confirmed malicious / typosquat → outcome `BLOCKED`, terminal, **no override** | SETUP |
 | **G2 Setup** | install log, `pytest --collect-only` output | install exit 0 within `setup_seconds` **and** collection exit 0 with ≥ 1 test | still failing after one AI-assisted retry (install commands only) → `ENV_FAILED` | — (infra failures resume, §7) | — | BASELINE (records pass/fail/flaky sets; not a gate; a partial baseline caps readiness) |
-| **G3 Reproduction** | test diff, 2 runs on the original code | diff touches test files only · the new test fails in **both** runs with an assertion error or the issue's error, not an import, syntax or collection error | otherwise → Test designer retry (≤ 2), then `CANNOT_REPRODUCE` | 1 of 2 runs fails (flaky) → counts as a failed attempt | — | DIAGNOSE: every cited evidence ID must exist; invalid → one Investigator retry; still invalid → analysis ends (`retries_exhausted`) as `TRIAGE_ONLY` with "diagnosis unavailable" |
+| **G3 Reproduction** | test diff, 2 runs on the original code | diff touches test files only · the new test fails in **both** runs with an assertion error, the issue's error, or an **import error the issue itself names** (see below); never a syntax error, and never a collection error inside the generated test file | otherwise → Test designer retry (≤ 2), then `CANNOT_REPRODUCE` | 1 of 2 runs fails (flaky) → counts as a failed attempt | — | DIAGNOSE: every cited evidence ID must exist; invalid → one Investigator retry; still invalid → analysis ends (`retries_exhausted`) as `TRIAGE_ONLY` with "diagnosis unavailable" |
 | **G4 Diff policy** | fix diff | non-test source files only · ≤ 5 files and ≤ 200 changed lines · no dependency-file changes · no `.github/` · no test deleted, skipped or edited | → back to the Fixer with the reason (counts as a Fixer attempt) | — | — | VERIFY |
 | **G5 Verification** | fresh-container runs on original + test diff + fix diff | the new test passes in **both** runs **and** every test in the baseline pass set passes | → Fixer retry with logs (≤ 3), then one re-diagnosis, then `TRIAGE_ONLY` | the new test passes 1 of 2, or a baseline test flips → counts as a failed attempt | — | REVIEW (the Reviewer can only lower readiness) |
 | **G6 Report integrity** | report, `gates`, evidence manifest | every status in the report equals the recorded status · every claim cites an existing evidence ID | the Explainer regenerates (≤ 2); then the report is rendered from the deterministic template without AI narrative. **Never changes the outcome** | — | — | outcome + status (§1.2) |
 
+**"an import error the issue itself names" (G3).** The error **type** (`ImportError` / `ModuleNotFoundError`) **and** the missing name must both appear in the IssueSpec as extracted by code from `issue.actual` / the summary. It is **never** matched against the Test designer's own `expected_failure`: a model must not be able to whitelist its own broken import. A `SyntaxError`, and a collection error whose traceback points inside the generated test file rather than at the import of the library under test, stay hard disqualifiers. *(Carried over word for word from #41 so closing #41 loses nothing; B owns the implementation in `backend/gates/reproduction.py`.)*
+
 ## 1.2 Outcome rule (deterministic, by code, per revision)
 
 When a revision's analysis ends, for whatever `EndReason`, take the **first** row that matches:
 
 | # | Condition | Outcome |
 |---|---|---|
+| 0 | G0 = blocked (v0.4: assessed only; G0 = failed means an accepted warning and does **not** match) | `ASSESSMENT_ONLY` |
 | 1 | G1 = blocked | `BLOCKED` |
 | 2 | G2 = failed | `ENV_FAILED` |
 | 3 | G5 = passed, `end_reason = completed`, Reviewer raised no concerns, no readiness cap | `VERIFIED_FIX` |
@@ -80,12 +84,13 @@ When a revision's analysis ends, for whatever `EndReason`, take the **first** ro
 - **`end_reason = user_stopped` always adds `RUN_STOPPED`**, so a stopped run is never publishable, even if G5 had passed (row 4 → FIX_NEEDS_ATTENTION, report-only).
 - `outcome`, `end_reason` and `readiness` describe the **latest revision**. Earlier revisions are kept in `revisions[]` (§2).
 
-**Readiness** (UI badge): VERIFIED_FIX → "Ready for human review" · FIX_NEEDS_ATTENTION → "Needs attention" · TRIAGE_ONLY → "Unable to verify a fix" · STOPPED → "Stopped, report so far" · the rest → "Unable to verify". Readiness is capped at FIX_NEEDS_ATTENTION when `supplyguard.status == INCONCLUSIVE`, the baseline is partial, or the Reviewer lowers it.
+**Readiness** (UI badge): VERIFIED_FIX → "Ready for human review" · FIX_NEEDS_ATTENTION → "Needs attention" · TRIAGE_ONLY → "Unable to verify a fix" · STOPPED → "Stopped, report so far" · ASSESSMENT_ONLY → "Assessment only: no fix attempted" · the rest → "Unable to verify". Readiness is capped at FIX_NEEDS_ATTENTION when `supplyguard.status == INCONCLUSIVE`, the baseline is partial, or the Reviewer lowers it.
 
 ## 1.3 Run status transitions
 
 | From | Event | To |
 |---|---|---|
+| (create) | G0 blocked (v0.4) | FINISHED (`ASSESSMENT_ONLY`, `completed`), no job; not counted toward run limits |
 | QUEUED | worker leases the job | RUNNING |
 | QUEUED | user stop | FINISHED (`STOPPED`, `user_stopped`) |
 | RUNNING / REVISING | provider quota or global budget hit; guided pause | PAUSED |
@@ -122,6 +127,7 @@ class RunState(BaseModel):
     owner: Owner                      # session_id_hash | account_id (never exposed)
     issue: IssueSpec                  # incl. html_url, number, repo, eligibility checks
     base_sha: str
+    assessment: IssueAssessment | None  # v0.4 (#48): intake assessment; None for older runs
     policy: RepoPolicy                # ai_policy: allowed|forbidden|unknown, prs_restricted, source file ids
     env: EnvProfile | None
     baseline: TestRun | None          # pass_set, fail_set, flaky_set, evidence_ids
@@ -146,6 +152,57 @@ class RunState(BaseModel):
 
 Large content (logs, diffs, test output) is stored in the artifact store, keyed by **`sha256:<hex>`** of the bytes. Those keys are the evidence IDs. State holds only IDs.
 
+### 2.1 IssueAssessment (v0.4, #48)
+
+`handling_decision` is a **field**, not a run status. **The model extracts, code decides** (DECISION 2026-11-07):
+- **Extraction (the classifier):** one bounded model call per issue version, `assess.extract()` through `llm_gateway`, role `assessor`. It returns `issue_type` + `problem_summary`, `acceptance_conditions` and `reproduction_information` as validated JSON.
+  - Bounds: ≤ 4,000 chars of the issue, ≤ 1,800 output tokens (reasoning models use part of it), a 20 s wall-clock wait, cached per issue `updated_at`.
+  - Counted: inside `global_llm_tokens_per_day`, plus its own cap `assess_llm_tokens_per_day` (§6). It never uses an execution slot or the per-run budget.
+  - Skipped for UNSUPPORTED repos, since nothing would run.
+- **Cross-check:** labels and text (keywords). If they disagree with the model on bug vs not-bug, or the reporter asks whether it's a bug at all ("is this expected?", "not sure if intentional"; from #41), the type is `unknown`.
+- **A non-bug hard block needs agreement:** G0 blocked (ASSESSMENT_ONLY) only when the model **and** labels/text both say non-bug. Neither one alone may set a gate (AGENTS.md hard rule; A's review of #50). One-sided → `unknown` → HUMAN_DECISION (overridable).
+- **Model unavailable** (budget, quota, timeout, invalid JSON) → `model_unavailable` → HUMAN_DECISION at best: never READY, and never a keyword-only hard block.
+- **For the human (changes the 19:01 DECISION's wording):** "non-bugs never reach the Fixer" now holds when the model and labels/text agree it's a non-bug. A **one-sided** non-bug can reach it, but only after the user ticks the consent box, and the report caveat goes on every outcome.
+- **Decision:** `decide_handling()` in code, first match wins. Unknown, invalid or ambiguous required fields are never `READY`: issue type, Python compatibility, linked-PR lookup, test runner, base commit.
+
+```python
+class IssueAssessment(BaseModel):
+    schema_version: Literal[1] = 1
+    issue_type: Literal["bug","regression","feature","enhancement","docs","refactor","maintenance",
+                        "build_ci","test_failure","question","other","unknown"]
+    issue_type_source: Literal["label","text","model","none"]     # provenance
+    issue_status: Literal["open","closed"]
+    problem_summary: str | None; acceptance_conditions: list[str]; reproduction_information: str | None
+    missing_information: list[str]        # no_expected, no_actual, no_repro
+    existing_resolution: list[int] | None # linked open PR numbers; None = lookup failed
+    build_system: Literal["pip","setuptools","poetry","uv","hatch","pdm","unknown"]
+    test_framework: Literal["pytest","unittest","unknown"]
+    environment_requirements: list[str]
+    compatibility_status: Literal["supported","unsupported","unknown"]
+    handling_decision: Literal["READY","NEEDS_INFORMATION","UNSUPPORTED","ALREADY_ADDRESSED","HUMAN_DECISION","ASSESSMENT_ONLY"]
+    decision_reasons: list[str]           # every rule that fired
+    draft_comment: str | None             # NEEDS_INFORMATION only; PatchPilot never posts it
+```
+
+| handling_decision | When (first match; `decision_reasons` code) | G0 | Run / job | Outcome · EndReason | Warning code (`continue_despite`) |
+|---|---|---|---|---|---|
+| `UNSUPPORTED` | not Python (`unsupported:not_python`) or no tests (`unsupported:no_tests`) | blocked | FINISHED run, **no job** | `ASSESSMENT_ONLY` · `completed` | none (not overridable) |
+| `ASSESSMENT_ONLY` | the model **and** labels/text agree it's not a bug (`not_a_bug:<type>`); or the user clicked "Save the assessment report" (`assessment_only: true`, G0 reason `saved_assessment_only`) | blocked | FINISHED run, **no job** | `ASSESSMENT_ONLY` · `completed` | none (not overridable) |
+| `HUMAN_DECISION` | `unclear_type`, `model_unavailable` | failed if accepted | runs only after consent | by §1.2 as usual | `unclear_type` |
+| | `compatibility_unknown`, `linked_pr_unknown`, `test_framework_unknown` | inconclusive / failed | runs only after consent | by §1.2 | `lookup_failed` (existing) |
+| | `base_sha_unknown` | failed if accepted | runs only after consent | by §1.2 | `base_unknown` |
+| | `other_os` (Windows/macOS-only; our sandbox is Linux) | failed if accepted | runs only after consent | by §1.2 | `other_os` |
+| `NEEDS_INFORMATION` | bug with no expected, no actual and no repro (`needs_info`) | failed if accepted | runs only after consent | by §1.2 | `needs_info` + a draft comment (never posted) |
+| `ALREADY_ADDRESSED` | linked open PR (`linked_pr`) or closed (`closed`); lookups can be wrong | failed if accepted | runs only after consent | by §1.2 | `linked_pr` / `closed` (existing, unchanged) |
+| `READY` | none of the above | passed | runs | by §1.2 | — |
+
+- `repo_forbids_ai` is listed in `decision_reasons` to explain the block. It doesn't change the decision; `REPO_FORBIDS_AI` stays a permanent publish blocker.
+- **Report caveat (from #41's `unclear_bug`):** a run that went ahead after `unclear_type`, `model_unavailable` or `needs_info` carries this fixed line on **every** outcome. It is rendered by code, never by the Explainer:
+  > Verified here means the fix passes the test PatchPilot wrote from the issue. The issue doesn't say what the right behaviour is, so check it matches what the maintainers want.
+- **G0 `blocked` vs `failed`:** `blocked` = nothing may run (row 0 of §1.2). `failed` = the user accepted a warning and the run went ahead, so it is never ASSESSMENT_ONLY.
+
+Not repeated here because they already exist: issue URL/repo/number/expected/actual (`IssueSpec`), language (`IssueCheck`), contribution policy (`RunView.policy`), base commit (`RunView.base_sha`).
+
 ## 3. Event stream (polling first, SSE optional)
 
 **Primary:** `GET /api/runs/{run_id}/events?after=<seq>` → `{"events": [<envelope>…], "next_after": <seq>}`, polled every 2 s while the run isn't terminal (every 10 s while paused). This works through any tunnel; Cloudflare Quick Tunnels don't support SSE. **Optional:** the same path with `Accept: text/event-stream`, using the format below. Every event is appended to the `events` table *before* it's returned, so both are views of the log.
@@ -180,8 +237,8 @@ data: {"v":1,"run_id":"…","seq":42,"ts":"2026-11-11T10:42:07Z","type":"step.fi
 
 | Method | Path | Notes |
 |---|---|---|
-| POST | `/api/issues/check` | `{url}` → `IssueCheck` (summary, eligibility, policy, publish preview). No run is created |
-| POST | `/api/runs` | `{issue_url, continue_despite: [warning codes]}` → `RunView`; enforces limits; creates the session cookie if missing |
+| POST | `/api/issues/check` | `{url}` → `IssueCheck` (summary, eligibility, policy, publish preview, `assessment`). No run is created |
+| POST | `/api/runs` | `{issue_url, continue_despite: [warning codes], assessment_only: bool = false}` → `RunView`; enforces limits; creates the session cookie if missing. v0.4: an UNSUPPORTED / ASSESSMENT_ONLY issue returns 201 with a FINISHED `ASSESSMENT_ONLY` run (no job, no limit used) instead of 422 `UNSUPPORTED_REPO` |
 | GET | `/api/runs/{id}` | `RunView`; 404 for both "doesn't exist" and "not yours" |
 | GET | `/api/runs/{id}/events?after=<seq>` | polling JSON; SSE if `Accept: text/event-stream` (§3) |
 | GET | `/api/runs/{id}/pr-status` | GitHub PR state, cached 10 min; `null` state = unknown |
@@ -239,6 +296,7 @@ global_llm_tokens_per_day = 0 # REQUIRED: must be set from a measured run before
 budget_measured_tokens_per_run = 0   # record the M3 feasibility measurement here
 budget_measured_on = ""             # date + model of that measurement
 run_llm_tokens = 300_000
+assess_llm_tokens_per_day = 120_000   # v0.4 (#48): intake extraction only (role "assessor"), ~3k tokens per new issue version → ~40/day; also counted in global_llm_tokens_per_day; 0 = extraction off. Not an execution quota: assessments use no run slot
 run_active_seconds = 1500
 setup_seconds = 480
 max_pause_seconds = 7200
```
