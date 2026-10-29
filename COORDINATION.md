# COORDINATION.md: how the three Claude sessions work together

**Talk in `messages.md`** (rules at its top). Issues track steps; PRs are handoffs; `main` is the integrated state. Every session follows this file.

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
3. **Talk:** in `messages.md` (append, pull --rebase, push immediately). Issues hold only the step checklist.
4. **Contracts:** never edit `backend/contracts/` or `docs/contracts.md` on a step branch. Open a separate PR titled `contracts: …`, label it `contracts`, and wait for all three approvals.
5. **Finish a step:** open a PR (`write-pr-description`) that links the issue (`Closes #n`) and includes the browser-check screenshots. One other role reviews it (`/code-review`). Merge to `main`, then comment `[ALL] B<NN> merged: <one line on what changed for you>`.
6. **Trust gate:** a wrong result, isolation leak or failure shown as empty is filed as an issue labelled `bug:P0` or `bug:P1`. No new feature PRs merge while one is open.
7. **Don't overlap:** touch another role's paths only through a PR that role reviews.
8. **Tokens:** one step per session, `/clear` between steps, no full logs in issues (`tail -30`).

## No duplicate work
- Before writing code, post `CLAIM: <step or module> <paths>` in messages.md. If a CLAIM already covers those paths, coordinate in messages.md first, don't start.
- Shared code lives in one place: contracts and rules in `backend/contracts/models.py` (outcome, readiness, blockers); sandbox calls in `backend/sandbox/`; GitHub calls in `backend/github/`; LLM calls only through `backend/llm_gateway.py`. Import, don't copy.
- Current claims (update when you claim or finish):

| Claim | Owner | Paths | Status |
|---|---|---|---|
| B01/B02 skeleton, contracts code, fixtures, API fixture mode, web shell | A | backend/contracts, backend/api, scripts/make_fixtures.py, fixtures/runs, web/ (shell + S-03/S-04 components) | in progress |
| SupplyGuard adapter (calls Devansh's CLI) | A | backend/sandbox/supplyguard.py | claimed, after B02 |
| B03 issue reader | C | backend/github/reader.py | open |
| B06–B09 agents and gates | B | backend/agents/, backend/gates/, backend/llm_gateway.py | open |

## Liveness, takeover and review (humans' rules)
- **Heartbeat:** while working, every session posts in messages.md at least every 30 min (`HB: <step>, <what's done>, <next>`), and pushes its branch at least every 30 min.
- **Down:** a session with a CLAIM that hasn't posted or pushed for **60 min** is considered down. Any live session may post `TAKEOVER: <step> from <role>`, continue from that role's latest pushed branch, and take over the CLAIM.
- **Back:** a returning session reads messages.md first. It does **not** resume a step someone took over; it posts `BACK: <role>` and picks the next unclaimed step from the plan (the live sessions suggest one in their reply).
- **Review:** every PR is reviewed by a different session before merge (`/code-review` + the browser check screenshots). Reviewers check the UI is plain, intuitive and complete for a first-time contributor, not only that tests pass.
- **Learning log:** after every event (step started/finished, decision, bug, fix, review, takeover) append one line to LEARNING.md, in the same commit as the work.
- **Done:** the product is done when B13's prototype exit and B19's MVP exit both pass on the public URL. Keep working until then.
