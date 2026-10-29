"""Dev only: seed a local run waiting for approval, owned by a fresh session. Prints TOKEN RUN_ID for browser checks."""
import hashlib
import secrets

from backend import artifacts, db
from backend.contracts.models import (CheckStatus, Diagnosis, IssueSpec, Location, Outcome, Patch, PublishBlocker, ReproTest,
                                      RunStatus, SGReport, TestRun, Verification)

FIX = ("diff --git a/tinycalc/ops.py b/tinycalc/ops.py\n--- a/tinycalc/ops.py\n+++ b/tinycalc/ops.py\n@@ -11,7 +11,4 @@ def subtract(a, b):\n"
       " def divide(a, b):\n-    try:\n-        return a / b\n-    except ZeroDivisionError:\n-        return 0\n+    return a / b\n")
TEST = ("diff --git a/tests/test_issue_1.py b/tests/test_issue_1.py\n--- /dev/null\n+++ b/tests/test_issue_1.py\n@@ -0,0 +1,7 @@\n"
        "+import pytest\n+\n+from tinycalc import divide\n+\n+\n+def test_divide_by_zero_raises():\n+    with pytest.raises(ZeroDivisionError):\n+        divide(1, 0)\n")
c = db.connect()
tok = secrets.token_urlsafe(32); h = hashlib.sha256(tok.encode()).hexdigest(); t = db.now().isoformat()
with db.tx(c):
    c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)", (h, None, t, t))
v = db.create_run(c, IssueSpec(html_url="https://github.com/pallets/click/issues/3888", repo="pallets/click", number=3888,
                               title="divide() returns 0 instead of raising (seeded sample)"), "2247b35e" * 5, owner_session_hash=h)
v.status, v.outcome, v.readiness = RunStatus.AWAITING_APPROVAL, Outcome.VERIFIED_FIX, "Ready for human review"
v.gates = {g: CheckStatus.PASSED for g in ("G1", "G2", "G3", "G4", "G5", "G6")}
v.publish_blockers = [PublishBlocker.NOT_APPROVED]
v.patch = Patch(fix_diff_id=artifacts.put(FIX), test_diff_id=artifacts.put(TEST), attempt=1, policy_result=CheckStatus.PASSED)
v.repro = ReproTest(test_diff_id=v.patch.test_diff_id, test_ids=["tests/test_issue_1.py::test_divide_by_zero_raises"],
                    expected_failure="DID NOT RAISE", runs_on_base=[CheckStatus.FAILED, CheckStatus.FAILED])
v.verify = Verification(new_test_runs=[CheckStatus.PASSED, CheckStatus.PASSED], container_id="seed")
v.baseline = TestRun(pass_set=["tests/test_ops.py::test_add"])
v.diagnosis = Diagnosis(locations=[Location(path="tinycalc/ops.py", line=12)],
                        hypothesis="divide() catches ZeroDivisionError and returns 0, hiding the error from callers.")
v.supplyguard = SGReport(report_id=artifacts.put("seed"), status=CheckStatus.PASSED)
db.save_run(c, v)
print(tok, v.run_id)
