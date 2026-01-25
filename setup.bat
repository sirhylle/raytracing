@echo off
REM Bootstrap script for Windows
REM Checks for 'uv' and launches setup_project.py

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 'uv' is not installed or not in your PATH.
    echo.
    echo Please install uv first.
    echo Open PowerShell and run:
    echo powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    echo Then restart your terminal and run this script again.
    pause
    exit /b 1
)

echo [BOOTSTRAP] Found uv. Launching setup...
uv run setup_project.py
if %errorlevel% neq 0 (
    echo [ERROR] Setup failed.
    pause
    exit /b 1
)

echo.
echo [BOOTSTRAP] Done. You can now run:
echo uv run main.py --editor
pause
