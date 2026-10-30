# B18 — Explore one repo (S5)

Build step B18 of **PatchPilot** (MVP). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B18) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user who pastes a repo URL sees 3 to 5 issues PatchPilot can likely run, with reasons.

**Why now:** Should feature for first-time contributors.

## Slice
- Use cases: UC-10
- Screens: S-09
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Rank by runnable signals (recipe known, tests found, issue clarity), not labels
- Effort labelled Estimate

## Out of scope for this step
- Multi-repo discovery

## Acceptance criteria
- [ ] Each suggestion shows why it may fit and its readiness signals
- [ ] A repo with no runnable issues shows the Empty state text, distinct from a GitHub failure

## Page states to render
- S-09: loading, success, empty, partial, failed

## Tests to write in this step (before calling it done)
- unit: ranking on fixture issues
- e2e: tests/e2e/explore.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **frontend-design** — S-09 shortlist

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B18/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Paste the team upstream repo -> screenshot b18-shortlist.png
2. Paste a JS repo -> screenshot b18-unsupported.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>/explore the upstream repo returns its planted bugs

## If it goes wrong
Keep main deployed and the golden path working; if this can't land, revert to the previous step's behaviour and report.

## When finished
1. Make sure everything above is deployed (frontend, backend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B18 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B18: Explore one repo (S5)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

