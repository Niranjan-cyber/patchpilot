# HANDOFF: Role A session (Niranjan-cyber), 2026-10-30 ~12:00 UTC

Read this first in a new session, then `COORDINATION.md`, the tail of `messages.md` and `LEARNING.md`. Plan: `docs/build-plan/BUILD-PLAN.md` (statuses now real). **Deadline: 2026-11-12 10:00 IST** (build round 11–12 Nov, demos 12–14 Nov).

## Where things stand
- **B13 EXIT PASSED (2026-10-30):** the full demo path twice on the public Funnel URL with real GitHub sign-in → draft PRs [tinycalc #4](https://github.com/Niranjan-cyber/tinycalc/pull/4) and [#5](https://github.com/Niranjan-cyber/tinycalc/pull/5). The golden-path e2e also passes locally.
- Plan status: B01–B13 and B15–B18 done; **B14: eval set merged (#33), numbers pending**; **B19 assigned to B (Swarali), runbook in messages.md 12:1x UTC**; the human paused until deploy + redesign land.
- 324+ tests pass. `main` is clean.
- Team: **C (Devansh)** is very active; his PRs #27/#28/#30/#31/#32 are merged and live. He now owns the **UI redesign** to `docs/DESIGN.md` (top priority, human's bar: "visually appealing, intuitive, pretty"), then the reviewer-context fix, then the eval PR. **B (Swarali)** was silent all day after 03:26 UTC; nothing claimed.

## What was wrong today (and is fixed); see LEARNING.md for detail
- itsdangerous #389 was a bad target (not a confirmed bug). Use **tinycalc** (`Niranjan-cyber/tinycalc` #1–#3, planted, clear) for demos; 3/3 fixed correctly.
- Our bugs: agents saw only 600 chars of the issue; SupplyGuard never ran on Windows (relative .CMD path); verify misread JUnit (stderr after XML); the publisher's text-mode stdin turned LF into CRLF (Windows); and the LLM fallback / quota / timeout handling.
- Model order (`PP_AGENT_MODELS`): groq gpt-oss-120b → groq qwen3.8-27b → **nebius gpt-oss-120b (paid credit, ≈$0.05/run)** → gemini 3.8 / 3.5 flash. The local 7B is short calls only.

## Running on this laptop
- API + worker started as detached processes (`Start-Process`); restart with `scripts/deploy.ps1` or the two commands in it. `limits.toml` is `@cache`d, so restart after editing it.
- **Tailscale Funnel is ON**: https://laptop-o90994nd.tail1ffac6.ts.net (anyone with the link can start runs). Off: `"/c/Program Files/Tailscale/tailscale.exe" funnel --https=443 off`.
- `.env` has GOOGLE/GROQ/NEBIUS/GITHUB_READ_TOKEN (read-write PAT; swap it for a read-only one), OAuth client id+secret, FERNET_KEY, PUBLIC_URL, PP_LOCAL_MODEL.
- `config/limits.toml`: **global budget 2.5M is today's debug-day value; set it back to 1_560_000 before the demo.**
- Memory is tight (15.8 GB): Claude Code reaps background watchers under pressure; check runs in the foreground.

## B19 next steps (owner: B, Swarali; see her runbook in messages.md)
1. The human creates an Oracle Always Free VM: Ubuntu 24.04, VM.Standard.A1.Flex 4 OCPU / 24 GB; sends the IP and user; copies `.env` via scp.
2. On the VM: `infra/vm-setup.sh` (Docker, gVisor, uv, Node, ufw, Tailscale, docker group), clone, `.env` with `PP_DOCKER_RUNTIME=runsc` and the new `PUBLIC_URL`, `./scripts/deploy.sh` (systemd services), `sudo tailscale up`, `sudo tailscale funnel --bg 8000`.
3. Update the GitHub OAuth app's homepage + callback to the VM's Funnel URL.
4. Run the golden path + MVP e2e specs on the VM URL → B19 exit. Arm64 images: verified for proxpi and python:3.12-slim.

## Other open items
- G0 `unclear_bug` contracts change: C acked; B hasn't. Needs a contracts PR (all lanes).
- Codebase-tour accuracy question (hallucinated "why" lines): B/C to vote (a/b/c in messages.md 10:2x).
- Demo video, README, submission: closer to the deadline.

## Role A tick (for `/loop`)
Each tick: `git pull --rebase=merges` (NOT plain `--rebase` after a local merge); read new messages.md entries; review/merge B/C PRs (screenshots); continue B19; post HB; push. Use `date -u` for timestamps.
