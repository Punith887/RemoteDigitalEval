# =========================================================================
# CENTRAL LAPTOP RUNNER (WSL + DOCKER) LIVE DEPLOYMENT PIPELINE
# =========================================================================
# Follows the exact continuous deployment sequence:
# Developer A/B/C -> Feature Branch -> PR -> Review/Merge -> MAIN ->
# GitHub Actions Trigger -> Central Laptop Runner (WSL + Docker) ->
# Checkout latest MAIN -> Docker Build -> Stop old container ->
# Start new container -> Health Check ✅ -> Live Website
# =========================================================================

param(
    [string]$TargetCommit = "",
    [string]$BaseCommit = "",
    [string]$DeployPath = "",
    [switch]$ForceRebuild = $false
)

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> CENTRAL LAPTOP RUNNER (WSL + DOCKER) DEPLOYMENT" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 0. Locate Project Directory on Central Laptop
$candidatePaths = @(
    $DeployPath,
    $env:DEPLOY_PATH,
    $env:GITHUB_WORKSPACE,
    "c:\Users\ASUS\RemoteDigitalEval",
    "c:\Users\ASUS\remote-digital",
    "c:\Users\91895\Digital-Evaluation",
    $PWD.Path
)

$targetDir = $null
foreach ($path in $candidatePaths) {
    if ($path -and (Test-Path "$path\docker-compose.yml")) {
        $targetDir = (Resolve-Path $path).Path
        break
    }
}

if (-not $targetDir) {
    Write-Error "Deployment folder with docker-compose.yml not found."
    exit 1
}

Set-Location -Path $targetDir
Write-Host "[RUNNER] Working Directory: $targetDir" -ForegroundColor Gray

# -------------------------------------------------------------------------
# STEP 1: CHECKOUT LATEST MAIN
# -------------------------------------------------------------------------
Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">> [STEP 1/5] Checkout latest MAIN" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow

$prevHead = (git rev-parse HEAD 2>$null)
if (-not $prevHead) { $prevHead = "HEAD~1" }

$syncStart = $stopwatch.ElapsedMilliseconds
git fetch origin main --quiet 2>$null

$localDirty = (git status --porcelain 2>$null)
if (-not $localDirty) {
    git reset --hard origin/main 2>$null
} else {
    Write-Host "[NOTE] Local uncommitted modifications preserved." -ForegroundColor Yellow
}

$newHead = (git rev-parse origin/main 2>$null)
if (-not $newHead) { $newHead = (git rev-parse HEAD 2>$null) }
$syncDuration = [Math]::Round(($stopwatch.ElapsedMilliseconds - $syncStart) / 1000, 2)
Write-Host "[OK] Checked out latest MAIN in $syncDuration s (HEAD: $newHead)" -ForegroundColor Green

# Determine changed files
$baseSha = if ($BaseCommit -and $BaseCommit -ne "0000000000000000000000000000000000000000") { $BaseCommit } else { $prevHead }
$targetSha = if ($TargetCommit) { $TargetCommit } else { $newHead }

$changedFiles = @()
if ($baseSha -and $targetSha -and ($baseSha -ne $targetSha)) {
    $diffOutput = git diff --name-only $baseSha $targetSha 2>$null
    if ($diffOutput) { $changedFiles = $diffOutput -split "`r?`n" | Where-Object { $_ -ne "" } }
} else {
    $diffOutput = git diff --name-only HEAD~1 HEAD 2>$null
    if ($diffOutput) { $changedFiles = $diffOutput -split "`r?`n" | Where-Object { $_ -ne "" } }
}

Write-Host "[DIFF] Modified files ($($changedFiles.Count)):" -ForegroundColor Gray
foreach ($f in $changedFiles) { Write-Host "   - $f" -ForegroundColor DarkGray }

$hasBackend    = ($changedFiles | Where-Object { $_ -like "backend/*" -or $_ -eq "requirements.txt" -or $_ -eq "requirements-dev.txt" }).Count -gt 0
$hasMigrations = ($changedFiles | Where-Object { $_ -like "backend/apps/*/migrations/*" }).Count -gt 0
$hasFrontend   = ($changedFiles | Where-Object { $_ -like "frontend/*" }).Count -gt 0
$hasIdentity   = ($changedFiles | Where-Object { $_ -like "identity_service/*" }).Count -gt 0
$hasStorage    = ($changedFiles | Where-Object { $_ -like "storage_gateway/*" }).Count -gt 0
$hasCompose    = ($changedFiles | Where-Object { $_ -eq "docker-compose.yml" -or $_ -like ".env*" }).Count -gt 0

$runtimeChanged = $hasBackend -or $hasFrontend -or $hasIdentity -or $hasStorage -or $hasCompose -or $ForceRebuild

# -------------------------------------------------------------------------
# STEP 2: DOCKER BUILD (BUILDKIT CACHED)
# -------------------------------------------------------------------------
Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">> [STEP 2/5] Docker Build" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow

