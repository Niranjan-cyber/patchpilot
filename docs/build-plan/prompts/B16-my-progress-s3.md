# B16 — My progress (S3)

Build step B16 of **PatchPilot** (MVP). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B16) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A signed-in user can see their issues, outcomes and PR statuses over time on S-08.

**Why now:** Should feature; extends S-08.

## Slice
- Use cases: UC-09
- Screens: S-08
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Progress view with PatchPilot and GitHub data in separate columns
- No scores, streaks or ranks

## Out of scope for this step
- Public profiles

## Acceptance criteria
- [ ] PR status from GitHub shows Status unavailable when the fetch fails, never closed or open as a guess
- [ ] Analyzed, fix proposed, PR opened and PR merged are shown as separate counts

## Page states to render
- S-08: empty, success, partial, failed

## Tests to write in this step (before calling it done)
- unit: counts never conflate outcomes
- e2e: tests/e2e/progress.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **frontend-design** — progress view

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B16/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Open S-08 progress as the contributor -> screenshot b16-progress.png
2. Block GitHub in the test -> screenshot b16-status-unavailable.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, the contributor sees their run and PR status

## If it goes wrong
Keep main deployed and the golden path working; if this can't land, revert to the previous step's behaviour and report.

## When finished
1. Make sure everything above is deployed (frontend, backend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B16 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B16: My progress (S3)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

