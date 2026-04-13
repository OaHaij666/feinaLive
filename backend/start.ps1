$Host.UI.RawUI.WindowTitle = "FeinaLive Backend"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FeinaLive Backend Starter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[INFO] Installing uv..." -ForegroundColor Yellow
    pip install uv -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install uv. Please run: pip install uv" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "[INFO] Syncing dependencies..." -ForegroundColor Green
uv sync --extra easyvtuber --quiet

Write-Host "[INFO] Starting backend server..." -ForegroundColor Green
Write-Host ""
uv run python main.py

Read-Host "Press Enter to exit"
