# B15 — Ask why, and optional guided pauses (S2)

Build step B15 of **PatchPilot** (MVP). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B15) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A first-time contributor can ask Why this file? on S-03/S-04 and get an answer citing evidence.

**Why now:** Serves the beginner user; builds on the Explainer.

## Slice
- Use cases: UC-08
- Screens: S-03, S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Ask panel -> Explainer with evidence IDs
- Pause toggles via interrupt()

## Out of scope for this step
- Free chat about anything

## Acceptance criteria
- [ ] Answers cite evidence IDs that open the source
- [ ] If the Explainer is unavailable the panel says so with retry; it never invents an answer without citations

## Page states to render
- S-03: running, failed
- S-04: success, failed

## Tests to write in this step (before calling it done)
- unit: answer without citations is rejected
- e2e: tests/e2e/ask.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **langgraph-human-in-the-loop** — optional pause points
2. **frontend-design** — side panel

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B15/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Ask Why this file? on a verified run -> screenshot b15-answer.png
2. Turn on pause after repro -> screenshot b15-paused.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, ask a question on planted bug #1 and get a cited answer

## If it goes wrong
Keep main deployed and the golden path working; if this can't land, revert to the previous step's behaviour and report.

## When finished
1. Make sure everything above is deployed (frontend, worker) and the done-check passes on the public URL.
2. Set `"status": "done"` for B15 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B15: Ask why, and optional guided pauses (S2)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

