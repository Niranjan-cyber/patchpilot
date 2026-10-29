"""DIAGNOSE (B07): the Investigator reads the code next to the failing test and cites real files, lines and evidence IDs.
Code checks every citation (contracts §1.1); invalid twice -> the run ends TRIAGE_ONLY with "diagnosis unavailable"."""
import shlex
import uuid

from backend import artifacts, db
from backend.agents import loop
from backend.contracts.models import Diagnosis, Location, TourItem
from backend.gates.diff_policy import check_diagnosis
from backend.llm_gateway import BudgetExceeded, QuotaPause
from backend.sandbox import docker
from backend.sandbox.steps import image, snap
from backend.worker.nodes import StepContext


def evidence_menu(run) -> dict[str, str]:
    """Evidence IDs the Investigator may cite, with what each one is."""
    menu = {}
    if run.repro:
        for i, e in enumerate(run.repro.evidence_ids):
            menu[e] = ["test designer transcript", "reproduction test diff", "failing test run 1", "failing test run 2"][i] \
                if i < 4 else "reproduction evidence"
    if run.baseline:
        for e in run.baseline.evidence_ids:
            menu[e] = "baseline test run"
    return menu


def task_prompt(run, menu: dict[str, str], failing: str, previous: str | None) -> str:
    i = run.issue
    tests = ", ".join(run.repro.test_ids) if run.repro else "(none)"
    ev = "\n".join(f"- {k}: {v}" for k, v in menu.items())
    return f"""Find the cause of this bug. Do NOT edit any file; only read (cat, grep, sed -n, git log).

Issue #{i.number}: {i.title}
Expected: {i.expected or "(not stated)"}
Actual: {i.actual or "(not stated)"}

The new test {tests} fails on the current code. Its output (end):
{failing[-3000:]}

Evidence you may cite (use these exact IDs, no others):
{ev}

When done, run: echo {loop.DONE} '<one line of JSON>' with this shape:
{{"hypothesis": "<2-3 plain sentences a first-time contributor understands>",
  "locations": [{{"path": "<repo-relative file>", "line": <line number>}}],
  "tour": [{{"path": "<file>", "why": "<one line: why this file matters>"}}],
  "evidence_ids": ["<ids from the list above that support the hypothesis>"]}}
Cite 1-3 locations and 2-5 tour files. Paths are relative to /src.
{"Your previous answer was rejected: " + previous if previous else ""}"""


def _bisect_once(ctx: StepContext) -> None:
    """B17 / S6: which commit introduced the bug (once per run; a re-diagnosis doesn't repeat it). Never blocks DIAGNOSE."""
    from backend.agents.bisect import run_bisect
    run = ctx.run
    if not run.repro or db.get_kv(db.connect(), f"bisect:{ctx.run_id}"):
        return
    ctx.emit("step.progress", "diagnose", message="Looking for the commit that introduced the bug (up to 6 test runs)…")
    try:
        res = run_bisect(run, (artifacts.get(run.repro.test_diff_id) or b"").decode("utf-8", "replace"))
        ctx.emit("step.progress", "diagnose", message=f"Commit search: {res['status']} ({res['reason']}).")
    except Exception as e:
        import json
        db.put_kv(db.connect(), f"bisect:{ctx.run_id}", json.dumps({"status": "not_run", "reason": f"error: {type(e).__name__}",
                                                                    "first_bad": None, "last_good": None, "probes": [], "window": 0}))


def diagnose(ctx: StepContext):
    rid, run = ctx.run_id, ctx.run
    _bisect_once(ctx)
    menu = evidence_menu(run)
    failing = (artifacts.get(run.repro.evidence_ids[2]) or b"").decode("utf-8", "replace") if run.repro and len(run.repro.evidence_ids) > 2 else ""
    previous = None
    for attempt in (1, 2):   # contracts: one Investigator retry
        name = f"pp-{rid[:8]}-inv-{attempt}-{uuid.uuid4().hex[:4]}"
        if docker.start(image(rid), name, snap(rid)).code:
            raise RuntimeError("could not start the agent sandbox")
        try:
            ex = lambda cmd: (lambda r: (r.code, r.out))(docker.exec_(name, cmd, timeout=120))
            try:
                res, transcript = loop.run(task_prompt(run, menu, failing, previous), exec_=ex, run_id=rid, role="investigator",
                                           on_step=lambda s, cmd: ctx.emit("step.progress", "diagnose", message=f"Step {s + 1}: {cmd[:120]}"))
            except QuotaPause as q:
                ctx.scratch["pause"] = q
                ctx.scratch["headline"] = "Paused: the free AI capacity is used up for now."
                return None
            except BudgetExceeded as b:
                ctx.scratch.update(end_reason="token_limit", status="not_run", headline=f"Stopped: the {b.scope} AI budget is used up.")
                return None

            def line_count(path: str) -> int | None:
                r = docker.exec_(name, f"test -f {shlex.quote(path)} && awk 'END{{print NR}}' {shlex.quote(path)}", timeout=20)
                return int(r.out.strip()) if r.code == 0 and r.out.strip().isdigit() else None
            why = check_diagnosis(res, set(menu), line_count)
        finally:
            docker.rm(name)
        tid = artifacts.put("\n\n".join(f"[{m['role']}]\n{m['content']}" for m in transcript))
        if why is None:
            run = db.get_run(db.connect(), rid)
            run.diagnosis = Diagnosis(
                hypothesis=str(res["hypothesis"]).strip()[:1200],
                locations=[Location(path=l["path"], line=l.get("line")) for l in res["locations"][:3]],
                tour=[TourItem(path=str(t.get("path", "")), why=str(t.get("why", ""))[:200])
                      for t in (res.get("tour") or [])[:5] if isinstance(t, dict) and t.get("path")],
                evidence_ids=[*res["evidence_ids"], tid])
            db.save_run(db.connect(), run)
            ctx.scratch["headline"] = f"Likely cause found in {run.diagnosis.locations[0].path}."
            return None
        previous = {"unknown_evidence_id": "you cited an evidence ID that isn't in the list.",
                    "unknown_file": "a location points to a file that doesn't exist.",
                    "line_out_of_range": "a location's line number is past the end of the file.",
                    }.get(why, f"'{why}': follow the JSON shape exactly.")
        ctx.emit("attempt.retry", "diagnose", role="investigator", attempt=attempt, max=2, reason=why, evidence_ids=[tid])
    # contracts §1.1: still invalid after one retry -> analysis ends (retries_exhausted) as TRIAGE_ONLY, diagnosis unavailable
    ctx.scratch.update(end_reason="retries_exhausted", status="failed",
                       headline="We couldn't pin down the cause with evidence we could check, so the diagnosis is unavailable.")
    return None
