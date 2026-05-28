<#
.SYNOPSIS
  重点股票元评估执行入口（stub）
.DESCRIPTION
  委托至 代码文件/重点股票/次日评估/run_meta_evaluation.ps1 执行元评估。
  保留此入口确保白皮书路径规范有效。
#>
$realScript = "C:\Users\34269\Documents\Claude\股票分析\代码文件\重点股票\次日评估\run_meta_evaluation.ps1"
if (-not (Test-Path $realScript)) { Write-Error "元评估脚本不存在: $realScript"; exit 1 }
& $realScript @args
