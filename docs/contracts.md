# PatchPilot: Shared Contracts (v0.2 draft)

This file is the boundary between the four build lanes: **(1) sandbox + setup + baseline, (2) agent roles + gates, (3) GitHub reader/publisher + auth, (4) React UI + event polling.** Lanes build against these types and fixtures, not against each other's code.

**Change rule:** freeze this before splitting work. After that, changes go through a PR touching only this file (and `backend/contracts/`), reviewed by one person from every lane. Bump the version on each merge.

Source of truth in code: `backend/contracts/*.py` (Pydantic v2). The frontend's TypeScript types are generated from the JSON Schema of these models, never hand-written.

## 1. Enums

```python
class StepId(str, Enum):
    INTAKE = "intake"; PREFLIGHT = "preflight"; SETUP = "setup"; BASELINE = "baseline"
    REPRODUCE = "reproduce"; DIAGNOSE = "diagnose"; FIX = "fix"; VERIFY = "verify"
    REVIEW = "review"; REPORT = "report"; APPROVAL = "approval"; PUBLISH = "publish"

class CheckStatus(str, Enum):          # one label per check (brief 7.6)
    PASSED = "passed"; FAILED = "failed"; INCONCLUSIVE = "inconclusive"
    NOT_RUN = "not_run"; BLOCKED = "blocked"

class RunStatus(str, Enum):            # lifecycle, drives S-03 vs S-04/S-05/S-07
    QUEUED = "queued"; RUNNING = "running"; PAUSED = "paused"
    INTERRUPTED = "interrupted"        # worker died; lease expired; will resume
    AWAITING_APPROVAL = "awaiting_approval"; REVISING = "revising"
    PUBLISHING = "publishing"; PUBLISHED = "published"
    FINISHED = "finished"              # terminal without a PR (any outcome)

class Outcome(str, Enum):              # set exactly once per revision, when that revision's analysis ends
    VERIFIED_FIX = "VERIFIED_FIX"; FIX_NEEDS_ATTENTION = "FIX_NEEDS_ATTENTION"
    TRIAGE_ONLY = "TRIAGE_ONLY"; CANNOT_REPRODUCE = "CANNOT_REPRODUCE"
    ENV_FAILED = "ENV_FAILED"; BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"                # ended (user or limit) before any outcome-defining evidence
    SYSTEM_ERROR = "SYSTEM_ERROR"      # our infrastructure failed before any outcome-defining evidence

class EndReason(str, Enum):            # why analysis stopped
    COMPLETED = "completed"; RETRIES_EXHAUSTED = "retries_exhausted"
    TOKEN_LIMIT = "token_limit"; RUNTIME_LIMIT = "runtime_limit"
    PAUSE_TIMEOUT = "pause_timeout"; USER_STOPPED = "user_stopped"; SYSTEM_ERROR = "system_error"

class PublishBlocker(str, Enum):       # empty list = publishing allowed
    # permanent for this run: status goes to FINISHED
    OUTCOME_NOT_VERIFIED = "outcome_not_verified"; REPO_FORBIDS_AI = "repo_forbids_ai"
    PRS_RESTRICTED = "prs_restricted"; RUN_STOPPED = "run_stopped"
    UPSTREAM_CHANGED = "upstream_changed"   # files in our diff changed upstream → re-run on latest code
    # clearable: status stays AWAITING_APPROVAL
    DEPS_INCONCLUSIVE = "deps_inconclusive"; ISSUE_CHANGED = "issue_changed"
    NOT_APPROVED = "not_approved"; NOT_SIGNED_IN = "not_signed_in"
```

## 1.1 Gates (canonical; the worker, the publisher and the UI all use this table)

Each gate is computed by code from recorded artifacts. Its `gate.result` event carries the status, a reason code and the evidence IDs.

