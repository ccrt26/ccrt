# D04 注册与闸门同步补丁方案

> 流程：F-ARCH | F-GATE
> 阶段门：G2（技术方案设计冻结）
> 日期：2026-06-08

---

## 一、capability_registry.json 注册现状

### 1.1 当前状态

C-D04-0001 已在 `capability_registry.json` 注册（第 265-296 行），字段如下：

| 字段 | 当前值 | schema 合规 |
|:-----|:-------|:------------|
| `capability_id` | `"C-D04-0001"` | ✅ 匹配 `^C-D(0[1-9]\|1[0-2])-[0-9]{4}$` |
| `name` | `"数据中台与历史分析服务能力"` | ✅ ≤64 字符 |
| `domain` | `"D04"` | ✅ 在 domain_enum 中 |
| `inputs` | `["C-D01-0001 DataSnapshot（已验证当日截面）", "tushare API 历史K线/财务补偿（一次拉取+增量）"]` | ✅ 字符串数组 |
| `outputs` | 8 个字符串描述接口产出 | ✅ 字符串数组 |
| `dependencies` | `["C-D01-0001", "C-D03-0001"]` | ✅ 字符串数组（`items: "capability_id"`） |
| `status` | `"active"` | ✅ 在 status_enum 中 |

### 1.2 存在的问题

| 问题 | 严重程度 | 处理方式 |
|:-----|:---------|:---------|
| `INDEX_地基正式文件索引_v1.0.md` §1.1 称 D04 "暂未注册最小能力" | 🟡 文档不同步 | STEP1 更新 INDEX 为"已注册 C-D04-0001" |
| `README_五步优化接力索引.md` 称 "D04 当前未在 capability_registry.json 正式注册" | 🟡 文档过时 | STEP1 更新 README 为"已注册" |
| C-D04-0001 的 `cost_profile.time` 为 `"0s"` | 🟢 预留占位 | Phase 2 上线后实测更新 |

### 1.3 最终确认项

☐ 当前 `capability_registry.json` 的 `C-D04-0001` 条目**没有** `consumed_by` 字段；这是现有 schema 允许的状态。STEP1 不得为了补充消费者关系而擅自扩 schema。

☐ 若后续确需记录消费者关系，只能采用两种方式之一：

| 方式 | 要求 | 相位 |
|:-----|:-----|:-----|
| 不扩 schema | 在地基文档或 source/capability 附注中记录 D05/D06/D07/D08 消费关系 | STEP1 可做 |
| 扩 schema | 先走 F-ARCH + F-GATE，定义 `consumed_by` 字段 schema，值必须是纯 capability_id，不得写 `"C-D08-0001（待注册）"` 这类混合文本 | 另起阶段 |

---

## 二、numeric_field_mapping.json 同步方案

### 2.1 当前状态

`kline_l2` 映射已在 `numeric_field_mapping.json` 注册（第 136-162 行）：

```json
"kline_l2": {
  "source_type": "sqlite",
  "source_path_template": "代码文件/数据/l2_cache/l2_cache.db",
  "source_table": "kline",
  "date_format": "YYYY-MM-DD",
  "lookup_key": "code",
  "fields": {
    "delta.close": { "source_query": "SELECT close FROM kline WHERE code=? AND date=?", "tolerance": 0.001 },
    "delta.change_pct": { "source_query": "SELECT close FROM kline WHERE code=? AND date=?", "tolerance": 0.05 },
    "delta.volume_wan_shou": { "source_query": "SELECT volume FROM kline WHERE code=? AND date=?", "tolerance_wan_shou": 1.0 }
  }
}
```

### 2.2 需补充

| 补充项 | 当前 | 需改为 | 处理步骤 |
|:-------|:-----|:-------|:---------|
| `description` 字段 | 已有 | 保持 | — |
| `enabled` 标记 | 无 | 增加 `"enabled": false`（Phase 2 启用） | GATE STEP1 增加 |
| `phase` 标记 | 无 | 增加 `"phase": 2` | GATE STEP1 增加 |
| `authority_resolution` | 无 | 增加 `"authority_resolution": "L1 优先——当日用 L1 判断；历史回引用 L2"` | GATE STEP1 增加 |

> **注意**：`numeric_field_mapping.json` 的 schema 未有标准 `enabled`/`phase` 字段定义。新增字段不影响现有 `check_numeric_source_consistency.py` 读取（脚本只读所需字段，忽略未知字段）。建议在文件头部 `description` 段注明新增字段用途。

---

## 三、freshness_rules.json 同步方案

### 3.1 当前状态

`kline_l2` 规则已在 `freshness_rules.json` 注册（第 101-119 行）：

