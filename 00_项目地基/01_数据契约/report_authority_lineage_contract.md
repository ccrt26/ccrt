# 报告权威继承契约

> 版本: 1.0 | 生效日期: 2026-06-04 | 维护人: 腰子+情墨+阿黑

---

## 一、权威层级总则

日报生成时，各字段的权威源按以下层级判定（从高到低）：

| 层级 | 来源 | 可用作 |
|:----:|:-----|:-------|
| **L1** | 权威注册表 / 基础数据源 | baseline_id、行情数值、资金、融资、板块相位、风控灯 |
| **L2** | 日报 JSON sidecar（第4阶段已验证） | 日报内镜像一致性 |
| **L3** | 日报 MD | 展示层，数值以 L1/L2 为准 |
| **L4** | 深度分析报告正文 | 分析假设、逻辑背景、研究脉络 |
| **L5** | 系统附录 / eval_hooks | 后评估衍生对象 |
| **L6** | 旧日报 | 仅历史记录，禁止作为当前生成源 |

---

## 二、深度分析能做和不能做的事

### 深度分析可以做
| 用途 | 示例 |
|:-----|:------|
| 提供分析假设和逻辑背景 | "核心逻辑：评分41分，风险等级low" |
| 提供研究脉络和策略推演 | "三情景展望：乐观/中性/悲观" |
| 提供定性判断参考 | "证据等级：L1/L2/L3" |

### 深度分析不能做
| 禁止 | 说明 |
|:-----|:------|
| ⛔ 不得作为日报 baseline_id 的权威源 | baseline_id 的权威源是 `baseline_registry.json` |
| ⛔ 不得作为行情数值的权威源 | 行情数值权威源是 `kline_cache` |
| ⛔ 不得作为资金数据的权威源 | 资金权威源是 `fund_flow_cache` |
| ⛔ 不得作为日期新鲜度的权威源 | 日期新鲜度规则见第3阶段契约 |
| ⛔ 不得作为风控数字的权威源 | 风控数字以 `data_scored` 和 sidecar 为准 |
| ⛔ 不得用深度分析正文标题的旧 ID 覆盖 registry 中的 baseline_id | 必须走 `resolve_current_baseline.py` |

---

## 三、日报 MD 与 JSON sidecar 的关系

| 角色 | 职责 |
|:-----|:------|
| **JSON sidecar** | 机器可读的事实镜像载体。数值、字段、日期必须与权威源一致 |
| **MD 正文** | 用户可读的展示层。数值服从 sidecar，动作方向与 sidecar 兼容 |
| **两者关系** | 同源一致（第4阶段契约），**MD 不是数值权威源** |

---

## 四、Baseline 权威继承

| 规则 | 内容 |
|:-----|:------|
| baseline_id 唯一来源 | `00_项目地基/02_权威注册表/baseline_registry.json` |
| 查询命令 | `python3 scripts/resolve_current_baseline.py --code --name --date --json` |
| 关键价位来源 | baseline_registry 中的 `key_fields` |
| 有效期 | `baseline_date <= trade_date <= valid_until` |
| 日报不得使用 | `deep_*` 旧 ID、深度分析正文标题、历史日报中的旧 ID |
| 禁止口径 | `600114_deep_20260529_v1.4` 等旧格式 |

---

## 五、数值字段权威继承

按第2阶段和第3阶段注册表执行：

| 字段 | 权威源 |
|:-----|:-------|
| close / change_pct / volume | `kline_cache/{code}.json` |
| super_large/large/medium/small/main_force | `fund_flow_cache/{code}.json` |
| margin trade_date | `margin_detail/{code}.json` |
| sector_phase | `data_scored.json`（三桶） |
| freshness | 第3阶段契约定义的新鲜度规则 |

---

## 六、日期字段权威继承

按第3阶段日期新鲜度契约执行：
- K 线：T+0，缺失 BLOCK
- 资金：T+0，缺失 BLOCK
- 融资：T+1 允许，超 T+2 需声明
- 板块：data_scored 最新评分
- Baseline：有效期窗口内
- Eval_hooks：t1 ≥ next_trade_date，t5 > trade_date

---

## 七、解释和评估对象的权威边界

| 对象 | 权威源 | 禁止 |
|:-----|:-------|:------|
| 分析逻辑 / 操作建议 | 白皮书、腰子口径 | 不得从系统附录反向推导 |
| 后评估 eval_hooks | 统一解读体系 | 不得覆盖日报事实字段 |
| 系统附录 | 深度分析生成时的衍生对象 | 不得作为 baseline 或数值权威源 |

---

## 八、旧日报的定位

旧日报（历史交易日已归档的报告）**只能作为历史记录被引用**。

旧日报禁止：
- ⛔ 作为当前日报的任何字段权威源
- ⛔ 作为 baseline_id 的依据
- ⛔ 作为行情/资金/板块数据的来源
- ⛔ 作为新鲜度和降级状态的参考

---

## 九、冲突覆盖规则

| 冲突场景 | 覆盖方向 |
|:---------|:---------|
| MD 数值 ≠ sidecar 数值 | sidecar 覆盖 MD |
| sidecar 数值 ≠ 权威注册表数据 | 权威源覆盖 sidecar |
| 深度分析说 "baseline_id=deep_xxx" 但 registry 说 "W2026W22" | **registry 覆盖一切** |
| 系统附录的 eval_hooks 与 sidecar 不一致 | 以 sidecar 为准（日报期最新） |
| 旧日报的内容与当前日报冲突 | 旧日报无覆盖力 |

---

## 十、日报生成前/后必须运行的命令

```bash
# 生成前：检查当前有效 baseline
python3 scripts/resolve_current_baseline.py --all --date <日期>

# 生成后：全闸门回归
python3 scripts/check_baseline_authority.py --all --date <日期>
python3 scripts/check_numeric_source_consistency.py --all --date <日期>
python3 scripts/check_freshness_degradation.py --all --date <日期>
python3 scripts/check_md_sidecar_consistency.py --all --date <日期>
python3 scripts/check_report_authority_lineage.py --all --date <日期>
```

---

## 十一、禁止事项

| 禁止 | 说明 |
|:-----|:------|
| ⛔ 禁止用 deep_* 格式 baseline_id | 必须用 registry 中的周度标准 ID |
| ⛔ 禁止用深度分析正文覆盖 baseline/数值权威 | 深度分析只提供逻辑假设 |
| ⛔ 禁止用系统附录反向决定日报事实字段 | 附录是衍生对象 |
| ⛔ 禁止用旧日报作为当前报告生成依据 | 旧日报只归档，不引用 |
| ⛔ 禁止用日报 MD 作为数值权威源 | MD 是展示层 |
