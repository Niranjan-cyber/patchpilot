# B08 — Fresh-container red to green proof (M4, G5)

Build step B08 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B08) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user sees the reproduction test go red on the original code and green after the fix in a brand-new container on S-04.

**Why now:** The winning feature; must be real and demoable as early as possible.

## Slice
- Use cases: UC-04
- Screens: S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Verify node: new container from the run image, original + test diff + fix diff, new test 2x, full baseline pass set
- G5 retries: Fixer up to 3, one re-diagnosis, then TRIAGE_ONLY
- Outcome + readiness computed per contracts 1.2
- S-04 proof panel with baseline counts

## Out of scope for this step
- Reviewer, Explainer, report download (B09)

## Acceptance criteria
- [ ] Planted bug #1 ends with S-04 Ready for human review: red 2/2 on original, green 2/2 after fix, every baseline-passing test still passing
- [ ] A fix that breaks a baseline test is retried; after all attempts S-04 shows Unable to verify a fix with the triage report
- [ ] Verification never runs in the container the agent worked in (container IDs recorded and different)
- [ ] If the fresh container fails to start or the test run errors, S-04 shows the failure with its log, never a green badge

## Page states to render
- S-04: success, failed, partial

## Tests to write in this step (before calling it done)
- unit: G5 on recorded runs (pass, regression, flaky new test)
- integration: verify container ID differs from every agent container ID of the run
- e2e: tests/e2e/verify.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **tdd** — G5 evaluation incl. flaky 1/2 and baseline regressions
2. **frontend-design** — the proof panel: red -> green, the one thing judges must understand in 60 s

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B08/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Run planted bug #1 end to end -> screenshot b08-proof.png
2. Run planted bug #3 (designed to tempt a regression) -> screenshot b08-triage.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, planted bug #1 shows the red -> green proof panel
2. Playwright verify spec passes

## If it goes wrong
The recorded backup run of this step is the video's safety net.

## When finished
1. Make sure everything above is deployed (worker, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B08 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B08: Fresh-container red to green proof (M4, G5)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

