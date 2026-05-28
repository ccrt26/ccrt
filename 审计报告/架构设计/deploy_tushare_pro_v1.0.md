# 灰度部署 — Tushare Pro 数据源接入

> pipeline_stage: stage_5 | 红枫 | 2026-05-28

---

## 一、影响范围评估

| 维度 | 影响 |
|:-----|:-----|
| 新增文件 | `stock_data_fetcher_tushare.py` (363行) |
| 修改文件 | `core.ps1` (+50行, 仅追加) / `api_config.json` (+10行) |
| 现有功能 | **零影响** — 所有改动为纯追加，不修改现有函数 |
| 依赖变更 | 新增 `tushare` pip包 |
| 环境变量 | 新增 `TUSHARE_TOKEN` |
| 数据管线 | Tushare不可用时自动降级到旧源，管线不中断 |

## 二、部署步骤

### Step 1: 安装依赖
```bash
pip install tushare
```

### Step 2: 配置Token
```bash
# 购买积分后从 https://tushare.pro 获取token
export TUSHARE_TOKEN="your_token_here"
# 持久化到 ~/.zshrc 或 ~/.bash_profile
echo 'export TUSHARE_TOKEN="your_token_here"' >> ~/.zshrc
```

### Step 3: 冒烟测试
```bash
# 测试连通性
python 代码文件/每日荐股/scripts/stock_data_fetcher_tushare.py hk_hold --code 600114 --end 2026-05-28

# 测试股东人数
python 代码文件/每日荐股/scripts/stock_data_fetcher_tushare.py holder_number --code 600114

# 测试股权质押
python 代码文件/每日荐股/scripts/stock_data_fetcher_tushare.py pledge --code 600114
```

### Step 4: 验证降级链
```bash
# 临时移除token，验证自动降级到旧源
TUSHARE_TOKEN="" python 代码文件/每日荐股/scripts/stock_data_fetcher_tushare.py hk_hold --code 600114
# 预期: 返回error JSON，PowerShell侧自动fallback到东方财富[8]
```

## 三、灰度策略

| 阶段 | 范围 | 时长 | 验收标准 |
|:----:|:-----|:----:|:--------|
| Gray-1 | 单股票(600114)冒烟 | 即时 | hk_hold/pledge/holder_number 三个action返回有效数据 |
| Gray-2 | 全部7只重点股票 | 3天 | 降级链0触发，数据字段完整率100% |
| Full | 全量放开 | — | 稳定性运行1周无异常 |

## 四、回滚方案

```
回滚触发条件:
  - Tushare连续3次调用失败
  - 返回数据字段缺失率 > 20%
  - token过期/积分不足

回滚操作:
  1. unset TUSHARE_TOKEN 或删除环境变量
  2. SourceRegistry会自动降级到旧源（东财/新浪）
  3. 无需代码回滚 — 降级链设计保证了自动切换

代码级回滚（如需彻底移除）:
  git checkout -- 代码文件/每日荐股/scripts/modules/core.ps1
  git checkout -- 代码文件/config/api_config.json
  rm 代码文件/每日荐股/scripts/stock_data_fetcher_tushare.py
```

## 五、监控指标

| 指标 | 阈值 | 告警 |
|:-----|:----:|:-----|
| Tushare调用成功率 | >95% | <95% → 检查token/积分 |
| 降级触发次数/天 | <5次 | >5次 → 检查Tushare服务状态 |
| 单次调用耗时 | <3s | >3s → 检查网络/限速 |

---

## 部署结论：READY — 等待用户购买积分后执行 Step 1-3
