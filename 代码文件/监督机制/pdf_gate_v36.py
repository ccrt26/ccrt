#!/usr/bin/env python3
"""pdf_gate_v36.py — 日报v3.6 PDF生成前置闸门
用法: python3 pdf_gate_v36.py <日报路径> [--json-output <path>]
退出码: 0=PASS(允许生成PDF), 1=WARN(可生成但标注缺口), 2=BLOCK(禁止生成PDF)
检查: 7项禁止级矛盾 + 5项必填字段
"""
import re, json, os, sys
from datetime import datetime


def load_sidecar(md_path):
    json_path = md_path.replace('.md', '.json')
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def sidecar_has_action_change(md_path):
    sidecar = load_sidecar(md_path)
    if not sidecar:
        return False
    valid = {'upgrade', 'unchanged', 'downgrade', 'stop_watch', 'reanalysis_required'}
    p0 = sidecar.get('p0_decision_card', {}) or {}
    mf = sidecar.get('machine_fields', {}) or {}
    value = p0.get('action_change') or mf.get('action_change') or sidecar.get('action_change')
    return value in valid


def has_text(md, pattern):
    return bool(re.search(pattern, md))

def check_blocking_contradictions(md, path):
    """7项禁止级矛盾检测，任一触发→BLOCK"""
    blocks = []

    # 1 & 2. 仓位上限矛盾 + 止损一致性（合并检测）
    cap_zero = has_text(md, r'仓位上限[^\d]*0%') or has_text(md, r'当前仓位[^\d]*0%')
    action_buy = has_text(md, r'(?:明日主动作|p0_action).*?(?:加仓|试探|买入)')
    has_conditional = has_text(md, r'(?:触发|条件|缩量|企稳|回踩).*?(?:建仓|试探|仓位)')
    if cap_zero and action_buy and not has_conditional:
        blocks.append('BLOCK-1: 仓位上限0%但建议买入/试探/加仓，且无触发条件说明')

    # 2. 止损价检测：0%仓位+新仓止损带条件说明→允许
    new_sl = re.findall(r'新(?:建)?仓止损[^\d]*([\d.]+)\s*元?', md)
    held_sl = re.findall(r'已持仓止损[^\d]*([\d.]+)\s*元?', md)
    # v3.6.1: 不做额外BLOCK，只要不是cap_zero+action_buy+无条件即可

    # 3. 日期与星期错误 — 全量扫描（完整日期+短日期）
    weekday_map = {'一':0,'二':1,'三':2,'四':3,'五':4,'六':5,'日':6,'天':6}
    weekday_names = ['周一','周二','周三','周四','周五','周六','周日']
    try:
        from datetime import date as dt_date
    except:
        dt_date = None

    # 3a. 完整日期：YYYY-MM-DD 或 YYYY/MM/DD
    for dm in re.finditer(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', md):
        try:
            y, m, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            actual_wd = dt_date(y, m, d).weekday()
            ctx = md[max(0,dm.start()-5):min(len(md),dm.end()+200)]
            wm = re.search(r'(?:周|星期)([一二三四五六日天])', ctx)
            if wm and wm.group(1) in weekday_map:
                if weekday_map[wm.group(1)] != actual_wd:
                    blocks.append(f'BLOCK-3a: {y}-{m}-{d}实际为{weekday_names[actual_wd]}，文中写星期{wm.group(1)}')
        except:
            pass

    # 3b. 短日期：M/D(周X) 或 M月D日 周X 或 M/D 周X
    trade_year = 2026  # default
    ymd = re.search(r'(\d{4})[-/年]', md)
    if ymd:
        trade_year = int(ymd.group(1))

    for dm in re.finditer(r'(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*(?:日)?\s*[(（]\s*([一二三四五六日天])\s*[)）]', md):
        try:
            m, d, claimed = int(dm.group(1)), int(dm.group(2)), dm.group(3)
            actual_wd = dt_date(trade_year, m, d).weekday()
            if claimed in weekday_map and weekday_map[claimed] != actual_wd:
                blocks.append(f'BLOCK-3b: {m}/{d}实际为{weekday_names[actual_wd]}，文中写({claimed})')
        except:
            pass

    for dm in re.finditer(r'(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*(?:日)?\s*(?:周|星期)([一二三四五六日天])', md):
        try:
            m, d, claimed = int(dm.group(1)), int(dm.group(2)), dm.group(3)
            actual_wd = dt_date(trade_year, m, d).weekday()
            if claimed in weekday_map and weekday_map[claimed] != actual_wd:
                blocks.append(f'BLOCK-3c: {m}/{d}实际为{weekday_names[actual_wd]}，文中写周{claimed}')
        except:
            pass

    # 4. 量能判断前后冲突
    has_shrink = has_text(md, r'缩量')
    has_surge = has_text(md, r'放量下跌')
    # "缩量休整"和"放量下跌"同时出现=冲突
    if has_shrink and has_surge:
        shrink_ctx = re.findall(r'缩量[^\n]{0,20}', md)
        surge_ctx = re.findall(r'放量[^\n]{0,20}', md)
        # 如果缩量描述的是前期、放量描述的是今日，不冲突
        same_context = any('今日' in s or '5/29' in s for s in shrink_ctx) and \
                       any('今日' in s or '5/29' in s for s in surge_ctx)
        if same_context:
            blocks.append('BLOCK-4: 同日出现"缩量"和"放量下跌"矛盾描述')

    # 5. 评分格式错误
    if has_text(md, r'60\s*/\s*10'):
        blocks.append('BLOCK-5: 评分格式错误(60/10)，应为单一数字(60)')

    # 6. 本地有数据但写不可获取
    if has_text(md, r'融资') and has_text(md, r'(?<!非.)不可获取'):
        blocks.append('BLOCK-6: 融资数据写"不可获取"——[12]已实测可用')

    # 7. 胜率<50%强化买入
    # 只检查信号胜率表中的百分比（T+1胜率列中的值，不是T+1延迟）
    win_pcts = re.findall(r'(?:T\+1胜率|胜率).*?(\d+\.?\d*)%', md)
    # 排除表头"能否增强买入"——只检测实际使用低胜率增强买入的语句
    has_buy_enhance = has_text(md, r'(?:胜率.*?(?:支持|触发|建议).*?买入|据此.*?买入|信号.*?(?:增强|支持).*?买)')
    if has_buy_enhance:
        for w in win_pcts:
            if float(w) < 50:
                blocks.append(f'BLOCK-7: 信号胜率{w}%<50%但用于增强买入建议')
                break

    return blocks

def check_required_fields(md, md_path=''):
    """必填字段检查（v3.6.3: action_change从JSON sidecar读取）"""
    missing = []
    for field, pattern in [
        ('P0明日决策卡', r'明日主动作'),
        ('四档资金结构', r'(?:超大单|四档资金)'),
        ('T+5展望', r'T\+5.*?(?:方向|展望)'),
    ]:
        if not has_text(md, pattern):
            missing.append(f'MISSING: {field}')
    # action_change: 用户版MD不展示，从JSON sidecar读取
    if md_path:
        json_path = md_path.replace('.md', '.json')
        if not os.path.exists(json_path):
            missing.append('MISSING: JSON sidecar')
        elif not sidecar_has_action_change(md_path):
            missing.append('MISSING: action_change in JSON sidecar')
    else:
        if not has_text(md, r'(?:action_change|基线是否改变)'):
            missing.append('MISSING: action_change')
    return missing

def check(path):
    if not os.path.exists(path):
        return {'status': 'BLOCK', 'error': f'文件不存在: {path}'}

    with open(path, 'r', encoding='utf-8') as f:
        md = f.read()

    blocks = check_blocking_contradictions(md, path)
    missing = check_required_fields(md, path)

    if blocks:
        status = 'BLOCK'
    elif len(missing) >= 3:
        status = 'BLOCK'
    elif missing:
        status = 'WARN'
    else:
        status = 'PASS'

    return {
        'status': status,
        'report_path': path,
        'pdf_allowed': status != 'BLOCK',
        'blocking_issues': blocks,
        'missing_fields': missing,
        'block_count': len(blocks),
        'missing_count': len(missing),
        'timestamp': datetime.now().isoformat(),
    }

def main():
    if len(sys.argv) < 2:
        print("用法: python3 pdf_gate_v36.py <日报路径> [--json-output <path>]")
        sys.exit(2)

    path = sys.argv[1]
    out_path = None
    if '--json-output' in sys.argv:
        idx = sys.argv.index('--json-output')
        if idx + 1 < len(sys.argv):
            out_path = sys.argv[idx + 1]

    result = check(path)

    print(f"PDF闸门 v3.6: {os.path.basename(path)}")
    if result['blocking_issues']:
        print(f"  ❌ 禁止级矛盾 ({result['block_count']}项):")
        for b in result['blocking_issues']:
            print(f"    - {b}")
    if result['missing_fields']:
        print(f"  ⚠️ 缺失必填字段 ({result['missing_count']}项):")
        for m in result['missing_fields']:
            print(f"    - {m}")
    if not result['blocking_issues'] and not result['missing_fields']:
        print(f"  ✅ 全部闸门通过")

    print(f"\n总体: {result['status']} | PDF: {'允许' if result['pdf_allowed'] else '禁止'}")

    if out_path:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    sys.exit({'PASS': 0, 'WARN': 1, 'BLOCK': 2}[result['status']])

if __name__ == '__main__':
    main()
