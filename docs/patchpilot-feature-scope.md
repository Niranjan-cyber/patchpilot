# PatchPilot: Feature Scope

**Event:** [AgentX Hackathon 2026 (Hack4Hack)](https://hack4hack.com/hackathons/agentx-hackathon-2026-hooc), PS-05 · **Idea deck due:** 30 Oct, 11:59 PM IST (≤ 6 slides, link) · **Build:** 11 Nov 10:00 → 12 Nov 10:00 IST · **Demos:** 12–14 Nov
**Team:** 4 people, ~40 h, several Claude Code sessions in parallel on one repo
**Judging:** problem fit and impact 25% · agent design (planning, tool use, memory) 25% · working demo and reliability 20% · innovation 15% · presentation 15%
**PS must-haves:** sandboxed code execution · tests that pass after the fix · human review before merging
**Deliverables:** GitHub repo with README · demo video ≤ 3 min · 6-slide deck
**Constraints chosen by the team:** everything free (free Gemini / Groq keys, Ollama as a local fallback); laptops host the demo; real-user hosting must also be free (see §8)
**Assumption to confirm:** the official build window is 24 h. The visible rules don't say whether building before 11 Nov is allowed. Ask the organizers before relying on the 40 h.

## 1. Who and why
- **Target users (both, equally):** (a) a **first-time contributor** who found a Python issue on someone else's repo and doesn't know where to start; (b) a **maintainer or triager** who wants a reproduction and a tested fix attached to an issue without spending an afternoon on it.
- **Job:** turn one GitHub issue into evidence: a reproduction, a diagnosis, and a fix proven by a test that fails before it and passes after. Then, only after approval, open a draft PR. This happens once per issue, whenever the user picks one up.
- **Today they:** clone, set up the environment, read code and guess, all by hand. That takes hours, and new contributors often give up. AI agents that skip this produce the untested PRs maintainers now ban (§7).

## 2. Core loop
1. **Paste a public issue URL** → eligibility and contribution-policy check.
2. **Sandbox setup** → SupplyGuard pre-flight, install, baseline tests.
3. **Reproduce → diagnose → fix** (AI roles propose; gates decide).
4. **Verify in a fresh container + honest report** ← ⭐ winning feature
5. **Approve the exact diff → draft PR** (direct or fork), or keep the report.

**Winning feature: the proof-carrying fix.** In under 60 seconds a judge sees the same new test go **red on the original code (twice) and green after the fix, in a brand-new container**, with the baseline tests still passing and every status traced to a recorded run. When that isn't possible, the run ends in an honest triage report, never a fake "fixed".
Why it wins: it hits *agent design* (planning, gates and retries, tool use) and *reliability* together. The PS asks for "tests that pass after the fix"; we also prove the test failed before it. Comparables don't show this. GitHub's Copilot agent needs write access and returns a PR. AutoMaintainer (Qwen hackathon) "generates tests", but its write-up doesn't describe reproducing the bug first. Even research systems produce a valid fail-then-pass test only 19–70% of the time (SWT-bench), so the honest triage path is something users actually need, not an edge case.

## 3. Must features (5)

### M1. Issue intake, eligibility and contribution-policy check (step 1) · real · M
- **User does and sees:** pastes an issue URL (no sign-in needed). Sees a card with the issue summary (expected vs. actual), repo, language, labels, and a checklist: open · unassigned · no linked open PR · Python detected · CONTRIBUTING / AI-policy status.
- **Acceptance criteria:**
  - [ ] Valid public issue URL → card renders within 5 s, with a pinned base commit SHA.
  - [ ] Closed, assigned, or has a linked open PR (GraphQL `closedByPullRequestsReferences`) → warning, and the run is skipped unless the user explicitly continues (recorded).
  - [ ] CONTRIBUTING or AI policy forbids AI contributions → **"report only" mode**: the publish button is disabled with the reason. Repo has PRs restricted to collaborators → fork PR flagged as likely blocked.
  - [ ] Bad URL, private repo, non-Python repo or GitHub rate limit → specific message plus next step, never a blank state.
- **Evidence:** Validated. Copilot only acts for users with write access ([docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-a-pr)), so working from an issue URL alone covers a real gap. AI-contribution bans are spreading (Ghostty, Godot, matplotlib; [RedMonk survey](https://redmonk.com/kholterhoff/2026/02/26/generative-ai-policy-landscape-in-open-source/)), and GitHub added repo-level PR restrictions in Feb 2026. That's why the policy check moved up from P1 to Must for real users.
- **Data source:** GitHub REST + GraphQL (unauthenticated, or a read-only token for rate limits) · **May claim:** observed. The AI-policy verdict is an *LLM reading of the docs* and is labelled as such.

### M2. Sandboxed setup and baseline (step 2) · real · L
- **User does and sees:** watches a live timeline: SupplyGuard → install → collect → baseline. Sees which existing tests pass, fail or are flaky.
- **Acceptance criteria:**
  - [ ] SupplyGuard runs **before** anything is installed. Confirmed malicious or typosquatted package → `BLOCKED`, **with no user override in the MVP** (false positives go to a team review queue; this changes the brief's G1). CVEs are listed but don't block. SupplyGuard down, a lookup failed or a format unsupported → "inconclusive", never "clean": analysis continues in the sandbox, but readiness is capped at Needs attention and **publishing stays disabled** until a later check is clean.
  - [ ] Install with `uv`, PyPI-only proxy, ~8 min cap. Every later container runs with `--network none`, non-root, `--cap-drop ALL`, CPU/memory/process limits.
  - [ ] `pytest --collect-only` succeeds → baseline pass/fail/flaky sets recorded (failures rerun once). Fails after one AI install-command retry → `ENV_FAILED` with the install log.
  - [ ] No environment is reused across runs: each run builds its own image in fresh containers. Speed comes from the `proxpi` PyPI cache and a saved **install recipe** (Python version + commands that worked) replayed in a fresh container. The recipe is the agent's **memory** (judging criterion).
- **Evidence:** Table stakes, and the highest risk. EnvBench: the best agent set up only 6.7% of hard Python repos; Repo2Run: 86% on standard repos with unit tests ([Repo2Run](https://arxiv.org/html/2502.13681v4)). Setup will decide most outcomes, so pick demo repos that install cleanly.
- **Data source:** repo files at the pinned SHA, PyPI · **May claim:** observed.
- **Feasibility test (1 h):** run setup + baseline on 3 small Python repos (one planted-bug repo, two SWE-bench Lite repos) on a laptop with Docker; record time and pass/fail.

### M3. Reproduce → diagnose → fix (step 3) · real · L
- **User does and sees:** the reproduction test and its failure output; the diagnosis with file/line links and cited evidence; a short codebase tour (relevant files, functions and tests, from the Investigator); the fix diff.
- **Acceptance criteria:**
  - [ ] **G3:** the test diff touches test files only. It fails 2/2 on the original code with an assertion or the error described in the issue (not an import, syntax or collection error). Up to 2 retries, then `CANNOT_REPRODUCE` → triage report.
  - [ ] The diagnosis cites evidence IDs that exist in the artifact store. Otherwise it is rejected as a failed attempt.
  - [ ] **G4:** the fix touches non-test sources only, stays under the size limit, adds no dependency or `.github/` changes, and deletes or skips no tests. A violation is returned to the Fixer with the reason.
  - [ ] Every role returns Pydantic-validated JSON. Invalid output counts as a failed attempt. Each role has a step budget (~15–20 on free LLMs, see §8).
- **Evidence:** Validated. SWT-bench F→P rates range from 19% (SWE-agent+) to 70% (ReProAgent preprint) ([SWT-bench](https://arxiv.org/pdf/2406.12952)), so it's achievable on simple bugs and fails often on hard ones. Multi-role issue-to-PR pipelines are common (AutoMaintainer, OpenHands resolver), so the *roles* aren't the innovation. The gates are.
- **Data source:** sandbox runs, LLM via LiteLLM (Gemini Flash free → Groq → Ollama fallback chain) · **May claim:** observed (test output); the diagnosis is labelled a *hypothesis*.
- **Feasibility test (1 h):** with free Gemini Flash and mini-SWE-agent, can the Test designer produce a 2/2-failing test for one planted bug within 20 steps? Count the LLM calls per run and compare with the daily free quota.

### M4. ⭐ Fresh-container verification and honest report (step 4) · real · M
- **User does and sees:** the run page shows *red → green* for the new test, baseline still passing, Reviewer concerns, SupplyGuard summary, the plain-language explanation and limitations, and a readiness badge: **Ready for human review / Needs attention / Unable to verify a fix (triage report) / Unable to verify**.
- **Acceptance criteria:**
  - [ ] **G5:** in a *new* container (original + test diff + fix diff): the new test passes 2/2, and every baseline-passing test still passes. Failure → back to the Fixer with logs (≤ 3 times), one re-diagnosis, then `TRIAGE_ONLY`.
  - [ ] The Reviewer can only *lower* the rating (flags special-casing or scope creep).
  - [ ] **G6:** every status in the report matches a recorded result, and every claim cites an evidence ID. The Explainer can't change statuses. A mismatch → the report is regenerated.
  - [ ] Every path (BLOCKED, ENV_FAILED, CANNOT_REPRODUCE, TRIAGE_ONLY, budget exhausted) ends with a downloadable report (Markdown + diff). No run ends silently.
- **Evidence:** Differentiator (see §2). Supporting point: curl's maintainer says PRs are less of a slop problem than bug reports because a PR that fails the test suite gets no attention ([opensourcesecurity.io](https://opensourcesecurity.io/2025/2025-05-curl_vs_ai_with_daniel_stenberg/)). Test evidence is what maintainers value.
- **Data source:** recorded runner exit codes and output · **May claim:** observed. "Ready for human review" never means safe to merge.

### M5. GitHub sign-in, approve and publish draft PR (step 5) · real · M
- **User does and sees:** reviews the exact diff → **Approve** / **Revise** (free-text feedback reruns M3 fix → M4) / **Keep report only**. To publish, clicks **Connect GitHub** (OAuth app, `public_repo`; each permission explained in plain language). PatchPilot shows whether a direct branch or a fork will be used, then opens a **draft** PR with the issue link, summary, test evidence, dependency summary, limitations and an AI-assistance note. Signed-in users see a simple list of their past runs.
- **Acceptance criteria:**
  - [ ] Approval stores a hash of the diff and the evidence. Any revision voids it. The publisher re-applies the diff on a clean checkout of the base SHA and refuses on a hash mismatch.
  - [ ] Write access → branch + draft PR upstream. No write access → fork, push, draft PR from the fork. Fork PR rejected (PRs restricted or disabled) → pre-filled compare link. Not signed in → download diff + report.
  - [ ] Idempotent: one PR per run, at most one per issue per user. Re-publishing updates the same PR.
  - [ ] The token lives only in the publisher (encrypted at rest), never in prompts, the sandbox or logs.
  - [ ] Server-enforced limits: 2 runs/day and 1 active per anonymous session; 5/day and 1 active per account; global sandbox concurrency (1 on the laptop, 2 on a VM) with a visible queue; a global daily LLM token budget; per run ~300k tokens, 25 min active runtime, 8 min setup, 2 h max pause. When a provider quota is hit, the run pauses and shows a resume time only if the provider gives one.
  - [ ] Run access: an anonymous run opens only in the browser that started it (an unguessable, revocable token in an HttpOnly cookie, never in URLs, logs or analytics). Other devices require GitHub sign-in, which claims the run. Reports are never publicly listed and are sent with `noindex`.
  - [ ] Runs execute in a separate worker from a durable job queue with SQLite checkpoints. They survive browser disconnects and worker restarts, resuming from the last completed step. A laptop host that sleeps or shuts down stops runs until it's back.
- **Evidence:** Validated. GitHub's docs list contributing to public repos where you aren't a member as a fine-grained-token gap ([docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)), so OAuth `public_repo` is the right method. The OpenHands resolver also tells users without push access to work from a fork ([PyPI](https://pypi.org/project/openhands-resolver/0.3.1)).
- **Data source:** GitHub REST/git · **May claim:** observed (PR URL and status come from GitHub).

**Fit check:** Must ≈ 26 h (M1 4 · M2 8 · M3 8 · M4 4 · M5 4, including the UI shell) of ~40 h. That's **65%, above the 50% target.** It's workable only because several sessions run in parallel. Planned parallel lanes: (1) sandbox + setup + baseline, (2) agent roles + gates, (3) GitHub reader/publisher + OAuth, (4) React UI + polled event timeline. The Should list is kept, as you asked, but **built in the order below, and only after the demo path runs end to end twice in a row.**

## 4. Should / Could (kept, in build order)
| # | Feature | Verdict | Note |
|---|---|---|---|
| S1 | **Eval slide:** 5 planted bugs + 5 SWE-bench Lite issues, counting verified / triage / unable / false-"verified" | Validated (reliability, 20%) | Cheapest way to prove reliability to judges; run it overnight on the laptop |
| S2 | Contextual Q&A ("Why this file?", "What does this test prove?") + 4 optional guided pauses | Unvalidated (assumption) | Builds on the Explainer and LangGraph `interrupt()`; serves the first-time contributor |
| S3 | My progress dashboard: issues worked, outcomes, PRs + live GitHub status (open/merged/closed), skills seen | Unvalidated | Extends M5's run list; keeps PatchPilot data and GitHub data visibly separate; private, no streaks |
| S4 | Hidden-variant test (Fixer never sees it) | Differentiator (integrity) | Adds one more container run per verify; can lower the rating only |
| S5 | Explore: ranked shortlist for **one** repo | Overdone (IssueScout, GitPulse, GitHub's own good-first-issues ML) | Our angle: rank by **"PatchPilot can actually run this"** (install recipe known, tests found, issue clear), not labels |
| S6 | `git bisect run` with the reproduction test → names the commit that introduced the bug | Differentiator for triagers | Cheap once M2/M3 work; can be slow on long histories, so cap the number of steps |
| C1 | Run the repo's own CI (GitHub Actions) on the draft PR | Could | Only with minimum token permissions |
| C2 | SWE-ReX / remote sandboxes | Could | After free hosting is proven |

## 5. Won't (cut list)
| Feature | Reason |
|---|---|
| Private / company repos, team admin | Off the loop; needs private auth and data-retention controls (brief P2) |
| Non-Python languages, UI/browser or infrastructure bugs | Setup is already the top risk in Python |
| Bring-your-own API key | Team decision: everything free; adds secure key storage |
| Paid sandbox hosts (E2B, Daytona, Modal) beyond free credits | Not free; reconsider after the hackathon |
| xAI Grok API | No reliable free tier found; use **Groq** (hosted open models) instead |
| Multi-issue runs, auto dependency upgrades, broad refactors | Out of scope in the brief |
| Auto-merge, publishing without approval, leaderboards/streaks, public profiles | Never, by design |

## 6. Demo path (≤ 3 min video)
1. Paste an issue from the team's "upstream" repo (owned by a second account) → eligibility card, policy check ✓.
2. Timeline: SupplyGuard clean → quick setup (recipe + warm package cache) → baseline (one known-failing test shown honestly).
3. Reproduction test **fails 2/2** → diagnosis with file:line → short codebase tour.
4. ⭐ Fix → **fresh container: red → green**, baseline intact, readiness = "Ready for human review".
5. Approve the exact diff → Connect GitHub → draft PR **from the fork** with evidence + AI note → the maintainer account reviews it (branch protection on).
6. 20 s cut: a second issue ends in an honest **triage report** (`CANNOT_REPRODUCE` or `TRIAGE_ONLY`). Then the eval slide.
Keep a recorded backup run; agent runs take minutes and sometimes fail.

## 7. What exists and our angle
- **GitHub Copilot / third-party coding agents:** assign an issue, get a PR. Needs write access and a paid Copilot plan. **We:** any public issue URL, fork flow, proof of fail-then-pass.
- **OpenHands resolver / Google Jules:** fix issues on repos you connect or install on; Jules runs setup in a cloud VM. **We:** no install on the target repo, gated verification, honest triage when a fix can't be verified.
- **AutoMaintainer (Qwen hackathon), Gitdefender (GitLab AI Hackathon 2026 winner):** multi-agent issue/finding → PR. **We:** compete on *verification integrity*, not agent count.

## 8. Hosting, LLMs and open risks
**Hosting (free):** demo on laptops (Docker Desktop + WSL2). Give judges a live URL through free **Tailscale Funnel**, which gives a stable `ts.net` hostname (needed for the OAuth callback). FastAPI serves the React build from the same origin, so the session cookie stays first-party. Cloudflare Quick Tunnels were dropped: they don't support SSE and change URL on every restart (see `patchpilot-architecture.md`). For real users, a free always-on option is an **Oracle Cloud Always Free Arm VM** running API + worker + Docker. Caveats: one report says the allowance dropped from 4 OCPU/24 GB to 2 OCPU/12 GB in June 2026 (unverified); free Arm capacity is often unavailable; Arm images need arm64 Python wheels. Render and Railway can't run Docker containers from your app.

| Risk | Mitigation |
|---|---|
| Environment setup fails on most real repos (EnvBench 6.7%) | Honest `ENV_FAILED` + log; saved install recipes + `proxpi` package cache (no reused images); demo on hand-picked repos; show the setup success rate on the eval slide |
| Free LLM quotas run out (Gemini free is Flash-only with low daily caps; Groq has a low tokens-per-minute cap; figures unverified) | LiteLLM fallback chain Gemini → Groq → Ollama; ~15–20 steps per role; count calls per run in the M3 feasibility test; a clear "today's free capacity is used up" state. Real users get a few runs a day, so say so |
| Weak models write bad reproduction tests or fixes | Gates G3–G6 turn failures into triage reports instead of false claims; pick the model by the S1 eval, not by feel |
| 24 h official window vs. 40 h plan | Confirm the prebuild rules today; if not allowed, the M1–M5 demo path is the whole build and S1–S6 go in the deck as roadmap |
| Laptop is the only sandbox host on demo day: a tunnel is not always-on compute; sleep or shutdown stops runs | Disable sleep during demo week; a "Demo server" banner in the UI; checkpoints let interrupted runs resume; recorded backup run; Oracle VM as a second host if capacity is available |
| Four people building in parallel don't integrate | Freeze `docs/contracts.md` (run state, events, outcomes, approval hash) before splitting work; changes only through a PR that all lanes review |

## Source log
- hack4hack.com/hackathons/agentx-hackathon-2026-hooc: rules, PS-05 text, judging weights, deliverables, dates (opened in browser)
- docs.github.com/…/coding-agent/create-a-pr: Copilot requires write access (search summary of the docs page) → M1, §7
- docs.github.com/…/managing-your-personal-access-tokens: fine-grained gap for non-member public repos (search summary) → M5
- github.com/orgs/community/discussions/106661: user reports of fine-grained PATs failing to open PRs (search summary) → M5
- redmonk.com/kholterhoff/2026/02/26/generative-ai-policy-landscape-in-open-source/ + blog.devgenius.io + softwareseni.com: AI policy bans, GitHub PR controls Feb 2026 (search summaries; secondary) → M1
- arxiv.org/html/2502.13681v4 (Repo2Run), EnvBench (arXiv 2503.14443): setup success rates (search summary) → M2, risks
- arxiv.org/pdf/2406.12952 (SWT-bench), AssertFlip, Otter, ReProAgent (preprint): F→P rates (search summary) → M3, §2
- opensourcesecurity.io/2025/2025-05-curl_vs_ai_with_daniel_stenberg/: tests filter AI slop PRs (search summary) → M4
- pypi.org/project/openhands-resolver: fork advice without push access (search summary) → M5, §7
- dev.to/okuhlecharlieman/building-automaintainer…: AutoMaintainer features; no prize mentioned (opened) → §2, §7
- GitLab AI Hackathon 2026 winners (via mirror + the brief's link): Gitdefender (unverified on Devpost) → §7
- github/github-mcp-server PR #3006: `closedByPullRequestsReferences` for linked PRs (search summary) → M1
- datacamp.com/tutorial/google-jules: Jules repo selection + cloud VM (search summary) → §7
- station.railway.com, community.render.com, community.fly.io: no Docker-in-Docker on Railway/Render; Fly works (search summary; forums) → §8
- medium.com/@imvinojanv (Oracle 4 OCPU/24 GB) vs. issoh.co.jp (2 OCPU/12 GB after June 2026): conflicting, unverified → §8
- hnshowcase IssueScout, dev.to GitPulse, github.blog good-first-issues: Explore is crowded (search summary) → S5
- agentdeals.dev/gemini-api-pricing-changes, dev.to free AI API lists: free-tier limits conflict, unverified → §8
- E2B/Daytona/Modal comparisons (morphllm, superagent): free credits only, third-party figures → Won't
