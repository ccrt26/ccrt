#!/usr/bin/env python3
"""数据质量闸门（DQ-Gate）— 每日管线Phase 0.5，自动检查+分级阻断+通报"""
import json, os, sys
from dq_issue_classifier import classify_report
from datetime import datetime
from collections import defaultdict

# === 配置 ===
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, '数据')
GATE_LOG = os.path.join(BASE, '..', 'logs', 'gates', 'gate_check.jsonl')
PROJECT_ROOT = os.path.dirname(BASE)
DAILY_TARGETS = os.path.join(PROJECT_ROOT, '00_项目地基', '02_权威注册表', 'daily_report_targets.json')
KLINE_CACHE_DIR = os.path.join(DATA_DIR, 'kline_cache')

THRESHOLDS = {
    'quote_coverage': 80,      # 行情覆盖率 ≥80%，否则FAIL
    'kline_min_bars': 30,      # K线最少根数，否则FAIL
    'api_consecutive_fail': 3, # API连续不可用天数，否则FAIL
    'cache_hit_rate': 10,      # 缓存命中率 ≥10%（含Tier 1实时数据不缓存，所以阈值低）
    'financial_coverage': 90,  # 财务覆盖率 ≥90%，否则WARN
    'fundflow_coverage': 50,   # 资金流覆盖率 ≥50%，否则WARN
    'gate_fail_rate': 60,      # 近5次门禁失败率 ≤60%，否则WARN
    # P1-3 新增阈值
    'cache_freshness_hours': 24,     # 缓存新鲜度上限(小时)
    'anomaly_zscore': 3.0,           # Z-score异常检测阈值
    'anomaly_mad': 5.0,              # MAD异常检测阈值
    'field_conflict_pct': 5.0,       # 字段冲突允许百分比
}

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def norm_date(value):
    return str(value or '').replace('-', '')[:8]

def load_quality_scope_codes():
    targets = load_json(DAILY_TARGETS)
    if not isinstance(targets, dict):
        return set()
    return {
        str(t.get('code', ''))
        for t in targets.get('active_targets', [])
        if t.get('enabled') and t.get('code')
    }

def kline_cache_rows(code):
    path = os.path.join(KLINE_CACHE_DIR, f'{code}.json')
    rows = load_json(path)
    return rows if isinstance(rows, list) else []

def kline_cache_has_date(code, target_date):
    target = norm_date(target_date)
    for row in kline_cache_rows(code):
        if not isinstance(row, dict):
            continue
        d = norm_date(row.get('date') or row.get('trade_date'))
        if d == target:
            return True
    return False

def kline_cache_has_min_bars(code, min_bars, target_date):
    rows = kline_cache_rows(code)
    return len(rows) >= min_bars and kline_cache_has_date(code, target_date)

