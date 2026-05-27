"""
玉夜 · 历史数据沉淀巡检+修复工具 (手动运维阶段 v1.0)
====================================================
用途: 每周一运行，核查历史数据完整性+准确性+交易日覆盖
修复: A类自动修复（含熔断），B/C类报告人工处理
预计固化: 2026年6月8日周 → 走§七流程正式纳入工程体系
"""

import json
import os
import sys
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

# === 配置 ===
BASE = Path(__file__).parent
DATA_DIR = BASE / '历史数据'
HOLIDAY_FILE = BASE / '每日荐股' / '运营记录' / 'holidays_2026.csv'
SCOPE_DAYS = 60  # 检查最近N天（覆盖约2个月/40个交易日）

# 每交易日必选文件清单: (子目录, 文件名模板, 描述)
REQUIRED_FILES = [
    ('04_原始数据', '{date}_data_full.json', '全量采集数据'),
    ('04_原始数据', '{date}_data_scored.json', '评分数据'),
    ('04_原始数据', '{date}_data_final.json', '终选数据'),
    ('04_原始数据', '{date}_score_history.jsonl', '评分历史'),
    ('05_参考数据', '{date}_dynamic_pool.json', '动态股票池'),
    ('05_参考数据', '{date}_sector_data.json', '板块聚合数据'),
    ('02_评估数据', '评估数据_{date}.json', '评估数据'),
    ('02_评估数据', '{date}_records.csv', '后评估明细'),
    ('02_评估数据', '{date}_summary.csv', '后评估汇总'),
    ('01_交易快照', 'snapshot_{date}.json', '交易快照'),
]

OPTIONAL_FILES = [
    ('04_原始数据', '{date}_data_final_optimized.json', '优化终选'),
    ('05_参考数据', '{date}_eastmoney_sector_map.json', '东方财富板块映射'),
    ('05_参考数据', '{date}_industry_map.json', '行业映射'),
    ('02_评估数据', '{date}_predictions.csv', '预判记录'),
    ('02_评估数据', '评估结果_{date}.json', '评估结果'),
]

# A类可自动修复: (源文件, 目标文件, 修复方式)
AUTO_REPAIR_RULES = {
    'data_final': {
        'source': 'data_scored',
        'method': 'extract_final_from_scored',
        'desc': '从scored提取Top-N passed股票'
    },
    'data_final_optimized': {
        'source': 'data_final',
        'method': 'copy',
        'desc': '复制data_final'
    },
    'eastmoney_sector_map': {
        'source': 'nearest_date',
        'method': 'copy_nearest',
        'desc': '从最近日期复制'
    },
    'industry_map': {
        'source': 'nearest_date',
        'method': 'copy_nearest',
        'desc': '从最近日期复制'
    },
}

# 熔断阈值
CIRCUIT_BREAKER_SINGLE_DAY = 3   # 单日缺失>3个必选 → 不自动修
CIRCUIT_BREAKER_CONSECUTIVE = 3  # 连续N天同类缺失 → 不自动修


