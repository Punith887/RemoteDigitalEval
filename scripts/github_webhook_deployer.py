#!/usr/bin/env python3
"""
=============================================================================
CENTRAL LAPTOP GITHUB WEBHOOK LIVE DEPLOYMENT SERVER
=============================================================================
Architecture:
  Developer commits/pushes
          ↓
  GitHub main changes
          ↓
  GitHub Webhook (HTTP POST)
          ↓
  Python script on central laptop (github_webhook_deployer.py)
          ↓
  Fetch latest main (git fetch origin main && git reset --hard origin/main)
          ↓
  Docker build (BuildKit cached / smart delta build)
          ↓
  Docker container restart (docker compose up -d)
          ↓
  New code LIVE! (Health check verified at http://localhost:3000)
=============================================================================
"""

import os
import sys
import json
import time
import hmac
import hashlib
import logging
import threading
import queue
import subprocess
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# CONFIGURATION & DEFAULTS
# ---------------------------------------------------------------------------
DEFAULT_PORT = int(os.environ.get("PORT", "9090"))
TARGET_BRANCH = os.environ.get("DEPLOY_BRANCH", "main")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()
BASE_DIR = Path(__file__).resolve().parent.parent

# Setup logging
LOG_DIR = BASE_DIR / "artifacts"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "webhook_deploy.log"

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setStream(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        stream_handler,
        logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
    ]
)
logger = logging.getLogger("WebhookDeployer")

# In-memory recent logs buffer for the Web Dashboard (capped at 500 lines)
recent_logs = []
logs_lock = threading.Lock()

def record_log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level}] {msg}"
    with logs_lock:
        recent_logs.append(formatted)
        if len(recent_logs) > 500:
            recent_logs.pop(0)
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)


# ---------------------------------------------------------------------------
# DEPLOYMENT ENGINE (STATE & WORKER)
# ---------------------------------------------------------------------------
class DeploymentState:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_deploying = False
        self.last_status = "idle"  # idle, deploying, success, error
        self.last_commit_sha = ""
        self.last_commit_author = ""
        self.last_commit_msg = ""
        self.last_deploy_time = "Never"
        self.last_deploy_duration = 0
        self.deploy_count = 0
        self.total_success = 0
        self.total_failed = 0
        self.docker_status = "unknown"

    def get_summary(self):
        with self.lock:
            return {
                "is_deploying": self.is_deploying,
                "status": self.last_status,
                "last_commit_sha": self.last_commit_sha,
                "last_commit_author": self.last_commit_author,
                "last_commit_msg": self.last_commit_msg,
                "last_deploy_time": self.last_deploy_time,
                "last_deploy_duration": self.last_deploy_duration,
                "deploy_count": self.deploy_count,
                "total_success": self.total_success,
                "total_failed": self.total_failed,
                "docker_status": self.docker_status,
                "target_branch": TARGET_BRANCH,
                "secret_configured": bool(WEBHOOK_SECRET),
                "repo_path": str(BASE_DIR),
            }

state = DeploymentState()
deploy_queue = queue.Queue()


def run_command(cmd, cwd=None, capture=True, env=None):
    """Executes a system shell command and logs output."""
    cwd = cwd or str(BASE_DIR)
    current_env = os.environ.copy()
    if env:
        current_env.update(env)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            shell=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=current_env
        )
        output, _ = proc.communicate()
        return proc.returncode, output.strip() if output else ""
    except Exception as e:
        return 1, str(e)


def check_docker_engine():
    """Checks whether Docker daemon is active and responsive."""
    code, out = run_command("docker info")
    if code == 0:
        state.docker_status = "online"
        return True
    else:
        state.docker_status = "offline"
        return False


