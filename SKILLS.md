# SKILLS.md: PatchPilot

Routing and phases: see `SKILL-PLAYBOOK.md`.
Installed 30 Oct 2026, project scope, copied into `.claude/skills/` (Claude Code). Reproduce with `bash scripts/install-skills.sh`. Every skill below was read before installing; none ships hooks, and the only script is `diagnosing-bugs`' human-in-the-loop template, which runs only when you choose to.

| Skill | Source @ commit | Why for PatchPilot | Use it when | How you'll know it helped |
|---|---|---|---|---|
| tdd | mattpocock/skills @a496f55 | gates G0–G6, the outcome table, diff hashing and limits are pure logic that must not drift between lanes | before writing any gate, rule, parser or hash | every contracts §1 rule has a failing-first test |
| diagnosing-bugs | mattpocock/skills @a496f55 | sandbox, worker-resume and polling bugs are hard to reproduce | something is broken, flaky or slow | bugs get a repro loop before a fix |
| langgraph-fundamentals | langchain-ai/langchain-skills @126c384 | the worker is a LangGraph state graph | building nodes and edges | graph matches the brief §7.1 flow |
| langgraph-persistence | langchain-ai/langchain-skills @126c384 | SqliteSaver checkpoints and resume after a worker crash (contracts §7) | checkpointing, thread IDs, resume | the kill-worker test resumes from the last node |
| langgraph-human-in-the-loop | langchain-ai/langchain-skills @126c384 | the approval gate uses `interrupt()` | approval, revise, resume flow | approve/revise resumes the same thread |
| container-hardening | bagelhole/devops-security-agent-skills @0365f57 | sandbox containers run hostile code | writing the `docker run` flags and images | every container passes the architecture §7 recipe |
| security-best-practices | openai/skills @49f948f (has FastAPI + React references) | cookies, OAuth, the publisher and redaction are the attack surface | writing auth, publisher, logging; before the demo | the security pass finds no high issues |
| frontend-design | anthropics/skills @ca45fc4 | presentation is 15% of judging; beginners need clear screens | building S-01…S-08 | screens look intentional, not default |
| write-pr-description | warpdotdev/common-skills @8792394 | team PRs (4 lanes) and PatchPilot's own PR body | opening a team PR; designing the generated PR template | reviewers get the why plus the evidence |

**Already on this machine, not installed again:** Playwright MCP (browser checks), built-in `/security-review`, `/code-review`, `run`; user-level planning skills (prototype-build-planner, skill-conductor, hackathon-demo-submission).

**Coding style:** Ponytail compact rules are merged into `AGENTS.md` (DietrichGebert/ponytail @96608e0). The Ponytail plugin stays off, so its rules aren't loaded twice.

**Turned off for this project** (`.claude/settings.json`), to save context tokens: plugins `mattpocock-skills` (replaced by the two copies above), `design`, `band-peer`, `ponytail`. **Manual:** in Claude Code, run `/mcp` and switch off the Canva, Gmail, Google Drive, Vercel, Slack, Claude Docs and `render` servers for this project.

**Teammates:** clone the repo; skills come with it. If anyone uses Codex or Cursor, add `-a codex -a cursor` in `scripts/install-skills.sh` and re-run it.

**Update / remove:** re-run the install script (it overwrites the copies), or delete `.claude/skills/<name>`. Check `npx skills ls`.

**Considered, rejected:**
- Superpowers / gstack / Addy Osmani: heavy methodology, costs time and tokens.
- UI UX Pro Max: overlaps frontend-design.
- Community FastAPI skills (~550 installs): FastAPI's own docs are better.
- `webapp-testing`: Playwright MCP covers it.
- warp `review-pr`: overlaps `/code-review`.
- `sandbox-guard` (openclaw), nvidia nemoclaw, `rivet-dev/sandbox-agent`: built for other products.
- `docker-destructive-guardrails`: not our risk.
- `skill-security`, `llm-trading-agent-security`: off-topic.
