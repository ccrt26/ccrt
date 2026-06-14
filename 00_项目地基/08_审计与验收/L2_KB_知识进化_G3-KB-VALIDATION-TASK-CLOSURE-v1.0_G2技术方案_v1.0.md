# G2 技术方案：G3-KB-VALIDATION-TASK-CLOSURE-v1.0

修复阶段：G3-KB-VALIDATION-TASK-CLOSURE-FIX-v1.0.1

修改对象：
- scripts/validate_global_krm_restore_after_qingshan_flow_v1_0.py（跳过自引用报告）
- scripts/validate_rule_candidate_validation_tasks_v1_0.py（严格 KRM PASS 检查）
- reports/global_krm_restore_after_qingshan_flow_validation_v1.1.2.json
- reports/knowledge_workflow_foundation_validation_v1.0.json
- reports/rule_candidate_validation_task_closure_validation_v1.0.json
- reports/rule_candidate_validation_task_closure_fix_validation_v1.0.json
- reports/workflow_foundation_warn_closure_v1.0.json
- manifest.json
- G0-G6 审计文件

核心修复：
1. KRM validator 跳过 manifest_integrity 中自身报告文件的 sha 检查。
2. validation task validator 通过 subprocess 真实执行 foundation validator。
3. validation task validator 通过 subprocess 真实执行 global KRM validator。
4. validation task validator 从 report JSON 读取 result 字段，只允许 PASS。
5. KRM WARN / FAIL / MISSING / PARSE_FAIL 都导致 validator FAIL。
6. G0-G6 审计文件补齐完整复查信息（目标、命令、检查项、产出物、边界、遗留）。
7. workflow_foundation_warn_closure 引用 G0-G6 作为证据。

允许改动的范围：
- knowledge/scripts/\*.py
- knowledge/reports/\*.json
- knowledge/manifest.json
- knowledge 下非 validation_task/validation_modules/literature_cards/rule_candidates/rules 的文件

禁止改动的范围：
- validation_tasks/ 下的 ValidationTask 正文
- validation_modules/ 下的模块注册表
- literature_cards/ 下的所有文献卡片
- rule_candidates/ 下的所有候选
- rules/ 下的 active rule
- .claude/agents/ 下的角色定义
- 任何周报/日报/荐股/模拟交易生产入口

验收命令：
python3 knowledge/scripts/validate_rule_candidate_validation_tasks_v1_0.py
python3 knowledge/scripts/validate_knowledge_workflow_foundation_v1_0.py
python3 knowledge/scripts/validate_global_krm_restore_after_qingshan_flow_v1_0.py

放行标准：
- validator result = PASS
- foundation exit_code = 0 且 report_result = PASS
- global KRM exit_code = 0 且 report_result = PASS
- global_krm_warn_not_accepted = true
- manifest 无坏账、无重复 id、固定 report id 存在
- ValidationTask 仍为 validation_task_open
- 未新增 LiteratureCard / RuleCandidate
- 未晋升 active rule

Formal pipeline：
- 本文件为 CCRT 接力包记录，不等同 actor/HMAC formal pipeline PASS。

遗留问题：
- 真实验证尚未开始。
- 后续需由场景留痕接入承接。
