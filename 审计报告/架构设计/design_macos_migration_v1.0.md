# macOS 迁移 — 架构设计文档

> 版本 v1.0 | 2026-05-28 | pipeline_stage: complete
> 设计人：情墨 | 项目：铁律量化 Windows → macOS 迁移
> 变更类型：E类工程变更 | 风险等级：🟠 R3（全局基础设施变更）

---

## 零、设计摘要

**目标**：将铁律量化项目从 Windows（PowerShell + Edge + Task Scheduler）迁移至 macOS，保持核心评分引擎和数据链路不变。

**核心策略**：Python 核心不动，PowerShell 脚本按优先级重写为 Python（非 Bash），PDF 引擎切 Chrome headless，调度切 launchd。

**Token 影响评估**：
- 模板体积：新增 ~15 个 Python 脚本，复用现有 engine/lib 代码，不新增 agent 知识文件
- 输出模式：脚本输出格式不变（JSON/CSV/MD/HTML/PDF），下游消费者无感知
- API 调用：数据源 API 调用次数无变化；迁移过程需 WebSearch 验证 macOS 工具链兼容性（预计 ≤5 次）
- 评估：Token 增量可控，迁移完成后日常 Token 消耗与 Windows 持平

---

## 一、模块归属与影响分析

### 1.1 受影响模块清单

| 层 | 受影响文件 | 当前形态 | 目标形态 | 代码分级 | 风险 |
|:---|:-----|:--------|:--------|:-------:|:---:|
| 配置层 | `代码文件/config/paths.json` | Windows 路径 | macOS 路径 | L0 | 🟢 |
| 配置层 | `代码文件/lib/config_loader.py` | `\\` 反斜杠 | `os.path.join` | L0 | 🟢 |
| 配置层 | `.claude/settings.json` | Windows hooks + MCP path | macOS hooks + MCP path | L0 | 🟡 |
| 配置层 | `.claude/scheduled_tasks.json` | Windows 路径 | macOS 路径 | L0 | 🟡 |
| 钩子层 | `.claude/hooks/fixbom.ps1` | PS | Python | L2 | 🟡 |
| 钩子层 | `.claude/hooks/pre-commit-check.ps1` | PS | Python | L2 | 🟠 |
| 钩子层 | `.claude/hooks/shared/pipeline-auth.ps1` | PS | Python | L2 | 🟡 |
| 工具层 | `代码文件/tools/gen_keystock_pdf.py` | 硬编码路径 | 动态 ROOT | L1 | 🟡 |
| 工具层 | `代码文件/tools/batch_convert_pdf.py` | 硬编码路径 | 动态 ROOT | L1 | 🟡 |
| 工具层 | `代码文件/tools/batch_gen_daily_pdfs.py` | 硬编码路径 | 动态 ROOT | L1 | 🟡 |
| 工具层 | `代码文件/tools/convert_md_to_pdf.py` | Edge 路径 | Chrome headless | L1 | 🟡 |
| 工具层 | `代码文件/tools/generate_roster_xlsx.py` | 硬编码路径 | 动态 ROOT | L1 | 🟢 |
| 工具层 | `代码文件/tools/weekly_factor_attribution.py` | PS 获取 ROOT | 动态 ROOT | L1 | 🟡 |
| 调度层 | 所有 `*.ps1` 调度/工作流脚本 | PS | Python + launchd | L1-L2 | 🟠 |
| 监督层 | 所有 `*.ps1` 检查脚本 | PS | Python | L1 | 🟡 |
| 报告层 | `代码文件/每日荐股/分析逻辑/gen_daily_html.py` | Edge PDF | Chrome headless | L1 | 🟡 |

### 1.2 不受影响模块（无需改动）

