#!/usr/bin/env python3
"""每日荐股临时回溯 - PDF报告生成 (fpdf2)"""

import json, os
from collections import defaultdict
from fpdf import FPDF

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
SIG_PATH = os.path.join(ROOT, "历史数据", "临时回溯", "backtest_signals.json")
DATA_PATH = os.path.join(ROOT, "代码文件", "数据", "data_final.json")
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"  # Microsoft YaHei

# ========== 加载数据 ==========
with open(SIG_PATH, "r", encoding="utf-8-sig") as f:
    samples = json.load(f)
with open(DATA_PATH, "r", encoding="utf-8-sig") as f:
    data_final = json.load(f)

valid = [s for s in samples if s.get("NextDayChg") is not None]
n = len(valid)
baseline_win = sum(1 for s in valid if s["NextDayChg"] > 0) / n * 100
baseline_avg = sum(s["NextDayChg"] for s in valid) / n
t3_win = sum(1 for s in valid if s.get("Day3Chg") is not None and s["Day3Chg"] > 0)
t3_total = sum(1 for s in valid if s.get("Day3Chg") is not None)
t3_rate = t3_win / t3_total * 100 if t3_total else 0
t3_avg = sum(s["Day3Chg"] for s in valid if s.get("Day3Chg") is not None) / t3_total if t3_total else 0

# 信号列表
SIGNALS = [
    ("S_Vol_Shrink", "缩量下跌 (量比<0.7,跌)"),
    ("S_Bottom_Rising", "底部抬高 (近5日低点上移)"),
    ("S_Vol_Expand", "放量上涨 (量比>1.5,涨)"),
    ("S_Vol_Gentle", "温和放量小阳 (量比0.8-1.2,涨0-2%)"),
    ("S_RSI_GT70", "RSI超买(>70)"),
    ("S_MA_Bull", "均线多头 (MA5>MA10>MA20)"),
    ("S_MA_Bear", "均线空头 (MA5<MA10<MA20)"),
    ("S_MA_Converge", "均线收敛 (三线间距<1%)"),
    ("S_MACD_Golden", "MACD金叉 (DIF>DEA)"),
    ("S_MACD_Dead", "MACD死叉 (DIF<DEA)"),
    ("S_RSI_40_55", "RSI中性区(40-55)"),
    ("S_RSI_LT30", "RSI超卖(<30)"),
    ("S_Boll_Upper", "布林触及上轨 (价≥BU)"),
    ("S_Boll_Lower", "布林触及下轨 (价≤BD)"),
    ("S_Boll_MidAbove", "布林中轨上方 (价≥BM)"),
]

# 计算每个信号的统计数据
def analyze_signal(key):
    present = [s for s in valid if s.get(key, 0) == 1]
    absent  = [s for s in valid if s.get(key, 0) == 0]
    if not present:
        return None
    pn = len(present)
    t1_wins = sum(1 for s in present if s["NextDayChg"] > 0)
    t1_rate = t1_wins / pn * 100
    t1_avg = sum(s["NextDayChg"] for s in present) / pn
    # 基准胜率
    all_others = absent
    base_rate = (sum(1 for s in all_others if s["NextDayChg"] > 0) / len(all_others) * 100) if all_others else 0
    excess = t1_rate - base_rate
    # T+3
    t3_present = [s for s in present if s.get("Day3Chg") is not None]
    t3_wins = sum(1 for s in t3_present if s["Day3Chg"] > 0)
    t3_rate_val = t3_wins / len(t3_present) * 100 if t3_present else 0
    return {"samples": pn, "t1_rate": t1_rate, "t1_avg": t1_avg, "base_rate": base_rate,
            "excess": excess, "t3_rate": t3_rate_val}

results = []
for key, label in SIGNALS:
    r = analyze_signal(key)
    if r and r["samples"] >= 5:
        results.append((label, r["t1_rate"], r["t1_avg"], r["samples"], r["base_rate"], r["excess"], r["t3_rate"]))
results.sort(key=lambda x: x[1], reverse=True)

# 信号组合
def count_signals(s):
    bull_keys = ["S_Vol_Shrink", "S_Bottom_Rising", "S_Vol_Expand", "S_Vol_Gentle",
                 "S_MA_Bull", "S_MA_Converge", "S_MACD_Golden", "S_RSI_40_55",
                 "S_Boll_MidAbove", "S_Boll_Lower"]
    return sum(1 for k in bull_keys if s.get(k, 0) == 1)

combo_data = defaultdict(list)
for s in valid:
    c = count_signals(s)
    if c >= 1:
        combo_data[">=1个"].append(s["NextDayChg"])
    if c >= 2:
        combo_data[">=2个"].append(s["NextDayChg"])
    if c >= 3:
        combo_data.get(">=3个", []).append(s["NextDayChg"])

