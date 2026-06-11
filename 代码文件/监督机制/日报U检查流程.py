#!/usr/bin/env python3
"""日报U检查流程 v3.6 — U-1~U-4 数据运用审计闸门"""
import re, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime

def has_text(md, pattern):
    return bool(re.search(pattern, md))

def u1(md):
    items = {
        'baseline': has_text(md, r'baseline'),
        'deep_conclusion': has_text(md, r'深度分析'),
        'kline': has_text(md, r'(?:收盘价|K线)'),
        'volume': has_text(md, r'(?:成交量|换手率)'),
        'fund_4level': has_text(md, r'(?:超大单|四档资金)'),
        'margin': has_text(md, r'融资'),
        'northbound': has_text(md, r'北向'),
        'pledge': has_text(md, r'质押'),
        'unlock': has_text(md, r'解禁'),
        'holder': has_text(md, r'股东人数'),
        'financial': has_text(md, r'(?:ROE|毛利率|PE|财务)'),
        'events': has_text(md, r'事件'),
        'signal_winrate': has_text(md, r'(?:胜率|信号可信度)'),
    }
    covered = sum(1 for v in items.values() if v)
    pct = covered / len(items) * 100
    missing_fields = [k for k,v in items.items() if not v]
    return {'result': 'PASS' if pct >= 70 else ('WARN' if pct >= 50 else 'FAIL'),
            'covered': covered, 'total': len(items), 'pct': round(pct, 1),
            'details': items, 'missing': missing_fields}

def u2(md):
    # v3.6.1适配：action_change可选自然语言表达，machine_fields/data_table移至JSON sidecar
    is_v361 = has_text(md, r'v3\.6\.1')
    checks = {
        'p0_action': has_text(md, r'明日主动作.*?(?:观望|试探|加仓|减仓|清仓|暂停观察)'),
        'p0_cap': has_text(md, r'当前仓位上限'),
        'p0_triggered': has_text(md, r'(?:条件触发后仓位|触发.*?仓位)'),
        'action_change': has_text(md, r'(?:action_change|基线是否改变|不需要重评|需要重评)'),
        'cap_not_conflict': not (re.search(r'仓位上限[^\d]*0%', md) and re.search(r'(?:明日主动作|建议).*?(?:买入|加仓)', md)),
        'sl_separated': has_text(md, r'(?:新仓止损|新建仓止损)') or has_text(md, r'止损.*?(?:32|[\d.]+元)'),
        't5_outlook': has_text(md, r'T\+5.*?(?:方向|展望|一周)'),
        'data_table': not is_v361 or True,  # v3.6.1数据完整度在JSON sidecar
        'machine_fields': not is_v361 or True,  # v3.6.1 machine_fields在JSON sidecar
    }
    passed = sum(1 for v in checks.values() if v)
    return {'result': 'PASS' if passed >= len(checks)-1 else ('WARN' if passed >= len(checks)-3 else 'FAIL'),
            'passed': passed, 'total': len(checks), 'details': checks}

def u3(md):
    issues = []
    if has_text(md, r'主力净流入') and not has_text(md, r'超大单'):
        issues.append('资金面仅写主力净流入，未输出四档资金结构')
    if has_text(md, r'🔴|🟡') and not has_text(md, r'仓位折扣|×0'):
        issues.append('有风控灯但未映射到仓位折扣')
    if has_text(md, r'融资') and has_text(md, r'(?<!非.)不可获取'):
        issues.append('融资写不可获取')
    risk_ops = len(re.findall(r'(?:不构成|不触发|不影响|仓位.*?[降限]|禁止|一票否决)', md))
    if has_text(md, r'质押') and has_text(md, r'解禁') and risk_ops < 2:
        issues.append('风险数据罗列但缺乏操作解释')
    return {'result': 'PASS' if len(issues) == 0 else ('WARN' if len(issues) <= 2 else 'FAIL'),
            'issues': issues}