| 层 | 文件 | 原因 |
|:---|:-----|:-----|
| 计算层 | `代码文件/每日荐股/分析逻辑/engine/*.py` (9文件) | 纯 Python，无 OS 依赖 |
| 数据层 | `代码文件/每日荐股/scripts/stock_data_fetcher_*.py` (7文件) | 纯 Python，API 调用跨平台 |
| 服务层 | `代码文件/tools/financial_mcp_server.py` | 纯 Python MCP server |
| 工具层 | `代码文件/tools/md_to_docx.py` | 纯 Python |
| 展示层 | `代码文件/信鸽信息采集/generate_portal.py` | 纯 Python |
| 展示层 | `代码文件/信鸽信息采集/pigeon_server.py` | 纯 Python |
| 配置层 | `代码文件/config/api_config.json` | 平台无关 |
| 配置层 | `代码文件/config/thresholds.json` | 平台无关 |
| 所有 Agent 定义 | `.claude/agents/*.md` | 平台无关 |
| 所有 Command 定义 | `.claude/commands/*.md` | 平台无关 |
| 所有知识库 | `.claude/knowledge/*.md` | 平台无关 |
| 规则红线 | `规则红线/*.md` | 平台无关 |

---

## 二、技术决策（ADR）

### ADR-1: PowerShell → Python（非 Bash）

**决策**：所有 .ps1 脚本重写为 Python，不使用 Bash。

**理由**：
1. 项目已有的 Python 资产（engine/、tools/、scripts/）证明团队 Python 能力强
2. Python 跨平台原生，macOS 自带 Python 3
3. Bash 处理 JSON/CSV 复杂数据结构能力弱，Python 的 `json`/`csv`/`pandas` 生态成熟
4. 统一技术栈降低维护成本——迁移后项目只有 Python + Markdown，消除 PS/Python 混合架构

**权衡**：部分系统交互（文件权限、进程管理）Python 不如 Bash 简洁，但 `subprocess`/`os`/`shutil` 足够覆盖本项目需求。

### ADR-2: PDF 引擎 → Google Chrome headless

**决策**：统一使用 Chrome headless `--headless --print-to-pdf`，废弃 Edge 无头模式。

**理由**：
1. macOS 预装 Chrome 概率高（或 `brew install google-chrome` 一行安装）
2. 项目报告模板是 HTML + 冻结 CSS，Chrome 渲染效果与 Edge 一致
3. 替代方案 wkhtmltopdf 对 CSS3 支持不完整，品牌色/渐变可能失真

**备选**：若 Chrome 不可用，降级为 `wkhtmltopdf`（`brew install wkhtmltopdf`），但需验证品牌色输出。

### ADR-3: 调度 → launchd（非 cron）

**决策**：macOS 定时任务使用 launchd plist，由 Python 脚本自动生成 plist 文件。

**理由**：
1. launchd 是 macOS 原生调度系统，支持间隔/日历/文件变更等多种触发方式
2. cron 在 macOS 上需要额外权限配置，且不支持开机自检
3. launchd 支持环境变量注入、工作目录指定、标准输出/错误日志——覆盖原 Windows Task Scheduler 功能

**权衡**：plist XML 格式比 cron 语法啰嗦，但由 Python 脚本自动生成，用户无需手写。

### ADR-4: ROOT 路径 → 单一自动检测

**决策**：在 `config_loader.py` 中实现 `detect_root()` 函数，所有模块统一通过此函数获取项目根目录。

**实现方案**：
```python
def detect_root():
    """从当前文件向上查找包含 CLAUDE.md 的目录"""
    p = Path(__file__).resolve().parent
    for _ in range(10):
        if (p / "CLAUDE.md").exists():
            return str(p)
        p = p.parent
    return os.getcwd()  # fallback
```

所有硬编码 `C:\Users\34269\...` 替换为 `os.path.join(ROOT, "相对路径")`。

### ADR-5: Hook 脚本 → Python

**决策**：`.claude/hooks/` 下 3 个 .ps1 重写为 .py，settings.json 中 hook 命令从 `powershell -File ...` 改为 `python3 ...`。

### ADR-6: 编码统一 → UTF-8（无 BOM）

**决策**：所有文件统一 UTF-8 without BOM，LF 换行。

