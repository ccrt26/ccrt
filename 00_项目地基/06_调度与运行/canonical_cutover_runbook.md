# canonical 生产切换运行手册（Runbook）

> 版本: 1.0 | 生效日期: 2026-06-04 | 维护人: 情墨+红结+新安+阿黑
>
> 第6-D阶段产物 — 第6-E执行的操作手册。

---

## 一、第6-E执行前检查清单

第6-E启动前，先跑准入清单：

```bash
# 1. 验收记录存在
test -f 00_项目地基/08_审计与验收/第6-A阶段_canonical影子对象与日报GoldenDiff验收记录.md
test -f 00_项目地基/08_审计与验收/第6-B阶段_canonical展示层影子渲染器验收记录.md
test -f 00_项目地基/08_审计与验收/第6-C阶段_canonical发布前总闸门验收记录.md
test -f 00_项目地基/01_数据契约/canonical_cutover_contract.md
test -f 00_项目地基/06_调度与运行/canonical_cutover_runbook.md

# 2. 验收结论 grep
rg "G5 审计结论: PASS" 00_项目地基/08_审计与验收/第6-A阶段*
rg "G5 审计结论: PASS" 00_项目地基/08_审计与验收/第6-B阶段*
rg "G5 审计结论: PASS" 00_项目地基/08_审计与验收/第6-C阶段*
```

全部 PASS 后才可进入第6-E。

---

## 二、E1 shadow-only 执行步骤

**目标**：canonical 只旁路生成，不影响正式输出。

```bash
# 1. 构建 canonical
python3 scripts/build_canonical_report.py --all --date {target_date} --out-dir /private/tmp/canonical_reports_{target_date}

# 2. 跑总闸门
python3 scripts/check_canonical_pipeline_gate.py --date {target_date} --canonical-dir /private/tmp/canonical_reports_{target_date} --render-dir /private/tmp/canonical_render_{target_date}

# 3. 验证 PASS
# 预期：CANONICAL_PIPELINE_GATE: PASS, exit 0
```

**失败处理**：闸门 BLOCK → 检查子闸门输出 → 修复后重跑。

**通过标准**：总闸门 4/4 PASS。验证人：玉夜+新安。

---

## 三、E2 dual-write 执行步骤

**目标**：正式输出仍用旧链路，同时生成 canonical 并 diff。

```bash
# 1. 构建 canonical
python3 scripts/build_canonical_report.py --all --date {target_date} --out-dir /private/tmp/canonical_reports_{target_date}

# 2. 渲染 canonical
python3 scripts/render_report_from_canonical.py --all --date {target_date} --canonical-dir /private/tmp/canonical_reports_{target_date} --out-dir /private/tmp/canonical_render_{target_date}

# 3. 跑 render diff
python3 scripts/check_canonical_render_diff.py --all --date {target_date} --render-dir /private/tmp/canonical_render_{target_date}

# 4. 跑总闸门
python3 scripts/check_canonical_pipeline_gate.py --date {target_date} --canonical-dir /private/tmp/canonical_reports_{target_date} --render-dir /private/tmp/canonical_render_{target_date}
```

**失败处理**：
- render diff BLOCK → 检查映射规则或 canonicla 数据
- 总闸门 BLOCK → 按子闸门逐项排查

**通过标准**：diff 全池 PASS + 总闸门 PASS。验证人：玉夜+新安+旧影。

---

## 四、E3 guarded-cutover 执行步骤

**目标**：真实输出来自 canonical，保留旧链路回滚入口。

```bash
# 0. 腰子放行确认（必须先签名）
# python3 scripts/sign_off.py --actor 腰子 --role 腰子 --run-id {E3_RUN_ID} ...

# 1. 备份旧 sidecar
# 第6-E执行时由脚本化备份实现，禁止手写通配路径直接执行。
# 备份规则：按目标日期备份目标日报 sidecar，不批量乱拷历史 json。
# 备份至：重点股票/股票报告/_cutover_backup/{target_date}/
mkdir -p "重点股票/股票报告/_cutover_backup/{target_date}/"
for dir in "东睦股份(600114)" "中科曙光(603019)" "多瑞医药(301075)" "拓普集团(601689)" "盈峰环境(000967)" "上海电气(601727)" "科大讯飞(002230)" "德力佳(603092)" "百邦科技(300736)" "先导智能(300450)"; do
    cp "重点股票/股票报告/$dir"/*"日报_{target_date}.json" "重点股票/股票报告/_cutover_backup/{target_date}/"
done

# 2. 构建 canonical
python3 scripts/build_canonical_report.py --all --date {target_date} --out-dir /private/tmp/canonical_reports_{target_date}

# 3. 渲染 canonical
python3 scripts/render_report_from_canonical.py --all --date {target_date} --canonical-dir /private/tmp/canonical_reports_{target_date} --out-dir /private/tmp/canonical_render_{target_date}

# 4. 跑总闸门（最终确认）
python3 scripts/check_canonical_pipeline_gate.py --date {target_date} --canonical-dir /private/tmp/canonical_reports_{target_date} --render-dir /private/tmp/canonical_render_{target_date}

# 5. 总闸门 PASS → 正式输出
# （修改 daily_orchestrator.py 等需在第6-E通过后按标准流程执行）
```

**失败处理**：
- 闸门 BLOCK → 立即回滚（见下一节）
- 无腰子签名 → 禁止发布 E3

**通过标准**：总闸门 PASS + 腰子签名 + 旧影确认。验证人：腰子+旧影。

---

## 五、回滚步骤

| 步骤 | 命令 |
|:-----|:-----|
| 1. 停 canonical 输出 | 恢复旧链路入口配置 |
| 2. 恢复备份 | `cp -R 重点股票/股票报告/_cutover_backup/{date}/. 重点股票/股票报告/各目录/` |
| 3. 跑回归 diff | `python3 scripts/check_canonical_render_diff.py --all --date {date} --render-dir /private/tmp/canonical_render_{date}` 预期 BLOCK |
| 4. 记录回滚原因 | 写入审计日志 |
| 5. 通知全员 | 阿黑发出回滚通告 |

---

## 六、禁止操作清单

- ❌ 跳过 E1 直上 E2/E3
- ❌ E3 前不备份旧 sidecar
- ❌ 腰子未放行进入 E3
- ❌ 闸门 BLOCK 时继续发布
- ❌ 一次性 full cutover
- ❌ 修改旧链路脚本而不留回滚入口

---

## 七、一键启动句

第6-E启动时可直接使用的指令：

```
阿黑，按照标准流程启动：第6-E canonical shadow-only接入方案
阿黑，按照标准流程执行：第6-E canonical shadow-only接入
```
