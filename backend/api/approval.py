"""B10: the human gate on the exact diff (contracts §5, screen S-05)."""
from contextlib import closing
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
from backend.gates.diff_policy import is_test_path
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


def for_viewer(v: RunView, request: Request) -> list[PublishBlocker]:
    """contracts v0.8 (#100): PUBLISH_NOT_ALLOWED depends on who is looking, so it's added to what we return and never
    stored on the run (Approve and the outcome rule never see it)."""
    from backend.api import session
    from backend.config import may_publish
    acct = session.account(request)
    return v.publish_blockers + ([] if may_publish(acct and acct["login"], v.issue.repo) else [PublishBlocker.PUBLISH_NOT_ALLOWED])


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
def _shown_elsewhere(c: dict, checks: list[dict], uncovered: list[str] | None) -> bool:
    """A concern code wrote (review.SOURCES tag, #108) whose cause the explainer lists itself. Untagged text, including
    every model concern, is never dropped, so de-duplicating can't hide a fact."""
    row = lambda i, **kw: any(x["id"] == i and x["status"] == CheckStatus.FAILED and all(x.get(k) == y for k, y in kw.items())
                              for x in checks)
    return {"variant": lambda: row("hidden_variant"), "coverage": lambda: bool(uncovered),
            "lint": lambda: row("repo_check", tool=c.get("tool"))}.get(c.get("source"), lambda: False)()


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
    # kv variant:<rid> is per attempt (Revise clears it); use it only when it matches the recorded status
    # kv variant:<rid> describes one attempt: use its reason and evidence only when they match the recorded status
    mine = variant if (variant or {}).get("status") == hv.value else {}
    ev = mine.get("evidence")   # only a list of strings counts: an int would raise, a string would be read letter by letter
    hv_reason, hv_ev = mine.get("reason"), ev if isinstance(ev, list) and all(isinstance(e, str) for e in ev) else []
    caps = cap_reasons(v)
    checks = [
        {"id": "reproduced", "status": g("G3"), "runs": r.runs_on_base if r else [], "evidence": r.evidence_ids if r else []},
        {"id": "fixed", "status": g("G5"), "runs": vf.new_test_runs if vf else [], "regressions": vf.regressions if vf else [],
         "evidence": [e for e in vf.evidence_ids if e not in hv_ev] if vf else []},   # #108: the variant's logs are its own
        {"id": "baseline", "status": g("G2"), "partial": b.partial if b else None, "evidence": b.evidence_ids if b else [],
         "counts": {"passed": len(b.pass_set), "failed": len(b.fail_set), "flaky": len(b.flaky_set)} if b else None},
        {"id": "hidden_variant", "status": hv, "reason": hv_reason, "evidence": hv_ev},
        {"id": "only_these_files", "status": g("G4")},
        {"id": "supplyguard", "status": v.supplyguard.status if v.supplyguard else CheckStatus.NOT_RUN},
        *([{"id": "repo_check", "tool": c["tool"], "status": REPO_CHECK.get(c["status"], CheckStatus.INCONCLUSIVE),
            "unsupported": c["status"] == "UNSUPPORTED", "note": c.get("note")} for c in rc["checks"]] if rc["checks"] else
          [{"id": "repo_check", "tool": None, "status": CheckStatus.NOT_RUN, "reason": rc.get("reason")}]),
    ]
    risks = ([{"kind": "review", "severity": c.get("severity"), "text": c.get("text"), "location": c.get("location")}
              for c in (v.review.concerns if v.review else [])
              if c.get("level") != "ACCEPTED_TRADEOFF" and not _shown_elsewhere(c, checks, r and r.uncovered)]
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


def _sentence(text: str) -> str:
    t = text.strip()
    return t if t.endswith((".", "!", "?")) else t + "."


def suggestions(e: dict, fix_files: list[str]) -> dict[str, str]:
    """#98: a suggested answer per ownership question, from a code template over the explainer's recorded fields only.
    Plain and short, so a contributor can say it to a maintainer; each sentence is only as strong as its evidence, because
    "Use this answer" copies it into the field (§2.3, v0.11). Test ids and failure text stay in the evidence beside it."""
    p, row = e["problem"], {c["id"]: c for c in e["verification"]}
    rep, fix, hv = row["reproduced"], row["fixed"], row["hidden_variant"]

    shown = rep["status"] == "passed"
    exp, act = (p["expected"] or "").strip(), (p["actual"] or "").strip()
    seen = (" The new test fails on the original code, which confirms it." if shown else
            " Not confirmed yet: the new test wasn't shown to fail on the original code.") if p["tests"] else ""
    if exp and act:
        broken = f"It should: {_sentence(exp)} Instead: {_sentence(act)}{seen}"
    elif exp:
        broken = f"It should: {_sentence(exp)} The issue doesn't say what happens instead.{seen}"
    elif act:
        broken = f"What goes wrong: {_sentence(act)} The issue doesn't say what should happen instead.{seen}"
    elif seen:
        broken = f"The issue doesn't spell out the expected behaviour.{seen}"
    else:
        broken = "Nothing was recorded about the bug, so describe it from the issue and the diff."

    files = ", ".join(fix_files) or "no source files"
    claim = ((e["root_cause"] or {}).get("claim") or "").strip()
    why = (f"{_sentence(claim)} The fix changes {files} to correct that." if claim else
           f"The cause wasn't recorded. The fix changes {files}; read the diff to see why it helps.")

    if not p["tests"]:
        return {"what_was_broken": broken, "why_this_fix": why,
                "what_the_test_proves": "No regression test was recorded, so there is nothing for a test to prove yet."}
    passes = fix["status"] == "passed"
    gaps = [r["text"] for r in e["risks"] if r["kind"] == "uncovered"]
    unchecked = any(r["kind"] == "coverage_not_checked" for r in e["risks"])
    # the strong ending only when every recorded check backs it (a Needs-attention run reaches this screen too)
    strong = shown and passes and hv["status"] == "passed" and not fix["regressions"] and not gaps and not unchecked
    one = len(p["tests"]) == 1
    t, f_, p_ = ("The new test", "fails", "passes") if one else (f"The {len(p['tests'])} new tests", "fail", "pass")
    if shown and passes:
        proves = f"{t} {f_} without the fix and {p_} with it" + (
            f", so this bug can't come back without {'the test' if one else 'them'} catching it." if strong else ".")
    elif not shown:
        proves = f"{t} {'was' if one else 'were'}n't shown to fail without the fix, so {'it doesn' if one else 'they don'}'t prove much yet."
    else:
        proves = f"{t} {f_} without the fix, but {'it was' if one else 'they were'}n't shown to pass with it."
    # one caveat at most, the most serious first
    caveat = ("A variant of the test still fails, so the fix may only cover the exact case tested." if hv["status"] == "failed" else
              f"{len(fix['regressions'])} existing test{'' if len(fix['regressions']) == 1 else 's'} broke with the fix." if fix["regressions"] else
              f"It doesn't check: {'; '.join(gaps)}." if gaps else
              "We didn't check that it covers everything the issue describes." if unchecked else
              {"inconclusive": "A variant of the test gave an unclear result.", "not_run": "A variant of the test wasn't run."}.get(hv["status"], ""))
    return {"what_was_broken": broken, "why_this_fix": why,
            "what_the_test_proves": f"{proves} {caveat}".strip() if not strong else proves}


@router.get("/api/runs/{run_id}/approval")
def approval_context(run_id: str, request: Request):
    import json
    import logging
    v = _run(request, run_id)
    diff = exact_diff(v)
    dh, eh = hashes(v, diff)
    try:   # optional help: a bad record must never block seeing or approving the diff
        with closing(db.connect()) as c:   # #108: closed here, not left open for the garbage collector
            try:
                variant = json.loads(db.get_kv(c, f"variant:{run_id}") or "null")
            except ValueError:
                variant = None
            rc = db.repo_checks(c, run_id)
        help_ = explainer(v, rc, variant if isinstance(variant, dict) else None)
    except Exception:
        logging.getLogger(__name__).exception("explainer failed for run %s", run_id)
        help_ = None
    fix_files = sorted(f for f in changed_files(diff) if not is_test_path(f))   # G4: the fix never edits tests
    try:   # its own guard: a template bug must not take down the explainer
        hints = suggestions(help_, fix_files) if help_ else None
    except Exception:
        logging.getLogger(__name__).exception("suggestions failed for run %s", run_id)
        hints = None
    return {"revision": v.revision, "diff": diff, "diff_hash": dh, "evidence_hash": eh, "files": sorted(changed_files(diff)),
            "publish_blockers": for_viewer(v, request), "approved": v.approval is not None,
            "pr_title": f"Fix #{v.issue.number}: {v.issue.title}"[:120],
            "pr_summary": summary_prefill(v),
            # v0.5 §2.3: what PatchPilot found, shown as help next to the three own-words questions (never prefilled into them)
            "help": {"explainer": help_, "suggestions": hints, "fix_files": fix_files},
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
    return _revise(_run(request, run_id), body.target, body.feedback)


TEST_ASKS = {"missing_test", "test_quality"}


def plan_request(plan: dict) -> tuple[str, str]:
    """#103: the maintainer's own words are the request; the assistant's reading is only a hint."""
    target = "test" if any(g["category"] in TEST_ASKS for g in plan["groups"]) else "fix"
    lines = ["The maintainer reviewed the pull request and asked for these changes. Their words are the request; "
             "the notes after them are an assistant's reading and may be wrong."]
    for n, i in enumerate((i for g in plan["groups"] for i in g["items"]), 1):
        where = f" ({i['path']}{':' + str(i['line']) if i.get('line') else ''})" if i.get("path") else ""
        lines.append(f"{n}. {i['author'] or 'CI'}{where}: {(i['quote'] or '')[:1500]}")
        hint = "; ".join(x for x in (i.get("meaning"), i.get("change")) if x)
        if hint:
            lines.append(f"   Hint: {hint[:800]}")
    return target, "\n".join(lines)[:12000]


@router.post("/api/runs/{run_id}/revise-from-feedback", response_model=RunView)
def revise_from_feedback(run_id: str, request: Request):
    """#103: revise using the saved revision plan from the PR page. The plan is used once."""
    import json
    v = _run(request, run_id)
    c = db.connect()
    eid = db.get_kv(c, f"revision_plan:{run_id}")
    try:
        plan = json.loads(artifacts.get(eid)) if eid else None
        target, text = plan_request(plan) if plan and plan.get("groups") else (None, None)
    except (ValueError, KeyError, TypeError):
        target = None
    if target is None:
        raise _err(409, "NO_PLAN", "Save a revision plan on the pull request page first.")
    from backend.github.progress import tracked
    if tracked(c, run_id).get("state") in ("merged", "closed"):
        raise _err(409, "PR_DONE", "This pull request is merged or closed, so there's nothing to push to. Start a new run instead.")
    v = _revise(v, target, text, plan_evidence_id=eid, plan_saved_at=plan.get("saved_at"))
    c.execute("DELETE FROM kv WHERE key=?", (f"revision_plan:{run_id}",))   # consumed; the revision keeps its id
    return v


def _revise(v: RunView, target: str, feedback: str, **plan) -> RunView:
    run_id = v.run_id
    if v.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.PUBLISHED):
        raise _err(409, "NOT_REVISABLE", "Only a finished fix can be revised.")
    if set(v.publish_blockers) & PERMANENT_BLOCKERS:
        raise _err(409, "NOT_REVISABLE", "This run can't be revised; start a new run instead.")
    if not budget_left(run_id):
        raise _err(409, "BUDGET_SPENT", NO_BUDGET)
    _void(v, "revise")
    v.revisions.append(RevisionSummary(revision=v.revision, outcome=v.outcome, end_reason=v.end_reason,
                                       diff_hash=diff_hash(exact_diff(v)), finished_at=v.updated_at,
                                       revise_target=target, feedback=feedback, **plan))
    v.revision += 1
    v.status, v.outcome, v.end_reason, v.readiness = RunStatus.REVISING, None, None, None
    c = db.connect()
    db.save_run(c, v)
    with db.tx(c):
        c.execute("INSERT INTO jobs(run_id,kind,state,available_at) VALUES(?,?,?,?)", (run_id, "revise", "queued", db.now().isoformat()))
        # #108/#113: per-attempt results; the next attempt writes its own, so a revision that stops early shows "not run"
        c.execute("DELETE FROM kv WHERE key IN (?,?,?)", (f"variant:{run_id}", f"repo_checks:{run_id}", f"bisect:{run_id}"))
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
