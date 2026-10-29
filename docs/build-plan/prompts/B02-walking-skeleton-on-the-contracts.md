# B02 — Walking skeleton on the contracts

Build step B02 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B02) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A judge can open a fixture run on the URL and watch S-03 and S-04 render it from the real API.

**Why now:** Freezes contracts v0.2 in code so the four roles can build in parallel without integration surprises.

## Slice
- Use cases: UC-04, UC-07
- Screens: S-03, S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- backend/contracts/*.py: enums, gates, RunState/RunView, event envelope, Approval (contracts sections 1-5)
- TypeScript types generated from the JSON Schema
- fixtures/runs/<15 cases> from contracts section 8
- GET /api/runs/{id} and GET /api/runs/{id}/events?after=<seq> served from fixtures in dev mode
- Polling client (2 s, 10 s while paused) that ignores older responses
- S-03 stepper + S-04 badge rendering every fixture outcome
- Demo assets: maintainer + contributor GitHub accounts, team upstream repo with 3 planted bugs and branch protection

## Out of scope for this step
- Real runs (B04)
- Real GitHub reads (B03)
- Approval UI (B10)

## Acceptance criteria
- [ ] Each of the 15 fixture runs opens at <FUNNEL_URL>/runs/<fixture-id> and shows the matching S-03/S-04 state from the screen flows
- [ ] Failed, empty and inconclusive look different: env_failed shows Setup failed with the log link, needs_attention_deps_inconclusive shows the inconclusive banner, never a blank panel
- [ ] A slower older poll response never overwrites newer events (seq ordering)
- [ ] The outcome function returns the contracts 1.2 outcome for every fixture

## Page states to render
- S-03: running, partial, failed
- S-04: success, failed, partial, empty

## Tests to write in this step (before calling it done)
- unit: outcome table (contracts 1.2), one test per row incl. stopped_during_setup -> STOPPED
- unit: readiness caps (deps inconclusive, partial baseline)
- integration: /events?after=n returns only seq>n in order
- e2e: tests/e2e/fixtures.spec.ts opens all 15 fixture runs

## Suggested tasks
- Write the 15 fixture runs
- Wire codegen for TS types into the web build
- Create the two GitHub accounts and the planted-bug repo

## Skills — use in this order
1. **tdd** — contract tests: every fixture validates against the Pydantic models; outcome table rows from contracts 1.2
2. **frontend-design** — S-03 stepper and S-04 badge components every later step reuses
3. **code-review** — all four roles review the contract code before freezing

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B02/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Open /runs/verified_fix -> screenshot b02-verified.png (green badge, proof panel)
2. Open /runs/env_failed -> screenshot b02-envfailed.png (Setup failed, not empty)
3. Open /runs/paused_quota_unknown_reset -> screenshot b02-paused.png (no fake resume time)
4. Open /runs/stopped_during_setup -> screenshot b02-stopped.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. Open <FUNNEL_URL>/runs/verified_fix and /runs/env_failed -> correct distinct states
2. Playwright fixtures spec passes in CI against <FUNNEL_URL>
3. contracts.md marked frozen v0.2

## If it goes wrong
Dev mode keeps serving fixtures; real runs are added behind RUN_MODE=real.

## When finished
1. Make sure everything above is deployed (frontend, backend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B02 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B02: Walking skeleton on the contracts`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
After B02, roles A-D branch off. Contract changes only via a PR reviewed by all four.

