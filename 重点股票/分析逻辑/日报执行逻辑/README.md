# 日报执行逻辑 — 正式资产目录

> 版本: v3.7.1 | 更新: 2026-06-11
> 设计依据: 重点股票/讨论/日报分析逻辑优化方案-v0.3-全团审议.md
> 边界: 本目录为正式维护资产，不构成生产日报入口

## 目录结构

```
日报执行逻辑/
├── README.md                          ← 本文件：目录索引
├── VERSION.md                         ← 版本追踪
├── rules/                             ← JSON 规则（可编程验证）
│   ├── daily_report_rules.json        ← 日报核心定位与执行规则
│   ├── state_machine.json             ← A/B/C/D/E/M 状态机
│   ├── fee_template_a_share_v0.1.json ← A股费用估算模板
│   ├── user_operation_rules.json      ← 用户操作卡规则
│   └── validation_rules.json          ← 校验规则（BLOCK/WARN）
└── schemas/                           ← JSON Schema（数据契约）
    ├── position_input.schema.json     ← 用户持仓输入 Schema
    ├── shadow_state.schema.json       ← 每日状态快照 Schema
    └── operation_card.schema.json     ← 操作卡输出 Schema
```

## 引用关系

```
daily_report_rules.json (顶层规则)
    ├── 引用 state_machine.json (状态机)
    ├── 引用 fee_template_a_share_v0.1.json (费用)
    ├── 引用 user_operation_rules.json (操作卡)
    └── 引用 validation_rules.json (校验)
```

## 脚本对应

```
代码文件/重点股票/日报执行/
├── position_cost.py      ← 读取 schemas/ + fee_template
├── validate_rules.py     ← 验证 rules/ 全部 JSON
├── validate_cases.py     ← 验证 tests/cases/ 全部用例
└── generate_reports.py   ← 读取全部输入 → 输出审计报告

代码文件/重点股票/日报执行/tests/
├── cases/                ← 9个输入用例
└── expected/             ← 9个期望输出
```

## 审计落点

```
00_项目地基/08_审计与验收/
├── 日报逻辑程序化收敛_G4自动自检报告.md
└── 日报逻辑程序化收敛_G5旧影复查报告.md

00_项目地基/99_归档/02_审计复查与放行/
└── 日报逻辑程序化收敛_G6归档记录.md
```

## 历史

| 版本 | 日期 | 说明 |
|:-----|:-----|:------|
| v3.7-draft | 2026-06-11 | Shadow 阶段初始设计 |
| v3.7.1-draft | 2026-06-11 | 成本计算字段补修 + 费用模板 |
| v3.7.1 | 2026-06-11 | 程序化收敛：从 .md 迁移为 JSON rules + schemas + scripts |

## 正式资产边界

- ✅ 本目录下的 `rules/` 和 `schemas/` 为后续维护的**唯一事实源**
- ✅ 脚本 `代码文件/重点股票/日报执行/` 为可重复执行的计算/验证工具
- ⛔ 临时报告/F-ARCH_shadow_preview_v1.0/ 仅保留 Shadow 历史样例，不再作为主执行依据
