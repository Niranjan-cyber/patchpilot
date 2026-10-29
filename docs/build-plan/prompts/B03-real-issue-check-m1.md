# B03 — Real issue check (M1)

Build step B03 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B03) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user who pastes a real GitHub issue URL on S-01 sees the real eligibility card on S-02.

**Why now:** First real external data source; Role C can build it while A builds the runtime.

## Slice
- Use cases: UC-01
- Screens: S-01, S-02
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- POST /api/issues/check
- GitHub reader with the server read-only token, ETag cache in issue_cache
- G0 checks: open, public, Python, tests found, unassigned, linked open PR via timeline cross-referenced events
- community/profile + README/CONTRIBUTING scan; AI-policy reading labelled Estimate
- URL validation: only github.com issue URLs (SSRF)

## Out of scope for this step
- Starting a run (B04)
- Limits (B12)

## Acceptance criteria
- [ ] pallets/click #3888 (fixture) shows the summary, repo card with pinned SHA and the checklist within 5 s
- [ ] A closed, assigned or linked-PR issue shows the Warning state with Find another issue / Start anyway
- [ ] A PR URL, private repo or non-Python repo shows the specific message from S-01/S-02 state tables, never a blank card
- [ ] GitHub 403/429 shows Failed with the retry time; a failed lookup shows Couldn't check, never a check mark

## Page states to render
- S-01: failed, success
- S-02: loading, success, partial, failed, empty

## Tests to write in this step (before calling it done)
- unit: G0 evaluation on fixture issue/timeline/repo/community JSON
- unit: issue URL parser rejects non-github hosts and PR URLs
- integration: /api/issues/check with mocked 429 returns GITHUB_UNAVAILABLE + retry_after
- e2e: tests/e2e/issue-check.spec.ts

## Suggested tasks
- Create the fine-grained read-only token, add to .env
- Parsers built against fixtures/github/*

## Skills — use in this order
1. **tdd** — G0 rules and the linked-PR detector on fixtures/github timeline samples
2. **security-best-practices** — URL validation and outbound request bounds
3. **frontend-design** — S-02 checklist card with Observed/Estimate labels

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B03/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Paste https://github.com/pallets/click/issues/3888 -> screenshot b03-success.png
2. Paste a closed issue from the team upstream repo -> screenshot b03-warning.png
3. Paste a PR URL -> screenshot b03-invalid.png
4. Paste a JavaScript repo issue -> screenshot b03-unsupported.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, paste a team upstream issue -> S-02 green checklist
2. Playwright issue-check spec passes against <FUNNEL_URL>

## If it goes wrong
issue_cache entries under 10 min old are shown labelled with fetch time if GitHub is rate-limited.

## When finished
1. Make sure everything above is deployed (frontend, backend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B03 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B03: Real issue check (M1)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

