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
