@echo off
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Please open Docker Desktop first, then run this again.
  pause
  exit /b 1
)
echo Starting. The report is rebuilt from data.db of the project root (about 1 minute),
echo and rebuilt again automatically whenever data.db changes.
docker compose up -d --build
if errorlevel 1 (
  pause
  exit /b 1
)
timeout /t 75 >nul
start "" http://localhost:8003
