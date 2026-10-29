# Deploy on the host laptop (architecture §2): pull, build, restart API + worker, check health.
# Usage (PowerShell, repo root):  ./scripts/deploy.ps1
$ErrorActionPreference = "Stop"
git pull --rebase
uv sync
Push-Location web; npm ci --no-audit --no-fund; npm run build; Pop-Location
docker build -q -t pp-base:3.12 -f infra/Dockerfile.base infra | Out-Null
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*backend.worker.main*' -or $_.CommandLine -like '*uvicorn*backend.api.main*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force data | Out-Null
Start-Process -WindowStyle Hidden uv -ArgumentList "run","uvicorn","backend.api.main:app","--host","127.0.0.1","--port","8000" -RedirectStandardOutput data/api.log -RedirectStandardError data/api.err
Start-Process -WindowStyle Hidden uv -ArgumentList "run","python","-m","backend.worker.main" -RedirectStandardOutput data/worker.log -RedirectStandardError data/worker.err
Start-Sleep 6
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json
Write-Host "Public URL: run 'tailscale funnel --bg 8000' once; then open https://<host>.<tailnet>.ts.net"
