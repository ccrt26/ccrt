# KRM 知识统一入口

> **知识正文统一管理位置**
> 版本：v1.2.1 | 更新日期：2026-06-11

## 真实目录结构
```
knowledge/
├── manifest.json                      ← 全知识源索引（v1.2.1）
├── README_KRM_知识入口.md             ← 本文
├── roles/<role>/                      ← 角色精华包（正式启动入口）
│   ├── README.md                      ← startup：角色知识路由
│   ├── 00_旧库来源索引.md             ← audit：旧库文件溯源
│   ├── 01_职责边界.md                 ← startup：职责与边界
│   ├── 02_输入证据.md                 ← startup：证据来源
│   ├── 03_判断规则.md                 ← startup：判断依据
│   ├── 04_输出模板.md                 ← task：输出结构
│   ├── 05_禁止事项.md                 ← startup：红线
│   ├── 06_后评估知识进化.md           ← task：知识进化路径
│   └── 07_深度读取触发器.md           ← startup：何时必须读 source 原文
├── sources/legacy_role_kb/<role>/     ← 旧库全文保真层（deep 读取）
│   ├── 原旧库 .md 文件
│   └── SOURCE_INDEX.md
├── shared/                            ← 共享规则摘要（按需读取）
└── legacy_refs/                       ← 旧版残留/历史快照（audit）
```

## 读取层级

| 层级 | 内容 | 读取条件 |
|:-----|:-----|:---------|
| **startup** | roles/<role>/README, 01, 02, 03, 05, 07 | 角色参与任务时默认读取 |
| **task** | roles/<role>/04, 06 | 输出或后评估任务时按需读取 |
| **deep** | sources/legacy_role_kb/<role>/ | 深度分析/争议复查/后评估/G5/G6 审计时读取 |
| **audit** | roles/<role>/00, sources/SOURCE_INDEX, manifest.json | 仅溯源追溯时读取 |

## 硬规则

- 触发深度读取但未读取 source 原文时，角色不得输出强结论，只能 WARN 或要求补证据。
- 精华包负责读取路由，source 原文负责能力保真。
- sources/ 默认不进入启动上下文。
- 旧 `.claude/agents/*-知识库/` 不再是任何角色的正式入口。

## 与六库和历史解释包的关系

| 来源 | 处理 |
|:-----|:-----|
| 旧 `.claude/knowledge/` | 原文保留，通过 manifest/legacy_refs 追溯 |
| 角色解释包 | 精华进入 roles/，原文按需追溯 |
| 六库原始文件 | 不进启动上下文 |
| 外部文献原文 | 不进启动上下文，只能摘要卡片化 |
