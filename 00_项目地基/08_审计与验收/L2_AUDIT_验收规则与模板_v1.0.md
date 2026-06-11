# AUDIT：验收规则与模板 v1.0

> **定位：** 阶段验收规则与报告模板。整合自 `阶段验收报告模板.md`。

---

## 1. 验收规则

1. **阶段通过必须同时满足：**
   - 所有允许范围内文件已创建/修改完成
   - 所有验收命令通过
   - 未修改允许范围之外的文件
   - git status 已解释
   - 无静默失败（报告说 PASS 但命令实际失败）
   - 未跳过必须的阶段门
   - 验收报告已提交

2. **补修规则：** 同一阶段内补修，不得扩大范围，补修后重跑验收命令。

3. **git status 规则：**
   - 所有 `M` 文件必须说明修改原因
   - 所有 `??` 文件必须说明来源
   - 允许范围外的变更立即停止

---

## 2. 验收报告字段

每个阶段验收报告必须包含：

| 字段 | 说明 |
|:-----|:------|
| 阶段编号 | 如 P5、P6 |
| 目标 | 一句话说明 |
| 修改清单 | 新增/修改/删除 文件清单 |
| 验收命令结果 | 每条命令输出与结论 |
| 结论表 | 判定项 + 结果 + 证据 |
| 风险表 | 风险描述 + 等级 + 说明 |
| 阻断 | 是否阻断下一阶段 |

---

## 3. 验收命令模板

参考模板：

```text
# 通用验收命令
test -f <文件路径>
jq . <json路径>
python3 -m json.tool <json路径>
git status --short -- <关注范围>
git diff --cached --name-only
grep -n "<关键词>" <文件路径>
```

---

*本文件整合自 `阶段验收报告模板.md`。原模板已迁入 `08_审计与验收/archive/fulltext/`，历史证据见 `INDEX_审计验收归档索引_v1.0.md`。*

---

## 4. D04 数据中台常规审计接入

> 自 STEP4 起，D04 数据中台（C-D04-0001）纳入常规审计体系。

### 4.1 日检

| # | 检查项 | 命令 | 验收标准 |
|:-:|:-------|:-----|:---------|
| D-01 | D04 目录完整性 | `python3 scripts/check_d04_health.py --dry-run` | ✅ PASS（DB 缺失时 WARN 可接受） |
| D-02 | K 线 freshness（含 L2 子项） | `python3 scripts/check_freshness_degradation.py --tier l2 --json \| grep -A5 kline_l2` | ✅ L2 子项 SKIP 不阻断 |
| D-03 | Numeric 一致性（含 kline_l2） | `python3 scripts/check_numeric_source_consistency.py --json \| grep -A5 kline_l2` | ✅ kline_l2 子项 SKIP 不阻断 |

### 4.2 周检

| # | 检查项 | 命令 | 验收标准 |
|:-:|:-------|:-----|:---------|
| D-04 | UnifiedDataSource 接口连通性 | `python3 scripts/run_shadow_diff.py --all-stocks --date <最近交易日>` | ✅ ALL PASS（diff 可接受） |
| D-05 | 注册表一致性 | `python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json && python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json` | ✅ JSON 语法校验通过 |

### 4.3 月检

| # | 检查项 | 命令 | 验收标准 |
|:-:|:-------|:-----|:---------|
| D-06 | L2 备份完整性 | `python3 scripts/check_d04_health.py` | 备份文件存在且 <7 天 |
| D-07 | 五步优化状态保持 | 全部验收命令 | 全部 ⚠️ WARN 以内 |
| D-08 | 禁止范围核验 | `grep -rn "unified_data_source\|UnifiedDataSource" 代码文件/tools/daily_orchestrator.py 代码文件/每日荐股/scripts/daily_workflow.py` | ✅ 无引用 |

### 4.4 审计命令模板

```bash
# D01: D04 健康检查
python3 scripts/check_d04_health.py --dry-run

# D02: Freshness L2 子项
python3 scripts/check_freshness_degradation.py --code 600114 --name 东睦股份 --date <YYYYMMDD> --tier l2 --json | grep -A5 kline_l2

# D03: Numeric L2 子项
python3 scripts/check_numeric_source_consistency.py --code 600114 --name 东睦股份 --date <YYYYMMDD> --json | grep -A5 kline_l2

# D04: UDS 接口连通性
python3 scripts/run_shadow_diff.py --code 600114 --date <YYYYMMDD>

# D05: 注册表 JSON 校验
python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json
python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json
```
