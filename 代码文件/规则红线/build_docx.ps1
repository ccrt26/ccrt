# 规则红线 MD→DOCX 转换
param([string]$Version = "v1.3")
$root = "C:\Users\34269\Documents\Claude\股票分析"
$md = "$root\规则红线\分析的规则红线--Claude_$Version.md"
$docx = "$root\规则红线\分析的规则红线--Claude_$Version.docx"
if (-not (Test-Path $md)) { Write-Error "未找到: $md"; exit 1 }
python "$root\代码文件\tools\md_to_docx.py" "$md" "$docx" "分析的规则红线--Claude $Version"
Write-Host "完成: $docx"
