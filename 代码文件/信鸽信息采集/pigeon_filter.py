#!/usr/bin/env python3
"""信鸽五层噪音过滤引擎

Replaces pigeon_filter.ps1. macOS compatible.
L1黑名单→L2腰子五问→L3山猫去重→L4青山标签+流金上限→L4c证据等级检测
Code level: L1
"""
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
CONFIG_PATH = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def title_similarity(title1, title2):
    """Jaccard相似度 — 共同词/总词数。阈值70%"""
    if not title1 or not title2:
        return 0.0
    words1 = set(re.findall(r'[\w一-鿿]{2,}', title1))
    words2 = set(re.findall(r'[\w一-鿿]{2,}', title2))
    if not words1 or not words2:
        return 0.0
    common = len(words1 & words2)
    union = len(words1 | words2)
    return round(common / union, 2) if union > 0 else 0.0


def get_event_tags(title, config):
    """三层标签分类 + impact_score计算"""
    cat_weight = config.get("impact_score_weights", {}).get("经营事件", 6)
    category, subtype = "经营事件", "其他"

    if re.search(r'业绩|预告|快报|年报|季报|中报|净利润|营收增长|EPS|ROE|扣非', title):
        category = "业绩"
        subtype = "业绩预告" if re.search(r'预告|预增|预减|预亏', title) else \
                  "业绩快报" if re.search(r'快报', title) else "正式财报"
        cat_weight = config.get("impact_score_weights", {}).get("业绩", 9)
    elif re.search(r'收购|并购|重组|合并|借壳|注入|出售.*资产|购买.*(股权|资产)|发行.*股份|注册批复|核准.*发行', title):
        category = "并购重组"
        subtype = "注册批复" if re.search(r'注册批复|核准|通过', title) else \
                  "重组预案" if re.search(r'预案|草案|筹划', title) else "并购进展"
        cat_weight = config.get("impact_score_weights", {}).get("并购重组", 10)
    elif re.search(r'增持|减持|回购|质押|解禁|股权激励|定向增发|控制权.*变更|要约', title):
        category = "股东行为"
        subtype = "增持" if re.search(r'增持', title) else \
                  "减持" if re.search(r'减持', title) else \
                  "回购" if re.search(r'回购', title) else \
                  "质押" if re.search(r'质押', title) else \
                  "解禁" if re.search(r'解禁', title) else "其他股东行为"
        cat_weight = config.get("impact_score_weights", {}).get("股东行为", 8)
    elif re.search(r'立案|调查|处罚|警示函|监管函|问询函|ST|\*ST|退市|暂停上市|责令|罚款|违法', title):
        category = "监管合规"
        subtype = "立案调查" if re.search(r'立案|调查', title) else \
                  "问询函" if re.search(r'问询函', title) else \
                  "处罚决定" if re.search(r'处罚|罚款|警示函', title) else \
                  "ST/退市风险" if re.search(r'ST|\*ST|退市|暂停上市', title) else "其他监管"
        cat_weight = config.get("impact_score_weights", {}).get("监管合规", 9)
    elif re.search(r'补贴|政策|关税|准入|标准|扶持|限制|淘汰|产能.*调控|环保.*限产|碳达峰|碳中和', title):
        category = "行业政策"
        subtype = "扶持政策" if re.search(r'补贴|扶持', title) else \
                  "限制政策" if re.search(r'限制|淘汰|调控', title) else "政策动态"
        cat_weight = config.get("impact_score_weights", {}).get("行业政策", 7)
    elif re.search(r'中标|合同|订单|投产|量产|定点|获批|新产品|新线|产能|供货|客户', title):
        category = "经营事件"
        subtype = "重大合同" if re.search(r'中标|合同|订单', title) else \
                  "产能投产" if re.search(r'投产|量产|产能|新线', title) else \
                  "产品/客户" if re.search(r'定点|获批|新产品', title) else "其他经营"
        cat_weight = config.get("impact_score_weights", {}).get("经营事件", 6)

    # Direction
    direction = 0
    if re.search(r'增持|回购|预增|增长|超预期|获批|中标|突破|利好|注册批复|通过|核准|上调|实施', title):
        direction = 1
    elif re.search(r'减持|预亏|预减|下降|不及预期|立案|处罚|问询|警示|退市|ST|\*ST|调查|失败|亏损|暴跌', title):
        direction = -1

    # Probability
    probability = 1.0
    if re.search(r'传闻|消息|据悉|或|或将|可能|拟|计划|筹划', title):
        probability = 0.5
    elif re.search(r'预告|预计|预测', title):
        probability = 0.7

    # Freshness
    freshness = config.get("freshness_weights", {}).get("today", 1.0)

    # Impact score
    impact_score = round(cat_weight * probability * freshness, 1)
    impact_score = min(impact_score, 10.0)

    # P0
    is_p0 = any(re.search(re.escape(kw), title) for kw in config.get("p0_keywords", []))

    # Keywords
    q1_q5 = config.get("q1_q5_rules", {})
    matched_keywords = [name for name, pattern in q1_q5.items() if re.search(pattern, title)]

    # Structured fields
    status = "announced"
    if re.search(r'完成|通过|批复|实施|投产|量产', title):
        status = "confirmed"
    elif re.search(r'筹划|拟|计划|预案', title):
        status = "planned"

    return {
        "category": category, "subtype": subtype, "direction": direction,
        "impact_score": impact_score, "probability": probability,
        "keywords": ",".join(matched_keywords), "is_p0": is_p0,
        "structured_fields": {"event_type": subtype, "status": status},
    }


