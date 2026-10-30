import pytest

from backend import artifacts
from backend.api import approval
from backend.contracts.models import (Approval, CheckStatus, IssueSpec, Outcome, Owner, Patch, PublishBlocker, ReproTest,
                                      RunStatus, RunView, SGReport, TestRun, Verification)
from backend.publisher import publisher as P

FIX = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
TEST = "diff --git a/tests/test_a.py b/tests/test_a.py\n--- /dev/null\n+++ b/tests/test_a.py\n@@ -0,0 +1 @@\n+def test(): pass\n"


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(approval, "stale_checks", lambda v, d: [])
    t = __import__("backend.db", fromlist=["now"]).now()
    v = RunView(run_id="1234abcd-0000-4000-8000-000000000000", status=RunStatus.AWAITING_APPROVAL, outcome=Outcome.VERIFIED_FIX,
                issue=IssueSpec(html_url="https://github.com/up/proj/issues/7", repo="up/proj", number=7, title="bug"),
                base_sha="a" * 40, created_at=t, updated_at=t, gates={"G5": CheckStatus.PASSED},
                patch=Patch(fix_diff_id=artifacts.put(FIX), test_diff_id=artifacts.put(TEST), attempt=1, policy_result=CheckStatus.PASSED),
                repro=ReproTest(test_diff_id="x", test_ids=["tests/test_a.py::test"], expected_failure="e", runs_on_base=[CheckStatus.FAILED] * 2),
                verify=Verification(new_test_runs=[CheckStatus.PASSED] * 2), baseline=TestRun(pass_set=["t1", "t2"], fail_set=["t3"]),
                supplyguard=SGReport(report_id="sha256:" + "1" * 64, status=CheckStatus.PASSED))
    dh, eh = approval.hashes(v, approval.exact_diff(v))
    v.approval = Approval(run_id=v.run_id, revision=0, diff_hash=dh, evidence_hash=eh, approved_by=Owner(session_id_hash="s"),
                          approved_at=t, checklist={}, pr_title="Fix #7: bug", pr_summary="Raises now.")
    return v


class FakeGH:
    def __init__(self, push=False, existing=None, refuse=False):
        self.push, self.existing, self.refuse, self.calls = push, existing, refuse, []
    def login(self): return "alice"
    def can_push(self, repo): return self.push
    def ensure_fork(self, repo, login): self.calls.append("fork"); return f"{login}/proj"
    def push_branch(self, target, base_sha, upstream, branch, diff, msg): self.calls.append(("push", target, branch, diff))
    def find_pr(self, repo, head): return self.existing
    def create_pr(self, repo, head, base, title, body):
        self.calls.append(("create", head, body)); return None if self.refuse else {"html_url": "https://github.com/up/proj/pull/9", "number": 9}
    def update_pr(self, repo, n, title, body): self.calls.append(("update", n)); return {"html_url": f"https://github.com/up/proj/pull/{n}", "number": n}


def test_fork_flow_opens_one_draft_pr(run):
    gh = FakeGH()
    r = P.publish(run, gh, "main")
    assert r.status == "created" and r.pr.fork_owner == "alice" and r.pr.number == 9
    assert "fork" in gh.calls and ("push", "alice/proj", "patchpilot/issue-7-1234abcd", approval.exact_diff(run)) in gh.calls


def test_direct_flow_when_user_can_push(run):
    gh = FakeGH(push=True)
    r = P.publish(run, gh, "main")
    assert r.pr.fork_owner is None and "fork" not in gh.calls


def test_republish_updates_same_pr(run):
    gh = FakeGH(existing={"number": 9})
    r = P.publish(run, gh, "main")
    assert r.status == "updated" and not any(c[0] == "create" for c in gh.calls if isinstance(c, tuple))


def test_refused_pr_falls_back_to_compare_link(run):
    r = P.publish(run, FakeGH(refuse=True), "main")
    assert r.status == "branch_only" and r.pr.compare_url.startswith("https://github.com/up/proj/compare/main...alice:")


def test_body_has_evidence_and_ai_note(run):
    body = P.pr_body(run)
    assert "Fixes #7" in body and "fails 2/2 on the original code" in body and P.AI_NOTE in body
    assert "2 existing tests passed before" in body and "1 were already failing" in body


@pytest.mark.parametrize("mutate,code", [
    (lambda v: setattr(v, "approval", None), "APPROVAL_STALE"),
    (lambda v: setattr(v, "revision", 1), "APPROVAL_STALE"),
    (lambda v: setattr(v.supplyguard, "report_id", "sha256:" + "2" * 64), "HASH_MISMATCH"),
    (lambda v: v.publish_blockers.append(PublishBlocker.DEPS_INCONCLUSIVE), "PUBLISH_BLOCKED"),
])
def test_refuses_without_publishing(run, mutate, code):
    mutate(run); gh = FakeGH()
    with pytest.raises(P.PublishRefused) as e:
        P.publish(run, gh, "main")
    assert e.value.code == code and gh.calls == []


def test_api_failure_after_push_is_branch_only_not_nothing(run):
    gh = FakeGH()
    gh.create_pr = lambda *a: (_ for _ in ()).throw(RuntimeError("502"))
    r = P.publish(run, gh, "main")
    assert r.status == "branch_only" and r.pr.compare_url and any(c[0] == "push" for c in gh.calls if isinstance(c, tuple))


def test_token_never_in_git_argv(monkeypatch):
    seen = []
    class Done:
        stdout = b""
    def fake_run(argv, **kw):
        seen.append((argv, kw["env"])); return Done()
    monkeypatch.setattr(P.subprocess, "run", fake_run)
    P.GitHubWriter("gho_TOPSECRET").push_branch("me/proj", "a" * 40, "up/proj", "b", "diff", "m")
    assert seen and all("TOPSECRET" not in " ".join(a) and "Authorization" not in " ".join(a) for a, _ in seen)
    assert all(env["GIT_CONFIG_KEY_0"] == "http.extraHeader" for _, env in seen)
    push = [a for a, _ in seen if "push" in a][0]
    assert any(x.startswith("--force-with-lease=refs/heads/b:") for x in push)


def test_the_diff_reaches_git_apply_as_bytes(monkeypatch):
    # Windows: text-mode stdin turns \n into \r\n, so `git apply` saw a CRLF diff and failed (first live publish)
    seen = []
    class Done:
        stdout = b""
    def fake_run(argv, **kw):
        seen.append((argv, kw)); return Done()
    monkeypatch.setattr(P.subprocess, "run", fake_run)
    P.GitHubWriter("gho_x").push_branch("me/proj", "a" * 40, "up/proj", "b", "line1\nline2\n", "m")
    apply = [kw for a, kw in seen if "apply" in a][0]
    assert apply["input"] == b"line1\nline2\n" and not apply.get("text")