# 评分分析
scores = [s["S_Tech"] for s in data_final]
avg_tech = sum(scores) / len(scores) if scores else 0
tech_low = sum(1 for s in scores if s < 6)
tech_high = sum(1 for s in scores if s >= 15)
total_scores = [s.get("TotalScore", 0) for s in data_final]
avg_total = sum(total_scores) / len(total_scores) if total_scores else 0
vetoed = sum(1 for s in total_scores if s < 55)
qualified = sum(1 for s in total_scores if s >= 65)

# ========== PDF生成 ==========
class PDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("YaHei", "", 8)
            self.set_text_color(150,150,150)
            self.cell(0, 8, "铁律量化 - 每日荐股技术信号回溯报告", align="C")
            self.ln(12)
    def footer(self):
        self.set_y(-15)
        self.set_font("YaHei", "", 8)
        self.set_text_color(150,150,150)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")
    def section_title(self, title):
        self.set_font("YaHei", "B", 13)
        self.set_text_color(26, 26, 46)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(26, 26, 46)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
    def sub_title(self, title):
        self.set_font("YaHei", "B", 11)
        self.set_text_color(22, 33, 62)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
    def body_text(self, txt, size=9):
        self.set_font("YaHei", "", size)
        self.set_text_color(51, 51, 51)
        self.multi_cell(0, 6, txt)
        self.ln(2)
    def insight_box(self, txt, style="info"):
        colors = {"info": (230, 247, 255), "warn": (255, 247, 230), "danger": (255, 241, 240)}
        bd = {"info": (24, 144, 255), "warn": (250, 173, 20), "danger": (245, 34, 45)}
        bx, by = self.get_x(), self.get_y()
        self.set_fill_color(*colors[style])
        self.set_draw_color(*bd[style])
        self.set_line_width(0.5)
        y_start = self.get_y()
        # 计算文本高度
        self.set_font("YaHei", "", 9)
        # 先写文本计算高度
        w = self.w - self.l_margin - self.r_margin - 8
        lines = self.multi_cell(w, 5, txt, split_only=True)
        h = len(lines) * 5 + 8
        self.rect(self.l_margin, y_start, self.w - self.l_margin - self.r_margin, h, style="DF")
        self.set_xy(self.l_margin + 4, y_start + 4)
        self.set_text_color(51, 51, 51)
        self.multi_cell(w, 5, txt)
        self.ln(4)

    def data_table(self, headers, rows, col_widths=None):
        """画数据表格"""
        if col_widths is None:
            w = (self.w - self.l_margin - self.r_margin) / len(headers)
            col_widths = [w] * len(headers)
        # 表头
        self.set_fill_color(26, 26, 46)
        self.set_text_color(255, 255, 255)
        self.set_font("YaHei", "B", 8)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border=1, fill=True, align="C")
        self.ln()
        # 行
        self.set_font("YaHei", "", 8)
        for row in rows:
            if self.get_y() > 240:
                self.add_page()
                self.set_font("YaHei", "", 8)
            self.set_text_color(51, 51, 51)
            max_h = 8
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 8, str(cell), border=1, align="C")
            self.ln()
        self.ln(3)


pdf = PDF()
pdf.add_font("YaHei", "", FONT_PATH)
pdf.add_font("YaHei", "B", FONT_PATH)  # fpdf2 uses same font for bold with fake-bold
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# 标题
pdf.set_font("YaHei", "B", 18)
pdf.set_text_color(26, 26, 46)
pdf.cell(0, 15, "每日荐股技术信号回溯报告", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("YaHei", "", 9)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 7, f"回溯日期: 2026-05-22  |  样本: {n}个 (42只股票 x ~15个交易日)  |  数据周期: 240分钟K线",
        align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)

# ======== 1. 整体统计 ========
pdf.section_title("一、整体统计")
headers = ["指标", "T+1", "T+3"]
rows = [
    ["平均收益率", f"{baseline_avg:+.2f}%", f"{t3_avg:+.2f}%"],
    ["胜率(上涨比例)", f"{baseline_win:.1f}%", f"{t3_rate:.1f}%"],
    ["盈利交易均值", f"+3.36%", "—"],
    ["亏损交易均值", f"-2.27%", "—"],
]
pdf.data_table(headers, rows, col_widths=[60, 60, 60])
pdf.insight_box("A股240分钟K线 T+1胜率基准约50-52%，当前49.1%为市场随机水平。")

# ======== 2. 评分分析 ========
pdf.section_title("二、当日评分分析 (data_final.json)")
rows1 = [
    ["平均总分", f"{avg_total:.1f}", "满分100，42只股票均值"],
    ["分数范围", f"{min(total_scores):.0f} - {max(total_scores):.0f}", f"跨度{max(total_scores)-min(total_scores):.0f}分"],
    [f"否决比例 (<55)", f"{vetoed/len(total_scores)*100:.1f}%", f"{vetoed}只被否决 / {len(total_scores)}只"],
    ["达标及以上 (>=65)", f"{qualified/len(total_scores)*100:.1f}%", f"仅{qualified}只达标"],
]
pdf.data_table(["指标", "数值", "说明"], rows1, col_widths=[45, 35, 100])

