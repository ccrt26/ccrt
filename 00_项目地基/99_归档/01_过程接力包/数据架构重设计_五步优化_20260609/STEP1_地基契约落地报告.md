# STEP1：地基契约与注册表落地报告（补修版）

> 流程编号：F-ARCH + F-GATE
> 启用阶段门：G0 → G2 → G3 → G4 → G5 → G6
> 跳过阶段门：G1（无金融/角色口径变更）
> 日期：2026-06-09（首次）+ 2026-06-09（补修）

---

## 一、阶段目标完成情况

| 目标 | 完成度 | 说明 |
|:-----|:------:|:-----|
| D04 能力注册 | ✅ | C-D04-0001：rules_applied 补齐，status=active，无 consumed_by |
| D04 source registry | ✅ | 5 条 L1/L2/L3 数据源，含真实路径，null fallback 删除，L2 status=degraded |
| numeric/freshness 映射更新 | ✅ | kline_l2 增加 enabled=false、phase=2、authority_resolution |
| D04 边界说明 | ✅ | 两份权威契约补充 D04/L1/L2/L3 权威源说明和过渡策略 |
| 阶段验收 policy | ✅ | STEP2_准入检查清单.md 已创建 |
| INDEX/README 同步 | ✅ | D04 描述从"暂未注册"修正为"已注册 C-D04-0001" |
| （补修）kline 权威源回退 | ✅ | rules.kline 权威源回退至 L1 单字符串，删除越界 source_resolution |
| （补修）source_registry 路径/状态 | ✅ | source_name 补路径，null fallback 删除，L2 status=degraded |

## 二、流程编号与阶段门

| 字段 | 值 |
|:-----|:----|
| 主流程编号 | F-ARCH |
| 挂载流程 | F-GATE（闸门补丁） |
| 启用阶段门 | G0 → G2 → G3 → G4 → G5 → G6 |
| 跳过阶段门 | G1（无金融/角色口径变更） |

## 三、角色职责与确认状态

> 执行模型不是项目角色。本表仅记录 STEP1 按标准流程应触达的角色职责与当前确认状态，不代表执行模型已代签角色结论。

| 角色/执行方 | 阶段门 | 职责 | 当前状态 |
|:------------|:-------|:-----|:---------|
| 阿黑 | G0 | 需求识别、流程路由、阶段调度 | 待项目侧确认；执行模型仅记录路由依据 |
| 情墨 | G2 | 架构一致性与契约落地口径确认 | 待项目侧确认；执行模型仅记录技术依据 |
| 玉夜 | G2 | 数据事实、权威源与 D04 边界确认 | 待项目侧确认；执行模型仅记录数据依据 |
| 执行模型 | G3 | 文件修改与补修执行 | 已执行，见修改文件清单 |
| 执行模型 | G4 | 执行者自检 | 已自检，见验收命令结果 |
| 旧影 | G5 | 独立复查 | 待用户/复查方确认；执行团队不得自签 |
| 腰子 | G6 | 放行确认 | 待用户确认；不得自行进入 STEP2 |

## 四、变更摘要

### 4.1 capability_registry.json（未修改）
- C-D04-0001：rules_applied=[], status=active, 无 consumed_by（首次执行完成，无需补修）

### 4.2 source_registry.json（补修）
- source_name 全部补入真实路径（因 schema 无 path 字段，路径在 name 中表达）
- 删除所有 null fallback_source 字段
- SRC-L1-0002 删除指向 L2 的 fallback（L2 未建设，不应表达为可用 fallback）
- SRC-L2-0001 status 改为 "degraded"（Phase 2 待建设，仅注册）

### 4.3 numeric_field_mapping.json（首次执行完成，未补修）
- kline_l2 增加 enabled=false、phase=2、authority_resolution

### 4.4 freshness_rules.json（补修）
- rules.kline.authority_source 从数组回退至单字符串 `代码文件/数据/kline_cache/{code}.json`
- rules.kline 删除越界添加的 source_resolution 字段（原文件没有）
- rules.kline_l2 保持不变（enabled=false, phase=2）

### 4.5 权威契约（首次执行完成，未补修）
- 新增 D04/L1/L2/L3 权威源说明和过渡策略

### 4.6 INDEX + README（首次执行完成，未补修）
- D04 状态已修正为"已注册 C-D04-0001"

## 五、验收命令结果

| 命令组 | 结果 |
|:-------|:-----|
| JSON 语法（4 文件） | ✅ 全部通过 |
| D04 registry 内容验证 | ✅ 全部通过 |
| source 路径验证 | ✅ 5 条路径全部匹配 |
| null fallback 验证 | ✅ 无 null fallback_source |
| freshness kline 权威源验证 | ✅ 已回退至 L1 单字符串 |
| kline_l2 phase 验证 | ✅ enabled=false, phase=2 保持不变 |
| 禁止范围修改检查 | ✅ STEP1 未越界（pre-existing dirty + pre-existing untracked 非本次造成） |

## 六、遗留问题

1. **G5/G6 尚待用户/复查方确认** — G5 独立复查和 G6 放行签字尚未由项目角色完成，进入 STEP2 前需用户明确确认。
2. `00_项目地基/02_数据架构重设计/G5_旧影独立复查报告.md` 为 pre-existing untracked 文件（日期 2026-06-08），非本次 STEP1 产物，不纳入 STEP1 验收范围。
3. 禁止范围 `代码文件/`、`scripts/`、`历史数据/`、`重点股票/` 下的 54 个 pre-existing dirty 文件为会话前已有的脏状态，非本次造成。

## 七、G5 / G6 状态

| 阶段门 | 职责 | 状态 |
|:------:|:-----|:----:|
| G5 | 独立复查 | **待用户/复查方确认；执行团队不得自签** |
| G6 | 放行 | **待用户确认；不得自行进入 STEP2** |