| Gate | Input evidence | `passed` | `failed` | `inconclusive` | `blocked` | Next |
|---|---|---|---|---|---|---|
| **G0 Eligibility** | IssueSpec, repo record, timeline (cross-referenced PRs), file listing | issue open · repo public · Python project · tests found · unassigned · no linked open PR | any of: closed, assigned, linked open PR → run only if the user sent the code in `continue_despite` (recorded) | a lookup failed → run only with `continue_despite` | — | PREFLIGHT. Private / non-Python / no tests → **no run is created** (API error `UNSUPPORTED_REPO`). AI policy "forbidden" isn't a gate failure; it adds the `REPO_FORBIDS_AI` blocker |
| **G1 Pre-flight** | dependency files at `base_sha`, SupplyGuard report | no confirmed malicious or typosquatted package (CVEs listed as findings) | — | SupplyGuard error, lookup failure or unsupported format → continue, add `DEPS_INCONCLUSIVE` | confirmed malicious / typosquat → outcome `BLOCKED`, terminal, **no override** | SETUP |
| **G2 Setup** | install log, `pytest --collect-only` output | install exit 0 within `setup_seconds` **and** collection exit 0 with ≥ 1 test | still failing after one AI-assisted retry (install commands only) → `ENV_FAILED` | — (infra failures resume, §7) | — | BASELINE (records pass/fail/flaky sets; not a gate; a partial baseline caps readiness) |
| **G3 Reproduction** | test diff, 2 runs on the original code | diff touches test files only · the new test fails in **both** runs with an assertion error or the issue's error, not an import, syntax or collection error | otherwise → Test designer retry (≤ 2), then `CANNOT_REPRODUCE` | 1 of 2 runs fails (flaky) → counts as a failed attempt | — | DIAGNOSE: every cited evidence ID must exist; invalid → one Investigator retry; still invalid → analysis ends (`retries_exhausted`) as `TRIAGE_ONLY` with "diagnosis unavailable" |
| **G4 Diff policy** | fix diff | non-test source files only · ≤ 5 files and ≤ 200 changed lines · no dependency-file changes · no `.github/` · no test deleted, skipped or edited | → back to the Fixer with the reason (counts as a Fixer attempt) | — | — | VERIFY |
| **G5 Verification** | fresh-container runs on original + test diff + fix diff | the new test passes in **both** runs **and** every test in the baseline pass set passes | → Fixer retry with logs (≤ 3), then one re-diagnosis, then `TRIAGE_ONLY` | the new test passes 1 of 2, or a baseline test flips → counts as a failed attempt | — | REVIEW (the Reviewer can only lower readiness) |
| **G6 Report integrity** | report, `gates`, evidence manifest | every status in the report equals the recorded status · every claim cites an existing evidence ID | the Explainer regenerates (≤ 2); then the report is rendered from the deterministic template without AI narrative. **Never changes the outcome** | — | — | outcome + status (§1.2) |

## 1.2 Outcome rule (deterministic, by code, per revision)

When a revision's analysis ends, for whatever `EndReason`, take the **first** row that matches:

| # | Condition | Outcome |
|---|---|---|
| 1 | G1 = blocked | `BLOCKED` |
| 2 | G2 = failed | `ENV_FAILED` |
| 3 | G5 = passed, `end_reason = completed`, Reviewer raised no concerns, no readiness cap | `VERIFIED_FIX` |
| 4 | G5 = passed (any other case, e.g. a limit was hit before review, Reviewer concerns, deps inconclusive, partial baseline) | `FIX_NEEDS_ATTENTION` |
| 5 | G3 = passed and the run then ended without a passing G5: diagnosis included if valid, otherwise marked "unavailable". **Exception:** a stop or limit *during* DIAGNOSE with no diagnosis yet falls through to row 8 | `TRIAGE_ONLY` |
| 6 | G3 = failed after its retries | `CANNOT_REPRODUCE` |
| 7 | `end_reason = system_error` | `SYSTEM_ERROR` |
| 8 | anything else (stopped or limit hit before rows 1–6 apply, e.g. during setup, while reproducing, or before the diagnosis finished) | `STOPPED` |

- A user stop is **never** `SYSTEM_ERROR`, and never `CANNOT_REPRODUCE` unless G3 really failed. A stopped run keeps every artifact recorded so far, and its report says where it stopped.
- **`end_reason = user_stopped` always adds `RUN_STOPPED`**, so a stopped run is never publishable, even if G5 had passed (row 4 → FIX_NEEDS_ATTENTION, report-only).
- `outcome`, `end_reason` and `readiness` describe the **latest revision**. Earlier revisions are kept in `revisions[]` (§2).

**Readiness** (UI badge): VERIFIED_FIX → "Ready for human review" · FIX_NEEDS_ATTENTION → "Needs attention" · TRIAGE_ONLY → "Unable to verify a fix" · STOPPED → "Stopped, report so far" · the rest → "Unable to verify". Readiness is capped at FIX_NEEDS_ATTENTION when `supplyguard.status == INCONCLUSIVE`, the baseline is partial, or the Reviewer lowers it.