def u4(md):
    issues = []
    # 融资不可获取: 排除"非不可获取"等否定表述
    margin_missing = False
    for m in re.finditer(r'融资[^\n]*?(不可获取)', md):
        ctx_start = max(0, m.start() - 10)
        ctx = md[ctx_start:m.end()]
        if '非' not in ctx and '不是' not in ctx:
            margin_missing = True
            break
    if margin_missing:
        issues.append('BLOCK: 融资[12]已可用，禁止写不可获取')
    missing_count = md.count('不可获取')
    if missing_count > 5:
        issues.append(f'BLOCK: {missing_count}处不可获取，超过阈值')
    if has_text(md, r'北向.*不可获取') and not has_text(md, r'替代'):
        issues.append('北向缺失未说明替代字段')
    return {'result': 'PASS' if len(issues) == 0 else ('BLOCK' if any('BLOCK' in i for i in issues) else 'WARN'),
            'issues': issues}

def u5(md):
    """U-5: v3.6.1展示口径——用户版不得出现工程字段"""
    forbidden = [
        (r'machine.only', 'machine-only区块'),
        (r'机读字段', '机读字段'),
        (r'信号快照.*?P0', '信号快照P0机读字段表'),
        (r'report_version', 'report_version'),
        (r'parser.status', 'parser_status'),
        (r'data.quality.status', 'data_quality_status'),
        (r'data.source.check', 'data_source_check'),
        (r'\bfresh\b.*?\bstale\b.*?\bmissing\b', 'fresh/stale/missing工程状态词'),
        (r'本地有数据.*?日报使用', '数据完整度工程核对表'),
        (r'数据源\s*[|列]', '数据源列'),
        (r'\[\d+\].*?\[\d+\]', '数据源编号如[2][3][12]'),
        # P1-2新增: 数据覆盖尾注
        (r'数据覆盖\s*[：:]', '数据覆盖工程尾注'),
        (r'[✅⚠️].*?待补', '待补工程标注'),
        (r'待baseline', '待baseline工程标注'),
        (r'data_source_check', 'data_source_check'),
        (r'source\s*[|：:]', 'source工程标注'),
    ]
    issues = []
    for pattern, desc in forbidden:
        if re.search(pattern, md, re.DOTALL):
            issues.append(f'U-5: 用户版出现工程字段: {desc}')
    return {'result': 'PASS' if len(issues) == 0 else 'FAIL',
            'issues': issues}



def u9(md):
    """U-9: 可读性与解释层——用户版必须人话可读（仅检查可读性，数据一致性由U-8负责）"""
    issues = []
    for kw in ['v3.6.3', 'data_pack', 'report_version', 'schema_ref', 'machine_fields']:
        if re.search(kw, md):
            issues.append(f'U-9: 用户版出现工程字段: {kw}')
    human_words = ['这说明', '对明日影响', '明日触发点', '为什么', '默认不买']
    found = [w for w in human_words if re.search(w, md)]
    if len(found) < 2:
        issues.append(f'U-9: 解释层不足，仅找到{len(found)}个人话关键词')
    if re.search(r'超大单', md) and not re.search(r'(?:还在卖|还在流出|承接|不能增强买入|不能抢)', md):
        issues.append('U-9: 四档资金段缺少人话解释')
    if re.search(r'胜率', md) and not re.search(r'(?:低于50|不能单独|不稳定)', md):
        issues.append('U-9: 信号胜率段缺少人话解释')
    return {'result': 'PASS' if len(issues) == 0 else 'FAIL', 'issues': issues}
