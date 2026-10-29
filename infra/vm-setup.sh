#!/usr/bin/env bash
# B19: prepare an always-on Ubuntu 24.04 VM (e.g. Oracle Always Free Arm) as the PatchPilot host. Run as a sudo user.
# A human runs this after creating the VM; it creates no cloud resources itself.
set -euo pipefail
sudo apt-get update && sudo apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh                       # Docker Engine
# gVisor (runsc), per https://gvisor.dev/docs/user_guide/install/
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
  | sudo tee /etc/apt/sources.list.d/gvisor.list >/dev/null
sudo apt-get update && sudo apt-get install -y runsc
sudo runsc install && sudo systemctl restart docker
docker info --format '{{json .Runtimes}}' | grep -q runsc && echo "gVisor OK"
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs
sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw --force enable   # public traffic arrives via Tailscale Funnel only
echo "Next: clone the repo, cp .env.example .env (set PP_DOCKER_RUNTIME=runsc), build infra/Dockerfile.base, start API + worker, tailscale funnel --bg 8000"