## 1.3 Run status transitions

| From | Event | To |
|---|---|---|
| QUEUED | worker leases the job | RUNNING |
| QUEUED | user stop | FINISHED (`STOPPED`, `user_stopped`) |
| RUNNING / REVISING | provider quota or global budget hit; guided pause | PAUSED |
| RUNNING / REVISING | lease expired | INTERRUPTED |
| RUNNING / REVISING | analysis ends; outcome VERIFIED_FIX or FIX_NEEDS_ATTENTION and only **clearable** blockers | AWAITING_APPROVAL |
| RUNNING / REVISING | analysis ends with any other outcome, or with a permanent blocker | FINISHED |
| PAUSED | capacity back / user clicks Continue | RUNNING (or REVISING) |
| PAUSED | paused > `max_pause_seconds` | analysis ends, `pause_timeout` → outcome by §1.2 → AWAITING_APPROVAL or FINISHED |
| any non-terminal | user stop | analysis ends, `user_stopped` → outcome by §1.2 → FINISHED |
| INTERRUPTED | job resumed | previous status |
| INTERRUPTED | 2 failed resumes of the same step | analysis ends, `system_error` → outcome by §1.2 → FINISHED |
| AWAITING_APPROVAL | Revise | REVISING (revision + 1, approval voided) |
| AWAITING_APPROVAL | recheck-deps finishes | AWAITING_APPROVAL (approval voided; blockers recomputed) |
| AWAITING_APPROVAL | publish with a valid approval | PUBLISHING |
| AWAITING_APPROVAL | "Keep report only" | FINISHED |
| PUBLISHING | `publish.finished` created / updated / branch_only | PUBLISHED |
| PUBLISHING | refused (stale, hash mismatch, upstream changed) or failed | AWAITING_APPROVAL with the error shown; `UPSTREAM_CHANGED` → FINISHED |
| PUBLISHED | Revise (updates the same PR) | REVISING |
| FINISHED | — | terminal. "Re-run" creates a **new** run |

Retention expiry (§9) isn't a status. It sets `details_expired_at`, and the UI shows "This run's details have expired".

## 2. Run state

Internal state is the brief's `RunState` (§7.4) plus the fields below. The API exposes a read-only **`RunView`**: everything except owner identifiers, raw LLM prompts and secrets.

```python
class RunState(BaseModel):
    run_id: str                       # uuid4; non-secret; appears in URLs
    revision: int = 0                 # +1 on every Revise; voids older approvals
    status: RunStatus
    outcome: Outcome | None = None
    end_reason: EndReason | None = None
    owner: Owner                      # session_id_hash | account_id (never exposed)
    issue: IssueSpec                  # incl. html_url, number, repo, eligibility checks
    base_sha: str
    policy: RepoPolicy                # ai_policy: allowed|forbidden|unknown, prs_restricted, source file ids
    env: EnvProfile | None
    baseline: TestRun | None          # pass_set, fail_set, flaky_set, evidence_ids
    repro: ReproTest | None
    diagnosis: Diagnosis | None       # locations, hypothesis, tour[], evidence_ids
    patch: Patch | None               # fix_diff_id, test_diff_id, attempt, policy_result
    verify: Verification | None
    supplyguard: SGReport | None      # status: CheckStatus, findings, files, failures
    review: ReviewResult | None
    gates: dict[str, CheckStatus]     # "G0".."G6"
    steps: dict[StepId, StepState]    # status, started_at, finished_at, attempt, headline
    attempts: dict[str, int]          # role -> attempts used
    budget: Budget                    # tokens_used/limit, active_seconds/limit, paused_since
    pause: PauseInfo | None           # reason, provider, resume_at: datetime | None (None = unknown)
    publish_blockers: list[PublishBlocker]
    revisions: list[RevisionSummary]  # per revision: outcome, end_reason, diff_hash, evidence_ids, finished_at
    details_expired_at: datetime | None  # set by retention (§9)
    approval: Approval | None
    pr: PullRequestRef | None         # url, number, head_branch, fork_owner, state (from GitHub)
    created_at: datetime; updated_at: datetime
```

Large content (logs, diffs, test output) is stored in the artifact store, keyed by **`sha256:<hex>`** of the bytes. Those keys are the evidence IDs. State holds only IDs.