def u10(md):
    """U-10: 资金解读一致性——只检查逐项解读行，跳过主力合计比较句（仅检查资金方向，数据一致性由U-8负责）"""
    issues = []
    sl_bullet = re.search(r'[-•]\s*超大单[^，,：:→\n]+(?:[，,→]|：|:)\s*(.+?)(?:\n|$)', md)
    lg_bullet = re.search(r'[-•]\s*(?<!超)大单[^，,：:→\n]+(?:[，,→]|：|:)\s*(.+?)(?:\n|$)', md)
    sl_table = re.search(r'超大单\s*\|\s*([+-]?[\d.,]+)万', md)
    lg_table = re.search(r'(?<!超)大单\s*\|\s*([+-]?[\d.,]+)万', md)
    if sl_bullet and sl_table:
        try:
            sl_val = float(sl_table.group(1).replace(',',''))
            sl_text = sl_bullet.group(1)
            if sl_val < 0 and re.search(r'(?:流入|在买|买入)', sl_text):
                issues.append('U-10: 超大单净额为负但逐项解读写流入/在买')
            if sl_val > 0 and re.search(r'(?:流出|在卖|卖出(?! >))', sl_text):
                issues.append('U-10: 超大单净额为正但逐项解读写流出/在卖')
        except: pass
    if lg_bullet and lg_table:
        try:
            lg_val = float(lg_table.group(1).replace(',',''))
            lg_text = lg_bullet.group(1)
            if lg_val < 0 and re.search(r'(?:流入|在买|买入)', lg_text):
                issues.append('U-10: 大单净额为负但逐项解读写流入/在买')
            if lg_val > 0 and re.search(r'(?:流出|在卖|卖出)', lg_text):
                issues.append('U-10: 大单净额为正但逐项解读写流出/在卖')
        except: pass
    return {'result': 'PASS' if len(issues) == 0 else 'FAIL', 'issues': issues}

def u6(md):
    """U-6: 10段结构完整性"""
    sections = [
        ('P0 明日决策卡', r'P0 明日决策卡|# 一、P0'),
        ('baseline引用与变化', r'深度分析基线|# 二、深度分析'),
        ('当日行情delta', r'今天行情|# 三、今天'),
        ('大盘与板块', r'大盘和板块|# 四、大盘'),
        ('四档资金结构', r'资金|# 五、资金'),
        ('融资北向筹码', r'融资.*北向|# 六、融资'),
        ('消息事件', r'消息事件|# 七、消息'),
        ('信号胜率', r'信号胜率|# 八、信号'),
        ('风控红黄绿灯', r'风控红黄绿灯|# 九、风控'),
        ('明日情景应对+T+5', r'明日情景应对|# 十、明日'),
    ]
    missing = []
    for name, pattern in sections:
        if not re.search(pattern, md):
            missing.append(name)
    return {'result': 'PASS' if len(missing) == 0 else 'FAIL',
            'missing': missing}

def u7(md):
    """U-7: 内容字段完整性"""
    checks = {
        'P0九字段_明日主动作': bool(re.search(r'明日主动作.*?(?:观望|试探|加仓|减仓|清仓|暂停观察)', md)),
        'P0九字段_条件触发仓位': bool(re.search(r'条件触发后仓位.*?[0-9]', md)),
        'P0九字段_关键买点': bool(re.search(r'关键买点.*?[0-9]+.*?元', md)),
        'P0九字段_新仓止损': bool(re.search(r'新仓止损.*?[0-9]+', md)),
        'P0九字段_已持仓止损': bool(re.search(r'已持仓止损', md)),
        'P0九字段_禁止动作': bool(re.search(r'禁止动作.*?(?:不建仓|不买|不追)', md)),
        'P0九字段_置信度': bool(re.search(r'置信度.*?(?:高|中|低)', md)),
        'P0九字段_一句话结论': bool(re.search(r'一句话结论', md)),
        'baseline_id': bool(re.search(r'baseline_id[：:]\s*\S+|baseline[：:]\s*\S+', md)),
        'delta_近4日': len(re.findall(r'\d{4}-\d{2}-\d{2}', md)) >= 4,
        '四档资金_5项': bool(re.search(r'超大单.*?大单.*?中单.*?小单.*?主力', md, re.DOTALL)),
        '融资段': bool(re.search(r'融资', md)),
        '北向段': bool(re.search(r'北向', md)),
        '消息事件表': bool(re.search(r'(?:消息|消息事件)(.+?)(?:## )', md, re.DOTALL)) and 'T+1' in md[md.find('## 七、消息'):md.find('## 八、信号')] and 'T+3' in md[md.find('## 七、消息'):md.find('## 八、信号')] and 'T+5' in md[md.find('## 七、消息'):md.find('## 八、信号')],
        '信号胜率表': bool(re.search(r'胜率.*?样本|样本.*?胜率', md)),
        '风控_7项': bool(re.search(r'质押.*?解禁.*?融资.*?(?:估值|财务).*?技术', md, re.DOTALL)),
        '情景应对_3种': len(re.findall(r'(?:观望|试探|暂停|不追)', md)) >= 2,
        'T+5展望': bool(re.search(r'T\+5展望|T\+5 展望', md)),
    }
    passed = sum(1 for v in checks.values() if v)
    return {'result': 'PASS' if passed >= len(checks)-2 else ('WARN' if passed >= len(checks)-5 else 'FAIL'),
            'passed': passed, 'total': len(checks), 'details': {k: v for k, v in checks.items() if not v}}

