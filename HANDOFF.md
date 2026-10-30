# HANDOFF: Role A session (Niranjan-cyber), 2026-10-30 ~02:35 UTC

Read this first in a new session, then `COORDINATION.md`, the tail of `messages.md` and `LEARNING.md`. Plan: `docs/build-plan/BUILD-PLAN.md`.

## Where things stand
- **Every plan step B01–B18 is code-complete on `main`**; 274 tests pass (`uv run pytest`). B19 code side is done too (gVisor via `PP_DOCKER_RUNTIME=runsc`, `infra/vm-setup.sh`).
- **Exit criteria NOT yet passed:** B13 (live golden path on the public URL) and B19 (always-on VM with gVisor). Both are human-gated (list below).
- Team: **C = DevanshNarlawar06** is active and reliable (reviews well, found two P1s). **B = swaralipatil11** has been silent since 2026-10-29 19:41 UTC; A took over B06 with her commits/authorship kept. No open PRs or P0/P1 bugs at handoff.

## Live testing status (started 2026-10-30)
- Gemini key is in `.env` as `GOOGLE_API_KEY` (config maps it to `GEMINI_API_KEY`). Model: `gemini/gemini-3.5-flash` (2.5-flash is closed to new keys). No Groq key → short calls use the same model.
- `config/limits.toml`: `global_llm_tokens_per_day = 600_000` is **PROVISIONAL**. Set the real value after a full measured run (tokens per run × planned runs/day), and record `budget_measured_tokens_per_run` / `budget_measured_on`.
- Live run 1 (itsdangerous #389): setup + baseline OK; Gemini 503 crashed it → **fixed** (503 = back off, then pause).
- Live run 2 `7a29e07b-1f6f-44c6-a0f3-3405d9876350` (itsdangerous #389, cookie jar `data/jarB`): reached REPRODUCE, then **paused on Gemini's free-tier DAILY quota** (resume 07:00 UTC). The 2 h pause cap ends it honestly at ~04:33 UTC. ⇒ **The free tier's request/day cap is the real bottleneck.** Options: a paid/higher-quota key, or run only the demo issue after the 07:00 UTC reset.
- Also seen live: G0 correctly refused itsdangerous #429 (an open linked PR exists).

## Running processes (this laptop)
- API: `uv run uvicorn backend.api.main:app --port 8000` (logs `data/api.log`); worker: `uv run python -m backend.worker.main` (`data/worker.log`). Started as Claude background tasks, so **they stop when this Claude session closes**. Restart with `scripts/deploy.ps1` or the two commands above.
- Before testing, check there's exactly one worker: `Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*backend.worker.main*' }`. Stale workers run old code (see LEARNING.md).
- Docker: `pp-base:3.12` image, `pp-proxpi` container on network `pp_setup` (`PROXPI_DOWNLOAD_TIMEOUT=600`). SupplyGuard is cloned at `data/tools/supplyguard` (`SUPPLYGUARD_CMD` in `.env`).
- The 20-min `/loop` job (`2ddc29a0`) is session-only; re-create it in the new session if wanted (prompt = the Role A tick in this file's last section).

## Human to-dos (blocking the exits)
1. **Public demo repo `Niranjan-cyber/tinycalc`**: the permission system blocks Claude from creating public repos even with your OK. The repo is built and committed locally at the scratchpad path `…/scratchpad/tinycalc`. Run yourself (from that folder): `gh repo create Niranjan-cyber/tinycalc --public --source . --push`, then create the 3 issues (divide by zero returns 0; mean([]) returns 0; parse_number("1,000") crashes). The issue texts are in LEARNING.md / this session's history. Or add a Bash permission rule for `gh repo create`.
2. `GITHUB_READ_TOKEN` (fine-grained, public repos, read-only) in `.env`: the anonymous 60 req/h limit is easy to hit.
3. Gemini quota: wait for the 07:00 UTC reset or use a higher-quota key.
4. Tailscale + `tailscale funnel --bg 8000` → set `PUBLIC_URL` in `.env`.
5. GitHub OAuth app (callback `PUBLIC_URL/auth/github/callback`) → `GITHUB_OAUTH_CLIENT_ID/SECRET`, plus `FERNET_KEY` (generate: `uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`).
6. B19: create the VM → `infra/vm-setup.sh` → `PP_DOCKER_RUNTIME=runsc`.

## Next steps for the new A session
1. Pull; check `messages.md` for C; review/merge C's PRs (merge locally if `LEARNING.md`/`messages.md` conflict: keep both sides).
2. After the quota reset: one full live run on a tinycalc issue (or itsdangerous #389) → read `GET /api/runs/{id}` + `/events`; fix what breaks (the trust gate applies); record tokens/run → set the real budget.
3. With the keys/URL ready: run `tests/e2e/golden-path.spec.ts` (`PP_DEMO_ISSUE=<tinycalc issue url>`) and `triage-path.spec.ts` against the Funnel URL → B13 exit. Then `scripts/eval.py` for the B14 numbers. Then B19 on the VM.
4. Keep `LEARNING.md` (one line per event) and `messages.md` (talk) updated; use `set -o pipefail` and `&&` before any commit (two slips so far).

## Role A tick (for `/loop 20m …`)
Role A session for PatchPilot (C:\Career\Hackathons\AgentX Hackathon). Each tick: git pull --rebase; read new entries in messages.md and reply to anything addressed to A or ALL; check B/C liveness per COORDINATION.md; review open PRs from B/C and merge if good; continue the current Role A step from HANDOFF.md "Next steps"; post HB in messages.md and push. Stop only when B13 and B19 exits pass.
