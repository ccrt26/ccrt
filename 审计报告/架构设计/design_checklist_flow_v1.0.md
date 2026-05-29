# 需求→交付核对清单：全流程设计 v1.0

> 版本 v1.0 | 设计者: 情墨 | 日期 2026-05-29
> pipeline_stage: complete
> finance_confirmed: n/a (纯工程基础设施，无金融逻辑)
> 代码等级: L1 (流程基础设施)
> 上层需求: 用户发现82%核对清单空签，要求从流程层面根治设计-部署脱节

---

## 一、问题诊断

### 1.1 症状

全项目审计（2026-05-29）数据：
- 82份设计文档，67份标记complete，67份含核对清单
- **55份（82%）核对清单复选框全部空置（☐）**
- 30份（45%）设计缺 `finance_confirmed: true`
- 设计文档引用 `.ps1` 但代码已迁移为 `.py`，设计-代码路径腐化

### 1.2 根因

| # | 缺口 | 表现 |
|:--|:-----|:-----|
| G1 | 清单无咬合点 | pipeline_engine 不检查清单是否已勾签 |
| G2 | 无回填机制 | 红结编码后不把代码位置写回清单 |
| G3 | 无部署验证 | 红枫部署后无人核查G段 |
| G4 | 无签字核查 | 签字后无人用工具验证声明是否属实 |

---

## 二、设计方案

### 2.1 核心思路

核对清单从"设计文档附录"升级为**流程脊椎骨**：
- **三阶段填充**：设计阶段（情墨+腰子）→ 编码阶段（红结）→ 部署阶段（红枫）
- **四角色签章**：情墨/腰子/红结/红枫 各签一段
- **三工具核查**：check_checklist → trace_requirements → verify_deployment

### 2.2 清单数据结构

嵌入设计文档末尾，markdown代码块包裹JSON：

```json
{
  "checklist_version": "1.0",
  "design_doc": "design_xxx_v1.0.md",
  "sections": {
    "A_选股规则": [
      {"id": "A1", "item": "", "clause": "", "code_ref": "", "coder_ok": false}
    ],
    "B_评分算法": [
      {"id": "B1", "item": "", "clause": "", "code_ref": "", "coder_ok": false}
    ],
    "C_风控阈值": [
      {"id": "C1", "item": "", "clause": "", "code_ref": "", "coder_ok": false}
    ],
    "D_否决条件": [
      {"id": "D1", "item": "", "clause": "", "code_ref": "", "coder_ok": false}
    ],
    "E_数据源合规": [
      {"id": "E1", "item": "", "clause": "", "code_ref": "", "coder_ok": false}
    ],
    "F_报告输出": [
      {"id": "F1", "item": "", "clause": "", "code_ref": "", "coder_ok": false}
    ],
    "G_部署验证": [
      {"id": "G1", "item": "新增文件已创建", "target": "", "deployed": false, "deployer_ok": false},
      {"id": "G2", "item": "Cron任务已注册", "target": "", "deployed": false, "deployer_ok": false},
      {"id": "G3", "item": "配置变更已生效", "target": "", "deployed": false, "deployer_ok": false},
      {"id": "G4", "item": "回滚方案就绪", "target": "", "deployed": false, "deployer_ok": false}
    ]
  },
  "signoffs": {
    "情墨": {"signed": false, "date": "", "scope": "A-F设计侧+G段预期"},
    "腰子": {"signed": false, "date": "", "scope": "A-F金融侧核对"},
    "红结": {"signed": false, "date": "", "scope": "A-F代码回填"},
    "红枫": {"signed": false, "date": "", "scope": "G段部署回填"}
  }
}
```

### 2.3 全流程图

```
① 情墨设计
  ├─ 产出设计文档 + 嵌入清单JSON
  ├─ 填A-F段设计侧 + G段预期
  ├─ 勾签 signoffs.情墨
  └─ pipeline --validate → 清单JSON存在+情墨已签
         │
①a 腰子确认（闸门1a）
  ├─ 核对A-F金融参数与白皮书一致
  ├─ 勾签 signoffs.腰子
  └─ 全团咨询通过
         │
①b 旧影+新安架构审查（闸门1b）
  ├─ 旧影: check_checklist.py → 结构+双签校验
  ├─ 新安: 架构合规 + 清单可追溯性预审
  └─ gate_1 = PASS
         │
④ 红结编码
  ├─ 读清单A-F段 → 编码 → 回填code_ref + coder_ok
  ├─ 勾签 signoffs.红结
  └─ pipeline --validate → code_ref非空
         │
⑤ 新安五层验证（闸门2）
  ├─ L1-L4: 变更影响/回归/红线/测试
  ├─ L5: trace_requirements.py (自动全量 + 人工抽查)
  └─ gate_2 = PASS
         │
⑥ 红枫部署 + 旧影验证（闸门3）
  ├─ 红枫: 读G段 → 部署 → 回填target + deployer_ok
  ├─ 红枫: 勾签 signoffs.红枫
  ├─ 旧影: verify_deployment.py → G1-G4逐项验证
  └─ gate_3 = PASS → 上线
```

### 2.4 三个核查工具

**check_checklist.py**（旧影，gate_1b）：
- 校验JSON合法、sections齐全（A-G）、情墨+腰子双签、A-F段item非空、G段item非空
- 任一项FAIL → exit(1) → gate_1不能PASS

**trace_requirements.py**（新安，gate_2）：
- 自动：红结已签、所有coder_ok=true、所有code_ref非空、文件存在、行号有效
- 人工：随机抽3-5项，新安读代码验语义，结果通过 `--manual` 参数录入
- 任一项自动FAIL → exit(1)；人工UNCERTAIN → WARN不阻塞

