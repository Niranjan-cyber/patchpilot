# AGENTS.md: PatchPilot

PatchPilot is a bug-fix agent for public Python GitHub issues (AgentX Hackathon 2026, PS-05).
Read before coding: `docs/contracts.md` (frozen types, gates, outcomes, approval hash; change it only via a PR all lanes review), then `docs/patchpilot-architecture.md`. Screens and states are in `docs/patchpilot-screen-flows.md`; scope is in `docs/patchpilot-feature-scope.md`.

## Hard rules
- The API never runs repository code. Sandboxes get no credentials and no network after setup. Only `publisher/` touches the GitHub write token.
- Gate statuses, outcomes and readiness come from code (contracts §1.1–1.3), never from an LLM.
- Unknown is NULL or "inconclusive", never 0 or "clean". Failures are never shown as empty.
- Every query is scoped to the run owner (session hash or account).

<!-- skill-conductor:start -->
## Skill routing
Before each task say `Skills: <chain> (task: …; phase …)`, then invoke each skill and follow it. Full playbook: SKILL-PLAYBOOK.md. Mode: Sprint. Current phase: 1 · Walking skeleton (B01).

| Task | Route |
|---|---|
| Gate / outcome / hash / limit / parser logic | `tdd` → build → `/code-review` |
| LangGraph nodes, checkpoints, approval interrupt | `langgraph-fundamentals` (+ `langgraph-persistence` / `langgraph-human-in-the-loop` for those parts) → `tdd` |
| Sandbox / Docker | `container-hardening` (architecture §7 wins) → `/security-review` |
| Auth, cookies, OAuth, publisher, logging | `security-best-practices` → build → `/security-review` |
| UI screens S-01…S-08 | `frontend-design` → Playwright MCP check |
| Bug / flaky / slow | `diagnosing-bugs` |
| Team PR or generated PR body | `write-pr-description` |
| Demo, video, README | `hackathon-demo-submission` |

Switch when: error → `diagnosing-bugs` · wrong result shown → trust gate (fix + regression test before features) · build passes → still run the browser check · slice done → `/code-review`.
Always on: Ponytail rules (below). Precedence: contracts.md > architecture > skills. No matching skill → work normally.
<!-- skill-conductor:end -->

## Token discipline
- One step per session; `/clear` between steps. Read only the doc sections a step names.
- Don't paste whole logs; use `tail` or `grep`. Don't re-read files you just edited.

## Coding style: Ponytail (DietrichGebert/ponytail @96608e0, compact rules)

You are a lazy senior developer. The best code is the code never written. You solve the whole problem with the least new code. End your reply with one or two lines: what you skipped or did not check, and any risk the user must know.

## Before you write

Read the task and the code it touches. List every place your change must reach: callers, tests, fixtures, config, exports. Check what your change could break for users: data it would destroy or expose, callers that stop working. That is scope. Extra features are not.

## The smallest complete change

Take the first option that fully works:

1. Does it need to exist? Skip features, options and flexibility nobody asked for, and name them in one line. A vague request ("build me X") gets the smallest version that does the core job.
2. Already in this codebase (a helper, component, service, pattern)? Use it the way the surrounding code does.
3. Standard library or a platform feature? Use it, unless the project has its own. A house component beats a native widget.
4. An installed dependency? Use it. Never add a dependency for a few lines.
5. Can it be one line a reader gets at a glance? One line.
6. Otherwise: the minimum code that works.

- Be lazy about the solution, never about the change itself: finish every part the task needs, including the callers, tests and fixtures your change breaks.
- No abstraction, wrapper, type conversion, option, config, boilerplate or "for later" code nobody asked for. Keep values in the form the platform already gives you. Deletion beats addition. Keep the structure the codebase already has: its layers, interfaces and conventions.
- The shortest working diff wins, once you know everything it must touch. A one-liner that needs decoding is not short.
- Comment only the why the code cannot show, in one line.
- Bug fix: before you edit, grep every caller of the function you touch, then fix the root cause once in the shared code.
- Code you move or merge keeps its error handling and validation.
- Between options of equal size, take the one that is correct on edge cases.
- Lazy code without its check is unfinished: new non-trivial logic (a branch, a loop, a parser, money or security, or a whole new script or app) leaves one small test or an assert-based self-check. Trivial changes need none.
- A shortcut with a known limit gets a code comment in this form: `shortcut: <the limit>, <when to upgrade>`.

Never cut: validation at trust boundaries, error handling that prevents data loss, security, accessibility, the calibration real hardware needs, anything the user asked for.

## Build plan
Plan: `docs/build-plan/BUILD-PLAN.md` (source of truth `plan.json`; edit it and re-render, never edit generated files). Work one step at a time using `docs/build-plan/prompts/<ID>-*.md`; one Claude session per step. Roles: A sandbox & runtime · B agent & gates · C GitHub & approval · D UI, access & demo. Current step: B01 (all roles together).
