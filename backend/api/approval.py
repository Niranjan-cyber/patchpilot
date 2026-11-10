"""B10: the human gate on the exact diff (contracts §5, screen S-05)."""
import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend import artifacts, db
from backend.contracts.hashing import canonical_diff, diff_hash, evidence_hash, evidence_manifest
from datetime import datetime

from backend.contracts.models import (Approval, ApproveRequest, CheckStatus, Owner, PERMANENT_BLOCKERS, PublishBlocker, RevisionSummary,
                                      cap_reasons,
                                      RunStatus, RunView)
from backend.github import reader

router = APIRouter()
CHECKLIST = ("read_diff", "understands_change", "ai_note_ok")
CLEARABLE_OK = {PublishBlocker.NOT_APPROVED, PublishBlocker.NOT_SIGNED_IN, PublishBlocker.NO_MAINTAINER_CONSENT}   # v0.5: consent comes later


def _err(status, code, msg, retry=None):
    from backend.api.main import ApiErr
    return ApiErr(status, code, msg, retry)


def _run(request: Request, run_id: str) -> RunView:
    from backend.api.main import _is_real, _own
    if not _is_real(run_id):
        raise _err(404, "NOT_FOUND", "This run isn't available.")
    _own(request, run_id)
    return db.get_run(db.connect(), run_id)


NO_BUDGET = "This run has used its AI budget, so a revision would stop at once. Start a new run to try a different fix."


def budget_left(run_id: str) -> bool:
    """Revise needs AI tokens; the gateway refuses every call once the run's cap is reached (ends with budget_run)."""
    from backend import llm_gateway
    from backend.config import limits
    return llm_gateway.tokens_used(run_id=run_id) < limits()["run_llm_tokens"]


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


def summary_prefill(v: RunView) -> str:
    """What the Review screen pre-fills for the PR's 'Cause and fix': the diagnosis, then the fixer's own summary. The user
    edits and approves it, so the fixer's words reach the PR only through text the user saw (ownership rule, #83)."""
    from backend.agents.fix import UNFINISHED
    cause = (v.diagnosis.hypothesis if v.diagnosis else "") or ""
    fix = (v.patch.policy_reason or "").strip() if v.patch and v.patch.policy_reason != UNFINISHED else ""
    return f"{cause}\n\nThe fix: {fix}".strip() if fix else cause


def changed_files(diff: str) -> set[str]:
    return {l.split(" b/", 1)[1].strip() for l in diff.splitlines() if l.startswith("diff --git ") and " b/" in l}


def new_existing_work(start: dict | None, now: dict, *, me: str | None, started_at: str, claims_known_at_start: bool) -> list[str]:
    """#70 item 4: work that appeared since the run started (code decides). The user's own comments never count.
    An unreadable source now is unknown, so it fails closed. Without a start snapshot (older runs), claims count only if the
    issue had none at the start."""
    out, mine = [], (me or "").lower()
    if now.get("claimants") is None:
        out.append("the issue's comments couldn't be read, so we can't confirm nobody has claimed it")
    else:
        before = set() if start is None else {x.lower() for x in (start.get("claimants") or []) + (start.get("assignees") or []) if x}
        people = [p for p in dict.fromkeys((now.get("claimants") or []) + (now.get("assignees") or []))
                  if p and p.lower() != mine and p.lower() not in before]
        if people and start is not None and start.get("claimants") is None:   # unreadable then: old and new look the same
            out.append("the comments couldn't be read when the run started, so we can't tell whether these claims are new: "
                       + ", ".join(people))
        elif people and (start is not None or claims_known_at_start):
            out.append("since the run started, " + ", ".join(people) + " claimed the issue or was assigned")
    for pr in now.get("closed_prs") or []:
        if pr.get("merged_at") and datetime.fromisoformat(pr["merged_at"]) > datetime.fromisoformat(started_at):
            out.append(f"pull request #{pr['number']}, which mentions this issue, was merged after the run started")
    return out


def _login(c, run_id: str) -> str | None:
    """The user's GitHub login: the publishing account, else the signed-in owner (at approve nothing is published yet)."""
    aid = db.get_kv(c, f"publish_account:{run_id}") or (c.execute("SELECT owner_account_id FROM runs WHERE run_id=?",
                                                                  (run_id,)).fetchone() or [None])[0]
    return (c.execute("SELECT login FROM accounts WHERE id=?", (int(aid),)).fetchone() or [None])[0] if aid else None