**理由**：原 Windows 项目大量使用 UTF-8-BOM（PS 默认），macOS/Linux 工具链默认 UTF-8 without BOM。统一编码避免中文乱码。

**特殊处理**：
- 读取历史数据文件时兼容 BOM（`encoding="utf-8-sig"`）
- 新写入文件统一 `encoding="utf-8"`（无 BOM）
- `.editorconfig`：`end_of_line = lf`，删除 PS1 的 crlf 特例

---

## 三、接口契约

### I-macOS-1: ROOT 检测接口

```
函数：detect_root()
输入：无
输出：str — 项目根目录绝对路径
异常：无（有 fallback 到 cwd）
契约：返回值末尾不含路径分隔符
```

### I-macOS-2: PDF 生成统一接口

```
函数：md_to_pdf(md_path: str, pdf_path: str, css: str = None) -> bool
输入：
  - md_path: Markdown 文件路径
  - pdf_path: 输出 PDF 路径
  - css: 可选 CSS 样式字符串（不传则使用冻结 CSS）
输出：bool — 成功/失败
副作用：在同目录生成临时 HTML 文件，PDF 生成后清理
异常：Chrome 不可用时降级 wkhtmltopdf，两者都不可用抛 RuntimeError
```

### I-macOS-3: 调度配置接口

```
函数：generate_launchd_plist(task_name: str, command: str, schedule: dict, working_dir: str = None) -> str
输入：
  - task_name: 任务唯一标识（如 "tielv-daily-workflow"）
  - command: 完整命令行（如 "python3 /path/to/script.py"）
  - schedule: {"type": "interval"|"calendar", "value": ...}
  - working_dir: 工作目录，默认 ROOT
输出：plist 文件路径
副作用：写入 ~/Library/LaunchAgents/{task_name}.plist
```

### 现有接口不变更

以下现有接口契约不做任何变更：
- I1-I8（数据获取→缓存→评分→报告→交易）
- 评分引擎输入输出 JSON Schema
- MCP Server HTTP API

---

## 四、迁移优先级与分批策略

### Phase 1: 基础配置（P0 — 让项目能加载）

| 文件 | 变更 | 代码分级 |
|:-----|:-----|:-------:|
| `代码文件/config/paths.json` | rootDir → macOS 路径 | L0 |
| `代码文件/lib/config_loader.py` | 反斜杠 → os.path.join | L0 |
| `.claude/settings.json` | hooks 路径 + MCP 路径 | L0 |
| `.claude/scheduled_tasks.json` | 任务路径更新 | L0 |
| `.editorconfig` | CRLF → LF | L0 |

### Phase 2: 核心工具（P0 — 让关键功能可用）

| 文件 | 变更 | 代码分级 |
|:-----|:-----|:-------:|
| `代码文件/tools/convert_md_to_pdf.py` | Edge → Chrome headless | L1 |
| `代码文件/tools/gen_keystock_pdf.py` | 路径 + 引擎 | L1 |
| `代码文件/tools/batch_convert_pdf.py` | 路径 + 引擎 | L1 |
| `代码文件/tools/batch_gen_daily_pdfs.py` | 路径 + 引擎 | L1 |
| `代码文件/tools/generate_roster_xlsx.py` | 路径 | L1 |
| `代码文件/tools/weekly_factor_attribution.py` | 路径 | L1 |
| `代码文件/每日荐股/分析逻辑/gen_daily_html.py` | 引擎 | L1 |

### Phase 3: 钩子与监督（P1 — 让 CI/检查工作）

| 文件 | 变更 | 代码分级 |
|:-----|:-----|:-------:|
| `.claude/hooks/fixbom.ps1` → `.py` | 重写为 Python | L2 |
| `.claude/hooks/pre-commit-check.ps1` → `.py` | 重写为 Python | L2 |
| `.claude/hooks/shared/pipeline-auth.ps1` → `.py` | 重写为 Python | L2 |
| `代码文件/规则红线/check_redlines.ps1` → `.py` | 重写为 Python | L1 |
| `代码文件/规则红线/build_docx.ps1` → `.py` | 重写为 Python | L1 |
| `代码文件/监督机制/version_supervisor.ps1` → `.py` | 重写为 Python | L1 |

