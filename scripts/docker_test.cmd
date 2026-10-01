@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker_test.ps1" %*
