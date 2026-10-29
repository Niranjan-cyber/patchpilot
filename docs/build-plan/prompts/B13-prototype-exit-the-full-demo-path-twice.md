# B13 — Prototype exit: the full demo path, twice

Build step B13 of **PatchPilot** (Prototype — 🏁 prototype exit). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B13) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A judge can walk the whole demo path on the URL and see an honest triage report on a second issue.

**Why now:** Prototype exit criteria and submission deliverables; feature freeze starts here.

## Slice
- Use cases: UC-01, UC-02, UC-03, UC-04, UC-05, UC-07
- Screens: S-01, S-02, S-03, S-04, S-05, S-06, S-07, S-08
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Full golden-path Playwright spec run twice in a row
- Remove every Sample data badge from the demo path
- Demo server banner + README (setup, architecture, limits, no-gVisor note)
- Recorded backup run, 3-min video, 6-slide deck
- healthz green before recording

## Out of scope for this step
- Any new feature (freeze)

## Acceptance criteria
- [ ] The golden-path spec passes twice in a row on <FUNNEL_URL> with no Sample data badge on the demo path
- [ ] A second issue ends in TRIAGE_ONLY or CANNOT_REPRODUCE with Download report
- [ ] No P0/P1 bug is open
- [ ] README, video (<= 3 min) and deck are linked from the repo

## Page states to render
- S-03: running
- S-04: success, failed
- S-07: success, failed

## Tests to write in this step (before calling it done)
- e2e: tests/e2e/golden-path.spec.ts
- e2e: tests/e2e/triage-path.spec.ts

## Suggested tasks
- Pre-warm proxpi with a rehearsal run
- Rehearse the demo twice

## Skills — use in this order
1. **code-review** — final pass over the main branch
2. **security-review** — last check of sandbox, auth and publisher before sharing the URL
3. **hackathon-demo-submission** — video script, README for judges, deck, submission checklist

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B13/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Run golden-path.spec.ts -> screenshots b13-01-issue.png .. b13-07-pr.png
2. Run triage-path.spec.ts -> screenshot b13-triage.png
3. Repeat once more -> all screenshots match

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, golden-path and triage-path specs pass twice in a row
2. Screenshots reviewed by two team members
3. Video, README and deck links exist

## If it goes wrong
Recorded backup run for the video if the live run fails on demo day.

## When finished
1. Make sure everything above is deployed (frontend, backend, worker) and the done-check passes on the public URL.
2. Set `"status": "done"` for B13 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B13: Prototype exit: the full demo path, twice`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Role A leads; everyone joins.

