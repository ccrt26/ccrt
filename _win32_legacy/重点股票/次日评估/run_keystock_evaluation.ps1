<#
.SYNOPSIS
  重点股票次日评估执行入口（stub）
.DESCRIPTION
  委托至 代码文件/重点股票/次日评估/run_keystock_evaluation.ps1 执行完整评估。
  保留此入口确保白皮书路径规范有效。
#>
$realScript = "C:\Users\34269\Documents\Claude\股票分析\代码文件\重点股票\次日评估\run_keystock_evaluation.ps1"
if (-not (Test-Path $realScript)) { Write-Error "评估执行脚本不存在: $realScript"; exit 1 }
& $realScript @args
