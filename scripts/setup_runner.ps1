# ADMIEZO GitHub Actions Self-Hosted Runner Setup Script
# Automates runner installation to enable instant, sub-second deployment triggers on push to main.

param(
    [string]$RunnerToken = "",
    [string]$RepoUrl = "https://github.com/Punith887/RemoteDigitalEval",
    [string]$RunnerDir = "C:\actions-runner"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> ADMIEZO GITHUB ACTIONS RUNNER AUTOMATION" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Repository : $RepoUrl" -ForegroundColor Gray
Write-Host "Directory  : $RunnerDir" -ForegroundColor Gray

# 1. Create Runner Directory
if (-not (Test-Path $RunnerDir)) {
    Write-Host "`n[1/4] Creating runner folder at $RunnerDir..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $RunnerDir -Force | Out-Null
}

Set-Location -Path $RunnerDir

# 2. Download and unpack runner if not already installed
if (-not (Test-Path "$RunnerDir\config.cmd")) {
    Write-Host "`n[2/4] Downloading GitHub Actions runner v2.322.0 (High-Speed)..." -ForegroundColor Yellow
    $runnerZip = "$RunnerDir\actions-runner-win-x64.zip"
    $downloadUrl = "https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-win-x64-2.322.0.zip"
    
    # Use native curl for maximum wire speed
    curl.exe -L -o $runnerZip $downloadUrl --silent --show-error
    
    Write-Host "[EXTRACT] Unpacking runner package..." -ForegroundColor Yellow
    tar.exe -xf $runnerZip -C $RunnerDir
    Remove-Item -Path $runnerZip -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "`n[2/4] Runner binaries are already present." -ForegroundColor Green
}

# 3. Register runner with GitHub
if (-not (Test-Path "$RunnerDir\.runner")) {
    if (-not $RunnerToken) {
        Write-Host "`n[3/4] Registration Token Required:" -ForegroundColor Yellow
        Write-Host "  1. Open your browser to: $RepoUrl/settings/actions/runners/new" -ForegroundColor Cyan
        Write-Host "  2. Copy the token generated under 'Configure'" -ForegroundColor Cyan
        Write-Host "  3. Run this command in PowerShell or CMD:" -ForegroundColor White
        Write-Host "     .\scripts\setup_runner.cmd -RunnerToken YOUR_TOKEN_HERE" -ForegroundColor Green
        exit 0
    }

    Write-Host "`n[3/4] Registering runner with repository..." -ForegroundColor Yellow
    $hostname = $env:COMPUTERNAME
    & .\config.cmd --url $RepoUrl --token $RunnerToken --name "$hostname-live-eval" --labels "self-hosted,Windows,X64,live-server" --unattended --replace
    Write-Host "[OK] Runner successfully registered with GitHub!" -ForegroundColor Green
} else {
    Write-Host "`n[3/4] Runner is already registered with repository." -ForegroundColor Green
}

# 4. Service installation and execution options
Write-Host "`n[4/4] Starting the Runner:" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "OPTION A: Run permanently in background as a Windows Service (Recommended):" -ForegroundColor White
Write-Host "  cd $RunnerDir" -ForegroundColor Gray
Write-Host "  .\svc.cmd install" -ForegroundColor Gray
Write-Host "  .\svc.cmd start" -ForegroundColor Gray
Write-Host "`nOPTION B: Run directly in an active console window:" -ForegroundColor White
Write-Host "  cd $RunnerDir; .\run.cmd" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan
