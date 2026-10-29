# B09 — Honest report with review and download (M4, G6)

Build step B09 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B09) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user can read a plain-language explanation and download a report whose every status matches the recorded results.

**Why now:** Every path must end in a trustworthy report before publishing is built on top.

## Slice
- Use cases: UC-04
- Screens: S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Reviewer (Groq, can only lower readiness)
- Explainer citing evidence IDs; G6 check, 2 regenerations, then deterministic template
- report.md + diff.patch downloads; POST /keep-report
- Retention reaper per contracts section 9 (logs 14 d, report 30 d, tombstone)

## Out of scope for this step
- Approval (B10)

## Acceptance criteria
- [ ] Every terminal outcome (all 15 fixtures + real runs) offers Download report and the report's statuses equal the run's gates
- [ ] An Explainer output claiming a passed check that was not run is rejected and the template report is shown instead
- [ ] Reviewer concerns turn Ready into Needs attention; the Reviewer can never raise readiness
- [ ] A run older than 14 days shows Logs expired; older than 30 days shows Details expired with outcome and PR link kept
- [ ] If report generation fails, the download still returns the deterministic template report, and the failure is shown in Show details

## Page states to render
- S-04: success, partial, failed, stale

## Tests to write in this step (before calling it done)
- unit: G6 integrity checker on 4 recorded Explainer outputs
- unit: Reviewer can only lower readiness
- unit: retention reaper on backdated rows
- e2e: tests/e2e/report.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **tdd** — G6: report statuses vs recorded statuses; claims without evidence IDs fail
2. **write-pr-description** — structure the report sections so they also feed the PR body later

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B09/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Open a finished planted bug #1 run -> screenshot b09-report.png and download report.md
2. Open the details_expired fixture -> screenshot b09-expired.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, download report.md for planted bug #1 and check its statuses against S-04
2. Playwright report spec passes

## If it goes wrong
If Groq is rate-limited, the Reviewer and Explainer fall back to Gemini; the fallback is shown in Show details.

## When finished
1. Make sure everything above is deployed (worker, backend, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B09 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B09: Honest report with review and download (M4, G6)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

