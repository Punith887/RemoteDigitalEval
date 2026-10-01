# Pure Python Continuous Integration & Continuous Deployment (CI/CD) Pipeline
*100% Native Python Execution • Zero GitHub Actions • Automated Webhooks & Live Deployment*

## 🎯 Architecture Overview

```text
Developer
   ↓
git push / PR merge
   ↓
GitHub main
   ↓
GitHub Webhook (HTTP POST) / Local Trigger / CLI Execution
   ↓
Pure Python CI/CD Engine (scripts/cicd_pipeline.py)
   │
   ├─► [STAGE 1: CI - CONTINUOUS INTEGRATION]
   │    1. Python Syntax & AST Integrity (all backend, identity, storage, scripts)
   │    2. Config & Docker Compose Validation (.env.example, docker-compose.yml)
   │    3. Security & Secret Leak Scanner (zero unmasked tokens or conflict markers)
   │    4. Service Test Suites (Django apps, Identity Store, Storage Gateway)
   │    5. Frontend Code & Dependencies Sanity Check
   │    └──► QUALITY GATE: If ANY test fails -> Abort CD & alert developer!
   │
   └─► [STAGE 2: CD - CONTINUOUS DEPLOYMENT] (Only if CI passes 100%)
        1. git fetch main (git fetch origin main && git reset --hard origin/main)
        2. Smart Delta Analysis (identify changed services & migrations)
        3. Docker BuildKit Rebuild (targeted delta build)
        4. Docker Run & Container Restart (docker compose up -d)
        5. Automated Database Migrations (manage.py migrate --noinput)
        6. Live Health Verification (http://localhost:3000)
        └──► Application Updated & LIVE!
```

---

## ⚡ Key Highlights

1. **Zero GitHub Actions Dependencies**: 100% Python native execution. No GitHub Actions minutes consumed, no cloud runner timeouts, no external workflow limits.
2. **Built-in Continuous Integration (CI)**: Runs static code analysis, AST syntax verification, configuration integrity tests, security leak scans, and service tests automatically before any code is allowed to deploy.
3. **Automated Quality Gate**: If any test fails, CD deployment is immediately aborted to prevent broken builds from reaching production.
4. **Smart Delta Rebuilding (CD)**: Rebuilds only what actually changed using Docker BuildKit layer caching.
5. **Interactive Web Dashboard**: Accessible at `http://localhost:9090` with real-time CI test cards, CD stage status, live log streaming, and manual trigger controls.
6. **Multi-Mode Execution**:
   - `python scripts/cicd_pipeline.py --ci`: Run CI tests in console.
   - `python scripts/cicd_pipeline.py --cd`: Run CD deployment in console.
   - `python scripts/cicd_pipeline.py --full`: Run complete CI -> CD pipeline.
   - `python scripts/cicd_pipeline.py --server`: Launch Webhook receiver & Dashboard.
   - `python scripts/cicd_pipeline.py --watch`: Autonomous polling watcher mode.

---

## 🚀 Quick Start Guide

### Step 1: Start Webhook Server on Central Laptop

You can start the server using either the Windows batch file or PowerShell:

**Batch File:**
```cmd
.\scripts\run_webhook.cmd
```

**PowerShell:**
```powershell
.\scripts\run_webhook.ps1 -Port 9090 -Branch main
```

**Direct Python:**
```powershell
python .\scripts\github_webhook_deployer.py --port 9090 --branch main
```

Once running:
- **Web Dashboard**: [http://localhost:9090](http://localhost:9090)
- **Webhook Endpoint**: `http://localhost:9090/webhook`

---

### Step 2: Connect GitHub Webhook to Central Laptop

Because your central laptop is behind a local router/NAT, use a webhook forwarder so GitHub can reach your laptop:

#### Option A: Smee.io (Recommended — Zero Account, Zero Config)
GitHub's official open-source webhook proxy:
1. Open [https://smee.io/new](https://smee.io/new) in your browser.
2. Copy your generated Smee URL (e.g. `https://smee.io/abc123xyz`).
3. Start the forwarder on your laptop:
   ```powershell
   .\scripts\setup_tunnel.ps1 -Mode smee -SmeeUrl https://smee.io/abc123xyz
   ```
4. In your GitHub repository:
   - Go to **Settings** &rarr; **Webhooks** &rarr; **Add webhook**.
   - **Payload URL**: `https://smee.io/abc123xyz`
   - **Content type**: `application/json`
   - **Events**: `Just the push event`
   - **Active**: Checked ✅
   - Click **Add webhook**.

#### Option B: Cloudflare Tunnel (Quick Tunnel)
If you have `cloudflared`:
```powershell
cloudflared tunnel --url http://localhost:9090
```
Use the generated `https://*.trycloudflare.com/webhook` as your GitHub Webhook Payload URL.

#### Option C: ngrok
```powershell
ngrok http 9090
```
Use the generated `https://*.ngrok-free.app/webhook` as your GitHub Webhook Payload URL.

---

### Step 3: Test Webhook Locally

You can test the entire pipeline locally without pushing to GitHub:

```powershell
# Send a test push event
python .\scripts\test_webhook.py --event push --author "Developer" --message "Testing live webhook deployment"

# Send a test ping event
python .\scripts\test_webhook.py --event ping
```

---

## 🔒 Security (Optional HMAC Webhook Secret)

To prevent unauthorized parties from triggering deployments, configure a secret:

1. In GitHub Webhook settings, enter a secret string in the **Secret** field (e.g. `my-secure-token-123`).
2. Start the webhook server with the secret:
   ```powershell
   .\scripts\run_webhook.ps1 -Secret "my-secure-token-123"
   ```
   or set environment variable:
   ```cmd
   set GITHUB_WEBHOOK_SECRET=my-secure-token-123
   ```
The server will verify every request against `X-Hub-Signature-256` and reject invalid requests with `HTTP 403`.

---

## 📂 File Directory

| File | Purpose |
|---|---|
| [`scripts/github_webhook_deployer.py`](file:///scripts/github_webhook_deployer.py) | Core Python webhook server & live deployment engine |
| [`scripts/run_webhook.cmd`](file:///scripts/run_webhook.cmd) | Windows batch quick-launcher |
| [`scripts/run_webhook.ps1`](file:///scripts/run_webhook.ps1) | PowerShell runner with configuration options |
| [`scripts/setup_tunnel.ps1`](file:///scripts/setup_tunnel.ps1) | Tunnel / proxy helper (Smee.io / Cloudflare / ngrok) |
| [`scripts/test_webhook.py`](file:///scripts/test_webhook.py) | Local webhook simulator & verification test tool |
| [`scripts/deploy_live.ps1`](file:///scripts/deploy_live.ps1) | Supporting PowerShell deployment script |
