#!/usr/bin/env bash
# B19: prepare an always-on Ubuntu 24.04 VM (e.g. Oracle Always Free Arm) as the PatchPilot host. Run as a sudo user.
# A human runs this after creating the VM; it creates no cloud resources itself.
set -euo pipefail
sudo apt-get update && sudo apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh                       # Docker Engine
sudo usermod -aG docker "$USER"                                  # the worker runs sandboxes without root (log out and back in once)
# gVisor (runsc), per https://gvisor.dev/docs/user_guide/install/
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
  | sudo tee /etc/apt/sources.list.d/gvisor.list >/dev/null
sudo apt-get update && sudo apt-get install -y runsc
sudo runsc install && sudo systemctl restart docker
# sudo, because this shell isn't in the docker group until the user logs out and back in.
# An `... && echo OK` here would pass silently when runsc is missing: set -e exempts a failing
# command in an && list, so the install would "succeed" and only break later in the worker.
if sudo docker info --format '{{json .Runtimes}}' | grep -q runsc; then
  echo "gVisor OK"
else
  echo "ERROR: runsc is not registered with Docker. B19 needs gVisor; fix this before deploying." >&2
  exit 1
fi
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs
curl -fsSL https://tailscale.com/install.sh | sh                   # public traffic: Tailscale Funnel only, no open ports
sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw --force enable   # public traffic arrives via Tailscale Funnel only
echo "Next: sudo tailscale up; clone the repo; cp .env.example .env (copy the keys, set PP_DOCKER_RUNTIME=runsc and PUBLIC_URL); ./scripts/deploy.sh; sudo tailscale funnel --bg 8000"
