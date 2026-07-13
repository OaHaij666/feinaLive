@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [FeinaLive] uv not found. Install uv and try again.
  pause
  exit /b 1
)

echo [FeinaLive] Preparing desktop launcher...
uv sync --project "%~dp0launcher"
if errorlevel 1 (
  echo [FeinaLive] Launcher dependency installation failed.
  pause
  exit /b 1
)

start "" "%~dp0launcher\.venv\Scripts\pythonw.exe" -m launcher.main
exit /b 0
