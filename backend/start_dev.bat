@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   FeinaLive Backend 开发模式
echo   (带热重载)
echo ========================================
echo.

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] uv 未安装，正在安装...
    pip install uv -q
)

echo [INFO] 检查依赖...
uv sync --quiet

echo [INFO] 启动开发服务器...
echo.
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
