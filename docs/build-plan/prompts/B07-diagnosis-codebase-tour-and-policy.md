# B07 — Diagnosis, codebase tour and policy-checked fix (M3, G4)

Build step B07 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B07) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user sees the likely cause with file:line links, a short codebase tour and a fix diff that passed the diff policy on S-03.

**Why now:** Completes the agent chain needed before verification.

## Slice
- Use cases: UC-03
- Screens: S-03
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Investigator role: locations, hypothesis, tour, evidence IDs that must exist
- Fixer role: non-test diff; G4 per contracts 1.1 (5 files, 200 lines, no deps, no .github, no test edits)
- Attempt history in Show details

## Out of scope for this step
- Verification (B08)
- Reviewer/Explainer (B09)

## Acceptance criteria
- [ ] Planted bug #1 shows a diagnosis citing the real file and line, with clickable evidence
- [ ] A fix touching a test file, a dependency file or .github/ is rejected with the reason and retried (counts as an attempt)
- [ ] A diagnosis citing a non-existent evidence ID is rejected; after one retry the run ends TRIAGE_ONLY with diagnosis unavailable

## Page states to render
- S-03: running, partial, failed

## Tests to write in this step (before calling it done)
- unit: G4 on 6 crafted diffs (ok, test file, requirements.txt, .github, too large, deleted test)
- unit: evidence ID validation
- e2e: tests/e2e/diagnose-fix.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **tdd** — G4 diff policy on crafted diffs; evidence-ID existence check
2. **frontend-design** — diagnosis card and tour list for first-time contributors

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B07/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Run planted bug #1 -> screenshot b07-diagnosis.png and b07-tour.png
2. Open Show details on a rejected attempt -> screenshot b07-policy-reject.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, planted bug #1 shows diagnosis + fix diff
2. Playwright diagnose-fix spec passes

## If it goes wrong
Without a valid diagnosis the run still ends as an honest TRIAGE_ONLY.

## When finished
1. Make sure everything above is deployed (worker, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B07 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B07: Diagnosis, codebase tour and policy-checked fix (M3, G4)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

