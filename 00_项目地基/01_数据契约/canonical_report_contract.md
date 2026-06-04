# canonical_report 影子对象权威契约

> 版本: 1.0 | 生效日期: 2026-06-04 | 维护人: 情墨+玉夜+阿黑
>
> 第6-A阶段产物 — 仅做 shadow，不切真实链路。

---

## 一、契约目的

定义 canonical_report 影子对象的数据结构、映射规则和校验标准，
使现有日报 MD + JSON sidecar 可被无损吸收到 canonical_report，
并能从 canonical_report 还原出与原始 MD/sidecar 完全一致的 shadow 输出。

---

## 二、适用对象

| 对象 | 路径格式 |
|:-----|:---------|
| **日报 MD** | `重点股票/股票报告/{名称}({代码})/{名称}({代码})日报_{date}.md` |
| **JSON sidecar** | `重点股票/股票报告/{名称}({代码})/{名称}({代码})日报_{date}.json` |
| **canonical_report** | `00_项目地基/03_报告对象/canonical_report.schema.json` |
| **映射规则** | `00_项目地基/03_报告对象/canonical_report_field_mapping.json` |

---

## 三、影子对象不变式

1. **shadow_only = true**：canonical_report 永不为真实生成链路的输入。
2. **source_hashes 约束**：构建时必须记录 MD 和 sidecar 的 SHA-256，校验时逐字节比对。
3. **source_payloads 约束**：MD 原文和 sidecar 原始 JSON 必须完整保存。
4. **render_snapshot 镜像**：`render_snapshot.md_text` === `source_payloads.md_text`，
   `render_snapshot.sidecar_payload` === `source_payloads.sidecar_payload`。
5. **单向构建**：build 脚本只读取，不写入正式报告目录，不修改任何输入文件。

---

## 四、字段映射总则

canonical_report 从 sidecar 映射的字段，保持原始数据类型（字符串/数字/对象不变）。

| canonical 路径 | sidecar 来源 | 类型 |
|:---------------|:-------------|:-----|
| report_identity.stock_code | sidecar.stock_code | string |
| report_identity.stock_name | sidecar.stock_name | string |
| report_identity.trade_date | sidecar.trade_date | string |
| authority_refs.baseline_id | sidecar.baseline_id | string |
| decision_snapshot.p0_decision_card | sidecar.p0_decision_card | object |
| data_snapshot.delta | sidecar.delta | object |
| data_snapshot.fund_flow_4level | sidecar.fund_flow_4level | object |
| data_snapshot.sector_phase | sidecar.sector_phase | object |
| data_snapshot.source_snapshot | sidecar.source_snapshot 或 {} | object |
| risk_snapshot.risk_light | sidecar.risk_light | object |
| interpretation_snapshot.role_interpretations | sidecar.role_interpretations | object |
| interpretation_snapshot.yaozi_integration | sidecar.yaozi_integration | object |
| eval_snapshot.eval_hooks | sidecar.eval_hooks | object |

---

## 五、完整字段清单

| 顶层字段 | 类型 | required | 说明 |
|:---------|:-----|:---------|:-----|
| canonical_version | string | yes | 本影子对象版本号 |
| shadow_only | boolean | yes | 必须为 true |
| report_identity | object | yes | 报告身份标识 |
| authority_refs | object | yes | 权威引用（baseline_id） |
| data_snapshot | object | yes | 行情/资金/板块数据快照 |
| decision_snapshot | object | yes | P0 决策卡 |
| risk_snapshot | object | yes | 风控灯 |
| interpretation_snapshot | object | yes | 角色解读+腰子整合 |
| eval_snapshot | object | yes | 后评估钩子 |
| render_snapshot | object | yes | 渲染镜像（MD原文+sidecar原JSON） |
| source_hashes | object | yes | 源文件哈希（sha256） |
| source_payloads | object | yes | 源文件完整内容 |

---

## 六、第6-B 展示层影子渲染规则

1. **影子链路**：canonical → MD/sidecar 渲染仍是影子链路，不切真实生成链路。
2. **输出约束**：渲染输出只能写入 `/private/tmp` 或显式 `--out-dir`，禁止写入 `重点股票/股票报告/`。
3. **唯一来源**：`render_snapshot` 是渲染的唯一来源。`render_report_from_canonical.py` 不得从正式报告目录重新读取 MD/sidecar。
4. **输入约束**：不得修改 canonical 输入文件。
5. **第6-B 闸门**：第6-B 不进入第6-C。第6-B 完成后不自动切入真实生成链路。

---

## 七、第6-C canonical发布前总闸门规则

1. **定位**：第6-C是发布前总闸门，串联第6-A/第6-B的四个子闸门。
2. **子闸门顺序**：
   - ① canonical shadow check（第6-A）
   - ② report golden diff（第6-A）
   - ③ canonical render（第6-B）
   - ④ canonical render diff（第6-B）
3. **判定规则**：任一子闸门非0退出码 → 总闸门 BLOCK。
4. **影子链路**：第6-C本身仍在影子链路内，不切真实生成链路。
5. **第6-C 闸门**：第6-C 不进入第6-D。第6-C 完成后不自动切入真实链路。

---

## 八、第6-D 生产切换策略冻结

1. **不切生产**：第6-D不切真实生成链路，仅冻结第6-E准入条件和切换策略。
2. **准入契约前置**：第6-E开始前必须完整阅读 `canonical_cutover_contract.md`，逐项确认9项硬性准入。
3. **三段式约束**：真实切换必须按 E1 shadow-only → E2 dual-write → E3 guarded-cutover 顺序执行，禁止一次性 full cutover。
4. **腰子放行**：E3 guarded-cutover 前必须获得腰子金融口径放行签名，腰子未放行不得进入 guarded-cutover。

---

## 九、契约强制

shadow check 失败 = BLOCK，禁止进入第6-B（已通过）。
Golden Diff 失败 = BLOCK，要求重建 canonical。
Render Diff 失败 = BLOCK，要求重建渲染产物。
