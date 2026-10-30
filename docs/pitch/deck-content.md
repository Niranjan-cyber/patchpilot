# PatchPilot: idea deck content (6 slides)

AgentX Hackathon 2026 (Hack4Hack), **PS-05**. Rules: idea deck **≤ 6 slides, submitted as a link, due 30 Oct 2026, 11:59 PM IST**. Judging: problem fit and impact 25% · agent design 25% · working demo and reliability 20% · innovation 15% · presentation 15%.
Every number below comes from a real run on 2026-10-30, or from the frozen contracts. Nothing is projected.
**To confirm before you submit:** the teammates' full names (taken from their GitHub handles) and the official PS-05 wording (slide 2 paraphrases it).

---

## Slide 1: PatchPilot · Team

**Title:** PatchPilot
**Subtitle:** From a GitHub issue to a fix you can verify: reproduced, fixed and proven in a sandbox before anyone opens a PR.

**Team**
| Member | Role |
|---|---|
| Niranjan Iyer (A) | Platform lead: worker and orchestration, LLM gateway, sandbox, publisher, deployment |
| Swarali Patil (B) *(confirm surname)* | Reproduction gate (G3), report and review screens, deployment (MVP host) |
| Devansh Narlawar (C) *(confirm surname)* | Supply-chain check (SupplyGuard), setup hardening, evaluation set, UI design |

**Visual:** the run-page proof strip, red red → green green (`docs/evidence/run-7b57e1fb/run-page.png`).

*Speaker note:* "PatchPilot doesn't just write a patch. It proves the bug existed and proves the fix removes it, in a container it has never touched."

---

## Slide 2: Problem statement and the core problem

**Problem statement (PS-05, paraphrased; replace with the official wording):** build an AI agent that takes a reported bug in a codebase and produces a fix, backed by tests that pass after the fix.

