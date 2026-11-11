# GCP deployment handoff for D (Sarthak), 2026-11-11

**Owner:** D (sarthakviche) owns the hosted deployment and the demo video recording.
**A's role:** A (Niranjan's session) helps with deployment: code fixes, deploy-script bugs, questions. A's main job is making the demo stronger. Ask in messages.md (`D→A: …`), and A answers there.

## Hard rule: the laptop demo stays the fallback
The laptop host (Tailscale Funnel + `scripts/deploy.ps1`) keeps running until the GCP host passes every check below. Don't change the GitHub OAuth app, `PUBLIC_URL` or the laptop's `.env` until then.

## What already exists (use it, don't rewrite it)
- `infra/vm-setup.sh` prepares an Ubuntu 24.04 VM: Docker, gVisor (`runsc`), uv, Node 20, Tailscale, and a ufw firewall that blocks all incoming traffic except SSH. It was written for Oracle (Arm). GCP e2/n2 machines are x86, which the script handles (`dpkg --print-architecture`).
- `scripts/deploy.sh` pulls, builds the web app and the `pp-base:3.12` image, installs the API and worker as systemd services, and fails loudly if `/healthz` doesn't answer.
- `.env.example` lists every variable. The real values are on Niranjan's laptop; get them from Niranjan directly, **never through git, messages.md or an issue.**

## Sizing: the free e2-micro is too small
GCP's Always Free VM (e2-micro: 2 shared vCPU, **1 GB RAM**, 30 GB disk) can't run Docker sandboxes that pip-install real repos and run their test suites, plus the API, worker and proxy. The laptop already struggles with 16 GB.
- **Recommended:** use the $300 free-trial credit on an **e2-standard-4 (4 vCPU, 16 GB)** or at least an e2-standard-2 (8 GB), Ubuntu 24.04, **50–100 GB balanced disk** (Docker images and pip caches fill disk fast). Pick a region near the judges.
- Set a **budget alert** in Billing before creating the VM, and stop the VM when it isn't needed.
- If only e2-micro is allowed, host only the read-only showcase there. Live runs stay on the laptop.

## Steps
1. Create the VM (above). SSH in as a normal sudo user.
2. Clone the repo, then run `bash infra/vm-setup.sh`. Log out and back in (docker group).
3. `sudo tailscale up` on a tailnet you control. Funnel gives HTTPS with no open ports, so no firewall rule or certificate is needed.
4. `cp .env.example .env`. Fill it with the values Niranjan sends. Set `PP_DOCKER_RUNTIME=runsc` and `PUBLIC_URL=https://<vm>.<tailnet>.ts.net`.
5. `./scripts/deploy.sh`, then `sudo tailscale funnel --bg 8000`.
6. `curl -s http://127.0.0.1:8000/healthz` must show `db`, `worker`, `docker` true and `"contracts":"0.10"` (or whatever main has).

## Checks before switching the demo to GCP
- [ ] `/healthz` is healthy on the public URL.
- [ ] A sample run opens: `/runs/verified_fix`.
- [ ] One real live run on `Niranjan-cyber/tinycalc` reaches approval, timed. Note the SETUP time (the laptop's slow PyPI was the biggest demo risk).
- [ ] gVisor really runs the sandbox. The health check says `"sandbox_runtime":"runsc"`.
- [ ] GitHub sign-in works. **This needs a second OAuth callback URL.** GitHub OAuth apps allow only one callback, so ask Niranjan to create a separate OAuth app for the GCP URL (or switch the existing one at cutover) and send you its id and secret.
- [ ] Publishing stays limited to the allowlist: a judge account can reach approval on any repo but can't publish outside it (#100).
- [ ] From a fresh browser session, with no API keys entered, a judge can do the whole demo path.
- [ ] The README link and the demo video point to the URL that will be live on judging day.

## Not in scope for this handoff
- Moving run history from the laptop's `data/app.db` (it holds the real pint/tinycalc runs). Ask Niranjan before copying it: it holds session data and encrypted tokens.
- Webhooks and email. Polling works as it is.
