# 代码基础设施现代化 — 情墨架构设计交付物

> pipeline_stage: complete
> finance_confirmed: true
> 设计日期：2026-05-25
> ⚠️ **平台标注 (2026-05-29)**：`init_encoding.ps1` 未创建，80个.ps1 dot-source迁移未执行。macOS Python环境不需要这些PowerShell编码初始化器。§2.2(encoding layer 3)和§3 Phase1(step 1.2-1.3)标注为"macOS已废弃"。
> 设计人：情墨（系统架构师）
> 代码分级：L0（基础设施层，不涉及评分/交易/风控逻辑）
> 关联需求：编码问题根治 + 脚本去重 + PS→PY迁移 + 配置中心化

---

## 一、问题诊断

### 1.1 当前痛点

| 问题 | 根因 | 影响面 |
|:-----|:-----|:------|
| PowerShell 编码乱码反复出现 | 无统一编码基础设施，80个.ps1各自处理 | 全部脚本 |
| 中文注释/字符串偶发乱码 | 无 BOM → PS 5.1 按 GBK(936) 误读 | 全部 .ps1 |
| IDE 保存时编码被破坏 | 无 .editorconfig 锁定 | VSCode 用户 |
| 4份 build_docx.ps1 各自维护 | 复制粘贴扩散 | 每日荐股/事后评估/规则红线/重点股票 |
| 2份 md_to_docx.py 版本不同步 | 同上 | 404行 vs 153行，功能差异不明 |
| gen_daily_html/gen_doc_v2 用 PS 写纯文本操作 | PowerShell 不适合字符串/模板密集型任务 | 报告生成链路 |
| 路径/API/阈值散落各处 | 无集中配置管理 | 全项目 |

### 1.2 根因归类

```
┌─────────────────────────────────────────────┐
│ L1 基础设施层 缺失三个关键模块               │
│                                             │
│ ✗ 编码契约 — 文件层/IDE层/运行时层 全空白    │
│ ✗ 公共库目录 — 代码文件/lib/ 不存在          │
│ ✗ 配置目录 — 代码文件/config/ 不存在         │
│                                             │
│ + 复制粘贴扩散（因缺少公共库，只能复制）       │
│ + PS 滥用（简单文本操作用 PS 而非 Python）    │
└─────────────────────────────────────────────┘
```

---

## 二、目标架构

### 2.1 L1 基础设施层现状 vs 目标

```
BEFORE (现状)                    AFTER (目标)
┌────────────────────┐          ┌────────────────────────────┐
│ L1 基础设施         │          │ L1 基础设施                 │
│ ├── 配置管理(散落)   │          │ ├── 编码契约 ★新增         │
│ ├── 日志系统(散落)   │          │ │   ├── .editorconfig      │
│ ├── 调度引擎         │          │ │   ├── init_encoding.ps1  │
│ └── 版本管理         │          │ │   └── UTF-8 BOM 标准     │
│                    │          │ ├── 公共库 ★新增            │
│ ★ 无编码契约        │          │ │   └── lib/               │
│ ★ 无公共库目录      │          │ │       ├── init_encoding.ps1│
│ ★ 无配置目录        │          │ │       └── (未来扩展)      │
└────────────────────┘          │ ├── 配置中心 ★新增          │
                                │ │   └── config/             │
                                │ │       ├── paths.json      │
                                │ │       ├── api_config.json │
                                │ │       └── thresholds.json │
                                │ ├── 配置管理(集中)           │
                                │ ├── 日志系统                 │
                                │ ├── 调度引擎                 │
                                │ └── 版本管理                 │
                                └────────────────────────────┘
```

### 2.2 编码三层防御

