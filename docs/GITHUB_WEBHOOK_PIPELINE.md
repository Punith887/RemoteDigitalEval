# Central Laptop GitHub Webhook Continuous Deployment Pipeline

## 🎯 Architecture Overview

```text
Developer
   ↓
git push / PR merge
   ↓
GitHub main
   ↓
GitHub Webhook (HTTP POST payload)
   ↓
Your Python program (scripts/github_webhook_deployer.py)
   ↓
git fetch main (git fetch origin main && git reset --hard origin/main)
   ↓
Docker build (BuildKit cached / smart delta build)
   ↓
Docker run/restart (docker compose up -d)
   ↓
Application updated (Verified LIVE at http://localhost:3000)
```

---

## ⚡ Key Highlights

1. **Direct Event-Driven (No Polling, No Idle Waste)**: Runs instantly when a commit lands on `main`.
2. **Instant Response to GitHub (<100ms)**: Responds with `HTTP 202 Accepted` immediately so GitHub never experiences webhook timeouts.
3. **Queue & Concurrency Protected**: Incoming commits are processed sequentially in a background worker thread. Overlapping pushes are safely handled without race conditions.
4. **Smart Delta Rebuilding**: Inspects `git diff` between previous and new HEAD.
   - Docs/Markdown/Scripts only: Git fast-sync without rebuilding containers.
   - Targeted container rebuilds: Backend, frontend, identity, or storage rebuild only what changed.
   - Database migrations: Automatically applies `python manage.py migrate --noinput` when migrations are detected.
5. **Interactive Web Dashboard**: Accessible at `http://localhost:9090` with real-time pipeline status, commit metadata, container metrics, and live log streaming.
6. **Zero Dependencies**: Uses Python standard library only. Runs on Python 3.8+ out of the box.

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
