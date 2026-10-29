# B19 — MVP exit: hardened host with gVisor

Build step B19 of **PatchPilot** (MVP — 🏁 MVP exit). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B19) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A real user can use PatchPilot on an always-on Linux host where sandboxes run under gVisor.

**Why now:** Replaces the prototype simplifications (laptop, no gVisor).

## Slice
- Use cases: UC-07
- Screens: S-01
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Oracle Always Free Arm VM, Docker Engine + runsc
- Same deploy script; data survives redeploy
- Remove the Demo server banner

## Out of scope for this step
- Scaling beyond 2 concurrent runs

## Acceptance criteria
- [ ] Sandbox containers report the runsc runtime
- [ ] Runs and reports survive a redeploy
- [ ] UC-08, UC-09 and UC-10 specs pass on the new host
- [ ] If runsc is missing or fails, the worker refuses to start runs and /healthz shows the failure

## Page states to render
- S-01: success, failed

## Tests to write in this step (before calling it done)
- integration: docker inspect shows runtime runsc for step containers
- e2e: full regression suite on the VM URL

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **container-hardening** — runtime flags under runsc
2. **security-review** — host and firewall review

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B19/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Run golden-path.spec.ts on the VM URL -> screenshots b19-*.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On the VM URL, the golden path and all MVP specs pass
2. Arm-specific install failures show honest ENV_FAILED

## If it goes wrong
If Oracle Arm capacity isn't available, stay on the laptop and keep the Demo server banner.

## When finished
1. Make sure everything above is deployed (infra, backend, worker, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B19 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B19: MVP exit: hardened host with gVisor`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

