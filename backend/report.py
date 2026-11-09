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
    if v.assessment:
        from backend.github.assess import report_lines
        L += report_lines(v.assessment)
    if v.issue.checks:
        L += ["## Issue eligibility", *[f"- {k.replace('_', ' ')}: {WORD.get(s, s)}" for k, s in v.issue.checks.items()], ""]
    if v.supplyguard:
        sg = v.supplyguard
        vulns = [f for f in sg.findings if f.get("type") == "vulnerability"]
        susp = [f for f in sg.findings if f.get("type") == "suspicious"]
        # #29: counts are only totals when the scan finished; unknown is never "none" or 0
        names = ', '.join(str(f.get('package')) for f in susp)
        if sg.status in (CheckStatus.PASSED, CheckStatus.BLOCKED):
            susp_txt, vuln_txt = names or "none", f"{len(vulns)}"
        elif set(sg.failures) & {"supplyguard_unavailable", "no_supported_dependency_files"}:
            susp_txt = vuln_txt = "unknown (the check didn't run)"
        else:
            susp_txt, vuln_txt = names or "none found before the check stopped", f"at least {len(vulns)} (the check didn't finish)"
        L += ["## Dependencies (SupplyGuard)", f"- Status: {WORD[sg.status]}", f"- Files checked: {', '.join(sg.files) or 'none found'}",
              f"- Suspicious packages: {susp_txt}",
              f"- Known vulnerabilities: {vuln_txt} (reported, not blocking: tests run offline in a sandbox)",
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
              f"- On the original code: {', '.join(WORD[s] for s in v.repro.runs_on_base) or 'not run'}",
              "- Covers what the issue expects: " + ("not checked" if v.repro.uncovered is None else "the test designer says it checks every stated condition (its own claim, not checked by code)"
                  if not v.repro.uncovered else "**no**, it leaves out: " + "; ".join(v.repro.uncovered)), ""]
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
    L += repo_checks_section(v.run_id)
    o = v.approval.ownership if v.approval else None   # contracts v0.5 §2.3; never in the PR body
    if o:
        L += ["## The contributor's explanation (own words)", f"- What was broken: {o.what_was_broken}",
              f"- Why this fix: {o.why_this_fix}", f"- What the new test proves: {o.what_the_test_proves}", ""]
    k = v.consent
    L += ["## Maintainer consent", "- Not recorded: no maintainer has agreed yet, so publishing is blocked." if k is None else
          f"- Override by the user (no maintainer consent): {k.override_reason}" if k.kind == "user_override" else
          f"- {k.kind.replace('_', ' ')}" + (f" by {k.author} ({k.author_association})" if k.author else "")
          + (", confirmed by the user" if k.attested_by_user else "") + f": \"{k.quote}\"" + (f" ({k.source_url})" if k.source_url else ""), ""]
    L += ["## Publishing", f"- Blockers: {', '.join(blockers) or 'none'}",
          *([f"- Pull request: {v.pr.url or v.pr.compare_url}"] if v.pr else []), "",
          "## Limitations",
          "- Only Python projects with discoverable tests are supported.",
          "- The sandbox trusts the project's own install steps inside its run; results apply to this commit only.",
          *(["- Some checks did not complete; inconclusive results are unknown, not passed."]
            if any(s == CheckStatus.INCONCLUSIVE for s in v.gates.values())
            or (v.supplyguard and v.supplyguard.status == CheckStatus.INCONCLUSIVE) else [])]
    return "\n".join(L) + "\n"


def repo_checks_section(run_id: str) -> list[str]:
    """#70 item 3: one line per tool with its command and exit code. Missing evidence says "not checked", never passed."""
    import json
    from backend import db
    try:
        raw = db.get_kv(db.connect(), f"repo_checks:{run_id}")
    except Exception:
        raw = None
    res = json.loads(raw) if raw else None
    if not res or res.get("checks") is None:
        return ["## Repository checks", "- Not checked: the repo's own linters and type checkers didn't run for this change.", ""]
    if not res["checks"]:
        why = {"no_python_files": "no Python files changed", "diff_did_not_apply": "the change didn't apply in the check sandbox",
               "sandbox_failed": "the check sandbox failed"}.get(res.get("reason"), "the repo configures none we can run")
        return ["## Repository checks", f"- Not checked: {why}.", ""]
    out = ["## Repository checks", "| Tool | Result | Exit code | Command | Notes |", "|---|---|---|---|---|"]
    for c in res["checks"]:
        cmd = f"`{c['command']}`" if c.get("command") else "-"
        notes = c.get("note", "") + ("; " + "; ".join(c["new"][:3]) if c.get("new") else "")
        out.append(f"| {c['tool']} | {c['status']} | {c['exit_code'] if c.get('exit_code') is not None else '-'} | {cmd} | {notes.replace('|', '/')} |")
    return [*out, ""]
