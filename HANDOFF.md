# HANDOFF: Role A session (Niranjan-cyber), 2026-10-30 ~15:45 UTC (21:15 IST)

Read this first in a new session, then `COORDINATION.md`, the tail of `messages.md` and `LEARNING.md` (one line per event, today is very detailed). Plan: `docs/build-plan/BUILD-PLAN.md` (statuses are real). **Hackathon deadline: build round 11–12 Nov, demos 12–14 Nov.**

## 🔥 Due TONIGHT: idea deck, 30 Oct 23:59 IST (≤ 6 slides, submitted as a link)
- Content is ready: `docs/pitch/deck-content.md` (6 slides, speaker notes, real numbers only).
- **C (Devansh) owns the deck but has been silent since ~12:17 UTC.** A promised (messages.md 13:5x) to build it if C hadn't answered by 15:30 UTC (21:00 IST); that time has passed. **First thing in the new session: check messages.md for C. If still nothing, build the 6-slide PPTX from deck-content.md** (skill `anthropic-skills:pptx`) so the human can submit before 23:59 IST.
- The human must confirm before submitting: teammates' surnames (Patil / Narlawar are guesses from GitHub handles) and the official PS-05 wording (slide 2 paraphrases it).

## Where things stand
- **B13 EXIT PASSED:** the full demo path twice on the public Funnel URL with real GitHub sign-in → draft PRs [tinycalc #4](https://github.com/Niranjan-cyber/tinycalc/pull/4), [#5](https://github.com/Niranjan-cyber/tinycalc/pull/5).
- Plan: B01–B13 and B15–B18 done · B14 eval set merged (#33), numbers not run · **B19 DEFERRED by the human** (Oracle declined the card; the laptop stays the demo host; the deploy kit `infra/vm-setup.sh` + `scripts/deploy.sh` is ready for later).
- 348 tests pass. The UI redesign (C, #34) is merged and live. The human plans to **record the demo video on the local link** and maybe ship a **frontend-only showcase link** later (A proposed a read-only static "showcase" build with bundled sample/real runs on Vercel; not started; ask before any public deploy).

## Open problem: SETUP is slow/fails on this laptop (P1 for the demo video)
- Symptom: tinycalc setup sometimes takes 6–8 min or times out (`ENV_FAILED install_timeout`). Two of the human's live runs hit it today (8684e573 ENV_FAILED; a863ee86 passed setup at 7m48s).
- Causes found:
  - (1) **Docker Desktop's network to PyPI is flaky**: one request 0.1 s, the next hangs 40 s. Host→PyPI is always fast. A Docker Desktop restart helped partially; Tailscale (installed today) is a suspect.
  - (2) proxpi had only 2 threads, so one slow fetch blocked everything.
- Done (commit 149ba45): proxpi recreated with **8 threads + `PROXPI_INDEX_TTL=86400`** (`backend/sandbox/docker.py`); **pp-base rebuilt with pip 26.2 / setuptools / wheel / pytest baked in** (`infra/Dockerfile.base`).
- **NOT fixed yet:** a timed tinycalc SETUP right after the proxy was recreated (cache empty) still took **452 s and INSTALL_EXIT=1**. Likely `pip install -e .` fetches `setuptools` for its *isolated build env* through the proxy over the flaky network.
- **Next steps:**
  - (a) Re-run the timing check (fetch_source + make_snapshot + `docker.run("pp-base:3.12", INSTALL, network=SETUP_NET, ...)`) and read the install log to confirm what failed.
  - (b) Pre-warm the proxy with the build backends (setuptools, wheel, flit_core, hatchling, poetry-core) after any proxy recreate.
  - (c) Consider `PIP_NO_BUILD_ISOLATION=1` only together with the baked-in setuptools/wheel (tinycalc-safe; check it doesn't break other repos).
  - (d) Test with Tailscale paused to see if Docker's network becomes stable.
  - (e) Before recording the demo video, run one tinycalc setup to warm everything.

## Other findings from today (all fixed + merged, details in LEARNING.md)
- Our bugs: agents saw 600 chars of the issue; SupplyGuard never ran on Windows (relative .CMD path); verify misread JUnit (stderr after XML, sentinel `partition`); publisher CRLF on Windows (git apply failed); G4 skipped paths with spaces (**P0 #38, B**); unvalidated tour paths (**P1 #35, B**); report showed "none/0" for an unfinished scan (**P1 #29, C**); LLM fallback/quota/timeouts; the laptop slept during runs.
- Open issue **#43 (P2):** an install timeout saves an EMPTY log as evidence (failure shown as empty).
- The last human run, a863ee86 (tinycalc #1, 15:18 UTC), ended **TRIAGE_ONLY**: diagnose couldn't cite checkable evidence. Not investigated yet. Check whether #36's tour validation or the investigator prompt is now too strict.

## PRs / team
- **#41 contracts v0.3** (unclear_bug warning + G3 import-error clause): A approved; **needs C's approval** before merge (rule 4). Follow-up agreed: an accepted unclear_bug caps readiness → FIX_NEEDS_ATTENTION.
- **B (Swarali):** active and excellent (found P0 #38, P1 #35, verify false negatives #42, deploy-script honesty #40). B19 released → she continues the gates/agents trust review (fix.py, review.py, explain.py, loop.py unread). She also has issue #43.
- **C (Devansh):** silent since ~12:17 UTC. Owes: the deck (tonight), the #41 review, and redesign follow-ups (mobile nav cue, "AI note, not checked" tag on tour items, consistent "Passed" green).

## Running on this laptop
- API + worker run as detached processes; restart with `scripts/deploy.ps1` (or the two `Start-Process` lines in it). `limits.toml` is `@cache`d, so restart after editing it. Rebuild `web/dist` (`cd web && npm run build`) after UI changes.
- **Tailscale Funnel is ON:** https://laptop-o90994nd.tail1ffac6.ts.net (anyone with the link can start runs). Off: `"/c/Program Files/Tailscale/tailscale.exe" funnel --https=443 off`. It's needed for GitHub sign-in (the OAuth callback is registered to that URL).
- `.env`: GOOGLE/GROQ/NEBIUS keys, GITHUB_READ_TOKEN (read-**write** PAT, swap for read-only), OAuth id/secret, FERNET_KEY, PUBLIC_URL, PP_LOCAL_MODEL.
- `config/limits.toml`: global budget **2.5M** (debug-day value): **set it back to 1_560_000 before the demo.**
- Model order (`PP_AGENT_MODELS`): groq gpt-oss-120b → groq qwen3.8-27b → nebius gpt-oss-120b (paid, ≈$0.05/run) → gemini 3.8/3.5 flash. The local 7B is for short calls only.
- **Memory is very tight** (15.8 GB; dropped to 0.4 GB free during the human's Meet call). Claude Code reaps background commands under pressure, so run long things in the foreground.
- Demo laptop rules: on AC, sleep off, Funnel on only while demoing, recorded backup run.

## Role A tick (for `/loop`)
Each tick: `git pull --rebase=merges` (never plain `--rebase` after a local merge); read new messages.md entries; review/merge B/C PRs (screenshots for UI); continue the open items above; post HB; push. Timestamps from `date -u`.
