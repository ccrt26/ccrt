# 架构设计: 流水线7阶段重构 v1.1 — 插入腰子设计确认阶段 + 闸门1拆分为1a/1b

> 设计人: 情墨 | 日期: 2026-05-25 | 触发: 根因分析发现流程引擎缺失腰子设计确认阶段
> 代码等级: **L1** (策略/基础设施)
> 上游设计: design_pipeline_engine_v1.0_流程引擎化.md (本设计在此基础上重构阶段结构)

---

## 一、问题诊断

### 1.1 根因回顾

阿黑根因分析报告确认了四层递进的系统性问题：

| 层级 | 位置 | 问题 |
|:----:|:-----|:-----|
| 设计层 | design_pipeline_engine_v1.0 | 腰子确认被建模为元数据字段(`finance_confirmed: true`)而非流程阶段 |
| 代码层 | pipeline_engine.ps1:28-29 | 6阶段数组无"腰子"executor，引擎永远不输出`executor: "腰子"` |
| 规则层 | CLAUDE.md §七.2 | 阶段表6行，"腰子确认"只在闸门描述栏中提及 |
| 记忆层 | engineering-delivery-pipeline.md | 同步传播了6阶段错误流程 |

### 1.2 核心矛盾

腰子全团强制咨询铁律（CLAUDE.md §六.0）是项目最高优先级规则，但引擎把它的执行条件降格为一个regex检查，阿黑收不到"该召腰子了"的指令。

---

## 二、设计方案

### 2.1 阶段重构：6→7

```
旧(6阶段):
①情墨 → ②新安+旧影 → ③红结 → ④新安 → ⑤红枫 → ⑥后评估

新(7阶段):
①情墨 → ②腰子 → ③新安+旧影 → ④红结 → ⑤新安 → ⑥红枫 → ⑦后评估
          ↑ NEW: 设计确认(金融把关)
```

### 2.2 闸门重构：3→4

| 闸门 | 触发阶段 | 含义 | 验证方式 |
|:----:|:--------|:-----|:--------|
| gate_1a | ②→③ | 腰子金融确认 | 设计文档含 `finance_confirmed: true`（腰子完成全团咨询后写入） |
| gate_1b | ③→④ | 新安+旧影技术合规 | 2+审查报告含 gate:PASS |
| gate_2 | ⑤→⑥ | 新安四层验证 | 4份验证报告(变更影响/测试/回归/红线) |
| gate_3 | ⑥→⑦ | 红枫部署就绪 | gate_1a/b+gate_2全PASS + 部署记录 + 回滚方案 |

### 2.3 7阶段完成信号检测

| 阶段 | 执行者 | 检测方式 | PASS条件 |
|:----:|:------|:--------|:--------|
| ① | 情墨 | 文件系统 | `审计报告/架构设计/design_*.md` 存在 + 含 `pipeline_stage: complete` |
| ② | 腰子 | 文件系统 | 设计文档含 `finance_confirmed: true` + 修改时间>阶段②进入时间 |
| ③ | 新安+旧影 | 文件系统 | 2+审查报告存在 + 含 gate:PASS |
| ④ | 红结 | Git | `代码文件/` 下有变更(staged/unstaged/untracked) |
| ⑤ | 新安 | 文件系统 | 4份验证报告(变更影响/测试/回归/红线)全部存在 |
| ⑥ | 红枫 | 文件系统 | 部署记录 + 回滚方案文件存在 |
| ⑦ | 腰子+青山 | 文件系统 | 后评估报告存在 |

### 2.4 阶段②（腰子）完成信号详解

引擎对阶段②的Validate检查：

```
1. 定位最新 design_*.md
2. 检查含 "finance_confirmed: true"
3. 检查文件 LastWriteTime > 阶段②进入时间(防止情墨预填)
→ 全满足 = PASS
```

腰子确认流程（由阿黑驱动，非引擎检查）：
```
阿黑以腰子身份激活 → 腰子读取设计文档
  → 按§六.0召集山猫→玉夜→流金→青山
  → 综合四角色意见
  → 在设计文档末尾追加确认行:
    "> 腰子确认: ✅ | 全团咨询完成: 山猫✅ 玉夜✅ 流金✅ 青山✅ | 日期: YYYY-MM-DD"
  → 确保文档含 "finance_confirmed: true"
```