def get_evidence_level(title, stock_code, stock_name, config):
    """按L1→L2→L3→L4优先级匹配关键词，返回证据等级+概念赛道"""
    result = {"level": "", "track_name": ""}
    rules = config.get("evidence_level_rules")
    if not rules:
        return result

    target_stocks = config.get("target_stocks", [])
    stock_config = next((s for s in target_stocks if s.get("code") == stock_code), None)

    matched_track = None
    if stock_config:
        for track in stock_config.get("concept_tracks", []):
            if re.search(track.get("keywords", ""), title):
                matched_track = track
                break

    # L1: 订单/定点/合同
    l1 = rules.get("L1_keywords", {})
    if l1.get("pattern") and re.search(l1["pattern"], title):
        if not l1.get("requires_company_name") or re.search(re.escape(stock_name), title):
            result["level"] = "L1"
            result["track_name"] = matched_track["name"] if matched_track else ""
            return result

    # L2: 公司业务方向
    l2 = rules.get("L2_keywords", {})
    if l2.get("pattern") and re.search(l2["pattern"], title):
        if not l2.get("requires_company_name") or re.search(re.escape(stock_name), title):
            result["level"] = "L2"
            result["track_name"] = matched_track["name"] if matched_track else ""
            return result

    # L3: 行业趋势/政策
    l3 = rules.get("L3_keywords", {})
    if l3.get("pattern") and re.search(l3["pattern"], title):
        result["level"] = "L3"
        result["track_name"] = matched_track["name"] if matched_track else ""
        return result

    # L4: 研报/分析
    l4 = rules.get("L4_default", {})
    if l4.get("pattern") and re.search(l4["pattern"], title):
        result["level"] = "L4"
        result["track_name"] = matched_track["name"] if matched_track else ""

    return result


def detect_evidence_upgrade(stock_code, concept_track, new_level, existing_events):
    """对比新事件 vs 历史最高证据等级，检测升级"""
    result = {"upgrade": False, "upgrade_type": ""}
    if not new_level or not concept_track:
        return result

    level_order = {"L4": 0, "L3": 1, "L2": 2, "L1": 3}
    history_max = "L4"

    for evt in (existing_events or []):
        evt_level = evt.get("evidence_level", "")
        evt_track = evt.get("concept_track", "")
        if evt_level and evt_track == concept_track:
            if level_order.get(evt_level, 0) > level_order.get(history_max, 0):
                history_max = evt_level

    new_order = level_order.get(new_level, 0)
    hist_order = level_order.get(history_max, 0)
    if new_order > hist_order:
        result["upgrade"] = True
        result["upgrade_type"] = f"{history_max}_to_{new_level}"

    return result


