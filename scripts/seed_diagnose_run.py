"""Dev only: seed two local runs for the B07 browser check (owned by one fresh session). Prints TOKEN RUN_OK RUN_TRIAGE.
RUN_OK is fixing with a diagnosis + one G4-rejected Fixer attempt; RUN_TRIAGE ended TRIAGE_ONLY with diagnosis unavailable."""
import hashlib
import secrets

from backend import artifacts, db
from backend.contracts.models import (CheckStatus, Diagnosis, EndReason, IssueSpec, Location, Outcome, ReproTest, RunStatus,
                                      StepId, StepState, TourItem)

SHA = "2247b35ea1c47c727d7a06e51fa280e12a863ff6"   # pallets/click main when seeded, so the file:line links open real code
c = db.connect()
tok = secrets.token_urlsafe(32); h = hashlib.sha256(tok.encode()).hexdigest(); t = db.now().isoformat()
with db.tx(c):
    c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)", (h, None, t, t))
ids = []
for kind in ("ok", "triage"):
    v = db.create_run(c, IssueSpec(html_url="https://github.com/pallets/click/issues/3888", repo="pallets/click", number=3888,
                                   title=f"Choice shows the wrong error for a bad value (seeded sample, {kind})"), SHA, owner_session_hash=h)
    ev = [artifacts.put(f"seeded transcript {kind}"), artifacts.put("seeded test diff"),
          artifacts.put("FAILED tests/test_patchpilot_issue_3888.py::test_choice_error - AssertionError (seeded)"), artifacts.put("run 2")]
    v.repro = ReproTest(test_diff_id=ev[1], test_ids=["tests/test_patchpilot_issue_3888.py::test_choice_error"],
                        expected_failure="AssertionError", runs_on_base=[CheckStatus.FAILED] * 2, evidence_ids=ev)
    v.gates = {"G1": CheckStatus.PASSED, "G2": CheckStatus.PASSED, "G3": CheckStatus.PASSED}
    for s in (StepId.PREFLIGHT, StepId.SETUP, StepId.BASELINE, StepId.REPRODUCE):
        v.steps[s] = StepState(status=CheckStatus.PASSED, headline="Done (seeded sample).")
    if kind == "ok":
        v.status = RunStatus.RUNNING
        v.diagnosis = Diagnosis(
            hypothesis="Choice.convert builds its error message from the normalized value instead of what the user typed, "
                       "so the message names a value the user never entered.",
            locations=[Location(path="src/click/types.py", line=454)],
            tour=[TourItem(path="src/click/types.py", why="Choice and its convert() method live here"),
                  TourItem(path="src/click/core.py", why="Parameters call convert() while parsing the command line"),
                  TourItem(path="tests/test_basic.py", why="Existing tests for choice options, to see expected messages")],
            evidence_ids=[ev[2], ev[0]])
        v.steps[StepId.DIAGNOSE] = StepState(status=CheckStatus.PASSED, headline="Likely cause found in src/click/types.py.")
        v.steps[StepId.FIX] = StepState(status="running", headline="Writing a small fix…")
        db.save_run(c, v)
        bad = artifacts.put("diff --git a/tests/test_basic.py b/tests/test_basic.py\n(seeded rejected diff)\n")
        db.emit(c, v.run_id, "attempt.retry", "fix", role="fixer", attempt=1, max=4, reason="edits_tests",
                evidence_ids=[artifacts.put("seeded fixer transcript"), bad])
    else:
        v.status, v.outcome, v.end_reason, v.readiness = RunStatus.FINISHED, Outcome.TRIAGE_ONLY, EndReason.RETRIES_EXHAUSTED, "Unable to verify a fix"
        v.steps[StepId.DIAGNOSE] = StepState(status=CheckStatus.FAILED, headline="We couldn't pin down the cause with evidence we "
                                             "could check, so the diagnosis is unavailable.")
        db.save_run(c, v)
        for a in (1, 2):
            db.emit(c, v.run_id, "attempt.retry", "diagnose", role="investigator", attempt=a, max=2, reason="unknown_evidence_id",
                    evidence_ids=[artifacts.put(f"seeded investigator transcript {a}")])
    ids.append(v.run_id)
print(tok, *ids)
