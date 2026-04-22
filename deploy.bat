@echo off
chcp 65001 >nul
REM ═══════════════════════════════════════════════════
REM  MagicQuant v0.3.5 一键部署脚本
REM  作用: 自动备份 → 覆盖文件 → 启动 bot
REM  使用: 解压 zip 到任意目录,双击这个 bat 即可
REM ═══════════════════════════════════════════════════

setlocal
set "MQ_ROOT=C:\MagicQuant"
set "BACKUP_NAME=MagicQuant_backup_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "BACKUP_NAME=%BACKUP_NAME: =0%"
set "BACKUP_DIR=C:\%BACKUP_NAME%"

REM 获取 bat 所在目录(解压后的源)
set "SCRIPT_DIR=%~dp0"
set "SRC_DIR=%SCRIPT_DIR%"

echo.
echo ═════════════════════════════════════════════
echo   MagicQuant v0.3.5 一键部署
echo ═════════════════════════════════════════════
echo.
echo   源目录: %SRC_DIR%
echo   目标:   %MQ_ROOT%
echo   备份:   %BACKUP_DIR%
echo.

REM ─── 确认 ───
set /p CONFIRM="按 Y 开始部署,其他键退出: "
if /i not "%CONFIRM%"=="Y" (
    echo 已取消
    pause
    exit /b 0
)

REM ─── Step 1: 检查目标目录 ───
if not exist "%MQ_ROOT%" (
    echo [X] 未找到 %MQ_ROOT%, 请先手动创建
    pause
    exit /b 1
)

REM ─── Step 2: 停止旧进程 ───
echo.
echo [1/6] 停止 bot / dashboard ...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

REM ─── Step 3: 备份 ───
echo.
echo [2/6] 备份当前项目 → %BACKUP_DIR% ...
xcopy "%MQ_ROOT%" "%BACKUP_DIR%" /E /I /Y /Q >nul
if %errorlevel% neq 0 (
    echo [X] 备份失败!为安全起见,部署中止
    pause
    exit /b 1
)
echo     ^✓ 备份完成

REM ─── Step 4: 覆盖文件 ───
echo.
echo [3/6] 复制新文件 ...

REM bot/bot_controller.py
copy /Y "%SRC_DIR%bot\bot_controller.py" "%MQ_ROOT%\bot\bot_controller.py" >nul
echo     ^✓ bot\bot_controller.py

REM 根目录文件
copy /Y "%SRC_DIR%version.py"            "%MQ_ROOT%\version.py" >nul
copy /Y "%SRC_DIR%CHANGELOG.md"          "%MQ_ROOT%\CHANGELOG.md" >nul
copy /Y "%SRC_DIR%test_ai_providers.py"  "%MQ_ROOT%\test_ai_providers.py" >nul
echo     ^✓ version.py / CHANGELOG.md / test_ai_providers.py

REM core/agents (5 个全新文件)
if not exist "%MQ_ROOT%\core\agents" mkdir "%MQ_ROOT%\core\agents"
copy /Y "%SRC_DIR%core\agents\*.py" "%MQ_ROOT%\core\agents\" >nul
echo     ^✓ core\agents\ (5 files)

REM core/focus (1 新文件 + 2 覆盖)
copy /Y "%SRC_DIR%core\focus\ai_advisor.py"    "%MQ_ROOT%\core\focus\ai_advisor.py" >nul
copy /Y "%SRC_DIR%core\focus\focus_manager.py" "%MQ_ROOT%\core\focus\focus_manager.py" >nul
copy /Y "%SRC_DIR%core\focus\__init__.py"      "%MQ_ROOT%\core\focus\__init__.py" >nul
echo     ^✓ core\focus\ (3 files)

REM dashboard
copy /Y "%SRC_DIR%dashboard\focus.html" "%MQ_ROOT%\dashboard\focus.html" >nul
copy /Y "%SRC_DIR%dashboard\server.py"  "%MQ_ROOT%\dashboard\server.py" >nul
echo     ^✓ dashboard\ (2 files)

REM 创建 data 目录(如果没有)
if not exist "%MQ_ROOT%\data" mkdir "%MQ_ROOT%\data"

REM ─── Step 5: 显示版本 ───
echo.
echo [4/6] 验证版本 ...
cd /d "%MQ_ROOT%"
python version.py 2>nul | findstr "v0.3"

REM ─── Step 6: 启动 ───
echo.
echo [5/6] 启动 Dashboard (新窗口) ...
start "MagicQuant Dashboard" cmd /k "cd /d %MQ_ROOT% && python dashboard\server.py"
timeout /t 3 /nobreak >nul

echo.
echo [6/6] 启动 Bot (新窗口) ...
start "MagicQuant Bot" cmd /k "cd /d %MQ_ROOT% && python bot\bot_controller.py"

echo.
echo ═════════════════════════════════════════════
echo   ^✓ v0.3.5 部署完成!
echo ═════════════════════════════════════════════
echo.
echo   浏览器:        http://localhost:5000/focus
echo   Telegram 测试: /focus  /ai_advise_status  /race_providers
echo.
echo   如需回滚: 
echo   1. taskkill /F /IM python.exe
echo   2. rmdir /s /q %MQ_ROOT%
echo   3. xcopy %BACKUP_DIR% %MQ_ROOT% /E /I /Y
echo.
timeout /t 15
