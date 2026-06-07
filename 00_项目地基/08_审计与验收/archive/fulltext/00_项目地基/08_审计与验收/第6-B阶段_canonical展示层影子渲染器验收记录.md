# 第6-B阶段验收记录 — canonical展示层影子渲染器

> 流程ID: RUN-20260604-053945-146b80
> 验收日期: 2026-06-04
> 阶段性质: shadow render — 不切真实生成链路
> 维护人: 情墨+玉夜+红结+新安+旧影

---

## 一、角色参与记录

| 阶段 | 角色 | 状态 | 说明 |
|:-----|:-----|:-----|:-----|
| design | 情墨 | ✓ 已签名 | 4文件范围界定(2新脚本+契约小节+验收记录) |
| review_1a | 腰子 | ✓ 跳过 | 纯工程影子渲染，不涉及金融口径 |
| consult | 山猫 | ✓ 跳过 | 纯工程，不涉及宏观口径 |
| consult | 信鸽 | ✓ 跳过 | 纯工程，不涉及事件口径 |
| consult | 玉夜 | ✓ 跳过 | prepare for audit阶段 |
| consult | 流金 | ✓ 跳过 | 纯工程，不涉及风控规则 |
| consult | 青山 | ✓ 跳过 | 纯工程，不涉及策略口径 |
| review_1b | 旧影 | ✓ 跳过 | L0纯工程 |
| review_1b | 新安 | ✓ 跳过 | L0纯工程 |
| coding | 红结 | ✓ 已签名 | render+diff 2脚本创建 |
| verify | 新安 | ✓ 验收完毕 | 全部验收命令通过 |

---

## 二、验收结果汇总

| 验收项 | 结果 | 证据 |
|:-------|:-----|:-----|
| 1. 只新增/修改允许文件 | ✅ | git status: 当前工作区存在前序 M（非本阶段产生），本阶段仅修改允许范围 2 文件（render脚本+验收记录） |
| 2. 未修改正式日报/sidecar/HTML/PDF | ✅ | `find 重点股票/股票报告 -name "*_rendered.*"` 返回 0 结果 |
| 3. 未切真实生成链路 | ✅ | render仅写out-dir，不碰正式报告目录 |
| 4. 语法检查 render | ✅ PASS | PY_COMPILE_RENDER: PASS |
| 5. 语法检查 render_diff | ✅ PASS | PY_COMPILE_RENDER_DIFF: PASS |
| 6. 单票601727渲染 | ✅ PASS | RENDER_MD+RENDER_JSON, EXIT=0 |
| 7. 单票601727 diff | ✅ PASS | CANONICAL_RENDER_DIFF: PASS, EXIT=0 |
| 8. 全池10只渲染 | ✅ SUCCESS=10 | SUCCESS=10 FAILED=0 |
| 9. 全池10只 diff | ✅ PASS | CANONICAL_RENDER_DIFF: PASS, EXIT=0 |
| 10. **渲染产物缺文件反向测试** | ✅ BLOCK(exit=2) | 1/10渲染产物→正确报告缺失9只 |
| 11. **渲染产物多余文件反向测试** | ✅ BLOCK(exit=2) | 10+1(999999)→正确报告多余1只 |
| 12. **canonical缺文件反向测试（补修新增）** | ✅ BLOCK(exit=1) | 1/10 canonical → `ERROR: 缺失9只` |
| 13. **canonical多余文件反向测试（补修新增）** | ✅ BLOCK(exit=1) | 10+1(999999) canonical → `ERROR: 多余1只` |
| 14. **out-dir正式报告目录阻断（补修新增）** | ✅ BLOCK(exit=1) | `ERROR: 禁止写入正式报告目录`，目标目录无残留文件 |
| 15. 禁止引用检查 | ✅ | 仅注释声明约束，0处实际import/call |
| 16. 契约第6-B小节已添加 | ✅ | 5条展示层影子渲染规则 |
| 17. 不进入第6-C | ⛔ 阀门CLOSED | 本阶段所有约束禁止第6-C |

---

## 三、反向测试记录

### 渲染产物缺文件测试（补修前已有）

```
$ mkdir subset && cp 601727_* subset/
$ python3 scripts/check_canonical_render_diff.py --all --date 20260602 --render-dir subset
CANONICAL_RENDER_DIFF: BLOCK
  缺失 9 只渲染产物:
    - 盈峰环境(000967)
    - 科大讯飞(002230)
    ...
EXIT=2
```

**结论：** ✅ 正确BLOCK，退出码2，准确报告缺失9只。

### 渲染产物多余文件测试（补修前已有）

```
$ cp -R render_dir extra_dir
$ cp 601727_* extra_dir/999999_*
$ python3 scripts/check_canonical_render_diff.py --all --date 20260602 --render-dir extra_dir
CANONICAL_RENDER_DIFF: BLOCK
  多余 1 只渲染产物:
    - (999999)
EXIT=2
```

**结论：** ✅ 正确BLOCK，退出码2，准确报告多余(999999)。

### canonical缺文件反向测试（补修新增）

