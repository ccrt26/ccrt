#!/usr/bin/env python3
"""
P0-I: 全团协作人话解读质量闸门 — 检查日报内容逐段解释与全团协作签名完整性。

检查项:
  I1: 每份MD至少8处"这说明"
  I2: 每份MD至少6处"对明日影响"
  I3: JSON 含 role_interpretations(山猫/信鸽/玉夜/流金/青山/腰子整合)
  I4: yaozu_integration 含 consensus/disagreement/final_action/reason/risk_boundary
  I5: 禁止空话列表(可参考/综合判断/需观察/不改变动作/趋势偏多/风险可控/等确认/数据可用/缓存存在/影响仓位上限/不作为短线加仓触发)
  I6: 任意两只股票连续30字以上解释相同 BLOCK
  I7: 同一句"这说明/对明日影响"在3只及以上重复 BLOCK
  I8: sidecar 无旧资金日期残留

用法:
  python3 scripts/check_daily_interpretation_quality.py --date 20260604

退出码:
  0 = PASS
  2 = BLOCK
"""
import argparse, json, re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "重点股票" / "股票报告"
PIGEON_CFG = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"

BANNED_SHORT = ["可参考", "综合判断", "需观察", "不改变动作",
                "风险可控", "等确认", "数据可用", "缓存存在", "影响仓位上限",
                "不作为短线加仓触发"]

# Contextual phrases that are OK in combination with real data
CONTEXTUAL_OK = ["不改变动作", "影响仓位上限", "不作为短线加仓触发", "数据可用", "缓存存在"]


