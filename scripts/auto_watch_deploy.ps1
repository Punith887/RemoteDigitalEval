# ADMIEZO Background Auto-Deploy Watcher
# Continuously checks GitHub origin/main and applies updates immediately in seconds.

param(
    [string]$Branch = "main",
    [int]$IntervalSeconds = 5,
    [string]$DeployPath = ""
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> ADMIEZO REAL-TIME AUTO-DEPLOY WATCHER" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Branch   : $Branch" -ForegroundColor Gray
Write-Host "Interval : Every $IntervalSeconds seconds" -ForegroundColor Gray

# 1. Resolve path
$candidatePaths = @(
    $DeployPath,
    "c:\Users\ASUS\RemoteDigitalEval",
    "c:\Users\ASUS\remote-digital",
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
Write-Host "Watching repository at: $targetDir" -ForegroundColor Green
Write-Host "Press Ctrl+C to terminate.`n" -ForegroundColor DarkGray

$lastKnownSha = (git rev-parse HEAD 2>$null)
Write-Host "[INIT] Initial commit hash: $lastKnownSha" -ForegroundColor Yellow

while ($true) {
    Start-Sleep -Seconds $IntervalSeconds
    try {
        # Check remote HEAD without heavy fetching
        $remoteRef = (git ls-remote origin "refs/heads/$Branch" 2>$null)
        if ($remoteRef) {
            $remoteSha = ($remoteRef -split '\s+')[0]
            if ($remoteSha -and ($remoteSha -ne $lastKnownSha)) {
                $now = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                Write-Host "`n[$now] NEW COMMIT DETECTED ON $Branch!" -ForegroundColor Cyan
                Write-Host "Previous : $lastKnownSha" -ForegroundColor DarkGray
                Write-Host "New SHA  : $remoteSha" -ForegroundColor Yellow
                
                # Execute instant delta deployment
                $deployScript = Join-Path $targetDir "scripts\deploy_live.ps1"
                if (Test-Path $deployScript) {
                    & $deployScript -TargetCommit $remoteSha -BaseCommit $lastKnownSha -DeployPath $targetDir
                } else {
                    git pull origin $Branch --quiet
                }
                
                $lastKnownSha = $remoteSha
            }
        }
    } catch {
        Write-Warning "Watcher check exception: $_"
    }
}
