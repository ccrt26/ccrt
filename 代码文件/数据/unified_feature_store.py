#!/usr/bin/env python3
"""unified_feature_store.py — 统一特征层读写接口。

提供从统一特征表中查询、写入、聚合的能力。
Phase 1: 基于data_full.json + data_scored.json + score_history.jsonl构建。

Code level: L1
"""
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
FEATURE_FILE = os.path.join(DATA_DIR, "unified_features.jsonl")


def build_from_sources(target_date=None):
    """从现有数据源构建统一特征表。Phase 1: data_full + data_scored + score_history。

    Args:
        target_date: 指定日期 YYYY-MM-DD，默认最新。

    Returns:
        list[dict]: 特征记录列表
    """
    features = []

    data_full = _load_json(os.path.join(DATA_DIR, "data_full.json"))
    data_scored = _load_json(os.path.join(DATA_DIR, "data_scored.json"))
    score_history = _load_score_history()

    if target_date:
        score_history = [r for r in score_history if r.get("date", "").startswith(target_date)]

    scored_by_code = {}
    if isinstance(data_scored, list):
        for s in data_scored:
            code = s.get("Code") or s.get("code")
            if code:
                scored_by_code[code] = s

    score_by_code_date = {}
    for r in score_history:
        key = (r.get("code", ""), r.get("date", "")[:10])
        score_by_code_date[key] = r

    stocks = data_full.get("Stocks", []) if data_full else []
    now = datetime.now().isoformat()

    for stock in stocks:
        code = stock.get("Code", "")
        name = stock.get("Name", "")
        if not code:
            continue

        date_str = target_date or datetime.now().strftime("%Y-%m-%d")

        def _add(field_name, value, source, quality="fresh"):
            if value is not None:
                features.append({
                    "date": date_str, "code": code, "name": name,
                    "field_name": field_name, "field_value": value,
                    "data_source": source, "updated_at": now,
                    "quality_flag": quality, "schema_version": "v1.0",
                })

        # OHLCV from data_full
        _add("price", stock.get("Price"), "[1]")
        _add("open", stock.get("Open"), "[1]")
        _add("high", stock.get("High"), "[1]")
        _add("low", stock.get("Low"), "[1]")
        _add("change_pct", stock.get("ChangePct"), "[1]")
        _add("volume", stock.get("Volume"), "[1]")
        _add("turnover_rate", stock.get("TurnoverRate"), "[1]")
        _add("total_market_value", stock.get("MarketValue"), "[1]")

        # PE(TTM) computation
        pe_source = stock.get("PESource") or stock.get("pe_source", "")
        pe_ttm_val = stock.get("PETTM") or stock.get("pe_ttm")
        _add("pe_ttm", pe_ttm_val, pe_source if pe_source else "[5]")

        scored = scored_by_code.get(code, {})
        if scored:
            for fld in ["S_Base","S_Fund","S_Tech","S_Money","S_News","S_Risk",
                        "S_SectorTrend","TotalScore"]:
                _add(fld, scored.get(fld), "[5]")
            for fld in ["S1_MA","S2_Converge","S3_Volume","S4_Support",
                        "S5_RSI","S6_MACD","S7_Breakout","S8_Momentum"]:
                _add(fld, scored.get(fld), "[5]")
            _add("veto_status", scored.get("veto_status") or scored.get("VetoStatus"), "[5]")
            _add("phase", scored.get("phase") or scored.get("Phase"), "[5]")
            _add("theme_path", scored.get("theme_path") or scored.get("ThemePath"), "[5]")

        score_key = (code, date_str)
        hist = score_by_code_date.get(score_key, {})
        if hist:
            for fld in ["ret_t1","ret_t3","ret_t5",
                        "ret_t1_vs_hs300","ret_t3_vs_hs300","ret_t5_vs_hs300",
                        "ret_t1_vs_sector","car5"]:
                if hist.get(fld) is not None:
                    _add(fld, hist[fld], "[5]")

    return features


def query(code, date_str, field_names=None):
    """查询统一特征表。

    Args:
        code: 股票代码
        date_str: 日期 YYYY-MM-DD
        field_names: 字段名列表，None=全部

    Returns:
        dict: {field_name: field_value}
    """
    features = load_features()
    result = {}
    for f in features:
        if f["code"] == code and f["date"] == date_str:
            if field_names is None or f["field_name"] in field_names:
                result[f["field_name"]] = f["field_value"]
    return result


def query_dataframe(codes, date_str, field_names):
    """批量查询，返回适合pandas的list[dict]。

    Args:
        codes: 股票代码列表
        date_str: 日期
        field_names: 需要的字段名列表

    Returns:
        list[dict]: 每个元素为 {code, name, field1, field2, ...}
    """
    features = load_features()
    by_code = {}
    for f in features:
        if f["date"] == date_str and f["code"] in set(codes):
            if f["field_name"] in field_names:
                if f["code"] not in by_code:
                    by_code[f["code"]] = {"code": f["code"], "name": f.get("name", "")}
                by_code[f["code"]][f["field_name"]] = f["field_value"]
    return list(by_code.values())


def save_features(features):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FEATURE_FILE, "w", encoding="utf-8") as f:
        for feat in features:
            f.write(json.dumps(feat, ensure_ascii=False) + "\n")


def load_features():
    if not os.path.exists(FEATURE_FILE):
        return []
    records = []
    with open(FEATURE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_score_history():
    fpath = os.path.join(DATA_DIR, "score_history.jsonl")
    if not os.path.exists(fpath):
        return []
    records = []
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records
