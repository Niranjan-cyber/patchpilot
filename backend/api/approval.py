"""B10: the human gate on the exact diff (contracts §5, screen S-05)."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend import artifacts, db
from backend.contracts.hashing import canonical_diff, diff_hash, evidence_hash, evidence_manifest
from backend.contracts.models import (Approval, ApproveRequest, Owner, PERMANENT_BLOCKERS, PublishBlocker, RevisionSummary,
                                      RunStatus, RunView)
from backend.github import reader

router = APIRouter()
CHECKLIST = ("read_diff", "understands_change", "ai_note_ok")
CLEARABLE_OK = {PublishBlocker.NOT_APPROVED, PublishBlocker.NOT_SIGNED_IN}


def _err(status, code, msg, retry=None):
    from backend.api.main import ApiErr
    return ApiErr(status, code, msg, retry)


def _run(request: Request, run_id: str) -> RunView:
    from backend.api.main import _is_real, _own
    if not _is_real(run_id):
        raise _err(404, "NOT_FOUND", "This run isn't available.")
    _own(request, run_id)
    return db.get_run(db.connect(), run_id)


def exact_diff(v: RunView) -> str:
    if not v.patch:
        raise _err(409, "NOT_READY", "This run has no verified change to review.")
    parts = [artifacts.get(v.patch.test_diff_id), artifacts.get(v.patch.fix_diff_id)]
    if any(p is None for p in parts):
        raise _err(410, "DETAILS_EXPIRED", "This run's diff has expired.")
    return canonical_diff(b"".join(parts).decode("utf-8", "replace"))


def hashes(v: RunView, diff: str) -> tuple[str, str]:
    dh = diff_hash(diff)
    m = evidence_manifest(run_id=v.run_id, revision=v.revision, base_sha=v.base_sha, diff_hash=dh,
                          gates={k: s.value for k, s in v.gates.items()}, outcome=v.outcome.value if v.outcome else None,
                          verify_evidence_ids=v.verify.evidence_ids if v.verify else [],
                          baseline_evidence_ids=v.baseline.evidence_ids if v.baseline else [],
                          repro_evidence_ids=v.repro.evidence_ids if v.repro else [],
                          supplyguard_report_id=v.supplyguard.report_id if v.supplyguard else None, review_id=None)
    return dh, evidence_hash(m)


def changed_files(diff: str) -> set[str]:
    return {l.split(" b/", 1)[1].strip() for l in diff.splitlines() if l.startswith("diff --git ") and " b/" in l}


def stale_checks(v: RunView, diff: str) -> list[PublishBlocker]:
    """Has the world moved since we tested? Fails closed: if GitHub can't confirm, raise (never assume unchanged)."""
    out = []
    try:
        chk = reader.check_issue(v.issue.html_url)
        if {"closed", "linked_pr"} & set(chk.warnings):
            out.append(PublishBlocker.ISSUE_CHANGED)
        with reader._client() as h:
            cmp = reader._get(h, f"/repos/{v.issue.repo}/compare/{v.base_sha}...{chk.default_branch}")
    except reader.GitHubError as e:
        raise _err(503, "GITHUB_UNAVAILABLE", f"We couldn't confirm nothing changed upstream. {e}", e.retry_after)
    files = {f["filename"] for f in cmp.get("files", [])}
    if len(cmp.get("files", [])) >= 300 or files & changed_files(diff):
        out.append(PublishBlocker.UPSTREAM_CHANGED)
    return out


@router.get("/api/runs/{run_id}/approval")
def approval_context(run_id: str, request: Request):
    v = _run(request, run_id)
    diff = exact_diff(v)
    dh, eh = hashes(v, diff)
    return {"revision": v.revision, "diff": diff, "diff_hash": dh, "evidence_hash": eh, "files": sorted(changed_files(diff)),
            "publish_blockers": v.publish_blockers, "approved": v.approval is not None,
            "pr_title": f"Fix #{v.issue.number}: {v.issue.title}"[:120],
            "pr_summary": (v.diagnosis.hypothesis if v.diagnosis else "") or ""}


