# B12 — Private runs and fair limits (UC-07)

Build step B12 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B12) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user's runs can only be opened from their own browser or GitHub account.

**Why now:** Isolation and abuse limits are P0 trust items before a public URL is shared with judges.

## Slice
- Use cases: UC-07
- Screens: S-01, S-06, S-08
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- pp_sid cookie (HttpOnly, Secure, SameSite=Lax), sessions table storing only the hash
- Owner scoping helper on every query; 404 for not-found and not-yours
- Limits from config/limits.toml: session 2/day, account 5/day, 1 active, global concurrency 1
- S-08 My runs + Forget this run; logging middleware strips cookies, auth, OAuth params; noindex + no-referrer headers

## Out of scope for this step
- My progress dashboard (MVP B16)

## Acceptance criteria
- [ ] A run URL opened in a second browser shows Sign in to see this run with no run details
- [ ] Browser A cannot read browser B's run, events or artifacts through any API path (404)
- [ ] A third run in one day from the same anonymous browser shows the session limit message on S-01
- [ ] Forget this run removes it from S-08 and the link stops working in that browser
- [ ] Daily limits from config/limits.toml are enforced on the server (session 2, account 5, 1 active); S-08 lists the user's runs

## Page states to render
- S-01: setup, success, failed
- S-06: setup
- S-08: empty, success, partial, failed

## Tests to write in this step (before calling it done)
- integration: every /api/runs/* and /api/artifacts/* route returns 404 for another session
- unit: limit counters per scope and day boundary
- integration: request logs contain no Cookie/Authorization/Set-Cookie values
- e2e: tests/e2e/access.spec.ts with two browser contexts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **security-best-practices** — cookie flags, header stripping, enumeration-safe 404
2. **tdd** — owner scoping and limit counters
3. **security-review** — review isolation before judges get the URL

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B12/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Start a run in context A, open its URL in context B -> screenshot b12-signin-required.png
2. Start 3 runs in context A -> screenshot b12-limit.png
3. S-08 with runs, then Forget one -> screenshots b12-myruns.png, b12-forgotten.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, two browsers cannot see each other's runs
2. Playwright access spec passes

## If it goes wrong
Keep main deployed and the golden path working; if this can't land, revert to the previous step's behaviour and report.

## When finished
1. Make sure everything above is deployed (backend, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B12 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B12: Private runs and fair limits (UC-07)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Role D also owns the shared page-state components and keeps the Playwright regression suite green for all roles.

