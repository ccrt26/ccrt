# 设计文档：重点股票名单统一配置

> **pipeline_stage**: complete | **日期**: 2026-05-29 | **设计师**: 情墨
> **变更等级**: L1（工具/配置层，不涉及评分/交易/风控逻辑）

---

## 一、问题诊断

重点股票名单在项目中 **8 处独立定义**，缺乏单一权威来源。`sim_trading.py` CODE_MAP（6只）与日报 skill/评估数据（8只）不一致，导致：
- 模拟交易无法覆盖上海电气/科大讯飞/德力佳
- 招商银行虽退出重点池但仍残留在 CODE_MAP 中

## 二、设计方案

### 2.1 新增：权威配置文件

```
代码文件/数据/key_stocks.json
```

```json
{
  "version": "1.0",
  "last_updated": "2026-05-29",
  "description": "重点股票核心观察池——权威名单，单一真相来源",
  "stocks": [
    {"code": "600114", "name": "东睦股份", "market": "sh", "board": "main", "industry": "汽车/机械"},
    {"code": "601727", "name": "上海电气", "market": "sh", "board": "main", "industry": "电气设备"},
    {"code": "603019", "name": "中科曙光", "market": "sh", "board": "main", "industry": "计算机/服务器"},
    {"code": "301075", "name": "多瑞医药", "market": "sz", "board": "chiNext", "industry": "医药"},
    {"code": "601689", "name": "拓普集团", "market": "sh", "board": "main", "industry": "汽车零部件"},
    {"code": "000967", "name": "盈峰环境", "market": "sz", "board": "main", "industry": "环保"},
    {"code": "002230", "name": "科大讯飞", "market": "sz", "board": "main", "industry": "AI/软件"},
    {"code": "603092", "name": "德力佳", "market": "sh", "board": "main", "industry": "风电/机械"}
  ]
}
```

### 2.2 修改：sim_trading.py CODE_MAP

当前（硬编码6只）→ 改为从 `key_stocks.json` 动态加载：

```python
def load_key_stocks(root_dir):
    config_path = os.path.join(root_dir, "代码文件", "数据", "key_stocks.json")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["code"]: {"Market": s["market"], "Name": s["name"], "Board": s["board"]}
            for s in data["stocks"]}
```

### 2.3 修改：batch_gen_keystock_pdfs.py

当前硬编码 STOCKS 列表 → 改为从 `key_stocks.json` 读取。

### 2.4 契约

| 消费者 | 读取方式 | 字段依赖 |
|:-----|:-----|:-----|
| sim_trading.py | `load_key_stocks()` | code, market, name, board |
| batch_gen_keystock_pdfs.py | 直接读 JSON | code, name |
| 日报 skill | 手动维护（表格） | 需与 key_stocks.json 保持同步 |
| 信鸽 pigeon_config.json | 独立维护 | 覆盖范围更大（10只），是 key_stocks 的超集 |

### 2.5 不变的部分

- `core_stocks.json`（55只每日荐股候选池）→ 不动，职责不同
- `pigeon_config.json`（10只事件采集）→ 不动，百邦/先导是新增监控标的
- 日报 skill 表格 → 不动，但后续需确保与 key_stocks.json 一致

## 三、影响范围

| 文件 | 操作 | 风险 |
|:-----|:-----|:-----|
| `代码文件/数据/key_stocks.json` | 新增 | 无 |
| `模拟交易/交易引擎/sim_trading.py` | 修改 ~10行 | 低（CODE_MAP 替换为函数调用） |
| `代码文件/tools/batch_gen_keystock_pdfs.py` | 修改 ~5行 | 低 |

## 四、Token 影响评估

- 新增文件 1 个（key_stocks.json，~1KB）
- 修改文件 2 个，合计变更 ≤ 20 行
- 无新增依赖，无 API 调用增加
- Token 影响：**0**（运行时无额外 API 调用，仅文件读取）

## 五、需求→代码核对清单

- [ ] key_stocks.json 包含 8 只股票，字段完整
- [ ] sim_trading.py CODE_MAP 从硬编码改为读取 key_stocks.json
- [ ] batch_gen_keystock_pdfs.py 从硬编码改为读取 key_stocks.json
- [ ] 旧 6 只 CODE_MAP 中的招商银行(600036)不再出现
- [ ] 新 3 只（上海电气/科大讯飞/德力佳）可被引擎正常识别
- [ ] 引擎 --date 任意日期运行时不再因 CODE_MAP 缺失而跳过标的