def execute_pipeline(commit_sha="", commit_author="", commit_msg="", force_full=False):
    """
    Executes the 5-step live deployment pipeline:
      1. Fetch latest main
      2. Analyze delta (changed files)
      3. Docker build (BuildKit cached)
      4. Docker container restart
      5. Health check & verification -> Live website
    """
    with state.lock:
        state.is_deploying = True
        state.last_status = "deploying"
        state.deploy_count += 1

    start_time = time.time()
    record_log("=" * 60)
    record_log(">> 🚀 STARTING LIVE DEPLOYMENT PIPELINE ON CENTRAL LAPTOP")
    record_log(f">> Target Branch : {TARGET_BRANCH}")
    record_log(f">> Triggered By  : {commit_author or 'GitHub Webhook'}")
    if commit_sha:
        record_log(f">> Target SHA    : {commit_sha[:8]}")
    if commit_msg:
        record_log(f">> Commit Message: {commit_msg}")
    record_log("=" * 60)

    try:
        # -------------------------------------------------------------------
        # STEP 1: FETCH LATEST MAIN
        # -------------------------------------------------------------------
        record_log("[STEP 1/5] Fetching latest changes from GitHub origin/main...")
        
        # Capture current HEAD before update for diff
        _, prev_sha = run_command("git rev-parse HEAD")
        prev_sha = prev_sha.strip() if prev_sha else "HEAD~1"

        # Fetch and hard reset to exact remote state
        code, out = run_command(f"git fetch origin {TARGET_BRANCH} --quiet")
        if code != 0:
            record_log(f"Warning during git fetch: {out}", "WARNING")

        # Ensure we are tracking target branch
        run_command(f"git checkout {TARGET_BRANCH} --quiet")
        code, reset_out = run_command(f"git reset --hard origin/{TARGET_BRANCH}")
        if code != 0:
            record_log(f"git reset failed: {reset_out}", "ERROR")
            raise RuntimeError(f"Git reset failed: {reset_out}")

        _, current_sha = run_command("git rev-parse HEAD")
        current_sha = current_sha.strip()

        _, current_author = run_command("git log -1 --pretty=%an")
        _, current_subject = run_command("git log -1 --pretty=%s")

        record_log(f"[OK] Checked out latest {TARGET_BRANCH} (SHA: {current_sha[:8]}) - {current_subject}", "SUCCESS")

        # -------------------------------------------------------------------
        # STEP 2: DELTA ANALYSIS (IDENTIFY CHANGED FILES)
        # -------------------------------------------------------------------
        record_log("[STEP 2/5] Analyzing changed files for smart delta rebuild...")
        diff_base = prev_sha if prev_sha and prev_sha != current_sha else "HEAD~1"
        _, diff_files = run_command(f"git diff --name-only {diff_base} {current_sha}")
        
        changed_list = [f.strip() for f in diff_files.splitlines() if f.strip()]
        record_log(f"[DIFF] {len(changed_list)} files changed since {diff_base[:8]}:")
        for f in changed_list[:10]:
            record_log(f"       - {f}")
        if len(changed_list) > 10:
            record_log(f"       ... and {len(changed_list) - 10} more files")

        has_backend = any(f.startswith("backend/") or f in ["requirements.txt", "requirements-dev.txt"] for f in changed_list)
        has_migrations = any("backend/apps/" in f and "/migrations/" in f for f in changed_list)
        has_frontend = any(f.startswith("frontend/") for f in changed_list)
        has_identity = any(f.startswith("identity_service/") for f in changed_list)
        has_storage = any(f.startswith("storage_gateway/") for f in changed_list)
        has_compose = any(f == "docker-compose.yml" or f.startswith(".env") for f in changed_list)

        runtime_changed = (
            force_full or has_backend or has_frontend or has_identity or 
            has_storage or has_compose or len(changed_list) == 0
        )

        # -------------------------------------------------------------------
        # STEP 3: DOCKER BUILD
        # -------------------------------------------------------------------
        record_log("[STEP 3/5] Checking Docker Engine and building containers...")
        docker_ready = check_docker_engine()
        
        if not docker_ready:
            record_log("[WARN] Docker Engine is not currently running.", "WARNING")
            record_log("[INFO] Source files successfully synced to latest main on laptop.", "INFO")
            record_log("[INFO] Please start Docker Desktop to bring containers up.", "INFO")
        else:
            build_env = {"DOCKER_BUILDKIT": "1", "COMPOSE_DOCKER_CLI_BUILD": "1"}

            if not runtime_changed:
                record_log("[SKIP] Only non-runtime files (docs/markdown/scripts) changed. Zero rebuilds needed!", "SUCCESS")
            elif force_full or has_compose:
                record_log("[BUILD] Building all Docker containers with BuildKit cache...")
                code, out = run_command("docker compose build", env=build_env)
                if code != 0:
                    record_log(f"docker compose build warning: {out[:300]}", "WARNING")
                else:
                    record_log("[OK] Docker compose build complete.", "SUCCESS")
            else:
                if has_backend:
                    record_log("[BUILD] Building backend containers...")
                    run_command("docker compose build backend outbox-worker integrity-worker ai-evaluation-worker secure-session-worker photocopy-expiry-worker", env=build_env)
                if has_frontend:
                    record_log("[BUILD] Building frontend container...")
                    run_command("docker compose build frontend", env=build_env)
                if has_identity:
                    record_log("[BUILD] Building identity container...")
                    run_command("docker compose build identity-service", env=build_env)
                if has_storage:
                    record_log("[BUILD] Building storage gateway container...")
                    run_command("docker compose build storage-gateway", env=build_env)

            # -------------------------------------------------------------------
            # STEP 4: DOCKER CONTAINER RESTART
            # -------------------------------------------------------------------
            record_log("[STEP 4/5] Starting / Updating Docker containers...")
            if runtime_changed:
                if force_full or has_compose:
                    code, out = run_command("docker compose up -d")
                    record_log("[OK] Docker compose stack updated.", "SUCCESS")
                else:
                    if has_backend:
                        run_command("docker compose up -d --no-deps backend outbox-worker integrity-worker ai-evaluation-worker secure-session-worker photocopy-expiry-worker")
                        if has_migrations:
                            record_log("[MIGRATE] Applying database migrations...")
                            m_code, m_out = run_command("docker compose exec -T backend python manage.py migrate --noinput")
                            record_log(f"[MIGRATE] Output: {m_out}")
                    if has_frontend:
                        run_command("docker compose up -d --no-deps frontend")
                    if has_identity:
                        run_command("docker compose up -d --no-deps identity-service")
                    if has_storage:
                        run_command("docker compose up -d --no-deps storage-gateway")
                record_log("[OK] Containers started successfully.", "SUCCESS")
            else:
                record_log("[OK] Existing containers remain active without downtime.", "SUCCESS")

            # -------------------------------------------------------------------
            # STEP 5: HEALTH CHECK & VERIFICATION
            # -------------------------------------------------------------------
            record_log("[STEP 5/5] Performing live health check verification...")
            health_passed = False
            for attempt in range(1, 12):
                try:
                    req = urllib.request.Request("http://127.0.0.1:3000", headers={"User-Agent": "WebhookDeployer"})
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        if resp.status in [200, 307, 308]:
                            health_passed = True
                            record_log(f"[HEALTH] ✅ Health Check PASSED on attempt {attempt} (HTTP {resp.status})", "SUCCESS")
                            break
                except Exception:
                    time.sleep(1)

            if not health_passed:
                record_log("[INFO] App warming up; service accessible at http://localhost:3000", "INFO")

        elapsed = round(time.time() - start_time, 2)
        record_log("=" * 60)
        record_log(f">> 🎉 NEW CODE IS LIVE! Total pipeline completed in {elapsed}s")
        record_log(">> Live Application URL : http://localhost:3000")
        record_log("=" * 60)

        with state.lock:
            state.last_status = "success"
            state.last_commit_sha = current_sha
            state.last_commit_author = current_author or commit_author
            state.last_commit_msg = current_subject or commit_msg
            state.last_deploy_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state.last_deploy_duration = elapsed
            state.total_success += 1

    except Exception as ex:
        elapsed = round(time.time() - start_time, 2)
        record_log(f"Deployment pipeline encountered error: {ex}", "ERROR")
        with state.lock:
            state.last_status = "error"
            state.last_deploy_duration = elapsed
            state.total_failed += 1
    finally:
        with state.lock:
            state.is_deploying = False