## 3. Event stream (polling first, SSE optional)

**Primary:** `GET /api/runs/{run_id}/events?after=<seq>` → `{"events": [<envelope>…], "next_after": <seq>}`, polled every 2 s while the run isn't terminal (every 10 s while paused). This works through any tunnel; Cloudflare Quick Tunnels don't support SSE. **Optional:** the same path with `Accept: text/event-stream`, using the format below. Every event is appended to the `events` table *before* it's returned, so both are views of the log.

```
id: 42
event: step.finished
data: {"v":1,"run_id":"…","seq":42,"ts":"2026-11-11T10:42:07Z","type":"step.finished","step":"reproduce","revision":0,"payload":{…}}
```

- `seq` is per-run, strictly increasing, and equals the SSE `id`. On reconnect the browser sends `Last-Event-ID`; the server replays every event with `seq > id`, then streams live ones. The UI rebuilds its state from `GET /api/runs/{id}` + replay, never from local guesses.
- Heartbeat comment `: ping` every 15 s.
- **Events never contain** tokens, cookies, OAuth codes, raw prompts, or full logs. Long output is referenced by evidence ID. Every log excerpt passes the redactor (token patterns, `Authorization:`, env dumps).

| type | payload |
|---|---|
| `run.queued` | `position` |
| `run.started` / `run.resumed` | `from_step` |
| `run.paused` | `reason` (`provider_quota` / `global_budget` / `guided_pause`), `resume_at` (or null) |
| `run.interrupted` | `last_completed_step` |
| `step.started` | `step`, `attempt`, `headline` |
| `step.progress` | `step`, `message` (≤ 200 chars, plain words) |
| `step.finished` | `step`, `status: CheckStatus`, `headline`, `evidence_ids[]` |
| `gate.result` | `gate`, `status`, `reason`, `evidence_ids[]` |
| `attempt.retry` | `role`, `attempt`, `max`, `reason` |
| `analysis.finished` | `outcome`, `end_reason`, `readiness`, `publish_blockers[]` |
| `approval.recorded` / `approval.voided` | `revision`, `diff_hash` / `reason` |
| `publish.progress` | `stage` (`apply`, `verify_hash`, `fork`, `push`, `open_pr`) |
| `publish.finished` | `status` (`created` / `updated` / `branch_only` / `failed`), `pr_url` / `compare_url`, `error_code` |

## 4. API surface (lane 3 + lane 4 agree on this)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/issues/check` | `{url}` → `IssueCheck` (summary, eligibility, policy, publish preview). No run is created |
| POST | `/api/runs` | `{issue_url, continue_despite: [warning codes]}` → `RunView`; enforces limits; creates the session cookie if missing |
| GET | `/api/runs/{id}` | `RunView`; 404 for both "doesn't exist" and "not yours" |
| GET | `/api/runs/{id}/events?after=<seq>` | polling JSON; SSE if `Accept: text/event-stream` (§3) |
| GET | `/api/runs/{id}/pr-status` | GitHub PR state, cached 10 min; `null` state = unknown |
| GET | `/healthz` | DB writable, worker heartbeat fresh, Docker reachable |
| POST | `/api/runs/{id}/stop` | ends analysis with `user_stopped`; outcome by §1.2; never publishable |
| POST | `/api/runs/{id}/revise` | `{feedback}` → revision +1, approval voided, back to FIX |
| POST | `/api/runs/{id}/approve` | `{revision, diff_hash, evidence_hash, checklist, explanation: str \| null (≤ 2,000 chars), pr_title, pr_summary}` (§5) |
| POST | `/api/runs/{id}/keep-report` | "Keep report only" → FINISHED |
| POST | `/api/runs/{id}/rerun` | new run on the latest default-branch commit (counts against limits) |
| POST | `/api/runs/{id}/publish` | requires an account + valid approval; idempotent |
| POST | `/api/runs/{id}/recheck-deps` | reruns SupplyGuard; **always voids the approval** (new report ID); may clear `DEPS_INCONCLUSIVE` |
| POST | `/api/runs/{id}/false-positive` | `{note}` → team review queue; the run stays BLOCKED |
| DELETE | `/api/runs/{id}/access` | "Forget this run" for this browser |
| GET | `/api/me/runs` | runs for this session and/or account |
| GET | `/api/artifacts/{evidence_id}` | owner-checked; `Content-Disposition` for downloads |
| GET | `/api/runs/{id}/report.md`, `/diff.patch` | downloads |
| GET | `/auth/github/start`, `/auth/github/callback` | OAuth; on success, claims the session's runs |

