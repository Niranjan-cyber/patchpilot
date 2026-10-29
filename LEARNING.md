# LEARNING.md: event log and lessons

Every session appends here after every event: a step started or finished, a decision, a bug found or fixed, a review, a takeover, a surprise. One entry per event, newest at the bottom: `- [YYYY-MM-DD HH:MM IST] <role> <EVENT|DECISION|BUG|FIX|REVIEW|LESSON>: what happened → what we learned or changed`. Keep each to 1–2 lines. messages.md is for talking; this file is the record.

## Planning (before code)
- [2026-10-29] A EVENT: feature scope, screen flows, architecture and contracts written → contracts v0.2 frozen before parallel work, so 3 sessions build against one definition.
- [2026-10-29] A LESSON: Cloudflare Quick Tunnels don't support SSE and change URL on restart → UI polls `/events?after=seq`; Tailscale Funnel gives the stable hostname OAuth needs.
- [2026-10-29] A LESSON: GitHub unauthenticated reads are 60/h per IP → server needs a read-only token (5,000/h).
- [2026-10-29] A LESSON: Groq free coding models cap at 8K tokens/min → Gemini Flash runs agent loops; Groq only short calls.
- [2026-10-30] A DECISION: no cross-run environment reuse (a setup step can plant a patched pytest) → per-run images; only proxpi (PyPI cache) and data-only install recipes are shared.
- [2026-10-30] A DECISION: user stops are never publishable; `STOPPED` outcome added; gates G0–G6 defined once in contracts §1.1.

## Build
- [2026-10-30] A EVENT: private repo Niranjan-cyber/patchpilot created; B=swaralipatil11, C=DevanshNarlawar06 invited and accepted.
- [2026-10-30] A EVENT: B02: contract models + `decide_outcome()` in code, 15 fixture runs generated from the models (valid by construction), fixture-mode API, React shell, S-03 stepper, S-04 proof panel. 37 tests + 6 Playwright checks.
- [2026-10-30] A BUG→FIX: fixture run pages had no "Sample data" label (sample data must always be labelled) → label shown for non-UUID run IDs.
- [2026-10-30] A LESSON: SupplyGuard (Devansh's Nexora_mindspark) is a TypeScript CLI, not a Python package; it reads requirements.txt / Pipfile.lock / poetry.lock but **not** pyproject.toml → demo repos need requirements.txt; pyproject-only repos come back inconclusive.
- [2026-10-30] B EVENT: draft PR #14: G3 evaluator + resume_at maths, 52 tests. A REVIEW: logic agreed; changes requested (use GateResult enum, tests in tests/, uv instead of requirements.txt).
- [2026-10-30] A LESSON: B posted on GitHub issues instead of messages.md (prompt predated the switch) → answered in both; re-stated the channel in messages.md.
- [2026-10-30] A DECISION: `GateResult(gate, status, reason, evidence_ids)` added to contracts so every gate returns the same shape.
- [2026-10-30] A EVENT: B04: SQLite store (runs/jobs/events/kv), run+job+event created in one transaction, worker with 60 s lease / 10 s heartbeat, LangGraph graph checkpointed in data/checkpoints.db, NODES registry for B/A to plug real steps into.
- [2026-10-30] A BUG→FIX: stub steps without a gate (Existing tests, Diagnose) were marked "Passed": a fake pass → stubs now report "Not run: this step isn't built yet". Caught by test_unbuilt_steps_never_fake_a_pass.
- [2026-10-30] A EVENT: B04 end-to-end on localhost: run created → worker killed mid "Existing tests" → /healthz showed worker false after 30 s → restarted worker took the expired lease → `run.interrupted` → `run.resumed` → finished. Kill/resume works outside tests too.
- [2026-10-30] A LESSON: until B05–B09 register real steps, real runs end "Stopped, report so far" with every step "Not run": honest, but don't demo real runs before B05.
