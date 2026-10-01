# ADMIEZO High-Speed Docker Build & Test Script
# Runs containerized builds and test suites with BuildKit caching.

param(
    [string]$Service = "all", # backend, frontend, identity, storage, all
    [switch]$NoCache = $false
)

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> ADMIEZO FAST DOCKER BUILD & TEST SUITE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Service : $Service" -ForegroundColor Gray

# 1. Enable BuildKit for maximum caching speed
$env:DOCKER_BUILDKIT = "1"
$env:COMPOSE_DOCKER_CLI_BUILD = "1"

# 2. Check Docker Engine
$dockerOk = $false
try {
    $null = docker info 2>$null
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
} catch {}

if (-not $dockerOk) {
    Write-Warning "Docker daemon is not currently running. Please start Docker Desktop to run container tests locally."
    exit 1
}

$cacheFlag = if ($NoCache) { "--no-cache" } else { "" }

# 3. Backend Docker Build & Test
if ($Service -in @("all", "backend")) {
    Write-Host "`n[BACKEND] Building Docker image..." -ForegroundColor Yellow
    docker build -f backend/Dockerfile --target runtime -t admiezo-backend:test .
    if ($LASTEXITCODE -ne 0) { Write-Error "Backend Docker build failed."; exit 1 }

    Write-Host "[BACKEND] Running tests inside container..." -ForegroundColor Cyan
    docker run --rm `
        -e DJANGO_SECRET_KEY=local-test-key-32-chars-minimum `
        -e DJANGO_DEBUG=true `
        --entrypoint "" `
        admiezo-backend:test `
        python manage.py test --settings=evaluation_core.test_settings --noinput
    if ($LASTEXITCODE -ne 0) { Write-Error "Backend container tests failed."; exit 1 }
    Write-Host "[OK] Backend Docker tests passed!" -ForegroundColor Green
}

# 4. Identity Service Docker Build & Test
if ($Service -in @("all", "identity")) {
    Write-Host "`n[IDENTITY] Building Docker image..." -ForegroundColor Yellow
    docker build -f identity_service/Dockerfile -t admiezo-identity:test .
    if ($LASTEXITCODE -ne 0) { Write-Error "Identity service Docker build failed."; exit 1 }

    Write-Host "[IDENTITY] Running tests inside container..." -ForegroundColor Cyan
    docker run --rm `
        --entrypoint "" `
        admiezo-identity:test `
        python manage.py test --noinput
    if ($LASTEXITCODE -ne 0) { Write-Error "Identity service container tests failed."; exit 1 }
    Write-Host "[OK] Identity service Docker tests passed!" -ForegroundColor Green
}

# 5. Storage Gateway Docker Build
if ($Service -in @("all", "storage")) {
    Write-Host "`n[STORAGE] Building Docker image..." -ForegroundColor Yellow
    docker build -f storage_gateway/Dockerfile -t admiezo-storage:test .
    if ($LASTEXITCODE -ne 0) { Write-Error "Storage gateway Docker build failed."; exit 1 }
    Write-Host "[OK] Storage gateway Docker build passed!" -ForegroundColor Green
}

# 6. Frontend Docker Build
if ($Service -in @("all", "frontend")) {
    Write-Host "`n[FRONTEND] Building Next.js Docker image (multi-stage)..." -ForegroundColor Yellow
    docker build -f frontend/Dockerfile -t admiezo-frontend:test .
    if ($LASTEXITCODE -ne 0) { Write-Error "Frontend Docker build failed."; exit 1 }
    Write-Host "[OK] Frontend Next.js Docker build passed!" -ForegroundColor Green
}

$stopwatch.Stop()
$totalSec = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host ">> ALL DOCKER BUILDS & TESTS PASSED IN $totalSec SECONDS!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
