# STEP1：地基契约与注册表落地

> 本步骤只落地地基契约、注册表、映射和闸门规则。仍不建设 L2 SQLite，不切生产链路。

---

## 新会话启动命令

```text
阿黑，按照标准流程执行：STEP1 地基契约与注册表落地。

前置要求：STEP0 已 PASS，并已有 D04 权威源决策表、能力边界冻结表、注册与闸门同步补丁方案。只允许修改本步骤允许范围内的地基契约/注册表/映射文件和必要闸门配置；禁止建设 L2，禁止切换生产脚本。
```

---

## 本步骤目标

把 STEP0 冻结的决策写入地基文件，使后续实现有合法依据。

落地内容：

1. D04 能力注册。
2. D04 source registry 或权威源 registry 条目。
3. numeric/freshness 权威源映射更新。
4. D04 边界说明。
5. 阶段验收 policy 更新。
6. 后续代码实现的验收命令清单。

---

## 前置检查

必须先确认以下文件存在，且结论为 PASS 或用户明确放行：

1. `00_项目地基/02_数据架构重设计/五步优化接力包/STEP0_设计冻结结论.md`
2. `00_项目地基/02_数据架构重设计/五步优化接力包/D04_权威源决策表.md`
3. `00_项目地基/02_数据架构重设计/五步优化接力包/D04_能力边界冻结表.md`
4. `00_项目地基/02_数据架构重设计/五步优化接力包/D04_注册与闸门同步补丁方案.md`

若缺失，必须 BLOCK，不得自行补脑继续。

---

## 必须读取

1. 本文件
2. STEP0 的全部交付物
3. `00_项目地基/02_权威注册表/capability_registry.json`
4. `00_项目地基/02_权威注册表/source_registry.json`
5. `00_项目地基/02_权威注册表/numeric_field_registry.json`
6. `00_项目地基/02_权威注册表/freshness_field_registry.json`
7. `00_项目地基/01_数据契约/numeric_authority_contract.md`
8. `00_项目地基/01_数据契约/freshness_authority_contract.md`
9. `00_项目地基/04_一致性闸门/numeric_field_mapping.json`
10. `00_项目地基/04_一致性闸门/freshness_rules.json`
11. `00_项目地基/04_一致性闸门/stage_acceptance_policy.json`

---

## 允许修改范围

仅允许修改：

1. `00_项目地基/01_数据契约/`
2. `00_项目地基/02_权威注册表/`
3. `00_项目地基/04_一致性闸门/*.json`
4. `00_项目地基/02_数据架构重设计/五步优化接力包/STEP1_*.md`

---

## 禁止修改范围

1. 禁止修改 `代码文件/` 下生产脚本。
2. 禁止修改 `代码文件/数据/` 下任何运行数据。
3. 禁止修改 `重点股票/股票报告/`。
4. 禁止创建或写入 `l2_cache.db`。
5. 禁止更改调度任务。

---

## 必须完成任务

1. 让 `capability_registry.json` 中 D04 条目符合现有 schema。
2. 若需要扩展 registry schema，必须单独列出变更理由和兼容检查。
3. 更新 source registry，让当日/历史/归档权威源可以被引用。
4. 更新 numeric/freshness 映射，使其不再只认旧缓存路径。
5. 写明 D04 与 D03/D06/D07/D08 的边界。
6. 写明旧闸门脚本在 STEP3 前的过渡策略。
7. 输出 STEP2 的实现准入条件。

---

## 验收命令

至少执行：

```bash
python3 -m json.tool 00_项目地基/02_权威注册表/capability_registry.json
python3 -m json.tool 00_项目地基/02_权威注册表/source_registry.json
python3 -m json.tool 00_项目地基/04_一致性闸门/numeric_field_mapping.json
python3 -m json.tool 00_项目地基/04_一致性闸门/freshness_rules.json
git status --short -- 00_项目地基/01_数据契约 00_项目地基/02_权威注册表 00_项目地基/04_一致性闸门 00_项目地基/02_数据架构重设计/五步优化接力包
```

如项目已有 registry 校验脚本，必须补充执行。

---

## 交付物

1. `STEP1_地基契约落地报告.md`
2. `STEP1_修改文件清单.md`
3. `STEP1_验收命令结果.md`
4. `STEP2_准入检查清单.md`

---

## 通过条件

1. JSON 全部可解析。
2. D04 注册合法。
3. numeric/freshness 映射与 D04 权威源一致。
4. 未修改禁止范围。
5. 旧影复查 PASS 或 WARN 可接受。
6. 用户确认进入 STEP2。