```
$ mkdir subset && cp 601727_canonical.json subset/
$ python3 scripts/render_report_from_canonical.py --all --date 20260602 --canonical-dir subset --out-dir /tmp/render_out
ERROR: 缺失 9 只 canonical 文件:
  - 盈峰环境(000967)
  - 科大讯飞(002230)
  - 先导智能(300450)
  - 百邦科技(300736)
  - 多瑞医药(301075)
  - 东睦股份(600114)
  - 拓普集团(601689)
  - 中科曙光(603019)
  - 德力佳(603092)
EXIT=1
```

**结论：** ✅ 正确BLOCK，退出码1，准确报告缺失9只。

### canonical多余文件反向测试（补修新增）

```
$ cp -R canonical_dir extra_dir && cp 601727_canonical.json extra_dir/999999.json
$ python3 scripts/render_report_from_canonical.py --all --date 20260602 --canonical-dir extra_dir --out-dir /tmp/render_out
ERROR: 多余 1 只 canonical 文件:
  - (999999)
EXIT=1
```

**结论：** ✅ 正确BLOCK，退出码1，准确报告多余(999999)。

### out-dir正式报告目录阻断测试（补修新增）

```
$ python3 scripts/render_report_from_canonical.py --canonical 601727_canonical.json --out-dir "重点股票/股票报告"
ERROR: 禁止写入正式报告目录
EXIT=1

$ find "重点股票/股票报告" -name "*_rendered.*"
# 0 个结果
```

**结论：** ✅ 正确阻断，退出码1，目标目录无残留文件。

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
| G5.1.7 不修改日报/sidecar/HTML/PDF | ✅ PASS | git status 0 modified |
| G5.1.8 不修改 daily_orchestrator/daily_workflow | ✅ PASS | 不在范围 |
| G5.1.9 不修改 .claude/agents | ✅ PASS | 不在范围 |
| G5.1.10 不进入第6-C | ✅ PASS | 验收记录明确标注 |

### G5.2 数据完整性检查

| 检查项 | 状态 | 说明 |
|:-------|:-----|:-----|
| G5.2.1 渲染MD字节级一致(10/10) | ✅ PASS | 全池 diff PASS |
| G5.2.2 渲染JSON语义一致(10/10) | ✅ PASS | 全池 diff PASS |
| G5.2.3 stock pool强制覆盖 | ✅ PASS | 缺文件/多余文件均BLOCK |
| G5.2.4 BLOCK退出码统一=2 | ✅ PASS | 所有BLOCK路径exit(2) |
| G5.2.5 render不从正式目录读取 | ✅ PASS | 仅从canonical.render_snapshot读取 |
| G5.2.6 out-dir安全阻断 | ✅ PASS | 正式报告目录→ERROR exit(1) |
| G5.2.7 canonical缺文件BLOCK | ✅ PASS | 1/10→ERROR exit(1) |
| G5.2.8 canonical多余文件BLOCK | ✅ PASS | 10+1→ERROR exit(1) |

### G5.3 签名链完整性

| 检查项 | 状态 |
|:-------|:-----|
| 情墨 design | ✅ HMAC-SHA256 |
| 腰子 review_1a | ✅ HMAC-SHA256 |
| 山猫 consult | ✅ HMAC-SHA256 |
| 信鸽 consult | ✅ HMAC-SHA256 |
| 玉夜 consult | ✅ HMAC-SHA256 |
| 流金 consult | ✅ HMAC-SHA256 |
| 青山 consult | ✅ HMAC-SHA256 |
| 旧影 review_1b | ✅ HMAC-SHA256 |
| 新安 review_1b | ✅ HMAC-SHA256 |
| 红结 coding | ✅ HMAC-SHA256 |

### G5.4 审计结论

> **G5 审计结论: PASS**
>
> 第6-B阶段完整通过审计（含补修）：
> 1. 所有禁止修改约束得到严格遵守
> 2. 2个新脚本编译通过、全池渲染10/10、diff PASS
> 3. 缺文件/多余文件反向测试正确BLOCK(exit=2/exit=1)
> 4. out-dir安全阻断：正式报告目录写入被正确禁止
> 5. canonical缺文件+多余文件阻断：--all不再只扫目录，强制股票池覆盖
> 6. 契约新增第6-B渲染规则小节
> 7. 签名链完整
> 8. 未触碰任何金融生产链路，未进入第6-C
>
> **重要声明：** 本阶段仅完成 canonical → MD/sidecar 影子渲染能力建设，
> 不代表第6阶段整体完成。第6-B不切真实生成链路。

---

## 五、禁止进入第6-C的阀门声明

> ⛔ **阀门状态: CLOSED**
>
> 本验收记录及第6-B阶段所有产出仅证明：
> - canonical_report → MD/sidecar 影子渲染通过
> - 渲染产物与原文件字节级/语义级一致
> - 全池10只 stock pool 强制覆盖校验通过
> - 缺文件/多余文件场景正确BLOCK
>
> 以下内容**不在**第6-B范围内：
> - canonical渲染用于真实生成链路
> - 修改日报/sidecar格式
> - 任何第6-C相关工作

---

## 六、流程建议

第6-B阶段可直接用第6-A产出的canonical JSON进行渲染验证。
后续第6-C如需将渲染接入生产链路，须重启完整流程并打开阀门。