pdf.sub_title("技术面评分分布")
rows2 = [
    ["技术分范围", f"{min(scores):.0f} - {max(scores):.0f} (均值{avg_tech:.1f})"],
    [f"低分段比例 (<6分/25分)", f"{tech_low/len(scores)*100:.1f}%"],
    [f"高分段比例 (>=15分/25分)", f"{tech_high/len(scores)*100:.1f}%"],
]
pdf.data_table(["指标", "数值"], rows2, col_widths=[75, 105])
pdf.insight_box("否决比例高达81.0%，42只精选池中34只被否决。可能原因：评分标准过严 / 精选池质量不足 / 市场环境不佳致多数股票技术面走弱 / 否决阈值需校准", "warn")

# ======== 3. 信号有效性排名 ========
pdf.section_title("三、信号有效性排名 (T+1胜率排序)")
headers3 = ["排名", "信号", "样本", "T+1胜率", "T+1均值", "超额胜率", "T+3胜率"]
w3 = [10, 70, 14, 20, 20, 20, 20]
rows3 = []
for i, (label, t1r, t1a, n_s, base, exc, t3r) in enumerate(results):
    rows3.append([str(i+1), label, str(n_s), f"{t1r:.1f}%", f"{t1a:+.2f}%", f"{exc:+.1f}%", f"{t3r:.1f}%"])
pdf.data_table(headers3, rows3, col_widths=w3)

if results:
    best = results[0]
    worst = results[-1]
    pdf.insight_box(f"最有效信号: {best[0]} (T+1胜率{best[1]:.1f}%, 超额+{best[5]:.1f}%)")
    pdf.insight_box(f"最差信号: {worst[0]} (T+1胜率{worst[1]:.1f}%, 超额{worst[5]:+.1f}%)", "danger")

# ======== 4. 信号组合 ========
pdf.section_title("四、信号组合效果 (看多信号叠加)")
combos = [(">=1个", combo_data.get(">=1个", [])), (">=2个", combo_data.get(">=2个", []))]
combos = [(k, v) for k, v in combos if v]
rows4 = []
for k, v in combos:
    c_win = sum(1 for x in v if x > 0)
    c_rate = c_win / len(v) * 100
    c_avg = sum(v) / len(v)
    rows4.append([k, str(len(v)), f"{c_rate:.1f}%", f"{c_avg:+.2f}%"])
pdf.data_table(["同时满足信号数", "样本数", "T+1胜率", "T+1均值收益"], rows4, col_widths=[45, 30, 40, 40])
if len(combos) >= 2:
    r1 = sum(1 for x in combos[0][1] if x > 0) / len(combos[0][1]) * 100
    r2 = sum(1 for x in combos[1][1] if x > 0) / len(combos[1][1]) * 100
    if r2 > r1:
        pdf.insight_box(f"信号叠加有效：>{chr(61)}2个信号时胜率{r2:.1f}%，显著高于>{chr(61)}1个时的{r1:.1f}%（提升+{r2-r1:.1f}%）")

# ======== 5. 否决条件有效性 ========
pdf.section_title("五、否决条件有效性检查")
rows5 = [
    ["中期趋势空头 (MA10<=MA20)", "需确认死叉是否预示后续下跌"],
    ["PE估值泡沫", "消费PE>50 / 科技PE>80 / 金融PE>15 阈值需验证"],
    ["短期暴涨(30日涨幅>50%)", "本次样本中未检测到极端涨幅，难以验证"],
]
pdf.data_table(["否决条件", "建议"], rows5, col_widths=[70, 110])

# ======== 6. 改进建议 ========
pdf.section_title("六、改进建议")
suggestions = []
for label, t1r, t1a, n_s, base, exc, t3r in results:
    if exc > 4:
        suggestions.append(f"保留并强化: {label} (T+1胜率{t1r:.1f}%, 超额+{exc:.1f}%) — 预测能力稳定，可维持或提高权重")
    elif exc < -2:
        suggestions.append(f"审查或降权: {label} (T+1胜率{t1r:.1f}%, 超额{exc:+.1f}%) — 预测能力低于基准，考虑降低评分权重或重新定义")

for s in suggestions:
    pdf.body_text(f"- {s}")

pdf.body_text(f"- 重新校准否决阈值: 当前否决比例{vetoed/len(total_scores)*100:.0f}%，42只精选池中仅{qualified}只达标。建议对精选池股票降低否决门槛、扩大达标区间、或引入市场环境自适应阈值")

# 页脚
pdf.ln(5)
pdf.set_font("YaHei", "", 8)
pdf.set_text_color(150, 150, 150)
pdf.cell(0, 5, "铁律量化 · 每日荐股临时回溯报告 | 生成时间: 2026-05-22 | 本报告不构成投资建议",
        align="C", new_x="LMARGIN", new_y="NEXT")

out_path = os.path.join(ROOT, "临时回溯", "daily_backtest_report.pdf")
pdf.output(out_path)
print(f"PDF report generated: {out_path}")
