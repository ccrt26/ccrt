# 深度分析后评估系统 v1.0 — 灰度部署记录

- 部署日期: 2026-05-26
- 部署工程师: 红枫
- 触发流程: §七 阶段⑥ 灰度部署
- 前序闸门: 闸门1 PASS (情墨设计+腰子确认) | 闸门2 PASS (新安四层验证)

## 部署清单

| # | 文件 | 位置 | 分级 | 用途 |
|:--|:-----|:-----|:----:|:-----|
| 1 | math_utils.ps1 | 代码文件/lib/ | L0 | Spearman/ICIR/Brier/MAPE共享函数 |
| 2 | parse_deep_analysis_report.py | 代码文件/深度分析/ | L0 | MD报告→结构化JSON |
| 3 | Invoke-DeepAnalysisParser.ps1 | 代码文件/深度分析/ | L0 | Python解析器PS封装 |
| 4 | Measure-DeepEvalMetrics.ps1 | 代码文件/深度分析/ | L1 | A+B双层评估计算引擎 |
| 5 | New-DeepEvalReport.ps1 | 代码文件/深度分析/ | L1 | HTML+PDF报告生成 |
| 6 | Update-DeepEvalKnowledge.ps1 | 代码文件/深度分析/ | L0 | 五路知识库更新 |
| 7 | Invoke-DeepEvalPipeline.ps1 | 代码文件/深度分析/ | L1 | 4阶段主编排器 |
| 8 | deep_eval_versions.json | 重点股票/深度分析/后评估逻辑/ | L0 | v1.0/v1.1/v1.2版本标准 |
| 9 | 深度分析后评估逻辑.md | 重点股票/深度分析/后评估逻辑/ | — | 方法论文档 v1.0 |

## 环境验证

| 依赖 | 版本 | 状态 |
|:-----|:-----|:----:|
| Python | 3.13.13 | OK |
| PowerShell | 5.1 | OK |
| Edge (PDF) | C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe | OK |
| UTF-8 BOM | 全部6个.ps1 | OK |

## 集成点

- **触发**: 每周五手动运行 `Invoke-DeepEvalPipeline.ps1 -ReportPath <md>`
- **输入**: 深度分析报告Markdown (重点股票/深度分析/)
- **输出**: 评估数据JSON + 评估结果JSON (后评估报告/)
- **报告**: HTML→PDF (深度分析报告/)
- **知识库**: 信号CSV + 改进日志MD + 建议JSON + 催化剂JSON + 元评估CSV

## 已知限制 (B3非阻塞)

1. 催化剂解析器需要报告使用"催化剂强制识别"节标题，v1.2用"催化剂清单"
2. 市场阶段解析不支持"震荡偏多"格式
3. 情景概率解析不支持表格格式
4. PDF输出路径在管道摘要中显示为数组（显示问题，不影响功能）

## 回滚路径

```
git checkout HEAD~1 -- 代码文件/深度分析/ 代码文件/lib/math_utils.ps1
```

所有变更在git版本控制下，无外部依赖安装，无数据库变更。

## 调度建议

- 每周五收盘后触发（与深度分析报告同频）
- 中周期(8次)/大周期(16次)/季度(24次)自动检测
- 当前：手动触发，待观察3轮后决定是否加入Task Scheduler
