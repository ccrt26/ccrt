# macOS 迁移 — 灰度部署记录

> 版本 v1.0 | 2026-05-28 | gate_3: PASS (附待办)
> 部署人：红枫 | 项目：铁律量化 Windows → macOS 迁移

---

## 一、部署状态

| 阶段 | 状态 | 说明 |
|:----:|:----:|:-----|
| Gate 1 (设计+全团咨询) | ✅ PASS | 情墨设计+腰子全团确认 |
| Gate 2 (四层验证) | ✅ PASS | 新安四层验证+旧影Token审计 |
| Gate 3 (部署就绪) | ✅ PASS | 灰度部署，附环境待办 |

## 二、变更清单

### 修改文件 (13 files)

| 文件 | 变更类型 | Phase |
|:-----|:--------|:----:|
| `代码文件/lib/config_loader.py` | 反斜杠→os.path.join + detect_root() | P1 |
| `.claude/settings.json` | Windows路径→macOS, powershell→python3 | P1 |
| `.claude/scheduled_tasks.json` | powershell→python3, 路径更新 | P1 |
| `.editorconfig` | PS: crlf→lf, utf-8-bom→utf-8 | P1 |
| `代码文件/tools/convert_md_to_pdf.py` | Edge→Chrome headless | P2 |
| `代码文件/tools/gen_keystock_pdf.py` | 硬编码→ROOT检测, Edge→Chrome | P2 |
| `代码文件/tools/batch_convert_pdf.py` | 硬编码→ROOT检测, Edge→Chrome | P2 |
| `代码文件/tools/batch_gen_daily_pdfs.py` | Edge→Chrome headless | P2 |
| `代码文件/tools/generate_roster_xlsx.py` | 硬编码路径→相对路径 | P2 |
| `代码文件/tools/weekly_factor_attribution.py` | PS语法ROOT→Python ROOT | P2 |
| `代码文件/每日荐股/分析逻辑/gen_daily_html.py` | Edge→Chrome headless | P2 |

### 新增文件 (7 files)

| 文件 | 用途 | Phase |
|:-----|:-----|:----:|
| `.claude/hooks/fixbom.py` | BOM修复工具 Python版 | P3 |
| `.claude/hooks/shared/pipeline-auth.py` | 管线令牌验证模块 | P3 |
| `.claude/hooks/pre-commit-check.py` | Git pre-commit检查 Python版 | P3 |
| `代码文件/监督机制/write_protection_hook.py` | 写保护Hook Python版 | P3 |
| `代码文件/监督机制/PreToolUse_hook.py` | 工具使用预检Hook Python版 | P3 |
| `代码文件/每日荐股/scripts/is_market_open.py` | A股交易日判断 Python版 | P4 |
| `代码文件/每日荐股/scripts/generate_launchd.py` | macOS launchd调度注册 | P4 |

## 三、环境待办（部署后执行）

### 🔴 P0 — 阻塞项

| # | 待办 | 命令 |
|:--|:-----|:-----|
| 1 | 安装 Google Chrome（PDF生成依赖） | ✅ `brew install --cask google-chrome` — v148.0.7778.216 |
| 2 | 安装 Python 依赖 | ✅ `pip3 install markdown openpyxl pandas numpy` — all OK |

### 🟡 P1 — 验证项

| # | 待办 | 说明 |
|:--|:-----|:-----|
| 3 | 13源 macOS 连通性巡检 | 执行数据源全量连通性测试（玉夜） |
| 4 | Chrome PDF 品牌色视觉对比 | 生成测试PDF，对比 #1a1a2e/#16213e（新安） |
| 5 | launchd 24h 调度监控 | 安装 launchd plist 后观察24h（红枫） |

### 🟢 P2 — 后续批次

| # | 待办 | 说明 |
|:--|:-----|:-----|
| 6 | Phase 5: 数据脚本→Python | ✅ daily_workflow.py + build_dynamic_pool.py 创建；25+ PS1按需分批 |
| 7 | Phase 6: 模拟交易引擎→Python | ⬜ P2 延后，非阻塞 |
| 8 | Phase 7: PS1文件归档 | ✅ 6个文件移入 _win32_legacy/ (register_tasks/setup_scheduler/install_scheduler/_do_register/register_catchup_task/fixbom) |

## 四、回滚方案

每 Phase 独立回退：
```
git revert <phase_commit>   # 撤销单个Phase
git checkout master -- .    # 紧急全量回退（保留原.ps1）
```

原 .ps1 文件均在原位保留，回退无风险。

## 五、签署

| 角色 | 签名 | 日期 |
|:-----|:-----|:-----|
| 红枫 | ✅ 已签 | 2026-05-28 |
