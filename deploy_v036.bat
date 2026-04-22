@echo off
chcp 65001 > nul
REM ══════════════════════════════════════════════════════════
REM  MagicQuant v0.3.6 patch 部署脚本
REM  一键把 /ai_test 主动召集智囊团指令加到你的 v0.3.5 上
REM ══════════════════════════════════════════════════════════

echo.
echo ═══════════════════════════════════════════════════
echo   MagicQuant v0.3.6 Patch — 部署中
echo   功能: 新增 /ai_test 主动召集 AI 智囊团
echo ═══════════════════════════════════════════════════
echo.

REM 切换到 patch 包根目录
cd /d "%~dp0"

REM 检查是否在正确位置
if not exist "apply_patch.py" (
    echo ❌ 找不到 apply_patch.py,请确认解压到 C:\MagicQuant\ 根目录
    pause
    exit /b 1
)

if not exist "bot\bot_controller.py" (
    echo ❌ 找不到 bot\bot_controller.py
    echo    请先把 patch 包解压到 C:\MagicQuant\ 下(覆盖合并)
    pause
    exit /b 1
)

REM 检查新模块文件是否已复制到位
if not exist "core\focus\manual_consult.py" (
    echo ❌ 找不到 core\focus\manual_consult.py
    echo    请确认解压时保留了目录结构
    pause
    exit /b 1
)

echo [1/2] 复制新模块文件...
echo       core\focus\manual_consult.py  ✅
echo       core\focus\__init__.py        ✅
echo.

echo [2/2] 给 bot_controller.py 打补丁...
python apply_patch.py
if %errorlevel% neq 0 (
    echo.
    echo ❌ patch 失败,请查看上方错误
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════
echo   ✅ v0.3.6 patch 部署成功!
echo ═══════════════════════════════════════════════════
echo.
echo  新指令:
echo    /ai_test              主动召集智囊团
echo    /ai_test RKLB异动      带原因召集
echo.
echo  前提:
echo    1. Focus 盯盘在运行 (/focus)
echo    2. .env 里至少配了 Claude + 1 个顾问的 Key
echo.
echo  如需回滚: 双击 rollback_v036.bat
echo.
pause