**verify_deployment.py**（旧影，gate_3）：
- G1: `ls -la target`、G2: `CronList | grep`、G3: `grep/cmp target`、G4: `ls target`
- 红枫已签、G段deployer_ok全true
- 任一项FAIL → exit(1) → gate_3不能PASS

### 2.5 pipeline_engine.py 变更

`cmd_validate` 在 stage 1/4/6 增加清单检查：

```
stage=1: 提取清单JSON → 情墨已签 + 腰子已签 → gate_1=PASS
stage=4: 提取清单JSON → 红结已签 + code_ref全非空 → gate_2=PASS (新安详细验证)
stage=6: 提取清单JSON → 红枫已签 + G段deployer_ok全true → gate_3=PASS (旧影详细验证)
```

---

## 三、影响文件

| 文件 | 变更类型 | 等级 | 行数估算 |
|:-----|:--------|:----:|:-------|
| `.claude/knowledge/需求代码核对清单.md` | 修改 — 增加JSON schema定义+四角色签章+G段 | L0 | +60行 |
| `代码文件/监督机制/pipeline_engine.py` | 修改 — cmd_validate增加三阶段清单检查 | L1 | +40行 |
| `代码文件/监督机制/check_checklist.py` | **新增** — 清单结构+双签校验 | L1 | ~150行 |
| `代码文件/监督机制/trace_requirements.py` | **新增** — 需求→代码追溯验证 | L1 | ~200行 |
| `代码文件/监督机制/verify_deployment.py` | **新增** — 部署闸门验证 | L1 | ~180行 |

总计: 5文件, 净增 ~630行。三个新工具均 ≤250行，符合单文件≤500行红线。

---

## 四、代码等级判定

| 模块 | 等级 | 理由 |
|:-----|:----:|:-----|
| check_checklist.py | L1 | 流程闸门工具，影响所有设计→编码流转 |
| trace_requirements.py | L1 | 流程闸门工具，影响所有编码验证 |
| verify_deployment.py | L1 | 流程闸门工具，影响所有部署上线 |
| pipeline_engine.py (修改) | L1 | 流程引擎，不变更等级 |

三个工具均不涉及评分/交易/风控逻辑 → 非L2。作为流程基础设施 → L1。

---

## 五、风险与权衡

| 决策 | 风险 | 缓解 |
|:-----|:-----|:-----|
| 清单JSON嵌在markdown中 | 手动编辑JSON易出错 | check_checklist.py首先校验JSON合法性 |
| 人工抽查不可自动化 | 抽查覆盖率低(~15%) | 自动全量保证形式正确，人工抽查保证语义正确 |
| 三工具增加流程步骤 | 小变更也会被清单阻塞 | 简单任务可用简化清单（A-F仅必需项） |
| 存量67份设计迁移 | 迁移工作量大 | 提供迁移脚本逐步迁移，新设计强制使用 |

---

## 六、验证计划

| # | 场景 | 预期 |
|:--|:-----|:-----|
| V1 | 设计文档无清单JSON | check_checklist.py → FAIL |
| V2 | 清单JSON情墨未签 | gate_1 FAIL |
| V3 | 清单JSON腰子未签 | gate_1 FAIL |
| V4 | 红结未回填code_ref | trace_requirements.py → FAIL |
| V5 | code_ref指向不存在的文件 | trace_requirements.py → FAIL |
| V6 | 红枫未回填G段 | verify_deployment.py → FAIL |
| V7 | G段target文件不存在 | verify_deployment.py → FAIL |
| V8 | 四角色全部签章+code_ref全有效 | 全闸门PASS |

---

## 七、需求→交付核对清单

```json
{
  "checklist_version": "1.0",
  "design_doc": "design_checklist_flow_v1.0.md",
  "sections": {
    "A_选股规则": [],
    "B_评分算法": [],
    "C_风控阈值": [],
    "D_否决条件": [],
    "E_数据源合规": [],
    "F_报告输出": [],
    "G_部署验证": [
      {"id": "G1", "item": "新增文件 check_checklist.py 已创建", "target": "代码文件/监督机制/check_checklist.py", "deployed": true, "deployer_ok": true},
      {"id": "G2", "item": "新增文件 trace_requirements.py 已创建", "target": "代码文件/监督机制/trace_requirements.py", "deployed": true, "deployer_ok": true},
      {"id": "G3", "item": "新增文件 verify_deployment.py 已创建", "target": "代码文件/监督机制/verify_deployment.py", "deployed": true, "deployer_ok": true},
      {"id": "G4", "item": "pipeline_engine.py 已修改含清单检查", "target": "代码文件/监督机制/pipeline_engine.py", "deployed": true, "deployer_ok": true},
      {"id": "G5", "item": "需求代码核对清单.md 已更新含JSON schema", "target": ".claude/knowledge/需求代码核对清单.md", "deployed": true, "deployer_ok": true},
      {"id": "G6", "item": "回滚方案就绪", "target": "git revert HEAD~1", "deployed": true, "deployer_ok": true}
    ]
  },
  "signoffs": {
    "情墨": {"signed": true, "date": "2026-05-29", "scope": "A-F设计侧+G段预期"},
    "腰子": {"signed": true, "date": "2026-05-29", "scope": "纯工程基础设施，无金融逻辑"},
    "红结": {"signed": true, "date": "2026-05-29", "scope": "A-F代码回填（纯工程，A-F无项）"},
    "红枫": {"signed": true, "date": "2026-05-29", "scope": "G段部署回填"}
  }
}
```

> 情墨签字：✓ 2026-05-29 | 腰子签字：✓ 2026-05-29 (纯工程基础设施)