@router.post("/api/runs/{run_id}/approve", response_model=RunView)
def approve(run_id: str, body: ApproveRequest, request: Request, accept_issue_changed: bool = False):
    from backend.api import session
    v = _run(request, run_id)
    if v.status != RunStatus.AWAITING_APPROVAL:
        raise _err(409, "APPROVAL_STALE", "This run isn't waiting for approval any more. Reload to see its current state.")
    if not all(body.checklist.get(k) for k in CHECKLIST):
        raise _err(422, "CHECKLIST_INCOMPLETE", "Tick all three boxes to approve.")
    diff = exact_diff(v)
    if (body.revision, body.diff_hash, body.evidence_hash) != (v.revision, *hashes(v, diff)):
        raise _err(409, "APPROVAL_STALE", "The change or its evidence changed since you opened it. Please review it again.")
    if set(v.publish_blockers) - CLEARABLE_OK - ({PublishBlocker.ISSUE_CHANGED} if accept_issue_changed else set()):
        raise _err(409, "PUBLISH_BLOCKED", "This run can't be approved: " + ", ".join(b.value for b in v.publish_blockers))
    new = [b for b in stale_checks(v, diff) if b not in v.publish_blockers]
    if PublishBlocker.ISSUE_CHANGED in new and accept_issue_changed:
        new.remove(PublishBlocker.ISSUE_CHANGED)
        db.emit(db.connect(), run_id, "approval.recorded", None, v.revision, note="approved despite issue change")
    if new:
        v.publish_blockers += new
        if PublishBlocker.UPSTREAM_CHANGED in new:
            v.status = RunStatus.FINISHED
        db.save_run(db.connect(), v)
        code = "UPSTREAM_CHANGED" if PublishBlocker.UPSTREAM_CHANGED in new else "APPROVAL_STALE"
        raise _err(409, code, "Files in this change were edited upstream after we tested. Re-run on the latest code."
                   if code == "UPSTREAM_CHANGED" else "The issue changed since the run (closed or a new linked pull request).")
    v.approval = Approval(run_id=run_id, revision=v.revision, diff_hash=body.diff_hash, evidence_hash=body.evidence_hash,
                          approved_by=Owner(session_id_hash=session.current(request)), approved_at=db.now(),
                          checklist=body.checklist, explanation=body.explanation, pr_title=body.pr_title, pr_summary=body.pr_summary)
    v.publish_blockers = [b for b in v.publish_blockers if b != PublishBlocker.NOT_APPROVED]
    db.save_run(db.connect(), v)
    db.emit(db.connect(), run_id, "approval.recorded", None, v.revision, diff_hash=body.diff_hash)
    return v


def _void(v: RunView, reason: str) -> None:
    if v.approval is not None:
        v.approval = None
        db.emit(db.connect(), v.run_id, "approval.voided", None, v.revision, reason=reason)
    if PublishBlocker.NOT_APPROVED not in v.publish_blockers:
        v.publish_blockers.append(PublishBlocker.NOT_APPROVED)


class ReviseBody(BaseModel):
    feedback: str = Field(min_length=3, max_length=2000)


@router.post("/api/runs/{run_id}/revise", response_model=RunView)
def revise(run_id: str, body: ReviseBody, request: Request):
    v = _run(request, run_id)
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.PUBLISHED):
        raise _err(409, "NOT_REVISABLE", "Only a finished fix can be revised.")
    if set(v.publish_blockers) & PERMANENT_BLOCKERS:
        raise _err(409, "NOT_REVISABLE", "This run can't be revised; start a new run instead.")
    _void(v, "revise")
    v.revisions.append(RevisionSummary(revision=v.revision, outcome=v.outcome, end_reason=v.end_reason,
                                       diff_hash=diff_hash(exact_diff(v)), finished_at=v.updated_at))
    v.revision += 1
    v.status, v.outcome, v.end_reason, v.readiness = RunStatus.REVISING, None, None, None
    c = db.connect()
    db.save_run(c, v)
    with db.tx(c):
        db.put_kv(c, f"revise:{run_id}", body.feedback)
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (run_id, "revise", "queued", db.now().isoformat()))
    return v


@router.post("/api/runs/{run_id}/recheck-deps", response_model=RunView)
def recheck_deps(run_id: str, request: Request):
    from backend.sandbox import steps
    v = _run(request, run_id)
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.FINISHED):
        raise _err(409, "NOT_READY", "Wait until the run has finished.")
    v.supplyguard = steps.run_supplyguard(run_id)
    v.publish_blockers = [b for b in v.publish_blockers if b != PublishBlocker.DEPS_INCONCLUSIVE]
    if v.supplyguard.status.value == "inconclusive":
        v.publish_blockers.append(PublishBlocker.DEPS_INCONCLUSIVE)
    _void(v, "dependencies re-checked")   # always: new report id → old evidence hash is invalid
    db.save_run(db.connect(), v)
    return v


@router.post("/api/runs/{run_id}/keep-report", response_model=RunView)
def keep_report(run_id: str, request: Request):
    v = _run(request, run_id)
    if v.status == RunStatus.AWAITING_APPROVAL:
        v.status = RunStatus.FINISHED
        db.save_run(db.connect(), v)
    return v



@router.get("/api/runs/{run_id}/diff.patch")
def download_diff(run_id: str, request: Request):
    from fastapi.responses import PlainTextResponse
    v = _run(request, run_id)
    return PlainTextResponse(exact_diff(v), headers={"Content-Disposition": f'attachment; filename="patchpilot-{run_id[:8]}.patch"'})