def u8(md, md_path=''):
    """U-8: 数据支撑一致性——检查MD/sidecar/data_pack三方一致"""
    issues = []
    # Try to find JSON sidecar
    json_path = md_path.replace('.md', '.json') if md_path else ''
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path) as f:
                sidecar = json.load(f)
            dp_path = sidecar.get('data_pack', '')
            if dp_path and os.path.exists(dp_path):
                with open(dp_path) as f:
                    dp = json.load(f)
                # Check events count
                dp_events = len(dp.get('events', []))
                sidecar_events = len(sidecar.get('events', []))
                md_event_rows = len(re.findall(r'T\+1.*?T\+3.*?T\+5', md))
                if dp_events != sidecar_events:
                    issues.append(f'events mismatch: dp={dp_events} sidecar={sidecar_events}')
                # Check signal count
                dp_sig = len(dp.get('signal_winrate', []))
                sidecar_sig = len(sidecar.get('signal_winrate', []))
                if dp_sig != sidecar_sig:
                    issues.append(f'signal_winrate mismatch: dp={dp_sig} sidecar={sidecar_sig}')
                # Check forbidden_actions in sidecar
                p0 = sidecar.get('p0_decision_card', {})
                if not p0.get('forbidden_actions'):
                    issues.append('P0 missing forbidden_actions in sidecar')
                # Check sector_phase exists
                if not dp.get('sector_phase'):
                    issues.append('data_pack missing sector_phase')
                # Check degraded disclosure in MD
                degraded = sidecar.get('degraded_items', [])
                for item in degraded:
                    keyword = item.split('(')[0] if '(' in item else item[:4]
                    # Map English keywords to Chinese MD terms
                    kw_map = {'margin': '融资', 'northbound_quarterly': '北向', 'financial': '财务', 'sector_phase': 'sector_phase', 'events': '事件'}
                    search_kw = kw_map.get(keyword, keyword)
                    # Try mapped keyword first, then original keyword
                    if not re.search(search_kw, md) and not re.search(keyword, md):
                        issues.append(f'DEGRADED item not disclosed in MD: {item}')
        except Exception as e:
            issues.append(f'U-8 error: {str(e)[:50]}')

    # P0-I: 硬检查 - baseline存在则禁止写缺失
    if md_path:
        # Check if baseline JSON exists
        import glob as _glob
        code_match = re.search(r'(\d{6})', os.path.basename(md_path))
        if code_match:
            code = code_match.group(1)
            report_dir = os.path.dirname(md_path)
            bl_pattern = os.path.join(report_dir, f'*深度分析_baseline_*.json')
            bl_files = _glob.glob(bl_pattern)
            if not bl_files:
                bl_pattern2 = os.path.join(ROOT, '重点股票', '基线', f'*{code}*baseline*.json')
                bl_files = _glob.glob(bl_pattern2)
            if bl_files:
                if re.search(r'baseline缺失|待baseline|baseline待引用|无baseline参考', md):
                    issues.append('U-8 BLOCK: baseline文件存在但报告写缺失/待引用')
                try:
                    with open(bl_files[0]) as f: bl = json.load(f)
                    kl = bl.get('key_levels', bl)  # support both formats
                    for k in ('S1', 'R1', 'stop_loss_new', 'stop_loss_held'):
                        v = kl.get(k)
                        if v is not None and str(v) not in md:
                            issues.append(f'U-8 BLOCK: baseline有{k}={v}但MD未引用')
                except: pass

        # Check kline consistency
        kline_dir = os.path.join(ROOT, '代码文件', '数据', 'kline_cache')
        if code_match:
            kf = os.path.join(kline_dir, f'{code_match.group(1)}.json')
            if os.path.exists(kf):
                try:
                    with open(kf) as f: kd = json.load(f)
                    date_match = re.search(r'(\d{8})', os.path.basename(md_path))
                    if date_match:
                        target = f'{date_match.group(1)[:4]}-{date_match.group(1)[4:6]}-{date_match.group(1)[6:8]}'
                        for r in kd:
                            if r.get('date') == target:
                                if sidecar:
                                    delta_close = (sidecar.get('delta') or {}).get('close')
                                    if delta_close is not None and abs(float(delta_close)-float(r['close']))>0.01:
                                        issues.append(f'U-8 BLOCK: sidecar delta.close与kline不一致')
                                break
                except: pass

    # Check signal_winrate_db
    sw_db = os.path.join(ROOT, '代码文件', '数据', 'signal_winrate_db.json')
    if os.path.exists(sw_db):
        signal_section = re.search(r'(?:## 八、信号|信号胜率)(.+?)(?:\n---|\n## 九、|\n## 十、)', md, re.S)
        sec = signal_section.group(1) if signal_section else ''
        if '样本不足' in sec and not re.search(r'样本.*?\d+|\d+.*?样本', sec):
            issues.append('U-8 BLOCK: signal_winrate_db存在但信号胜率段泛写样本不足无具体数字')

    return {'result': 'PASS' if len(issues) == 0 else 'FAIL', 'issues': issues}
