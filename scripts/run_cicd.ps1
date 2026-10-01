<#
.SYNOPSIS
    ADMIEZO Pure Python CI/CD Pipeline Launcher
.DESCRIPTION
    Runs the native Python CI/CD pipeline engine without GitHub Actions.
    Supports --ci, --cd, --full, --watch, and server dashboard modes.
.PARAMETER Port
    HTTP port for Webhook receiver and Web Dashboard (default: 9090)
.PARAMETER Branch
    Target Git branch to deploy (default: main)
.PARAMETER Stage
    Stage to execute: 'server', 'ci', 'cd', 'full', 'watch'
.PARAMETER Secret
    Optional GitHub HMAC Webhook secret
#>
param(
    [int]$Port = 9090,
    [string]$Branch = "main",
    [ValidateSet("server", "ci", "cd", "full", "watch")]
    [string]$Stage = "server",
    [string]$Secret = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
Set-Location -Path $projectDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ">> 🐍 ADMIEZO PURE PYTHON CI/CD PIPELINE ENGINE" -ForegroundColor Green
Write-Host ">> Zero GitHub Actions - 100% Python Native Execution" -ForegroundColor DarkCyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Project Directory : $projectDir"
Write-Host "Target Branch     : $Branch"
Write-Host "Pipeline Stage    : $Stage"
Write-Host "Dashboard Port    : $Port"

$pipelineScript = Join-Path $scriptDir "cicd_pipeline.py"
$cmdArgs = @()

if ($Stage -eq "ci") {
    $cmdArgs += "--ci"
} elseif ($Stage -eq "cd") {
    $cmdArgs += "--cd"
} elseif ($Stage -eq "full") {
    $cmdArgs += "--full"
} elseif ($Stage -eq "watch") {
    $cmdArgs += "--watch"
} else {
    $cmdArgs += @("--port", $Port, "--branch", $Branch)
    if ($Secret) {
        $cmdArgs += @("--secret", $Secret)
    }
}

python $pipelineScript @cmdArgs
