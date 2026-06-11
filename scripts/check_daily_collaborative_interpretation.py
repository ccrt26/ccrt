#!/usr/bin/env python3
"""P4-E: 协作解读闸门 — 包含式伪解释检查 + MD模板归一化"""
import argparse, json, sys, re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]

OBJS = ["p0_action","baseline_interpretation","kline_interpretation",
        "market_sector_interpretation","fund_flow_interpretation",
        "risk_interpretation","event_interpretation","signal_interpretation",
        "tomorrow_plan","t5_outlook"]
FIELDS = ["data_fact","interpretation","action_impact","trigger_condition","invalidation_condition","confidence"]

PSEUDO = [
    "各角色事实一致", "资金面分歧/共振需确认", "信号可参考不单独触发",
    "风控黄灯限制仓位", "消息面无变化，板块不增强", "综合判断：观望",
    "反向突破", "等方向确认", "量能缩小、资金流出收窄",
    "量能变化和资金方向同时确认", "才允许调整仓位；否则继续当前操作",
    "缩量+资金改善+K线止跌", "S1守住+量缩+资金改善",
    "S1跌破+资金恶化+板块转弱", "价格+资金+K线同时确认",
    "维持当前判断", "近4日K线数据已更新", "今日行情已纳入delta分析",
    "观望为主，不追不抄",
    "估值可接受", "趋势判断", "板块中性", "风险可控", "真空期",
    "不改变", "无", "综合", "参考", "资金转正", "转绿灯", "转红灯",
    "等待明确信号", "中性", "偏弱", "偏多",
]

def contains_pseudo(text, pseudo_list):
    text = str(text)
    for p in pseudo_list:
        if p in text and len(p) >= 4:
            return p
    return None

def check_single(code: str, name: str, date_str: str) -> int:
    """Single-stock mode. Only check the specified stock."""
    dc = date_str.replace("-", "")
    issues = []
    stock_dir = ROOT / "重点股票" / "股票报告" / f"{name}({code})"
    jp = stock_dir / f"{name}({code})日报_{dc}.json"
    mp = stock_dir / f"{name}({code})日报_{dc}.md"
    jfiles = [jp] if jp.exists() else []
    mdfiles = [mp] if mp.exists() else []
    if not jfiles:
        issues.append(f"{name}({code}): JSON缺失")
        return _output(issues)
    _check_files(jfiles, mdfiles, dc, issues)
    return _output(issues)