```json
"kline_l2": {
  "source_path": "代码文件/数据/l2_cache/l2_cache.db (kline表)",
  "allowed_lag_days": 1,
  "required_for_action": false,
  "on_missing": "WARN",
  "on_stale_claim": "WARN",
  "authority_source": ["代码文件/数据/kline_cache/{code}.json", "代码文件/数据/l2_cache/l2_cache.db"],
  "source_resolution": "L1优先——当日用L1判断；历史回引用L2。freshness检查以L1为准。",
  "max_lag_days": 1,
  "decision_impact": "中——L2为历史分析回源，不阻断当日报告",
  "block_condition": "L1无当日数据且L2无当日数据",
  "warn_condition": "L1有当日但L2无当日",
  "degradation_required": false,
  "description": "L2 K线——历史分析回源，不阻断当日报告。相位0仅注册规则，Phase 2启用闸门检查。"
}
```

### 3.2 状态确认

`freshness_rules.json` 的 `kline_l2` 规则已经比较完整：
- ✅ 含 `source_resolution` 字段标注 L1/L2 优先级
- ✅ 含 Phase 说明（Phase 0 仅注册规则，Phase 2 启用闸门检查）
- ✅ 权威源数组明确
- ✅ 降级策略明确

需 STEP1 补充：
| 补充项 | 处理 |
|:-------|:-----|
| 增加 `"phase": 2` 字段标记启用相位 | GATE STEP1 |
| 增加 `"enabled": false` 字段 | GATE STEP1 |

---

## 四、source_registry.json 同步方案

`source_registry.json`（`00_项目地基/02_权威注册表/source_registry.json`）当前为骨架状态。STEP1 需补充：

| 新增条目 | source_id | type | path | tier |
|:---------|:----------|:-----|:-----|:-----|
| L1 data_full | `src_l1_data_full` | json_file | `代码文件/数据/data_full.json` | L1 |
| L1 kline_cache | `src_l1_kline_cache` | json_dir | `代码文件/数据/kline_cache/` | L1 |
| L1 fund_flow | `src_l1_fund_flow` | json_dir | `代码文件/数据/fund_flow_cache/` | L1 |
| L2 cache | `src_l2_db` | sqlite | `代码文件/数据/l2_cache/l2_cache.db` | L2 |
| L3 archive | `src_l3_archive` | json_dir | `历史数据/04_原始数据/{year}/` | L3 |

> **注意**：`source_registry.json` 修改属 GATE STEP1 范围，本步仅记录方案。

---

## 五、check_*.py 闸门脚本适配方案

| 闸门脚本 | 当前 | 适配内容 | 启用相位 |
|:---------|:-----|:---------|:---------|
| `check_numeric_source_consistency.py` | 支持 `kline_l2` 映射 | — | Phase 0 已注册，Phase 2 启用检查 |
| `check_freshness_degradation.py` | 支持 `kline_l2` 规则 | 增加 `--tier l2` 参数 | Phase 2 |
| `check_daily_data_completeness.py` | 基于 L1 | 无需修改 | — |
| `check_daily_release_gate.py` | 基于 L1 | 无需修改 | — |

> 闸门脚本修改属于 GATE 流程，不在本 F-ARCH 流程中直接处理。本方案仅记录接口和相位。

---

## 六、INDEX 与 README 同步方案

| 文件 | 当前内容 | 需修正为 | 处理步骤 |
|:-----|:---------|:---------|:---------|
| `INDEX_地基正式文件索引_v1.0.md` §1.1 | "D04 缓存/权威源沉淀，暂未注册最小能力" | "D04 数据中台，已注册 C-D04-0001" | STEP1 |
| `README_五步优化接力索引.md` §冲突摘要 1 | "D04 当前未在 capability_registry.json 正式注册" | "D04 已注册 C-D04-0001（需确认 schema 完全兼容）" | STEP1 |

---

## 七、复查必跑命令

```bash
# JSON 合法性
python3 -m json.tool 00_项目地基/02_权威注册表/capability_registry.json >/tmp/capability_registry.check
python3 -m json.tool 00_项目地基/04_一致性闸门/numeric_field_mapping.json >/tmp/numeric_field_mapping.check
python3 -m json.tool 00_项目地基/04_一致性闸门/freshness_rules.json >/tmp/freshness_rules.check

# D04 注册字段核验：不得假设 consumed_by 已存在
python3 -c "import json; c=json.load(open('00_项目地基/02_权威注册表/capability_registry.json'))['capabilities']['C-D04-0001']; assert c['capability_id']=='C-D04-0001'; assert c['status']=='active'; assert 'consumed_by' not in c; print('C-D04-0001 schema-compatible OK')"

# kline_l2 注册痕迹
rg -n '\"kline_l2\"|source_resolution|authority_source' 00_项目地基/04_一致性闸门/numeric_field_mapping.json 00_项目地基/04_一致性闸门/freshness_rules.json

# STEP0 禁止越界改动检查
git status --short -- 代码文件 scripts 历史数据
```
