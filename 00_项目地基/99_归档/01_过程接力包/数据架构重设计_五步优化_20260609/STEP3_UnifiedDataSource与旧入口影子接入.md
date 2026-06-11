# STEP3：UnifiedDataSource 与旧入口影子接入

> 本步骤把 D04 接入运行链路，但只允许 shadow 或 dual-write 验证。禁止 guarded cutover，除非用户另行启动切换阶段。

---

## 新会话启动命令

```text
阿黑，按照标准流程执行：STEP3 UnifiedDataSource 与旧入口影子接入。

前置要求：STEP2 已 PASS。只允许新增/适配 UnifiedDataSource、旧入口适配器、shadow/dual-write 验证和回归测试；禁止直接让正式日报/深度分析以 D04 为唯一输入，禁止生产切换。
```

---

## 本步骤目标

建立统一访问接口，并验证它与旧链路输出一致。

核心目标：

1. 新增 `代码文件/数据/unified_data_source.py`。
2. 旧 `CachedDataSource` 明确适配或保留范围。
3. `daily_workflow.py` 只做 shadow/dual-write，不改变真实输出。
4. numeric/freshness 闸门支持新旧权威路径比对。
5. 生成 Golden Diff / shadow diff 报告。
6. fallback 链路有测试。

---

## 前置检查

必须确认：

1. `STEP2_D04数据层建设报告.md` 存在并 PASS。
2. L2 dry-run/build/update/health 已可执行。
3. STEP2 明确了 L2 DB 路径、哨兵路径、备份路径。
4. STEP1 已明确旧闸门过渡策略。

缺失则 BLOCK。

---

## 必须读取

1. 本文件
2. STEP1/STEP2 交付物
3. `代码文件/lib/cached_data_source.py`
4. `代码文件/每日荐股/scripts/batch_data_collector.py`
5. `代码文件/每日荐股/scripts/daily_workflow.py`
6. `scripts/check_numeric_source_consistency.py`
7. `scripts/check_freshness_degradation.py`
8. `scripts/check_daily_data_chain_health.py`
9. `scripts/golden_master_diff.py` 或现有 Golden Diff 脚本
10. `00_项目地基/03_报告对象/canonical_report.schema.json`

---

## 允许修改范围

1. 新增 `代码文件/数据/unified_data_source.py`
2. `代码文件/lib/cached_data_source.py`
3. `代码文件/每日荐股/scripts/batch_data_collector.py`
4. `代码文件/每日荐股/scripts/daily_workflow.py`
5. `scripts/check_numeric_source_consistency.py`
6. `scripts/check_freshness_degradation.py`
7. `scripts/check_daily_data_chain_health.py`
8. 新增 `tests/test_d04_*.py`
9. 新增 shadow/golden diff 辅助脚本
10. `00_项目地基/02_数据架构重设计/五步优化接力包/STEP3_*.md`

---

## 禁止修改范围

1. 禁止修改正式报告输出目录。
2. 禁止让 D04 成为唯一生产输入。
3. 禁止删除旧缓存。
4. 禁止修改金融分析规则。
5. 禁止绕过 numeric/freshness 闸门。

---

## 必须完成任务

1. UnifiedDataSource 返回格式统一：外层含 `data_source`、`requested_at`、`status`。
2. 支持 `get_quote`、`get_kline`、`get_score_history`、`get_financials`、`get_macro`。
3. 计算型接口只读取预计算结果或标注 deprecated/redirect，不在 D04 扩张。
4. 支持 L1 fallback、L2 哨兵异常降级、L3 重建状态查询。
5. `CachedDataSource` 改为适配器或保留兼容说明。
6. `daily_workflow.py` 增加 shadow 记录，不改变正式输出。
7. 闸门脚本能按 STEP1 的新权威关系校验。
8. 加 fallback 回归测试。
9. 加 Golden Diff 或 shadow diff 验证。
10. 输出 E3 guarded-cutover 前置条件，但本步骤不得切换。

---

## 验收命令

至少执行：

```bash
python3 -m py_compile 代码文件/数据/unified_data_source.py
python3 -m py_compile 代码文件/lib/cached_data_source.py
python3 -m py_compile 代码文件/每日荐股/scripts/batch_data_collector.py
python3 -m py_compile 代码文件/每日荐股/scripts/daily_workflow.py
python3 -m py_compile scripts/check_numeric_source_consistency.py
python3 -m py_compile scripts/check_freshness_degradation.py
python3 -m py_compile scripts/check_daily_data_chain_health.py
pytest tests/test_d04_*.py -q
python3 scripts/check_numeric_source_consistency.py --all --date <最近交易日> --json
python3 scripts/check_freshness_degradation.py --all --date <最近交易日> --json
git status --short -- 代码文件/数据/unified_data_source.py 代码文件/lib/cached_data_source.py 代码文件/每日荐股/scripts scripts tests 00_项目地基/02_数据架构重设计/五步优化接力包
```

如果没有 pytest 环境，必须说明并用等价脚本验证 fallback。

---

## 交付物

1. `STEP3_UnifiedDataSource影子接入报告.md`
2. `STEP3_旧入口适配矩阵.md`
3. `STEP3_闸门同步验证报告.md`
4. `STEP3_GoldenDiff或ShadowDiff报告.md`
5. `STEP3_验收命令结果.md`
6. `STEP4_准入检查清单.md`

---

## 通过条件

1. UnifiedDataSource 可用但未切生产。
2. 旧入口有清晰适配状态。
3. 闸门能识别新权威链路。
4. fallback 测试通过。
5. Golden/shadow diff 无阻断问题。
6. 旧影复查 PASS 或 WARN 可接受。
7. 用户确认进入 STEP4。

