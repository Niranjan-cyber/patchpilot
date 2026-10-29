"""Dev only: seed runs for the B16 browser check, owned by one fresh session. Prints TOKEN.
PRs point at REAL pallets/click PRs (#3884 merged, #3900 open when seeded) so S-08 shows live GitHub status."""
import hashlib
import secrets

from backend import db
from backend.contracts.models import IssueSpec, Outcome, PullRequestRef, RunStatus

c = db.connect()
tok = secrets.token_urlsafe(32); h = hashlib.sha256(tok.encode()).hexdigest(); t = db.now().isoformat()
with db.tx(c):
    c.execute("INSERT INTO sessions(id_hash,ip_hash,created_at,last_seen_at) VALUES(?,?,?,?)", (h, None, t, t))
for n, title, outcome, readiness, status, pr in [
    (3888, "use the path_type to perform the other click.Path checks", Outcome.VERIFIED_FIX, "Ready for human review", RunStatus.PUBLISHED, 3884),
    (3886, "Prevent Click from terminating when less is interrupted", Outcome.FIX_NEEDS_ATTENTION, "Needs attention", RunStatus.PUBLISHED, 3900),
    (2402, "resolve_command fails if cmd is None", Outcome.TRIAGE_ONLY, "Unable to verify a fix", RunStatus.FINISHED, None),
]:
    v = db.create_run(c, IssueSpec(html_url=f"https://github.com/pallets/click/issues/{n}", repo="pallets/click", number=n,
                                   title=f"{title} (seeded sample)"), "2247b35e" * 5, owner_session_hash=h)
    v.outcome, v.readiness, v.status = outcome, readiness, status
    if pr:
        v.pr = PullRequestRef(url=f"https://github.com/pallets/click/pull/{pr}", number=pr, head_branch=f"patchpilot/issue-{n}")
    db.save_run(c, v)
print(tok)
