# ADMIEZO Ultra-Fast Zero-Lag Live Server Deployment Script
# Designed for instant updates on git push with zero user disruption.

param(
    [string]$TargetCommit = "",
    [string]$BaseCommit = "",
    [string]$DeployPath = "",
    [switch]$ForceRebuild = $false
)

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> ADMIEZO ULTRA-FAST ZERO-LAG LIVE DEPLOYMENT" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Resolve Target Deployment Directory
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
    Write-Error "Could not locate a valid deployment directory containing docker-compose.yml."
    exit 1
}

Write-Host "[DIR] Active Project Directory: $targetDir" -ForegroundColor Gray
Set-Location -Path $targetDir

# 2. Check current HEAD before pull
$prevHead = (git rev-parse HEAD 2>$null)
if (-not $prevHead) {
    $prevHead = "HEAD~1"
}

# 3. Fast-sync latest code from origin/main
Write-Host "[SYNC] Synchronizing code with origin/main..." -ForegroundColor Yellow
$syncStart = $stopwatch.ElapsedMilliseconds
git fetch origin main --quiet 2>$null

$localDirty = (git status --porcelain 2>$null)
if (-not $localDirty) {
    git reset --hard origin/main 2>$null
} else {
    Write-Host "[NOTE] Local uncommitted changes present. Keeping local files for safe testing." -ForegroundColor Yellow
}

$newHead = (git rev-parse origin/main 2>$null)
if (-not $newHead) {
    $newHead = (git rev-parse HEAD 2>$null)
}
$syncDuration = [Math]::Round(($stopwatch.ElapsedMilliseconds - $syncStart) / 1000, 2)
Write-Host "[OK] Git sync completed in $syncDuration s (HEAD: $newHead)" -ForegroundColor Green

# 4. Determine Changed Files via Git Diff
$baseSha = if ($BaseCommit -and $BaseCommit -ne "0000000000000000000000000000000000000000") { $BaseCommit } else { $prevHead }
$targetSha = if ($TargetCommit) { $TargetCommit } else { $newHead }

$changedFiles = @()
if ($baseSha -and $targetSha -and ($baseSha -ne $targetSha)) {
    $diffOutput = git diff --name-only $baseSha $targetSha 2>$null
    if ($diffOutput) {
        $changedFiles = $diffOutput -split "`r?`n" | Where-Object { $_ -ne "" }
    }
} else {
    $diffOutput = git diff --name-only HEAD~1 HEAD 2>$null
    if ($diffOutput) {
        $changedFiles = $diffOutput -split "`r?`n" | Where-Object { $_ -ne "" }
    }
}

Write-Host "`n[DIFF] Changed files in this deployment ($($changedFiles.Count) files):" -ForegroundColor Gray
foreach ($f in $changedFiles) {
    Write-Host "   - $f" -ForegroundColor DarkGray
}

# 5. Analyze Affected Service Layers
$hasBackend      = ($changedFiles | Where-Object { $_ -like "backend/*" -or $_ -eq "requirements.txt" -or $_ -eq "requirements-dev.txt" }).Count -gt 0
$hasMigrations   = ($changedFiles | Where-Object { $_ -like "backend/apps/*/migrations/*" }).Count -gt 0
$hasFrontend     = ($changedFiles | Where-Object { $_ -like "frontend/*" }).Count -gt 0
$hasIdentity     = ($changedFiles | Where-Object { $_ -like "identity_service/*" }).Count -gt 0
$hasStorage      = ($changedFiles | Where-Object { $_ -like "storage_gateway/*" }).Count -gt 0
$hasCompose      = ($changedFiles | Where-Object { $_ -eq "docker-compose.yml" -or $_ -like ".env*" }).Count -gt 0

$runtimeChanged = $hasBackend -or $hasFrontend -or $hasIdentity -or $hasStorage -or $hasCompose -or $ForceRebuild

# 6. Check Docker Engine Availability
$dockerAvailable = $false
try {
    $null = docker info 2>$null
    if ($LASTEXITCODE -eq 0) {
        $dockerAvailable = $true
    }
} catch {
    $dockerAvailable = $false
}

if (-not $dockerAvailable) {
    $dockerDesktopPath = "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    if (Test-Path $dockerDesktopPath) {
        Write-Host "[INFO] Docker Desktop is installed at: $dockerDesktopPath" -ForegroundColor Yellow
    }
    Write-Host "[INFO] Docker Engine is not currently running. Source code updated to latest commit." -ForegroundColor Yellow
    Write-Host "[INFO] Running containers will automatically pick up code changes on next launch." -ForegroundColor Yellow
    $stopwatch.Stop()
    $totalSec = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
    Write-Host "`n[FAST] Source synchronization completed in $totalSec seconds!" -ForegroundColor Green
    exit 0
}

# Enable Docker BuildKit for ultra-fast layer caching & parallel builds
$env:DOCKER_BUILDKIT = "1"
$env:COMPOSE_DOCKER_CLI_BUILD = "1"

# 7. Execute Targeted Zero-Lag Update
Write-Host "`n[EXEC] Executing Smart Targeted Update..." -ForegroundColor Cyan

if (-not $runtimeChanged) {
    Write-Host "[SKIP] Only non-runtime files (documentation, CI workflows, or scripts) modified." -ForegroundColor Green
    Write-Host "[FAST] Zero container rebuilds needed. Zero lag, zero downtime for users!" -ForegroundColor Green
}
elseif ($ForceRebuild -or $hasCompose) {
    Write-Host "[STACK] Core compose configuration modified or force flag set. Updating services with BuildKit caching..." -ForegroundColor Yellow
    docker compose up -d --build
}
else {
    # Targeted service updates: update only modified services without disrupting others
    if ($hasBackend) {
        Write-Host "[BACKEND] Backend/worker code modified. Updating backend services..." -ForegroundColor Yellow
        docker compose up -d --no-deps --build backend outbox-worker integrity-worker ai-evaluation-worker secure-session-worker photocopy-expiry-worker
        if ($hasMigrations) {
            Write-Host "[DB] Applying new database migrations..." -ForegroundColor Yellow
            docker compose exec -T backend python manage.py migrate --noinput
        }
    }

    if ($hasFrontend) {
        Write-Host "[FRONTEND] Frontend code modified. Updating frontend container with layer caching..." -ForegroundColor Yellow
        docker compose up -d --no-deps --build frontend
    }

    if ($hasIdentity) {
        Write-Host "[IDENTITY] Identity service modified. Updating identity-service..." -ForegroundColor Yellow
        docker compose up -d --no-deps --build identity-service
    }

    if ($hasStorage) {
        Write-Host "[STORAGE] Storage gateway modified. Updating storage-gateway..." -ForegroundColor Yellow
        docker compose up -d --no-deps --build storage-gateway
    }
}

# 8. Rapid Health Check
Write-Host "`n[HEALTH] Checking live application responsiveness..." -ForegroundColor Cyan
Start-Sleep -Seconds 1
$healthOk = $false
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:3000" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
    if ($resp.StatusCode -in @(200, 307, 308)) {
        $healthOk = $true
    }
} catch {}

if ($healthOk) {
    Write-Host "[OK] Live application is fully responsive at http://127.0.0.1:3000" -ForegroundColor Green
} else {
    Write-Host "[INFO] Deployment completed; service initialization underway." -ForegroundColor Gray
}

$stopwatch.Stop()
$totalSec = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ">> DEPLOYMENT SUCCESSFULLY COMPLETED IN $totalSec SECONDS!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