**The core problem: an untested AI patch costs maintainers time instead of saving it.**
- Reproducing a bug from an issue means cloning, setting up an environment, reading unfamiliar code and guessing. That takes hours, and first-time contributors often give up.
- AI coding agents skip that step and open PRs that "look right". Maintainers now ban or ignore them: a PR that fails the test suite gets no attention (curl's maintainer, opensourcesecurity.io, 2025).
- Even research systems write a valid fail-then-pass test only **19–70%** of the time (SWT-bench). When an AI can't prove a fix, it needs to say so honestly.
- Running a stranger's repository code is a security risk: malicious packages and typosquats arrive through installs.

**Who feels it**
- **First-time contributors**, who found an issue and don't know where to start.
- **Maintainers and triagers**, who want a reproduction and a tested fix, not a guess.

*Speaker note:* "The gap isn't writing code. It's trust: proof that the bug is real and that the fix fixes it."

---

## Slide 3: The solution: a proof-carrying fix

**Paste one public issue URL. PatchPilot does five things:**
1. **Checks eligibility and policy:** the issue is open and unassigned with no competing PR, and the repo's AI-contribution policy is read.
2. **Sets up a sandbox:** a supply-chain scan *before* any install, then install and baseline tests in a locked-down container.
3. **Reproduces, diagnoses and fixes:** AI roles write a test that **fails twice** on the original code, find the cause, and write a minimal fix.
4. **Verifies in a brand-new container:** the same test goes **green twice**, and every test that passed before still passes. ⭐
5. **Human approval, then a draft PR:** you approve the exact diff (hash-locked), sign in with GitHub, and a **draft** PR opens with the evidence attached. Or you keep the honest report.

**Live proof from today (all real):**
- 3 of 3 planted bugs fixed correctly, each in about **2–7 minutes**: 2 × VERIFIED_FIX and 1 × FIX_NEEDS_ATTENTION, where the reviewer flagged a behaviour change.
- The full path ran twice on the public URL, with real GitHub sign-in, and opened draft PRs [tinycalc #4](https://github.com/Niranjan-cyber/tinycalc/pull/4) and [#5](https://github.com/Niranjan-cyber/tinycalc/pull/5).
- When a fix can't be proven, the run ends as **TRIAGE_ONLY / CANNOT_REPRODUCE** with the evidence, never a fake "fixed".

**Visual:** the five steps as a horizontal flow, and a screenshot of PR #4 (Summary · Evidence · Limitations · AI-assistance note).

---

## Slide 4: High-level architecture and tech stack

**Diagram (redraw as boxes, grouped in three trust zones):**
```
 Browser (React SPA) ──HTTPS (Tailscale Funnel)──▶ FastAPI API ──▶ SQLite (runs, jobs, events) + artifact store
                                                        │                (content-addressed evidence)
                                                        ▼
                                         Worker: LangGraph pipeline + code gates
                                           │            │               │
                                  LLM gateway     Docker sandboxes   Publisher (only holder of the
                                  (LiteLLM:       (no network, no    user's GitHub token; clean clone
                                   Groq → Nebius   credentials;      outside the sandbox → draft PR)
                                   → Gemini)       gVisor on MVP)
                                                        │
                                              proxpi (PyPI-only cache, setup only)
```
**Trust zones:**
- **Untrusted:** sandbox containers. No credentials, no network after setup.
- **Semi-trusted:** the LLM gateway. It sees code and issue text, never tokens, and secrets are redacted.
- **Trusted:** API, worker, publisher, database. The API never runs repository code.

**Tech stack**
| Layer | Choice |
|---|---|
| Frontend | React + Vite, served by FastAPI (same origin) |
| API | FastAPI + Uvicorn |
| Orchestration | Python worker · **LangGraph** with SQLite checkpoints · mini-SWE-agent-style shell loop |
| LLMs | LiteLLM gateway with fallback by quota: Groq gpt-oss-120b → Groq Qwen3.8-27B → Nebius gpt-oss-120b → Gemini 3.8/3.5 Flash |
| Sandbox | Docker (cap-drop ALL, read-only, non-root, pids/memory limits, no network) · **gVisor** on the MVP VM |
| Supply chain | SupplyGuard (our own analyzer) before any install · proxpi PyPI-only proxy |
| Data | SQLite (WAL) + sha256 content-addressed artifact store |
| GitHub | Read-only token for reading · OAuth (`public_repo`) for publishing only |
| Hosting | Tailscale Funnel (stable HTTPS URL) → laptop (prototype) / Oracle Always Free VM with systemd (MVP) |

---

## Slide 5: Agent orchestration and data model

**Orchestration: the AI proposes, code decides.**
LangGraph pipeline: `intake → preflight → setup → baseline → reproduce → diagnose → fix → verify → review → report → approval → publish`

| Agent role | What it does | The gate that judges it (code, not the LLM) |
|---|---|---|
| — (rules) | issue + repo checks | **G0 Eligibility**: open, public, Python, tests found, unassigned, no linked PR |
| — (SupplyGuard) | dependency scan before install | **G1 Pre-flight**: blocks confirmed malicious or typosquat packages |
| Setup | install + collect tests | **G2 Setup**: install OK and ≥ 1 test collected |
| Test designer | writes the reproduction test | **G3 Reproduction**: fails in **both** runs, on an assertion or the issue's error |
| Investigator | finds the cause | every cited evidence ID and file:line must exist |
| Fixer | writes the minimal fix | **G4 Diff policy**: source only, ≤ 5 files / 200 lines, no test or dependency edits |
| — (fresh container) | re-runs everything | **G5 Verification**: new test green 2/2 and the whole baseline still green |
| Reviewer + Explainer | shortcut check, report | **G6 Report integrity**: every status equals the recorded status, every claim cites evidence |

**Reliability built in:**
- Bounded retries per role; loop detection.
- Quota-aware model fallback: waits for short rate limits, skips models until their known reset time, pauses honestly when everything is out.
- Per-run and daily token budgets.
- Crash-safe resume via checkpoints + job leases.
- Six deterministic outcomes: VERIFIED_FIX · FIX_NEEDS_ATTENTION · TRIAGE_ONLY · CANNOT_REPRODUCE · ENV_FAILED · BLOCKED.

**Memory:** the env-recipe store replays install commands that worked, as data only, never a reused image. Every LLM call is logged per role for budgets and evaluation.

**Data model (SQLite):**
- `runs` (owner-scoped state), `jobs` (leases, heartbeats), `events` (append-only timeline)
- `artifacts` (sha256 evidence IDs), `approvals` (diff_hash + evidence_hash), `publications` (PR link and state)
- `accounts` (GitHub token, Fernet-encrypted, decrypted only by the publisher), `sessions` (hashed)
- `env_recipes`, `llm_calls`, `usage_counters`, `issue_cache`

**Rule:** every query is scoped to the run's owner; unknown is NULL, never 0 or "clean".

---

## Slide 6: Features · impact · benefits · feasibility · scalability

**Key features**
- The ⭐ **proof strip**: the same test red 2/2 on the original code → green 2/2 in a fresh container.
- **Honest outcomes:** a triage report with evidence instead of a fake fix.
- **Supply-chain pre-flight** and a hardened sandbox before running any repo code.
- **Human-in-the-loop:** you approve the exact hash-locked diff, then a draft PR is opened under *your* GitHub account, with an AI-assistance note.
- Extra checks: hidden test variant, code-decided review concerns (e.g. a swallowed `except`), "Ask why" answers grounded in evidence, explore a repo for good first issues.

**Impact and benefits**
- **Contributors:** from "I found an issue" to a reviewable, tested draft PR in minutes, without setting up anything locally.
- **Maintainers:** PRs arrive with proof (a fail-then-pass test, the baseline intact, the base commit pinned), so there's less AI slop and faster review.
- **Trust:** every status on screen traces to a recorded run, and the evidence can be downloaded.

**Feasibility (it already works)**
- Built and running: the full pipeline, **326 automated tests**, end-to-end browser tests.
- The B13 exit passed twice on a public URL with real draft PRs.
- Runs on **free tiers** (Groq/Gemini) with a ~$0.05/run paid fallback (Nebius). A tinycalc run uses ~45k tokens.
- An evaluation set of 10 SWE-bench-Live cases (checked to grade honestly in our sandbox) plus 3 planted bugs.

**Scalability**
- Stateless API + leased job queue → more workers = more parallel runs. Sandboxes are per-run and disposable.
- Model-agnostic gateway: add providers or models by configuration; quota-aware fallback.
- Next steps: an always-on VM with gVisor (deploy kit ready; for the prototype the demo runs on a laptop behind Tailscale Funnel), a durable queue (e.g. Redis/Postgres) for multiple workers, JS/TS support, and CI-failure triggers.

*Speaker note:* "Other agents compete on autonomy. We compete on verification integrity: if PatchPilot says it's fixed, you can see the proof."

---

### Assets to use
- Run page (real VERIFIED run): `docs/evidence/run-7b57e1fb/run-page.png`
- Draft PRs: https://github.com/Niranjan-cyber/tinycalc/pull/4, https://github.com/Niranjan-cyber/tinycalc/pull/5
- Home screen (new design, pass 1): `docs/evidence/redesign-pass1-home.png`
- C already built a 6-slide deck (on Devansh's machine). Merge this content into it rather than starting over.
