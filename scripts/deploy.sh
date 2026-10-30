#!/usr/bin/env bash
# Deploy on the Linux host (B19 VM): pull, build, (re)install the API + worker as systemd services, check health.
# Linux twin of scripts/deploy.ps1. Run from the repo root as the deploy user (in the docker group), not as root.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=$(pwd); UV=$(command -v uv || echo "$HOME/.local/bin/uv")

# The units below bake in User=$USER. Run under sudo and they'd run the worker as root,
# which quietly undoes "sandboxes run as a non-root user in the docker group".
if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: run deploy.sh as the deploy user, not as root or via sudo." >&2
  exit 1
fi
[ -x "$UV" ] || { echo "ERROR: uv not found at '$UV'. Run infra/vm-setup.sh, then log out and back in." >&2; exit 1; }

git pull --rebase=merges
"$UV" sync
(cd web && npm ci --no-audit --no-fund && npm run build)
docker build -q -t pp-base:3.12 -f infra/Dockerfile.base infra >/dev/null
mkdir -p data

# systemd: restart on crash and on reboot ("always-on"); the app reads .env itself, so no secrets live in the units
unit() {   # name, description, command
  sudo tee "/etc/systemd/system/$1.service" >/dev/null <<EOF
[Unit]
Description=$2
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
User=$USER
WorkingDirectory=$REPO
ExecStart=$UV run $3
Restart=always
RestartSec=5
StandardOutput=append:$REPO/data/$1.log
StandardError=append:$REPO/data/$1.err

[Install]
WantedBy=multi-user.target
EOF
}
unit patchpilot-api "PatchPilot API (127.0.0.1:8000, published via Tailscale Funnel)" "uvicorn backend.api.main:app --host 127.0.0.1 --port 8000"
unit patchpilot-worker "PatchPilot worker (runs sandboxes)" "python -m backend.worker.main"
sudo systemctl daemon-reload
sudo systemctl enable --now patchpilot-api patchpilot-worker
sudo systemctl restart patchpilot-api patchpilot-worker

# A bare `curl && break` loop ends silently when every attempt fails (set -e exempts a failing
# command in an && list), so a deploy whose API never started used to print the success line
# and exit 0. A failed deploy has to say so.
healthy=""
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/healthz; then echo; healthy=1; break; fi
  sleep 2
done
if [ -z "$healthy" ]; then
  echo "ERROR: /healthz did not answer within 40s. Last lines of the API log:" >&2
  tail -n 20 "$REPO/data/patchpilot-api.err" "$REPO/data/patchpilot-api.log" 2>/dev/null >&2 || true
  echo "Also: systemctl status patchpilot-api patchpilot-worker" >&2
  exit 1
fi
grep -q '^PP_DOCKER_RUNTIME=runsc' .env || echo "WARNING: PP_DOCKER_RUNTIME=runsc is not set in .env (B19 needs gVisor)" >&2
echo "Public URL: sudo tailscale funnel --bg 8000 (once); logs: data/patchpilot-{api,worker}.{log,err}"
