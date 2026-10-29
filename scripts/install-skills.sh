#!/usr/bin/env bash
# Reproduce the project skill set (Claude Code, copied into .claude/skills/).
set -euo pipefail
A="-a claude-code --copy -y"
npx -y skills add mattpocock/skills --skill tdd --skill diagnosing-bugs $A
npx -y skills add langchain-ai/langchain-skills --skill langgraph-fundamentals --skill langgraph-persistence --skill langgraph-human-in-the-loop $A
npx -y skills add anthropics/skills --skill frontend-design $A
npx -y skills add openai/skills --skill security-best-practices $A
npx -y skills add bagelhole/devops-security-agent-skills --skill container-hardening $A
npx -y skills add warpdotdev/common-skills --skill write-pr-description $A
# Add Codex/Cursor: append  -a codex -a cursor  to $A
