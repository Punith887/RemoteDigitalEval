#!/usr/bin/env python3
"""
=============================================================================
CENTRAL LAPTOP GITHUB WEBHOOK LIVE CI/CD PIPELINE
Zero GitHub Actions — 100% Python Native Execution
=============================================================================
Architecture:
  Developer
     ↓
  git push / PR merge
     ↓
  GitHub main
     ↓
  GitHub Webhook (HTTP POST)
     ↓
  Your Python program (github_webhook_deployer.py / cicd_pipeline.py)
     │
     ├─► [STAGE 1: CI - CONTINUOUS INTEGRATION]
     │    1. Python Code Quality & AST Syntax Check (compileall + ast.parse)
     │    2. Config & Docker Compose Validation (YAML structure, .env.example)
     │    3. Security & Secret Leak Scanner (unmasked tokens, merge conflicts)
     │    4. Service Test Verification (Django, Identity, Storage Gateway)
     │    5. Frontend Code & Dependencies Sanity Check
     │    └──► QUALITY GATE: If ANY test fails -> ABORT CD & Report!
     │
     └─► [STAGE 2: CD - CONTINUOUS DEPLOYMENT] (Only if CI passes 100%)
          1. Git Fetch & Fast-Forward (git fetch origin main && git reset --hard)
          2. Smart Delta Analysis (identify changed services & migrations)
          3. Docker BuildKit Rebuild (targeted delta build)
          4. Docker Run & Container Restart (docker compose up -d)
          5. Automated Database Migrations (manage.py migrate --noinput)
          6. Live Health Verification (http://localhost:3000)
          └──► Application Updated & LIVE!
=============================================================================
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cicd_pipeline import main

if __name__ == "__main__":
    main()