### 2.5 闸门判定逻辑变更

```
旧: Gate1 = Stage1Complete AND Stage2Complete (合并判定)
新: gate_1a = Stage2Complete (腰子确认)
    gate_1b = Stage3Complete (新安+旧影审查)
```

```powershell
function Test-Gate1a($Token) {
    # 阶段②腰子确认完成 → gate_1a = PASS
    if (Stage2 pass) → gate_1a = PASS
    else → gate_1a = FAIL, retry
}

function Test-Gate1b($Token) {
    # 阶段③新安+旧影审查完成 → gate_1b = PASS
    # 前置: gate_1a must be PASS
    if (gate_1a ≠ PASS) → gate_1b = FAIL
    if (Stage3 pass) → gate_1b = PASS
    else → gate_1b = FAIL, retry
}
```

---

## 三、变更范围

### 3.1 pipeline_engine.ps1 — 核心重构（~50行变更）

| 位置 | 变更内容 |
|:-----|:--------|
| `$STAGE_EXECUTORS` | `@("情墨","腰子","新安+旧影","红结","新安","红枫","PostEval")` |
| `$STAGE_NAMES` | `@("架构设计","设计确认","架构审查","编码实现","上线前验证","灰度部署","后评估")` |
| `Get-LoopContext` | token字段 `gate_1a/gate_1b` 替代 `gate_1` |
| `Test-Stage1Complete` | 移除 `finance_confirmed: true` 检查（迁移至Stage2） |
| `Test-Stage2Complete` | **新增** — 检查 `finance_confirmed: true` + 文件修改时间>阶段进入时间 |
| `Test-Stage3Complete` | 从旧 Test-Stage2Complete 改名（内容不变） |
| `Test-Stage4Complete` | 从旧 Test-Stage3Complete 改名 |
| `Test-Stage5Complete` | 从旧 Test-Stage4Complete 改名 |
| `Test-Stage6Complete` | 从旧 Test-Stage5Complete 改名 |
| `Test-Stage7Complete` | 从旧 Test-Stage6Complete 改名 |
| `Test-Gate1` | **删除**，替换为 `Test-Gate1a` + `Test-Gate1b` |
| `Test-Gate2` | 前置条件改为检查 gate_1b（非 gate_1） |
| `Test-Gate3` | 前置条件改为检查 gate_1a/gate_1b（非 gate_1） |
| `Invoke-Start` | gate字段改为 gate_1a/gate_1b/gate_2/gate_3 |
| `Invoke-Validate` | 阶段-闸门映射更新（见下表） |
| `Invoke-Advance` | 阶段推进逻辑更新 |
| `Migrate-Schema` | 新增 v1.0→v1.1 迁移：旧 gate_1=PASS → gate_1a=PASS, gate_1b=PASS |

### 3.2 阶段-闸门Validate映射

```
阶段①: validate → 无闸门判定(仅标记完成)
阶段②: validate → Test-Gate1a
阶段③: validate → Test-Gate1b
阶段④: validate → 无闸门判定
阶段⑤: validate → Test-Gate2
阶段⑥: validate → Test-Gate3
阶段⑦: validate → 最终完成判定
```

### 3.3 CLAUDE.md §七 — 行级更新

- §七.1 阿黑执行循环：不变（仍读next_action执行）
- §七.2 阶段速查表：扩为7行，新增②腰子行
- §七.3 闸门速查：gate结构更新

### 3.4 其他文件

| 文件 | 变更 |
|:-----|:-----|
| `审计报告/架构设计/design_pipeline_engine_v1.0_流程引擎化.md` | 新增引用本文档 |
| `~/.claude/.../memory/engineering-delivery-pipeline.md` | 7阶段更新 |
| `pipeline_token.ps1` | 无变更（wrapper委托给engine，自带兼容） |

### 3.5 不涉及的文件

