"""B17 / S6: which commit introduced the bug. Host-side `git bisect run` with the reproduction test, step-capped.
Probes run in fresh hardened containers (the run's image, editable install), each on a tarball of that commit.
Over the cap, no passing commit in range, or a probe we can't read -> not_run / inconclusive. Never a guessed commit."""
import json
import re
import shutil
import uuid

import httpx

from backend import db
from backend.sandbox import docker
from backend.sandbox.steps import GH, WORK, _gh_headers, fetch_source, image

CAP, WINDOW = 6, 32


def probe_result(out: str) -> str | None:
    """pytest output -> "fail" (the test fails), "pass", or None (errors/unclear: neither good nor bad)."""
    m = re.findall(r"(\d+) (passed|failed|errors?)\b", out or "")
    n = {k.rstrip("s"): int(v) for v, k in m}
    if n.get("error"):
        return None
    if n.get("failed"):
        return "fail"
    return "pass" if n.get("passed") else None


def bisect(commits: list[str], probe, cap: int = CAP) -> dict:
    """commits: newest first; commits[0] is the pinned base, where the repro test fails (G3)."""
    probes: list[dict] = []
    out = lambda status, reason, bad=None, good=None: {"status": status, "reason": reason, "first_bad": bad, "last_good": good,
                                                      "probes": probes, "window": len(commits)}
    if len(commits) < 2:
        return out("not_run", "no_history")
    def p(i):
        r = probe(commits[i]); probes.append({"sha": commits[i], "result": r}); return r
    first = p(len(commits) - 1)
    if first is None:
        return out("inconclusive", "probe_unclear")
    if first == "fail":
        return out("not_run", "no_passing_commit_in_range")
    bad, good = 0, len(commits) - 1
    while good - bad > 1:
        if len(probes) >= cap:
            return out("not_run", "step_cap")
        mid = (bad + good) // 2
        r = p(mid)
        if r is None:
            return out("inconclusive", "probe_unclear")
        bad, good = (mid, good) if r == "fail" else (bad, mid)
    return out("found", "ok", commits[bad], commits[good])


def _commits(repo: str, base_sha: str) -> list[str]:
    with httpx.Client(headers=_gh_headers(), timeout=20) as h:
        r = h.get(f"{GH}/repos/{repo}/commits", params={"sha": base_sha, "per_page": WINDOW})
        r.raise_for_status()
        return [c["sha"] for c in r.json()]


def run_bisect(run, test_diff: str) -> dict:
    """Live: commit list from GitHub, one fresh sandbox per probe. Stores the result in kv bisect:<run_id>."""
    rid, tests = run.run_id, " ".join(sorted({t.split("::")[0] for t in run.repro.test_ids})) if run.repro else ""
    try:
        commits = _commits(run.issue.repo, run.base_sha)
    except Exception:
        res = {"status": "not_run", "reason": "history_unavailable", "first_bad": None, "last_good": None, "probes": [], "window": 0}
    else:
        def probe(sha: str) -> str | None:
            key, vol = f"{rid}-bis-{sha[:8]}", f"pp-snap-{rid}-b{sha[:8]}"
            try:
                _, src = fetch_source(run.issue.repo, key, sha)
                if docker.make_snapshot(vol, src).code:
                    return None
                r = docker.run(image(rid), f"cat > /tmp/t.diff <<'PP_EOF'\n{test_diff}\nPP_EOF\n"
                               f"git apply /tmp/t.diff && python -m pytest -p no:cacheprovider -rfE {tests} 2>&1 | tail -c 4000",
                               name=f"pp-{rid[:8]}-bis-{uuid.uuid4().hex[:6]}", timeout=180, snapshot_volume=vol)
                return probe_result(r.out) if "error: patch failed" not in r.out else None
            except Exception:
                return None
            finally:
                docker.rm_volume(vol); shutil.rmtree(WORK / key, ignore_errors=True)
        res = bisect(commits, probe)
    if res["status"] == "found":
        res["url"] = f"https://github.com/{run.issue.repo}/commit/{res['first_bad']}"
    db.put_kv(db.connect(), f"bisect:{rid}", json.dumps(res))
    return res
