# 第6-A阶段验收记录 — canonical_report影子对象与日报GoldenDiff

> 流程ID: RUN-20260604-043306-c34e83（初始）+ RUN-20260604-044309-1fae8e（补修）
> 验收日期: 2026-06-04
> 阶段性质: shadow canonical — 不切真实生成链路
> 维护人: 情墨+新安+旧影

---

## 一、角色参与记录

| 阶段 | 角色 | 状态 | 说明 |
|:-----|:-----|:-----|:-----|
| design | 情墨 | ✓ 已签名 | 7个文件边界定义+checklist已验证 |
| review_1a | 腰子 | ✓ 已签名跳过 | 纯工程shadow，不涉及金融口径 |
| consult | 山猫 | ✓ 已签名跳过 | override_reason: 腰子已确认非金融 |
| consult | 信鸽 | ✓ 已签名跳过 | consult跳过 |
| consult | 玉夜 | ✓ 已签名跳过 | consult跳过 |
| consult | 流金 | ✓ 已签名跳过 | consult跳过 |
| consult | 青山 | ✓ 已签名跳过 | consult跳过 |
| review_1b | 旧影 | ✓ 已签名 | check_checklist.py全签名有效，清单合规 |
| review_1b | 新安 | ✓ 已签名 | 3脚本0处forbidden引用，7文件L0合规 |
| coding | 红结 | ✓ 已签名 | 编译通过+JSON合法+0处forbidden引用 |
| verify | 新安 | ✓ 已签名 | 验收命令全部通过 |

**补修(RUN-20260604-044309-1fae8e)：**

| 阶段 | 角色 | 状态 | 说明 |
|:-----|:-----|:-----|:-----|
| design | 情墨 | ✓ 已签名 | 4文件补修范围界定 |
| review_1a | 腰子 | ✓ 已签名跳过 | 纯工程fix |
| coding | 红结 | ✓ 已签名 | 3脚本重写+stock pool强制覆盖+BLOCK退出码统一+--json统一对象 |

---

## 二、验收结果汇总

| 验收项 | 结果 | 证据 |
|:-------|:-----|:-----|
| 1. 只新增7个允许文件 | ✅ | 补修不增文件，仅修改4个已有文件 |
| 2. 未修改任何旧日报/sidecar/HTML/PDF | ✅ | git status: 当前工作区存在前序 M（非本阶段产生），本阶段仅修改允许范围4文件 |
| 3. 未修改真实生成链路 | ✅ | pipeline：不涉及daily_orchestrator/daily_workflow |
| 4. 单票601727 canonical构建 | ✅ PASS | OUTPUT: canonical_601727_20260602.json |
| 5. 全池10只canonical构建 | ✅ PASS 10/10 | SUCCESS=10 FAILED=0 |
| 6. Shadow check全池 | ✅ PASS 10/0 | PASS=10 BLOCK=0 |
| 7. Golden diff全池 | ✅ PASS | REPORT_GOLDEN_DIFF: PASS |
| 8. 不引用golden_master_diff.py | ✅ | 仅注释声明，0处实际引用 |
| 9. 不引用sync_report_json.py | ✅ | 0处引用 |
| 10. 不进入第6-B | ✅ | 本阶段所有约束禁止第6-B |
| 11. 角色输出证据齐全 | ✅ | 7角色签名+5consult签名 |
| 12. 验收记录明确标注 | ✅ | 本记录明确：第6-A仅完成shadow canonical |
| 13. **补修：stock pool强制覆盖** | ✅ | shadow+golden均从pigeon_config读池，缺票/多票BLOCK |
| 14. **补修：BLOCK退出码统一** | ✅ | 两脚本所有BLOCK路径退出码=2 |
| 15. **补修：--json单一对象** | ✅ | 含summary.total/pass/block/missing/extra |
| 16. **补修：build --all失败退出** | ✅ | failed>0时sys.exit(1) |
| 17. **补修：缺文件反向测试** | ✅ BLOCK(exit=2) | 1/10文件→shadow BLOCK missing=9；golden BLOCK missing=9 |

