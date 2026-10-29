# B10 — Approve the exact diff, or revise (M5)

Build step B10 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B10) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user can approve the exact diff on S-05 after ticking the 3-item checklist.

**Why now:** The human gate the PS requires; the publisher depends on its hash contract.

## Slice
- Use cases: UC-05, UC-06
- Screens: S-05
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Canonical diff + evidence manifest hashing (contracts section 5)
- POST /approve with explanation; POST /revise (LangGraph interrupt/resume, revision + 1)
- Stale checks at approve: ISSUE_CHANGED, UPSTREAM_CHANGED via compare API, DEPS_REPORT_CHANGED
- POST /recheck-deps always voids approval
- Checklist + PR title/summary kept locally across polls

## Out of scope for this step
- OAuth + publishing (B11)

## Acceptance criteria
- [ ] Approve stays disabled until all 3 boxes are ticked; approving stores diff_hash and evidence_hash
- [ ] Revise (same screen) voids the approval, reruns Fix -> Verify, and S-05 shows the new diff
- [ ] If a file in the diff changed upstream, S-05 shows Stale (upstream) with Re-run on latest code and no approve-anyway
- [ ] A completed recheck-deps clears the checklist and shows Re-approve needed; a background poll never wipes typed text

## Page states to render
- S-05: success, stale, running, failed

## Tests to write in this step (before calling it done)
- unit: canonical diff hash is stable across CRLF/LF and path order
- unit: evidence manifest changes when supplyguard_report_id changes
- unit: compare API truncated (>300 files) -> UPSTREAM_CHANGED
- integration: approve with a stale revision returns APPROVAL_STALE
- e2e: tests/e2e/approve.spec.ts

## Suggested tasks
Decide the tasks yourself from the goal and the slice.

## Skills — use in this order
1. **langgraph-human-in-the-loop** — interrupt() at the approval node, resume on approve/revise
2. **tdd** — hash determinism, voiding rules, stale rules
3. **frontend-design** — S-05 diff view and checklist

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B10/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Open a verified run's S-05, tick boxes, approve -> screenshot b10-approved.png
2. Type a revise note, submit -> screenshot b10-revising.png
3. Push a change to the edited file on the upstream repo, reload -> screenshot b10-stale-upstream.png
4. Type in the PR summary while a poll completes -> screenshot b10-edit-kept.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, approve planted bug #1, then revise it and approve the new diff
2. Playwright approve spec passes

## If it goes wrong
Keep main deployed and the golden path working; if this can't land, revert to the previous step's behaviour and report.

## When finished
1. Make sure everything above is deployed (backend, worker, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B10 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B10: Approve the exact diff, or revise (M5)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Can start on fixture runs (verified_fix, upstream_changed) before B08 lands.