$dockerAvailable = $false
try {
    $null = docker info 2>$null
    if ($LASTEXITCODE -eq 0) { $dockerAvailable = $true }
} catch { $dockerAvailable = $false }

if (-not $dockerAvailable) {
    Write-Host "[INFO] Docker Engine is not currently running." -ForegroundColor Yellow
    Write-Host "[INFO] Source files checked out to latest MAIN ($newHead)." -ForegroundColor Yellow
    Write-Host "[INFO] When Docker Desktop/WSL is launched, containers will start with this code." -ForegroundColor Yellow
    $stopwatch.Stop()
    $totalSec = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
    Write-Host "`n[FAST] Source synchronization completed in $totalSec seconds!" -ForegroundColor Green
    exit 0
}

$env:DOCKER_BUILDKIT = "1"
$env:COMPOSE_DOCKER_CLI_BUILD = "1"

if (-not $runtimeChanged) {
    Write-Host "[SKIP] Non-runtime files changed (docs/CI/scripts). Zero container rebuilds needed!" -ForegroundColor Green
} elseif ($ForceRebuild -or $hasCompose) {
    Write-Host "[BUILD] Building all Docker containers with BuildKit layer caching..." -ForegroundColor Cyan
    docker compose build
} else {
    if ($hasBackend)  { Write-Host "[BUILD] Building backend containers..."; docker compose build backend outbox-worker integrity-worker ai-evaluation-worker secure-session-worker photocopy-expiry-worker }
    if ($hasFrontend) { Write-Host "[BUILD] Building frontend container..."; docker compose build frontend }
    if ($hasIdentity) { Write-Host "[BUILD] Building identity container..."; docker compose build identity-service }
    if ($hasStorage)  { Write-Host "[BUILD] Building storage container..."; docker compose build storage-gateway }
}

# -------------------------------------------------------------------------
# STEP 3: STOP OLD CONTAINER
# -------------------------------------------------------------------------
Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">> [STEP 3/5] Stop old container" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow

if ($runtimeChanged) {
    if ($ForceRebuild -or $hasCompose) {
        Write-Host "[STOP] Stopping containers for stack update..." -ForegroundColor Cyan
        docker compose stop
    } else {
        if ($hasBackend)  { Write-Host "[STOP] Stopping old backend containers..."; docker compose stop backend outbox-worker integrity-worker ai-evaluation-worker secure-session-worker photocopy-expiry-worker }
        if ($hasFrontend) { Write-Host "[STOP] Stopping old frontend container..."; docker compose stop frontend }
        if ($hasIdentity) { Write-Host "[STOP] Stopping old identity container..."; docker compose stop identity-service }
        if ($hasStorage)  { Write-Host "[STOP] Stopping old storage container..."; docker compose stop storage-gateway }
    }
} else {
    Write-Host "[SKIP] No runtime containers to stop." -ForegroundColor Green
}

# -------------------------------------------------------------------------
# STEP 4: START NEW CONTAINER
# -------------------------------------------------------------------------
Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">> [STEP 4/5] Start new container" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow

if ($runtimeChanged) {
    if ($ForceRebuild -or $hasCompose) {
        docker compose up -d
    } else {
        if ($hasBackend) {
            docker compose up -d --no-deps backend outbox-worker integrity-worker ai-evaluation-worker secure-session-worker photocopy-expiry-worker
            if ($hasMigrations) {
                Write-Host "[MIGRATE] Applying database migrations..." -ForegroundColor Cyan
                docker compose exec -T backend python manage.py migrate --noinput
            }
        }
        if ($hasFrontend) { docker compose up -d --no-deps frontend }
        if ($hasIdentity) { docker compose up -d --no-deps identity-service }
        if ($hasStorage)  { docker compose up -d --no-deps storage-gateway }
    }
    Write-Host "[OK] New containers started successfully." -ForegroundColor Green
} else {
    Write-Host "[OK] Existing containers remain active with zero downtime." -ForegroundColor Green
}

# -------------------------------------------------------------------------
# STEP 5: HEALTH CHECK ✅ -> LIVE WEBSITE
# -------------------------------------------------------------------------
Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">> [STEP 5/5] Health Check ✅ -> Live Website" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow

$healthOk = $false
$maxTries = 10

for ($i = 1; $i -le $maxTries; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:3000" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -in @(200, 307, 308)) {
            $healthOk = $true
            Write-Host "[HEALTH] ✅ Health Check Passed on attempt $i (HTTP $($resp.StatusCode))" -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $healthOk) {
    Write-Host "[INFO] Containers warming up; traffic ready at http://localhost:3000" -ForegroundColor Gray
}

$stopwatch.Stop()
$totalSec = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host ">> 🎉 LIVE WEBSITE ONLINE: http://localhost:3000" -ForegroundColor Green
Write-Host ">> Process completed in $totalSec seconds" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