### Phase 4: 调度（P1 — 让自动化跑起来）

| 文件 | 变更 | 代码分级 |
|:-----|:-----|:-------:|
| `代码文件/每日荐股/scripts/daily_workflow.ps1` → `.py` | 重写为 Python | L1 |
| `代码文件/每日荐股/scripts/batch_data_collector.ps1` → `.py` | 重写为 Python | L1 |
| 调度注册 → `generate_launchd.py` | 新建 | L1 |
| `代码文件/每日荐股/scripts/is_market_open.ps1` → `.py` | 重写为 Python | L1 |

### Phase 5: 数据采集（P1 — 让数据管道完整）

| 文件 | 变更 | 代码分级 |
|:-----|:-----|:-------:|
| `代码文件/每日荐股/scripts/stock_data_fetcher.psm1` → `.py` | 重写核心为 Python | L1 |
| 其余 25+ .ps1 数据/评估脚本 | 按使用频率分批重写 | L1 |

### Phase 6: 模拟交易（P2 — 非阻塞）

| 文件 | 变更 | 代码分级 |
|:-----|:-----|:-------:|
| `模拟交易/交易引擎/sim_trading.ps1` → `.py` | 重写为 Python | L2 |
| 其余 10+ .ps1 交易脚本 | 重写为 Python | L2 |

### Phase 7: 归档（P3 — 删除废弃文件）

| 操作 | 说明 |
|:-----|:-----|
| 删除 `register_tasks.ps1` / `setup_scheduler.ps1` / `install_scheduler.ps1` | Windows Task Scheduler 专用，macOS 无用 |
| 删除 `fixbom.ps1` | BOM 修复脚本，编码统一后无 BOM 问题 |
| 保留原始 .ps1 文件在 `_win32_legacy/` | 作为参考，不被任何流程引用 |

---

## 五、数据流不变性保证

```
迁移前（Windows）：
  API → stock_data_fetcher.psm1 → JSON/CSV缓存 → scoring_engine_v2.py 
  → 评分JSON → gen_daily_html.ps1 → HTML → msedge --headless → PDF

迁移后（macOS）：
  API → stock_data_fetcher.py → JSON/CSV缓存 → scoring_engine_v2.py（不变）
  → 评分JSON → gen_daily_html.py → HTML → chrome --headless → PDF
```

**关键不变项**：
- 缓存文件格式（JSON/CSV）不变
- 评分引擎输入输出 Schema 不变
- 报告 HTML 模板 + 冻结 CSS 不变
- MCP Server HTTP API 不变
- Agent/Command 定义不变
- 知识库文件不变
- 规则红线不变

---

## 六、回退方案

每 Phase 独立回退，Phase N 失败不影响 Phase 1~(N-1)：

1. **Git 分支策略**：从 master 创建 `migration/macos` 分支，每个 Phase 一个 commit
2. **回退粒度**：`git revert <phase_commit>` 即可撤销单个 Phase
3. **验证标准**：每 Phase 完成后运行 `python3 scoring_engine_v2.py`（冒烟测试），确认引擎正常
4. **保留原始文件**：Phase 7 前不删除任何 .ps1 文件，仅新增 .py 替代。Phase 7 才移入 `_win32_legacy/`

---

## 七、反模式检查

对照情墨知识库 04-反模式库：

| 反模式 | 触发？ | 说明 |
|:-----|:-----:|:-----|
| AP-01 上帝模块 | ❌ | 每个 .py 替代一个 .ps1，功能一一对应 |
| AP-02 硬编码 | ❌ | 统一 ROOT 检测，消除硬编码 |
| AP-03 跨层调用 | ❌ | 各层边界不变，仅替换实现语言 |
| AP-04 重复代码 | ❌ | PDF 生成统一为 `md_to_pdf()` 函数 |
| AP-05 隐藏依赖 | ❌ | `requirements.txt` 显式声明所有依赖 |
| AP-06 不可测试 | ❌ | Python 脚本比 PS 更易于单元测试 |
| AP-07 文件扩散 | ❌ | 统一使用一个 `md_to_docx.py`，无新副本 |

