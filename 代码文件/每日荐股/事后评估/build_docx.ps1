# 次日后评估白皮书 MD→DOCX 转换
param([string]$Version = "v1.5")
$root = "C:\Users\34269\Documents\Claude\股票分析"
$md = "$root\每日荐股\事后评估\次日后评估白皮书_$Version.md"
$docx = "$root\每日荐股\事后评估\次日后评估白皮书_$Version.docx"
if (-not (Test-Path $md)) { Write-Error "未找到: $md"; exit 1 }
python "$root\代码文件\tools\md_to_docx.py" "$md" "$docx" "次日后评估白皮书 $Version"
Write-Host "完成: $docx"
