"""Deterministic run report (B09; G6's fallback template). Every status is read from recorded gates, never written by an LLM."""
from backend.contracts.models import CheckStatus, RunView

WORD = {CheckStatus.PASSED: "passed", CheckStatus.FAILED: "failed", CheckStatus.INCONCLUSIVE: "inconclusive",
        CheckStatus.NOT_RUN: "not run", CheckStatus.BLOCKED: "blocked"}
GATES = [("G0", "Issue eligibility"), ("G1", "Dependency safety check (SupplyGuard)"), ("G2", "Setup: install + tests collect"),
         ("G3", "Reproduction test fails 2/2 on the original code"), ("G4", "Fix follows the diff policy"),
         ("G5", "Fresh-sandbox verification: new test passes 2/2, no regressions"), ("G6", "Report matches recorded results")]


def render(v: RunView, narrative: str | None = None) -> str:
    g = lambda k: WORD.get(v.gates.get(k, CheckStatus.NOT_RUN), "not run")
    L = [f"# PatchPilot report: {v.issue.repo} #{v.issue.number}", "",
         f"**{v.issue.title}**  ", f"Issue: {v.issue.html_url}  ", f"Base commit: `{v.base_sha}`  ",
         f"Outcome: **{v.outcome.value if v.outcome else 'still running'}**: {v.readiness or 'not decided yet'}  ",
         f"Ended because: {v.end_reason.value if v.end_reason else 'n/a'}  ", f"Run: {v.run_id}, revision {v.revision}", "",
         "> Ready for human review never means safe to merge automatically. Passing tests don't prove the code is bug-free.", "",
         "## Checks", "| Check | Result |", "|---|---|", *[f"| {name} | {g(k) if k != 'G6' else 'passed (template report)'} |" for k, name in GATES], ""]
    if v.issue.checks:
        L += ["## Issue eligibility", *[f"- {k.replace('_', ' ')}: {WORD.get(s, s)}" for k, s in v.issue.checks.items()], ""]
    if v.supplyguard:
        sg = v.supplyguard
        vulns = [f for f in sg.findings if f.get("type") == "vulnerability"]
        susp = [f for f in sg.findings if f.get("type") == "suspicious"]
        L += ["## Dependencies (SupplyGuard)", f"- Status: {WORD[sg.status]}", f"- Files checked: {', '.join(sg.files) or 'none found'}",
              f"- Suspicious packages: {', '.join(str(f.get('package')) for f in susp) or 'none'}",
              f"- Known vulnerabilities: {len(vulns)} (reported, not blocking: tests run offline in a sandbox)",
              *([f"- Couldn't complete: {', '.join(sg.failures)}"] if sg.failures else []),
              "- Not a proof of security; no full transitive or malware analysis is claimed.", ""]
    if v.env:
        L += ["## Setup", f"- Python {v.env.python_version}; install commands: " + ("; ".join(f"`{c}`" for c in v.env.install_cmds) or "none"), ""]
    if v.baseline:
        b = v.baseline
        L += ["## Existing tests (before any change)", f"- Passed: {len(b.pass_set)}", f"- Already failing (not caused by us): {len(b.fail_set)}",
              *[f"  - `{t}`" for t in b.fail_set[:20]], f"- Flaky: {len(b.flaky_set)}", *([f"  - `{t}`" for t in b.flaky_set[:20]]),
              *(["- Partial: some results couldn't be read."] if b.partial else []), ""]
    if v.repro:
        L += ["## Reproduction", f"- Test: {', '.join(f'`{t}`' for t in v.repro.test_ids)}", f"- Expected failure: {v.repro.expected_failure}",
              f"- On the original code: {', '.join(WORD[s] for s in v.repro.runs_on_base) or 'not run'}", ""]
    if v.diagnosis:
        L += ["## Likely cause (hypothesis)", v.diagnosis.hypothesis, *[f"- `{l.path}`" + (f" line {l.line}" if l.line else "") for l in v.diagnosis.locations],
              *(["", "Codebase tour:"] + [f"- `{t.path}`: {t.why}" for t in v.diagnosis.tour] if v.diagnosis.tour else []), ""]
    if v.patch:
        L += ["## Change", f"- Fix attempt {v.patch.attempt}; diff policy: {WORD[v.patch.policy_result]}" + (f" ({v.patch.policy_reason})" if v.patch.policy_reason else ""),
              f"- Exact diff: download `/api/runs/{v.run_id}/diff.patch`", ""]
    if v.verify:
        L += ["## Verification in a fresh sandbox", f"- New test after the fix: {', '.join(WORD[s] for s in v.verify.new_test_runs) or 'not run'}",
              f"- Regressions: {', '.join(v.verify.regressions) or 'none'}", ""]
    if v.review and v.review.concerns:
        L += ["## Reviewer concerns", *[f"- [{c.get('severity', '?')}] {c.get('text', '')}" for c in v.review.concerns], ""]
    if narrative:
        L += ["## Explanation", narrative, ""]
    blockers = [b.value for b in v.publish_blockers]
    L += ["## Publishing", f"- Blockers: {', '.join(blockers) or 'none'}",
          *([f"- Pull request: {v.pr.url or v.pr.compare_url}"] if v.pr else []), "",
          "## Limitations",
          "- Only Python projects with discoverable tests are supported.",
          "- The sandbox trusts the project's own install steps inside its run; results apply to this commit only.",
          *(["- Some checks did not complete; inconclusive results are unknown, not passed."]
            if any(s == CheckStatus.INCONCLUSIVE for s in v.gates.values())
            or (v.supplyguard and v.supplyguard.status == CheckStatus.INCONCLUSIVE) else [])]
    return "\n".join(L) + "\n"