def accept_issue_change(run_id: str) -> None:
    """The user approved despite the change: what they saw becomes the baseline, so publish blocks only on newer changes."""
    import json
    c = db.connect()
    if (raw := db.get_kv(c, f"existing_work_recheck:{run_id}")):
        seen = json.loads(raw)
        db.put_kv(c, f"existing_work:{run_id}", json.dumps({k: x for k, x in seen.items() if k not in ("new", "warnings")}))
        db.put_kv(c, f"issue_change_accepted:{run_id}", json.dumps(seen.get("warnings") or []))


def stale_checks(v: RunView, diff: str) -> list[PublishBlocker]:
    """Has the world moved since we tested? Fails closed: if GitHub can't confirm, raise (never assume unchanged)."""
    import json
    out, recheck, c = [], None, db.connect()
    try:
        chk = reader.check_issue(v.issue.html_url, extract_model=False)   # repo facts only: no assessor call
        warned = sorted({"closed", "linked_pr"} & set(chk.warnings))
        if set(warned) - set(json.loads(db.get_kv(c, f"issue_change_accepted:{v.run_id}") or "[]")):
            out.append(PublishBlocker.ISSUE_CHANGED)
        if chk.existing_work is not None:   # new claims / assignees / merged PRs since the start (#70 item 4)
            start = json.loads(db.get_kv(c, f"existing_work:{v.run_id}") or "null")
            new = new_existing_work(start, chk.existing_work, me=_login(c, v.run_id), started_at=v.created_at.isoformat(),
                                    claims_known_at_start=v.issue.checks.get("unassigned") == CheckStatus.PASSED)
            recheck = {**chk.existing_work, "new": new, "warnings": warned}
            if new and PublishBlocker.ISSUE_CHANGED not in out:
                out.append(PublishBlocker.ISSUE_CHANGED)
        with reader._client() as h:
            cmp = reader._get(h, f"/repos/{v.issue.repo}/compare/{v.base_sha}...{chk.default_branch}")
    except reader.GitHubError as e:
        raise _err(503, "GITHUB_UNAVAILABLE", f"We couldn't confirm nothing changed upstream. {e}", e.retry_after)
    if recheck is not None:   # saved only once every lookup answered, so a 503 never leaves a clean-looking re-check
        db.put_kv(c, f"existing_work_recheck:{v.run_id}", json.dumps(recheck))
    files = {f["filename"] for f in cmp.get("files", [])}
    if len(cmp.get("files", [])) >= 300 or files & changed_files(diff):
        out.append(PublishBlocker.UPSTREAM_CHANGED)
    return out


REPO_CHECK = {"PASS": CheckStatus.PASSED, "FAIL": CheckStatus.FAILED, "BLOCKED": CheckStatus.INCONCLUSIVE,
              "NOT_RUN": CheckStatus.NOT_RUN, "UNSUPPORTED": CheckStatus.NOT_RUN}
# Reviewer concerns that code wrote from facts the explainer can list itself (variant.review_concern, publisher.COVERAGE_NOTE,
# lint.review_concerns). test_approval builds them with those producers, so a wording change there fails a test.
VARIANT_CONCERN = re.compile(r"^The fix passes the visible test but fails a hidden variant")
COVERAGE_CONCERN = re.compile(r"^The test designer didn't claim")
LINT_CONCERN = re.compile(r"^The repo's (.+?) reports \d+ new problems? in the changed files")


def _shown_elsewhere(text: str, checks: list[dict], uncovered: list[str] | None) -> bool:
    """True only if the explainer lists this concern's cause itself, so dropping it never hides a fact."""
    row = lambda i, **kw: any(c["id"] == i and c["status"] == CheckStatus.FAILED and all(c.get(k) == x for k, x in kw.items())
                              for c in checks)
    if VARIANT_CONCERN.match(text):
        return row("hidden_variant")
    if COVERAGE_CONCERN.match(text):
        return bool(uncovered)
    m = LINT_CONCERN.match(text)
    return bool(m and row("repo_check", tool=m.group(1)))


def _cap_says_it(c: dict, caps: list[str]) -> bool:
    """An inconclusive check whose only cause is a readiness cap is listed once, as the cap."""
    if c["id"] == "supplyguard":
        return c["status"] == CheckStatus.INCONCLUSIVE and "supplyguard_inconclusive" in caps
    return (c["id"] == "baseline" and c["status"] == CheckStatus.INCONCLUSIVE and "baseline_partial" in caps
            and not (c["counts"] and (c["counts"]["flaky"] or c["counts"]["failed"])))


