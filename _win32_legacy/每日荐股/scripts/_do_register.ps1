. "$PSScriptRoot/../../lib/init_encoding.ps1"
# PowerShell script to register TieLv tasks
# 用 Register-ScheduledTask 设置 S4U + Highest，无需密码

& $PSScriptRoot\register_tasks.ps1 @args
