# COORDINATION.md: how the three Claude sessions work together

Claude sessions on different GitHub accounts can't message each other directly. **This repo is the channel:** issues are tasks and messages, PRs are handoffs, and `main` is the integrated state. Every session follows this file.

## Roles (one person + one Claude session each)
| Role | Person | Steps (docs/build-plan/prompts/) | Owns these paths |
|---|---|---|---|
| A: Sandbox, runtime & integration lead | Niranjan-cyber | B01, B02 (lead), B04, B05, B13 (lead) | `backend/worker/`, `backend/sandbox/`, `scripts/`, `infra/` |
| B: Agent & gates | swaralipatil11 | B06, B07, B08, B09 | `backend/agents/`, `backend/gates/`, `backend/llm_gateway.py` |
| C: GitHub, approval, access & UI states | DevanshNarlawar06 | B03, B10, B11, B12 | `backend/github/`, `backend/publisher/`, `backend/api/`, `web/` (shared) |
Shared, change only by a PR that all three approve: `backend/contracts/`, `docs/contracts.md`, `fixtures/runs/`.

## Protocol
1. **Start of session:** `git pull`, then `gh issue list --label status:in-progress` and `gh issue list --search "mentions:@me is:open"`. Read the comments on your step's issue.
2. **Claim a step:** assign yourself on its issue (`gh issue edit <n> --add-assignee @me --add-label status:in-progress`). Work on branch `b<NN>-<slug>`. Follow the step prompt and SKILL-PLAYBOOK.md.
3. **Talk:** comment on the relevant issue, starting with `[A→B]`, `[B→C]`, `[ALL]`, etc. For questions that block you, also add the label `blocked` and `@mention` the person. Keep comments under 10 lines and link files or lines instead of pasting code.
4. **Contracts:** never edit `backend/contracts/` or `docs/contracts.md` on a step branch. Open a separate PR titled `contracts: …`, label it `contracts`, and wait for all three approvals.
5. **Finish a step:** open a PR (`write-pr-description`) that links the issue (`Closes #n`) and includes the browser-check screenshots. One other role reviews it (`/code-review`). Merge to `main`, then comment `[ALL] B<NN> merged: <one line on what changed for you>`.
6. **Trust gate:** a wrong result, isolation leak or failure shown as empty is filed as an issue labelled `bug:P0` or `bug:P1`. No new feature PRs merge while one is open.
7. **Don't overlap:** touch another role's paths only through a PR that role reviews.
8. **Tokens:** one step per session, `/clear` between steps, no full logs in issues (`tail -30`).
