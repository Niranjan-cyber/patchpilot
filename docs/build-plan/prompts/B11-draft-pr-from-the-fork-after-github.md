# B11 — Draft PR from the fork after GitHub sign-in (M5)

Build step B11 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B11) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A signed-in contributor sees a draft PR opened from their fork after approving, with the next steps on S-07.

**Why now:** Completes the golden path; fork permissions are a stated risk.

## Slice
- Use cases: UC-05
- Screens: S-06, S-07
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- GitHub OAuth app (public_repo), Fernet-encrypted token, callback claims session runs
- Publisher: clean clone at base_sha, re-apply, hash checks 3/4/4a/4b, fork, push, draft PR with AI note + evidence
- Idempotent by head branch; branch_only -> compare link; download fallback
- GET /pr-status cached 10 min; S-07 what happens next

## Out of scope for this step
- GitHub App flow
- PR comment replies

## Acceptance criteria
- [ ] As the contributor account, approving planted bug #1 opens a draft PR from the fork against the upstream repo, visible to the maintainer account
- [ ] Publishing twice updates the same PR (Already exists state), never a second PR
- [ ] If PR creation is refused, S-07 shows Partial with a pre-filled compare link; if OAuth is cancelled, nothing is published and the diff download is offered
- [ ] The OAuth token never appears in logs, events, prompts or sandbox environments (grep test)
- [ ] If GitHub returns an error or secondary rate limit, S-07 shows Failed with Retry and nothing is half-published silently

## Page states to render
- S-06: setup, loading, success, failed
- S-07: loading, success, partial, failed

## Tests to write in this step (before calling it done)
- unit: publisher refuses on diff hash mismatch and on a changed SupplyGuard report
- integration: idempotent publish against a mocked GitHub (existing head branch -> update)
- integration: log + event + llm_calls grep finds no token pattern after a publish
- e2e: tests/e2e/publish.spec.ts against the team upstream repo

## Suggested tasks
- Register the OAuth app with callback <FUNNEL_URL>/auth/github/callback

## Skills — use in this order
1. **security-best-practices** — OAuth state, token storage, cookie flags
2. **write-pr-description** — the generated PR body: why, evidence, limitations, AI note
3. **security-review** — review the publisher and auth diff

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B11/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. S-06 Connect GitHub as the contributor -> screenshot b11-connect.png
2. Publish -> screenshot b11-pr-opened.png, open the PR on GitHub -> b11-github-pr.png
3. Publish again -> screenshot b11-already-exists.png
4. Cancel OAuth -> screenshot b11-oauth-cancelled.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, the contributor account opens a draft PR on the upstream repo from its fork
2. The maintainer account sees it with branch protection on
3. Playwright publish spec passes

## If it goes wrong
If the fork flow fails: branch_only + compare link (still an honest path for the demo).

## When finished
1. Make sure everything above is deployed (backend, worker, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B11 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B11: Draft PR from the fork after GitHub sign-in (M5)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

