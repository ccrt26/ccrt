# 红枫 · 部署记录 — data_final僵尸文件修复

**部署日期**: 2026-05-27
**部署类型**: L0 热修复（无需重启）
**部署结果**: gate: PASS

---

## 变更清单

| 文件 | 变更 | SHA256(前8) |
|:-----|:-----|:-----------|
| `engine/__init__.py` | +1行 FINAL_FILE路径 | 新增 |
| `engine/engine.py` | +12行 data_final生成逻辑 | 修改 |
| `inspect_data_health.py` | data_final_optimized 必选→可选 | 修改 |

## 生效方式

无需重启。下次 `daily_workflow.ps1 -Mode daily` 运行时，scoring_engine_v2.py 将自动产出与 data_scored 一致的 data_final.json。

## 回滚方案

```bash
git checkout HEAD~1 -- 代码文件/每日荐股/分析逻辑/engine/__init__.py
git checkout HEAD~1 -- 代码文件/每日荐股/分析逻辑/engine/engine.py
git checkout HEAD~1 -- inspect_data_health.py
```

回滚影响：data_final.json 恢复为僵尸文件状态，巡检恢复为4天WARN。

## 验证确认

- [x] 评分引擎运行通过
- [x] data_final 与 data_scored 一致性 100%
- [x] 巡检 PASS+1 / WARN-1
- [x] 历史数据4天全部修复
