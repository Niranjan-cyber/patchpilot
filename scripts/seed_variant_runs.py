"""Dev only: seed two finished runs for the B17 browser check (one fresh session). Prints TOKEN RUN_HIDDEN_FAIL RUN_CAP.
RUN_HIDDEN_FAIL: visible test passes, hidden variant fails -> Needs attention; bisect found (real pallets/click shas).
RUN_CAP: verified, hidden variant passed; bisect over the step cap -> Not run, no commit shown."""
import os
import hashlib
import json
import secrets

from backend import artifacts, db
from backend.contracts.models import (CheckStatus, Diagnosis, EndReason, IssueSpec, Location, Outcome, Patch, ReproTest,
                                      ReviewResult, RunStatus, StepId, StepState, Verification)

# dev seeds add fake runs AND queued jobs; the live worker would run them (2026-10-30: real setups on pallets/click)
assert os.getenv("PP_DB"), "set PP_DB to a separate test DB, never the live data/app.db (README: Tests)"

BAD, GOOD = "2247b35ea1c47c727d7a06e51fa280e12a863ff6", "9f0bcdf0d868edfc71435cd0aac2dcc08cf94828"
c = db.connect()
tok = secrets.token_urlsafe(32); h = hashlib.sha256(tok.encode()).hexdigest(); t = db.now().isoformat()
with db.tx(c):
    c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)", (h, None, t, t))
ids = []
for kind in ("hidden_fail", "cap"):
    v = db.create_run(c, IssueSpec(html_url="https://github.com/pallets/click/issues/3888", repo="pallets/click", number=3888,
                                   title=f"divide special-cases the test input (seeded sample, {kind})"), BAD, owner_session_hash=h)
    ev = artifacts.put(f"seed {kind}")
    v.repro = ReproTest(test_diff_id=ev, test_ids=["tests/test_patchpilot_issue_3888.py::t"], expected_failure="x",
                        runs_on_base=[CheckStatus.FAILED] * 2, evidence_ids=[ev])
    v.patch = Patch(fix_diff_id=artifacts.put(f"fix {kind}"), test_diff_id=ev, attempt=1, policy_result=CheckStatus.PASSED)
    v.diagnosis = Diagnosis(hypothesis="seeded", locations=[Location(path="src/click/types.py", line=454)], evidence_ids=[ev])
    hv = CheckStatus.FAILED if kind == "hidden_fail" else CheckStatus.PASSED
    v.verify = Verification(new_test_runs=[CheckStatus.PASSED] * 2, hidden_variant=hv)
    v.gates = {g: CheckStatus.PASSED for g in ("G1", "G2", "G3", "G4", "G5", "G6")}
    for s in StepId:
        v.steps[s] = StepState(status=CheckStatus.PASSED, headline="Done (seeded sample).")
    if kind == "hidden_fail":
        v.review = ReviewResult(concerns=[{"severity": "high", "text": "The fix passes the visible test but fails a hidden variant."}],
                                lowers_readiness=True)
        v.outcome, v.readiness = Outcome.FIX_NEEDS_ATTENTION, "Needs attention"
        bis = {"status": "found", "reason": "ok", "first_bad": BAD, "last_good": GOOD, "window": 32,
               "url": f"https://github.com/pallets/click/commit/{BAD}",
               "probes": [{"sha": GOOD, "result": "pass"}, {"sha": BAD, "result": "fail"}]}
    else:
        v.outcome, v.readiness = Outcome.VERIFIED_FIX, "Ready for human review"
        bis = {"status": "not_run", "reason": "step_cap", "first_bad": None, "last_good": None, "window": 32,
               "probes": [{"sha": GOOD, "result": "pass"}] + [{"sha": f"{i:040x}", "result": "fail"} for i in range(1, 6)]}
    v.status, v.end_reason = RunStatus.AWAITING_APPROVAL, EndReason.COMPLETED
    db.save_run(c, v)
    db.put_kv(c, f"bisect:{v.run_id}", json.dumps(bis))
    ids.append(v.run_id)
print(tok, *ids)
