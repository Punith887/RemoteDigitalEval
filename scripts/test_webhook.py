#!/usr/bin/env python3
"""
ADMIEZO Local GitHub Webhook Simulator
Tests the central laptop webhook deployment server without needing a live GitHub push.
"""

import sys
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def send_mock_webhook(url="http://localhost:9090/webhook", event="push", branch="main", secret="", author="DevTester", message="Test push from local developer"):
    print("=" * 60)
    print(f">> Sending simulated GitHub '{event}' event to {url}...")
    print(f">> Target Branch : refs/heads/{branch}")
    print(f">> Author        : {author}")
    print(f">> Message       : {message}")
    print("=" * 60)

    if event == "ping":
        payload = {
            "zen": "Encourage flow over perfection.",
            "hook_id": 12345678,
            "hook": {
                "type": "Repository",
                "id": 12345678,
                "name": "web",
                "active": True,
                "events": ["push"],
            }
        }
    else:
        fake_sha = hashlib.sha1(str(time.time()).encode()).hexdigest()
        payload = {
            "ref": f"refs/heads/{branch}",
            "before": "0000000000000000000000000000000000000000",
            "after": fake_sha,
            "repository": {
                "name": "RemoteDigitalEval",
                "full_name": "Punith887/RemoteDigitalEval",
                "html_url": "https://github.com/Punith887/RemoteDigitalEval"
            },
            "pusher": {
                "name": author,
                "email": f"{author.lower()}@example.com"
            },
            "head_commit": {
                "id": fake_sha,
                "message": message,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "author": {
                    "name": author,
                    "email": f"{author.lower()}@example.com"
                }
            }
        }

    raw_body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Hookshot/1.0",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": hashlib.md5(str(time.time()).encode()).hexdigest()
    }

    if secret:
        sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = sig

    req = urllib.request.Request(url, data=raw_body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.status
            resp_body = resp.read().decode("utf-8")
            print(f"\n[RESPONSE] Status: HTTP {status_code}")
            try:
                formatted = json.dumps(json.loads(resp_body), indent=2)
                print(f"[RESPONSE BODY]:\n{formatted}")
            except Exception:
                print(f"[RESPONSE BODY]:\n{resp_body}")
            print("\n✅ Simulation request accepted by webhook server!")
    except urllib.error.HTTPError as e:
        print(f"\n[HTTP ERROR] Status: {e.code}")
        print(f"[ERROR BODY]: {e.read().decode('utf-8')}")
    except urllib.error.URLError as e:
        print(f"\n[CONNECTION ERROR] Could not connect to {url}: {e.reason}")
        print("Please ensure the Python webhook server is running (scripts\\run_webhook.cmd).")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Simulate GitHub Webhook call")
    parser.add_argument("--url", default="http://localhost:9090/webhook", help="Webhook receiver URL")
    parser.add_argument("--event", default="push", choices=["push", "ping"], help="GitHub event type")
    parser.add_argument("--branch", default="main", help="Target branch")
    parser.add_argument("--secret", default="", help="HMAC secret if enabled")
    parser.add_argument("--author", default="Developer", help="Author name")
    parser.add_argument("--message", default="Automated webhook test commit", help="Commit message")
    args = parser.parse_args()

    send_mock_webhook(
        url=args.url,
        event=args.event,
        branch=args.branch,
        secret=args.secret,
        author=args.author,
        message=args.message
    )
