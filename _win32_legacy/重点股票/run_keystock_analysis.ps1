<#
.SYNOPSIS
  重点股票深度分析入口（stub）
.DESCRIPTION
  委托至 代码文件/重点股票/run_keystock_analysis.ps1 执行完整分析。
  保留此入口确保白皮书 §5.1 路径规范有效。
#>
$realScript = "C:\Users\34269\Documents\Claude\股票分析\代码文件\重点股票\run_keystock_analysis.ps1"
if (-not (Test-Path $realScript)) { Write-Error "核心分析脚本不存在: $realScript"; exit 1 }
& $realScript @args
