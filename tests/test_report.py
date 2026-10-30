import pytest
from fastapi.testclient import TestClient

from backend.api import main
from backend.contracts.models import RunView

c = TestClient(main.app)
CASES = ["verified_fix", "triage_only", "cannot_reproduce", "env_failed", "blocked", "stopped_during_setup",
         "needs_attention_deps_inconclusive", "paused_quota_unknown_reset"]


@pytest.mark.parametrize("case", CASES)
def test_report_statuses_match_recorded_gates(case):
    r = c.get(f"/api/runs/{case}/report.md")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    v = RunView.model_validate(c.get(f"/api/runs/{case}").json())
    from backend.report import GATES, WORD
    for k, name in GATES[:-1]:
        want = WORD[v.gates[k]] if k in v.gates else "not run"
        assert f"| {name} | {want} |" in r.text, (case, k)


def test_inconclusive_is_never_reported_clean():
    t = c.get("/api/runs/needs_attention_deps_inconclusive/report.md").text
    assert "Status: inconclusive" in t and "unknown, not passed" in t


def test_report_is_owner_scoped_for_real_runs():
    assert c.get("/api/runs/00000000-0000-4000-8000-000000000000/report.md").status_code == 404

def test_unfinished_dependency_scan_is_never_reported_as_none_or_zero():   # #29 (run 11 said "none" and "0")
    import json
    from pathlib import Path
    from backend.contracts.models import CheckStatus, SGReport
    from backend.report import render
    v = RunView.model_validate(json.loads(Path("fixtures/runs/needs_attention_deps_inconclusive/state.json").read_text(encoding="utf-8")))
    v.supplyguard = SGReport(report_id="sha256:" + "0" * 64, status=CheckStatus.INCONCLUSIVE, failures=["supplyguard_unavailable"])
    t = render(v)
    assert "Suspicious packages: unknown" in t and "Known vulnerabilities: unknown" in t
    assert "Suspicious packages: none" not in t and "Known vulnerabilities: 0" not in t
    v.supplyguard = SGReport(report_id="sha256:" + "0" * 64, status=CheckStatus.INCONCLUSIVE, failures=["OSV lookup timed out"],
                             findings=[{"type": "vulnerability", "package": "x", "id": "CVE-1"}])
    t = render(v)
    assert "Known vulnerabilities: at least 1" in t and "none found before the check stopped" in t
    v.supplyguard = SGReport(report_id="sha256:" + "0" * 64, status=CheckStatus.PASSED)
    t = render(v)
    assert "Suspicious packages: none" in t and "Known vulnerabilities: 0 " in t   # a finished clean scan still says so
