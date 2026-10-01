# =========================================================================
# ADMIEZO Central Laptop GitHub Webhook Live Deployment Launcher
# =========================================================================
param(
    [int]$Port = 9090,
    [string]$Branch = "main",
    [string]$Secret = ""
)

$Host.UI.RawUI.WindowTitle = "ADMIEZO Central Laptop Webhook Live Deployment"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Set-Location -Path $projectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> ADMIEZO CENTRAL LAPTOP GITHUB WEBHOOK LIVE PIPELINE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Project Root : $projectRoot" -ForegroundColor Gray
Write-Host "Port         : $Port" -ForegroundColor Gray
Write-Host "Branch       : $Branch" -ForegroundColor Gray
Write-Host "Secret       : $(if ($Secret) { 'Configured' } else { 'None (Open Mode)' })" -ForegroundColor Gray
Write-Host "Dashboard    : http://localhost:$Port/" -ForegroundColor Yellow
Write-Host "Webhook URL  : http://localhost:$Port/webhook" -ForegroundColor Yellow
Write-Host "Live App     : http://localhost:3000" -ForegroundColor Green
Write-Host "==========================================================`n" -ForegroundColor Cyan

# Check Python availability
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python was not found in PATH. Please install Python 3.8+."
    exit 1
}

$deployerScript = Join-Path $scriptDir "github_webhook_deployer.py"

$argsList = @($deployerScript, "--port", "$Port", "--branch", "$Branch")
if ($Secret) {
    $argsList += @("--secret", "$Secret")
}

& python @argsList
