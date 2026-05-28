# 编码初始化 — 全项目统一入口
# 所有 .ps1 脚本入口处 dot-source 本文件

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$OutputEncoding = [System.Text.Encoding]::UTF8