**Error shape:** `{"code": "LIMIT_SESSION_DAILY", "message": "plain words", "retry_after": 3600 | null}`. Codes: `INVALID_URL`, `NOT_AN_ISSUE`, `PRIVATE_REPO`, `UNSUPPORTED_REPO`, `GITHUB_UNAVAILABLE`, `LIMIT_SESSION_DAILY`, `LIMIT_ACCOUNT_DAILY`, `LIMIT_ACTIVE_RUN`, `LIMIT_GLOBAL_BUDGET`, `NOT_FOUND`, `APPROVAL_STALE`, `HASH_MISMATCH`, `UPSTREAM_CHANGED`, `DEPS_REPORT_CHANGED`, `PUBLISH_BLOCKED`, `AUTH_REQUIRED`, `DETAILS_EXPIRED`.

## 5. Approval and hash contract

```python
class Approval(BaseModel):
    run_id: str
    revision: int
    diff_hash: str          # sha256 of the canonical combined diff
    evidence_hash: str      # sha256 of the canonical evidence manifest
    approved_by: Owner      # session or account; must be the run owner
    approved_at: datetime
    checklist: dict[str, bool]   # read_diff, understands_change, ai_note_ok: all True
    explanation: str | None      # optional "in your own words"; sent in the approve request; stored, never in the PR body
    pr_title: str; pr_summary: str   # editable; NOT part of either hash
```

- **Canonical diff:** `git diff --no-color --no-ext-diff --full-index --binary <base_sha>` of the test diff + fix diff applied together, with paths sorted, LF line endings, and no trailing whitespace changes. `diff_hash = sha256(bytes)`.
- **Evidence manifest:** canonical JSON (sorted keys, no whitespace) of `{run_id, revision, base_sha, diff_hash, gates, outcome, verify_evidence_ids, baseline_evidence_ids, repro_evidence_ids, supplyguard_report_id, review_id}`. `evidence_hash = sha256(manifest)`.
- **Approve** is accepted only if the request's `revision`, `diff_hash` and `evidence_hash` equal the server's current values, all checklist items are true, and `publish_blockers` contains nothing except `NOT_APPROVED` / `NOT_SIGNED_IN`. Otherwise → `APPROVAL_STALE`.
- **Voiding:** Revise, **any completed recheck-deps** (it always creates a new `supplyguard_report_id`, whatever the result), or any change to a hashed field → `approval = None` + `approval.voided` event. The user must review and approve the current evidence again; the UI never carries the old checklist over.
- **Publisher (the only holder of a GitHub write token):** (1) load the approval; (2) fresh clone at `base_sha` in its own workspace, outside the sandbox; (3) apply the stored diff, recompute `diff_hash` and the manifest, compare → `HASH_MISMATCH` refuses; (4) re-check the issue (open, no new linked PR) → otherwise `APPROVAL_STALE` with `ISSUE_CHANGED`; (4a) check that the **latest** SupplyGuard report ID equals the manifest's `supplyguard_report_id`, and that its status isn't inconclusive → otherwise `DEPS_REPORT_CHANGED`; (4b) **upstream check:** `GET /repos/{o}/{r}/compare/{base_sha}...{default_branch}`. If any file in the canonical diff appears in the changed files, or the compare result is truncated (> 300 files), → `UPSTREAM_CHANGED` (permanent blocker; the UI offers Re-run on latest code). Other upstream changes are allowed, and the PR body names `base_sha`. The same checks also run when `approve` is called, so S-05 shows Stale before the user publishes; (5) branch `patchpilot/issue-<number>-<run_id[:8]>`; (6) **idempotency:** look up an existing PR with that head branch first, update it if found; (7) open a **draft** PR whose body includes the AI-assistance note and evidence summary.

## 6. Access and limits

- **Browser identity:** cookie `pp_sid` = 256-bit random token, `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=30d`. The server stores only `sha256(token)`. Runs are owned by a session hash or an account ID. "Forget this run" removes the run from that session; signing out or clearing revokes the session row.
- **Sign-in claims runs:** on the OAuth callback, every run owned by the current session moves to the account.
- **Never logged:** the `Cookie`, `Authorization` and `Set-Cookie` headers, OAuth `code`/`state`, and GitHub tokens are stripped by logging middleware. Analytics events carry no run token, no session token and no issue URL query string. Run pages and the API send `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer`.
- **Limits config** (`config/limits.toml`, all enforced in the API and worker, never in the browser):