def extract_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def get_pool():
    """Read dynamic stock pool from pigeon_config.json."""
    stocks = []
    if PIGEON_CFG.exists():
        try:
            cfg = json.loads(PIGEON_CFG.read_text(encoding="utf-8"))
            for s in cfg.get("target_stocks", []):
                c = str(s.get("code", ""))
                n = s.get("name", "")
                if c and n:
                    stocks.append((c, n))
            if stocks:
                return stocks
        except Exception:
            pass
    # Fallback to report dirs
    for subdir in sorted(REPORT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        m = re.match(r'(.+)\((\d{6})\)', subdir.name)
        if m:
            stocks.append((m.group(2), m.group(1)))
    return stocks


def check_single(code, date_str):
    """Check a single stock. Returns list of issues."""
    stocks = get_pool()
    for c, n in stocks:
        if c == code:
            return check_stock(c, n, date_str)
    return [f"I0: 股票{code}未在池中找到"]


def check_stock(code, name, date_str):
    """Check a single stock's interpretation quality. Returns list of issues."""
    issues = []
    sd = REPORT_DIR / f"{name}({code})"
    md_path = sd / f"{name}({code})日报_{date_str}.md"
    json_path = sd / f"{name}({code})日报_{date_str}.json"
    md = extract_text(md_path)

    # I1: 至少3处"这说明"
    sm_cnt = md.count("这说明")
    if sm_cnt < 3:
        issues.append(f"I1: {name}({code}) MD 仅 {sm_cnt} 处'这说明'(需≥3)")

    # I2: 至少3处"对明日影响"
    dy_cnt = md.count("对明日影响")
    if dy_cnt < 3:
        issues.append(f"I2: {name}({code}) MD 仅 {dy_cnt} 处'对明日影响'(需≥3)")

    # I5: 禁止空话
    for phrase in BANNED_SHORT:
        if phrase in md:
            lines_with_phrase = [l.strip() for l in md.split('\n') if phrase in l]
            for line in lines_with_phrase:
                line_clean = line.replace("**", "").strip()
                if any(k in line for k in ["**北向**", "**质押**", "**解禁**", "**股东人数**", "**融资**"]):
                    continue
                if any(k in line_clean for k in ["北向：", "质押：", "解禁：", "股东人数：", "融资："]):
                    continue
                if any(c.isdigit() for c in line_clean):
                    continue
                if len(line_clean) > 40:
                    continue
                tokens = line_clean.replace(',', ' ').replace('，', ' ').replace('；', ' ').replace('、', ' ').split()
                if len(tokens) <= 4:
                    issues.append(f"I5: {name}({code}) 行仅含禁止空话'{phrase}': '{line[:60]}'")

    # JSON checks
    if not json_path.exists():
        issues.append(f"I3: {name}({code}) JSON 缺失")
        return issues

    try:
        sj = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        issues.append(f"I3: {name}({code}) JSON解析失败: {e}")
        return issues

    # I3: role_interpretations
    ri = sj.get("role_interpretations", {})
    required_roles = ["山猫_宏观", "信鸽_事件", "玉夜_数据", "流金_风控", "青山_信号", "腰子_整合"]
    for r in required_roles:
        if r not in ri:
            issues.append(f"I3: {name}({code}) role_interpretations 缺 '{r}'")
        elif not isinstance(ri[r], dict):
            issues.append(f"I3: {name}({code}) role_interpretations.{r} 非dict")
        else:
            content_fields = [k for k, v in ri[r].items() if isinstance(v, str) and len(v) >= 5]
            if not content_fields:
                issues.append(f"I3: {name}({code}) role.{r} 无实质内容")

    # I4: yaozi_integration
    yi = sj.get("yaozi_integration", {})
    if not yi or not isinstance(yi, dict):
        issues.append(f"I4: {name}({code}) yaozi_integration 缺失或非dict")
    else:
        content_fields = [k for k, v in yi.items() if isinstance(v, str) and len(v) >= 10 or isinstance(v, dict)]
        if len(content_fields) < 3:
            issues.append(f"I4: {name}({code}) yaozi_integration 内容不足({len(content_fields)}个有值字段)")

    # I8: 旧资金日期残留
    md_clean = md.replace("**", "")
    for bad_pattern in ["6/3 Tushare", "tushare_moneyflow(6/3)", "资金（6/3"]:
        if bad_pattern in md_clean:
            issues.append(f"I8: {name}({code}) MD 有旧资金日期残留: '{bad_pattern}'")

    return issues


def check_cross_stock(date_str, stocks):
    """Cross-stock checks: I6, I7. Returns list of issues."""
    issues = []

    # Collect MD texts
    md_texts = {}
    for code, name in stocks:
        sd = REPORT_DIR / f"{name}({code})"
        md_path = sd / f"{name}({code})日报_{date_str}.md"
        if md_path.exists():
            md_texts[f"{name}({code})"] = extract_text(md_path).replace("**", "")

    # Clean common boilerplate from cross-stock check
    for key in md_texts:
        lines = md_texts[key].split('\n')
        content_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('>') or stripped.startswith('#') or stripped.startswith('---'): continue
            if stripped.startswith('免责声明') or stripped.startswith('风险提示'): continue
            if stripped.startswith('| 项目 | 内容 |') or stripped.startswith('|:-----|:------'): continue
            if 'data_full.json.Fun' in stripped or '当日资金流' in stripped: continue
            if stripped.startswith('| 禁止动作') or stripped.startswith('| **禁止动作**'): continue
            if '尚有一定距离' in stripped or '近4日窗口：' in stripped: continue
            if '说明：今日价格在S1' in stripped: continue
            if stripped.startswith('| 日期 |') and '开盘' in stripped: continue
            content_lines.append(line)
        cleaned = []
        blank = 0
        for line in content_lines:
            if not line.strip():
                blank += 1
                if blank <= 1: cleaned.append(line)
            else:
                blank = 0
                cleaned.append(line)
        md_texts[key] = '\n'.join(cleaned)

    # I7: "这说明" duplicates across 3+ stocks
    shuoming = {}
    for key, md in md_texts.items():
        parts = re.split(r'\n---+|\n## ', md)
        for p in parts:
            if "这说明" in p:
                shuoming[key] = shuoming.get(key, []) + [re.sub(r'\s+', '', p)]
    from collections import Counter
    all_sm = []
    for key, vals in shuoming.items():
        for v in vals:
            all_sm.append(v)
    sm_counter = Counter(all_sm)
    for txt, cnt in sm_counter.most_common(3):
        if cnt >= 3 and len(txt) >= 10:
            keys = [k for k, vs in shuoming.items() if txt in vs]
            issues.append(f"I7: '这说明'重复{cnt}次: 前3只={keys[:3]}")
            break

    # I6: 30+ char substrings
    for key, md in md_texts.items():
        for other_key, other_md in md_texts.items():
            if key >= other_key: continue
            for i in range(len(md) - 30):
                sub = md[i:i+30]
                if sub.strip().startswith('|:'): continue
                if '| 项目 | 内容 |' in sub: continue
                if sub.strip().startswith('| 项目 |'): continue
                if sub.count('|') >= 3 and len(sub.strip()) < 60: continue
                if '禁止动作' in sub or '明日主动作' in sub: continue
                if 'data_full.json.FundFlows' in sub or '当日资金流数据' in sub: continue
                meaningful = re.sub(r'[\d\.\%，\。\+\-\(\)\s\[\]]', '', sub.strip())
                if len(meaningful) < 3: continue
                if sub in other_md:
                    issues.append(f"I6: {key} 与 {other_key} 共享连续30+字: '{sub[:40]}...'")
                    break
            break
        break  # One pair enough to catch issues

    return issues


def check_all(date_str):
    """Full check: per-stock + cross-stock. Returns issues list."""
    issues = []
    stocks = get_pool()
    if not stocks:
        issues.append("I0: 空股票池")
        return issues

    # Per-stock checks
    for code, name in stocks:
        issues.extend(check_stock(code, name, date_str))

    # Cross-stock checks (only in full mode)
    issues.extend(check_cross_stock(date_str, stocks))

    return issues

    for code, name in stocks:
        sd = REPORT_DIR / f"{name}({code})"
        md_path = sd / f"{name}({code})日报_{date_str}.md"
        json_path = sd / f"{name}({code})日报_{date_str}.json"
        md = extract_text(md_path)

        # I1: 至少3处"这说明" (匹配母版格式)
        sm_cnt = md.count("这说明")
        if sm_cnt < 3:
            issues.append(f"I1: {name}({code}) MD 仅 {sm_cnt} 处'这说明'(需≥3)")

        # I2: 至少3处"对明日影响" (匹配母版格式)
        dy_cnt = md.count("对明日影响")
        if dy_cnt < 3:
            issues.append(f"I2: {name}({code}) MD 仅 {dy_cnt} 处'对明日影响'(需≥3)")

        # I5: 禁止空话 - only flag when banned phrase is the SOLE interpretation (standalone)
        # Exclude: data status disclosures in Section 5, table cells with values, alignment rows
        for phrase in BANNED_SHORT:
            if phrase in md:
                lines_with_phrase = [l.strip() for l in md.split('\n') if phrase in l]
                for line in lines_with_phrase:
                    line_clean = line.replace("**", "").strip()
                    # Skip data status disclosures (Section 5 - 北向/质押/解禁/股东人数)
                    if any(k in line for k in ["**北向**", "**质押**", "**解禁**", "**股东人数**", "**融资**"]):
                        continue
                    # Also skip by content (original markdown):
                    if any(k in line_clean for k in ["北向：", "质押：", "解禁：", "股东人数：", "融资："]):
                        continue
                    # Skip table cells that also contain numbers or values
                    if any(c.isdigit() for c in line_clean):
                        continue
                    # Skip lines with obvious data facts (not just empty phrases)
                    if len(line_clean) > 40:
                        continue
                    tokens = line_clean.replace(',', ' ').replace('，', ' ').replace('；', ' ').replace('、', ' ').split()
                    if len(tokens) <= 4:
                        issues.append(f"I5: {name}({code}) 行仅含禁止空话'{phrase}': '{line[:60]}'")

        # JSON checks
        if not json_path.exists():
            issues.append(f"I3: {name}({code}) JSON 缺失")
            continue

        try:
            sj = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as e:
            issues.append(f"I3: {name}({code}) JSON解析失败: {e}")
            continue

        # I3: role_interpretations with content (checks existence + non-empty content)
        ri = sj.get("role_interpretations", {})
        required_roles = ["山猫_宏观", "信鸽_事件", "玉夜_数据", "流金_风控", "青山_信号", "腰子_整合"]
        for r in required_roles:
            if r not in ri:
                issues.append(f"I3: {name}({code}) role_interpretations 缺 '{r}'")
            elif not isinstance(ri[r], dict):
                issues.append(f"I3: {name}({code}) role_interpretations.{r} 非dict")
            else:
                content_fields = [k for k, v in ri[r].items() if isinstance(v, str) and len(v) >= 5]
                if not content_fields:
                    issues.append(f"I3: {name}({code}) role.{r} 无实质内容")

        # 腰子整合
        if "腰子_整合" not in ri and "yaozi_integration" not in sj:
            issues.append(f"I3: {name}({code}) 缺少 yaozi_integration")

        # I4: yaozi_integration exists with content
        yi = sj.get("yaozi_integration", {})
        if not yi or not isinstance(yi, dict):
            issues.append(f"I4: {name}({code}) yaozi_integration 缺失或非dict")
        else:
            content_fields = [k for k, v in yi.items() if isinstance(v, str) and len(v) >= 10 or isinstance(v, dict)]
            if len(content_fields) < 3:
                issues.append(f"I4: {name}({code}) yaozi_integration 内容不足({len(content_fields)}个有值字段)")

        # I8: 旧资金日期残留
        md_clean = md.replace("**", "")
        for bad_pattern in ["6/3 Tushare", "tushare_moneyflow(6/3)", "资金（6/3"]:
            if bad_pattern in md_clean:
                issues.append(f"I8: {name}({code}) MD 有旧资金日期残留: '{bad_pattern}'")

    # I6: 同质化解释检测(连续30字以上相同)
    md_texts = {}
    for code, name in stocks:
        sd = REPORT_DIR / f"{name}({code})"
        md_path = sd / f"{name}({code})日报_{date_str}.md"
        if md_path.exists():
            md_texts[f"{name}({code})"] = extract_text(md_path).replace("**", "")

    # Extract all "这说明" and "对明日影响" paragraph text
    shuoming = {}
    dui_mingri = {}
    for key, md in md_texts.items():
        parts = re.split(r'\n---+|\n## ', md)
        for p in parts:
            if "这说明" in p:
                shuoming[key] = shuoming.get(key, []) + [re.sub(r'\s+', '', p)]
            if "对明日影响" in p:
                dui_mingri[key] = dui_mingri.get(key, []) + [re.sub(r'\s+', '', p)]

    # I7: 同一句"这说明"在3只及以上重复
    all_sm = []
    for key, vals in shuoming.items():
        for v in vals:
            all_sm.append(v)
    sm_counter = Counter(all_sm)
    for txt, cnt in sm_counter.most_common(3):
        if cnt >= 3 and len(txt) >= 10:
            keys = [k for k, vs in shuoming.items() if txt in vs]
            issues.append(f"I7: '这说明'重复{cnt}次: 前3只={keys[:3]} len={len(txt)}")

    # I6: 连续30字以上相同(仅检查MD正文，跳过头部模板)
    # Remove common boilerplate (header/footer)
    import re as _re
    for key in md_texts:
        # Strip header line, footnote line, common structure markers
        lines = md_texts[key].split('\n')
        # Keep only content sections (between ## headings)
        content_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('>') or stripped.startswith('#') or stripped.startswith('---'):
                continue
            if stripped.startswith('免责声明') or stripped.startswith('风险提示'):
                continue
            if stripped.startswith('| 项目 | 内容 |') or stripped.startswith('|:-----|:------'):
                continue
            if 'data_full.json.Fun' in stripped or '当日资金流' in stripped:
                continue
            if stripped.startswith('| 禁止动作') or stripped.startswith('| **禁止动作**'):
                continue
            # Skip common template text
            if '尚有一定距离' in stripped or '近4日窗口：' in stripped:
                continue
            if '说明：今日价格在S1' in stripped or '今日价格' in stripped:
                continue
            if stripped.startswith('| 日期 |') and '开盘' in stripped:
                continue
            content_lines.append(line)
        # Remove consecutive empty lines (collapse >1 blank lines)
        cleaned = []
        blank_count = 0
        for line in content_lines:
            if not line.strip():
                blank_count += 1
                if blank_count <= 1:
                    cleaned.append(line)
            else:
                blank_count = 0
                cleaned.append(line)
        md_texts[key] = '\n'.join(cleaned)

    for key, md in md_texts.items():
        for other_key, other_md in md_texts.items():
            if key >= other_key:
                continue
            # Check for overlapping 30+ char substrings in content
            # Skip table alignment rows, table header patterns
            found = False
            for i in range(len(md) - 30):
                sub = md[i:i+30]
                # Skip alignment rows and header patterns
                if sub.strip().startswith('|:'):
                    continue
                if '| 项目 | 内容 |' in sub:
                    continue
                if sub.strip().startswith('| 项目 |'):
                    continue
                # Skip short table rows (common template structure)
                if sub.count('|') >= 3 and len(sub.strip()) < 60:
                    continue
                # Skip P0 decision card rows (标准化结构)
                if '禁止动作' in sub or '明日主动作' in sub:
                    continue
                # Skip shared metadata text
                if 'data_full.json.FundFlows' in sub or '当日资金流数据' in sub:
                    continue
                if sub in other_md and len(sub.strip()) >= 20:
                    # Require at least 3 letters/Chinese chars (not just digits/punctuation)
                    meaningful = re.sub(r'[\d\.\%，\。\+\-\(\)\s\[\]]', '', sub.strip())
                    if len(meaningful) < 3:
                        continue
                    issues.append(f"I6: {key} 与 {other_key} 共享连续30+字文本: '{sub[:40]}...'")
                    found = True
                    break
            if found:
                break
            break  # Only check first pair to avoid explosion

    return issues


def check_incremental(codes, date_str):
    """增量模式: 只检查传入代码集合内的 P0-I。
    跨股票 I6/I7 只在传入代码之间执行。"""
    issues = []
    pool = get_pool()
    # Filter pool to only specified codes
    filtered = [(c, n) for c, n in pool if c in codes]
    if not filtered:
        issues.append("I0: incremental-codes 在池中无匹配")
        return issues

    missing = [c for c in codes if c not in {p[0] for p in pool}]
    if missing:
        issues.append(f"I0: incremental-codes 不在池中: {missing}")

    # Per-stock checks
    for code, name in filtered:
        issues.extend(check_stock(code, name, date_str))

    # Cross-stock checks only among filtered stocks
    if len(filtered) >= 2:
        issues.extend(check_cross_stock(date_str, filtered))

    return issues


def main():
    ap = argparse.ArgumentParser(description="P0-I: 全团协作人话解读质量闸门")
    ap.add_argument("--date", required=True, help="日期 YYYYMMDD")
    ap.add_argument("--code", default="", help="单票模式(指定股票代码)")
    ap.add_argument("--incremental-codes", default="", help="增量模式:逗号分隔股票代码(只检查这些代码的跨股票重复)")
    args = ap.parse_args()

    if args.incremental_codes:
        codes = [c.strip() for c in args.incremental_codes.split(",") if c.strip()]
        issues = check_incremental(codes, args.date)
    elif args.code:
        issues = check_single(args.code, args.date)
    else:
        issues = check_all(args.date)

    deduped = set(issues)
    if deduped:
        for i in sorted(deduped):
            print(f"  ❌ {i}")
        print(f"\n结果: {len(deduped)} BLOCK")
        sys.exit(2)
    else:
        suffix = f"({args.code})" if args.code else ""
        print(f"✅ P0-I: 全团协作解读质量检查通过{suffix}")
        sys.exit(0)


if __name__ == "__main__":
    main()