def explainer(v: RunView, repo_checks: dict | None, variant: dict | None) -> dict:
    """#97: the Contribution Explainer, only from what this run recorded (no model calls). Statuses are the recorded
    ones; anything that didn't run is "not_run" and listed under risks, never shown as passed. Each cause is listed once."""
    g = lambda k: v.gates.get(k, CheckStatus.NOT_RUN)
    r, d, vf, b = v.repro, v.diagnosis, v.verify, v.baseline
    rc = repo_checks or {"checks": None, "reason": "not_run_yet"}
    hv = (vf and vf.hidden_variant) or CheckStatus.NOT_RUN
    # kv variant:<rid> isn't reset on a revision: its reason only explains the status it was written with
    hv_reason = (variant or {}).get("reason") if (variant or {}).get("status") == hv.value else None
    caps = cap_reasons(v)
    checks = [
        {"id": "reproduced", "status": g("G3"), "runs": r.runs_on_base if r else [], "evidence": r.evidence_ids if r else []},
        {"id": "fixed", "status": g("G5"), "runs": vf.new_test_runs if vf else [], "regressions": vf.regressions if vf else [],
         "evidence": vf.evidence_ids if vf else []},
        {"id": "baseline", "status": g("G2"), "partial": b.partial if b else None, "evidence": b.evidence_ids if b else [],
         "counts": {"passed": len(b.pass_set), "failed": len(b.fail_set), "flaky": len(b.flaky_set)} if b else None},
        {"id": "hidden_variant", "status": hv, "reason": hv_reason},
        {"id": "only_these_files", "status": g("G4")},
        {"id": "supplyguard", "status": v.supplyguard.status if v.supplyguard else CheckStatus.NOT_RUN},
        *([{"id": "repo_check", "tool": c["tool"], "status": REPO_CHECK.get(c["status"], CheckStatus.INCONCLUSIVE),
            "unsupported": c["status"] == "UNSUPPORTED", "note": c.get("note")} for c in rc["checks"]] if rc["checks"] else
          [{"id": "repo_check", "tool": None, "status": CheckStatus.NOT_RUN, "reason": rc.get("reason")}]),
    ]
    risks = ([{"kind": "review", "severity": c.get("severity"), "text": c.get("text"), "location": c.get("location")}
              for c in (v.review.concerns if v.review else [])
              if c.get("level") != "ACCEPTED_TRADEOFF" and not _shown_elsewhere(str(c.get("text") or ""), checks, r and r.uncovered)]
             + [{"kind": "check", **c} for c in checks if c["status"] != CheckStatus.PASSED and not _cap_says_it(c, caps)]
             + [{"kind": "cap", "reason": x} for x in caps]
             + ([{"kind": "uncovered", "text": t} for t in r.uncovered] if r and r.uncovered
                else [{"kind": "coverage_not_checked"}] if r and r.uncovered is None else []))
    blob = f"https://github.com/{v.issue.repo}/blob/{v.base_sha}/"
    return {
        "problem": {"expected": v.issue.expected, "actual": v.issue.actual, "tests": r.test_ids if r else [],
                    "failure": r.expected_failure if r else None, "evidence": [r.test_diff_id, *r.evidence_ids] if r else []},
        "root_cause": d and {"claim": d.hypothesis, "evidence": d.evidence_ids,
                             "citations": [{"path": l.path, "line": l.line,
                                            "url": blob + quote(l.path) + (f"#L{l.line}" if l.line else "")} for l in d.locations]},
        "fix": {"only_these_files": g("G4"), "evidence": [v.patch.fix_diff_id, v.patch.test_diff_id] if v.patch else []},
        "verification": checks, "risks": risks, "readiness": v.readiness,
    }


@router.get("/api/runs/{run_id}/approval")
def approval_context(run_id: str, request: Request):
    import json
    import logging
    v = _run(request, run_id)
    diff = exact_diff(v)
    dh, eh = hashes(v, diff)
    try:   # optional help: a bad record must never block seeing or approving the diff
        c = db.connect()
        try:
            variant = json.loads(db.get_kv(c, f"variant:{run_id}") or "null")
        except ValueError:
            variant = None
        help_ = explainer(v, db.repo_checks(c, run_id), variant if isinstance(variant, dict) else None)
    except Exception:
        logging.getLogger(__name__).exception("explainer failed for run %s", run_id)
        help_ = None
    return {"revision": v.revision, "diff": diff, "diff_hash": dh, "evidence_hash": eh, "files": sorted(changed_files(diff)),
            "publish_blockers": v.publish_blockers, "approved": v.approval is not None,
            "pr_title": f"Fix #{v.issue.number}: {v.issue.title}"[:120],
            "pr_summary": summary_prefill(v),
            # v0.5 §2.3: what PatchPilot found, shown as help next to the three own-words questions (never prefilled into them)
            "help": {"explainer": help_},
            "revise_blocked": None if budget_left(run_id) else NO_BUDGET}


