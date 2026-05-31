@echo off
REM MagicQuant run_tradingagents_rklb.bat
REM VERSION : v0.1.0
REM DEPENDS : run_ta_daily.py, TradingAgents
REM Run RKLB TradingAgents analysis in a visible console.
REM 启动 RKLB TradingAgents 分析，运行结束后保留窗口方便查看日志。

chcp 65001 >nul
cd /d C:\MagicQuant

echo ============================================================
echo   MagicQuant TradingAgents RKLB
echo   %date% %time%
echo ============================================================
echo.

"C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe" run_ta_daily.py

echo.
echo ============================================================
echo   TradingAgents finished. Press any key to close.
echo ============================================================
pause >nul