```toml
session_runs_per_day = 2      # plus hashed-IP backstop
account_runs_per_day = 5
active_runs_per_owner = 1
global_concurrent_runs = 1    # 2 on a VM
global_llm_tokens_per_day = 0 # REQUIRED: must be set from a measured run before the demo. 0 = unset → the worker leases no jobs, /healthz is red, POST /api/runs returns LIMIT_GLOBAL_BUDGET. Never treated as unlimited
budget_measured_tokens_per_run = 0   # record the M3 feasibility measurement here
budget_measured_on = ""             # date + model of that measurement
run_llm_tokens = 300_000
run_active_seconds = 1500
setup_seconds = 480
max_pause_seconds = 7200
retries = { test_designer = 2, fixer = 3, rediagnose = 1 }
```

`resume_at` is set only from a provider's `Retry-After` header or a documented reset time. Otherwise it's null and the UI says "until capacity is available".

## 7. Execution guarantee

- The `jobs` table holds: `run_id, state, lease_owner, lease_expires_at, heartbeat_at, attempt`. The worker heartbeats every 10 s with a 60 s lease. An expired lease → another (or the restarted) worker takes the job, emits `run.interrupted` → `run.resumed`, and continues from the last LangGraph checkpoint.
- A step interrupted mid-way re-runs in a new container. Infrastructure re-runs don't count as role attempts. After 2 failed resumes of the same step, analysis ends with `end_reason = system_error`. The outcome then follows §1.2: `SYSTEM_ERROR` only if no outcome-defining evidence exists yet, otherwise the best honest outcome, with the report so far.
- **No cross-run environment reuse.** Each run builds its **own** setup image (`pp-run-<run_id>`) from a pinned base image (`python:<ver>-slim@sha256:…`). Every step starts a fresh container from it, with a fresh writable workspace volume. Nothing built or written by repository code is ever reused by another run or user. The image is deleted 48 h after the run reaches AWAITING_APPROVAL/PUBLISHED/FINISHED; a later Revise rebuilds it from the run's recipe.
- **Shared caches are trusted and immutable:** (a) `proxpi` caches files downloaded from PyPI (its only upstreams are `pypi.org` and `files.pythonhosted.org`; it never accepts uploads); (b) `env_recipes` stores *data only* (Python version, install commands that succeeded, base image digest), replayed as commands in a fresh container. The uv/pip cache inside a run's container is never mounted from or saved to the host.
- The API process never runs repository code and never holds a GitHub write token.
- SQLite runs in WAL mode; one API and one worker process share the database on the same host.

## 8. Fixtures to create first (so lanes can work before the backend exists)

`fixtures/runs/<case>/state.json` + `events.jsonl` for: `verified_fix`, `needs_attention_deps_inconclusive`, `triage_only`, `cannot_reproduce`, `env_failed`, `blocked`, `paused_quota_unknown_reset`, `pause_timeout`, `interrupted_then_resumed`, `stopped_during_setup`, `stopped_after_verify`, `upstream_changed`, `published_fork`, `publish_branch_only`, `details_expired`. Lane 4 builds every S-03/S-04/S-07 state against these. Lane 2 has to produce real runs whose events match them. A contract test replays each fixture through the Pydantic models in CI.

## 9. Retention

| Data | Kept | After that |
|---|---|---|
| Sandbox containers and workspace volumes | until the step ends; all deleted when the run leaves RUNNING | — |
| Per-run setup image | 48 h after the run stops changing | a later Revise rebuilds it from the recipe |
| Logs, test output, command transcripts, `events.payload` excerpts, `llm_calls` rows | **14 days** | deleted; S-03 Show details says "Logs expired" |
| Report (`report.md`), canonical diff, run summary (`RunView` without logs), approvals, `fp_reports` | **30 days** | deleted; `details_expired_at` set |
| Tombstone (run_id, owner, created_at, outcome, PR URL) | until the owner forgets the run or the session expires (30 d) / the account is deleted | the run link shows "This run's details have expired"; the PR stays on GitHub |

The reaper (architecture §7) enforces this daily. Expiry never turns a recorded outcome into "unknown": the tombstone keeps it.
