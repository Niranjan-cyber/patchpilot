"""B14: eval comparison on recorded results (verified claims vs the official tests)."""
from backend.eval import summarize, verdict


def case(i, outcome, official, seconds=60.0):
    return {"id": f"c{i}", "kind": "planted", "issue_url": f"https://github.com/o/r/issues/{i}",
            "outcome": outcome, "official": official, "seconds": seconds}


def test_verdicts():
    assert verdict(case(1, "VERIFIED_FIX", "pass")) == "confirmed"
    assert verdict(case(1, "VERIFIED_FIX", "fail")) == "false_verified"
    assert verdict(case(1, "VERIFIED_FIX", None)) == "unconfirmed"    # unknown is never a pass
    assert verdict(case(1, "TRIAGE_ONLY", "fail")) == "no_claim"
    assert verdict(case(1, "FIX_NEEDS_ATTENTION", "pass")) == "no_claim"
    assert verdict(case(1, None, None)) == "no_result"


def test_unknown_official_values_are_unknown_not_pass():
    for junk in ("", "PASSED", "maybe", 1, True):
        assert verdict(case(1, "VERIFIED_FIX", junk)) == "unconfirmed"


def test_false_verified_listed_first_and_counted():
    s = summarize({"cases": [case(1, "VERIFIED_FIX", "pass"), case(2, "TRIAGE_ONLY", None),
                             case(3, "VERIFIED_FIX", "fail"), case(4, "CANNOT_REPRODUCE", None)]})
    assert [r["id"] for r in s["rows"]][0] == "c3"
    assert s["rows"][0]["verdict"] == "false_verified"
    n = s["counts"]
    assert (n["total"], n["verified"], n["confirmed"], n["false_verified"], n["triage"], n["unable"]) == (4, 2, 1, 1, 1, 1)
    assert s["state"] == "success"


def test_states():
    assert summarize({"cases": []})["state"] == "failed"
    assert summarize({"cases": [case(1, None, None)]})["state"] == "failed"
    assert summarize({"cases": [case(1, "VERIFIED_FIX", "pass"), case(2, None, None)]})["state"] == "partial"
    assert summarize({"cases": [case(1, "VERIFIED_FIX", None)]})["state"] == "partial"   # claim not checked yet


def test_missing_time_stays_none():
    s = summarize({"cases": [case(1, "TRIAGE_ONLY", None, seconds=None)]})
    assert s["rows"][0]["seconds"] is None and s["counts"]["median_seconds"] is None


def test_official_result_from_pytest_ra():
    from backend.eval import official_result, parse_ra
    st = parse_ra("PASSED tests/a.py::t1\nFAILED tests/a.py::T::t2 - assert 0\nERROR tests/b.py::t3\nnoise PASSED x\n")
    assert st == {"tests/a.py::t1": "PASSED", "tests/a.py::T::t2": "FAILED", "tests/b.py::t3": "ERROR"}
    assert official_result(["tests/a.py::t1"], [], st) == "pass"
    assert official_result(["tests/a.py::t1"], ["tests/a.py::T::t2"], st) == "fail"     # a regression fails too
    assert official_result(["tests/b.py::t3"], [], st) == "fail"
    assert official_result(["tests/a.py::t1", "tests/missing.py::t"], [], st) is None   # not seen = unknown
    assert official_result([], [], st) is None


def test_api_eval_not_run_and_results(tmp_path, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from backend.api import main
    monkeypatch.setattr(main, "EVAL_RESULTS", tmp_path / "results.json")
    c = TestClient(main.app)
    r = c.get("/api/eval")
    assert r.status_code == 404 and r.json()["code"] == "EVAL_NOT_RUN"   # no numbers before a real run
    (tmp_path / "results.json").write_text(json.dumps({"cases": [case(1, "VERIFIED_FIX", "pass"), case(2, "VERIFIED_FIX", "fail")]}))
    s = c.get("/api/eval").json()
    assert s["rows"][0]["verdict"] == "false_verified" and s["counts"]["false_verified"] == 1
    (tmp_path / "results.json").write_text("{not json")
    assert c.get("/api/eval").status_code == 500
