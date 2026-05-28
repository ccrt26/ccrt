# 架构设计 — 日报命令文件去硬编码，股票池统一引用

> **设计编号**: DES-20260529-001 | **情墨产出** | **版本**: v1.0
> **日期**: 2026-05-29 | **触发**: 5/28股票池扩容至10只，日报.md未同步→遗漏2只日报
> **pipeline_stage**: complete

---

## 一、问题诊断

### 1.1 当前状态（反模式：配置散落）

```
股票池定义同时存在于3个位置：
  pigeon_config.json          → 10只 ✅ (5/28已更新)
  .claude/commands/日报.md     → 8只  ❌ (硬编码表格，未同步)
  batch_gen_keystock_pdfs.py  → 8只  ❌ (硬编码STOCKS列表，未同步)
```

### 1.2 根因

arch-anti-patterns 中明确记录的"配置散落"——同一事实（重点股票池）在多个文件中独立硬编码，扩容时靠人工逐文件同步，必然漂移。

---

## 二、设计方案

### 2.1 核心决策：单一权威源

```
pigeon_config.json = 股票池唯一权威定义

所有下游消费者通过引用获取，不复制：
  日报.md     → 指令中引用 pigeon_config.json，用Python生成动态表格
  batch脚本   → import json读取 pigeon_config.json
  其他下游    → 统一接口: pigeon_config.json[].code + .name
```

### 2.2 变更范围与分级

| # | 文件 | 变更类型 | 等级 | 行数 | 说明 |
|:--|:-----|:--------|:---:|:---:|:-----|
| 1 | `.claude/commands/日报.md` | 替换硬编码表格 | M类 | ~15行 | 删除8行表格+2行固定数字，替换为动态引用指令 |
| 2 | `代码文件/tools/batch_gen_keystock_pdfs.py` | 硬编码→动态读取 | L0 | ~10行 | STOCKS列表改为从pigeon_config.json加载 |
| 3 | `代码文件/监督机制/pipeline_engine.py` | 新增一致性检查 | L1 | ~20行 | 增加 `--check-pool-consistency` 子命令 |
| 4 | `代码文件/监督机制/check_pool_consistency.py` | **新增** | L0 | ~40行 | 独立校验脚本，检查日报.md/pigeon_config/其他文件的股票数一致性 |

### 2.3 日报.md变更细节

**删除**（第14-29行）：
```markdown
## 重点股票池（全部8只，必须每只都出）

| # | 代码 | 名称 | 行业 |
|:--|:----|:-----|:-----|
| 1 | 600114 | 东睦股份 | 汽车/机械 |
...
> ⛔ 每个交易日生成8份日报
```

**替换为**：
```markdown
## 重点股票池

> ⛔ **动态池**：从 `代码文件/信鸽信息采集/pigeon_config.json` 读取当前股票池。
> 执行日报前必须运行以下命令确认池子：
> ```
> python3 -c "import json; [print(f'{s[\"code\"]} {s[\"name\"]}') for s in json.load(open('代码文件/信鸽信息采集/pigeon_config.json'))]"
> ```
> ⛔ **每只股票独立产出**：池中有N只就产出N份日报，每日数量以pigeon_config.json为准。
```

### 2.4 Token影响评估

| 场景 | 变更前 | 变更后 | 增量 |
|:-----|:------|:-----|:---:|
| 日报命令加载 | 读取8行硬编码表格 | 读取引用指令+执行Python查询 | +~1K tokens |
| 股票数变更 | 手动编辑MD | 仅更新pigeon_config.json | **零增量** |
| 跨文件校验 | 无 | pipeline_engine.py --check-pool-consistency | +~0.5K/次 |

> **结论**: 每次日报调用增加约1K tokens（Python查询输出），但消除"遗漏标的"风险。净收益为正——1K token换来零遗漏保证。

---

## 三、接口契约

### 3.1 pigeon_config.json 作为权威源

```
消费者接口:
  import json
  stocks = json.load(open('代码文件/信鸽信息采集/pigeon_config.json'))
  # stocks[i]['code'], stocks[i]['name'], stocks[i]['market']

向后兼容:
  - 字段不删除，只追加
  - 新增字段必须有默认值
  - code/name/market 为必填字段
```

### 3.2 check_pool_consistency.py 接口

```
输入: 无（自动扫描已知位置）
输出: JSON {consistent: bool, mismatches: [{file, count, expected}]}
退出码: 0=一致, 1=不一致
```

---

## 四、需求→代码核对清单

| 编号 | 检查项 | 依据 | 情墨勾 | 腰子勾 |
|:----:|:------|:-----|:-----:|:-----:|
| R1 | 日报.md不再包含硬编码股票列表 | 本设计§2.3 | ☐ | ☐ |
| R2 | batch_gen_keystock_pdfs.py从pigeon_config.json动态读取 | 本设计§2.2 | ☐ | ☐ |
| R3 | check_pool_consistency.py检查≥2个已知位置 | 本设计§3.2 | ☐ | ☐ |
| R4 | pigeon_config.json字段不变，保持向后兼容 | 本设计§3.1 | ☐ | ☐ |
| R5 | 日报.md中"8只""8份"等固定数字全部移除 | 本设计§2.3 | ☐ | ☐ |
| R6 | 新增代码≤500行，单文件≤500行 | 红线§9.2 | ☐ | ☐ |