def check_data_full():
    """检查 data_full.json 数据完整性"""
    issues = []
    metrics = {}

    data = load_json(os.path.join(DATA_DIR, 'data_full.json'))
    if not data:
        return [{'id': 'DQ-F1', 'severity': 'FAIL', 'desc': 'data_full.json 不可读'}], metrics

    meta = data.get('_Meta', {})
    cache = meta.get('cache_stats', {})
    stocks = data.get('Stocks', [])
    financials = data.get('Financials', {})
    fundflows = data.get('FundFlows', {})
    scope_codes = load_quality_scope_codes()
    if scope_codes:
        scoped_stocks = [s for s in stocks if str(s.get('Code') or s.get('code', '')) in scope_codes]
    else:
        scoped_stocks = stocks
    target_date = norm_date(meta.get('target_date') or meta.get('trade_date') or meta.get('data_date'))
    metrics['quality_scope'] = 'daily_report_targets' if scope_codes else 'data_full_stocks'
    metrics['quality_scope_count'] = len(scoped_stocks)

    # 行情覆盖率
    total = len(scoped_stocks)
    has_price = sum(
        1 for s in scoped_stocks
        if (s.get('Price') and s.get('Price') > 0)
        or kline_cache_has_date(str(s.get('Code') or s.get('code', '')), target_date)
    )
    metrics['quote_coverage'] = round(has_price / total * 100, 1) if total else 0
    if metrics['quote_coverage'] < THRESHOLDS['quote_coverage']:
        issues.append({'id': 'DQ-F1', 'severity': 'FAIL',
                       'desc': f"行情覆盖率{metrics['quote_coverage']}% < {THRESHOLDS['quote_coverage']}%"})

    # K线完整性
    kline_ok = sum(
        1 for s in scoped_stocks
        if (s.get('KClose') and len(s.get('KClose', [])) >= THRESHOLDS['kline_min_bars'])
        or kline_cache_has_min_bars(str(s.get('Code') or s.get('code', '')), THRESHOLDS['kline_min_bars'], target_date)
    )
    metrics['kline_completeness'] = round(kline_ok / total * 100, 1) if total else 0
    missing_kline = [
        str(s.get('Code') or s.get('code', ''))
        for s in scoped_stocks
        if not (
            (s.get('KClose') and len(s.get('KClose', [])) >= THRESHOLDS['kline_min_bars'])
            or kline_cache_has_min_bars(str(s.get('Code') or s.get('code', '')), THRESHOLDS['kline_min_bars'], target_date)
        )
    ]
    if missing_kline:
        issues.append({'id': 'DQ-F2', 'severity': 'FAIL',
                       'desc': f"K线数据不足({THRESHOLDS['kline_min_bars']}根): {missing_kline[:5]}"})

    # 缓存命中率（含Tier 1实时数据不缓存，所以阈值较低）
    tushare_hit = cache.get('tushare_hit', 0)
    ps_cache_hit = cache.get('cache_hit', 0)
    pipeline_hit = cache.get('pipeline_hit', 0)
    total_miss = cache.get('miss', 0)
    total_req = tushare_hit + ps_cache_hit + pipeline_hit + total_miss
    metrics['cache_hit_rate'] = round((tushare_hit + ps_cache_hit + pipeline_hit) / total_req * 100, 1) if total_req else 0
    # 注意: miss中包含Tier 1实时行情(不应缓存)+未实现接口, 阈值设为10%
    if metrics['cache_hit_rate'] < 10 and total_req > 50:
        issues.append({'id': 'DQ-W1', 'severity': 'WARN',
                       'desc': f"缓存命中率{metrics['cache_hit_rate']}% < 10%（Tier 2/3数据缓存可能失效）"})
    # Tier 1本地缓存(Tushare)健康检查
    if tushare_hit == 0 and total_req > 50:
        issues.append({'id': 'DQ-W1b', 'severity': 'WARN',
                       'desc': 'Tushare本地缓存命中=0，Tier 2/3缓存可能全部失效'})

    # 财务覆盖率
    fin_count = len(set(financials.keys()) & scope_codes) if scope_codes and isinstance(financials, dict) else (len(financials) if isinstance(financials, dict) else 0)
    metrics['financial_coverage'] = round(fin_count / total * 100, 1) if total else 0
    if metrics['financial_coverage'] < THRESHOLDS['financial_coverage']:
        issues.append({'id': 'DQ-W2', 'severity': 'WARN',
                       'desc': f"财务覆盖率{metrics['financial_coverage']}% < {THRESHOLDS['financial_coverage']}%"})

    # 资金流覆盖率
    ff_count = len(set(fundflows.keys()) & scope_codes) if scope_codes and isinstance(fundflows, dict) else (len(fundflows) if isinstance(fundflows, dict) else 0)
    metrics['fundflow_coverage'] = round(ff_count / total * 100, 1) if total else 0
    if metrics['fundflow_coverage'] < THRESHOLDS['fundflow_coverage']:
        issues.append({'id': 'DQ-W3', 'severity': 'WARN',
                       'desc': f"资金流覆盖率{metrics['fundflow_coverage']}% < {THRESHOLDS['fundflow_coverage']}%"})

    return issues, metrics


