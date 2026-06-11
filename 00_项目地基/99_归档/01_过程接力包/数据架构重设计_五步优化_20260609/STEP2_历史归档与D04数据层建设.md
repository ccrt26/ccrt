# STEP2：历史归档与 D04 数据层建设

> 本步骤开始做最小工程实现：先保证 L3 可保留、L2 可构建、可更新、可校验、可恢复。仍不切报告生产链路。

---

## 新会话启动命令

```text
阿黑，按照标准流程执行：STEP2 历史归档与 D04 数据层建设。

前置要求：STEP1 已 PASS。只允许实现 L3 归档保留、L2 SQLite 构建/更新/校验/备份/哨兵相关的最小脚本；禁止让日报/深度分析直接依赖新 D04，禁止生产切换。
```

---

## 本步骤目标

建立 D04 的数据基础设施：

1. L3 冷归档不再被 90 天清理误删。
2. L3 按年目录或 STEP1 冻结的结构归档。
3. L2 SQLite schema 落地。
4. 支持一次性构建、每日增量、历史回填。
5. 支持健康检查、checksum、哨兵、备份、恢复。
6. 支持从 L3 重建关键历史表。

---

## 前置检查

必须确认：

1. `STEP1_地基契约落地报告.md` 存在。
2. `STEP2_准入检查清单.md` 存在且 PASS。
3. D04 schema 字段已冻结。
4. `.gitignore` 对 L2 DB、WAL、备份策略已有明确方案。

若缺失，必须 BLOCK。

---

## 必须读取

1. 本文件
2. STEP1 交付物
3. `代码文件/每日荐股/scripts/archive_data.py`
4. `代码文件/每日荐股/scripts/daily_workflow.py`
5. `scripts/materialize_daily_authoritative_cache.py`
6. `代码文件/数据/score_history.schema.md`
7. `.gitignore`
8. `00_项目地基/02_数据架构重设计/数据分层架构_v2.8_设计提案.md` 中 L2/L3/运维章节

---

## 允许修改范围

1. `代码文件/每日荐股/scripts/archive_data.py`
2. 新增 `scripts/build_l2_cache.py`
3. 新增 `scripts/update_l2_cache.py`
4. 新增 `scripts/rebuild_score_history.py`
5. 新增 `scripts/migrate_historical_kline.py`
6. 新增 `scripts/check_d04_health.py` 或 `.sh`
7. 新增 `代码文件/数据/l2_cache/.gitkeep`
8. `.gitignore`
9. `00_项目地基/02_数据架构重设计/五步优化接力包/STEP2_*.md`

如需修改其他文件，必须先说明原因并等待用户确认。

---

## 禁止修改范围

1. 禁止修改日报/深度分析生成器以读取 D04。
2. 禁止修改报告正式产物。
3. 禁止删除历史归档文件。
4. 禁止 destructive git 操作。
5. 禁止把 L2 DB 主文件默认提交进 git，除非 STEP1 明确要求。

---

## 必须完成任务

1. `archive_data.py` 去除或绕开 90 天清理对 D04/L3 关键归档的影响。
2. 明确归档目录结构和 manifest/hash 记录。
3. 实现 L2 schema 创建。
4. 实现一次性 build，支持断点重续。
5. 实现每日 update，支持 quality_priority 幂等覆盖。
6. 实现 score_history 从 L3 重建。
7. 实现 K 线历史迁移。
8. 实现哨兵文件和 operation log。
9. 实现备份和 integrity check。
10. 输出不会切生产的证明。

---

## 验收命令

至少执行：

```bash
python3 -m py_compile 代码文件/每日荐股/scripts/archive_data.py
python3 -m py_compile scripts/build_l2_cache.py
python3 -m py_compile scripts/update_l2_cache.py
python3 -m py_compile scripts/rebuild_score_history.py
python3 -m py_compile scripts/migrate_historical_kline.py
python3 -m py_compile scripts/check_d04_health.py
python3 scripts/check_d04_health.py --dry-run
python3 scripts/build_l2_cache.py --dry-run
python3 scripts/update_l2_cache.py --dry-run
git status --short -- 代码文件/每日荐股/scripts/archive_data.py scripts .gitignore 代码文件/数据/l2_cache 00_项目地基/02_数据架构重设计/五步优化接力包
```

如脚本不支持 `--dry-run`，必须先增加 dry-run，不允许直接实写真实数据。

---

## 交付物

1. `STEP2_D04数据层建设报告.md`
2. `STEP2_修改文件清单.md`
3. `STEP2_验收命令结果.md`
4. `STEP2_不切生产证明.md`
5. `STEP3_准入检查清单.md`

---

## 通过条件

1. L3 关键归档不会被 90 天清理误删。
2. L2 schema 可以 dry-run 创建。
3. build/update/rebuild/migrate/health 脚本可编译。
4. health dry-run 可执行。
5. 未切换报告生产链路。
6. 旧影复查 PASS 或 WARN 可接受。
7. 用户确认进入 STEP3。

