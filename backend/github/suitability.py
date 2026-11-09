"""#70 item 7 (trust plan §5): issue suitability, one dimension at a time. Code decides; it explains the existing
handling_decision and never replaces it. No single score.

Each dimension: {dimension, outcome: ok | concern | blocker | unknown, explanation, evidence: [{source, text, url?}], missing}.
`source` says whose words or what fact it is, so an inference is never shown as a maintainer decision:
reporter (the issue author), maintainer (OWNER / MEMBER / COLLABORATOR), contributor (any other commenter),
repository (labels, files, GitHub's own data), patchpilot (our model's extraction or our own check)."""
from backend.contracts.models import CheckStatus, IssueAssessment
from backend.github.consent import INVITE_LABELS, MAINTAINER

ORDER = ["problem_clarity", "expected_behavior", "reproducibility", "technical_scope", "repo_compatibility", "testability",
         "maintainer_intent", "existing_work", "system_support"]
FIXABLE = {"bug", "regression"}


def _ev(source: str, text: str | None, url: str | None = None) -> dict:
    return {"source": source, "text": (text or "").strip()[:300], **({"url": url} if url else {})}


def _who(c: dict, reporter: str | None) -> str:
    login = (c.get("user") or {}).get("login")
    if c.get("author_association") in MAINTAINER:
        return "maintainer"
    return "reporter" if login and login == reporter else "contributor"


