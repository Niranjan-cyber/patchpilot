# PatchPilot

**Paste a GitHub issue. PatchPilot reproduces the bug in a locked-down sandbox, tests a fix, and shows you the proof: the same test failing on the original code and passing after the fix, in a brand-new sandbox. You decide whether to open a draft pull request.**

Built for AgentX Hackathon 2026, PS-05 (bug-fix agent for code repositories).

## Why it's different
- **Proof, not promises.** A fix counts as verified only when a new test fails twice on the original code and passes twice after the fix, in a fresh container, with every previously passing test still passing.
- **Honest when it can't.** When it can't verify a fix, you get a triage report (the reproduction, the likely cause, what was tried), never a fake "fixed".
- **Works on repos you don't own.** Paste any public Python issue; publishing goes through your fork.
- **For first-time contributors too.** Plain-language steps, a short codebase tour, and "What's this?" help for every term.
- **A human always decides.** Draft PRs only, after you approve the exact diff. Nothing is merged automatically.

## How it works
```
Issue URL → eligibility + contribution-policy check → SupplyGuard dependency check
→ install in a sandbox (PyPI only) → run existing tests (baseline)
→ AI writes a failing test (must fail 2/2) → diagnosis → small fix (diff policy)
→ verify in a FRESH sandbox (2/2 green + no regressions) → review → report
→ you approve the exact diff → draft PR (direct or via your fork)
```
AI roles only propose. Code decides every status (gates G0–G6, `docs/contracts.md`).

## Safety
- Repository code runs only in sandboxes: non-root, all capabilities dropped, read-only root filesystem, CPU/memory/process limits, **no network after setup** (setup can reach PyPI only, through a caching proxy).
- Each run builds its own environment; nothing built by repository code is reused by another run.
- Credentials never reach the sandbox or the AI. Only the publisher holds a GitHub write token.
- Dependency check with **SupplyGuard**: known-malicious or typosquatted packages block the run; a check that couldn't complete turns publishing off.
- Prototype limitation: on the demo laptop (Docker Desktop) sandboxes run without gVisor. Use controlled demo repositories only. The MVP host adds gVisor.

## Run it locally
Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, Docker.
```bash
cp .env.example .env              # fill what you have; GITHUB_READ_TOKEN strongly recommended
uv sync
cd web && npm ci && npm run build && cd ..
docker build -t pp-base:3.12 -f infra/Dockerfile.base infra
uv run uvicorn backend.api.main:app --port 8000      # terminal 1
uv run python -m backend.worker.main                 # terminal 2
```
Open http://localhost:8000. Sample runs (labelled "Sample data") show every outcome without any setup. On Windows, `./scripts/deploy.ps1` does all of the above.

Tests: `uv run pytest` (unit + Docker integration) and `npx playwright test` (browser checks, from the repo root with the app running).

## Repository map
| Path | What |
|---|---|
| `backend/contracts/` | shared types, gates, outcome rules (source of truth: `docs/contracts.md`) |
| `backend/api/` | FastAPI: serves the app and the run API |
| `backend/worker/` | durable job queue, LangGraph pipeline, crash/resume |
| `backend/sandbox/` | Docker sandboxes, setup, baseline, SupplyGuard adapter |
| `backend/agents/`, `backend/gates/` | AI roles and gate evaluators |
| `web/` | React app |
| `docs/` | feature scope, screen flows, architecture, contracts, build plan |

## Team
Three people, each paired with a Claude Code session: see `COORDINATION.md`, the live channel `messages.md`, and the decision log `LEARNING.md`.
