# B06 — AI reproduction test that fails 2/2 (M3, G3)

Build step B06 of **PatchPilot** (Prototype). Paste this into Claude Code / Codex / Cursor at the repo root. Do only this step.

## Read first
- `docs/build-plan/BUILD-PLAN.md` (section B06) and `docs/build-plan/plan.json`
- `AGENTS.md`, `SKILL-PLAYBOOK.md`, `SKILLS.md`
- `uploaded patchpilot_product_updated1.md` (Brief)
- `docs/patchpilot-feature-scope.md` (Feature scope)
- `docs/patchpilot-screen-flows.md` (Screen flows)
- `docs/patchpilot-architecture.md` (Architecture)
- `docs/contracts.md` (Contracts)
- `fixtures/github/` (Fixtures)

## The goal (the only goal of this step)
A user sees PatchPilot write a test that fails twice on the original code for the demo bug, with its output on S-03.

**Why now:** Second riskiest unknown: free-tier quota and model quality decide whether the product works at all.

## Slice
- Use cases: UC-03
- Screens: S-03, S-04
- Components: —
- Stack: frontend: React + Vite SPA built to web/dist, served by FastAPI (same origin); backend: FastAPI API + separate Python worker (LangGraph, mini-SWE-agent), SQLite WAL, Docker Desktop sandboxes, proxpi; ai: LiteLLM SDK -> Gemini Flash (free); Groq for short calls; hosting: Windows host laptop exposed via Tailscale Funnel; deploy = scripts/deploy.ps1 (git pull, build SPA, restart API + worker)

## In scope
- llm_gateway.py: LiteLLM, token accounting in llm_calls, per-run and global budgets, redaction, Groq for short calls
- Pause on 429: resume_at only from retry-after or the Gemini midnight PT reset, else null; 2 h max pause
- mini-SWE-agent Test designer in a --network none container, step limit 15-20, Pydantic JSON result
- G3 per contracts 1.1; retries 2; CANNOT_REPRODUCE
- AI-assisted install retry for G2 (install commands only)
- Measure tokens per run -> set budget_measured_tokens_per_run and global_llm_tokens_per_day

## Out of scope for this step
- Diagnosis and fix (B07)

## Acceptance criteria
- [ ] On planted bug #1, the new test fails 2/2 with an assertion error and S-03 shows its output
- [ ] A test failing with ImportError or failing only 1 of 2 runs is rejected and retried; after 2 retries S-04 shows Can't reproduce
- [ ] Hitting the provider limit shows S-03 Paused with a time only if the provider gave one; over 2 h -> run ends with the report so far
- [ ] With global_llm_tokens_per_day unset, POST /api/runs returns LIMIT_GLOBAL_BUDGET and /healthz is red

## Page states to render
- S-03: running, partial, failed
- S-04: failed

## Tests to write in this step (before calling it done)
- unit: G3 evaluation on 5 recorded pytest outputs (assertion, issue error, ImportError, collection error, flaky)
- unit: resume_at computation from retry-after and the PT midnight rule; null otherwise
- integration: invalid role JSON counts as a failed attempt
- integration: budget unset blocks run creation
- e2e: tests/e2e/reproduce.spec.ts

## Suggested tasks
- Gemini API key in .env
- Run the M3 feasibility test on all 3 planted bugs, record tokens

## Skills — use in this order
1. **tdd** — G3 rules on recorded test outputs (assertion vs import/collection error, flaky 1/2)
2. **langgraph-fundamentals** — replace the reproduce stub node, retry edges
3. **diagnosing-bugs** — when the agent loop stalls or misreads output

Always-on rules for every step: **Ponytail rules in AGENTS.md**.

## Browser check (on the deployed URL, with screenshots)
Run with Playwright (tests/e2e/, run against <FUNNEL_URL> from GitHub Actions and locally) + Playwright MCP for screenshot review. Save screenshots to `docs/build-plan/evidence/B06/` and look at each one before calling the step done. Also re-run the earlier steps' browser checks for the golden path.
1. Start a run on planted bug #1 -> screenshot b06-repro.png (fails 2/2)
2. Run the no-repro fixture issue -> screenshot b06-cannot.png
3. Force a 429 from the gateway stub -> screenshot b06-paused.png

## Done when (check on the deployed app, not locally)
Build, lint and type-check passing is not evidence that this step works.
1. On <FUNNEL_URL>, planted bug #1 reaches a 2/2 failing reproduction
2. Measured tokens per run recorded in config/limits.toml
3. Playwright reproduce spec passes

## If it goes wrong
If Gemini Flash can't reproduce within budget: shorten prompts, reduce context to the files in the traceback, or try Flash-Lite; record the result for the deck.

## When finished
1. Make sure everything above is deployed (worker, backend, frontend) and the done-check passes on the public URL.
2. Set `"status": "done"` for B06 in `docs/build-plan/plan.json`, then run `python C:\Users\Niranjan Iyer\.claude\skills\synced\4388f05c-eb72-4dd8-a66b-700dfbb34581_a5c3319d-ef87-457c-8cc8-fe986ddce72a\prototype-build-planner\scripts\build_plan.py render docs/build-plan/plan.json`.
3. Commit as `B06: AI reproduction test that fails 2/2 (M3, G3)`.
4. Report what changed, the test output, the browser-check screenshots and the done-check result, then stop. Don't start the next step without being asked.
5. If you found a bug you didn't fix, add it to `bugs` in `plan.json` with a severity (P0 correctness/safety, P1 trust/core loop, P2 polish). An open P0/P1 blocks the next feature step.

## Notes
Role B can start on recorded outputs and a stub sandbox while B05 finishes.

