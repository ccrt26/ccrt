@echo off
chcp 65001 >nul
REM ============================================
REM 铁律量化 · Task Scheduler 注册脚本
REM 自动提权 → 调用 PowerShell 注册脚本
REM ============================================
set SCRIPTS_DIR=C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\scripts
set PS_SCRIPT=%SCRIPTS_DIR%\register_tasks.ps1

REM 检查管理员权限
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 请求管理员权限以注册定时任务...
    powershell.exe -NoProfile -Command "Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%PS_SCRIPT%\"' -Verb RunAs -Wait"
    echo.
    echo 注册完成。
    pause
    exit /b
)

REM 已是管理员，直接运行
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
echo.
pause
