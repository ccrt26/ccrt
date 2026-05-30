# 数据运用合规自动检查 — 设计文档 v1.0

> **版本**: v1.0 | **日期**: 2026-05-30 | **制定**: 情墨（架构设计）
> **需求来源**: 腰子全团+工程全团联合讨论，《数据运用优化方案 v1.3》§八审计机制
> **关联方案**: `重点股票/分析逻辑/数据运用优化方案_v1.3.md`

---

## 一、需求概述

将优化方案的执行检查从"事后人工审计"升级为"事前自动闸门"。金融侧玉夜定义检查规则（U-1~U-4），旧影定义进度检查（C-5~C-10）。工程侧实现三层闸门架构。

---

## 二、三层闸门架构

```
第一层 Pre-Report Gate     报告 .md 产出后 → 自动检查 → FAIL 阻断 HTML/PDF 生成
第二层 Daily Audit Gate     audit_scan.py --daily → 自动检查 → FAIL 告警
第三层 Weekly Audit Gate    audit_scan.py --weekly → 自动检查 → FAIL 上报阿黑
```

**集成时序**：
```
第一层（手动阶段，两周）:
  腰子产出 .md → 手动运行 check_data_utilization.py → PASS/FAIL 输出 → 腰子处理

第一层（自动阶段，两周后）:
  腰子产出 .md → 千光集成的 pre-commit/report-gate → 自动运行 → FAIL 阻断 .html 生成

第二/三层（立即自动）:
  audit_scan.py --daily/--weekly → 千光调度 → 自动运行 → FAIL 飞书通知
```

---

## 三、代码清单

### 3.1 新建脚本

| 文件 | 路径 | 代码等级 | 预计行数 | Token预算 |
|:-----|:-----|:------:|:------:|:------:|
| check_data_utilization.py | `scripts/check_data_utilization.py` | **L0** | ~150行 | ≤3K token |

### 3.2 修改现有脚本

| 文件 | 路径 | 代码等级 | 预计新增行数 | Token预算 |
|:-----|:-----|:------:|:------:|:------:|
| audit_scan.py | `scripts/audit_scan.py` | **L1** | +80行 | ≤2K token |
| feishu_bridge.py | `代码文件/tools/feishu_bridge.py` | **L0** | +30行 | ≤1K token |

### 3.3 不涉及的文件

- 评分引擎、报告生成脚本、数据管线、样式定义 — 本次不改
- 旧影知识库 01 — 审计方法已更新（C-5~C-10+C-8b），不做额外改动
- 优化方案 v1.3.md — 本次完成后更新§八.7引用新脚本

---

## 四、check_data_utilization.py 详细设计

### 4.1 函数签名

```python
def check_report(report_path: str, report_type: str) -> dict:
    """
    返回:
    {
        "pass": bool,
        "u1": {"pass": bool, "count": int, "threshold": int, "sources": list},
        "u2": {"pass": bool, "total": int, "missing": list, "details": dict},
        "u3": {"pass": bool, "has_structure": bool},
        "u4": {"pass": bool, "missing_rate": float, "threshold": float},
        "failures": [str, ...]
    }
    """
```

### 4.2 CLI 接口

```
python3 scripts/check_data_utilization.py --report <path> --type <depth_analysis|daily>
```

退出码：0 = PASS，1 = FAIL，2 = 脚本异常。

### 4.3 U-1 数据源种类统计

**方法**：正则提取报告中所有 `[数字]` `[数字字母]` `[tushare]` `[baostock]` 引用，去重计数。

**阈值**：
- depth_analysis: ≥12/19 类
- daily: ≥8/19 类（日报不引用全部数据类）

**正则以 `[` 开头 `]` 结尾的内容**：`r'\[(\d+[A-Za-z]*)\]|\[tushare\]|\[baostock\]'`

### 4.4 U-2 强制字段存在性（6项）

| 字段 | 正则 | 适用报告 |
|:-----|:-----|:------:|
| 质押风险 | `质押.*(占其持股\|占总股本\|比例)` | 深度分析 |
| 杜邦拆解 | `净利率.*周转率.*杠杆\|杜邦` | 深度分析 |
| 板块相位 | `板块相位\|SectorPhaseMap\|管线.*相位` | 两者 |
| 四档资金 | `超大单\|大单.*中单\|小单.*净额` | 两者 |
| PE分位 | `PE.*分位\|百分位\|历史分位` | 两者 |
| 行业资金 | `行业资金.*[\[（](10\|7)[\]）]` | 两者 |

日报的强制字段为 4 项（不含质押和杜邦，因为这两个是日报复用深度分析）。

### 4.5 U-3 四档资金结构

**方法**：检查是否包含"超大单"和"大单"两个关键词。

**阈值**：两者均出现 = PASS。仅一个 = WARN。一个都没有 = FAIL。

### 4.6 U-4 "不可获取"率

**方法**：统计 `数据不可[获取得]` 出现次数 / 报告中数据引用次数的比值。

**阈值**：<20% = PASS，20-50% = WARN，≥50% = FAIL。

**特殊处理**：北向个股标注"不可获取"为预期行为，不计入分子。

### 4.7 输出格式

PASS 时：
```
PASS: U-1 数据源种类 14/19 ✓
PASS: U-2 强制字段 6/6 ✓
PASS: U-3 四档资金结构 ✓
PASS: U-4 "不可获取"率 5% ✓
总判定: PASS
```

FAIL 时：
```
FAIL: U-2 强制字段 5/6 ✗
  缺失项:
    - 质押风险行 (正则未匹配: "质押.*(占其持股|占总股本|比例)")
  建议: 在 §六 风控段补充大股东质押比例行
总判定: FAIL
```

