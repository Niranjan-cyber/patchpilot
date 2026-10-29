import json
from pathlib import Path
import pytest
from backend.contracts.models import Event, RunView

WANT = {  # case: (status, outcome)
    "verified_fix": ("awaiting_approval", "VERIFIED_FIX"),
    "needs_attention_deps_inconclusive": ("awaiting_approval", "FIX_NEEDS_ATTENTION"),
    "triage_only": ("finished", "TRIAGE_ONLY"), "cannot_reproduce": ("finished", "CANNOT_REPRODUCE"),
    "env_failed": ("finished", "ENV_FAILED"), "blocked": ("finished", "BLOCKED"),
    "paused_quota_unknown_reset": ("paused", None), "pause_timeout": ("finished", "STOPPED"),
    "interrupted_then_resumed": ("running", None), "stopped_during_setup": ("finished", "STOPPED"),
    "stopped_after_verify": ("finished", "FIX_NEEDS_ATTENTION"), "upstream_changed": ("finished", "VERIFIED_FIX"),
    "published_fork": ("published", "VERIFIED_FIX"), "publish_branch_only": ("published", "VERIFIED_FIX"),
    "details_expired": ("finished", "VERIFIED_FIX"),
}
ROOT = Path("fixtures/runs")

@pytest.mark.parametrize("case", sorted(WANT))
def test_fixture_valid(case):
    v = RunView.model_validate_json((ROOT / case / "state.json").read_text())
    assert (v.status.value, v.outcome.value if v.outcome else None) == WANT[case]
    seqs = [Event.model_validate_json(l).seq for l in (ROOT / case / "events.jsonl").read_text().splitlines()]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)

def test_paused_has_no_guessed_resume_time():
    v = RunView.model_validate_json((ROOT / "paused_quota_unknown_reset" / "state.json").read_text())
    assert v.pause and v.pause.resume_at is None

def test_stopped_after_verify_not_publishable():
    v = RunView.model_validate_json((ROOT / "stopped_after_verify" / "state.json").read_text())
    assert "run_stopped" in [b.value for b in v.publish_blockers]