class PigeonEvent:
    """信鸽事件数据类"""
    def __init__(self, **kwargs):
        self.event_id = kwargs.get("event_id", "")
        self.code = kwargs.get("code", "")
        self.name = kwargs.get("name", "")
        self.category = kwargs.get("category", "")
        self.subtype = kwargs.get("subtype", "")
        self.title = kwargs.get("title", "")
        self.source = kwargs.get("source", "")
        self.source_type = kwargs.get("source_type", "primary")
        self.reliability = "verified" if kwargs.get("source_type") == "primary" else "single_source"
        self.quantifiable = kwargs.get("quantifiable", False)
        self.direction = kwargs.get("direction", 0)
        self.impact_score = kwargs.get("impact_score", 0.0)
        self.probability = kwargs.get("probability", 1.0)
        self.structured_fields = kwargs.get("structured_fields", {})
        self.raw_summary = (kwargs.get("title", "") or "")[:200]
        self.publish_time = kwargs.get("publish_time", "")
        self.pdf_url = kwargs.get("pdf_url")
        self.content = kwargs.get("content", "")
        self.announcement_id = kwargs.get("announcement_id")
        self.cninfo_url = kwargs.get("cninfo_url")
        self.keywords = kwargs.get("keywords", "")
        self.is_p0 = kwargs.get("is_p0", False)
        self.evidence_level = ""
        self.evidence_upgrade = False
        self.evidence_upgrade_type = ""
        self.concept_track = ""


