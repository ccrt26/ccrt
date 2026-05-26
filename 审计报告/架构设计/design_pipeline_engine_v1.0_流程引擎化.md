# 架构设计: 流程引擎化 v1.0 — 从"文档驱动"到"引擎驱动"

> 设计人: 情墨 | 日期: 2026-05-25 | 触发: 流程"全自动"失效——阿黑频繁问"继续"、跳过环节
> 代码等级: **L1** (策略/基础设施)

---

## 一、问题诊断

当前流程架构存在三层断点：

```
规则层（CLAUDE.md §七）     ✅ 语义完整
        │  ← 断点1: 规则无法自我执行
协调层（阿黑）             ❌ 靠记忆+自觉，跨轮次丢失上下文
        │  ← 断点2: 无事件触发、无持久驱动
机制层（token+hooks）      ⚠️ 只能"堵"（阻断违规），不能"疏"（驱动推进）
```

核心矛盾：流程设计需要持续状态+事件驱动，但机制层只提供静态标记+被动阻断。阿黑被迫用记忆弥合鸿沟。

---

## 二、设计原则

1. **引擎管状态，阿黑管执行** — 引擎说"做什么"，阿黑做
2. **完成可检测** — 每阶段有机器可读的完成信号，不依赖主观判断
3. **闸门自动化** — 引擎自动校验文件系统/git/报告存在性，无需人工
4. **静默续跑** — 上下文将满时 ScheduleWakeup 自动续，不打断用户
5. **L3 唯一停止点** — 只有引擎判定 `stop_l3` 时才打断用户

---

## 三、新增模块

### 3.1 pipeline_engine.ps1（流程引擎）

- 位置: `代码文件/监督机制/pipeline_engine.ps1`
- 功能: 流程状态机——管理 6 阶段全生命周期，输出阿黑执行指令
- 预计行数: ~200 行
- 参数接口:

| 操作 | 说明 |
|:-----|:-----|
| `-Status` | 返回当前状态 JSON（含 `next_action`） |
| `-Start -Task "描述"` | 初始化流程，stage=1，executor=情墨 |
| `-Validate -OutputPath "..."` | 校验当前阶段完成信号 → 判定闸门 PASS/FAIL |
| `-Advance` | PASS 后推进到下一阶段 |
| `-Retry` | FAIL 后打回重做（attempts+1，达 max 则升级 L3） |
| `-Complete` | 归档并重置 |

- 返回结构（JSON，stdout）：

```json
{
    "schema_version": "1.0",
    "active": true,
    "task": "...",
    "stage": 2,
    "stage_name": "架构审查",
    "executor": "新安+旧影",
    "next_action": "invoke_role",
    "gate_1": "PASS",
    "gate_2": "PENDING",
    "gate_3": "PENDING",
    "attempts": 1,
    "max_attempts": 3,
    "l3_triggered": false,
    "l3_reason": "",
    "loop_context": "流程①→⑥第2/6阶段：架构审查。调用新安+旧影审查设计文档。",
    "stage_history": [
        {"stage":1, "executor":"情墨", "gate":"PASS", "output":"审计报告/架构设计/design_xxx.md"}
    ],
    "started": "2026-05-25T10:00:00",
    "updated": "2026-05-25T10:15:00"
}
```

### 3.2 阶段完成信号检测（引擎内置）

| 阶段 | 检测方式 | PASS 条件 |
|:-----|:--------|:---------|
| ① 情墨设计 | 文件系统 | `审计报告/架构设计/design_*.md` 存在 + 修改时间 > 阶段开始时间 |
| ② 新安+旧影审查 | 文件系统 | `审计报告/流程审计/` 下审查报告存在 + 含 `gate: PASS` |
| ③ 红结编码 | Git | 有新 commit 或 staged files，路径在 `代码文件/` |
| ④ 新安验证 | 文件系统 | 四层验证报告（变更影响/测试/回归/红线）全部存在 |
| ⑤ 红枫部署 | 文件系统 | 部署记录存在 + 回滚方案存在 |
| ⑥ 后评估 | 文件系统 | 后评估报告存在（按对应白皮书路径） |

### 3.3 pipeline_active.json schema 升级

新增字段：`stage_history[]`, `current_attempts`, `max_attempts`, `gate_1/2/3`, `l3_triggered`, `l3_reason`, `next_action`, `loop_context`

引擎启动时自动检测旧 schema 并迁移。向后兼容：旧字段 `active/task/stage/executor/started/updated` 保持不变。

---

## 四、变更模块

### 4.1 CLAUDE.md §七 — 压缩为阿黑循环协议

当前 §七 约 80 行规则 → 压缩为 ~15 行执行协议：

```
阿黑流程执行循环：
1. status = pipeline_engine.ps1 -Status
2. 若 next_action=="done": 输出摘要，结束
3. 若 next_action=="stop_l3": 呈现 l3_reason，等用户
4. 若 next_action=="invoke_role":
   a. 读 .claude/commands/<executor>.md
   b. 以该角色产出交付物
   c. pipeline_engine.ps1 -Validate -OutputPath "交付物路径"
5. 若 next_action=="retry": 静默打回，重新执行步骤4
6. 上下文>70%: ScheduleWakeup(60s, loop_context)
7. goto 1
```

原 §七 详细内容（阶段职责/闸门定义/违规处理/日志要求）移至 pipeline_engine.ps1 注释 + 引擎内置逻辑。

### 4.2 pipeline_token.ps1 → 轻量 wrapper