def _check_files(jfiles, mdfiles, dc, issues):
    """Core check logic extracted from main."""
    for jp in jfiles:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            issues.append(f"{jp.parent.name}: JSON解析失败")
            continue
        synth = (data.get("yaozi_integration") or {}).get("daily_synthesis")
        if not isinstance(synth, dict):
            issues.append(f"{jp.parent.name}: daily_synthesis缺失")
            continue
        for obj in OBJS:
            item = synth.get(obj)
            if not isinstance(item, dict):
                issues.append(f"{jp.parent.name}: {obj}缺失")
                continue
            for f in FIELDS:
                v = item.get(f)
                if v is None or v == "" or v == [] or v == {}:
                    issues.append(f"{jp.parent.name}: {obj}.{f}为空")
            conf = item.get("confidence")
            if conf not in ("高","中","低","中-低"):
                issues.append(f"{jp.parent.name}: {obj}.confidence无效")
            interp = str(item.get("interpretation", ""))
            a_impact = str(item.get("action_impact", ""))
            trigger = str(item.get("trigger_condition", ""))
            inval = str(item.get("invalidation_condition", ""))
            if len(interp.replace(" ", "")) < 5:
                issues.append(f"{jp.parent.name}: {obj}.interpretation过短({len(interp)}字): {interp}")
            if len(a_impact.replace(" ", "")) < 2:
                issues.append(f"{jp.parent.name}: {obj}.action_impact过短({len(a_impact)}字): {a_impact}")
            BANNED_TRIGGER = {"综合","资金转正","新事件","转绿灯","催化出现"}
            BANNED_INVAL = {"综合","继续流出","转红灯"}
            if trigger in BANNED_TRIGGER:
                issues.append(f"{jp.parent.name}: {obj}.trigger_condition为模板词: {trigger}")
            if inval in BANNED_INVAL:
                issues.append(f"{jp.parent.name}: {obj}.invalidation_condition为模板词: {inval}")
            for cf in ["data_fact","interpretation","action_impact","trigger_condition","invalidation_condition"]:
                val = str(item.get(cf, ""))
                hit = contains_pseudo(val, PSEUDO)
                if hit:
                    issues.append(f"{jp.parent.name}: {obj}.{cf}包含伪解释: {hit}")
        ys = str(data.get("yaozi_integration", {}).get("synthesis", ""))
        hit = contains_pseudo(ys, PSEUDO)
        if hit:
            issues.append(f"{jp.parent.name}: synthesis包含伪解释: {hit}")

    # Phase 2 & 3: only run for full mode (>=10 files)
    if len(jfiles) >= 10:
        HOMO_FIELDS = ["interpretation","action_impact","trigger_condition","invalidation_condition"]
        for obj in OBJS:
            for field in HOMO_FIELDS:
                vals = []
                for jp in jfiles:
                    d = json.loads(jp.read_text(encoding="utf-8"))
                    s = (d.get("yaozi_integration") or {}).get("daily_synthesis") or {}
                    raw = str(s.get(obj, {}).get(field, ""))
                    norm = re.sub(r'\d{6}|\d+(?:\.\d+)?%?|[+-]?\d+(?:\.\d+)?(?:万|亿|元|手)?', '{N}', raw)
                    norm = re.sub(r'[，。；：:、\s()（）]', '', norm)
                    if norm and len(norm) >= 2:
                        vals.append((jp.parent.name, norm))
                for t, cnt in Counter([x[1] for x in vals]).items():
                    if cnt >= 3:
                        names = [x[0] for x in vals if x[1] == t][:3]
                        issues.append(f"同质化:{obj}.{field} x{cnt} 归一化后重复 ({','.join(names)})")

    # Phase 3: MD template (only if 10 MDs)
    if len(mdfiles) >= 10:
        pats = {}
        for mp in mdfiles:
            text = mp.read_text(encoding="utf-8")
            m = re.search(r'\*\*明日一句话操作\*\*[：:]\s*(.+)', text)
            if m:
                s = re.sub(r'[\d.]+|元', '{P}', m.group(1))
                s = re.sub(r'\s+', '', s)
                pats.setdefault(s, []).append(str(mp))
        for s, flist in pats.items():
            if len(flist) >= 4:
                issues.append(f"MD模板重复 x{len(flist)}: {s[:50]}")

    # Phase 4 (subset for single-stock)
    for mp in mdfiles:
        text = mp.read_text(encoding="utf-8")
        name = mp.parent.name
        trunc_pats = [
            (r'观望。主(?:\s|\||$)', '观望后截断'),
            (r'回避。主(?:\s|\||$)', '回避后截断'),
            (r'建议观望。主', '建议观望后截断'),
            (r'建议回避。主', '建议回避后截断'),
            (r'资金。(?:\s|$)', '资金句中截断'),
            (r'小单[，。](?:\s|$)', '小单后截断'),
        ]
        for pat, label in trunc_pats:
            if re.search(pat, text):
                issues.append(f"{name}: MD正文{label}: {pat}")
        num_trunc = [
            (r'(?<!\d)[+-]\d{3,}[。](?=\s|$|\||\n)', '数值后截断'),
            (r'(超大单|大单|中单|小单|主力)[^。；，]*[+-][。；，]', '资金字段后截断'),
            (r'小单[+-]\d{1,2}[。；，]', '小单数值截断'),
            (r'。。+', '连续句号'),
        ]
        for pat, label in num_trunc:
            m = re.search(pat, text)
            if m:
                issues.append(f"{name}: MD{label}: {m.group()[:50]}")
        why_m = re.search(r'\*\*为什么\*\*[：:]\s*(.+)', text)
        if why_m:
            why_text = why_m.group(1).strip()
            if re.search(r'(超大单|大单|中单|小单)', why_text):
                amt_issues = re.findall(r'(超大单|大单|中单|小单)[^，。；]*?(?<!\d)([+-]?\d{4,})(?![Channel\.\d万%亿]|$)', why_text)
                for fld, val in amt_issues:
                    issues.append(f"{name}: **为什么**中{fld}金额{val}缺'万'/'亿': {why_text[:50]}")
        why_m = re.search(r'\*\*为什么\*\*[：:]\s*(.+)', text)
        if why_m:
            why_text = why_m.group(1).strip()
            if len(why_text) < 35:
                issues.append(f"{name}: **为什么**行过短({len(why_text)}字): {why_text[:40]}")
        p0_m = re.search(r'\|[^|]*明日主动作[^|]*\|[^|]*\|', text)
        if p0_m:
            action_cell = p0_m.group(0).split('|')[2].strip() if len(p0_m.group(0).split('|')) > 2 else ''
            allowed_prefix = ('观望','回避','可关注','持有待涨','加仓','减仓','清仓')
            if action_cell and not any(action_cell.startswith(p) for p in allowed_prefix):
                issues.append(f"{name}: P0明日主动作格式异常: {action_cell[:30]}")
            if '。' in action_cell:
                parts = action_cell.split('。', 1)
                if len(parts) > 1 and parts[1].strip():
                    if len(parts[1].strip()) < 15:
                        issues.append(f"{name}: P0明日主动作含句号截断: {action_cell[:40]}")


