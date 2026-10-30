# B14 — Eval slide numbers

Build step B14 of **PatchPilot** (MVP). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B14) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A judge can see PatchPilot's outcomes compared with the official tests on an /eval page.

**Why now:** Reliability is 20% of judging; cheapest proof. Highest-value Should.

## Slice
- Use cases: UC-04
- Screens: S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- scripts/eval.py runs 5 planted bugs + 5 SWE-bench Lite issues
- Compares PatchPilot outcome with the official tests
- Static /eval page from the results JSON

## Out of scope for this step
- Large-scale benchmarking

## Acceptance criteria
- [ ] /eval lists each issue with outcome, official-test result and time
- [ ] Any false verified claim is listed first in red; unknown official results show unknown, not pass

## Page states to render
- S-04: success, partial, failed

## Tests to write in this step (before calling it done)
- unit: eval comparison on recorded results
- e2e: tests/e2e/eval.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **tdd** — the comparison logic (verified vs official tests)

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B14/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Open <FUNNEL_URL>/eval -> screenshot b14-eval.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>/eval the numbers match results.json

## If it goes wrong
Keep main deployed and the golden path working; if this can't land, revert to the previous step's behaviour and report.

## When finished
1. Make sure everything above is deployed (frontend, worker) and the done-check passes on the public URL.
2. Set `"status": "done"` for B14 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B14: Eval slide numbers`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Run overnight on the host.

