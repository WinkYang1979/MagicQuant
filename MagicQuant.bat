@echo off
chcp 65001 >nul
title MagicQuant
cd /d C:\MagicQuant

echo.
echo  ==========================================
echo   MagicQuant - Dare to dream. Data to win.
echo   Version 0.1.0
echo  ==========================================
echo.

echo  [1/3] Collecting account data...
python core\data_collector.py
echo.

rem echo  [2/3] Starting dashboard...
rem start "MagicQuant-Dashboard" cmd /k "cd /d C:\MagicQuant && python dashboard\server.py"
rem timeout /t 3 /nobreak >nul

echo  [2/3] Starting Telegram Bot...
start "MagicQuant-Bot" cmd /k "cd /d C:\MagicQuant && python bot\bot_controller.py"
timeout /t 2 /nobreak >nul

rem Legacy SimWeekly is replaced by Duel PK for default paper simulation.
rem To run it manually: python scripts\sim_weekly_run.py

echo  [3/3] Starting fair duel runner (Claude vs OpenAI, paper 24h PK)...
start "MagicQuant-Duel" cmd /k "cd /d C:\MagicQuant && set PYTHONIOENCODING=utf-8 && python scripts\sim_weekly_duel_run.py --poll 30 --trade-hours all"
timeout /t 2 /nobreak >nul

echo.
echo  ==========================================
echo   All services started!
echo   Dashboard  : http://localhost:5000
echo   Telegram   : @laoyangquant_bot
echo   Duel PK    : Claude vs OpenAI, paper $10k, 24h weekday mode
echo   SimWeekly  : retired from auto-start; run manually only if needed
echo   Close the other windows to stop.
echo  ==========================================
echo.
pause
