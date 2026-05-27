# 门户本地优先发布制度 — 架构设计

> pipeline_stage: complete
> 设计者: 情墨 | 日期: 2026-05-27 | 代码分级: L0（工具脚本 + 流程文档）
> 关联: [[design_portal_liquid_glass_20260527]]

---

## 一、现状与问题

### 1.1 当前部署链路

```
portal_template.html ──→ generate_portal.py ──→ docs/index.html ──→ git push ──→ GitHub Pages
                                │                                           (ccrt26.github.io/ccrt)
                          注入数据 + 替换API
```

### 1.2 问题

| 问题 | 影响 |
|:-----|:-----|
| 修改后直接 `generate_portal.py` → `git push`，无本地验证 | 错误直接暴露到线上 |
| `pigeon_server.py` 提供本地预览，但无人知道流程 | 本地验证能力闲置 |
| 无分阶段检查点 | 无法确定"哪个环节出的问题" |
| 模板修改后需手动 copy 到 `pigeon_dashboard.html` | 两份文件容易不一致 |

---

## 二、目标流程（六阶段）

```
[1] git pull                    ← 同步远程最新数据
     │
[2] 本地开发                     ← 编辑 portal_template.html
     │
[3] 本地预览验证                  ← pigeon_server.py (实时API, 3标签页)
     │                           ← 浏览器验证: 数据渲染/交互/样式
     │
[4] 构建静态站                    ← generate_portal.py (嵌入数据, 替换API)
     │
[5] 本地静态验证                  ← python -m http.server docs/ (纯静态)
     │                           ← 浏览器验证: 离线可用/数据完整
     │
[6] 部署上线                     ← git add + commit + push → GitHub Pages
```

### 2.1 各阶段详细说明

| 阶段 | 命令 | 验证项 | 通过标准 |
|:----:|:-----|:------|:-----|
| ① 同步 | `git pull` | 本地=远程 | 无冲突 |
| ② 开发 | 编辑模板 | -- | -- |
| ③ 动态预览 | `launch_pigeon_dashboard.ps1` | 事件数据/过滤/展开/三标签切换 | 全部功能正常 |
| ④ 构建 | `python generate_portal.py` | 无报错 | 输出 `[OK]` |
| ⑤ 静态预览 | `python -m http.server 9999 -d docs/` | 同③ + 离线可用 + 报告链接有效 | 全部功能正常 |
| ⑥ 部署 | `git_autopush.ps1` + 验证线上 | GitHub Pages 正常 | 线上与本地一致 |

---

## 三、文件架构

```
代码文件/信鸽信息采集/
├── portal_template.html          ← 【唯一编辑入口】设计模板
├── pigeon_dashboard.html         ← 【自动同步】= portal_template.html 的副本
├── generate_portal.py            ← 构建脚本（模板 → docs/）
├── pigeon_server.py              ← 本地API服务器
├── launch_pigeon_dashboard.ps1   ← 一键启动本地预览
├── portal_deploy.ps1             ← 【新增】一键完整部署脚本
└── pigeon_config.json            ← 配置文件

docs/                             ← GitHub Pages 源目录
├── index.html                    ← 构建产物
├── deep_analysis/                ← 深度分析报告副本
└── daily_reports/                ← 日报副本
```

---

## 四、核心脚本设计：portal_deploy.ps1

### 4.1 功能

```
portal_deploy.ps1 -Stage <sync|preview|build|verify|deploy|full>
```

| Stage | 操作 |
|:------|:-----|
| `sync` | git pull → 同步 portal_template.html + 数据文件 |
| `preview` | 同步 portal_template.html → pigeon_dashboard.html → 启动 pigeon_server.py → 打开浏览器 |
| `build` | 运行 generate_portal.py → 生成 docs/index.html |
| `verify` | 启动 python http.server on docs/ → 打开浏览器验证静态站 |
| `deploy` | git add + commit + push（带确认） |
| `full` | sync → preview → build → verify → (确认) → deploy |

### 4.2 安全闸门

- `deploy` 前强制检查：`verify` 是否已完成？
- `deploy` 前展示变更摘要（`git diff --stat`）
- 用户手动确认后才推送
- 推送失败自动回退代理策略

---

## 五、代码等级

| 模块 | 等级 | 理由 |
|:-----|:----:|:-----|
| portal_deploy.ps1 | L0 | 工具脚本，无业务逻辑 |
| 流程文档 | M类 | 知识/流程文档 |
| portal_template.html | L0 | 纯UI层 |

---

## 六、需求→实施核对

| 编号 | 检查项 | 用户需求 | 状态 |
|:----:|:------|:------|:----:|
| R1 | Git数据同步到本地 | "全部同步到本地" | ☐ |
| R2 | 本地修改→预览→确认 | "先在本地进行发布" | ☐ |
| R3 | 确认后部署到Web | "确认没有问题后再发布到互联网" | ☐ |
| R4 | 标准流程制度 | "按照标准流程设计一下制度" | ☐ |
| R5 | 一键部署脚本 | 工程化落地 | ☐ |
