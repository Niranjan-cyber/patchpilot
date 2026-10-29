# B04 — Durable runs that survive a worker crash

Build step B04 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B04) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user who clicks Start run on S-02 sees S-03 move from Queued to Running and keep going after the worker is killed.

**Why now:** Every later step runs inside this job loop; crash/resume is a stated risk.

## Slice
- Use cases: UC-02, UC-07
- Screens: S-02, S-03
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- POST /api/runs: runs + jobs rows in one transaction, run.queued emitted after commit
- Worker: lease 60 s, heartbeat 10 s, reaper, run.interrupted/run.resumed
- LangGraph graph with stub nodes per contracts 1.1 + SqliteSaver in data/checkpoints.db
- POST /api/runs/{id}/stop -> STOPPED per contracts 1.2
- Status transitions per contracts 1.3

## Out of scope for this step
- Real sandbox steps (B05)
- LLM roles (B06)
- Limits and ownership (B12)

## Acceptance criteria
- [ ] Start run -> S-03 shows Queued then Running within 3 s, stub steps advancing
- [ ] Killing the worker mid-step -> S-03 shows Interrupted, then resumes from the last finished step after restart; no step runs twice to completion
- [ ] Stop during a stub setup step -> S-04 shows Stopped, report so far, not System error
- [ ] 2 failed resumes of one step -> analysis ends with end_reason system_error and the 1.2 outcome

## Page states to render
- S-03: running, failed, partial
- S-04: success, failed

## Tests to write in this step (before calling it done)
- unit: every row of the contracts 1.3 transition table
- integration: job row is invisible to the worker until the run transaction commits
- integration: kill worker process mid-node, restart, assert resume from checkpoint
- e2e: tests/e2e/run-lifecycle.spec.ts

## Suggested tasks
- SQLite WAL + busy_timeout
- Run worker as a separate process from deploy.ps1

## Skills — use in this order
1. **langgraph-fundamentals** — graph shape and node/edge per gate
2. **langgraph-persistence** — SqliteSaver, thread_id = run_id, resume from the last node
3. **tdd** — transition table and commit-before-enqueue tests

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B04/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Start a run from S-02 -> screenshot b04-queued.png, then b04-running.png
2. Kill the worker -> screenshot b04-interrupted.png -> restart -> b04-resumed.png
3. Click Stop -> screenshot b04-stopped.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, start a run, kill and restart the worker, the run finishes
2. Playwright lifecycle spec passes

## If it goes wrong
RUN_MODE=fixture keeps the demo path on fixtures until real runs are stable.

## When finished
1. Make sure everything above is deployed (backend, worker, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B04 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B04: Durable runs that survive a worker crash`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