def check_score_history():
    """检查 score_history.jsonl 记录完整性"""
    issues = []
    hist_path = os.path.join(DATA_DIR, 'score_history.jsonl')
    if not os.path.exists(hist_path):
        return [{'id': 'DQ-W4', 'severity': 'WARN', 'desc': 'score_history.jsonl 不存在'}], {}

    zero_score_dates = set()
    with open(hist_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                score = rec.get('TotalScore', rec.get('total_score', -1))
                if score == 0 or score == -1:
                    zero_score_dates.add(rec.get('date', 'unknown'))
            except Exception:
                pass

    if zero_score_dates:
        issues.append({'id': 'DQ-W4', 'severity': 'WARN',
                       'desc': f"score_history score=0的日期: {sorted(zero_score_dates)}"})

    return issues, {}


def check_gate_health():
    """检查门禁健康度"""
    issues = []
    if not os.path.exists(GATE_LOG):
        return [{'id': 'DQ-W5', 'severity': 'WARN', 'desc': 'gate_check.jsonl 不存在'}], {}

    recent = []
    with open(GATE_LOG) as f:
        for line in f:
            try:
                recent.append(json.loads(line))
            except Exception:
                pass

    last_5 = recent[-5:]
    if len(last_5) >= 3:
        fails = sum(1 for r in last_5 if r.get('overall_result') == 'FAIL')
        fail_rate = fails / len(last_5) * 100
        if fail_rate > THRESHOLDS['gate_fail_rate']:
            issues.append({'id': 'DQ-W5', 'severity': 'WARN',
                           'desc': f"近{len(last_5)}次门禁失败率{fail_rate:.0f}% > {THRESHOLDS['gate_fail_rate']}%"})

    return issues, {}


def check_api_health():
    """检查API连通性"""
    issues = []
    health_files = [
        ('tencent', os.path.join(DATA_DIR, '.tencent_health.json')),
        ('sina', os.path.join(DATA_DIR, '.sina_health.json')),
        ('eastmoney', os.path.join(DATA_DIR, '.eastmoney_health.json')),
    ]

    for name, path in health_files:
        h = load_json(path)
        if h and isinstance(h, dict):
            consecutive = h.get('consecutive_failures', 0)
            if consecutive >= THRESHOLDS['api_consecutive_fail']:
                issues.append({'id': 'DQ-F3', 'severity': 'FAIL',
                               'desc': f'{name} API连续不可用{consecutive}日'})

    return issues, {}


# === P1-3 五维新维度检查 ===

def check_freshness():
    """检查缓存新鲜度：区分fresh/stale/expired。"""
    issues = []
    metrics = {}
    data = load_json(os.path.join(DATA_DIR, 'data_full.json'))
    if not data:
        return [{'id': 'DQ-F4', 'severity': 'WARN', 'desc': '无法检查缓存新鲜度(data_full不可读)'}], metrics

    cache = data.get('_Meta', {}).get('cache_stats', {})
    stale_count = cache.get('stale_count', 0) + cache.get('expired_count', 0)
    total_cached = cache.get('hit', 0) + stale_count
    metrics['freshness_stale_count'] = stale_count
    metrics['freshness_total_cached'] = total_cached

    if total_cached > 0 and stale_count > 0:
        stale_pct = round(stale_count / total_cached * 100, 1)
        metrics['freshness_stale_pct'] = stale_pct
        if stale_pct > 20:
            issues.append({'id': 'DQ-W6', 'severity': 'WARN',
                          'desc': f'缓存过期率{stale_pct}% > 20%（{stale_count}/{total_cached}条过期）'})
    return issues, metrics


def check_anomaly():
    """检查异常值：Z-score和MAD检测。"""
    issues = []
    metrics = {}
    data = load_json(os.path.join(DATA_DIR, 'data_full.json'))
    if not data:
        return [], metrics

    stocks = data.get('Stocks', [])
    prices = [s.get('Price', 0) for s in stocks if s.get('Price') and s.get('Price') > 0]
    changes = [s.get('ChangePct', 0) for s in stocks if s.get('ChangePct') is not None]

    if len(prices) >= 10:
        mean_p = sum(prices) / len(prices)
        std_p = (sum((p - mean_p)**2 for p in prices) / len(prices)) ** 0.5
        if std_p > 0:
            anomalies = sum(1 for p in prices if abs(p - mean_p) / std_p > THRESHOLDS['anomaly_zscore'])
            metrics['anomaly_count'] = anomalies
            if anomalies > 0:
                issues.append({'id': 'DQ-W7', 'severity': 'WARN',
                              'desc': f'{anomalies}只股票价格异常(Z-score>{THRESHOLDS["anomaly_zscore"]})'})

    if len(changes) >= 10:
        mean_c = sum(changes) / len(changes)
        if mean_c != 0:
            devs = [abs(c - mean_c) for c in changes]
            mad = sorted(devs)[len(devs)//2]
            if mad > 0:
                anomalies = sum(1 for c in changes if abs(c - mean_c) / mad > THRESHOLDS['anomaly_mad'])
                metrics['anomaly_mad_count'] = anomalies
    return issues, metrics


def check_field_conflict():
    """检查字段冲突：同一字段不同来源的值是否一致。"""
    issues = []
    conflicts = []
    data = load_json(os.path.join(DATA_DIR, 'data_full.json'))
    if not data:
        return [], {}

    stocks = data.get('Stocks', [])
    for s in stocks[:10]:
        code = s.get('Code', '')
        pe_static = s.get('PE')
        pe_ttm = s.get('PETTM') or s.get('pe_ttm')
        if pe_static and pe_ttm and abs(pe_static - pe_ttm) / max(pe_static, 1) > 0.3:
            conflicts.append({'code': code, 'pe_static': pe_static, 'pe_ttm': pe_ttm})

    if conflicts:
        issues.append({'id': 'DQ-W8', 'severity': 'WARN',
                      'desc': f'{len(conflicts)}只股票PE(TTM)与静态PE偏差>30%，可能存在口径不一致'})
    return issues, {'field_conflicts': len(conflicts)}


def check_applicability():
    """检查数据适用性：区分缺失和不适用(required vs optional)。"""
    issues = []
    data = load_json(os.path.join(DATA_DIR, 'data_full.json'))
    if not data:
        return [], {"required_missing": 0, "optional_missing": 0, "not_applicable": 0}

    stocks = data.get('Stocks', [])
    missing = 0
    not_applicable = 0
    for s in stocks:
        for fld in ['PETTM', 'EPS', 'ROE']:
            val = s.get(fld) or s.get(fld.lower())
            if val is None or val == 0:
                if s.get('Industry') in ['银行', '非银金融']:
                    not_applicable += 1
                else:
                    missing += 1

    if missing > 0:
        issues.append({'id': 'DQ-W9', 'severity': 'WARN',
                      'desc': f'{missing}个字段缺失(非不适用)。required_missing=0, optional_missing={missing}(非生产阻塞)'})
    return issues, {'missing_fields': missing, 'not_applicable_fields': not_applicable}


def check_traceability():
    """检查数据可追溯性：每个值可追溯到原始API响应时间。"""
    issues = []
    metrics = {}
    data = load_json(os.path.join(DATA_DIR, 'data_full.json'))
    if not data:
        return [], {}

    meta = data.get('_Meta', {})
    checked_at = meta.get('checked_at', '')
    data_date = meta.get('data_date', '')
    metrics['traceability_checked_at'] = checked_at
    metrics['traceability_data_date'] = data_date

    if not checked_at and not data_date:
        issues.append({'id': 'DQ-W10', 'severity': 'WARN',
                      'desc': '数据缺少更新时间戳(_Meta.checked_at/data_date)，可追溯性不足'})
    return issues, metrics


# === P1-4 决策贡献率检查 ===

def check_decision_impact():
    """U-5: 检查报告中数据的决策影响力。

    区分"展示数据"和"实际影响结论的数据"。
    统计decision_impact_flag在各报告中的使用情况。
    """
    issues = []
    metrics = {"display_only": 0, "decision_impact": 0, "reports_checked": 0}

    report_dirs = [
        os.path.join(BASE, '..', '..', '每日荐股', '股票报告'),
        os.path.join(BASE, '..', '..', '重点股票', '股票报告'),
    ]

    for d in report_dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith('.json'):
                    continue
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        report = json.load(fh)
                except (json.JSONDecodeError, OSError):
                    continue

                impact = report.get('decision_impact', {})
                if not impact:
                    continue

                metrics['reports_checked'] += 1
                has_impact = False
                for key in ['scoring_fields', 'veto_fields', 'downgrade_fields',
                           'position_fields', 'stop_loss_fields']:
                    fields = impact.get(key, [])
                    if fields:
                        has_impact = True
                        metrics['decision_impact'] += len(fields)
                    else:
                        metrics['display_only'] += 1

                if not has_impact:
                    issues.append({'id': 'DQ-W11', 'severity': 'WARN',
                                  'desc': f'{os.path.basename(fpath)}: 无decision_impact标记，无法区分展示/决策数据'})

    if metrics['reports_checked'] > 0:
        total = metrics['display_only'] + metrics['decision_impact']
        if total > 0:
            metrics['decision_impact_rate'] = round(metrics['decision_impact'] / total * 100, 1)

    return issues, metrics


def check_escalation(current_issues):
    """检查连续3天同一WARN → 升级为FAIL"""
    escalated = []
    tracker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_quality_tracker.md')

    if not os.path.exists(tracker_path):
        return escalated

    # 提取WARN ID列表（当前）
    current_warn_ids = set(i['id'] for i in current_issues if i['severity'] == 'WARN')
    if not current_warn_ids:
        return escalated

    # 读取tracker最近3天的记录（按日期去重）
    daily_records = {}
    with open(tracker_path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith('| 202'):
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 7:
                continue
            date_str = parts[1][:10]  # YYYY-MM-DD
            if date_str not in daily_records:
                # 解析问题描述，提取WARN ID
                issues_text = parts[6] if len(parts) > 6 else ''
                warn_ids = set()
                for token in issues_text.replace('个问题', '').split():
                    if token.startswith('DQ-W'):
                        warn_ids.add(token.strip(','))
                daily_records[date_str] = {
                    'date': date_str,
                    'status': parts[2],
                    'warn_ids': warn_ids,
                    'issues_text': issues_text,
                }

    # 取最近3个不同日期
    recent_dates = sorted(daily_records.keys(), reverse=True)[:3]
    if len(recent_dates) < 3:
        return escalated

    # 检查当前WARN是否都出现在最近3天
    for warn_id in current_warn_ids:
        consecutive_days = 0
        for d in recent_dates:
            if warn_id in daily_records[d]['warn_ids']:
                consecutive_days += 1
            else:
                break  # 不连续，停止计数
        if consecutive_days >= 3:
            escalated.append({
                'id': f'{warn_id}-ESCALATED',
                'severity': 'FAIL',
                'desc': f'{warn_id}连续{consecutive_days}天未修复 → 自动升级为FAIL。请立即修复。',
                'original_id': warn_id,
            })

    return escalated


def update_tracker(report):
    """更新数据质量跟踪清单"""
    tracker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_quality_tracker.md')

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    metrics = report.get('metrics', {})
    issues = report.get('issues', [])
    overall = report.get('overall', 'UNKNOWN')

    status_emoji = {'PASS': '🟢', 'WARN': '🟡', 'FAIL': '🔴'}
    emoji = status_emoji.get(overall, '⚪')

    entry = f"\n| {now} | {emoji} {overall} | 缓存{metrics.get('cache_hit_rate','?')}% | 行情{metrics.get('quote_coverage','?')}% | 财务{metrics.get('financial_coverage','?')}% | 资金流{metrics.get('fundflow_coverage','?')}% | {len(issues)}个问题 |"

    if os.path.exists(tracker_path):
        with open(tracker_path) as f:
            content = f.read()
        # Insert after the table header
        if '|:-----|' in content:
            lines = content.split('\n')
            new_lines = []
            inserted = False
            for line in lines:
                new_lines.append(line)
                if '|:-----|' in line and not inserted:
                    # Find the separator line of the daily log table
                    if '检查时间' in '\n'.join(new_lines[-3:]):
                        new_lines.append(entry)
                        inserted = True
            if not inserted:
                new_lines.append(entry)
            content = '\n'.join(new_lines)
        else:
            content += entry
    else:
        content = f"""# 数据质量跟踪清单

> 负责人: 玉夜 | 自动更新: check_data_quality.py | 通报: 腰子/阿黑

## 每日检查记录

| 检查时间 | 状态 | 缓存命中率 | 行情覆盖率 | 财务覆盖率 | 资金流覆盖率 | 问题数 |
|:-----|:----:|:--------:|:--------:|:--------:|:--------:|:----:{entry}
"""

    with open(tracker_path, 'w') as f:
        f.write(content)


def main():
    import argparse as _ap
    _parser = _ap.ArgumentParser(description="数据质量闸门(DQ-Gate)")
    _parser.add_argument("--date", default="", help="YYYYMMDD 目标日期（当前仅用于标注）")
    _parser.add_argument("--json-output", default="", help="输出JSON路径")
    _parser.add_argument("--write-tracker", action="store_true", help="显式写入data_quality_tracker.md；默认只输出report")
    _args, _ = _parser.parse_known_args()

    all_issues = []
    all_metrics = {}

    # DQ-W9 区分 required vs optional 缺失
    scope_path = os.path.join(BASE, "..", "configs", "daily_production_scope.json")
    _required_fields = set()
    if os.path.exists(scope_path):
        with open(scope_path) as _f:
            _scope = json.load(_f)
        for _r in _scope.get("required_outputs", []):
            _required_fields.add(os.path.basename(_r["path"]))
    _DQ_W9_REQUIRED_FIELDS = _required_fields

    # 运行各项检查
    for check_fn, name in [(check_data_full, 'data_full'), (check_score_history, 'score_history'),
                            (check_gate_health, 'gate_health'), (check_api_health, 'api_health'),
                            (check_freshness, 'freshness'), (check_anomaly, 'anomaly'),
                            (check_field_conflict, 'field_conflict'), (check_applicability, 'applicability'),
                            (check_traceability, 'traceability'), (check_decision_impact, 'decision_impact')]:
        try:
            issues, *metrics = check_fn()
            all_issues.extend(issues)
            if metrics and metrics[0]:
                all_metrics.update(metrics[0])
        except Exception as e:
            all_issues.append({'id': 'DQ-ERR', 'severity': 'WARN', 'desc': f'{name}检查异常: {e}'})

    # 升级检查：连续3天同一WARN → FAIL
    escalated = check_escalation(all_issues)
    if escalated:
        all_issues.extend(escalated)
        # 从WARN列表中移除已升级的ID（避免重复）
        escalated_ids = set(e['original_id'] for e in escalated)
        all_issues = [i for i in all_issues if not (i['severity'] == 'WARN' and i['id'] in escalated_ids)]

    # 判定
    has_fail = any(i['severity'] == 'FAIL' for i in all_issues)
    has_warn = any(i['severity'] == 'WARN' for i in all_issues)
    overall = 'FAIL' if has_fail else ('WARN' if has_warn else 'PASS')

    _required_missing = 0
    _optional_missing = 0
    _missing_fields_count = int(all_metrics.get('missing_fields', 0) or 0)
    for _i in all_issues:
        if _i.get('id') == 'DQ-W9':
            _r = _i.get('desc', '')
            if 'required_missing=0' in _r:
                _optional_missing = _missing_fields_count
            else:
                _required_missing = _missing_fields_count if _missing_fields_count else 1
    _warn_policy = 'not_applied'
    _scope_path = os.path.join(BASE, '..', 'configs', 'daily_production_scope.json')
    if os.path.exists(_scope_path):
        with open(_scope_path) as _sf:
            _scope = json.load(_sf)
        if _scope.get('dq_warn_allowlist'):
            _warn_policy = 'applied'

    report = {
        'check_time': datetime.now().isoformat(),
        'overall': overall,
        'target_date': _args.date if _args.date else 'not_specified',
        'metrics': all_metrics,
        'issues': all_issues,
        'blocked': has_fail,
        'required_missing': _required_missing,
        'optional_missing': _optional_missing,
        'warn_policy_applied': _warn_policy,
    }

    # 输出报告
    report = classify_report(report, target_date=_args.date)
    report_path = os.path.join(DATA_DIR, 'data_quality_report.json')
    if _args.json_output:
        report_path = _args.json_output
    os.makedirs(os.path.dirname(report_path) if os.path.dirname(report_path) else ".", exist_ok=True)
    with open(report_path, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 默认只读：只有显式 --write-tracker 才更新跟踪清单，避免验证命令产生副作用
    if _args.write_tracker:
        update_tracker(report)

    # 输出到stdout
    print(f"[DQ-Gate] {overall} | {len(all_issues)} issues | blocked={has_fail}")
    for i in all_issues:
        print(f"  [{i['severity']}] {i['id']}: {i['desc']}")
    if _args.date:
        print(f"[DQ-Gate] target_date={_args.date}")

    return report


if __name__ == '__main__':
    main()
