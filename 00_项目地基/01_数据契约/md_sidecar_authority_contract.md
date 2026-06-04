# MD/Sidecar 一致性权威契约

> 版本: 1.0 | 生效日期: 2026-06-02 | 维护人: 情墨+玉夜+阿黑

---

## 一、契约目的

定义日报 MD 正文与同名 JSON sidecar 之间的一致性规则，确保同一份报告的机器可读数据和用户可读内容不互相矛盾。

---

## 二、适用对象

| 对象 | 路径格式 |
|:-----|:---------|
| **日报 MD** | `重点股票/股票报告/{名称}({代码})/{名称}({代码})日报_{date}.md` |
| **JSON sidecar** | `重点股票/股票报告/{名称}({代码})/{名称}({代码})日报_{date}.json` |

同一只股票、同一交易日的 MD 与 JSON 必须一致。

---

## 三、一致性类别

| 类别 | 检查项 | BLOCK 条件 |
|:-----|:-------|:-----------|
| **A. 报告身份字段** | stock_code, stock_name, trade_date | 任意不一致 |
| **B. baseline_id** | MD 头部 baseline_id vs sidecar.baseline_id | 不一致 |
| **C. P0 决策卡** | t1_action, position_cap, stop_loss, confidence, forbidden_actions | 关键价格/动作/仓位不一致 |
| **D. 行情字段** | close, change_pct, volume_wan_shou | 超过容差 |
| **E. 四档资金字段** | super_large/large/medium/small/main_force_net | 超过容差 |
| **F. 板块相位** | sector_phase (MD vs SC vs 山猫大盘板块) | 不一致 |
| **G. 风控灯** | risk_light.overall | 不一致 |
| **H. eval_hooks** | t1_verify, t5_verify 日期 | 日期冲突 |
| **I. sidecar 内部镜像** | machine_fields vs 顶层字段 | 任意不一致 |

---

## 四、BLOCK 规则

以下情况必须 BLOCK，日报不得归档：

| 规则 | 检测方式 |
|:-----|:---------|
| MD 与 sidecar 关键身份字段不一致（code/name/date） | `check_md_sidecar_consistency.py` |
| baseline_id 不一致 | `check_md_sidecar_consistency.py` |
| P0 决策卡关键价格/仓位不一致（仓位 >0.01, 止损 >0.01） | `check_md_sidecar_consistency.py` |
| 当前动作方向冲突（buy↔hold, sell↔hold, buy↔sell） | `check_md_sidecar_consistency.py` |
| 行情/资金数值超过容差（close>0.001, change>0.05%, volume>1万手, 资金>1万） | `check_md_sidecar_consistency.py` |
| 板块相位不一致 | `check_md_sidecar_consistency.py` |
| 风控灯不一致 | `check_md_sidecar_consistency.py` |
| eval_hooks 日期冲突 | `check_md_sidecar_consistency.py` |
| sidecar 内部镜像字段冲突 | `check_md_sidecar_consistency.py` |
| sidecar 有关键字段但 MD 缺失 | `check_md_sidecar_consistency.py` |
| MD 有额外持仓/止损声明与 P0 表不符 | `check_md_sidecar_consistency.py` |

---

## 五、WARN 规则

以下情况输出 WARN，不阻塞归档但需记录：

| 规则 | 例子 |
|:-----|:------|
| 非决策展示字段缺失 | MD 未包含某个辅助字段 |
| 可解释的格式差异 | MD "35.16元(S1支撑位)" vs sidecar "35.16元(S1)" |
| 不影响动作的辅助字段差异 | 不改变决策的次要说明 |

---

## 六、PASS 规则

通过必须满足：

| 条件 | 说明 |
|:-----|:------|
| 关键字段一致 | code/name/date/baseline_id 全部一致 |
| 数值字段在容差内 | close±0.001, change±0.05%, volume±1万手, 资金±1万 |
| 条件动作与当前动作已区分 | `extract_primary_action` 正确分辨 |
| 动作方向兼容 | hold↔hold, hold↔neutral 不冲突 |
| sidecar 内部镜像一致 | 7 项全部一致 |

---

## 七、禁止事项

| 禁止 | 说明 |
|:-----|:------|
| ⛔ 禁止通过修改日报适配闸门 | 历史报告保持原地不动 |
| ⛔ 禁止通过修改 sidecar 掩盖 MD 错误 | sidecar 是事实载体，不是适配目标 |
| ⛔ 禁止用 MD 作为数值权威源 | MD 是展示层，数值以 sidecar 和权威源为准 |
| ⛔ 禁止跳过 sidecar 内部镜像检查 | machine_fields 必须与顶层一致 |

---

## 八、生成前/生成后要求

| 阶段 | 要求 |
|:-----|:------|
| **日报生成后** | 必须执行 `python3 scripts/check_md_sidecar_consistency.py --all --date <日期>` |
| **出现 BLOCK** | 不得归档，需修复后方可提交 |
