# 规则红线检查工具

## check_redlines.ps1
自动化红线合规检查脚本。
用法：powershell -File check_redlines.ps1
在提交代码前运行，检查数据源完整性、文件一致性、版本管理等。

## gen_redlines_doc.ps1
[遗留] 红线文档 DOCX 生成器（硬编码内容）。
注意：这个脚本不执行任何检查，它只是编译文档。
替代方案：使用 `..\tools\md_to_docx.py` 从 .md 自动生成 .docx。

## build_docx.ps1
使用 python-docx 从 .md 自动生成 .docx。
用法：.\build_docx.ps1 [-Version v1.3]
