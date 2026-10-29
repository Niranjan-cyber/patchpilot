"""OAuth code → token exchange + encryption live here, next to the only code that may use the token (C review #9)."""
import os

import httpx

from backend.publisher import tokens


def exchange(code: str, redirect_uri: str) -> tuple[dict, str, str]:
    """Returns (github user, encrypted token, scopes). Raises on any GitHub error (caller shows a friendly message)."""
    tok = httpx.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, timeout=15,
                     data={"client_id": os.environ["GITHUB_OAUTH_CLIENT_ID"], "client_secret": os.environ["GITHUB_OAUTH_CLIENT_SECRET"],
                           "code": code, "redirect_uri": redirect_uri}).json()
    access = tok["access_token"]
    user = httpx.get("https://api.github.com/user", timeout=15, headers={"Authorization": f"Bearer {access}"}).json()
    _ = user["id"], user["login"]      # validate inside the caller's try (C review #6)
    return user, tokens.encrypt(access), tok.get("scope", "")
