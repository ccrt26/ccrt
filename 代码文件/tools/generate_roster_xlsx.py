"""生成团队名册.xlsx — 铁律量化项目成员名册 Excel 版本"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import date

# --- Styles ---
DARK_BG = PatternFill(start_color="1A1A2E", end_color="1A1A2E", fill_type="solid")
MID_BG = PatternFill(start_color="16213E", end_color="16213E", fill_type="solid")
LIGHT_BG = PatternFill(start_color="F0F2F5", end_color="F0F2F5", fill_type="solid")
WHITE_BG = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
RED_FONT = Font(name="Microsoft YaHei", bold=True, color="E74C3C", size=11)
GREEN_FONT = Font(name="Microsoft YaHei", bold=True, color="27AE60", size=11)
HEADER_FONT = Font(name="Microsoft YaHei", bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(name="Microsoft YaHei", bold=True, color="1A1A2E", size=16)
SUBTITLE_FONT = Font(name="Microsoft YaHei", bold=True, color="1A1A2E", size=12)
NORMAL_FONT = Font(name="Microsoft YaHei", color="333333", size=10)
SMALL_FONT = Font(name="Microsoft YaHei", color="666666", size=9)
THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
LEFT_TOP = Alignment(horizontal="left", vertical="top", wrap_text=True)

def style_header_row(ws, row, col_count):
    for c in range(1, col_count + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEADER_FONT
        cell.fill = DARK_BG
        cell.alignment = CENTER
        cell.border = THIN_BORDER

def style_data_cell(ws, row, col, align=CENTER):
    cell = ws.cell(row=row, column=col)
    cell.font = NORMAL_FONT
    cell.alignment = align
    cell.border = THIN_BORDER
    cell.fill = WHITE_BG
    return cell

def auto_width(ws, min_w=8, max_w=50):
    for col_cells in ws.columns:
        col_letter = get_column_letter(col_cells[0].column)
        lengths = []
        for cell in col_cells:
            if cell.value:
                lines = str(cell.value).split('\n')
                max_line = max(len(line) for line in lines)
                # Approximate: CJK chars ~2, ASCII ~1
                cjk = sum(1 for ch in str(cell.value) if '一' <= ch <= '鿿')
                ascii_chars = len(str(cell.value)) - cjk
                lengths.append(cjk * 2.2 + ascii_chars * 1.1)
        if lengths:
            w = min(max(max(lengths) + 2, min_w), max_w)
            ws.column_dimensions[col_letter].width = w

today = date.today().isoformat()

wb = openpyxl.Workbook()

# ============ Sheet 1: 成员总览 ============
ws1 = wb.active
ws1.title = "成员总览"

# Title
ws1.merge_cells("A1:G1")
ws1.cell(row=1, column=1, value="铁律量化 — 团队名册").font = TITLE_FONT
ws1.cell(row=1, column=1).alignment = CENTER

ws1.merge_cells("A2:G2")
ws1.cell(row=2, column=1, value=f"版本 v1.3 | {today} | 项目总监 阿黑").font = Font(name="Microsoft YaHei", color="666666", size=10)
ws1.cell(row=2, column=1).alignment = CENTER

# Architecture diagram
ws1.merge_cells("A4:G4")
ws1.cell(row=4, column=1, value="团队架构").font = SUBTITLE_FONT
ws1.merge_cells("A5:G5")
ws1.cell(row=5, column=1, value="用户(创始人) → 阿黑(项目总监) → 腰子(金融专家) | Vega(风控官) | Pulse(数据监理) | Alpha(策略研究员) | Sentinel(宏观巡检)").font = Font(name="Microsoft YaHei", color="1A1A2E", size=10)
ws1.cell(row=5, column=1).alignment = CENTER
ws1.cell(row=5, column=1).fill = LIGHT_BG

# Member overview table
headers = ["角色", "名称", "召唤", "核心职责", "一句话", "完整定义", "召唤命令"]
row = 7
for c, h in enumerate(headers, 1):
    ws1.cell(row=row, column=c, value=h)
style_header_row(ws1, row, len(headers))

members = [
    ["项目总监", "阿黑", "—", "调度团队、跟踪全局、主动运营", "让合适的人做合适的事",
     ".claude/agents/项目总监-阿黑.md", "—"],
    ["金融专家", "腰子", "/腰子", "个股分析、策略评估、宏观判断", "告诉你该不该买",
     ".claude/agents/金融专家-腰子.md", ".claude/commands/腰子.md"],
    ["风控官", "Vega", "/Vega", "风险审计、过拟合检测、交易纪律", "告诉你买了会亏多少",
     ".claude/agents/风控官-Vega.md", ".claude/commands/Vega.md"],
    ["数据监理", "Pulse", "/Pulse", "API巡检、缓存审计、数据完整性", "告诉你数据能不能用",
     ".claude/agents/数据监理-Pulse.md", ".claude/commands/Pulse.md"],
    ["策略研究员", "Alpha", "/Alpha", "因子有效性、策略优化、规律挖掘", "告诉你怎么让策略更聪明",
     ".claude/agents/策略研究员-Alpha.md", ".claude/commands/Alpha.md"],
    ["宏观巡检", "Sentinel", "/Sentinel", "政策信号、经济日历、市场情绪", "告诉你外部环境怎么变",
     ".claude/agents/宏观巡检-Sentinel.md", ".claude/commands/Sentinel.md"],
]

for i, m in enumerate(members):
    r = row + 1 + i
    for c, v in enumerate(m, 1):
        style_data_cell(ws1, r, c, CENTER if c <= 3 else LEFT)
        ws1.cell(row=r, column=c, value=v)
    # Alternate row color
    if i % 2 == 0:
        for c in range(1, len(headers) + 1):
            ws1.cell(row=r, column=c).fill = LIGHT_BG

auto_width(ws1)

# ============ Sheet 2: 详细职能 ============
ws2 = wb.create_sheet("详细职能")

ws2.merge_cells("A1:C1")
ws2.cell(row=1, column=1, value="各角色详细职能").font = TITLE_FONT
ws2.cell(row=1, column=1).alignment = CENTER

detail_data = [
    ("阿黑 — 项目总监", "不自己分析，任务是判断什么任务该找谁；复杂任务拆解→分派→综合结论；主动运营：盘前提醒数据巡检、策略退化预警、版本一致性跟踪"),
    ("腰子 — 金融专家", "四维评分：基本面+技术面+资金面+情绪面；策略逻辑评估、宏观环境判断、行业轮动分析；不写代码，分析结论输出给Claude执行"),
    ("Vega — 风控官", "持仓集中度、相关性、流动性、事件风险四位一体；策略过拟合检测、回撤监控、交易纪律审查；红线规则深度审计（不只看格式，审逻辑）；不写代码，只出风险判断"),
    ("Pulse — 数据监理", "三大API（腾讯/新浪/东方财富）连通性巡检；缓存新鲜度审计、数据完整性验证；1+2架构合规检查（主→备→缓存）；不修代码，只给诊断报告和修复指令"),
    ("Alpha — 策略研究员", "因子IC/ICIR/分层收益/衰退趋势分析；策略优化提案（权重/阈值/周期）；新因子探索、后评估规律挖掘；不跑代码，设计方案给Claude执行回测"),
    ("Sentinel — 宏观巡检", "每日盘前宏观简报（政策+数据+事件+情绪）；经济日历前瞻（未来一周重要日程预警）；政策信号解读（央行/产业/监管/财政）；事件风险预警（解禁/重大财报/重组审批）；不写代码，只做宏观判断和预警"),
]

h2 = ["角色", "详细职能", "硬边界"]
row2 = 3
for c, h in enumerate(h2, 1):
    ws2.cell(row=row2, column=c, value=h)
style_header_row(ws2, row2, len(h2))

boundaries = [
    "不自己分析，不越界替角色决策",
    "不写代码、不编造数据、不预测精确价位",
    "不写代码、不提供个股买卖建议",
    "不修代码，只给诊断报告和修复指令",
    "不跑代码，设计方案给Claude执行回测",
    "不写代码、不编造政策信息、不提供个股买卖建议",
]

for i, (name, detail) in enumerate(detail_data):
    r = row2 + 1 + i
    style_data_cell(ws2, r, 1, LEFT)
    style_data_cell(ws2, r, 2, LEFT_TOP)
    style_data_cell(ws2, r, 3, LEFT_TOP)
    ws2.cell(row=r, column=1, value=name)
    ws2.cell(row=r, column=2, value=detail)
    ws2.cell(row=r, column=3, value=boundaries[i])
    if i % 2 == 0:
        for c in range(1, 4):
            ws2.cell(row=r, column=c).fill = LIGHT_BG

# Column widths
ws2.column_dimensions['A'].width = 25
ws2.column_dimensions['B'].width = 65
ws2.column_dimensions['C'].width = 35

# ============ Sheet 3: 协作规则 ============
ws3 = wb.create_sheet("协作规则")

ws3.merge_cells("A1:B1")
ws3.cell(row=1, column=1, value="团队协作规则").font = TITLE_FONT
ws3.cell(row=1, column=1).alignment = CENTER

# Information flow chain
ws3.merge_cells("A3:B3")
ws3.cell(row=3, column=1, value="信息流").font = SUBTITLE_FONT
ws3.merge_cells("A4:B4")
ws3.cell(row=4, column=1, value="Sentinel盘前简报 → Pulse数据巡检 → 腰子选股分析 → Vega风险评估 → Alpha持续优化").font = Font(name="Microsoft YaHei", color="16213E", size=10, bold=True)
ws3.cell(row=4, column=1).alignment = CENTER
ws3.cell(row=4, column=1).fill = LIGHT_BG

# Coverage chain
ws3.merge_cells("A6:B6")
ws3.cell(row=6, column=1, value="全链路覆盖").font = SUBTITLE_FONT

chain_headers = ["环节", "角色 · 覆盖内容"]
r = 7
for c, h in enumerate(chain_headers, 1):
    ws3.cell(row=r, column=c, value=h)
style_header_row(ws3, r, 2)

chain_data = [
    ("宏观环境", "Sentinel — 政策信号 / 经济日历 / 市场情绪"),
    ("数据管线", "Pulse — API巡检 / 缓存审计 / 完整性验证"),
    ("分析决策", "腰子 — 四维评分 / 选股推荐 / 逻辑质疑"),
    ("风险审计", "Vega — 集中度 / 过拟合 / 纪律审查"),
    ("策略进化", "Alpha — 因子IC / 参数优化 / 规律挖掘"),
]

for i, (label, detail) in enumerate(chain_data):
    r2 = r + 1 + i
    style_data_cell(ws3, r2, 1, CENTER)
    style_data_cell(ws3, r2, 2, LEFT)
    ws3.cell(row=r2, column=1, value=label)
    ws3.cell(row=r2, column=2, value=detail)
    if i % 2 == 0:
        for c in range(1, 3):
            ws3.cell(row=r2, column=c).fill = LIGHT_BG

# Rules
rules_start = r + 7
ws3.merge_cells(f"A{rules_start}:B{rules_start}")
ws3.cell(row=rules_start, column=1, value="协作纪律").font = SUBTITLE_FONT

rules = [
    ("分工明确，互不越界", "腰子不做风控，Vega不挖因子，Alpha不看单票，Sentinel不做个股"),
    ("争议解决", "角色间有分歧时，阿黑做最终判断，用户做最终决策"),
    ("版本追踪", "每个角色定义文件独立版本管理"),
    ("红线共守", "所有角色共同遵守规则红线最新版本"),
    ("信息流顺序", "盘前简报→数据巡检→选股分析→风险评估→策略优化"),
]

for i, (rule, desc) in enumerate(rules):
    r3 = rules_start + 1 + i
    style_data_cell(ws3, r3, 1, LEFT)
    style_data_cell(ws3, r3, 2, LEFT)
    ws3.cell(row=r3, column=1, value=rule)
    ws3.cell(row=r3, column=2, value=desc)
    ws3.cell(row=r3, column=1).font = Font(name="Microsoft YaHei", bold=True, color="1A1A2E", size=10)
    if i % 2 == 0:
        for c in range(1, 3):
            ws3.cell(row=r3, column=c).fill = LIGHT_BG

ws3.column_dimensions['A'].width = 25
ws3.column_dimensions['B'].width = 65

# ============ Sheet 4: 文件索引 ============
ws4 = wb.create_sheet("文件索引")

ws4.merge_cells("A1:C1")
ws4.cell(row=1, column=1, value="相关文件索引").font = TITLE_FONT
ws4.cell(row=1, column=1).alignment = CENTER

idx_headers = ["类型", "路径", "说明"]
r = 3
for c, h in enumerate(idx_headers, 1):
    ws4.cell(row=r, column=c, value=h)
style_header_row(ws4, r, len(idx_headers))

files = [
    ("本名册(.md)", "项目成员/团队名册.md", "Markdown 源文件"),
    ("本名册(.xlsx)", "项目成员/团队名册.xlsx", "Excel 版本（本文件）"),
    ("阿黑角色定义", ".claude/agents/项目总监-阿黑.md", "项目总监完整人设"),
    ("腰子角色定义", ".claude/agents/金融专家-腰子.md", "金融专家完整人设"),
    ("Vega角色定义", ".claude/agents/风控官-Vega.md", "风控官完整人设"),
    ("Pulse角色定义", ".claude/agents/数据监理-Pulse.md", "数据监理完整人设"),
    ("Alpha角色定义", ".claude/agents/策略研究员-Alpha.md", "策略研究员完整人设"),
    ("Sentinel角色定义", ".claude/agents/宏观巡检-Sentinel.md", "宏观巡检完整人设"),
    ("召唤命令 ×5", ".claude/commands/腰子.md 等", "角色召唤触发器"),
    ("规则红线", "规则红线/分析的规则红线--Claude_v1.7.md", "项目最高优先级规则"),
]

for i, (ftype, fpath, fdesc) in enumerate(files):
    r2 = r + 1 + i
    style_data_cell(ws4, r2, 1, CENTER)
    style_data_cell(ws4, r2, 2, LEFT)
    style_data_cell(ws4, r2, 3, LEFT)
    ws4.cell(row=r2, column=1, value=ftype)
    ws4.cell(row=r2, column=2, value=fpath)
    ws4.cell(row=r2, column=3, value=fdesc)
    if i % 2 == 0:
        for c in range(1, 4):
            ws4.cell(row=r2, column=c).fill = LIGHT_BG

auto_width(ws4)

# Freeze panes for all sheets
ws1.freeze_panes = "A8"
ws2.freeze_panes = "A4"
ws3.freeze_panes = "A3"
ws4.freeze_panes = "A4"

output_path = r"c:\Users\34269\Documents\Claude\股票分析\项目成员\团队名册.xlsx"
wb.save(output_path)
print(f"[OK] 团队名册.xlsx generated at {output_path}")
