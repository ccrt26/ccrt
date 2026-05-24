# 每日荐股分析逻辑白皮书 MD→DOCX 转换
param([string]$Version = "v2.4")
$root = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
$md = "$root\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_$Version.md"
$docx = "$root\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_$Version.docx"
if (-not (Test-Path $md)) { Write-Error "未找到: $md"; exit 1 }
python "$root\代码文件\tools\md_to_docx.py" "$md" "$docx" "每日荐股分析逻辑白皮书 $Version"
Write-Host "完成: $docx"