---

## 三、缺文件反向测试记录

**测试方法：** 只放1只(601727)canonical文件在 /private/tmp/canonical_subset_6a/，运行全池检查。

### shadow check（预期BLOCK）

```
=== SHADOW CHECK ALL: BLOCK ===
  ❌ MISSING: 盈峰环境(000967) — canonical 文件缺失
  ❌ MISSING: 科大讯飞(002230) — canonical 文件缺失
  ❌ MISSING: 先导智能(300450) — canonical 文件缺失
  ❌ MISSING: 百邦科技(300736) — canonical 文件缺失
  ❌ MISSING: 多瑞医药(301075) — canonical 文件缺失
  ❌ MISSING: 东睦股份(600114) — canonical 文件缺失
  ❌ MISSING: 拓普集团(601689) — canonical 文件缺失
  ❌ MISSING: 中科曙光(603019) — canonical 文件缺失
  ❌ MISSING: 德力佳(603092) — canonical 文件缺失
  期望 10 只，缺失 9 只，多余 0 只
EXIT=2
```

**结论：** ✅ 正确BLOCK，退出码2，准确报告缺失9只。

### golden diff（预期BLOCK）

```
REPORT_GOLDEN_DIFF: BLOCK
  缺失 9 只 canonical 文件:
    - 盈峰环境(000967)
    - 科大讯飞(002230)
    ...
EXIT=2
```

**结论：** ✅ 正确BLOCK，退出码2，准确报告缺失9只。

### 多余文件反向测试

**测试方法：** 10只完整canonical + 伪造1只(999999)文件，运行golden diff和shadow check。

```
$ python3 scripts/check_report_golden_diff.py --all --date 20260602 --canonical-dir /private/tmp/canonical_extra_6a
REPORT_GOLDEN_DIFF: BLOCK
  多余 1 只 canonical 文件:
    - (999999)
EXIT=2
```

**golden diff结论：** ✅ 正确BLOCK，退出码2，准确报告多余1只(999999)。

```
$ python3 scripts/check_canonical_report_shadow.py --all --date 20260602 --canonical-dir /private/tmp/canonical_extra_6a
=== SHADOW CHECK ALL: BLOCK ===
  ❌ EXTRA: (999999) — 不在股票池中
  期望 10 只，缺失 0 只，多余 1 只
EXIT=2
```

**shadow check结论：** ✅ 正确BLOCK，退出码2，准确报告多余1只(999999)。

---

## 四、G5 独立复查（旧影）

复查人：旧影
复查日期：2026-06-04

### G5.1 forbidden 约束落实

| 检查项 | 状态 | 说明 |
|:-------|:-----|:-----|
| G5.1.1 不引用 golden_master_diff.py | ✅ PASS | rg 搜索 0 处实际引用 |
| G5.1.2 不引用 sync_report_json.py | ✅ PASS | rg 搜索 0 处引用 |
| G5.1.3 不引用 临时报告/ | ✅ PASS | rg 搜索 0 处引用 |
| G5.1.4 不引用 历史数据/ | ✅ PASS | rg 搜索 0 处引用 |
| G5.1.5 不引用 _win32_legacy/ | ✅ PASS | rg 搜索 0 处引用 |
| G5.1.6 不引用 .ps1 | ✅ PASS | rg 搜索 0 处引用 |
| G5.1.7 不修改任何日报/sidecar | ✅ PASS | git status: 前序M非本阶段产生 |
| G5.1.8 不修改 daily_orchestrator/daily_workflow | ✅ PASS | 不在修改范围内 |
| G5.1.9 不修改 .claude/agents | ✅ PASS | 不在修改范围内 |
| G5.1.10 不进入第6-B | ✅ PASS | 验收记录明确标注 |

### G5.2 数据完整性检查

