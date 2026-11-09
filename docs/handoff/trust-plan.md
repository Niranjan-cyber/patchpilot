# Maintainer-trust plan: task for C (Devansh + Claude)

Owner: **C**. Reviewer and merger: **A**. Contract changes go through a PR that B reviews (AGENTS.md rule).
Given by the human on 2026-11-09. The full plan is in the appendix below. This header holds the human's decisions and A's map of what already exists. **Read it first; the header wins over the appendix.**

## Human decisions (2026-11-09)
1. **Scope: as much as possible before the demo** (build round 11–12 Nov, demos 12–14 Nov). Work in the order below. Keep each item a small PR with tests, and keep main demo-safe: never merge a half-built flow.
2. **Consent is enforced in the backend, with a typed override.** Publishing is refused unless one of these is recorded:
   - maintainer consent: a reply on the issue from an OWNER/MEMBER/COLLABORATOR (GitHub `author_association`) after our ask, or an explicit maintainer request in the thread;
   - a CONTRIBUTING rule that invites PRs for this kind of change;
   - the user's typed override reason, which is shown in the report. Never put it in the PR body as if it were consent.

   Silence, an open issue, no assignee or no PR is **never** consent. This needs **contracts v0.5** (a new publish blocker and what counts as consent evidence), reviewed by B.
3. **Ownership: the own-words explanation becomes required before publishing.** Three short answers: what was broken, why this fix addresses it, what the new test proves. Set a minimum length. Imperfect answers are never rejected; show more explanation instead. Store the answers with the approval and in the report, not in the PR body. Hash-bound approval stays as it is.
4. `global_llm_tokens_per_day = 3_000_000` is approved and documented. Don't change limits without a recorded human decision.

