import pytest

from backend import artifacts
from backend.api import approval
from backend.contracts.models import (Approval, CheckStatus, ConsentEvidence, OwnershipAnswers, IssueSpec, Outcome, Owner, Patch, PublishBlocker, ReproTest,
                                      RunStatus, RunView, SGReport, TestRun, Verification)
from backend.publisher import publisher as P

FIX = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
TEST = "diff --git a/tests/test_a.py b/tests/test_a.py\n--- /dev/null\n+++ b/tests/test_a.py\n@@ -0,0 +1 @@\n+def test(): pass\n"


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setattr(approval, "stale_checks", lambda v, d: [])
    monkeypatch.setattr(__import__("backend.db", fromlist=["x"]), "DB_PATH", str(tmp_path / "app.db"))   # pr_body reads kv
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
                          approved_at=t, checklist={}, pr_title="Fix #7: bug", pr_summary="Raises now.",
                          ownership=OwnershipAnswers(what_was_broken="x = 1 was wrong for this case", why_this_fix="Setting x = 2 fixes the case",
                                                     what_the_test_proves="It fails before and passes after"))
    v.consent = ConsentEvidence(kind="maintainer_reply", source_url="https://github.com/up/proj/issues/7#issuecomment-2",
                                author="maint", author_association="OWNER", quote="Yes please", recorded_at=t)
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
    def comment(self, repo, n, body): self.calls.append(("comment", repo, n, body)); return {"html_url": f"https://github.com/{repo}/issues/{n}#issuecomment-1"}
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


def test_body_has_labels_evidence_and_ai_note(run):
    body = P.pr_body(run)
    # #70 item 5: bold labels in this order, no headings (mcstatus #1238: the long body read as vibe-coding)
    labels = ["**Problem:**", "**Cause:**", "**Fix:**", "**Tests:**", "**Limitations:**", "**AI assistance:**", "<details>"]
    assert [body.index(x) for x in labels] == sorted(body.index(x) for x in labels) and "## " not in body
    assert "Fixes #7" in body and "**Problem:** bug" in body and "**Cause:** Raises now." in body
    assert "**Fix:** changes `src/a.py` (+1 −1)." in body   # counted from the fix diff, not the test diff
    assert "fails 2/2 on the original code" in body and P.AI_NOTE in body
    assert "2 existing tests passed before" in body and "1 were already failing" in body
    assert "own linters and type checkers were not checked" in body   # no rows stored: never implied as passed
    assert "A maintainer agreed to a pull request [on the issue](https://github.com/up/proj/issues/7#issuecomment-2)." in body


def test_body_names_the_repo_checks_that_ran_and_did_not(run):
    import json
    from backend import db
    db.put_kv(db.connect(), f"repo_checks:{run.run_id}", json.dumps({"checks": [
        {"tool": "ruff check", "status": "PASS"}, {"tool": "mypy", "status": "FAIL"},
        {"tool": "flake8", "status": "NOT_RUN"}, {"tool": "pre-commit: codespell", "status": "UNSUPPORTED"}], "files": [], "reason": None}))
    run.repro.uncovered = ["works for uppercase schemes"]
    body = P.pr_body(run)
    assert "run on the changed files: ruff check (no new problems), mypy (new problems)." in body
    assert "Not run here: flake8, pre-commit: codespell; please check them in CI." in body
    assert "The test doesn't claim to check: works for uppercase schemes." in body


@pytest.mark.parametrize("kind", ["user_override", "contributing_invites"])
def test_body_never_claims_a_maintainer_asked_without_their_words(run, kind):
    run.consent = run.consent.model_copy(update={"kind": kind, "override_reason": "The maintainer said yes on Discord, link lost"})
    body = P.pr_body(run)
    assert "maintainer agreed" not in body and "Discord" not in body


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


def test_ask_comment_is_short_and_asks_before_any_pr(run):
    # human decision 2026-11-09 after mcstatus #1238: ask the maintainer first, open the PR only on a yes
    body = P.ask_comment(run)
    assert "Raises now." in body and "only open one if you say yes" in body and P.ASK_NOTE in body
    assert "2 existing tests still pass" in body and len(body) < 1000 and "<details>" not in body


def test_ask_posts_one_comment_after_the_same_checks(run):
    gh = FakeGH()
    assert P.ask(run, gh, "Would you like a PR?").endswith("#issuecomment-1")
    assert gh.calls == [("comment", "up/proj", 7, "Would you like a PR?")]   # no fork, no branch, no PR
    run.revision = 1   # approval no longer matches: nothing is posted
    gh = FakeGH()
    with pytest.raises(P.PublishRefused):
        P.ask(run, gh, "Would you like a PR?")
    assert gh.calls == []


def test_no_pr_without_consent_but_the_ask_still_works(run):
    # contracts v0.5 §2.2 (human decision 2026-11-09): publishing needs recorded consent; asking is how you get it
    run.consent = None
    run.publish_blockers.append(PublishBlocker.NO_MAINTAINER_CONSENT)
    gh = FakeGH()
    with pytest.raises(P.PublishRefused) as e:
        P.publish(run, gh, "main")
    assert e.value.code == "PUBLISH_BLOCKED" and gh.calls == []
    assert P.ask(run, gh, "Would you like a PR?").endswith("#issuecomment-1")


def test_override_is_never_written_into_the_pr_body(run):
    run.consent = ConsentEvidence(kind="user_override", override_reason="The maintainer asked me on Discord to send it.",
                                  recorded_at=run.created_at)
    assert "Discord" not in P.pr_body(run) and "maintainer asked" not in P.pr_body(run).lower()


def test_old_approval_without_answers_cannot_publish_and_answers_stay_out_of_the_pr(run):
    assert "fails before and passes after" not in P.pr_body(run)   # stored with the approval and the report only
    run.approval.ownership = None
    gh = FakeGH()
    with pytest.raises(P.PublishRefused) as e:
        P.publish(run, gh, "main")
    assert e.value.code == "APPROVAL_STALE" and gh.calls == []


def test_the_problem_line_is_the_issue_title_never_model_text(run):
    # A's review of #83: every word published under the user's name is text they saw (the PR title holds the issue title)
    from backend.contracts.models import IssueAssessment
    run.assessment = IssueAssessment(issue_type="bug", issue_type_source="model", issue_status="open", compatibility_status="supported",
                                     handling_decision="READY", problem_summary="@org/team please merge [this](http://evil)")
    body = P.pr_body(run)
    assert "evil" not in body and "@org/team" not in body and f"**Problem:** {run.issue.title}" in body


@pytest.mark.parametrize("stored", ['{"checks": [{"name": "ruff", "status": "PASS"}]}', '{"checks": ["ruff"]}', '{"checks": 3}', "not json"])
def test_a_malformed_repo_check_record_reads_as_not_checked(run, stored):
    from backend import db
    db.put_kv(db.connect(), f"repo_checks:{run.run_id}", stored)
    assert "own linters and type checkers were not checked" in P.pr_body(run)


def test_fix_counts_lines_that_start_with_dashes_or_pluses():
    diff = ("diff --git a/docs/x.md b/docs/x.md\n--- a/docs/x.md\n+++ b/docs/x.md\n@@ -1,2 +1,2 @@\n----\n+++heading\n"
            " keep\n")
    assert P._changed(diff) == ["`docs/x.md` (+1 −1)"]
