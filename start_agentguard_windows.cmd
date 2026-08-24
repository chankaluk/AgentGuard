@echo off
setlocal
cd /d "%~dp0"

echo [AgentGuard] Preparing Python environment...
if not exist ".venv\Scripts\python.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_env.ps1"
  if errorlevel 1 (
    echo [AgentGuard] Environment setup failed.
    pause
    exit /b 1
  )
)

echo [AgentGuard] Starting local dashboard...
echo Open http://127.0.0.1:8080 in your browser after the server starts.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_demo.ps1"
pause
