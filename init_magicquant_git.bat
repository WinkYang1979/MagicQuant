@echo off
REM ════════════════════════════════════════════════════════════════
REM  MagicQuant Git 初始化脚本
REM  用法: 放在 C:\MagicQuant\ 下双击,或命令行运行
REM  功能:
REM    1. 初始化 git 仓库
REM    2. 创建合理的 .gitignore(排除密钥、缓存、备份)
REM    3. 提交 v0.5.13 baseline
REM ════════════════════════════════════════════════════════════════

cd /d %~dp0

echo.
echo ========================================================
echo   MagicQuant Git 初始化
echo ========================================================
echo.

REM 检查 git 是否可用
where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git 命令不存在!
    echo.
    echo 请先下载安装 Git for Windows:
    echo https://git-scm.com/download/win
    echo.
    echo 安装后重新打开 cmd 窗口再运行本脚本。
    pause
    exit /b 1
)

REM 检查当前目录是不是 MagicQuant
if not exist "bot\bot_controller.py" (
    echo [ERROR] 当前目录不是 MagicQuant 根目录!
    echo 当前目录: %CD%
    echo 请把此脚本放到 C:\MagicQuant\ 下运行
    pause
    exit /b 1
)

REM 检查是不是已经初始化过
if exist ".git" (
    echo [WARN] .git 目录已存在,本仓库已经初始化过。
    echo.
    echo 当前状态:
    git status --short
    echo.
    echo 最近 5 个 commit:
    git log --oneline -5
    echo.
    pause
    exit /b 0
)

echo 步骤 1/4: git init
git init
if errorlevel 1 (
    echo [ERROR] git init 失败
    pause
    exit /b 1
)

echo.
echo 步骤 2/4: 配置 user
git config user.name "laoyang"
git config user.email "happy.yz@gmail.com"
echo   user.name  = laoyang
echo   user.email = happy.yz@gmail.com

echo.
echo 步骤 3/4: 创建 .gitignore
(
echo # ══════════════════════════════════════════════════════════
echo #  MagicQuant .gitignore
echo #  保护密钥 / 运行数据 / 备份目录不被 commit
echo # ══════════════════════════════════════════════════════════
echo.
echo # 环境变量和密钥
echo .env
echo _env
echo *.env
echo.
echo # Python 缓存
echo __pycache__/
echo *.pyc
echo *.pyo
echo *.pyd
echo .Python
echo.
echo # 运行时数据(每次运行都会变,不应纳入版本)
echo data/signals_latest.json
echo data/account_data.json
echo data/usage.json
echo data/*.cache
echo data/*.log
echo.
echo # 备份目录
echo backup_*/
echo.
echo # 日志
echo logs/
echo *.log
echo.
echo # IDE
echo .vscode/
echo .idea/
echo *.swp
echo.
echo # 系统
echo .DS_Store
echo Thumbs.db
) > .gitignore
echo   .gitignore 创建完成

echo.
echo 步骤 4/4: 首次 commit 作为 v0.5.13 baseline
git add .
git commit -m "v0.5.13 baseline - 2026-04-22 HKD cash bug fixed, ai_test fixed"
if errorlevel 1 (
    echo [ERROR] 首次 commit 失败
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   ✅ Git 仓库初始化完成!
echo ========================================================
echo.
git log --oneline
echo.
echo 以后的工作流:
echo.
echo   [改代码前快照]
echo     git add -A
echo     git commit -m "before vX.X.X deploy"
echo.
echo   [一键回滚到上一个 commit]
echo     git reset --hard HEAD~1
echo.
echo   [查看所有历史]
echo     git log --oneline
echo.
echo   [对比当前和上一版有何不同]
echo     git diff HEAD~1
echo.
echo ========================================================
echo.
pause
