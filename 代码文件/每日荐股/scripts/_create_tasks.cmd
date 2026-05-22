@echo off
chcp 65001 >nul
REM ============================================
REM 以最高权限在固定时间运行注册脚本
REM 用于绕过某些环境下的 UAC 限制
REM ============================================
set SCRIPTS_DIR=C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\scripts

REM 直接调用管理员提权批处理
call "%SCRIPTS_DIR%\register_tasks_admin.bat"