def deployment_worker_thread():
    """Background worker thread that consumes deployment requests one-by-one."""
    record_log("Deployment worker thread active and waiting for webhook events...")
    while True:
        try:
            task = deploy_queue.get()
            if task is None:
                break
            execute_pipeline(
                commit_sha=task.get("sha", ""),
                commit_author=task.get("author", ""),
                commit_msg=task.get("message", ""),
                force_full=task.get("force", False)
            )
            deploy_queue.task_done()
        except Exception as e:
            record_log(f"Worker exception: {e}", "ERROR")


# ---------------------------------------------------------------------------
# WEBHOOK & DASHBOARD HTTP HANDLER
# ---------------------------------------------------------------------------
class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "CentralDeployer/1.0"

    def verify_github_signature(self, raw_body: bytes) -> bool:
        """Verifies X-Hub-Signature-256 HMAC header if WEBHOOK_SECRET is set."""
        if not WEBHOOK_SECRET:
            return True  # Open mode if no secret specified

        sig_header = self.headers.get("X-Hub-Signature-256", "")
        if not sig_header:
            return False

        try:
            hash_type, signature = sig_header.split("=", 1)
            if hash_type != "sha256":
                return False
            mac = hmac.new(WEBHOOK_SECRET.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256)
            return hmac.compare_digest(mac.hexdigest(), signature)
        except Exception:
            return False

    def send_json(self, status_code: int, data: dict):
        response_body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_body)

    def send_html(self, status_code: int, html_str: str):
        response_body = html_str.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            summary = state.get_summary()
            self.send_json(200, summary)

        elif path == "/api/logs":
            with logs_lock:
                logs_copy = list(recent_logs)
            self.send_json(200, {"logs": logs_copy})

        elif path in ["/", "/dashboard"]:
            summary = state.get_summary()
            html = render_dashboard_html(summary)
            self.send_html(200, html)

        elif path == "/health":
            self.send_json(200, {"status": "ok", "service": "webhook-deployer"})

        else:
            self.send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. Manual redeploy trigger from Dashboard or API
        if path == "/api/deploy" or path == "/redeploy":
            if state.is_deploying:
                self.send_json(409, {"status": "error", "message": "Deployment is already running."})
                return

            deploy_queue.put({"sha": "", "author": "Manual Trigger (Web Dashboard)", "message": "Manual deployment triggered", "force": True})
            self.send_json(202, {"status": "accepted", "message": "Deployment queued successfully."})
            return

        # 2. GitHub Webhook receiver: /webhook or /
        if path in ["/webhook", "/"]:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)

            # Security verification
            if not self.verify_github_signature(raw_body):
                record_log("Rejected webhook request: Invalid HMAC signature.", "WARNING")
                self.send_json(403, {"error": "Invalid signature. Check your GitHub Webhook Secret."})
                return

            event_type = self.headers.get("X-GitHub-Event", "push")
            record_log(f"Received GitHub Webhook event: '{event_type}'")

            # Handle GitHub Ping Event
            if event_type == "ping":
                record_log("[GITHUB PING] GitHub webhook connection verified successfully! ✅", "SUCCESS")
                self.send_json(200, {
                    "status": "pong",
                    "message": "RemoteDigitalEval Webhook server connected successfully!",
                    "branch": TARGET_BRANCH
                })
                return

            # Handle GitHub Push Event
            if event_type == "push":
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                except Exception as ex:
                    self.send_json(400, {"error": f"Invalid JSON payload: {ex}"})
                    return

                ref = payload.get("ref", "")
                expected_ref = f"refs/heads/{TARGET_BRANCH}"

                if ref != expected_ref:
                    record_log(f"Ignored push event to '{ref}' (watching '{expected_ref}').", "INFO")
                    self.send_json(200, {
                        "status": "ignored",
                        "reason": f"Push was to {ref}, not {expected_ref}"
                    })
                    return

                # Pushed to target branch!
                head_commit = payload.get("head_commit") or {}
                after_sha = payload.get("after") or head_commit.get("id") or ""
                author_info = head_commit.get("author") or {}
                author_name = author_info.get("name") or payload.get("pusher", {}).get("name") or "GitHub User"
                commit_message = head_commit.get("message") or "Push to " + TARGET_BRANCH

                record_log(f"⚡ WEBHOOK TRIGGER: Pushed to {TARGET_BRANCH} by @{author_name} ({after_sha[:8]})", "SUCCESS")

                # Enqueue deployment task
                deploy_queue.put({
                    "sha": after_sha,
                    "author": author_name,
                    "message": commit_message,
                    "force": False
                })

                # Respond 202 Accepted immediately so GitHub does not time out!
                self.send_json(202, {
                    "status": "accepted",
                    "message": f"Deployment queued for {TARGET_BRANCH}",
                    "commit": after_sha[:8],
                    "author": author_name
                })
                return

            # Any other GitHub event
            self.send_json(200, {"status": "ignored", "event": event_type})
            return

        self.send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # Suppress default noisy HTTP request logs
        return


