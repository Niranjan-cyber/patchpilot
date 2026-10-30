# B01 — App shell live on the Funnel URL

Build step B01 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B01) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
Anyone can open the public Funnel URL and click through stub screens S-01 to S-08 labelled sample data.

**Why now:** Forces the real deploy path (laptop + FastAPI serving the SPA + Funnel) to work on day one; tests the Funnel risk first.

## Slice
- Use cases: UC-01
- Screens: S-01, S-02, S-03, S-04, S-05, S-06, S-07, S-08
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Repo layout: backend/ (api, worker, contracts, publisher), web/, tests/, scripts/
- FastAPI serves web/dist and GET /healthz
- React Router stubs for S-01..S-08 with a Sample data badge and the Demo server banner
- scripts/deploy.ps1 and Tailscale Funnel on 443
- Playwright harness + GitHub Actions smoke job against <FUNNEL_URL>

## Out of scope for this step
- Real data (B02+)
- Auth (B11/B12)
- Styling beyond a clean shell (frontend-design later per screen)

## Acceptance criteria
- [ ] GET <FUNNEL_URL>/ renders the app shell with navigation to all 8 stub screens, each showing a Sample data badge
- [ ] GET <FUNNEL_URL>/healthz returns JSON with db, worker, docker and llm_budget fields; unknown parts show false or unset, never true by default
- [ ] With the API stopped, the smoke job fails with a clear message (it doesn't pass on a cached page)

## Page states to render
- S-01: success, failed

## Tests to write in this step (before calling it done)
- integration: /healthz returns 200 with all fields present
- e2e: tests/e2e/shell.spec.ts opens every stub route

## Suggested tasks
- git push to the team GitHub repo
- Install Tailscale on the host, enable Funnel, note <FUNNEL_URL>
- Disable laptop sleep during build/demo week
- Add FUNNEL_URL as a GitHub Actions variable

## Skills — use in this order
1. **frontend-design** — pick the visual direction and app shell layout once, so later screens stay consistent
2. **code-review** — review the skeleton diff before everyone branches from it

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B01/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Open <FUNNEL_URL> from a phone on mobile data -> screenshot b01-shell.png
2. Click through S-01..S-08 -> screenshots b01-s01.png..b01-s08.png show the Sample data badge
3. Open <FUNNEL_URL>/healthz -> screenshot b01-health.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. Open <FUNNEL_URL> on a phone off the home network -> shell loads
2. GitHub Actions smoke job passes against <FUNNEL_URL>
3. Screenshots reviewed

## If it goes wrong
If Funnel fails on Windows: Cloudflare named tunnel (needs a domain); quick tunnels are not acceptable (no stable URL for OAuth).

## When finished
1. Make sure everything above is deployed (frontend, backend, infra) and the done-check passes on the public URL.
2. Set `"status": "done"` for B01 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B01: App shell live on the Funnel URL`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Whole team pairs on this; everyone needs the same layout and deploy path.

