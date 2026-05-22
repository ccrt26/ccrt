@echo off
chcp 65001 >nul
REM ============================================
REM 铁律量化 · Task Scheduler 注册脚本（备用）
REM 使用 schtasks.exe (兼容性更好)
REM ============================================
set SCRIPTS_DIR=C:\Users\34269\Documents\Claude\股票分析\每日荐股\scripts
set PS_CMD=powershell.exe -NoProfile -ExecutionPolicy Bypass -File

echo ===== Registering TieLv Scheduled Tasks =====
echo.

REM Task 1: Evaluation at 19:00
schtasks /CREATE /SC DAILY /TN "TieLv-Evaluation" /TR "%PS_CMD% \"%SCRIPTS_DIR%\daily_workflow.ps1\" -Mode eval" /ST 19:00 /F
echo   [Created] TieLv-Evaluation — daily at 19:00

REM Task 2: Daily Stock Analysis at 20:00
schtasks /CREATE /SC DAILY /TN "TieLv-DailyStock" /TR "%PS_CMD% \"%SCRIPTS_DIR%\daily_workflow.ps1\" -Mode daily_latest" /ST 20:00 /F
echo   [Created] TieLv-DailyStock — daily at 20:00

echo.
echo Done. Use taskschd.msc to verify.
echo.
schtasks /QUERY /TN "TieLv-*" 2>nul
