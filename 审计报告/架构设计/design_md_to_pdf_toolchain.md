# 架构设计：MD→PDF 转换工具链

> **pipeline_stage**: ① 架构设计 | **pipeline_stage: complete**
> **设计者**: 情墨 | **审查者**: 腰子 | **finance_confirmed: true**
> **日期**: 2026-05-25
> **关联需求**: 重点股票深度分析 Markdown 报告 → 批量生成正式 PDF
> **代码等级**: L0（工具/数据/缓存）
>
> **腰子确认意见**：设计方案合理。Python markdown + Edge headless 双段管道是 Windows 环境下唯一可行方案。日期一致性预检是上次东睦日期不一致问题的直接修复。品牌CSS样式与报告基线一致。无金融分析逻辑涉及，无须全团咨询即可确认。同意流入下一阶段。

---

## 一、需求分析

### 1.1 输入
- 8份 Markdown 深度分析报告（`临时报告/<代码>_<名称>_深度分析_20260525.md`）
- 报告长度：150-320 行 Markdown，含表格、代码块、引用块

### 1.2 输出
- 8份 PDF 报告（`重点股票/股票报告/<名称>(<代码>)/<名称>(<代码>)分析报告__20260525.pdf`）
- PDF 使用品牌样式（#1a1a2e / #16213e）

### 1.3 约束
- Windows 环境（无 pandoc，无 weasyprint GTK 依赖）
- 可用：Python markdown 库 + Edge headless 浏览器
- 批量模式：8 份串行或依次处理

### 1.4 v3.3 白皮书要求
- §A.1 报告自检清单：日期一致、数据源标注、无编造数字
- 批量生成前需执行日期一致性预检

---

## 二、技术选型

### 2.1 MD → HTML 转换

| 方案 | 优点 | 缺点 | 结论 |
|:-----|:-----|:-----|:----|
| **Python markdown** | pip 已安装，支持 tables/fenced_code 扩展 | 需自行编写 CSS | **选用** |
| pandoc | 功能全面，模板丰富 | Windows 未安装，需额外部署 | 不选 |
| 手写 HTML | 完全可控 | 重复劳动，不可维护 | 不选 |

### 2.2 HTML → PDF 转换

| 方案 | 优点 | 缺点 | 结论 |
|:-----|:-----|:-----|:----|
| **Edge headless** | Windows 内置，零依赖，已验证可行（batch_convert_pdf.py 即用此方案） | 命令行参数含中文路径时编码需注意 | **选用** |
| weasyprint | Python 原生，字体控制精确 | Windows 缺 GTK/Pango 库，无法运行 | 不选 |
| pyhtml2pdf | 简单 | 质量差，表格支持弱 | 不选 |

### 2.3 技术决策理由

选择"Python markdown + Edge headless"两段式管道：
- **零新依赖**：markdown 库已安装，Edge 为系统内置
- **已验证路径**：`batch_convert_pdf.py`（2026-05-22）使用相同方案成功产出 8 份 PDF
- **权衡**：两段式比 weasyprint 多一个中间 HTML 文件，但避免了 GTK 环境问题——在 Windows 上稳定性优先于优雅性

---

## 三、模块设计

### 3.1 模块划分（2 文件）

```
代码文件/tools/
├── convert_md_to_pdf.py    # L0 — 核心：单文件 MD→HTML→PDF
└── batch_gen_keystock_pdfs.py  # L0 — 编排：8 只股票批量 + 预检
```

### 3.2 模块 1：convert_md_to_pdf.py

**职责**：单文件 MD → PDF 转换
**等级**：L0（工具/数据）
**预估行数**：~120 行

**函数接口**：

```python
def find_edge() -> str | None:
    """定位 Edge 浏览器可执行文件路径"""

def md_to_html_body(md_text: str) -> str:
    """Markdown 文本 → 带 CSS 的 HTML body"""

def convert(md_path: str, pdf_path: str, edge_path: str | None = None) -> bool:
    """单文件转换主函数。返回 True/False。
    Side effect: 在同目录生成中间 .html 文件"""
```

**数据流**：
```
md_path ──read──▶ md_text ──markdown──▶ html_body ──wrap──▶ full_html
    ──write──▶ .html 文件 ──Edge headless──▶ .pdf 文件
```

**错误处理**：
- MD 文件不存在 → 打印 ERROR 并返回 False
- Edge 浏览器找不到 → 打印 ERROR 并返回 False
- PDF 生成后 size < 5KB → 判定失败

**CSS 常量**：嵌入模块顶部的 CSS 字符串，品牌色 #1a1a2e / #16213e，涨 #e74c3c / 跌 #27ae60。

### 3.3 模块 2：batch_gen_keystock_pdfs.py

