@echo off
title ADMIEZO Central Laptop GitHub Webhook CD Server
cd /d "%~dp0.."
echo =========================================================================
echo ^>^> Starting ADMIEZO Central Laptop GitHub Webhook CD Server
echo =========================================================================
python "%~dp0github_webhook_deployer.py" %*
pause
