@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_tunnel.ps1" %*