def pigeon_filter(raw_messages, stock_code, stock_name, existing_events=None):
    """五层过滤漏斗 — 每只股票最多保留N条高价值信号

    L1: 黑名单关键词+域名 → 直接丢弃
    L2: 腰子五问法 Q1-Q5 → 至少YES一个
    L3: 山猫增量性检查 → 去重+无效研报丢弃
    L4: 青山三层标签分类+流金上限控制
    L4c: 证据等级自动检测+升级检测
    """
    if existing_events is None:
        existing_events = []

    config = load_config()
    stats = {"L1_in": len(raw_messages), "L1_out": 0, "L2_in": 0, "L2_out": 0,
             "L3_in": 0, "L3_out": 0, "L4_in": 0, "L4_out": 0}

    if not raw_messages:
        print(f"[filter] {stock_code}: 0 raw messages, skipping all layers")
        return {"events": [], "stats": stats}

    # === L1: 黑名单过滤 ===
    blacklist_kw = config.get("blacklist_keywords", [])
    blacklist_domains = config.get("blacklist_domains", [])
    after_l1 = []
    for msg in raw_messages:
        title = msg.get("title", "") if isinstance(msg, dict) else getattr(msg, "title", "")
        source = msg.get("source", "") if isinstance(msg, dict) else getattr(msg, "source", "")
        drop = any(kw in title for kw in blacklist_kw) or any(d in source for d in blacklist_domains)
        if not drop:
            after_l1.append(msg)
    stats["L1_out"] = len(after_l1)
    stats["L2_in"] = len(after_l1)

    # === L2: 腰子五问 ===
    q1_q5 = config.get("q1_q5_rules", {})
    after_l2 = []
    for msg in after_l1:
        title = msg.get("title", "") if isinstance(msg, dict) else getattr(msg, "title", "")
        if any(re.search(pattern, title) for pattern in q1_q5.values()):
            if isinstance(msg, dict):
                msg["quantifiable"] = True
            else:
                msg.quantifiable = True
            after_l2.append(msg)
    stats["L2_out"] = len(after_l2)
    stats["L3_in"] = len(after_l2)

    # === L3: 去重 + 研报过滤 ===
    dedup_threshold = config.get("dedup_similarity_threshold", 0.7)
    after_l3 = []
    for msg in after_l2:
        title = msg.get("title", "") if isinstance(msg, dict) else getattr(msg, "title", "")
        is_dup = False
        # L3a: 去重
        for existing in existing_events:
            ext = existing.get("title", "") if isinstance(existing, dict) else getattr(existing, "title", "")
            if title_similarity(title, ext) > dedup_threshold:
                is_dup = True
                break
        # L3b: 研报过滤
        if not is_dup and re.search(r'研报|研究报告|深度报告', title):
            is_first = re.search(r'首次覆盖|首覆|首次|新覆盖', title)
            has_rating = re.search(r'上调|下调|调高|调低|维持.*评级', title)
            has_est = re.search(r'盈利预测|EPS预测|业绩预测', title)
            if not is_first and not has_rating and not has_est:
                is_dup = True
        if not is_dup:
            after_l3.append(msg)
    stats["L3_out"] = len(after_l3)
    stats["L4_in"] = len(after_l3)

    # === L4: 标签 + 证据等级 ===
    tagged = []
    for msg in after_l3:
        title = msg.get("title", "") if isinstance(msg, dict) else getattr(msg, "title", "")
        tags = get_event_tags(title, config)

        event = PigeonEvent(
            code=stock_code, name=stock_name,
            category=tags["category"], subtype=tags["subtype"],
            title=title,
            source=msg.get("source", "") if isinstance(msg, dict) else getattr(msg, "source", ""),
            source_type=msg.get("source_type", "primary") if isinstance(msg, dict)
                else getattr(msg, "source_type", "primary"),
            quantifiable=msg.get("quantifiable", False) if isinstance(msg, dict)
                else getattr(msg, "quantifiable", False),
            direction=tags["direction"], impact_score=tags["impact_score"],
            probability=tags["probability"], structured_fields=tags["structured_fields"],
            publish_time=msg.get("publish_time", "") if isinstance(msg, dict)
                else getattr(msg, "publish_time", ""),
            pdf_url=msg.get("pdf_url") if isinstance(msg, dict) else getattr(msg, "pdf_url", None),
            content=msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", ""),
            announcement_id=msg.get("announcement_id") if isinstance(msg, dict)
                else getattr(msg, "announcement_id", None),
            cninfo_url=msg.get("cninfo_url") if isinstance(msg, dict) else getattr(msg, "cninfo_url", None),
            keywords=tags["keywords"], is_p0=tags["is_p0"],
        )
        tagged.append(event)

    # L4c: 证据等级
    for event in tagged:
        el = get_evidence_level(event.title, stock_code, stock_name, config)
        event.evidence_level = el["level"]
        event.concept_track = el["track_name"]
        if el["level"]:
            up = detect_evidence_upgrade(stock_code, el["track_name"], el["level"], existing_events)
            event.evidence_upgrade = up["upgrade"]
            event.evidence_upgrade_type = up["upgrade_type"]

    # L4a: 按impact_score排序，P0优先
    max_per_stock = config.get("max_events_per_stock", 5)
    p0_events = [e for e in tagged if e.is_p0]
    normal = sorted([e for e in tagged if not e.is_p0], key=lambda e: e.impact_score, reverse=True)

    final_events = list(p0_events)
    remaining = max_per_stock - len(p0_events)
    if remaining > 0:
        final_events += normal[:remaining]

    # L4b: event_id
    fetch_date = date.today().strftime("%Y%m%d")
    for i, event in enumerate(final_events):
        event.event_id = f"PIGEON_{fetch_date}_{stock_code}_{i+1:03d}"

    stats["L4_out"] = len(final_events)

    print(f"[filter] {stock_code}: L1 {stats['L1_in']}->{stats['L1_out']} | "
          f"L2 {stats['L2_in']}->{stats['L2_out']} | "
          f"L3 {stats['L3_in']}->{stats['L3_out']} | "
          f"L4 {stats['L4_in']}->{stats['L4_out']}")

    return {"events": final_events, "stats": stats}