@router.post("/api/runs/{run_id}/approve", response_model=RunView)
def approve(run_id: str, body: ApproveRequest, request: Request, accept_issue_changed: bool = False):
    from backend.api import session
    v = _run(request, run_id)
    if v.status != RunStatus.AWAITING_APPROVAL:
        raise _err(409, "APPROVAL_STALE", "This run isn't waiting for approval any more. Reload to see its current state.")
    if not all(body.checklist.get(k) for k in CHECKLIST):
        raise _err(422, "CHECKLIST_INCOMPLETE", "Tick all three boxes to approve.")
    if body.ownership is None:   # contracts v0.5 §2.3: required; only the length is checked, never the content
        raise _err(422, "OWNERSHIP_REQUIRED", "Answer the three short questions in your own words before approving.")
    diff = exact_diff(v)
    if (body.revision, body.diff_hash, body.evidence_hash) != (v.revision, *hashes(v, diff)):
        raise _err(409, "APPROVAL_STALE", "The change or its evidence changed since you opened it. Please review it again.")
    if set(v.publish_blockers) - CLEARABLE_OK - ({PublishBlocker.ISSUE_CHANGED} if accept_issue_changed else set()):
        raise _err(409, "PUBLISH_BLOCKED", "This run can't be approved: " + ", ".join(b.value for b in v.publish_blockers))
    new = [b for b in stale_checks(v, diff) if b not in v.publish_blockers]
    if PublishBlocker.ISSUE_CHANGED in new and accept_issue_changed:
        new.remove(PublishBlocker.ISSUE_CHANGED)
        accept_issue_change(run_id)
        db.emit(db.connect(), run_id, "approval.recorded", None, v.revision, note="approved despite issue change")
    if new:
        v.publish_blockers += new
        if PublishBlocker.UPSTREAM_CHANGED in new:
            v.status = RunStatus.FINISHED
        db.save_run(db.connect(), v)
        code = "UPSTREAM_CHANGED" if PublishBlocker.UPSTREAM_CHANGED in new else "APPROVAL_STALE"
        raise _err(409, code, "Files in this change were edited upstream after we tested. Re-run on the latest code."
                   if code == "UPSTREAM_CHANGED" else "The issue changed since the run: it was closed, a pull request now addresses it, or someone else claimed it.")
    v.approval = Approval(run_id=run_id, revision=v.revision, diff_hash=body.diff_hash, evidence_hash=body.evidence_hash,
                          approved_by=Owner(session_id_hash=session.current(request)), approved_at=db.now(),
                          checklist=body.checklist, explanation=body.explanation, ownership=body.ownership, pr_title=body.pr_title, pr_summary=body.pr_summary)
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
    target: Literal["fix", "test"] = "fix"   # v0.6: "test" rewrites the reproduction test (smart_open-833), then re-fixes


@router.post("/api/runs/{run_id}/revise", response_model=RunView)
def revise(run_id: str, body: ReviseBody, request: Request):
    v = _run(request, run_id)
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.PUBLISHED):
        raise _err(409, "NOT_REVISABLE", "Only a finished fix can be revised.")
    if set(v.publish_blockers) & PERMANENT_BLOCKERS:
        raise _err(409, "NOT_REVISABLE", "This run can't be revised; start a new run instead.")
    if not budget_left(run_id):
        raise _err(409, "BUDGET_SPENT", NO_BUDGET)
    _void(v, "revise")
    v.revisions.append(RevisionSummary(revision=v.revision, outcome=v.outcome, end_reason=v.end_reason,
                                       diff_hash=diff_hash(exact_diff(v)), finished_at=v.updated_at,
                                       revise_target=body.target, feedback=body.feedback))
    v.revision += 1
    v.status, v.outcome, v.end_reason, v.readiness = RunStatus.REVISING, None, None, None
    c = db.connect()
    db.save_run(c, v)
    with db.tx(c):
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