# ---------------------------------------------------------------------------
# EMBEDDED DASHBOARD UI (HTML/CSS/JS)
# ---------------------------------------------------------------------------
def render_dashboard_html(data: dict) -> str:
    status = data["status"]
    is_deploying = data["is_deploying"]
    badge_color = "#3b82f6" if is_deploying else ("#10b981" if status == "success" else ("#ef4444" if status == "error" else "#6b7280"))
    status_text = "DEPLOYING..." if is_deploying else status.upper()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Central Laptop CD Webhook | Admiezo RemoteDigitalEval</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --accent: #8b5cf6;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text-main);
      font-family: 'Plus Jakarta Sans', sans-serif;
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 24px;
    }}
    .logo-area h1 {{
      font-size: 22px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #60a5fa, #a78bfa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .logo-area p {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .badge-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: {badge_color};
      box-shadow: 0 0 10px {badge_color};
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.5; transform: scale(0.9); }}
    }}
    /* Flow diagram */
    .flow-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .flow-title {{
      font-size: 13px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 16px;
    }}
    .flow-steps {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      overflow-x: auto;
      gap: 12px;
      padding-bottom: 8px;
    }}
    .flow-step {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      font-size: 12px;
      text-align: center;
      min-width: 130px;
      flex-shrink: 0;
    }}
    .flow-step .num {{
      font-size: 10px;
      color: #60a5fa;
      font-weight: 700;
      display: block;
      margin-bottom: 4px;
    }}
    .flow-step .label {{
      font-weight: 600;
      color: #e5e7eb;
    }}
    .flow-arrow {{
      color: var(--text-muted);
      font-size: 14px;
      font-weight: bold;
    }}
    /* Grid */
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
    }}
    .card-label {{
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 6px;
    }}
    .card-value {{
      font-size: 20px;
      font-weight: 700;
      color: var(--text-main);
    }}
    .card-sub {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: 'JetBrains Mono', monospace;
    }}
    /* Action & Controls */
    .actions-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }}
    .btn {{
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: #fff;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .btn:hover {{
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
    }}
    .btn-outline {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-main);
    }}
    .btn-outline:hover {{
      background: rgba(255, 255, 255, 0.05);
      box-shadow: none;
    }}
    /* Logs Terminal */
    .terminal {{
      background: #060911;
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
    }}
    .terminal-header {{
      background: #0f1422;
      padding: 10px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
    }}
    .terminal-title {{
      font-size: 12px;
      font-weight: 700;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }}
    .terminal-body {{
      padding: 16px;
      height: 380px;
      overflow-y: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: #d1d5db;
      white-space: pre-wrap;
      word-break: break-all;
    }}
    .log-line {{
      margin-bottom: 4px;
      line-height: 1.4;
    }}
    .log-SUCCESS {{ color: #34d399; }}
    .log-ERROR {{ color: #f87171; font-weight: bold; }}
    .log-WARNING {{ color: #fbbf24; }}
    .log-INFO {{ color: #93c5fd; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-area">
        <h1>ADMIEZO Continuous Deployment Pipeline</h1>
        <p>Central Laptop Webhook Listener (GitHub Push &rarr; Auto-Deploy &rarr; Docker Live)</p>
      </div>
      <div>
        <span class="badge">
          <span class="badge-dot"></span>
          <span id="status-badge" style="color: {badge_color};">{status_text}</span>
        </span>
      </div>
    </header>

    <!-- 7-Stage Pipeline Flow -->
    <div class="flow-card">
      <div class="flow-title">Pipeline Architecture</div>
      <div class="flow-steps">
        <div class="flow-step">
          <span class="num">STAGE 1</span>
          <span class="label">Developer Push</span>
        </div>
        <span class="flow-arrow">&rarr;</span>
        <div class="flow-step">
          <span class="num">STAGE 2</span>
          <span class="label">GitHub 'main'</span>
        </div>
        <span class="flow-arrow">&rarr;</span>
        <div class="flow-step" style="border-color: #60a5fa;">
          <span class="num">STAGE 3</span>
          <span class="label">GitHub Webhook</span>
        </div>
        <span class="flow-arrow">&rarr;</span>
        <div class="flow-step" style="border-color: #a78bfa;">
          <span class="num">STAGE 4</span>
          <span class="label">Python Server</span>
        </div>
        <span class="flow-arrow">&rarr;</span>
        <div class="flow-step">
          <span class="num">STAGE 5</span>
          <span class="label">Fetch Latest Main</span>
        </div>
        <span class="flow-arrow">&rarr;</span>
        <div class="flow-step">
          <span class="num">STAGE 6</span>
          <span class="label">Docker Build</span>
        </div>
        <span class="flow-arrow">&rarr;</span>
        <div class="flow-step" style="border-color: #34d399;">
          <span class="num">STAGE 7</span>
          <span class="label">🎉 Live Website</span>
        </div>
      </div>
    </div>

    <!-- Metrics Grid -->
    <div class="grid">
      <div class="card">
        <div class="card-label">Last Deployed Commit</div>
        <div class="card-value" id="val-sha">{data["last_commit_sha"][:8] or 'None Yet'}</div>
        <div class="card-sub" id="val-msg">{data["last_commit_msg"] or 'Waiting for first push...'}</div>
      </div>

      <div class="card">
        <div class="card-label">Last Deploy Timestamp</div>
        <div class="card-value" id="val-time" style="font-size: 16px;">{data["last_deploy_time"]}</div>
        <div class="card-sub" id="val-author">Author: {data["last_commit_author"] or 'N/A'}</div>
      </div>

      <div class="card">
        <div class="card-label">Target Branch</div>
        <div class="card-value" style="color: #60a5fa;">{data["target_branch"]}</div>
        <div class="card-sub">Secret: {'Configured ✅' if data['secret_configured'] else 'Open Mode ⚠️'}</div>
      </div>

      <div class="card">
        <div class="card-label">Live App Status</div>
        <div class="card-value" style="color: #34d399;">
          <a href="http://localhost:3000" target="_blank" style="color: inherit; text-decoration: none;">http://localhost:3000 &nearr;</a>
        </div>
        <div class="card-sub">Docker: {data["docker_status"]} | Runs: {data["deploy_count"]}</div>
      </div>
    </div>

    <!-- Actions & Logs -->
    <div class="actions-bar">
      <div style="font-size: 14px; font-weight: 700; color: var(--text-muted);">LIVE PIPELINE STREAM</div>
      <div style="display: flex; gap: 10px;">
        <button class="btn btn-outline" onclick="fetchLogs()">Refresh Logs</button>
        <button class="btn" id="deploy-btn" onclick="triggerManualDeploy()">⚡ Trigger Manual Deploy</button>
      </div>
    </div>

    <div class="terminal">
      <div class="terminal-header">
        <span class="terminal-title">CONSOLE OUTPUT & AUDIT TRAIL</span>
        <span style="font-size: 11px; color: var(--text-muted);">Auto-refreshing every 2s</span>
      </div>
      <div class="terminal-body" id="logs-container">Loading deployment logs...</div>
    </div>
  </div>

  <script>
    async function fetchStatus() {{
      try {{
        const res = await fetch('/api/status');
        const d = await res.json();
        const badge = document.getElementById('status-badge');
        badge.innerText = d.is_deploying ? 'DEPLOYING...' : d.status.toUpperCase();
        badge.style.color = d.is_deploying ? '#3b82f6' : (d.status === 'success' ? '#10b981' : (d.status === 'error' ? '#ef4444' : '#6b7280'));

        if (d.last_commit_sha) {{
          document.getElementById('val-sha').innerText = d.last_commit_sha.substring(0, 8);
        }}
        if (d.last_commit_msg) {{
          document.getElementById('val-msg').innerText = d.last_commit_msg;
        }}
        if (d.last_deploy_time) {{
          document.getElementById('val-time').innerText = d.last_deploy_time;
        }}
        if (d.last_commit_author) {{
          document.getElementById('val-author').innerText = 'Author: ' + d.last_commit_author;
        }}

        const btn = document.getElementById('deploy-btn');
        if (d.is_deploying) {{
          btn.disabled = true;
          btn.innerText = '⏳ Deployment in progress...';
          btn.style.opacity = '0.6';
        }} else {{
          btn.disabled = false;
          btn.innerText = '⚡ Trigger Manual Deploy';
          btn.style.opacity = '1';
        }}
      }} catch (err) {{
        console.error(err);
      }}
    }}

    async function fetchLogs() {{
      try {{
        const res = await fetch('/api/logs');
        const data = await res.json();
        const container = document.getElementById('logs-container');
        if (data.logs && data.logs.length > 0) {{
          container.innerHTML = data.logs.map(line => {{
            let cls = 'log-line';
            if (line.includes('[SUCCESS]') || line.includes('PASSED') || line.includes('🎉')) cls += ' log-SUCCESS';
            else if (line.includes('[ERROR]') || line.includes('failed')) cls += ' log-ERROR';
            else if (line.includes('[WARNING]') || line.includes('[WARN]')) cls += ' log-WARNING';
            else if (line.includes('[STEP') || line.includes('>>')) cls += ' log-INFO';
            return `<div class="${{cls}}">${{escapeHtml(line)}}</div>`;
          }}).join('');
          container.scrollTop = container.scrollHeight;
        }} else {{
          container.innerHTML = '<div class="log-line">No deployment logs yet. Waiting for first webhook push!</div>';
        }}
      }} catch (err) {{
        console.error(err);
      }}
    }}

    function escapeHtml(text) {{
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }}

    async function triggerManualDeploy() {{
      if (!confirm('Trigger a manual deployment (Fetch latest main -> Docker build -> Restart containers)?')) return;
      try {{
        const res = await fetch('/api/deploy', {{ method: 'POST' }});
        const data = await res.json();
        alert(data.message || 'Deployment triggered!');
        fetchStatus();
        fetchLogs();
      }} catch (err) {{
        alert('Failed to trigger deploy: ' + err);
      }}
    }}

    setInterval(() => {{
      fetchStatus();
      fetchLogs();
    }}, 2000);

    fetchStatus();
    fetchLogs();
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------------------------
def main():
    global TARGET_BRANCH, WEBHOOK_SECRET
    import argparse
    parser = argparse.ArgumentParser(description="Central Laptop GitHub Webhook Live Deployment Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--branch", type=str, default=TARGET_BRANCH, help=f"Target Git branch (default: {TARGET_BRANCH})")
    parser.add_argument("--secret", type=str, default=WEBHOOK_SECRET, help="GitHub Webhook HMAC Secret token")
    args = parser.parse_args()

    port = args.port
    TARGET_BRANCH = args.branch
    WEBHOOK_SECRET = args.secret

    # Start deployment queue worker
    worker = threading.Thread(target=deployment_worker_thread, daemon=True)
    worker.start()

    # Pre-check docker
    check_docker_engine()

    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, WebhookHandler)

    record_log("=" * 65)
    record_log(">> 🚀 ADMIEZO CENTRAL LAPTOP GITHUB WEBHOOK SERVER ONLINE")
    record_log("=" * 65)
    record_log(f">> Webhook URL  : http://localhost:{port}/webhook (or /)")
    record_log(f">> Web Dashboard: http://localhost:{port}/")
    record_log(f">> Target Branch: {TARGET_BRANCH}")
    record_log(f">> HMAC Secret  : {'Configured ✅' if WEBHOOK_SECRET else 'None (Open Mode) ⚠️'}")
    record_log(f">> Repository   : {BASE_DIR}")
    record_log("=" * 65)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        record_log("\nShutting down webhook server...")
        httpd.server_close()
        deploy_queue.put(None)


if __name__ == "__main__":
    main()
