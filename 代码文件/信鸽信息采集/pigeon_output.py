#!/usr/bin/env python3
"""信鸽结构化输出 + 缓存管理

Replaces pigeon_output.ps1. macOS compatible.
Code level: L0
"""
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def export_events(filtered_events, filter_stats, output_dir, db_path=None):
    """将过滤后的事件写入日期文件 + 追加到events_db.json

    Args:
        filtered_events: dict {code: {"events": [...], "stats": {...}}}
        filter_stats: dict {code: stats}
        output_dir: 输出目录(相对ROOT)
        db_path: events_db.json路径

    Returns:
        dict with date_file, db_file, count
    """
    out_dir = os.path.join(ROOT, output_dir)
    os.makedirs(out_dir, exist_ok=True)

    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M:%S")

    all_events = []
    total_raw = 0
    drops = {"L1": 0, "L2": 0, "L3": 0, "L4": 0}

    for code, result in filtered_events.items():
        events = result.get("events", [])
        all_events.extend(events)
        stats = result.get("stats", {})
        total_raw += stats.get("L1_in", 0)
        drops["L1"] += stats.get("L1_in", 0) - stats.get("L1_out", 0)
        drops["L2"] += stats.get("L2_in", 0) - stats.get("L2_out", 0)
        drops["L3"] += stats.get("L3_in", 0) - stats.get("L3_out", 0)
        drops["L4"] += stats.get("L4_in", 0) - stats.get("L4_out", 0)

    # Convert events to serializable dicts, normalize field names
    serializable = []
    for e in all_events:
        if hasattr(e, '__dict__'):
            d = vars(e).copy()
        elif isinstance(e, dict):
            d = e.copy()
        else:
            d = e
        # Normalize cninfo raw field names -> PigeonEvent field names
        if not d.get("code") and d.get("sec_code"):
            d["code"] = d["sec_code"]
        if not d.get("name") and d.get("sec_name"):
            d["name"] = d["sec_name"]
        serializable.append(d)

    output = {
        "fetch_date": today,
        "fetch_time": now,
        "total_raw": total_raw,
        "total_filtered": len(serializable),
        "filter_stats": {
            "L1_dropped": drops["L1"],
            "L2_dropped": drops["L2"],
            "L3_dropped": drops["L3"],
            "L4_dropped": drops["L4"],
        },
        "events": serializable,
    }

    # Write date file
    date_file = os.path.join(out_dir, f"{today}_events.json")
    with open(date_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[output] Date file written: {date_file} ({len(serializable)} events)")

    # Append to events_db.json
    if not db_path:
        db_path = os.path.join(ROOT, "重点股票", "消息面数据", "events_db.json")

    existing_db = []
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                existing_db = json.load(f)
            if not isinstance(existing_db, list):
                existing_db = []
        except (json.JSONDecodeError, OSError):
            print("[output] events_db.json parse failed, creating new")
            existing_db = []

    skipped_empty = 0
    for event in serializable:
        code = event.get("code") or event.get("sec_code") or ""
        name = event.get("name") or event.get("sec_name") or ""
        if not code:
            skipped_empty += 1
            continue
        db_entry = {
            "event_id": event.get("event_id", ""),
            "code": code,
            "name": name,
            "category": event.get("category", ""),
            "subtype": event.get("subtype", ""),
            "title": event.get("title", ""),
            "direction": event.get("direction", 0),
            "impact_score": event.get("impact_score", 0),
            "pdf_url": event.get("pdf_url"),
            "content": event.get("content", ""),
            "announcement_id": event.get("announcement_id"),
            "cninfo_url": event.get("cninfo_url"),
            "fetch_date": today,
            "evidence_level": event.get("evidence_level"),
            "evidence_upgrade": event.get("evidence_upgrade", False),
            "evidence_upgrade_type": event.get("evidence_upgrade_type"),
            "concept_track": event.get("concept_track"),
            "actual_return_T1": None, "actual_return_T3": None, "actual_return_T5": None,
            "market_return_T1": None, "market_return_T3": None, "market_return_T5": None,
            "excess_return_T1": None, "excess_return_T3": None, "excess_return_T5": None,
            "verified": False, "verified_date": None,
        }
        existing_db.append(db_entry)

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(existing_db, f, ensure_ascii=False, indent=2)
    msg = f"[output] events_db.json updated: {len(existing_db)} total records"
    if skipped_empty:
        msg += f" (skipped {skipped_empty} empty-code entries)"
    print(msg)

    return {"date_file": date_file, "db_file": db_path, "count": len(serializable)}


def update_cache(output_data, cache_dir):
    """更新缓存[C] — TTL=24h"""
    cache_path = os.path.join(ROOT, cache_dir)
    os.makedirs(cache_path, exist_ok=True)

    today = date.today().isoformat()
    now = datetime.now()
    cache_file = os.path.join(cache_path, f"{today}_cache.json")

    entry = {
        "cached_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "ttl_hours": 24,
        "expires_at": (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"),
        "data": output_data,
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2, default=str)
    print(f"[cache] Written: {cache_file}")

    # Clean expired (>7 days)
    cutoff = time.time() - 7 * 86400
    for f in os.listdir(cache_path):
        fp = os.path.join(cache_path, f)
        if f.endswith("_cache.json") and os.path.getmtime(fp) < cutoff:
            os.remove(fp)


def get_cache(cache_dir, target_date=None):
    """读取缓存[C] — 主源+备源不可用时兜底"""
    if not target_date:
        target_date = date.today().isoformat()
    cache_file = os.path.join(ROOT, cache_dir, f"{target_date}_cache.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        expires = datetime.strptime(cache["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() < expires:
            print(f"[cache] Hit: {cache_file} (expires {cache['expires_at']})")
            return cache["data"]
        else:
            print(f"[cache] Expired: {cache_file}")
    except Exception:
        print(f"[cache] Read failed: {cache_file}")
    return None