---

## 八、需求→代码核对清单

> 本迁移为工程变更，不涉及金融需求变更。核对清单聚焦技术合规。

### A. 路径配置

| # | 检查项 | 标准 | 代码对应 | 情墨✓ | 腰子✓ |
|:--|:------|:----|:--------|:-----:|:-----:|
| A1 | rootDir 指向 macOS 用户目录 | `paths.json` | `代码文件/config/paths.json` | ☐ | N/A |
| A2 | 无 `C:\` 硬编码残留 | grep 全项目 | 全部 .py/.json/.md | ☐ | N/A |
| A3 | 无 `\\` 反斜杠路径 | grep 全项目 | 全部 .py | ☐ | N/A |
| A4 | ROOT 检测函数可用 | `detect_root()` | `代码文件/lib/config_loader.py` | ☐ | N/A |

### B. 数据链路

| # | 检查项 | 标准 | 代码对应 | 情墨✓ | 腰子✓ |
|:--|:------|:----|:--------|:-----:|:-----:|
| B1 | 评分引擎冒烟测试通过 | `scoring_engine_v2.py` 零报错 | engine/*.py | ☐ | ☐ |
| B2 | 数据源 API 连通 | 13源巡检通过 | `inspect_data_health.py` | ☐ | ☐ |
| B3 | 缓存格式不变 | JSON Schema 兼容 | data_cache/*.json | ☐ | N/A |

### C. PDF 生成

| # | 检查项 | 标准 | 代码对应 | 情墨✓ | 腰子✓ |
|:--|:------|:----|:--------|:-----:|:-----:|
| C1 | Chrome headless 可用 | `chrome --headless` 正常 | `convert_md_to_pdf.py` | ☐ | N/A |
| C2 | 品牌色输出正确 | `#1a1a2e`/`#16213e` 一致 | 输出 PDF 视觉对比 | ☐ | ☐ |
| C3 | 字体渲染正常 | 中文无乱码/无豆腐块 | 输出 PDF | ☐ | ☐ |

### D. 钩子合规

| # | 检查项 | 标准 | 代码对应 | 情墨✓ | 腰子✓ |
|:--|:------|:----|:--------|:-----:|:-----:|
| D1 | pre-commit 检查可用 | git commit 触发 | `.claude/hooks/pre-commit-check.py` | ☐ | N/A |
| D2 | BOM 处理正确 | UTF-8 without BOM | 全部 .py 文件 | ☐ | N/A |
| D3 | 版本一致性检查可用 | `version_supervisor.py` | `代码文件/监督机制/` | ☐ | N/A |

### E. 文档同步

| # | 检查项 | 标准 | 代码对应 | 情墨✓ | 腰子✓ |
|:--|:------|:----|:--------|:-----:|:-----:|
| E1 | md_to_docx.py 可用 | `python3 md_to_docx.py` | `代码文件/tools/md_to_docx.py` | ☐ | N/A |
| E2 | 版本号一致性 | 文件名 = 内部声明 = CHANGELOG | 全部 .md | ☐ | N/A |
| E3 | 未删除任何 PDF | 红线 §1.7 | `find . -name "*.pdf"` | ☐ | ☐ |

---

## 九、签署

| 角色 | 签名 | 日期 | 结论 |
|:-----|:-----|:-----|:-----|
| 情墨 | ✅ 已签 | 2026-05-28 | ☑ 通过 — 设计完整，6 ADR有理有据，分批策略合理，回退方案完备 |
| 腰子 | ✅ 已签 | 2026-05-28 | ☑ 通过（附条件）— 条件：①Phase2后玉夜13源macOS连通性巡检 ②Phase3流金红线逐条复核 ③Phase4 launchd 24h调度监控 |

> 双签通过后，流入阶段③新安+旧影架构审查。
