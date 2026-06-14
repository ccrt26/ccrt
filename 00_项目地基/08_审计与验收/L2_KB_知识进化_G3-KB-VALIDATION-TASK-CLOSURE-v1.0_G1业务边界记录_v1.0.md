# G1 业务边界记录：G3-KB-VALIDATION-TASK-CLOSURE-v1.0

修复阶段：G3-KB-VALIDATION-TASK-CLOSURE-FIX-v1.0.1

业务目标：
- 保证第 2 步的放行条件真实可靠。
- global KRM 必须是 PASS；WARN 代表仍有待处理风险，不能继续自动推进。
- KRM validator 之前的 manifest_integrity 检查了其自身报告文件，自引用导致无法 PASS。
- G0-G6 必须能被复查者独立理解和追溯。

本阶段不做：
- 不评估 Fama/French 候选是否有效。
- 不开始周报/日报真实验证。
- 不生成任何 active rule。
- 不改变角色知识能力。

验收口径：
- validator 必须真实执行 foundation validator 并通过 subprocess 获取其报告。
- validator 必须真实执行 global KRM validator 并通过 subprocess 获取其报告。
- validator 必须读取 global KRM report result，只允许 result == PASS。
- KRM validator 自身须跳过自引用报告文件的 sha 检查。
- G0-G6 必须包含目标、命令、检查项、产出物、边界、结果、遗留问题。

执行命令：
python3 /Users/ccrt/ccrt/00_项目地基/07_知识进化/knowledge/scripts/validate_rule_candidate_validation_tasks_v1_0.py

Formal pipeline：
- 本文件为 CCRT 接力包记录，不等同 actor/HMAC formal pipeline PASS。
