# B05 — Real setup and baseline in a per-run sandbox (M2)

Build step B05 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B05) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user who starts a run on a team demo repo sees the real install and the real baseline test results on S-03.

**Why now:** Riskiest unknown: setup is where most runs fail, and Docker Desktop on Windows is unproven.

## Slice
- Use cases: UC-02
- Screens: S-03, S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- Tarball at base_sha extracted by the worker, git init + baseline commit in a volume
- SupplyGuard scan() adapter -> G1 (blocked, no override; inconclusive -> DEPS_INCONCLUSIVE)
- proxpi container on --internal network; per-run image pp-run-<id> from a pinned base digest
- G2: uv install within 480 s, pytest --collect-only; one AI-free retry path stubbed until B06
- Baseline: pass/fail/flaky sets, failures rerun once, --network none
- Sandbox flags from architecture section 7
- env_recipes rows (data only)
- POST /api/runs/{id}/false-positive

## Out of scope for this step
- AI-assisted install retry (B06 adds the LLM)
- gVisor (MVP)

## Acceptance criteria
- [ ] A team demo repo installs and S-03 shows the baseline counts; a known-failing test is listed as already failing
- [ ] A repo pinning a known typosquat package (test fixture) shows S-04 Blocked with Report a false positive and no override
- [ ] SupplyGuard raising an error shows Dependency check inconclusive and the run continues with publishing disabled
- [ ] A repo whose install fails shows S-04 Setup failed with the install log; a step container can reach no network (curl fails)
- [ ] A second run on the same repo installs into a fresh image; no container, volume or image from the first run is reused

## Page states to render
- S-03: running, partial, failed
- S-04: failed, partial, success

## Tests to write in this step (before calling it done)
- unit: G1 mapping of SupplyGuard results (clean, malicious, error, unsupported)
- unit: baseline pass/fail/flaky from two recorded pytest JSON reports
- integration: step container has no network and no env secrets
- integration: per-run image naming and cleanup after the run leaves RUNNING
- e2e: tests/e2e/setup.spec.ts

## Suggested tasks
- Pin python base image digests
- Write the SupplyGuard adapter with its owner
- Measure first and second install time on each demo repo

## Skills — use in this order
1. **container-hardening** — docker run flags, non-root, read-only root, tmpfs
2. **tdd** — G1/G2 evaluation and baseline set computation on recorded outputs
3. **security-review** — review sandbox flags, mounts and network isolation
4. **diagnosing-bugs** — when Docker Desktop or proxpi misbehave

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B05/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Start a run on upstream bug #1 -> screenshot b05-baseline.png
2. Start a run on the typosquat fixture repo -> screenshot b05-blocked.png
3. Start a run on the broken-install fixture repo -> screenshot b05-envfailed.png
4. Run with SupplyGuard forced to error -> screenshot b05-inconclusive.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, a real run on the demo repo reaches baseline with correct counts
2. Blocked, Setup failed and Inconclusive render as distinct states
3. Playwright setup spec passes

## If it goes wrong
If Docker Desktop networking blocks proxpi, pre-download wheels into proxpi from the host before the run (still PyPI-only).

## When finished
1. Make sure everything above is deployed (backend, worker, infra) and the done-check passes on the public URL.
2. Set `"status": "done"` for B05 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B05: Real setup and baseline in a per-run sandbox (M2)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Record setup time per repo; it feeds the S-03 time estimate and the eval slide.