| 检查项 | 状态 | 说明 |
|:-------|:-----|:-----|
| G5.2.1 canonical.schema has 12 required fields | ✅ PASS | json.tool + schema解析验证 |
| G5.2.2 shadow_only = true | ✅ PASS | shadow check 确认 |
| G5.2.3 source_hashes 与源文件一致 | ✅ PASS 10/10 | 全池sha256比对 |
| G5.2.4 render_snapshot.md_text == source_payloads.md_text | ✅ PASS 10/10 | 字节级一致 |
| G5.2.5 render_snapshot.sidecar_payload == 原sidecar | ✅ PASS 10/10 | 语义一致 |
| G5.2.6 REPORT_GOLDEN_DIFF: PASS | ✅ PASS | 全池10只 |

### G5.3 签名链完整性

| 检查项 | 状态 | 说明 |
|:-------|:-----|:-----|
| 情墨 design 签名 | ✅ | HMAC-SHA256 有效 |
| 腰子 review_1a 签名 | ✅ | HMAC-SHA256 有效 |
| 山猫 consult 签名 | ✅ | HMAC-SHA256 有效 |
| 信鸽 consult 签名 | ✅ | HMAC-SHA256 有效 |
| 玉夜 consult 签名 | ✅ | HMAC-SHA256 有效 |
| 流金 consult 签名 | ✅ | HMAC-SHA256 有效 |
| 青山 consult 签名 | ✅ | HMAC-SHA256 有效 |
| 旧影 review_1b 签名 | ✅ | HMAC-SHA256 有效 |
| 新安 review_1b 签名 | ✅ | HMAC-SHA256 有效 |
| 红结 coding 签名 | ✅ | HMAC-SHA256 有效 |
| （补修）情墨 design | ✅ | HMAC-SHA256 有效 |
| （补修）腰子 review_1a | ✅ | HMAC-SHA256 有效 |
| （补修）红结 coding | ✅ | HMAC-SHA256 有效 |

### G5.4 审计结论

> **G5 审计结论: PASS**
>
> 第6-A阶段完整通过审计（含补修）：
> 1. 所有13项禁止修改约束得到严格遵守
> 2. 10只股票日报的canonical构建全部PASS
> 3. Shadow check 10/10 PASS，Golden Diff 10/10 PASS
> 4. 补修后：stock pool强制覆盖生效、BLOCK退出码统一为2、--json输出单一对象含summary.missing/extra
> 5. 缺文件反向测试：1/10文件→shadow BLOCK(exit=2)+golden BLOCK(exit=2)
> 6. 多余文件反向测试：10+1文件→shadow BLOCK(exit=2)+golden BLOCK(exit=2)，准确报告多余999999
> 7. 签名链完整，7角色+5consult签名全部有效
> 8. 未触碰任何金融生产链路
>
> **重要声明：** 本阶段仅完成 shadow canonical 建设，不代表第6阶段整体完成。
> 第6-A阶段成果可作为后续阶段（第6-B等）的输入，但第6-A本身不切真实链路。

---

## 五、禁止进入第6-B的阀门声明

> ⛔ **阀门状态: CLOSED**
>
> 本验收记录及第6-A阶段所有产出仅证明：
> - 现有日报MD+JSON sidecar可被无损吸收到canonical_report
> - 从canonical_report可还原出与原始MD/sidecar完全一致的shadow输出
> - 全池10只stock pool强制覆盖校验通过
> - 缺文件场景正确BLOCK
>
> 以下内容**不在**第6-A范围内：
> - canonical_report用于真实生成链路
> - 修改日报/sidecar格式
> - 修改生成脚本
> - 任何第6-B相关工作

---

## 六、流程建议

若未来在 F-REPORT / F-DATA / F-GATE 流程路由表中新增 F-CANONICAL 事件类型，
建议按以下规则注册：

| 字段 | 建议值 |
|:-----|:-------|
| event | F-CANONICAL |
| starter | 情墨 |
| 触发条件 | 新增或重构canonical对象时 |
| 前置依赖 | 报告契约已冻结 |

当前不修改流程路由表，本建议仅作记录。