def _output(issues):
    if issues:
        print("COLLABORATIVE_INTERPRETATION: BLOCK")
        for i in issues[:25]:
            print(f"  - {i}")
        return 2
    print("COLLABORATIVE_INTERPRETATION: PASS")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--code", default="", help="单票模式(指定股票代码)")
    ap.add_argument("--name", default="", help="单票模式(指定股票名称)")
    args = ap.parse_args()
    dc = args.date.replace("-", "")

    # Single-stock mode
    if args.code and args.name:
        return check_single(args.code, args.name, args.date)

    issues = []
    jfiles = sorted((ROOT / "重点股票" / "股票报告").glob(f"*/*日报_{dc}.json"))
    mdfiles = sorted((ROOT / "重点股票" / "股票报告").glob(f"*/*日报_{dc}.md"))

    if len(jfiles) != 10:
        issues.append("JSON数量错误")

    _check_files(jfiles, mdfiles, dc, issues)  # Phase 2-4 handled internally
    HOMO_FIELDS = ["interpretation","action_impact","trigger_condition","invalidation_condition"]
    for obj in OBJS:
        for field in HOMO_FIELDS:
            vals = []
            for jp in jfiles:
                d = json.loads(jp.read_text(encoding="utf-8"))
                s = (d.get("yaozi_integration") or {}).get("daily_synthesis") or {}
                raw = str(s.get(obj, {}).get(field, ""))
                # 归一化：去数字/百分比/金额/代码/标点
                norm = re.sub(r'\d{6}|\d+(?:\.\d+)?%?|[+-]?\d+(?:\.\d+)?(?:万|亿|元|手)?', '{N}', raw)
                norm = re.sub(r'[，。；：:、\s()（）]', '', norm)
                if norm and len(norm) >= 2:
                    vals.append((jp.parent.name, norm))
            for t, cnt in Counter([x[1] for x in vals]).items():
                if cnt >= 3:
                    names = [x[0] for x in vals if x[1] == t][:3]
                    issues.append(f"同质化:{obj}.{field} x{cnt} 归一化后重复 ({','.join(names)})")

    # Phase 3: MD template normalization
    if len(mdfiles) == 10:
        pats = {}
        for mp in mdfiles:
            text = mp.read_text(encoding="utf-8")
            m = re.search(r'\*\*明日一句话操作\*\*[：:]\s*(.+)', text)
            if m:
                s = re.sub(r'[\d.]+|元', '{P}', m.group(1))
                s = re.sub(r'\s+', '', s)
                pats.setdefault(s, []).append(str(mp))
        for s, flist in pats.items():
            if len(flist) >= 4:
                issues.append(f"MD模板重复 x{len(flist)}: {s[:50]}")

    # Phase 4: 截断/残句检查
    for mp in mdfiles:
        text = mp.read_text(encoding="utf-8")
        name = mp.parent.name
        # 截断模式
        trunc_pats = [
            (r'观望。主(?:\s|\||$)', '观望后截断'),
            (r'回避。主(?:\s|\||$)', '回避后截断'),
            (r'建议观望。主', '建议观望后截断'),
            (r'建议回避。主', '建议回避后截断'),
            (r'资金。(?:\s|$)', '资金句中截断'),
            (r'小单[，。](?:\s|$)', '小单后截断'),
        ]
        for pat, label in trunc_pats:
            if re.search(pat, text):
                issues.append(f"{name}: MD正文{label}: {pat}")
        # 数值截断检查
        num_trunc = [
            (r'(?<!\d)[+-]\d{3,}[。](?=\s|$|\||\n)', '数值后截断'),
            (r'(超大单|大单|中单|小单|主力)[^。；，]*[+-][。；，]', '资金字段后截断'),
            (r'小单[+-]\d{1,2}[。；，]', '小单数值截断'),
            (r'。。+', '连续句号'),
        ]
        for pat, label in num_trunc:
            m = re.search(pat, text)
            if m:
                issues.append(f"{name}: MD{label}: {m.group()[:50]}")
        # **为什么**行强制检查
        why_m = re.search(r'\*\*为什么\*\*[：:]\s*(.+)', text)
        if why_m:
            why_text = why_m.group(1).strip()
            # 若提到资金字段，金额必须带万/亿
            if re.search(r'(超大单|大单|中单|小单)', why_text):
                amt_issues = re.findall(r'(超大单|大单|中单|小单)[^，。；]*?(?<!\d)([+-]?\d{4,})(?![\.\d万%亿]|$)', why_text)
                for fld, val in amt_issues:
                    issues.append(f"{name}: **为什么**中{fld}金额{val}缺'万'/'亿': {why_text[:50]}")
        # 为什么行长度
        why_m = re.search(r'\*\*为什么\*\*[：:]\s*(.+)', text)
        if why_m:
            why_text = why_m.group(1).strip()
            if len(why_text) < 35:
                issues.append(f"{name}: **为什么**行过短({len(why_text)}字): {why_text[:40]}")
        # P0表明日主动作不能含句号截断
        p0_m = re.search(r'\|[^|]*明日主动作[^|]*\|[^|]*\|', text)
        if p0_m:
            action_cell = p0_m.group(0).split('|')[2].strip() if len(p0_m.group(0).split('|')) > 2 else ''
            allowed_prefix = ('观望','回避','可关注','持有待涨','加仓','减仓','清仓')
            if action_cell and not any(action_cell.startswith(p) for p in allowed_prefix):
                issues.append(f"{name}: P0明日主动作格式异常: {action_cell[:30]}")
            # 检查句号截断：如果动作后跟句号且后面还有内容但不在允许枚举内
            if '。' in action_cell:
                parts = action_cell.split('。', 1)
                if len(parts) > 1 and parts[1].strip():
                    if len(parts[1].strip()) < 15:
                        issues.append(f"{name}: P0明日主动作含句号截断: {action_cell[:40]}")

    if issues:
        print("COLLABORATIVE_INTERPRETATION: BLOCK")
        for i in issues[:25]:
            print(f"  - {i}")
        return 2
    print("COLLABORATIVE_INTERPRETATION: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
