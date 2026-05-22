<#
.SYNOPSIS
  重点股票次日后评估报告生成入口（stub）
.DESCRIPTION
  委托至 代码文件/重点股票/次日评估/gen_eval_doc.ps1 执行完整评估报告生成。
  保留此入口确保白皮书路径规范有效。
#>
$realScript = "C:\Users\34269\Documents\Claude\股票分析\代码文件\重点股票\次日评估\gen_eval_doc.ps1"
if (-not (Test-Path $realScript)) { Write-Error "评估报告脚本不存在: $realScript"; exit 1 }
& $realScript @args
