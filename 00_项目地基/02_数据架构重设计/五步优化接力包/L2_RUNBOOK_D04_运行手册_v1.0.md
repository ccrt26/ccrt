# D04 运行手册

> **流程编号**：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G3（实施阶段）
> **日期**：2026-06-09
> **版本**：v1.0（STEP4 落盘）
> **适用角色**：玉夜（日常运维）、新安（验收）、红结（实施）

---

## 一、D04 架构概览

### 1.1 能力定义

D04 数据中台（C-D04-0001）是**数据中台与历史分析服务能力**，负责：

| 能力边界 | 内容 |
|:---------|:------|
| ✅ 存储 | L1 JSON 热数据、L2 SQLite 温数据、L3 JSON 归档 |
| ✅ 索引 | 按 code + date 组合索引 |
| ✅ 查询 | UnifiedDataSource 10 个统一接口 |
| ✅ 预计算结果读取 | 因子面板、历史百分位、风险指标等只读查询 |

**十不做**（NOT-01 ~ NOT-10）：不采集、不质量验证、不回测、不生成因子/信号、不自定义因子 IC、不做统一解读、不做风控决策、不做交易决策、不做投资建议、不做分析推理。

### 1.2 三层权威架构

| 层级 | 定位 | 路径 | 生命周期 |
|:-----|:-----|:------|:---------|
| **L1** | 当日权威 | `代码文件/数据/data_full.json` + `kline_cache/{code}.json` + `fund_flow_cache/{code}.json` | 每日更新，git 跟踪 |
| **L2** | 历史权威 | `代码文件/数据/l2_cache/l2_cache.db（SQLite 7 表）` | Phase 2 启用，永久保留 |
| **L3** | 归档权威 | `历史数据/04_原始数据/{年}/` 周级快照 | 永久归档，仅审计追溯 |

### 1.3 权威裁决规则

- 当日判断 → **L1 为准**（引擎当日唯一读入源）
- 历史回溯 → **L2 为首选**（索引快 + SQL JOIN + 口径统一）
- 审计追溯 → **L3 为参考**（仅存档验证，不被程序常规读取）
- L1 vs L2 不一致 → **L1 为准**（L1 是生产数据实时截面）
- L2 vs L3 不一致 → **L2 为准**（L2 是最新重建基线）

---

## 二、目录结构

```
代码文件/数据/
├── data_full.json              # L1 截面权威（报价+财务+板块）
├── kline_cache/{code}.json     # L1 K 线缓存（57 只股票，~122 天/只）
├── fund_flow_cache/{code}.json # L1 四档资金缓存（14 条目）
├── l2_cache/
│   ├── .gitignore              # 排除 *.db / backup / 运行时日志
│   ├── README.md               # L2 目录说明
│   ├── SOP_P0.md               # L2 P0 运维标准操作流程
│   ├── backup/                 # L2 备份目录（Phase 2 启用）
│   └── shadow_diff_log.jsonl   # UnifiedDataSource shadow diff 日志
├── unified_data_source.py      # D04 统一数据访问接口（Shadow 模式）
├── data_scored.json            # 评分引擎输出（L1 日内截面缓存）
├── data_final.json             # 最终评分输出（L1 日内截面缓存）
└── dynamic_pool.json           # 动态股票池
```

---

## 三、日常运维操作

### 3.1 健康检查（日检）

```bash
# D04 目录/DB/哨兵/备份综合检查
python3 scripts/check_d04_health.py --dry-run

# Freshness 闸门（含 L2 子项验证，SKIP 不阻断）
python3 scripts/check_freshness_degradation.py --all --date <YYYYMMDD> --tier l2

# Numeric 一致性检查（含 kline_l2 子项验证，SKIP 不阻断）
python3 scripts/check_numeric_source_consistency.py --all --date <YYYYMMDD>
```

### 3.2 Shadow 验证（周检）

```bash
# 验证 UnifiedDataSource 与 legacy 源的数据一致性
python3 scripts/run_shadow_diff.py --all-stocks --date <YYYYMMDD>
```

### 3.3 注册表一致性检查（周检）

```bash
# 验证两个注册表 JSON 语法
python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json
python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json
```

### 3.4 禁止范围核验（月检）

```bash
# 确认正式日报入口未引用 UnifiedDataSource
grep -rn "unified_data_source\|UnifiedDataSource" \
  代码文件/tools/daily_orchestrator.py \
  代码文件/每日荐股/scripts/daily_workflow.py \
  代码文件/lib/cached_data_source.py

# 确认 l2_cache.db 未错误创建
test ! -e 代码文件/数据/l2_cache/l2_cache.db
```

---

## 四、UnifiedDataSource 接口查询

```python
from unified_data_source import UnifiedDataSource
ds = UnifiedDataSource()

# 行情查询
quote = ds.get_quote("600114")                # L1 data_full.json
kline = ds.get_kline("600114", 120)           # L1 kline_cache → L2 fallback

# 历史追溯
hist = ds.get_score_history("600114", "2026-01-01", "2026-06-09")
fins = ds.get_financials("600114", 4)

# 宏观数据（L2 依赖，无 L2 时返回 degraded）
macro = ds.get_macro("CPI", 6)

# 暂存接口（→D06/D07/D08，无预计算结果时返回 not_available_in_step3）
ic    = ds.compute_factor_ic("TotalScore", 20)
dd    = ds.get_max_drawdown("600114")
panel = ds.export_factor_panel(["600114", "300736"], "2026-01-01", "2026-06-09")
```

---

## 五、故障处理

| 症状 | 可能原因 | 处理步骤 | 升级路径 |
|:-----|:---------|:---------|:---------|
| check_d04_health.py WARN | l2_cache.db 不存在（预期） | 忽略（Phase 2 前正常） | 如需创建需用户授权 |
| Freshness L2 子项 SKIP | kline_l2 enabled=false | 确认 phase<2，正常 | — |
| Numeric kline_l2 SKIP | kline_l2 enabled=false | 确认 phase<2，正常 | — |
| UDS 接口返回 degraded | l2_cache.db 不存在 | 确认 L2 依赖接口预期行为 | 如需创建需用户授权 |
| Shadow diff 超出容差 | kline_cache 与 data_full 数据差异 | 输出差异报告，不阻断 | 通知新安/玉夜排查 |
| 注册表 JSON 解析失败 | 手动编辑导致语法错误 | 回退到 git 历史版本 | 通知红结/情墨 |

---

## 六、停止操作

D04 为只读数据中台层，无运行中服务需要停止。如需停用 UnifiedDataSource shadow 验证，仅不再运行 `scripts/run_shadow_diff.py` 即可。

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 阶段门：G3*
*formal pipeline actor/HMAC 明示例外*
