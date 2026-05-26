<#
.SYNOPSIS
  重点股票白皮书 DOCX 生成入口（stub）
.DESCRIPTION
  委托至 build_docx.ps1 从 .md 生成 .docx，确保内容永远与白皮书同步。
  保留此入口确保白皮书 §5.1 路径规范有效。
.PARAMETER Version
  白皮书版本号，默认 v2.0
#>
param([string]$Version = "v2.0")
$buildScript = Join-Path $PSScriptRoot "..\..\代码文件\重点股票\分析逻辑\build_docx.ps1"
if (Test-Path $buildScript) {
    & $buildScript -Version $Version
} else {
    Write-Error "build_docx.ps1 not found: $buildScript"
    exit 1
}