```
┌──────────────────────────────────────────────────┐
│                  编码三层防御                      │
│                                                  │
│  第1层 文件层                                      │
│  ┌──────────────────────────────────────────┐   │
│  │ UTF-8 with BOM                           │   │
│  │ 范围：所有 .ps1 / .psm1                   │   │
│  │ 原因：PS 5.1 无BOM→按936(GBK)解析中文     │   │
│  │ 验证：check_redlines.ps1 新增编码检查项    │   │
│  └──────────────────────────────────────────┘   │
│                      ↓ 兜底                       │
│  第2层 IDE层                                      │
│  ┌──────────────────────────────────────────┐   │
│  │ .editorconfig                            │   │
│  │ 范围：项目根目录                           │   │
│  │ 作用：VSCode 保存时强制 utf-8-bom         │   │
│  │ 覆盖：.ps1/.psm1/.py/.md                  │   │
│  └──────────────────────────────────────────┘   │
│                      ↓ 兜底                       │
│  第3层 运行时层                                    │
│  ┌──────────────────────────────────────────┐   │
│  │ init_encoding.ps1                        │   │
│  │ 位置：代码文件/lib/init_encoding.ps1       │   │
│  │ 注入：所有.ps1入口 dot-source              │   │
│  │ 设置：                                    │   │
│  │   [Console]::OutputEncoding = UTF8        │   │
│  │   $PSDefaultParameterValues['*:Encoding'] │   │
│  │   $OutputEncoding = UTF8                  │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

### 2.3 去重后目录结构

```
BEFORE (重复)                        AFTER (统一)

build_docx.ps1 ×4                   代码文件/tools/build_docx.ps1 ← 唯一入口
├── 每日荐股/分析逻辑/build_docx.ps1      ├── 每日荐股/分析逻辑/ → 调用 tools/
├── 每日荐股/事后评估/build_docx.ps1      ├── 每日荐股/事后评估/ → 调用 tools/
├── 规则红线/build_docx.ps1              ├── 规则红线/         → 调用 tools/
└── 重点股票/分析逻辑/build_docx.ps1      └── 重点股票/分析逻辑/ → 调用 tools/

md_to_docx.py ×2                    代码文件/tools/md_to_docx.py ← 404行版本(权威)
├── 代码文件/tools/md_to_docx.py        代码文件/每日荐股/分析逻辑/md_to_docx.py → 删除
└── 代码文件/每日荐股/分析逻辑/...       (153行旧版，功能合并到tools版)

gen_doc.ps1 ×2                      代码文件/重点股票/分析逻辑/gen_doc.ps1 ← 418行主实现
├── 代码文件/重点股票/分析逻辑/...       重点股票/分析逻辑/gen_doc.ps1 → 改为薄包装器
└── 重点股票/分析逻辑/gen_doc.ps1       (17行→改为调用主实现)
```

### 2.4 PS→PY 迁移目标

```
BEFORE                               AFTER

gen_daily_html.ps1                   gen_daily_html.py
├── 功能：HTML报告生成                 ├── 同功能，Python实现
├── 本质：字符串拼接+模板替换           ├── 优势：jinja2模板/f-string
└── 问题：PS字符串转义地狱             └── 编码天然UTF-8

gen_doc_v2.ps1                      gen_doc_v2.py
├── 功能：DOCX报告生成                 ├── 同功能，Python实现
├── 本质：数据读取+模板渲染+样式         ├── 优势：python-docx原生
└── 问题：COM Word不稳定               └── 编码天然UTF-8
```

### 2.5 配置中心化

```
代码文件/config/
├── paths.json          # 所有目录路径
│   ├── data_dir        # 数据目录
│   ├── output_dir      # 输出目录
│   ├── cache_dir       # 缓存目录
│   ├── log_dir         # 日志目录
│   └── temp_dir        # 临时目录
├── api_config.json     # API配置
│   ├── endpoints       # 各API端点URL
│   ├── timeout         # 超时设置(按源)
│   ├── retry           # 重试策略(按源)
│   └── rate_limit      # 频率控制(按源)
└── thresholds.json     # 阈值配置
    ├── scoring         # 评分相关阈值
    ├── risk            # 风控相关阈值
    └── trading         # 交易相关阈值