**职责**：8 只重点股票批量编排 + 生成前预检
**等级**：L0（工具/数据）
**预估行数**：~60 行

**流程**：
```
1. 日期一致性预检（preflight）
   ├─ 遍历 8 个 MD 文件
   ├─ 提取每份报告的日期行
   ├─ 检查：日期行一致？文件名日期一致？全部为 2026-05-25？
   └─ 不通过 → 打印差异报告并 exit(1)
2. 批量转换
   ├─ 遍历 STOCKS 列表
   ├─ 调用 convert_md_to_pdf.convert()
   └─ 汇总 OK/FAIL 计数
3. 输出报告
```

**STOCKS 配置**（hardcoded，非运行时参数）：
```python
STOCKS = [
    ("600036_招商银行_深度分析_20260525.md", "招商银行(600036)", "招商银行(600036)分析报告__20260525.pdf"),
    # ... 其余 7 只
]
```

### 3.4 为什么不合并为一个文件？

两个理由分开：
1. **单一职责**：convert 模块可单独调用（单只股票临时转换），batch 模块专注于编排逻辑
2. **测试独立**：convert 模块可单独测试（传入测试 MD → 验证 PDF），不依赖 batch 逻辑

两个文件合计 < 200 行，远低于 500 行红线。

---

## 四、接口契约

### 4.1 文件路径约定

| 项目 | 路径模板 |
|:-----|:--------|
| 源 MD | `临时报告/<代码>_<名称>_深度分析_20260525.md` |
| 目标 PDF | `重点股票/股票报告/<名称>(<代码>)/<名称>(<代码>)分析报告__20260525.pdf` |
| 中间 HTML | 与目标 PDF 同目录同名 .html（生成后保留，便于调试） |

### 4.2 命名规范

- 文件名日期：`20260525`（YYYYMMDD）
- 报告内日期：`2026年5月25日`
- 数据截止日：`基于5月22日收盘数据`（最新交易日）

### 4.3 向后兼容

- 现有 `batch_convert_pdf.py` 保持不变（它做 HTML→PDF，不同职责）
- 现有 `gen_keystock_pdf.ps1` 保持不变（通用 HTML→PDF 转换器）
- 新模块是**新增**，不替换任何现有工具

---

## 五、样式规格

继承自 `报告样式基线_v1.2.md` + 品牌色规范：

| 元素 | 规格 |
|:-----|:-----|
| 页面 | A4, margin 15mm 18mm |
| 标题 H1 | 22px, #1a1a2e, 底部 2px 实线 |
| 标题 H2 | 17px, #16213e, 底部 1.5px 实线 |
| 表格 TH | 背景 #1a1a2e, 白色文字 |
| 表格 TD | 边框 #ddd, 偶数行背景 #f8f9fa |
| 涨/看多 | #e74c3c |
| 跌/看空 | #27ae60 |
| 免责声明 | 11px, #999, 顶部分割线 |

---

## 六、风险与权衡

| 风险 | 等级 | 缓解 |
|:-----|:----|:-----|
| Edge 版本更新改变 headless 行为 | 低 | --no-pdf-header-footer 是稳定参数 |
| 中文路径编码问题 | 中 | 使用 os.path.join 拼接，避免 stdin 管道传中文路径 |
| 中间 HTML 文件残留 | 低 | 保留不删（便于调试，体积小） |
| 非线程安全 | 低 | 串行调用，每次 subprocess.run 后等待 1.5s |

---

## 七、需求→代码核对清单

> 情墨 + 腰子共同勾签后放行（§九.2）

| # | 需求项 | 对应代码位置 | 验证方式 |
|:--|:------|:----------|:--------|
| 1 | MD→HTML 转换 | `convert_md_to_pdf.py` → `md_to_html_body()` | 传入测试 MD，检查 HTML 输出 |
| 2 | 品牌 CSS 样式 | `convert_md_to_pdf.py` → `CSS` 常量 | 目视检查 PDF 颜色 |
| 3 | HTML→PDF via Edge | `convert_md_to_pdf.py` → `convert()` | 检查 PDF 文件生成且 > 5KB |
| 4 | 日期一致性预检 | `batch_gen_keystock_pdfs.py` → `preflight()` | 故意制造不一致日期验证拒绝 |
| 5 | 8 只股票批量 | `batch_gen_keystock_pdfs.py` → `STOCKS` 列表 | 计数 OK=8 |
| 6 | 错误处理 | `convert()` 返回 bool | 传入不存在路径验证 False |
| 7 | 单文件 ≤ 500 行 | 两个文件均 < 200 行 | `wc -l` |
| 8 | L0 代码等级标注 | 设计文档 §三 + 代码文件头注释 | grep L0 |
