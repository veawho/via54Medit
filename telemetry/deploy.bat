@echo off
chcp 65001 >nul
title medit-telemetry 一键部署向导

echo ================================================================
echo 🚀 via54Medit medit-telemetry Windows CMD 一键独立部署引擎
echo ================================================================

set "SCRIPT_DIR=%~dp0"
set "DEPLOY_PY=%SCRIPT_DIR%deploy.py"

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_EXE=python"
    goto :RUN
)

if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
    goto :RUN
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :RUN
)

echo [!] 未能检测到 Python 3，请确认 Python 已安装并加入 PATH。
pause
exit /b 1

:RUN
"%PY_EXE%" "%DEPLOY_PY%" %*
if %errorlevel% neq 0 (
    echo [!] 部署过程中遇到异常，返回码: %errorlevel%
    pause
    exit /b %errorlevel%
)

pause
