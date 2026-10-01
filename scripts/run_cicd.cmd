@echo off
title ADMIEZO Pure Python CI/CD Pipeline Server
cd /d "%~dp0.."
echo =========================================================================
echo ^>^> Starting ADMIEZO Pure Python CI/CD Pipeline Engine
echo ^>^> Zero GitHub Actions - 100%% Python Native
echo =========================================================================
python "%~dp0cicd_pipeline.py" %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Pipeline exited with code %ERRORLEVEL%
    pause
)
