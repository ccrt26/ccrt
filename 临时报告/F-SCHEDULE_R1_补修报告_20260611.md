# F-SCHEDULE-R1 补修报告

生成时间：2026-06-11T16:03:13.883145

## 修复项

1. **Fix #1 — 交易日调度修复**: `pigeon`、`daily_signal`、`post_eval`、`sim_trading` 四个
   任务的 launchd StartCalendarInterval 从单个 `Weekday: 1` 改为周一至周五 5 个 interval
   (Weekday 1,2,3,4,5)，使用 `weekday_schedules()` 辅助函数生成。

2. **Fix #2 — scheduler_health**: schedule 改为 `[{"Minute": 3}, {"Minute": 33}]`，
   :03 和 :33 均保留在 plist 中，不再依赖 extra_schedules 机制。

3. **Fix #3 — C12 闸门**: 
   - 禁止使用 `label.endswith("")` 空字符串误匹配
   - 改为 `ALLOWED_PLIST_LABELS` 严格白名单（9 个允许的 com.tielv.* label）
   - 每个 plist 必须 label 在白名单中，且 registry 中有对应 `label_suffix` 字段
   - `com.tielv.caffeinate` 不在白名单中，出现即 BLOCK

4. **Fix #4 — caffeinate 处理**:
   - 已卸载 launchd 服务
   - 已归档至 `临时报告/com.tielv.caffeinate.plist.disabled_20260611`

5. **Fix #5 — 超范围文件恢复**:
   - `git restore -- 临时报告/git_autocommit.log` 已执行

6. **Fix #6 — generate_plist() 支持 list schedule**: 当 `schedule` 为 list 时直接作为
   StartCalendarInterval；为 dict 时包装为单元素 list。同时更新 list_tasks() 和 show_status()
   以正确显示多 interval 调度。

## 验证结果

- runtime gate: **PASS** (C1-C12 全部通过，无 caffeinate 误匹配)
- crontab: 已清空
- launchd: 9 个 com.tielv.* 服务运行中，无 caffeinate
- 所有交易日任务 plist 包含 Weekday 1,2,3,4,5
- scheduler_health plist 包含 :03 和 :33 两个 interval
- git status: 只包含允许修改范围文件 + R1 产物

## 待复查

交给 Codex 执行 G5 复查。