```

读取接口：所有脚本通过统一函数 `Get-ProjectConfig` / `load_config()` 读取，不再硬编码。

---

## 三、实施路线图

### Phase 1: 编码基础设施 (P0 + 用户3项)
**预估**: 1-2h | **类型**: L0基础设施 | **风险**: 极低

| 步骤 | 交付物 | 执行者 |
|:----:|:------|:-----:|
| 1.1 | 创建 `.editorconfig`（项目根目录） | 阿黑 |
| 1.2 | 创建 `代码文件/lib/init_encoding.ps1` | 红结 |
| 1.3 | 全项目 80 个 .ps1 入口 dot-source 注入 | 红结 |
| 1.4 | `check_redlines.ps1` 新增编码检查项 | 红结 |
| 1.5 | 新安验证：编码检查 PASS，无乱码回归 | 新安 |

**dot-source 注入规范**：
```
# 在每个 .ps1 文件第1行（param()块之前，如有）插入：
. "$PSScriptRoot/../../lib/init_encoding.ps1"    # 按相对深度调整 ../
```

### Phase 2: 脚本去重 (P1)
**预估**: 2h | **类型**: L0工具层 | **风险**: 低

| 步骤 | 交付物 | 执行者 |
|:----:|:------|:-----:|
| 2.1 | 统一 `build_docx.ps1` → `代码文件/tools/` | 红结 |
| 2.2 | 4个原位置替换为调用器（1行 dot-source） | 红结 |
| 2.3 | 合并 `md_to_docx.py` 到 tools 版（404行） | 红结 |
| 2.4 | `gen_doc.ps1` 根目录版改为薄包装器 | 红结 |
| 2.5 | 新安验证：4个调用点全部正常生成 DOCX | 新安 |

**build_docx.ps1 统一规格**：
```powershell
# 代码文件/tools/build_docx.ps1 — 唯一权威版本
param([string]$InputFile, [string]$OutputFile)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$converter = Join-Path $scriptDir "md_to_docx.py"
python $converter $InputFile $OutputFile
```

**原位置替换为调用器**：
```powershell
# 每日荐股/分析逻辑/build_docx.ps1 — 调用器
& "$PSScriptRoot/../../../代码文件/tools/build_docx.ps1" @args
```

### Phase 3: PowerShell→Python 迁移 (P2)
**预估**: 半天 | **类型**: L0展示层 | **风险**: 中

| 步骤 | 交付物 | 执行者 |
|:----:|:------|:-----:|
| 3.1 | 分析 `gen_daily_html.ps1` 逻辑，写出等价 Python 版 | 红结 |
| 3.2 | 分析 `gen_doc_v2.ps1` 逻辑，写出等价 Python 版 | 红结 |
| 3.3 | 更新调用方（daily_workflow.ps1等）指向 .py 版 | 红结 |
| 3.4 | 新旧输出 Golden Master diff 对比 | 新安 |
| 3.5 | 旧 .ps1 文件加 `_deprecated` 后缀保留（不删除） | 红结 |

**迁移原则**：
- 功能完全等价，输出格式不变
- 旧文件不删除，加 `_deprecated.ps1` 后缀保留 30 天
- Golden Master diff 不一致 → FAIL，打回红结

### Phase 4: 配置中心化 (P3)
**预估**: 1天 | **类型**: L0基础设施 | **风险**: 中

| 步骤 | 交付物 | 执行者 |
|:----:|:------|:-----:|
| 4.1 | 设计 `paths.json` / `api_config.json` / `thresholds.json` Schema | 情墨 |
| 4.2 | 创建 `Get-ProjectConfig` (PS) + `load_config()` (PY) | 红结 |
| 4.3 | 全项目硬编码路径迁移到配置读取 | 红结 |
| 4.4 | 新安验证：修改配置值 → 所有脚本行为正确切换 | 新安 |

**配置读取接口契约**：
```
PowerShell:
  $config = Get-ProjectConfig -Section "paths"
  $dataDir = $config.data_dir

Python:
  from config_loader import load_config
  config = load_config("paths")
  data_dir = config["data_dir"]
