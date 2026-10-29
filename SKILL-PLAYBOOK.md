# SKILL-PLAYBOOK.md: PatchPilot

**Build mode: Sprint** (hackathon; build round 11 Nov 10:00 → 12 Nov 10:00 IST; demo by 12–14 Nov). Ceremony: a 5-line task card instead of a spec, tests on logic only, a browser check on the public URL, a light review. Skills inventory: `SKILLS.md`. Contracts are law: `docs/contracts.md`.

## Roles: one lead each
| Role | Lead | Others / notes |
|---|---|---|
| clarify | none: re-read the docs section; ask the user | the user-level `grilling` plugin is off for this project |
| spec / plan | `docs/` + `docs/build-plan/` (prototype-build-planner, user-level) | no spec skill in Sprint mode |
| build: worker graph | `langgraph-fundamentals` | `langgraph-persistence` only for checkpoints/resume; `langgraph-human-in-the-loop` only for approve/revise `interrupt()` |
| build: sandbox | `container-hardening` | architecture §7 recipe wins on any conflict |
| build: API / backend | none: FastAPI docs by section | `security-best-practices` (python-fastapi reference) for cookies, OAuth, publisher |
| ui | `frontend-design` | the user-level plugin copy isn't enabled, so no conflict |
| test | `tdd` | gates, outcome table, hashing, limits, parsers |
| debug | `diagnosing-bugs` | its HITL script runs only when you choose to |
| review | built-in `/code-review` | built-in `/security-review` for sandbox, auth, publisher, logging diffs |
| qa / browser check | Playwright MCP (user-level) | screenshots reviewed before a step is done |
| docs / PR | `write-pr-description` | also the source for PatchPilot's generated PR body |
| ship / demo | built-in `run`; user-level `hackathon-demo-submission` (video, README, deck) | — |
| modifier (always on) | Ponytail rules in `AGENTS.md` | the Ponytail plugin is off, so its rules aren't loaded twice |

Gaps (no skill, work normally): FastAPI, mini-SWE-agent, LiteLLM, the GitHub API: read their docs by section.

## Phases
| # | Phase | Exit check | Chain | Skip in Sprint |
|---|---|---|---|---|
| 0 | Prep | contracts v0.2 frozen; `fixtures/runs/*` exist; demo GitHub accounts + planted-bug repo ready; Funnel URL reachable | `tdd` (contract tests replay fixtures) | a separate design phase |
| 1 | Walking skeleton (B01–B02) | SPA served by FastAPI on the Funnel URL; S-01→S-04 render fixture runs via `/api/runs/{id}` + polling | `frontend-design` → build → Playwright check → `/code-review` | pixel polish |
| 2 | Sandbox + setup + baseline (riskiest) | a real repo installs in a per-run image; baseline sets recorded; ENV_FAILED/BLOCKED shown | `container-hardening` → `tdd` (G1/G2) → build → `/security-review` | gVisor (MVP) |
| 3 | Agent loop + gates | repro fails 2/2; G3/G4 enforced; kill-worker test resumes | `langgraph-fundamentals` → `langgraph-persistence` → `tdd` (gates, outcome table) → build → `/code-review` | hidden variant (S4) |
| 4 | ⭐ Verify + report | fresh-container red → green on S-04; every outcome state renders | `tdd` (G5/G6, readiness) → build → `frontend-design` (proof panel) → Playwright | — |
| 5 | Approve + publish | approve → OAuth → draft PR from the fork; hash, stale and upstream checks refuse correctly | `langgraph-human-in-the-loop` → `tdd` (hash contract) → `security-best-practices` → build → `/security-review` → `write-pr-description` (PR body) | GitHub App flow |
| 6 | Prototype exit + demo | demo path walked twice on the URL; triage path shown; README, video, deck | Playwright full walk → `/code-review` → `hackathon-demo-submission` | new features (freeze) |
| 7 | Should (S1–S6), only after phase 6 | per the feature scope | per step | — |

## Switch triggers
- Unexpected error or failing test → `diagnosing-bugs`, then back.
- A wrong outcome, status, gate result, or a failure shown as empty/"clean" → stop features; `diagnosing-bugs` + a regression test first (trust gate).
- Touching the sandbox flags, cookies, OAuth, tokens, publisher or log redaction → `security-best-practices` while coding, `/security-review` on the diff.
- UI inside a backend task → `frontend-design` for that part.
- Build/lint passes → not done; run the Playwright check on the Funnel URL.
- Async work (jobs, polling) → test commit-before-enqueue and stale-response handling.
- `.env` / deploy config → edit one variable at a time and verify.
- Slice done → `/code-review` → `write-pr-description` → PR.

## Token rules
One step per session, then `/clear`. Load only the chain's skills. Read doc sections, not whole files. `tail` logs.
