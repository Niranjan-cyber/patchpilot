from backend.contracts.hashing import canonical_diff, diff_hash, evidence_hash, evidence_manifest

A = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
T = "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -0,0 +1 @@\n+def test(): pass\n"


def test_order_and_line_endings_dont_change_the_hash():
    h = diff_hash(A + T)
    assert diff_hash(T + A) == h
    assert diff_hash((A + T).replace("\n", "\r\n")) == h


def test_content_change_changes_the_hash():
    assert diff_hash(A + T) != diff_hash(A.replace("x = 2", "x = 3") + T)


def test_canonical_diff_sorted_by_path():
    assert canonical_diff(T + A).index("src/a.py") < canonical_diff(T + A).index("tests/test_a.py")


def test_evidence_hash_tracks_supplyguard_report():
    base = dict(run_id="r", revision=0, base_sha="s", diff_hash="d", gates={"G5": "passed"}, outcome="VERIFIED_FIX",
                verify_evidence_ids=["e1"], baseline_evidence_ids=["e2"], repro_evidence_ids=["e3"],
                supplyguard_report_id="sg1", review_id=None)
    h1 = evidence_hash(evidence_manifest(**base))
    assert h1 == evidence_hash(evidence_manifest(**dict(reversed(list(base.items())))))   # key order irrelevant
    assert h1 != evidence_hash(evidence_manifest(**{**base, "supplyguard_report_id": "sg2"}))