```

---

## 四、接口变更影响评估

| 变更 | 影响模块 | 影响角色 | 风险 |
|:-----|:--------|:--------|:----:|
| 新增 `init_encoding.ps1` | 全部 80 个 .ps1（只加1行） | 红结(实施) 新安(验证) | 极低 |
| 新增 `.editorconfig` | VSCode 用户 | 无 | 无 |
| 统一 `build_docx.ps1` | 4个调用点 | 红结 新安 | 低 |
| 合并 `md_to_docx.py` | 每日荐股报告生成链 | 新安(回归) | 中 |
| `gen_daily_html.ps1→py` | daily_workflow.ps1 | 新安(全量对比) | 中 |
| `gen_doc_v2.ps1→py` | 每日荐股DOCX报告链 | 新安(全量对比) | 中 |
| 配置中心化 | 所有读配置的脚本 | 红结 新安 | 中 |

---

## 五、风险与回退

| 风险 | 概率 | 缓解 | 回退方案 |
|:-----|:----:|:-----|:--------|
| dot-source 路径计算错误 | 中 | 统一用 `$PSScriptRoot` + 相对路径，逐文件验证 | 撤回该行即可，无副作用 |
| md_to_docx.py 合并后功能缺失 | 低 | diff 对比 404行 vs 153行，合并差异功能 | 保留旧文件 30 天 |
| Python 版报告输出不一致 | 中 | Golden Master diff 门禁，不一致不进下一步 | 旧 .ps1 保留，恢复调用 |
| 配置迁移遗漏 | 中 | grep 全项目硬编码路径，建迁移清单逐项勾 | 旧硬编码仍可工作（双读过渡期） |

---

## 六、需求→代码核对清单

> 情墨 + 腰子 共同勾签后放行至红结

| 编号 | 需求 | 设计覆盖 | 情墨✓ | 腰子✓ |
|:----:|:-----|:-------|:-----:|:-----:|
| R1 | 所有 .ps1 统一 UTF-8 BOM | §2.2 第1层 | ☐ | ☐ |
| R2 | .editorconfig 锁定编码 | §2.2 第2层 | ☐ | ☐ |
| R3 | 脚本入口统一编码声明 | §2.2 第3层 + §3 Phase1 | ☐ | ☐ |
| R4 | 4个 build_docx.ps1 去重 | §2.3 + §3 Phase2 | ☐ | ☐ |
| R5 | 2个 md_to_docx.py 去重 | §2.3 + §3 Phase2 | ☐ | ☐ |
| R6 | gen_doc.ps1 去重 | §2.3 + §3 Phase2 | ☐ | ☐ |
| R7 | gen_daily_html PS→PY | §2.4 + §3 Phase3 | ☐ | ☐ |
| R8 | gen_doc_v2 PS→PY | §2.4 + §3 Phase3 | ☐ | ☐ |
| R9 | 配置中心化 | §2.5 + §3 Phase4 | ☐ | ☐ |
| R10 | 不删除任何 PDF/旧文件 | §3 保留30天+_deprecated | ☐ | ☐ |
| R11 | 不改变评分/交易/风控逻辑 | L0级别，仅基础设施 | ☐ | ☐ |
| R12 | 编码检查加入 redlines | §3 Phase1.4 | ☐ | ☐ |

---

## 七、架构决策记录 (ADR)

### ADR-008: 编码基础设施三层防御

- **决策**：采用文件层(BOM) + IDE层(.editorconfig) + 运行时层(init_encoding.ps1) 三层防御
- **替代方案**：仅运行时层 → 不选，因为文件被非 VSCode 编辑器打开时仍会破坏编码
- **替代方案**：全项目迁 PowerShell 7 → 不选，pwsh 7 仍需 BOM，且引入迁移成本
- **权衡**：三层有少量冗余，但每层防御不同攻击面，冗余是设计意图

### ADR-009: PS→PY 迁移边界

- **决策**：仅迁移"纯字符串/模板操作"类脚本，保留"Windows 调度/COM"类脚本
- **原则**：Python 做数据处理和报告生成，PowerShell 做系统调度和胶水
- **边界**：不为了"全 Python"而强行迁移 Windows 绑定脚本

### ADR-010: 配置中心化格式选择

- **决策**：使用 JSON 格式 + 统一读取函数
- **替代方案**：YAML → 不选，需额外依赖
- **替代方案**：环境变量 → 不选，结构化配置(嵌套对象/数组)不便
- **理由**：JSON 是 PS 和 Python 原生支持的共同格式

---

> **文档版本**: v1.0 | **设计人**: 情墨 | **pipeline_stage**: complete
> **下一步**: 腰子确认闸门1a → 新安+旧影闸门1b → 红结实施