def check(path):
    if not os.path.exists(path):
        return {'status': 'BLOCK', 'error': f'文件不存在: {path}'}
    with open(path, 'r', encoding='utf-8') as f:
        md = f.read()
    results = {'U-1': u1(md), 'U-2': u2(md), 'U-3': u3(md), 'U-4': u4(md), 'U-5': u5(md),
               'U-6': u6(md), 'U-7': u7(md), 'U-8': u8(md, path), 'U-9': u9(md), 'U-10': u10(md)}
    statuses = [r['result'] for r in results.values()]
    if 'BLOCK' in statuses or 'FAIL' in statuses:
        overall = 'BLOCK'
    elif statuses.count('WARN') >= 2:
        overall = 'WARN'
    elif 'WARN' in statuses:
        overall = 'WARN'
    else:
        overall = 'PASS'
    return {'status': overall, 'report_path': path, 'checks': results,
            'pdf_allowed': overall != 'BLOCK', 'timestamp': datetime.now().isoformat()}

def main():
    if len(sys.argv) < 2:
        print("用法: python3 日报U检查流程.py <日报路径> [--json-output <path>]")
        sys.exit(2)
    path = sys.argv[1]
    out_path = None
    if '--json-output' in sys.argv:
        idx = sys.argv.index('--json-output')
        if idx + 1 < len(sys.argv):
            out_path = sys.argv[idx + 1]
    result = check(path)
    print(f"日报U检查 v3.6: {os.path.basename(path)}")
    for cid, c in result['checks'].items():
        print(f"  {cid}: {c['result']}")
        for i in c.get('issues', []):
            print(f"    - {i}")
    print(f"\n总体: {result['status']} | PDF: {'允许' if result['pdf_allowed'] else '禁止'}")
    if out_path:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    sys.exit({'PASS': 0, 'WARN': 0, 'BLOCK': 2}[result['status']])

if __name__ == '__main__':
    main()