def dimensions(*, a: IssueAssessment, issue: dict, comments: list | None, checks: dict[str, CheckStatus],
               expected: str | None, actual: str | None, unsupported: str | None, ai_policy: str) -> list[dict]:
    reporter = (issue.get("user") or {}).get("login")
    labels = [l["name"] for l in issue.get("labels", []) if isinstance(l, dict)]
    r = set(a.decision_reasons)
    out: dict[str, dict] = {}

    def put(dim, outcome, explanation, evidence=(), missing=()):
        out[dim] = {"dimension": dim, "outcome": outcome, "explanation": explanation, "evidence": [e for e in evidence if e["text"]],
                    "missing": list(missing)}

    # problem clarity: is this a bug report at all?
    t = a.issue_type
    ev = [_ev("repository", f"labels: {', '.join(labels)}") if labels else _ev("repository", ""),
          _ev("patchpilot", f"AI summary (may be wrong): {a.problem_summary}" if a.problem_summary else "")]
    if t in FIXABLE:
        put("problem_clarity", "ok", f"Reads as a {t} report ({a.issue_type_source} and our cross-check agree).", ev)
    elif t == "unknown":
        put("problem_clarity", "unknown", "We couldn't tell whether this is a bug: the model, the labels or the wording disagree, "
            "or the reporter asks whether it's a bug.", ev, ["Whether the current behaviour is a bug"])
    else:
        put("problem_clarity", "blocker", f"Reads as {t.replace('_', ' ')}, not a bug, so PatchPilot doesn't change code for it.", ev)

    # expected behaviour: the reporter's words, then our extraction (labelled as ours)
    conds = [_ev("patchpilot", f"AI-extracted condition: {c}") for c in a.acceptance_conditions[:5]]
    if expected:
        put("expected_behavior", "ok", "The reporter says what should happen.", [_ev("reporter", expected), *conds])
    elif "no_expected" in a.missing_information:
        put("expected_behavior", "concern", "The issue doesn't say what should happen instead, so the test would define "
            "\"right\" on its own.", conds, ["What should happen instead"])
    elif t in FIXABLE:
        put("expected_behavior", "ok", "The issue describes what should happen (an expectation in the text).", conds)
    else:
        put("expected_behavior", "unknown", "Not checked: we check this only once the issue reads as a bug.", conds)

    # reproducibility
    ev = [_ev("reporter", f"actual: {actual}" if actual else ""),
          _ev("patchpilot", f"AI-extracted reproduction: {a.reproduction_information}" if a.reproduction_information else "")]
    miss = [m for m in ("no_actual", "no_repro") if m in a.missing_information]
    if t not in FIXABLE:
        put("reproducibility", "unknown", "Not checked: we check this only once the issue reads as a bug.", ev)
    elif not miss:
        put("reproducibility", "ok", "The issue shows the problem (code, steps, an error or a traceback). Whether it really "
            "reproduces is decided later by running the test twice on the original code.", ev)
    else:
        put("reproducibility", "concern", "The issue lacks " + " and ".join(
            {"no_actual": "the actual output or error", "no_repro": "a code example or steps"}[m] for m in miss) + ".", ev,
            [{"no_actual": "What happens now (output, error or traceback)", "no_repro": "A small code example or steps"}[m] for m in miss])

    put("technical_scope", "unknown", "Not judged before the run: the investigation finds which files are involved, and "
        "a change that touches too much is stopped by the diff policy.")

    # repository compatibility
    py = checks.get("python")
    ev = [_ev("repository", f"build system: {a.build_system}")]
    if unsupported == "not_python" or py == CheckStatus.FAILED:
        put("repo_compatibility", "blocker", "Not a Python project; PatchPilot only runs Python projects.", ev)
    elif py == CheckStatus.INCONCLUSIVE:
        put("repo_compatibility", "unknown", "We couldn't read the repository's files to check its language.", ev)
    else:
        put("repo_compatibility", "ok", "A Python project PatchPilot can set up.", ev)

    # testability
    tf = checks.get("tests_found")
    ev = [_ev("repository", f"test runner: {a.test_framework}")]
    if unsupported == "no_tests" or tf == CheckStatus.FAILED:
        put("testability", "blocker", "No test suite found, so a fix can't be verified.", ev)
    elif tf == CheckStatus.INCONCLUSIVE or a.test_framework == "unknown":
        put("testability", "unknown", "We couldn't confirm the repository has tests we can run.", ev)
    else:
        put("testability", "ok", "The repository has tests that pytest can run.", ev)

    # maintainer intent: only maintainers' own words or labels count; silence is unknown, never consent
    said = [c for c in (comments or []) if isinstance(c, dict) and c.get("author_association") in MAINTAINER]
    invite = [l for l in labels if l.lower() in INVITE_LABELS]
    ev = [*[_ev("repository", f"label: {l}") for l in invite],
          *[_ev("maintainer", f"{(c.get('user') or {}).get('login')}: {c.get('body') or ''}", c.get("html_url")) for c in said[-2:]],
          *([_ev("maintainer", f"the reporter is a maintainer ({issue.get('author_association')})")]
            if issue.get("author_association") in MAINTAINER else [])]
    if ai_policy == "forbidden":
        put("maintainer_intent", "blocker", "The repository's contribution docs forbid AI-generated contributions.",
            [*ev, _ev("repository", "AI policy: forbidden")])
    elif issue.get("state_reason") == "not_planned":
        put("maintainer_intent", "blocker", "A maintainer closed the issue as not planned.", ev)
    elif invite:
        put("maintainer_intent", "ok", "A label invites contributions. Publishing still needs consent recorded on the run.", ev)
    elif said:
        put("maintainer_intent", "unknown", "A maintainer commented; read their words below. We don't treat a comment as "
            "agreement unless it clearly asks for a fix.", ev, ["Whether the maintainers want a pull request"])
    else:
        put("maintainer_intent", "unknown", "No maintainer has said whether they want a fix. Ask on the issue before opening "
            "a pull request.", ev, ["Whether the maintainers want a pull request"])

    # existing work
    assignees = [x.get("login") for x in issue.get("assignees") or [] if isinstance(x, dict)]
    from backend.github.reader import claimed_by   # late: reader imports assess, which may import this module
    claims = claimed_by(comments) if comments is not None else None
    by = {(c.get("user") or {}).get("login"): _who(c, reporter) for c in comments or [] if isinstance(c, dict)}
    ev = [*[_ev("repository", f"assigned to {x}") for x in assignees],
          *[_ev(by.get(x, "contributor"), f"{x} said they'll work on it") for x in claims or []],
          *([_ev("repository", "open pull requests mentioning it: " + ", ".join(f"#{n}" for n in a.existing_resolution))]
            if a.existing_resolution else [])]
    if a.issue_status == "closed":
        put("existing_work", "concern", "The issue is closed.", ev)
    elif assignees or claims or a.existing_resolution:
        put("existing_work", "concern", "Someone may already be working on this; check before you start.", ev)
    elif claims is None or a.existing_resolution is None:
        put("existing_work", "unknown", "We couldn't read the comments or the linked pull requests.", ev)
    else:
        put("existing_work", "ok", "No assignee, no claim in the comments, no open pull request mentions it.", ev)

    # system support: things about PatchPilot itself
    sys_r = [x for x in ("other_os", "model_unavailable", "base_sha_unknown", "compatibility_unknown") if x in r]
    text = {"other_os": "the issue mentions Windows or macOS; our sandbox is Linux", "model_unavailable": "our model was unavailable",
            "base_sha_unknown": "we couldn't read the latest commit", "compatibility_unknown": "we couldn't check the language"}
    if unsupported:
        put("system_support", "blocker", "PatchPilot can't run this project today.", [_ev("patchpilot", unsupported)])
    elif sys_r:
        put("system_support", "concern", "PatchPilot may not handle this well: " + "; ".join(text[x] for x in sys_r) + ".",
            [_ev("patchpilot", x) for x in sys_r])
    else:
        put("system_support", "ok", "Nothing about the issue is outside what PatchPilot supports.")
    return [out[d] for d in ORDER]


LABEL = {"problem_clarity": "Problem clarity", "expected_behavior": "Expected behaviour", "reproducibility": "Reproducibility",
         "technical_scope": "Technical scope", "repo_compatibility": "Repository compatibility", "testability": "Testability",
         "maintainer_intent": "Maintainer intent", "existing_work": "Existing work", "system_support": "PatchPilot support"}
SOURCE = {"reporter": "reporter", "maintainer": "maintainer", "contributor": "another commenter", "repository": "repository",
          "patchpilot": "PatchPilot"}


def report_lines(dims: list[dict] | None) -> list[str]:
    if not dims:
        return ["## Suitability by dimension", "- Not checked for this run.", ""]
    out = ["## Suitability by dimension",
           "These explain the decision above; there is no overall score. Sources: whose words or which check each line is from.", ""]
    for d in dims:
        out.append(f"- **{LABEL[d['dimension']]}: {d['outcome']}.** {d['explanation']}")
        out += [f"  - {SOURCE[e['source']]}: {e['text']}" + (f" ({e['url']})" if e.get("url") else "") for e in d["evidence"]]
        out += [f"  - missing: {m}" for m in d["missing"]]
    return [*out, ""]
