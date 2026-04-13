@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   FeinaLive Backend Starter
echo ========================================
echo.

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing uv...
    pip install uv -q
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install uv. Please run: pip install uv
        pause
        exit /b 1
    )
)

echo [INFO] Syncing dependencies...
uv sync --extra easyvtuber --quiet

echo [INFO] Starting backend server...
echo.
uv run python main.py

pause