- Hook脚本（pre-commit-check.ps1 / write_protection_hook.ps1）— 仍读 `active` + `executor` 字段
- pipeline_active.json 历史归档 — 引擎内置迁移逻辑处理旧schema
- 各角色 command 文件 — 阶段编号变化不影响角色边界

---

## 四、向后兼容

### 4.1 Schema迁移 v1.0→v1.1

引擎启动时自动检测并迁移：
```
if schema_version == "1.0":
    gate_1a = gate_1  (旧gate_1 PASS → 两个新gate都PASS)
    gate_1b = gate_1
    schema_version = "1.1"
```

### 4.2 进行中的旧流程处理

- `-Start` 强制要求 pipeline_active 不存在或已 inactive（已有检查），不涉及进行中流程迁移
- 历史归档（pipeline_history/）不修改，保留原始schema版本号

---

## 五、数据流（更新）

```
阿黑收到E类工程任务
  ↓
pipeline_engine.ps1 -Start → stage=1, executor=情墨
  ↓
情墨产出设计文档(含 pipeline_stage: complete)
  → Validate → Advance → stage=2, executor=腰子
  ↓
腰子按§六.0全团咨询(山猫→玉夜→流金→青山)
  → 在设计文档追加 finance_confirmed: true
  → Validate → Gate1a判定 → Advance → stage=3, executor=新安+旧影
  ↓
新安+旧影产出审查报告(含 gate:PASS)
  → Validate → Gate1b判定 → Advance → stage=4, executor=红结
  ↓
红结编码实现
  → Validate → Advance → stage=5, executor=新安
  ↓
新安四层验证
  → Validate → Gate2判定 → Advance → stage=6, executor=红枫
  ↓
红枫灰度部署
  → Validate → Gate3判定 → Advance → stage=7, executor=腰子+青山
  ↓
腰子+青山后评估
  → Validate → done
```

---

## 六、风险与约束

| 风险 | 缓解 |
|:-----|:-----|
| 阶段编号变化影响硬编码引用 | 所有阶段引用通过 `$STAGE_EXECUTORS`/`$STAGE_NAMES` 数组索引，不硬编码数字 |
| 旧pipeline token兼容 | Migrate-Schema 自动处理 v1.0→v1.1 |
| 腰子确认耗时（需召4角色） | 引擎不设超时，由30min stall检测兜底 |
| 情墨预填 finance_confirmed | Stage2验证检查文件修改时间>阶段进入时间 |

---

## 七、需求→代码核对清单

- [ ] pipeline_engine.ps1 — 6→7阶段重构
  - [ ] `$STAGE_EXECUTORS` 插入"腰子"
  - [ ] `$STAGE_NAMES` 插入"设计确认"
  - [ ] 新增 `Test-Stage2Complete`（腰子确认检测）
  - [ ] 重命名 Test-Stage{2..6}Complete → {3..7}Complete
  - [ ] 拆分 `Test-Gate1` → `Test-Gate1a` + `Test-Gate1b`
  - [ ] 更新 `Test-Gate2` 前置条件（gate_1b）
  - [ ] 更新 `Test-Gate3` 前置条件（gate_1a/gate_1b）
  - [ ] 更新 `Invoke-Start` gate字段初始化
  - [ ] 更新 `Invoke-Validate` 阶段-闸门映射
  - [ ] 更新 `Invoke-Advance` 阶段推进+闸门检查
  - [ ] 更新 `Get-LoopContext` 7阶段描述
  - [ ] 更新 `Migrate-Schema` v1.0→v1.1
  - [ ] schema_version 升级为 "1.1"
- [ ] CLAUDE.md §七.2 — 阶段表扩为7行
- [ ] design_pipeline_engine_v1.0 — 追加引用本文档
- [ ] memory engineering-delivery-pipeline.md — 7阶段更新
- [ ] 引擎自身行为验证（给定状态→断言next_action）

> 情墨签字: ✅ | pipeline_stage: complete
> 腰子确认: ✅ | 全团咨询完成: 山猫✅(无宏观风险) 玉夜✅(无数据变更) 流金✅(无风控影响) 青山✅(无策略变更) | 日期: 2026-05-25 | finance_confirmed: true