# === 交易日历 ===
def load_holidays():
    """从CSV加载节假日"""
    holidays = set()
    makeup_days = set()
    if HOLIDAY_FILE.exists():
        with open(HOLIDAY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                parts = line.split(',')
                if len(parts) >= 2:
                    typ, d = parts[0].strip(), parts[1].strip()
                    if typ == 'holiday':
                        holidays.add(d)
                    elif typ == 'makeup':
                        makeup_days.add(d)
    return holidays, makeup_days


def is_trading_day(d, holidays, makeup_days):
    """判断是否为A股交易日"""
    d_str = d.strftime('%Y-%m-%d')
    # 调休补班 → 交易日
    if d_str in makeup_days:
        return True
    # 周末 → 非交易日
    if d.weekday() >= 5:
        return False
    # 节假日 → 非交易日
    if d_str in holidays:
        return False
    return True


def enumerate_trading_days(scope_days):
    """枚举范围内的所有交易日"""
    holidays, makeup_days = load_holidays()
    today = date.today()
    start = today - timedelta(days=scope_days)
    trading_days = []
    d = start
    while d <= today:
        if is_trading_day(d, holidays, makeup_days):
            trading_days.append(d.strftime('%Y%m%d'))
        d += timedelta(days=1)
    return trading_days, holidays, makeup_days


# === 文件检查 ===
def check_file_exists(subdir, template, date_str):
    """检查单个文件是否存在且有效（JSON/JSONL/CSV）"""
    fname = template.format(date=date_str)
    fpath = DATA_DIR / subdir / fname
    if not fpath.exists():
        return {'status': 'missing', 'path': str(fpath.relative_to(BASE))}

    fsize = fpath.stat().st_size
    if fsize == 0:
        return {'status': 'empty', 'path': str(fpath.relative_to(BASE))}

    ext = fpath.suffix.lower()

    # CSV: 只检查存在+非空
    if ext == '.csv':
        return {
            'status': 'ok',
            'path': str(fpath.relative_to(BASE)),
            'size': fsize,
            'struct': 'csv',
            'data': None
        }

    # JSONL: 检查每行是有效JSON
    if ext == '.jsonl':
        try:
            with open(fpath, 'r', encoding='utf-8-sig') as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                return {'status': 'empty', 'path': str(fpath.relative_to(BASE))}
            json.loads(lines[0])
            return {
                'status': 'ok',
                'path': str(fpath.relative_to(BASE)),
                'size': fsize,
                'struct': f'jsonl[{len(lines)}]',
                'data': None
            }
        except (json.JSONDecodeError, Exception) as e:
            return {'status': 'corrupt', 'path': str(fpath.relative_to(BASE)), 'error': str(e)[:80]}

    # JSON: 完整解析
    try:
        with open(fpath, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        had_bom = fpath.read_bytes().startswith(b'\xef\xbb\xbf')

        # 结构检查
        if isinstance(data, list):
            struct = f'array[{len(data)}]'
        elif isinstance(data, dict):
            struct = f'dict<{",".join(list(data.keys())[:6])}>'
        else:
            struct = type(data).__name__

        return {
            'status': 'ok',
            'path': str(fpath.relative_to(BASE)),
            'size': fsize,
            'bom': had_bom,
            'struct': struct,
            'data': data  # 保留给内部一致性检查
        }
    except json.JSONDecodeError as e:
        return {'status': 'corrupt', 'path': str(fpath.relative_to(BASE)), 'error': str(e)[:80]}
    except Exception as e:
        return {'status': 'error', 'path': str(fpath.relative_to(BASE)), 'error': str(e)[:80]}


# === 内部一致性检查 ===
def check_consistency(day_results):
    """跨文件内部一致性校验"""
    issues = []

    scored = day_results.get('data_scored', {})
    full = day_results.get('data_full', {})
    final = day_results.get('data_final', {})
    dpool = day_results.get('dynamic_pool', {})

    # 1. scored处理总数 = full股票数（AllStocks仅含passed，应用Summary.Total）
    if scored.get('data') and full.get('data'):
        summary = scored['data'].get('Summary', {})
        scored_count = summary.get('Total', 0)
        if not scored_count:
            scored_count = len(scored['data'].get('AllStocks', [])) + len(scored['data'].get('VetoedStocks', []))
        full_count = len(full['data'].get('Stocks', []))
        if scored_count != full_count:
            issues.append(f'股票数不一致: scored={scored_count} vs full={full_count}')

    # 2. final股票 ⊆ scored passed
    if final.get('data') and scored.get('data'):
        final_codes = {s['Code'] for s in final['data']}
        passed_codes = {s['Code'] for s in scored['data'].get('AllStocks', [])
                        if s.get('VetoStatus') == 'passed'}
        if not final_codes.issubset(passed_codes):
            issues.append(f'final含非passed股票: {final_codes - passed_codes}')

    # 3. final数量 ≤ passed数量
    if final.get('data') and scored.get('data'):
        passed_count = sum(1 for s in scored['data'].get('AllStocks', [])
                          if s.get('VetoStatus') == 'passed')
        final_count = len(final['data'])
        if final_count > passed_count:
            issues.append(f'final数量({final_count}) > passed数量({passed_count})')

    # 4. dynamic_pool涵盖scored全量
    if dpool.get('data') and scored.get('data'):
        pool_codes = {s['Code'] for s in dpool['data'].get('Stocks', [])}
        scored_codes = {s['Code'] for s in scored['data'].get('AllStocks', [])}
        missing = scored_codes - pool_codes
        if missing:
            issues.append(f'dynamic_pool缺失{len(missing)}只股票')

    return issues


# === 修复分类 ===
def classify_gap(file_type, date_str):
    """分类缺失/损坏的可修复性: A(自动) / B(半自动) / C(不可修)"""
    if file_type in AUTO_REPAIR_RULES:
        return 'A'
    if file_type in ('dynamic_pool', 'sector_data'):
        return 'B'
    return 'C'


# === A类自动修复 ===
def repair_data_final(date_str):
    """从scored提取final"""
    scored_path = DATA_DIR / '04_原始数据' / f'{date_str}_data_scored.json'
    if not scored_path.exists():
        return False, '源文件data_scored不存在'

    with open(scored_path, 'r', encoding='utf-8-sig') as f:
        scored = json.load(f)

    FINAL_KEYS = ['PE', 'MktCap', 'Name', 'TurnoverRate', 'Amplitude', 'TotalScore',
                  'S_News', 'S_Tech', 'Industry', 'S_Base', 'ChangePct', 'S_Fund',
                  'Price', 'Volume', 'S_Risk', 'Code', 'S_Money']

    passed = [s for s in scored['AllStocks'] if s.get('VetoStatus') == 'passed']
    passed.sort(key=lambda x: x.get('TotalScore', 0), reverse=True)
    final = [{k: s[k] for k in FINAL_KEYS if k in s} for s in passed[:len(passed)]]

    out_path = DATA_DIR / '04_原始数据' / f'{date_str}_data_final.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False)
    return True, f'生成{len(final)}只股票'


def repair_copy_file(date_str, file_type):
    """复制修复 (optimized←final, maps←nearest)"""
    if file_type == 'data_final_optimized':
        src = DATA_DIR / '04_原始数据' / f'{date_str}_data_final.json'
        dst = DATA_DIR / '04_原始数据' / f'{date_str}_data_final_optimized.json'
        if src.exists():
            dst.write_bytes(src.read_bytes())
            return True, '复制自data_final'
        return False, '源文件data_final不存在'

    if file_type in ('eastmoney_sector_map', 'industry_map'):
        ref_dir = DATA_DIR / '05_参考数据'
        # 找最近日期的同名文件
        pattern = f'2026'  # 同年
        candidates = sorted(ref_dir.glob(f'*_{file_type}.json'))
        if candidates:
            latest = candidates[-1]
            dst = ref_dir / f'{date_str}_{file_type}.json'
            shutil.copy(latest, dst)
            return True, f'复制自{latest.stem[:8]}'
        return False, '无可用近邻'

    return False, '未知修复类型'


# === 主巡检逻辑 ===
def run_inspection(scope_days=SCOPE_DAYS, auto_repair=True):
    """主巡检函数"""
    print("=" * 60)
    print("  玉夜 · 历史数据沉淀巡检")
    print(f"  时间: {date.today().isoformat()}")
    print(f"  范围: 最近{scope_days}天")
    print("=" * 60)

    trading_days, holidays, makeup_days = enumerate_trading_days(scope_days)
    print(f"\n交易日历: {len(trading_days)}个交易日")

    # 逐日检查
    day_results = {}
    total_ok = 0
    total_warn = 0
    total_fail = 0
    repairs_applied = []
    consecutive_missing = defaultdict(int)  # 用于熔断检测

    # 先扫描，不修复
    for td in trading_days:
        day_files = {}
        for subdir, template, desc in REQUIRED_FILES:
            ftype = template.split('.')[0].replace('{date}_', '').replace('_data', '').replace('评估数据_', 'eval_')
            # 简化: 从template提取文件类型标识
            key = template.replace('{date}_', '').replace('.json', '')
            key = key.replace('_data', '').replace('评估数据_', 'eval_')
            # 更简洁的key
            if '_data_full' in template: key = 'data_full'
            elif '_data_scored' in template: key = 'data_scored'
            elif '_data_final_optimized' in template: key = 'data_final_optimized'
            elif '_data_final' in template: key = 'data_final'
            elif 'score_history' in template: key = 'score_history'
            elif 'dynamic_pool' in template: key = 'dynamic_pool'
            elif 'sector_data' in template: key = 'sector_data'
            elif 'industry_map' in template: key = 'industry_map'
            elif 'eastmoney_sector_map' in template: key = 'eastmoney_sector_map'
            elif 'records' in template: key = 'records'
            elif 'summary' in template: key = 'summary'
            elif '评估数据' in template: key = 'eval_data'
            elif 'snapshot' in template: key = 'snapshot'

            result = check_file_exists(subdir, template, td)
            result['desc'] = desc
            result['type'] = key
            result['required'] = True
            # snapshot当日未生成属正常（盘后管线产出），不标记为required
            if key == 'snapshot' and td == date.today().strftime('%Y%m%d'):
                result['required'] = False
            # records/summary/predictionsCSV当日可能未生成
            if key in ('records', 'summary') and td == date.today().strftime('%Y%m%d'):
                result['required'] = False
            day_files[key] = result

        # Optional files
        for subdir, template, desc in OPTIONAL_FILES:
            key = template.replace('{date}_', '').replace('.json', '').replace('.csv', '')
            if 'eastmoney' in template: key = 'eastmoney_sector_map'
            elif 'industry_map' in template: key = 'industry_map'
            elif 'predictions' in template: key = 'predictions'
            elif '评估结果' in template: key = 'eval_result'
            result = check_file_exists(subdir, template, td)
            result['desc'] = desc
            result['type'] = key
            result['required'] = False
            day_files[key] = result

        # Consistency check
        consistency_issues = check_consistency(day_files)

        # Aggregate
        required_missing = [k for k, v in day_files.items()
                           if v.get('required') and v['status'] != 'ok']
        optional_missing = [k for k, v in day_files.items()
                           if not v.get('required') and v['status'] != 'ok']
        corrupt = [k for k, v in day_files.items() if v['status'] == 'corrupt']

        day_results[td] = {
            'files': day_files,
            'required_missing': required_missing,
            'optional_missing': optional_missing,
            'corrupt': corrupt,
            'consistency_issues': consistency_issues,
        }

    # 找到第一个有数据的交易日（管线启动日）
    first_data_day = None
    for td in sorted(day_results.keys()):
        dr = day_results[td]
        if len(dr['required_missing']) < len(REQUIRED_FILES):
            first_data_day = td
            break

    # 统计并报告
    print(f"\n{'='*60}")
    print(f"  逐日扫描结果")
    if first_data_day:
        print(f"  管线启动日: {first_data_day[:4]}-{first_data_day[4:6]}-{first_data_day[6:8]} (此前无数据沉淀)")
    print(f"{'='*60}")

    # 合并显示预管线期
    pre_pipeline_days = [td for td in sorted(day_results.keys())
                         if len(day_results[td]['required_missing']) == len(REQUIRED_FILES)]
    if pre_pipeline_days:
        first_pp = pre_pipeline_days[0]
        last_pp = pre_pipeline_days[-1]
        print(f"  [INFO] {first_pp[:4]}-{first_pp[4:6]}-{first_pp[6:8]} ~ {last_pp[:4]}-{last_pp[4:6]}-{last_pp[6:8]}: {len(pre_pipeline_days)}天预管线期, 无数据沉淀(正常)")
        for td in pre_pipeline_days:
            day_results[td]['_pre_pipeline'] = True
            total_ok += 1  # 预管线期不计入WARN

    for td in sorted(day_results.keys()):
        dr = day_results[td]
        if dr.get('_pre_pipeline'):
            continue

        n_missing = len(dr['required_missing'])
        n_corrupt = len(dr['corrupt'])
        n_cons = len(dr['consistency_issues'])

        if n_missing == 0 and n_corrupt == 0 and n_cons == 0:
            total_ok += 1
            status = 'PASS'
        elif n_corrupt > 0:
            total_fail += 1
            status = 'FAIL'
        else:
            total_warn += 1
            status = 'WARN'

        date_display = f'{td[:4]}-{td[4:6]}-{td[6:8]}'
        print(f"  [{status}] {date_display}", end='')
        if n_missing:
            print(f" | missing {n_missing}: {', '.join(dr['required_missing'])}", end='')
        if n_corrupt:
            print(f" | corrupt {n_corrupt}: {', '.join(dr['corrupt'])}", end='')
        if n_cons:
            print(f" | inconsistent: {'; '.join(dr['consistency_issues'])}", end='')
        if n_missing == 0 and n_corrupt == 0 and n_cons == 0:
            print(f" | all present", end='')
        print()

    # 修复阶段
    if auto_repair:
        print(f"\n{'='*60}")
        print(f"  A类自动修复 (熔断: 单日>{CIRCUIT_BREAKER_SINGLE_DAY}缺/连续>{CIRCUIT_BREAKER_CONSECUTIVE}天)")
        print(f"{'='*60}")

        # 熔断检查: 连续天数统计
        for td in sorted(day_results.keys()):
            dr = day_results[td]
            if dr.get('_pre_pipeline'):
                continue
            for ftype in dr['required_missing']:
                consecutive_missing[ftype] += 1
            for ftype in list(consecutive_missing.keys()):
                if ftype not in dr['required_missing']:
                    consecutive_missing[ftype] = 0

        for td in sorted(day_results.keys()):
            dr = day_results[td]
            if dr.get('_pre_pipeline'):
                continue
            if not dr['required_missing']:
                continue

            # 熔断判断
            if len(dr['required_missing']) > CIRCUIT_BREAKER_SINGLE_DAY:
                print(f"  [熔断] {td[:4]}-{td[4:6]}-{td[6:8]}: 单日缺失{len(dr['required_missing'])}个>{CIRCUIT_BREAKER_SINGLE_DAY}，跳过自动修复")
                continue

            for ftype in dr['required_missing']:
                if consecutive_missing.get(ftype, 0) >= CIRCUIT_BREAKER_CONSECUTIVE:
                    print(f"  [熔断] {td[:4]}-{td[4:6]}-{td[6:8]}/{ftype}: 连续缺失{consecutive_missing[ftype]}天>{CIRCUIT_BREAKER_CONSECUTIVE}，跳过自动修复")
                    continue

                grade = classify_gap(ftype, td)
                if grade == 'A':
                    success, msg = repair_data_final(td) if ftype == 'data_final' else \
                                  (repair_copy_file(td, ftype) if ftype in ('data_final_optimized', 'eastmoney_sector_map', 'industry_map') else \
                                   (False, '未实现'))
                    if success:
                        repairs_applied.append(f'{td}/{ftype}: {msg}')
                        print(f"  [修复] {td[:4]}-{td[4:6]}-{td[6:8]}/{ftype}: {msg}")
                    else:
                        print(f"  [修复失败] {td[:4]}-{td[4:6]}-{td[6:8]}/{ftype}: {msg}")
                elif grade == 'B':
                    print(f"  [需人工B] {td[:4]}-{td[4:6]}-{td[6:8]}/{ftype}: 半自动修复，需玉夜确认")
                else:
                    print(f"  [不可修C] {td[:4]}-{td[4:6]}-{td[6:8]}/{ftype}: 源数据已过期")

    # 汇总
    print(f"\n{'='*60}")
    print(f"  巡检汇总")
    print(f"{'='*60}")
    print(f"  交易日检查: {len(trading_days)}天")
    print(f"  PASS: {total_ok}  |  WARN: {total_warn}  |  FAIL: {total_fail}")
    print(f"  自动修复: {len(repairs_applied)}项")
    if repairs_applied:
        for r in repairs_applied:
            print(f"    - {r}")

    return day_results, repairs_applied


if __name__ == '__main__':
    import shutil
    do_repair = '--no-repair' not in sys.argv
    run_inspection(auto_repair=do_repair)
