#!/usr/bin/env python3
"""fault_events.py — 数据调用故障事件记录与查询

共享工具模块。数据获取函数在1+2降级发生时调用 write_fault_event() 写入故障记录。
orchestrator/玉夜/旧影通过 read_fault_events() 读取并分析趋势。

用法:
    from fault_events import write_fault_event, read_fault_events, summarize_faults

    write_fault_event("P3-01", "新浪", "新浪行情API连接失败，降级到缓存")
    events = read_fault_events(resolved_only=False)
    summary = summarize_faults()

Schema 复用玉夜知识库05 §11.1，字段: EventID, Timestamp, Level, Source, Description, ConsecutiveCount, Resolved

Code level: L0
Design: 审计报告/架构设计/design_data_fault_closure_v1.0.md
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
FAULT_FILE = os.path.join(ROOT, "代码文件", "数据", "fault_events.json")
TZ_SHANGHAI = timezone(timedelta(hours=8))

# 同一源+同一EventID在一小时内视为同一次故障，仅更新计数
DEDUP_WINDOW_MINUTES = 60


def _load():
    if not os.path.exists(FAULT_FILE):
        return {"events": []}
    try:
        with open(FAULT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "events" not in data:
                data["events"] = []
            return data
    except (json.JSONDecodeError, OSError):
        return {"events": []}


def _save(data):
    os.makedirs(os.path.dirname(FAULT_FILE), exist_ok=True)
    try:
        with open(FAULT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAULT_SAVE_FAIL] {e}", file=sys.stderr)


def write_fault_event(event_id, source, description):
    """写入一条故障事件。降级发生时调用。写失败不影响调用方。

    Args:
        event_id: P0-P5级别+编号，如 "P3-01"
        source: 数据源名称，如 "新浪" "腾讯" "东财"
        description: 人类可读描述

    Returns:
        True if written, False if failed (caller should never branch on this)
    """
    try:
        data = _load()
        now = datetime.now(TZ_SHANGHAI)

        # Dedup: same event_id + same source within DEDUP_WINDOW_MINUTES
        for evt in data["events"]:
            if evt.get("EventID") == event_id and evt.get("Source") == source:
                try:
                    last_ts = datetime.fromisoformat(evt["Timestamp"])
                    delta = (now - last_ts).total_seconds() / 60
                    if delta < DEDUP_WINDOW_MINUTES:
                        evt["ConsecutiveCount"] = evt.get("ConsecutiveCount", 1) + 1
                        evt["Timestamp"] = now.isoformat()
                        _save(data)
                        return True
                except (ValueError, KeyError):
                    pass

        # New event
        event = {
            "EventID": event_id,
            "Timestamp": now.isoformat(),
            "Level": event_id.split("-")[0] if "-" in event_id else event_id,
            "Source": source,
            "Description": description,
            "ConsecutiveCount": 1,
            "Resolved": False,
        }
        data["events"].append(event)
        _save(data)
        return True
    except Exception as e:
        print(f"[FAULT_RECORD_FAIL] {event_id} {source}: {e}", file=sys.stderr)
        return False


def read_fault_events(since_hours=None, resolved_only=False, min_level=None):
    """读取故障事件，支持过滤。

    Args:
        since_hours: 仅返回最近N小时的事件
        resolved_only: 仅返回已解决的事件
        min_level: 最低等级过滤，如 "P2" 返回 P0-P2

    Returns:
        list of event dicts, sorted by Timestamp desc
    """
    data = _load()
    events = data.get("events", [])
    now = datetime.now(TZ_SHANGHAI)

    level_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}

    filtered = []
    for evt in events:
        if resolved_only and not evt.get("Resolved", False):
            continue
        if since_hours is not None:
            try:
                ts = datetime.fromisoformat(evt["Timestamp"])
                if (now - ts).total_seconds() / 3600 > since_hours:
                    continue
            except (ValueError, KeyError):
                continue
        if min_level is not None:
            evt_level = evt.get("Level", "P5")
            if level_order.get(evt_level, 99) > level_order.get(min_level, 99):
                continue
        filtered.append(evt)

    filtered.sort(key=lambda e: e.get("Timestamp", ""), reverse=True)
    return filtered


def summarize_faults():
    """返回故障摘要：按源+等级聚合计数，检查升级阈值。

    Returns:
        dict with keys: total, by_source, by_level, alerts (需升级的事件)
    """
    events = read_fault_events(since_hours=168)  # Last 7 days
    summary = {
        "total": len(events),
        "by_source": {},
        "by_level": {},
        "alerts": [],
    }

    for evt in events:
        src = evt.get("Source", "unknown")
        lvl = evt.get("Level", "P5")
        summary["by_source"][src] = summary["by_source"].get(src, 0) + 1
        summary["by_level"][lvl] = summary["by_level"].get(lvl, 0) + 1

        # Upgrade check: P3连续3次 → alert
        if lvl == "P3" and evt.get("ConsecutiveCount", 0) >= 3:
            summary["alerts"].append({
                "event_id": evt["EventID"],
                "source": src,
                "count": evt["ConsecutiveCount"],
                "reason": f"同一P3事件连续{evt['ConsecutiveCount']}次，建议升级为P2",
                "last_seen": evt["Timestamp"],
            })

    return summary


def mark_resolved(event_id, source):
    """标记某类故障为已解决。"""
    data = _load()
    resolved_count = 0
    for evt in data["events"]:
        if evt.get("EventID") == event_id and evt.get("Source") == source:
            if not evt.get("Resolved", False):
                evt["Resolved"] = True
                evt["ResolvedAt"] = datetime.now(TZ_SHANGHAI).isoformat()
                resolved_count += 1
    if resolved_count > 0:
        _save(data)
    return resolved_count
