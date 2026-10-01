@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0auto_watch_deploy.ps1" %*