---

## 五、audit_scan.py 扩展设计

### 5.1 新增函数

**check_optimization_compliance_daily()**：
- C-9: 检查 `每日荐股/事后评估/records.csv` 行数。最近 5 个交易日是否每日 +1
- C-10: 检查 `重点股票/深度分析/后评估报告/` 下最新评估 JSON 的时间戳。是否在 7 天内
- 返回 findings 列表

**check_optimization_compliance_weekly()**：
- C-5~C-8b: 检查各批次里程碑
  - C-5: 第一批 5 项 — 检查最新深度分析报告是否含质押行/板块相位行；检查最新日报是否含四档资金表；检查玉夜链路报告是否存在
  - C-6: 第二批 5 项 — 检查深度分析模板是否升版到 v1.5
  - C-7: 第三批 4 项 — 检查白皮书是否升版到 v3.6
  - C-8: 第四批 4 项 — 检查信号胜率表是否存在
  - C-8b: 第五批 5 项 — 检查 sim_trading.py 是否更新开仓条件
- 返回 findings 列表

### 5.2 scan_all() 集成

```python
def scan_all(mode="daily"):
    findings = []
    findings.extend(check_signature_chain())
    findings.extend(check_checklist_sig_timing())
    findings.extend(check_token_overspend())
    findings.extend(check_process_bypass())
    findings.extend(check_file_oversize())
    
    # 新增：优化方案合规
    findings.extend(check_optimization_compliance_daily())
    if mode == "weekly":
        findings.extend(check_optimization_compliance_weekly())
    
    return findings
```

### 5.3 CLI 扩展

```
python3 scripts/audit_scan.py           # 默认 daily 模式
python3 scripts/audit_scan.py --weekly  # weekly 模式，额外运行 C-5~C-8b
```

---

## 六、feishu_bridge.py 扩展设计

### 6.1 新增功能

增加 `--notify` 参数，支持主动推送通知消息到飞书群：

```
python3 代码文件/tools/feishu_bridge.py --notify "消息内容"
```

### 6.2 实现方式

利用现有 `FEISHU_REPLY_URL` 端点。若当前为轮询模式（被动回复），增加主动发送能力。

备选方案：若 `--notify` 实现复杂，降级为向 `.claude/im_queue/` 写入消息文件，由 feishu_bridge 下次轮询时自动发送。

---

## 七、文件预算

| 文件 | 操作 | 预计行数 | 代码等级 | Token预算 |
|:-----|:----|:------|:------|:------|
| scripts/check_data_utilization.py | 新建 | ~150行 | L0 | ≤3K |
| scripts/audit_scan.py | 修改 | +80行 | L1 | ≤2K |
| 代码文件/tools/feishu_bridge.py | 修改 | +30行 | L0 | ≤1K |
| **合计** | — | **~260行** | — | **≤6K** |

---

## 八、测试用例

| 编号 | 输入 | 预期 |
|:----|:-----|:-----|
| TC1 | 全合规深度分析报告（6 强制字段齐全+四档资金+14/19 类数据源） | 总 PASS |
| TC2 | 缺质押行的报告 | U-2 5/6 FAIL，标注"缺少质押风险行" |
| TC3 | 缺杜邦+板块相位+四档资金的报告 | U-2 3/6 FAIL，U-3 FAIL，标注三项缺失 |
| TC4 | v1.4 方案前历史报告（无任何新字段） | U-1 不达标，U-2 大面积 FAIL |
| TC5 | audit_scan.py --daily 运行 | C-9/C-10 输出 PASS/FAIL |
| TC6 | audit_scan.py --weekly 运行 | C-5~C-8b 输出 PASS/FAIL |
| TC7 | feishu_bridge.py --notify "测试消息" | 飞书群收到消息 |

---

## 九、部署清单（G段）

| # | 部署项 | 源文件 | 目标路径 | 验证方法 |
|:--|:------|:------|:-----|:-----|
| G1 | 合规检查脚本 | `scripts/check_data_utilization.py`（新建） | `scripts/` | `python3 check_data_utilization.py --help` |
| G2 | audit_scan 更新 | `scripts/audit_scan.py`（修改） | `scripts/` | `python3 audit_scan.py` 全 PASS |
| G3 | feishu_bridge 扩展 | `代码文件/tools/feishu_bridge.py`（修改） | `代码文件/tools/` | `python3 feishu_bridge.py --notify "部署验证"` |
| G4 | 千光调度注册 | audit_scan.py --daily/--weekly | Task Scheduler / cron | 下一个调度周期自动执行 |

---

## 十、需求→代码核对清单

| # | 需求 | code_ref（红结回填） | coder_ok |
|:--|:-----|:-----|:---:|
| R1 | check_data_utilization.py 实现 U-1~U-4 检查和 CLI 接口 | | |
| R2 | audit_scan.py 新增 check_optimization_compliance_daily() | | |
| R3 | audit_scan.py 新增 check_optimization_compliance_weekly() | | |
| R4 | audit_scan.py scan_all() 集成 mode 参数 | | |
| R5 | feishu_bridge.py 增加 --notify 参数 | | |
| R6 | 退出码 0=PASS, 1=FAIL, 2=异常 | | |
| R7 | 日报和深度分析使用不同阈值 | | |
| R8 | 北向"不可获取"不计入 U-4 分子 | | |

---

> **情墨签字**: 设计完成。代码分级 L0/L1，文件预算 ~260行，Token 预算 ≤6K。提交腰子核对。
