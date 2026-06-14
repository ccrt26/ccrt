# G0 路由记录：G3-KB-VALIDATION-TASK-CLOSURE-v1.0

修复阶段：G3-KB-VALIDATION-TASK-CLOSURE-FIX-v1.0.1
流程编号：F-GATE

需求识别：
- Fama/French RuleCandidate 已生成 ValidationTask。
- 当前修复只处理流程治理问题：global KRM WARN 放行漏洞、G0-G6 审计过短。
- KRM validator 因自引用 manifest_integrity 检查其自身报告文件，导致永远返回 WARN。
- 不进入真实验证，不生成 ScenarioTrace。

执行命令：
python3 /Users/ccrt/ccrt/00_项目地基/07_知识进化/knowledge/scripts/validate_rule_candidate_validation_tasks_v1_0.py

路由结论：
- 允许进入 G1/G2/G3-G6 修复闭环。
- 本阶段属于知识进化底座治理，不属于金融判断。

禁止范围：
- 不修改 ValidationTask 正文。
- 不修改 validation module registry。
- 不修改 LiteratureCard / RuleCandidate 正文。
- 不修改 active rule。
- 不修改生产入口。

Formal pipeline：
- 本文件为 CCRT 接力包记录，不等同 actor/HMAC formal pipeline PASS。

遗留问题：
- 真实验证尚未开始。
- 后续需由场景留痕接入承接。
