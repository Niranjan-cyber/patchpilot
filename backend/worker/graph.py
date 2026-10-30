"""LangGraph pipeline (brief §7.1 / contracts §1.1). Checkpointed after every node in data/checkpoints.db."""
import operator
import sqlite3
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend import db
from backend.config import ROOT
from backend.contracts.models import (CheckStatus, EndReason, PublishBlocker, RunStatus, StepId, StepState, decide_outcome,
                                      end_blockers, readiness, status_after_analysis)
from backend.worker.nodes import NODES, ORDER, StepContext

HEADLINE_RUNNING = {
    StepId.PREFLIGHT: "Checking the project's dependencies for known-bad packages…",
    StepId.SETUP: "Installing the project in a fresh sandbox…", StepId.BASELINE: "Running the existing tests…",
    StepId.REPRODUCE: "Writing a test that should fail because of this bug…", StepId.DIAGNOSE: "Looking for the cause…",
    StepId.FIX: "Writing a small fix…", StepId.VERIFY: "Checking the fix in a brand-new sandbox…",
    StepId.REVIEW: "Reviewing the fix for shortcuts…",
}
STOP_EARLY = {"G1": {CheckStatus.BLOCKED}, "G2": {CheckStatus.FAILED}, "G3": {CheckStatus.FAILED},
              "G4": {CheckStatus.FAILED}, "G5": {CheckStatus.FAILED}}


class S(TypedDict, total=False):
    run_id: str
    gates: Annotated[dict, operator.or_]
    end_reason: str | None
    stopped_at: str | None


def _step_node(step: StepId):
    def node(state: S) -> S:
        c = db.connect(); rid = state["run_id"]; run = db.get_run(c, rid)
        if db.stop_requested(c, rid):
            return {"end_reason": EndReason.USER_STOPPED.value, "stopped_at": step.value}
        if _guided_pause(c, run, step):
            interrupt({"paused_before": step.value})   # LangGraph stops here; Continue re-enters this node
        run.steps[step] = StepState(status="running", started_at=db.now(), headline=HEAD(step)); db.save_run(c, run)
        db.emit(c, rid, "step.started", step.value, run.revision, attempt=1, headline=HEAD(step))
        ctx = StepContext(rid, run, lambda t, s=None, **p: db.emit(c, rid, t, s, run.revision, **p))
        res = NODES[step](ctx)
        while (q := ctx.scratch.pop("pause", None)) is not None:     # provider quota: pause, never guess a resume time
            since = ctx.scratch.setdefault("paused_since", __import__("time").time())
            if not _wait_out_pause(c, rid, q, since, step.value):
                return {"end_reason": EndReason.PAUSE_TIMEOUT.value if not db.stop_requested(c, rid) else EndReason.USER_STOPPED.value,
                        "stopped_at": step.value}
            ctx.run = db.get_run(c, rid)
            res = NODES[step](ctx)
        run = db.get_run(c, rid)   # a step may have saved its own fields
        stubbed = step.value in ctx.scratch.get("stub_steps", [])
        # a gateless step (DIAGNOSE) reports its own failure via scratch, so it is never shown as passed
        status = res.status if res else CheckStatus(ctx.scratch.get("status") or (CheckStatus.NOT_RUN if stubbed else CheckStatus.PASSED))
        line = (ctx.scratch.get("headline") or ("This step isn't built yet." if stubbed
                else HEAD(step).replace("…", ".")))
        run.steps[step] = StepState(status=status, started_at=run.steps[step].started_at, finished_at=db.now(),
                                    attempt=1, headline=line)
        out: S = {}
        if ctx.scratch.get("end_reason"):
            out["end_reason"] = ctx.scratch["end_reason"]
        if res:
            run.gates[res.gate] = res.status; out["gates"] = {res.gate: res.status.value}
            db.emit(c, rid, "gate.result", step.value, run.revision, gate=res.gate, status=res.status.value,
                    reason=res.reason, evidence_ids=res.evidence_ids)
            if res.status in STOP_EARLY.get(res.gate, ()):
                out["end_reason"] = EndReason.RETRIES_EXHAUSTED.value
        db.save_run(c, run)
        db.emit(c, rid, "step.finished", step.value, run.revision, status=status.value, headline=line,
                evidence_ids=res.evidence_ids if res else [])
        return out
    return node


