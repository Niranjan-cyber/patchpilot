"""Shared contracts (docs/contracts.md v0.2). Change only via a `contracts:` PR approved by all three roles."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

CONTRACTS_VERSION = "0.2"


class StepId(str, Enum):
    INTAKE = "intake"; PREFLIGHT = "preflight"; SETUP = "setup"; BASELINE = "baseline"
    REPRODUCE = "reproduce"; DIAGNOSE = "diagnose"; FIX = "fix"; VERIFY = "verify"
    REVIEW = "review"; REPORT = "report"; APPROVAL = "approval"; PUBLISH = "publish"


class CheckStatus(str, Enum):
    PASSED = "passed"; FAILED = "failed"; INCONCLUSIVE = "inconclusive"
    NOT_RUN = "not_run"; BLOCKED = "blocked"


class RunStatus(str, Enum):
    QUEUED = "queued"; RUNNING = "running"; PAUSED = "paused"; INTERRUPTED = "interrupted"
    AWAITING_APPROVAL = "awaiting_approval"; REVISING = "revising"
    PUBLISHING = "publishing"; PUBLISHED = "published"; FINISHED = "finished"


class Outcome(str, Enum):
    VERIFIED_FIX = "VERIFIED_FIX"; FIX_NEEDS_ATTENTION = "FIX_NEEDS_ATTENTION"
    TRIAGE_ONLY = "TRIAGE_ONLY"; CANNOT_REPRODUCE = "CANNOT_REPRODUCE"
    ENV_FAILED = "ENV_FAILED"; BLOCKED = "BLOCKED"; STOPPED = "STOPPED"; SYSTEM_ERROR = "SYSTEM_ERROR"


class EndReason(str, Enum):
    COMPLETED = "completed"; RETRIES_EXHAUSTED = "retries_exhausted"
    TOKEN_LIMIT = "token_limit"; RUNTIME_LIMIT = "runtime_limit"
    PAUSE_TIMEOUT = "pause_timeout"; USER_STOPPED = "user_stopped"; SYSTEM_ERROR = "system_error"


class PublishBlocker(str, Enum):
    OUTCOME_NOT_VERIFIED = "outcome_not_verified"; REPO_FORBIDS_AI = "repo_forbids_ai"
    PRS_RESTRICTED = "prs_restricted"; RUN_STOPPED = "run_stopped"; UPSTREAM_CHANGED = "upstream_changed"
    DEPS_INCONCLUSIVE = "deps_inconclusive"; ISSUE_CHANGED = "issue_changed"
    NOT_APPROVED = "not_approved"; NOT_SIGNED_IN = "not_signed_in"


PERMANENT_BLOCKERS = {
    PublishBlocker.OUTCOME_NOT_VERIFIED, PublishBlocker.REPO_FORBIDS_AI, PublishBlocker.PRS_RESTRICTED,
    PublishBlocker.RUN_STOPPED, PublishBlocker.UPSTREAM_CHANGED,
}
GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
READINESS = {
    Outcome.VERIFIED_FIX: "Ready for human review",
    Outcome.FIX_NEEDS_ATTENTION: "Needs attention",
    Outcome.TRIAGE_ONLY: "Unable to verify a fix",
    Outcome.STOPPED: "Stopped, report so far",
}


# ---- sub-models (fields from contracts §2 comments) ----
class Owner(BaseModel):
    session_id_hash: str | None = None
    account_id: int | None = None


class IssueSpec(BaseModel):
    html_url: str
    repo: str                      # owner/name
    number: int
    title: str
    summary: str | None = None     # AI summary, label: estimate
    expected: str | None = None
    actual: str | None = None
    labels: list[str] = []
    checks: dict[str, CheckStatus] = {}   # G0 items: open, public, python, tests_found, unassigned, no_linked_pr


class RepoPolicy(BaseModel):
    ai_policy: Literal["allowed", "forbidden", "unknown"] = "unknown"
    prs_restricted: bool | None = None
    source_evidence_ids: list[str] = []


class EnvProfile(BaseModel):
    python_version: str
    install_cmds: list[str]
    test_cmd: str = "pytest"
    image_id: str | None = None


class TestRun(BaseModel):
    pass_set: list[str] = []
    fail_set: list[str] = []
    flaky_set: list[str] = []
    partial: bool = False
    evidence_ids: list[str] = []


class ReproTest(BaseModel):
    test_diff_id: str
    test_ids: list[str]
    expected_failure: str
    runs_on_base: list[CheckStatus] = []   # one per run; G3 needs two FAILED
    evidence_ids: list[str] = []


class Location(BaseModel):
    path: str
    line: int | None = None


class TourItem(BaseModel):
    path: str
    why: str


class Diagnosis(BaseModel):
    locations: list[Location] = []
    hypothesis: str
    tour: list[TourItem] = []
    evidence_ids: list[str] = []


class Patch(BaseModel):
    fix_diff_id: str
    test_diff_id: str
    attempt: int
    policy_result: CheckStatus
    policy_reason: str | None = None


class Verification(BaseModel):
    new_test_runs: list[CheckStatus] = []
    regressions: list[str] = []
    container_id: str | None = None
    hidden_variant: CheckStatus | None = None
    evidence_ids: list[str] = []


class SGReport(BaseModel):
    report_id: str
    status: CheckStatus
    findings: list[dict[str, Any]] = []
    files: list[str] = []
    failures: list[str] = []


class ReviewResult(BaseModel):
    concerns: list[dict[str, str]] = []    # {severity, text}
    lowers_readiness: bool = False


class StepState(BaseModel):
    status: CheckStatus | Literal["running"] = CheckStatus.NOT_RUN
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempt: int = 0
    headline: str | None = None


class Budget(BaseModel):
    tokens_used: int = 0
    tokens_limit: int = 300_000
    active_seconds: int = 0
    active_seconds_limit: int = 1500
    paused_since: datetime | None = None


class PauseInfo(BaseModel):
    reason: Literal["provider_quota", "global_budget", "guided_pause"]
    provider: str | None = None
    resume_at: datetime | None = None    # None = unknown; never guessed


class PullRequestRef(BaseModel):
    url: str | None = None
    number: int | None = None
    head_branch: str
    fork_owner: str | None = None
    compare_url: str | None = None
    state: Literal["open", "merged", "closed"] | None = None   # None = unknown


class RevisionSummary(BaseModel):
    revision: int
    outcome: Outcome | None
    end_reason: EndReason | None
    diff_hash: str | None = None
    evidence_ids: list[str] = []
    finished_at: datetime | None = None


class Approval(BaseModel):
    run_id: str
    revision: int
    diff_hash: str
    evidence_hash: str
    approved_by: Owner
    approved_at: datetime
    checklist: dict[str, bool]
    explanation: str | None = Field(default=None, max_length=2000)
    pr_title: str
    pr_summary: str


class ApproveRequest(BaseModel):
    revision: int
    diff_hash: str
    evidence_hash: str
    checklist: dict[str, bool]
    explanation: str | None = Field(default=None, max_length=2000)
    pr_title: str
    pr_summary: str


class RunView(BaseModel):
    """What the API returns. RunState (worker-internal) = RunView + owner."""
    run_id: str
    revision: int = 0
    status: RunStatus
    outcome: Outcome | None = None
    end_reason: EndReason | None = None
    readiness: str | None = None
    issue: IssueSpec
    base_sha: str
    policy: RepoPolicy = RepoPolicy()
    env: EnvProfile | None = None
    baseline: TestRun | None = None
    repro: ReproTest | None = None
    diagnosis: Diagnosis | None = None
    patch: Patch | None = None
    verify: Verification | None = None
    supplyguard: SGReport | None = None
    review: ReviewResult | None = None
    gates: dict[str, CheckStatus] = {}
    steps: dict[StepId, StepState] = {}
    attempts: dict[str, int] = {}
    budget: Budget = Budget()
    pause: PauseInfo | None = None
    publish_blockers: list[PublishBlocker] = []
    revisions: list[RevisionSummary] = []
    approval: Approval | None = None
    pr: PullRequestRef | None = None
    details_expired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunState(RunView):
    owner: Owner


EventType = Literal[
    "run.queued", "run.started", "run.resumed", "run.paused", "run.interrupted",
    "step.started", "step.progress", "step.finished", "gate.result", "attempt.retry",
    "analysis.finished", "approval.recorded", "approval.voided", "publish.progress", "publish.finished",
]


class Event(BaseModel):
    v: Literal[1] = 1
    run_id: str
    seq: int
    ts: datetime
    type: EventType
    step: StepId | None = None
    revision: int = 0
    payload: dict[str, Any] = {}


class GateResult(BaseModel):
    """What every gate evaluator returns (contracts §1.1). Code decides; never an LLM."""
    gate: Literal["G0", "G1", "G2", "G3", "G4", "G5", "G6"]
    status: CheckStatus
    reason: str                      # short machine-readable code, e.g. "import_error", "flaky_1_of_2"
    evidence_ids: list[str] = []


class ApiError(BaseModel):
    code: str
    message: str
    retry_after: int | None = None


# ---- deterministic rules (contracts §1.2) ----
def decide_outcome(gates: dict[str, CheckStatus], end_reason: EndReason, *, review_concerns: bool = False,
                   readiness_capped: bool = False, diagnosis_valid: bool = False,
                   stopped_during_diagnose: bool = False) -> Outcome:
    g = lambda k: gates.get(k, CheckStatus.NOT_RUN)
    if g("G1") == CheckStatus.BLOCKED:
        return Outcome.BLOCKED
    if g("G2") == CheckStatus.FAILED:
        return Outcome.ENV_FAILED
    if g("G5") == CheckStatus.PASSED:
        clean = end_reason == EndReason.COMPLETED and not review_concerns and not readiness_capped
        return Outcome.VERIFIED_FIX if clean else Outcome.FIX_NEEDS_ATTENTION
    if g("G3") == CheckStatus.PASSED and not (stopped_during_diagnose and not diagnosis_valid):
        return Outcome.TRIAGE_ONLY
    if g("G3") == CheckStatus.FAILED:
        return Outcome.CANNOT_REPRODUCE
    if end_reason == EndReason.SYSTEM_ERROR:
        return Outcome.SYSTEM_ERROR
    return Outcome.STOPPED


def readiness(outcome: Outcome, *, capped: bool = False) -> str:
    if outcome == Outcome.VERIFIED_FIX and capped:
        outcome = Outcome.FIX_NEEDS_ATTENTION
    return READINESS.get(outcome, "Unable to verify")


def status_after_analysis(outcome: Outcome, blockers: list[PublishBlocker]) -> RunStatus:
    publishable = outcome in (Outcome.VERIFIED_FIX, Outcome.FIX_NEEDS_ATTENTION)
    if publishable and not (set(blockers) & PERMANENT_BLOCKERS):
        return RunStatus.AWAITING_APPROVAL
    return RunStatus.FINISHED


def end_blockers(end_reason: EndReason, outcome: Outcome) -> list[PublishBlocker]:
    """Blockers implied by how analysis ended (contracts §1.2)."""
    out = []
    if outcome not in (Outcome.VERIFIED_FIX, Outcome.FIX_NEEDS_ATTENTION):
        out.append(PublishBlocker.OUTCOME_NOT_VERIFIED)
    if end_reason == EndReason.USER_STOPPED:
        out.append(PublishBlocker.RUN_STOPPED)
    return out
