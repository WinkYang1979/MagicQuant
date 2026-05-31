@echo off
REM MagicQuant run_tradingagents_full_cli.bat
REM VERSION : v0.1.0
REM DEPENDS : TradingAgents, py launcher
REM Launch the native TradingAgents interactive CLI.
REM This is independent from MagicQuant daily briefing.

chcp 65001 >nul
setlocal

set "BASE_DIR=%~dp0"
set "TA_DIR=%BASE_DIR%TradingAgents"

if not exist "%TA_DIR%\cli\main.py" (
  echo [ERROR] TradingAgents CLI not found:
  echo         "%TA_DIR%\cli\main.py"
  echo.
  pause
  exit /b 1
)

cd /d "%TA_DIR%"

title TradingAgents Full CLI
echo ============================================================
echo   TradingAgents Full CLI
echo   Native interactive mode: ticker / date / model / depth
echo   Checkpoint resume: ON
echo ============================================================
echo.

py -3.13 -V >nul 2>&1
if not errorlevel 1 (
  py -3.13 -m cli.main --checkpoint
) else (
  "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe" -m cli.main --checkpoint
)

echo.
echo ============================================================
echo   TradingAgents exited. Press any key to close.
echo ============================================================
pause >nul
