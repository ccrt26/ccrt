# 数据健康检查基础设施升级 — 架构设计

> pipeline_stage: complete | 设计日期: 2026-05-28 | 版本: v1.0 | 等级: L0

---

## 一、背景

玉夜5/28巡检发现：
- P2: `.sina_health.json`检查过期25h+，腾讯/东财无独立健康检查文件
- P3: 3个JSON文件带UTF-8 BOM（`data_full.json`/`dynamic_pool.json`/`events_db.json`）
- P4: 三源健康检查不完整（仅新浪有持久化健康记录）

## 二、现有架构

```
health_check.py (L1, 138行)
  ├── check_api_connectivity() → 内存级三源检查(腾讯/新浪/东财)
  ├── check_data_file() → 数据文件完整性
  └── main() → CLI: --mode {boot,daily_sim,key_stock,eval}
                  → 输出JSON到stdout
                  → blocked时 exit(1)

.sina_health.json → 仅新浪独立持久化 {LastCheck, ConsecutiveFails}
                   更新频率: 手动/按需
                   最后更新: 2026-05-27 20:00
```

**缺陷**：
- 腾讯/东财无独立健康文件 → 1+2架构不完整
- 健康检查无自动调度 → 检查频率依赖人工触发
- BOM编码不一致 → `json.load()`需指定`encoding='utf-8-sig'`

## 三、设计方案

### 3.1 P2+P4: 三源健康持久化

**方案**：扩展`health_check.py`，增加`--persist`模式，每次检查后写入独立的源健康文件。

**新增输出文件**：
```
代码文件/数据/.sina_health.json       (已有，格式不变)
代码文件/数据/.tencent_health.json    (新增)
代码文件/数据/.eastmoney_health.json  (新增)
```

**健康文件Schema**（三源统一）：
```json
{
  "Source": "tencent|sina|eastmoney",
  "SourceId": "[1]|[2]|[3]",
  "LastCheck": "ISO8601",
  "LatencyMs": 123,
  "Status": "ok|degraded|down",
  "ConsecutiveFails": 0,
  "LastSuccess": "ISO8601",
  "TTL": 3600
}
```

**CLI扩展**：
```
python3 health_check.py --mode hourly  → 轻量三源检查+持久化(盘中使用)
python3 health_check.py --mode daily   → 完整检查+持久化(盘前/盘后)
python3 health_check.py --persist      → 任何模式附加持久化
```

**变更范围**：仅`health_check.py`单文件，新增~60行，不改接口。

### 3.2 P3: BOM编码统一

**根因**：PowerShell脚本用`Out-File -Encoding UTF8`写入（Windows默认带BOM），Python脚本部分用`encoding='utf-8-sig'`读取以兼容。迁移到Mac后BOM不再需要。

**方案**：
1. 修复3个当前受影响的JSON文件（一次性转码）
2. 更新写入端：`batch_data_collector.py`、`scoring_engine_v2.py`确保使用`encoding='utf-8'`(无BOM)
3. 更新读取端：`health_check.py`、`scoring_engine_v2.py`中所有`encoding='utf-8-sig'`改为`encoding='utf-8'`

**变更范围**：
| 操作 | 文件 | 类型 |
|:-----|:-----|:----|
| 转码 | `data_full.json` | 数据文件 |
| 转码 | `dynamic_pool.json` | 数据文件 |
| 转码 | `events_db.json` | 数据文件 |
| 修改读取编码 | `engine/engine.py:211` (utf-8-sig→utf-8) | 代码 |
| 修改读取编码 | `engine/engine.py:253` (utf-8-sig→utf-8) | 代码 |
| 确认写入编码 | `batch_data_collector.py` | 代码 |

## 四、Token影响评估

| 维度 | 评估 |
|:-----|:-----|
| 模板体积 | 无新增Agent模板 |
| 输出模式 | 无需改动（已有JSON输出） |
| API调用 | P2+P4每次检查+3次HTTP(已有)，无新增API |
| 健康文件 | 每文件~200B，3文件共计~600B，可忽略 |
| BOM修复 | 减少`utf-8-sig`兼容代码，净减token消耗 |

**结论**：Token影响可忽略。无新增LLM调用，无新增Agent。

## 五、需求→代码核对清单

- [ ] `health_check.py` 增加 `--persist` 参数
- [ ] `health_check.py` 增加 `hourly` mode
- [ ] `.tencent_health.json` 生成逻辑
- [ ] `.eastmoney_health.json` 生成逻辑
- [ ] `.sina_health.json` Schema升级（增加TTL/Status字段）
- [ ] 3个JSON文件BOM移除
- [ ] `engine/engine.py` utf-8-sig → utf-8 (2处)
- [ ] 写入端确认无BOM
- [ ] 玉夜巡检验证三源健康文件存在且新鲜

## 六、代码分级

| 文件 | 等级 | 理由 |
|:-----|:----:|:-----|
| `health_check.py` | L0 | 工具/监控，不参与评分/交易决策 |
| `.tencent_health.json` | L0 | 数据文件 |
| `.eastmoney_health.json` | L0 | 数据文件 |
| `engine/engine.py` | L1 | 编码修正，不改变逻辑 |

---

> **闸门1a准备就绪** — 待腰子确认finance维度影响后流入阶段③。
