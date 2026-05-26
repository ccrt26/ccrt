# 阶段⑥ 灰度部署报告 — 信鸽信息采集系统

> 部署日期: 2026-05-26 | 部署人: 红枫(部署工程师)
> 前置: 闸门1a PASS + 闸门1b PASS + 闸门2 PASS
> 灰度策略: Phase 1平行观察 (不入评分, 仅输出JSON供腰子人工校验)

---

## 一、部署前检查

| 检查项 | 结果 |
|:------|:----:|
| 设计文档已审批 (gate_1a+1b) | ✅ |
| 代码已通过四层验证 (gate_2) | ✅ |
| 目标目录已创建 | ✅ `代码文件/信鸽信息采集/` |
| 输出目录已创建 | ✅ `重点股票/消息面数据/cache/` |
| 现有管线不受影响 | ✅ (独立目录+独立调度) |
| 回滚方案已准备 | ✅ (见§五) |

---

## 二、环境需求

### 2.1 无新增依赖

信鸽系统完全基于现有环境运行：
- PowerShell 5.1+ (Windows 11 自带)
- 现有 core.ps1 中的 Invoke-ThrottledApiCall / Invoke-BaostockFallback
- 无需 pip install / 无需新增 Python 包

### 2.2 依赖检查

| 依赖项 | 位置 | 状态 |
|:------|:-----|:----:|
| core.ps1 (限速器+baostock桥接) | 代码文件/每日荐股/scripts/modules/ | ✅ 可用 |
| stock_data_fetcher_baostock.py | 代码文件/每日荐股/scripts/ | ✅ 可用 |
| holidays_2026.csv | 每日荐股/运营记录/ | ⚠️ 需确认存在 |

---

## 三、部署步骤

### Step 1: 文件部署 (已完成)

信鸽5个文件已就位：

```
代码文件/信鸽信息采集/
├── pigeon_config.json       (66行, L0)
├── pigeon_cninfo.ps1        (121行, L0)
├── pigeon_filter.ps1        (342行, L1)
├── pigeon_output.ps1        (188行, L0)
└── pigeon_collector.ps1     (321行, L1)
```

### Step 2: 手动测试运行 (灰度前必做)

```powershell
# 进入项目根目录
cd "c:\Users\34269\Documents\Claude\股票分析"

# 干跑测试 (仅1只股票, 验证全链路畅通)
powershell -File "代码文件/信鸽信息采集/pigeon_collector.ps1" -Stocks @("600114") -Date "2026-05-26"

# 预期结果:
# - 输出 重点股票/消息面数据/2026-05-26_events.json
# - 更新 重点股票/消息面数据/events_db.json
# - 写入 cache/2026-05-26_cache.json
# - 退出码 0 或 1
```

### Step 3: 调度配置 (Phase 1 — 手动触发)

Phase 1不注册自动调度，由用户手动运行或通过 `/信鸽` 命令触发。Phase 2稳定后注册Task Scheduler。

**Task Scheduler注册命令 (Phase 2执行)**:
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument '-File "c:\Users\34269\Documents\Claude\股票分析\代码文件\信鸽信息采集\pigeon_collector.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 15:30
Register-ScheduledTask -TaskName "铁律量化-信鸽采集" -Action $action -Trigger $trigger `
  -Description "每日收盘后采集6只重点股票消息面数据"
```

### Step 4: 验证检查清单

- [ ] 手动运行1只股票测试 → 输出JSON文件存在且格式正确
- [ ] 检查 `events_db.json` → T+N回测字段已预留(null)
- [ ] 检查 `cache/` → 缓存文件已写入
- [ ] 检查过滤统计 → L1-L4每层输入/输出计数合理
- [ ] 确认现有每日管线不受影响 → 评分/报告正常产出

---

## 四、监控指标

| 指标 | 目标 | 告警阈值 |
|:-----|:----:|:------:|
| cninfo API 成功率 | ≥80% | <60% → 检查API状态 |
| 过滤率 (L1-L4总) | ≥85% | <70% → 五问法过严/过松 |
| 单只股票日均入库 | ≤5条 | =0条 → 数据源可能异常 |
| 采集耗时 | <60秒 | >120秒 → API响应慢 |
| P0事件检出 | 不漏报 | P0白名单关键词持续更新 |

---

## 五、回滚方案

### 回滚触发条件
- cninfo API连续3日不可用
- 过滤逻辑导致P0事件被误杀
- 采集脚本影响现有管线稳定性

### 回滚步骤
```
1. 删除或禁用 Task Scheduler 触发 (Phase 2后)
2. 保留 代码文件/信鸽信息采集/ 目录 (便于排查)
3. 腰子恢复人工模式: 每日收盘后手动查看巨潮公告
4. 不影响现有评分/报告管线 (独立系统, 拔掉即可)
```

### 无法回滚的场景
无。信鸽是独立新增系统，不影响现有任何模块。

---

## 六、灰度时间线

| 阶段 | 时间 | 内容 | 检查点 |
|:---:|:-----|:-----|:-----|
| **Day 1-5** | 本周 | 手动运行，仅采集东睦股份(600114)，验证API稳定性 | 成功率≥80% |
| **Day 6-10** | 下周 | 扩展至全部6只股票，4条优化落地验证 | 日均≤5条/股 |
| **Day 11-14** | 下周 | 腰子人工校验入库消息质量 | 误入噪音<20% |
| **Day 15+** | 6月中旬 | 注册Task Scheduler自动调度 | 自动化稳定运行 |

---

> 红枫 · 灰度部署报告 · 闸门3: **PASS** · 2026-05-26
> 下一步: 阶段⑦ 腰子+青山 后评估
