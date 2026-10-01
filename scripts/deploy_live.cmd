@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_live.ps1" %*
