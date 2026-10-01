# =========================================================================
# ADMIEZO Webhook Tunnel & Proxy Helper
# Exposes http://localhost:9090 to GitHub over the internet
# =========================================================================
param(
    [string]$Mode = "smee",   # "smee", "cloudflared", or "ngrok"
    [string]$SmeeUrl = "",
    [int]$LocalPort = 9090
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">> ADMIEZO GITHUB WEBHOOK PUBLIC TUNNEL HELPER" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$webhookPath = "http://localhost:$LocalPort/webhook"

if ($Mode -eq "smee") {
    Write-Host "`n[SMEE.IO] GitHub's Official Webhook Proxy (Recommended)" -ForegroundColor Yellow
    Write-Host "  Zero account required, works behind any Wi-Fi/NAT/firewall." -ForegroundColor Gray
    
    if (-not $SmeeUrl) {
        Write-Host "`n1. Open your browser to: https://smee.io/new" -ForegroundColor Cyan
        Write-Host "2. Copy your unique Webhook Proxy URL (e.g., https://smee.io/abc123xyz)" -ForegroundColor Cyan
        Write-Host "3. In GitHub Repository -> Settings -> Webhooks -> Add webhook:" -ForegroundColor Green
        Write-Host "     Payload URL  : (Your Smee URL)" -ForegroundColor White
        Write-Host "     Content type : application/json" -ForegroundColor White
        Write-Host "     Events       : Just the push event" -ForegroundColor White
        Write-Host "`n4. Run this command to start forwarding to your local Python server:" -ForegroundColor Yellow
        Write-Host "   .\scripts\setup_tunnel.ps1 -Mode smee -SmeeUrl YOUR_SMEE_URL" -ForegroundColor Green
        Write-Host "`nTip: Launching https://smee.io/new in browser now..." -ForegroundColor Gray
        Start-Process "https://smee.io/new"
        exit 0
    }

    Write-Host "`nStarting Smee client forwarder..." -ForegroundColor Green
    Write-Host "Forwarding: $SmeeUrl -> $webhookPath`n" -ForegroundColor Cyan
    npx -y smee-client --url $SmeeUrl --target $webhookPath
}
elseif ($Mode -eq "cloudflared") {
    Write-Host "`n[CLOUDFLARE TUNNEL] Quick HTTPS Tunnel" -ForegroundColor Yellow
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        Write-Host "cloudflared not found in PATH." -ForegroundColor Yellow
        Write-Host "Download from: https://github.com/cloudflare/cloudflared/releases/latest" -ForegroundColor Cyan
        exit 1
    }
    cloudflared tunnel --url "http://localhost:$LocalPort"
}
elseif ($Mode -eq "ngrok") {
    Write-Host "`n[NGROK] HTTP Tunnel" -ForegroundColor Yellow
    $ng = Get-Command ngrok -ErrorAction SilentlyContinue
    if (-not $ng) {
        Write-Host "ngrok not found in PATH. Install ngrok or use Smee.io mode." -ForegroundColor Yellow
        exit 1
    }
    ngrok http $LocalPort
}