保留现有 CLI 接口（-Start/-Advance/-Complete/-Status），内部改为调用 pipeline_engine.ps1。不破坏已有脚本和 muscle memory。

### 4.3 memory 文件同步

- `engineering-delivery-pipeline.md` — 更新为引擎化架构描述
- `feedback/ahhei-autonomous-pipeline.md` — 更新为循环协议引用

---

## 五、数据流

```
阿黑收到工程任务
  │
  ▼
pipeline_engine.ps1 -Start -Task "..."    ← 引擎初始化状态
  │
  ▼
┌─────────────────────────────────────────────────────┐
│              阿黑执行循环（自动续跑）                    │
│                                                       │
│  pipeline_engine.ps1 -Status                          │
│    → next_action: "invoke_role", executor: "情墨"     │
│    → 阿黑读 .claude/commands/情墨.md                  │
│    → 情墨产出设计文档                                   │
│    → pipeline_engine.ps1 -Validate -OutputPath "..."  │
│    → 引擎检测: 设计文档存在 → gate_1 候选 PASS          │
│    → pipeline_engine.ps1 -Advance                     │
│    → next_action: "invoke_role", executor: "新安+旧影" │
│    → ...循环...                                        │
│    → next_action: "done"                              │
│    → 阿黑输出摘要，结束                                 │
│                                                       │
│  仅当 next_action=="stop_l3" 时 → 打断用户             │
│  上下文将满时 → ScheduleWakeup(60s) → 下轮自动续       │
└─────────────────────────────────────────────────────┘
```

---

## 六、闸门自动化逻辑

### 闸门1 — 设计闸（①→②）
```
引擎检查:
  [ ] 审计报告/架构设计/design_*.md 存在（修改时间 > 阶段①开始时间）
  [ ] 文档含 pipeline_stage: complete 标记（情墨完成信号）
  [ ] 文档含 finance_confirmed: true 标记（腰子确认信号）
      ↳ 腰子须先完成 §6.0 全团强制咨询: 山猫→玉夜→流金→青山 → 综合决策后签字
  → 全满足=PASS → -Advance → ②
  → 任一不满足=FAIL → retry_count++ → 引擎设 next_action="retry"
  → retry_count>=3 → next_action="stop_l3", l3_reason="设计文档或腰子确认3次未通过"
```

### 闸门2 — 代码闸（③→④）
```
引擎检查:
  [ ] git diff --name-only HEAD 或 staged 含 代码文件/ 变更
  [ ] 变更文件路径匹配设计文档中声明的文件列表
  [ ] 审计报告/ 下四层验证报告存在
  → 全满足=PASS
```

### 闸门3 — 上线闸（④→⑤）
```
引擎检查:
  [ ] gate_1==PASS AND gate_2==PASS
  [ ] 部署记录文件存在
  [ ] 回滚方案文件存在
  → 全满足=PASS
```

---

## 七、接口契约

### 7.1 引擎 ↔ 阿黑

- 引擎 stdout: 单行 JSON（`-Status` 时）
- 阿黑: 读取 JSON，按 `next_action` 执行
- 错误: exit code != 0 → 阿黑报告给用户（L3 升级）

### 7.2 引擎 ↔ 角色

- 角色完成信号: 交付物写入约定路径（参见 §三.2）
- 引擎检测: 基于文件系统 + git 状态，不解析角色输出内容
- 角色无需感知引擎存在（零侵入）

### 7.3 引擎 ↔ pipeline_token.ps1

- pipeline_token.ps1 内部调用 `pipeline_engine.ps1` 同名参数
- CLI 接口不变：`-Start/-Advance/-Complete/-Status`
- 返回值透传

### 7.4 向后兼容

- `pipeline_active.json` 旧 schema → 引擎启动时自动迁移
- `pipeline_history/` 归档格式不变
- Hook 脚本（pre-commit-check.ps1 / write_protection_hook.ps1）无需修改，仍读 `active` + `executor` 字段

---

## 八、需求→代码核对清单

- [ ] pipeline_engine.ps1 — 新建，~200行
  - [ ] -Status 操作 + JSON 输出
  - [ ] -Start 操作（初始化状态对象）
  - [ ] -Validate 操作（6阶段完成信号检测）
  - [ ] -Advance 操作（闸门判定 + 阶段推进）
  - [ ] -Retry 操作（attempts 递增 + max 检测 → L3）
  - [ ] -Complete 操作（归档 + 重置）
  - [ ] 旧 schema 自动迁移逻辑
- [ ] pipeline_token.ps1 — 改为 engine wrapper
- [ ] CLAUDE.md §七 — 压缩为阿黑循环协议（~15行）
- [ ] pipeline_active.json — schema 文档更新（注释或配套 .schema.json）
- [ ] memory — engineering-delivery-pipeline.md 更新
- [ ] memory — feedback/ahhei-autonomous-pipeline.md 更新
- [ ] engine 自身行为契约测试（给定输入状态，断言输出 next_action）
- [ ] 闸门1 finance_confirmed 标记检测（腰子确认后写入）
- [ ] 引擎错误处理（git不可用/文件权限/JSON损坏 → 结构化错误输出）
- [ ] ScheduleWakeup 兜底：引擎检测 >30min 无进展 → stop_l3

> 情墨签字: ✅ | 腰子确认: ✅ | 新安审查: ✅ (审计报告/旧影独立审计_流程引擎v1.0_20260525.md)
> 旧影审计: ✅ (同上) | 闸门1: PASS | finance_confirmed: true
