import logging

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend import db
from backend.api import auth, main
from backend.contracts.models import IssueSpec, RepoPolicy
from backend.github.reader import IssueCheck

URL = "https://github.com/o/r/issues/1"


class R:
    def __init__(self, j): self._j = j
    def json(self): return self._j


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid"); monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "sec")
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    chk = IssueCheck(issue=IssueSpec(html_url=URL, repo="o/r", number=1, title="t"), base_sha="abc", default_branch="main",
                     language="Python", policy=RepoPolicy(), fetched_at=db.now())
    monkeypatch.setattr(main, "check_issue", lambda url: chk)
    from backend.publisher import oauth
    user = {"id": 42, "login": "alice"}
    monkeypatch.setattr(oauth.httpx, "post", lambda *a, **k: R({"access_token": "gho_SECRET", "scope": "public_repo"}))
    monkeypatch.setattr(oauth.httpx, "get", lambda *a, **k: R(dict(user)))
    monkeypatch.setattr(auth, "_user", user, raising=False)
    return TestClient(main.app, base_url="https://testserver", follow_redirects=False)


def sign_in(b, run=""):
    r = b.get(f"/auth/github/start?run={run}")
    assert r.status_code == 303 and r.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    assert "scope=public_repo" in r.headers["location"]
    state = b.cookies.get("pp_oauth", path="/auth").split(":")[0]
    return b.get(f"/auth/github/callback?code=abc&state={state}")


def test_sign_in_claims_runs_and_encrypts_token(env):
    b = env
    rid = b.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    r = sign_in(b, rid)
    assert r.status_code == 303 and "signed_in=1" in r.headers["location"]
    assert b.get("/api/me").json()["login"] == "alice"
    row = db.connect().execute("SELECT token_enc FROM accounts").fetchone()
    assert row and "gho_SECRET" not in row[0]
    assert db.connect().execute("SELECT owner_account_id FROM runs WHERE run_id=?", (rid,)).fetchone()[0] is not None


def test_forged_state_rejected(env):
    b = env
    b.get("/auth/github/start")
    r = b.get("/auth/github/callback?code=abc&state=forged")
    assert "error=state" in r.headers["location"] and db.connect().execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0


def test_publish_requires_sign_in(env):
    b = env
    rid = b.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    r = b.post(f"/api/runs/{rid}/publish")
    assert r.status_code == 401 and r.json()["code"] == "AUTH_REQUIRED"


def test_not_configured_redirects_honestly(env, monkeypatch):
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID")
    r = env.get("/auth/github/start?run=x")
    assert "error=not_configured" in r.headers["location"]


def test_oauth_callback_never_logged():
    rec = logging.LogRecord("uvicorn.access", 20, "", 0, '%s - "%s %s"', ("1.2.3.4", "GET", "/auth/github/callback?code=SECRET&state=x"), None)
    assert main._NoSecrets().filter(rec) is False


def test_second_account_on_shared_browser_cannot_take_first_accounts_runs(env, monkeypatch):
    b = env
    rid = b.post("/api/runs", json={"issue_url": URL}).json()["run_id"]
    sign_in(b, rid)                                   # alice claims it
    auth._user.update(id=43, login="bob")             # bob signs in on the same browser
    sign_in(b)
    assert db.connect().execute("SELECT a.login FROM runs r JOIN accounts a ON a.id=r.owner_account_id WHERE run_id=?",
                                (rid,)).fetchone()[0] == "alice"
    assert b.get(f"/api/runs/{rid}").status_code == 404


def test_github_user_error_is_friendly_not_500(env, monkeypatch):
    from backend.publisher import oauth
    monkeypatch.setattr(oauth.httpx, "get", lambda *a, **k: R({"message": "Bad credentials"}))
    b = env
    b.get("/auth/github/start")
    state = b.cookies.get("pp_oauth", path="/auth").split(":")[0]
    r = b.get(f"/auth/github/callback?code=abc&state={state}")
    assert r.status_code == 303 and "error=github" in r.headers["location"]