def _guided_pause(c, run, step: StepId) -> bool:
    """B15: True the first time we reach `step` after a step the user asked to pause after. The kv marker makes the
    re-entry after Continue skip the pause, so no step ever runs twice."""
    import json
    i = ORDER.index(step)
    prev = ORDER[i - 1].value if i else None
    key = f"guided:{run.run_id}:{run.revision}:{prev}"
    if not prev or prev not in json.loads(db.get_kv(c, f"pauses:{run.run_id}") or "[]") or db.get_kv(c, key):
        return False
    from backend.contracts.models import PauseInfo
    db.put_kv(c, key, db.now().isoformat())
    run.status, run.pause = RunStatus.PAUSED, PauseInfo(reason="guided_pause")
    db.save_run(c, run)
    db.emit(c, run.run_id, "run.paused", None, run.revision, reason="guided_pause", resume_at=None, after=prev)
    return True


def _wait_out_pause(c, rid: str, q, since: float, step: str = "") -> bool:
    """True = resume; False = paused too long (or user stopped). Polls every 60 s when the reset time is unknown."""
    import time
    from backend.config import limits
    from backend.contracts.models import PauseInfo
    run = db.get_run(c, rid)
    run.status, run.pause = RunStatus.PAUSED, PauseInfo(reason="provider_quota", provider=q.provider, resume_at=q.resume_at)
    db.save_run(c, run)
    db.emit(c, rid, "run.paused", None, run.revision, reason="provider_quota", resume_at=q.resume_at.isoformat() if q.resume_at else None)
    deadline = since + limits()["max_pause_seconds"]   # counted from the FIRST pause, not each retry
    while time.time() < deadline:
        if db.stop_requested(c, rid):
            return False
        wait = (q.resume_at - db.now()).total_seconds() if q.resume_at else 60
        if wait <= 0:
            break
        time.sleep(min(wait, 30))
        if not q.resume_at:
            break                                  # unknown reset: try again every minute
    else:
        return False
    run = db.get_run(c, rid); run.status, run.pause = RunStatus.RUNNING, None; db.save_run(c, run)
    db.emit(c, rid, "run.resumed", None, run.revision, from_step=step)
    return True


def HEAD(step: StepId) -> str:
    return HEADLINE_RUNNING[step]


def finish(state: S) -> S:
    c = db.connect(); run = db.get_run(c, state["run_id"])
    end = EndReason(state.get("end_reason") or EndReason.COMPLETED.value)
    gates = {k: CheckStatus(v) for k, v in run.gates.items()}
    capped = bool(run.supplyguard and run.supplyguard.status == CheckStatus.INCONCLUSIVE) or bool(run.baseline and run.baseline.partial)
    outcome = decide_outcome(gates, end, review_concerns=bool(run.review and run.review.lowers_readiness),
                             readiness_capped=capped, diagnosis_valid=run.diagnosis is not None,
                             stopped_during_diagnose=state.get("stopped_at") == StepId.DIAGNOSE.value)
    blockers = list(dict.fromkeys(end_blockers(end, outcome) + run.publish_blockers))
    status = status_after_analysis(outcome, blockers)
    if status == RunStatus.AWAITING_APPROVAL and PublishBlocker.NOT_APPROVED not in blockers:
        blockers.append(PublishBlocker.NOT_APPROVED)
    run.outcome, run.end_reason, run.readiness, run.status = outcome, end, readiness(outcome, capped=capped), status
    run.publish_blockers = blockers
    db.save_run(c, run)
    db.emit(c, run.run_id, "analysis.finished", None, run.revision, outcome=outcome.value, end_reason=end.value,
            readiness=run.readiness, publish_blockers=[b.value for b in blockers])
    return {}


def _route(nxt: str):
    return lambda state: "finish" if state.get("end_reason") else nxt


def build(ckpt_path: str | None = None):
    g = StateGraph(S)
    for st in ORDER:
        g.add_node(st.value, _step_node(st))
    g.add_node("finish", finish)
    g.add_edge(START, ORDER[0].value)
    for a, b in zip(ORDER, ORDER[1:] + [None]):
        g.add_conditional_edges(a.value, _route(b.value if b else "finish"), [b.value if b else "finish", "finish"])
    g.add_edge("finish", END)
    saver = SqliteSaver(sqlite3.connect(ckpt_path or str(ROOT / "data" / "checkpoints.db"), check_same_thread=False))
    return g.compile(checkpointer=saver)