## What already exists (don't rebuild it)
| Plan section | Already on main | Gap to close |
|---|---|---|
| 4.1 repo checks | #67: ruff/mypy/(based)pyright on the changed files, before vs after; added problems → medium Reviewer concern | Show its own row per tool: PASS / FAIL / NOT_RUN / UNSUPPORTED / BLOCKED, with the command and exit code recorded. Discover from tox.ini, noxfile, .pre-commit-config, CI workflows, CONTRIBUTING. Put `--` before file arguments. Live re-run of mcstatus #1237 (not done yet). |
| 4.2 consent | #68: "ask the maintainer" comment, user-edited, same preflight as a PR, one ask per run (A added the guard) | Decision 2 above. Read the replies (author_association), record consent evidence with source and time, add a backend publish blocker plus typed override, and show the state on S-06/S-07. Map states onto the existing RunStatus/publish_blockers; don't add a 12-state machine. |
| 4.3 existing work | timeline + mentioning open PRs (#55), comment claims (#69, unknown = inconclusive after A's fix) | Re-check claims and new PRs at publish (`stale_checks` only checks closed/linked_pr; exclude the user's own ask comment). Recently closed PRs. Record the source and time checked. |
| 4.4 PR body | #66: summary + AI note, evidence folded | Problem / Cause / Fix / Tests / Limitations / AI as **bold labels**, still short (the test forbids `##`). Name the repo checks that ran and didn't. Never claim a maintainer asked unless consent evidence says so. |
| 5 suitability | #48/#50 IssueAssessment (READY / ASSESSMENT_ONLY / HUMAN_DECISION / UNSUPPORTED), model + keyword cross-check | Per-dimension outcome + evidence + missing info (the table in §5). Tell maintainer statements apart from reporter statements (author_association). No single score. |
| 6 investigator | DIAGNOSE citation check, tour validation (#35/#36) | Add callers, regression risks, test strategy and uncertainty to the Investigator output; facts must cite evidence. |
| 7 test quality | G3 fails 2/2, G5 two fresh runs, hidden variant (B17) | A deterministic test-quality report: fails on base / passes with fix (exists), assertion present, mock-heavy flagged, framework and test folder follow the repo, no new deps. |
| 8 reviewer | Reviewer concerns high/medium/low, can only lower readiness | Map to BLOCKER / IMPORTANT / SUGGESTION / ACCEPTED_TRADEOFF with file:line. Plus your own "Revise the test" proposal: approved; resume at `reproduce`. |
| 9 ownership | Approve: 3-box checklist + optional explanation, hash-bound, Revise voids approval | Decision 3 above. |
| 10 orchestration | leases, checkpoints, quota pause, EndReason taxonomy, budgets | Audit only. Map the plan's failure names onto the existing EndReason; don't add a parallel enum. Fix only real gaps you find, with tests. |
| 11 report | report.md (deterministic) | Add consent, ownership and repo-check sections. Missing evidence must say "not checked". |
| 12 eval | B14 eval set (`eval/`), never run | A 10–20 real-issue set with the outcome definitions from §12. Re-check the candidates (pylint #11791, boltons #750, html2text #468) first. A correct stop counts as a success. |
| 13 don't build | | Follow it. |

## Order
1. Consent enforcement (contracts v0.5 PR → B reviews), then the code.
2. Required ownership explanation.
3. Repo-check rows + live mcstatus re-run.
4. Re-check existing work at publish.
5. PR body labels.
6. "Revise the test".
7. Suitability dimensions.
8. Test-quality report.
9. Reviewer severities.
10. Investigator fields.
11. Real-issue eval set.

After each PR, post in messages.md and add a LEARNING line. A reviews and merges.

---

# Appendix: the plan as given by the human

## Role
Act as a senior staff engineer, AI-agent systems architect, developer-tools product engineer, and experienced open-source maintainer. You are working on PatchPilot, an AI-assisted open-source contribution platform. Improve the existing product into something real open-source contributors and maintainers can trust. Work with the existing implementation, architecture, contracts, tests, Git history and outstanding PRs. This is incremental, not a rewrite. Be skeptical of unnecessary abstractions, additional agents, additional providers and features that don't improve the core contribution workflow. Don't optimize for files changed, agents or PRs generated.

Optimize for: (1) correctly identifying issues worth working on; (2) understanding the repository and its contribution expectations; (3) minimal, technically correct fixes; (4) meaningful regression tests; (5) verification with repository-native checks; (6) a human contributor who understands and owns the change; (7) respecting maintainer intent and reducing review burden.

## 1. Product context
Workflow: GitHub issue → understand → investigate → reproduce → regression test → fix → verify → review → human approval → draft PR. Value proposition: PatchPilot turns a GitHub issue into a technically verified, repository-appropriate contribution that a human understands, approves and can responsibly submit for maintainer review. It should make contributions more reliable and easier to review, not increase the volume of automated PRs.

Critical principle: deterministic decisions stay in ordinary code. LLMs only interpret, investigate, explain and reason. An LLM never decides alone that a contribution is ready to publish; the gates and contracts decide whether the required evidence exists.

## 2. Inspect before changing
Audit the structure, docs, LEARNING, architecture, contracts, LangGraph workflow, API routes, DB, GitHub integration, sandbox/worker, prompts, gates, SupplyGuard, Reviewer, publishing, tests, config, recent commits, git status and open PRs. Build a capability matrix (Capability | Exists? | Correct? | Tested? | Limitation | Action). Classify each feature as complete / partial / insufficiently tested / broken / missing / not required. For each change, name the module, contract, tests, exact gap, minimal implementation and acceptance criteria. Don't duplicate; don't replace working infrastructure.

## 3. Technical correctness is not enough
Keep three questions separate:
- **A. Technical trust:** reproduced? Does the test show the original failure (fails on base, passes with fix)? Is the actual cause fixed? Do the relevant tests pass? Is the change safe and scoped?
- **B. Project trust:** is the issue still valid? Already claimed or PR'd? Maintainer preference? Does the repo accept this kind of contribution? Project rules? Consistent with project direction?
- **C. Contributor trust:** can the human explain the problem, the fix and the tests? Have they reviewed the diff? Can they answer maintainer questions? Are they accountable?

Technical verification is not proof of project approval or of human understanding. Implement these distinctions explicitly.

## 4. Priority 0: finish existing work (#66–#69)
### 4.1 Repo-native checks (#67)
- Discover checks from pyproject.toml, pytest.ini, tox.ini, noxfile.py, setup.cfg, .pre-commit-config.yaml, GitHub Actions and contributor docs.
- Cover unit tests, focused tests, lint, format, type check and static analysis.
- Discovery is deterministic. Prefer documented commands and avoid irrelevant or expensive checks.
- Record the commands discovered, the commands executed, exit codes and useful output, and the checks that couldn't run.
- Never report an unexecuted check as passed. Keep sandbox isolation and expose no secrets.
- Statuses: PASS / FAIL / NOT_RUN / UNSUPPORTED / BLOCKED, never collapsed into one generic error.

### 4.2 Maintainer consent (#68)
- An open, valid issue isn't permission. Use a lifecycle with unambiguous transitions, following project naming: issue discovered → assessed → context checked → maintainer contact required → awaiting response → consent granted / declined / no response → in progress → human review required → approved for draft PR → published.
- Consent evidence: a maintainer explicitly requests a fix, confirms someone should work on it, asks for an implementation or test, or agrees to the contributor working on it.
- Not consent: the issue is open, unassigned or has no linked PR; no response; the contributor or an AI thinks it's easy or worth fixing.
- Without consent: no automatic draft PR. Give the contributor a concise message to post, explain why consent is needed, store the state, and allow assessment or waiting.
- No repeated pings and no spam. A decline stops the workflow unless new legitimate authorization arrives. Silence isn't approval.
- The message says what was understood, the proposed scope, the test/verification approach and a polite question. No generic AI intro, no long report. The contributor reviews and explicitly approves it before posting.

### 4.3 Existing-work detection (#69)
- Check issue state, comments, linked PRs, cross-refs, open and recently closed PRs, branches where relevant, duplicates and claims.
- Outcomes: NO_KNOWN_EXISTING_WORK / CONTRIBUTION_ALREADY_CLAIMED / EXISTING_PR_FOUND / DUPLICATE_ISSUE / HUMAN_REVIEW_REQUIRED / INSUFFICIENT_EVIDENCE.
- Never claim "no existing work" unless the sources were actually checked. Record the source and the time checked. Re-check before publication.

### 4.4 Concise PR description (#66)
- Sections: Problem, Cause, Fix, Tests (the regression test plus the repo checks run), Limitations, AI assistance (per repo policy).
- No agent history in the body; details stay in the report.
- Don't claim a maintainer requested the fix unless the evidence supports it.

## 5. Priority 1: issue suitability
Assess each dimension independently: problem clarity, expected behavior, reproducibility, technical scope, repo compatibility, testability, maintainer intent, existing work, system support. Each gets a structured outcome, evidence, missing information and a short explanation. No single unexplained score.

Keep the existing outcomes:
- **READY:** technically suitable; doesn't imply consent.
- **ASSESSMENT_ONLY:** analysis only.
- **HUMAN_DECISION:** a decision or clarification is needed.
- **UNSUPPORTED:** can't be handled safely.

Explain every outcome. Use the full context: description, comments, labels, assignees, milestone, linked PRs, cross-refs, contribution policy and discussions. Distinguish reporter statements, maintainer statements, contributor assumptions and PatchPilot inferences. Never present an inference as a maintainer decision.

## 6. Priority 2: repository understanding
- No repo-wide knowledge graph; bounded context.
- Inspect the affected function/module, callers, dependencies, existing tests, similar code, error-handling, naming and style conventions, version compatibility, contribution docs and prior fixes/PRs.
- The Investigator answers: where the behavior originates, which paths are affected, current vs expected behavior, assumptions, affected callers and regression risks.
- Important claims need evidence (files, functions, test results). If evidence is short, investigate more; don't invent.

## 7. Priority 3: regression test quality
A deterministic report covering:
- Reproduces the bug: exercises the reported failure, fails on base, passes with the fix, observable behavior.
- Non-vacuous: meaningful, specific assertions; fails when broken.
- Realistic inputs: edge cases, not only mocks, mocks scoped.
- Repo conventions: framework, fixtures, helpers, no new deps, supported Python versions.
- Scope: covers the issue, nothing unrelated, no needless complexity.

Example output: reproduced PASS · fails on base PASS · passes with fix PASS · assertions PASS · mocks REVIEW_REQUIRED · conventions PASS · edge cases NOT_COVERED. Not a free-form LLM opinion. Hidden variants don't establish correctness alone.

## 8. Priority 4: agent responsibilities (no new agents)
- **Investigator:** root-cause hypothesis, evidence, code locations, affected callers, expected behavior, minimal fix, regression risks, test strategy, uncertainty. Facts vs hypotheses.
- **Fixer:**
  - Make the smallest fix: no unrelated rewrites, no new abstractions, no unjustified public-API change.
  - Keep compatibility and follow the repo's conventions. No speculative cleanup.
  - Never edit unrelated tests, weaken assertions or delete failing tests.
  - Explain before widening the scope.
- **Reviewer:**
  - Review the actual diff and evidence independently across 8 dimensions: correctness, regression risk, scope, test quality, conventions, compatibility, maintainability, evidence quality.
  - Each finding has a severity, file/location, explanation, evidence and required action.
  - Severities: BLOCKER / IMPORTANT / SUGGESTION / ACCEPTED_TRADEOFF.
  - It can reject a patch even when all tests pass. Keep the deterministic gates.

## 9. Priority 5: contributor understanding and ownership
- Before publishing, show:
  - A. the problem in plain language;
  - B. the root cause, with code;
  - C. the exact behavior change;
  - D. the test: what it checks, and why it fails before the fix and passes after;
  - E. limitations;
  - F. the diff in readable sections.
- The contributor can inspect, comment, request revisions or reject.
- Ownership: the contributor explains in their own words what was broken, why the fix works and what the test proves.
  - It's guided learning, not an exam. A checkbox isn't proof.
  - Imperfect answers aren't rejected; misunderstandings get more explanation.
- Explicit final approval of the diff. Keep hash-bound approval; a changed diff invalidates it.

## 10. Priority 6: orchestration reliability
- Keep LangGraph.
- Persist: the current node, gates, attempts, retries, model/provider, tokens, budget, tool outcomes, sandbox ids, artifacts, human decisions, approval hashes and failure classes. Nothing critical stays in memory.
- Structured, validated agent outputs: handle missing fields, malformed JSON and unknown enum values; tell model failure apart from task failure. Provider specifics stay outside business logic. No new provider abstraction if the current layer works.
- Failure taxonomy: MODEL_UNAVAILABLE, MODEL_TIMEOUT, RATE_LIMITED, INVALID_MODEL_OUTPUT, MISSING_EVIDENCE, TOOL_EXECUTION_FAILED, ENVIRONMENT_SETUP_FAILED, TEST_EXECUTION_FAILED, CODE_GENERATION_FAILED, PATCH_REJECTED, QUOTA_EXHAUSTED, HUMAN_ACTION_REQUIRED, UNSUPPORTED_OPERATION. Say which retry, which need a human and which terminate. Bounded retries with backoff, no infinite loops.
- Budgets: user and global limits enforced, retries counted, tokens recorded, safe pause, resume without repeating work, a useful exhaustion message. Limits never change silently, and rate limits aren't solved by raising the budget.
- Security: isolation, no credentials reach repo code, no unintended network, SupplyGuard and diff policy, artifact integrity, approval before publishing. Any boundary change needs tests.

## 11. Priority 7: evidence and reporting
Build on the existing artifacts; no parallel system. The report covers:
- issue assessment (outcome, why, evidence, consent needed?);
- reproduction (environment, command, result, artifacts);
- investigation (root cause, files, evidence);
- fix (what changed, why minimal, compatibility risks);
- tests (regression test, fails on base / passes with fix, checks run and not run, uncertainty);
- review (findings, blockers, accepted tradeoffs);
- ownership (diff reviewed, understanding shown, final approval);
- publishing (consent, existing work rechecked, approval bound to the diff, PR actually published).

Missing evidence is never shown as success. It must be readable for beginners without hiding detail.

## 12. Priority 8: real-repository evaluation
- 10–20 real issues, Python, pip/pytest.
- Kinds:
  - clear bug;
  - edge case;
  - error handling;
  - version compatibility;
  - missing test;
  - ambiguous issue;
  - existing contribution;
  - needs maintainer clarification;
  - unsupported environment;
  - correct-to-stop.
- Candidates: pylint #11791, boltons #750, html2text #468. They're evaluation candidates, not authorization to submit. Re-check their status, replies, PRs and policies first.
- Measure: suitability accuracy, the proceed/stop decision, reproduction, root cause, test quality, fix correctness, repo-native checks, Reviewer accuracy, human understanding, maintainer response, acceptance or revisions, and merge.
- Track rejection reasons separately. A correct ASSESSMENT_ONLY or UNSUPPORTED is a success.

## 13. Don't build
Multi-language autonomous fixing, autonomous merging, bulk resolution, mass PRs, more agents, more providers, repo-wide knowledge graphs, big dashboards, gamification, social features, reputation systems, long PR narratives, an orchestration rewrite.

## 14. Logical workflow (reuse the existing nodes)
1. Intake
2. Assessment
3. Existing-work detection
4. Repo and maintainer context
5. Consent lifecycle
6. Baseline and reproduce
7. Investigate
8. Test design
9. Fix
10. Diff/security policy
11. Fresh-container verify
12. Independent review
13. Contributor walkthrough and ownership
14. Final approval
15. Re-check issue/PR status and approval validity
16. Draft PR

Every publishing decision is enforced in the backend, not only in the UI or a prompt.

## 15. Tests (minimum)
- **Suitability:** clear, ambiguous, unsupported language or environment, missing expected behavior, existing PR, assignee or claim, maintainer request, rejection, no response.
- **Consent:** no publish without it; silence isn't consent; a decline blocks; the message is reviewable; state survives restart; no repeated pings; consent is re-checked.
- **Repo checks:** commands detected and run, output captured, missing tooling, timeouts, NOT_RUN correct, unexecuted never passed.
- **Test quality:** fails on base, passes with fix, vacuous assertion caught, wrong test rejected, mock-heavy flagged.
- **Ownership:** inspect the diff, request changes, reject, approval bound to the diff, a changed diff invalidates it, answers stored.
- **Orchestration:** restart, interruption, retry exhaustion, timeout, rate limit, invalid output, quota, sandbox failure, resume without duplicate work.
- **Publishing:** missing consent or approval blocks; a stale issue or existing PR triggers re-evaluation; a changed diff invalidates approval; errors are reported accurately.
- Never weaken tests. Run the full suite and report skips with reasons.

## 16. Method
For each change, in order:
1. Inspect.
2. Find the gap.
3. Explain the change.
4. Name the contracts and modules it touches.
5. Make the smallest change.
6. Add tests.
7. Run the focused tests.
8. Run the repo checks.
9. Inspect the diff.
10. Update the docs.

- No unrelated mega-patches.
- No silent changes to APIs, DB contracts, env vars or security boundaries. A contract change explains why, updates every consumer, handles compatibility, tests old and new behavior, and updates the docs.
- No speculative abstractions and no deleting capabilities without evidence. If requirements are unclear, stop that part and report it.

## 17. Deliverables
- A: audit
- B: gap-to-implementation map
- C: architecture doc update (update the existing one)
- D: implementation
- E: tests
- F: evaluation procedure
- G: final engineering report (files, contracts, tests added/run/passed/failed/skipped, risks, open decisions, work not done, next step)

## 18. Definition of done
1. Audited.
2. Nothing duplicated.
3. Consent explicit and enforced.
4. Existing work checked.
5. Suitability backed by evidence.
6. Repo checks run and reported honestly.
7. Tests meaningfully evaluated.
8. Agent roles clear.
9. Contributors understand the change.
10. Approval tied to the exact diff.
11. State survives interruption.
12. Failures and rate limits predictable.
13. Security intact.
14. Tests pass.
15. Docs match behavior.
16. Nothing publishes just because an AI says it's ready.

**The objective is not to make PatchPilot open more PRs. It is to make every contribution it recommends more correct, more understandable, more repository-appropriate, and easier for maintainers to review.**
