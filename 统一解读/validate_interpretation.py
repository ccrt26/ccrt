#!/usr/bin/env python3
"""
统一解读闸门验证 — schema校验 + U-9 事实审计 + U-10 动作审计 + 模板污染
用法: python3 validate_interpretation.py <解释对象JSON> [--json]
退出码: 0=PASS, 1=WARN, 2=BLOCK
"""

import json, re, sys, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "interpretation_schema.json")

POLLUTION = {
    "BLOCK": [
        ("大概率上涨", "因果关系不成立"), ("确定性机会", "不存在确定性"),
        ("后市看涨", "无时间窗口"), ("逢低布局", "未定义'低'的标准"),
        ("长期看好", "未定义'长期'"), ("强烈推荐", "无量化标准"),
        ("毋庸置疑", "绝对性表述"), ("必然", "绝对性表述"),
        ("肯定", "绝对性表述"), ("一定", "绝对性表述"),
    ],
    "WARN": [
        ("建议关注", "请替换为具体触发条件"), ("值得关注", "请替换为观察指标"),
        ("可适当", "请量化范围"), ("相对乐观", "请量化程度"),
        ("偏谨慎", "请量化程度"), ("存在机会", "请指明具体机会"),
        ("风险可控", "请列出具体风险"), ("有望", "请替换为概率估计"),
        ("或将", "请替换为条件判断"), ("大概率", "请给出概率区间"),
    ]
}

# D07 v1.2 过度表达触发词
SOCIAL_SECURITY_OVERUSE = [
    "社保买了所以买", "养老金增持所以买入", "退出前十大等于清仓",
    "社保减持所以卖出", "长期机构资金作为交易指令", "直接生成买卖信号",
    "养老金增持=买入", "社保基金=交易信号"
]

DATA_FACT_BLOCKED = ["建议","看好","推荐","买入","卖出","增持","减持","值得","机会",
                     "风险小","安全边际","估值偏低","估值偏高","超跌","超买","底部","顶部","见底","见顶"]
BOILERPLATE = ["市场风险","政策风险","系统性风险","不确定性","大盘波动"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 内置 Schema 校验（零外部依赖）
# ============================================================
class SchemaValidator:
    def __init__(self, schema_path):
        self.schema = load_json(schema_path)
        self.errors = []
        self.warnings = []

    def validate(self, obj, path=""):
        self.errors.clear()
        self.warnings.clear()
        self._validate_object(obj, self.schema, path)
        return self.errors, self.warnings

    def _add_err(self, msg):
        self.errors.append(msg)

    def _add_warn(self, msg):
        self.warnings.append(msg)

    def _validate_object(self, obj, schema, path):
        if not isinstance(obj, dict):
            self._add_err(f"{path}: 期望object，收到{type(obj).__name__}")
            return

        # required 字段
        for field in schema.get("required", []):
            if field not in obj:
                self._add_err(f"缺少必填字段: {path}.{field}" if path else f"缺少必填字段: {field}")

        # properties
        for field, prop_schema in schema.get("properties", {}).items():
            if field not in obj or obj[field] is None:
                continue
            val = obj[field]
            fp = f"{path}.{field}" if path else field

            # type check
            expected_type = prop_schema.get("type")
            if expected_type:
                if expected_type == "string" and not isinstance(val, str):
                    self._add_err(f"{fp}: 期望string，收到{type(val).__name__}")
                    continue
                if expected_type == "array" and not isinstance(val, list):
                    self._add_err(f"{fp}: 期望array，收到{type(val).__name__}")
                    continue
                if expected_type == "object" and not isinstance(val, dict):
                    self._add_err(f"{fp}: 期望object，收到{type(val).__name__}")
                    continue

            # enum
            if "enum" in prop_schema and val not in prop_schema["enum"]:
                self._add_err(f"{fp}: '{val}' 不在允许值中: {prop_schema['enum']}")

            # pattern
            if "pattern" in prop_schema and isinstance(val, str):
                if not re.match(prop_schema["pattern"], val):
                    self._add_err(f"{fp}: '{val}' 不匹配模式 {prop_schema['pattern']}")

            # minLength
            if "minLength" in prop_schema and isinstance(val, str):
                if len(val) < prop_schema["minLength"]:
                    self._add_err(f"{fp}: 长度{len(val)} < 最小{prop_schema['minLength']}")

            # minItems
            if "minItems" in prop_schema and isinstance(val, list):
                if len(val) < prop_schema["minItems"]:
                    self._add_err(f"{fp}: 元素数{len(val)} < 最小{prop_schema['minItems']}")

            # nested object
            if prop_schema.get("type") == "object" and "properties" in prop_schema:
                self._validate_object(val, prop_schema, fp)

            # array items
            if prop_schema.get("type") == "array" and "items" in prop_schema:
                item_schema = prop_schema["items"]
                if isinstance(item_schema, dict) and item_schema.get("type") == "object":
                    for i, item in enumerate(val):
                        self._validate_object(item, item_schema, f"{fp}[{i}]")

        # allOf
        for clause in schema.get("allOf", []):
            if "if" in clause and "then" in clause:
                if self._check_condition(obj, clause["if"]):
                    then_req = clause["then"].get("required", [])
                    for field in then_req:
                        if not obj.get(field):
                            fp = f"{path}.{field}" if path else field
                            self._add_err(f"{fp}: 条件触发后必填（action_bias=BUY/SELL时）")

    def _check_condition(self, obj, if_clause):
        props = if_clause.get("properties", {})
        for field, cond in props.items():
            val = obj.get(field)
            if "enum" in cond:
                if val not in cond["enum"]:
                    return False
            if "const" in cond:
                if val != cond["const"]:
                    return False
        return True


# ============================================================
# U-9 + U-10 + 污染
# ============================================================
def run_u9(obj):
    findings = []
    status = "PASS"

    # 事实观点分离（递归扫描，跳过结构化枚举字段）
    def _collect_text(value, path=""):
        skip_paths = {
            "data_fact.values.change_type",
            "data_fact.values.change_types",
            "data_fact.values.institutional_change_type",
            "data_fact.values.long_term_institutional_change_type",
            "data_fact.values.holding_rank",
            "data_fact.values.share_count",
            "data_fact.values.share_ratio",
            "data_fact.values.consecutive_periods",
            "data_fact.values.pension_chain",
        }
        if path in skip_paths:
            return []
        if isinstance(value, dict):
            out = []
            for k, v in value.items():
                out.extend(_collect_text(v, f"{path}.{k}" if path else k))
            return out
        if isinstance(value, list):
            out = []
            for item in value:
                out.extend(_collect_text(item, path))
            return out
        if isinstance(value, str):
            return [value]
        return []
    data_text = " ".join(_collect_text(obj.get("data_fact", {}), "data_fact"))
    hits = [t for t in DATA_FACT_BLOCKED if t in data_text]
    if hits:
        findings.append({"check": "事实观点分离", "result": "WARN",
                         "detail": f"data_fact 含结论性词汇: {', '.join(hits)}"})
        status = "WARN"

    # 反证存在
    counter = obj.get("counter_evidence", [])
    if not counter:
        findings.append({"check": "反证存在", "result": "BLOCK", "detail": "counter_evidence 为空"})
        status = "BLOCK"

    # 反证质量
    if len(counter) == 1:
        ev = counter[0].get("evidence", "")
        if any(bp in ev for bp in BOILERPLATE):
            findings.append({"check": "反证质量", "result": "WARN", "detail": f"反证仅1条且为套话: {ev}"})
            if status == "PASS": status = "WARN"

    # 失效条件
    inv = obj.get("invalidation_condition", "")
    if not inv or len(inv) < 15:
        findings.append({"check": "失效条件", "result": "BLOCK", "detail": "invalidation_condition 为空或<15字"})
        status = "BLOCK"

    # 单一信号强结论
    if len(obj.get("supporting_evidence", [])) == 1 and obj.get("action_bias") in ("BUY", "SELL"):
        findings.append({"check": "单一信号强结论", "result": "WARN", "detail": "仅1条支持证据但给出强动作"})
        if status == "PASS": status = "WARN"

    # 相关性≠因果
    text = obj.get("interpretation_hypothesis","") + " " + obj.get("investment_implication","")
    if re.search(r"因为.*所以.*(涨|跌)|由于.*导致.*(上涨|下跌)|.*推动.*(上涨|下跌|走高|走低)", text):
        findings.append({"check": "相关性≠因果", "result": "WARN", "detail": "可能存在因果断言"})
        if status == "PASS": status = "WARN"

    return status, findings


def run_u10(obj):
    findings = []
    status = "PASS"
    ab = obj.get("action_bias", "NEUTRAL")

    # 强动作必须有触发条件
    if ab in ("BUY", "SELL") and not obj.get("trigger_condition"):
        findings.append({"check": "触发条件", "result": "BLOCK", "detail": f"action_bias={ab} 但无 trigger_condition"})
        status = "BLOCK"

    # LOW不能强动作
    if obj.get("confidence") == "LOW" and ab in ("BUY", "SELL"):
        findings.append({"check": "置信度与动作匹配", "result": "BLOCK", "detail": f"confidence=LOW 但 action_bias={ab}"})
        status = "BLOCK"

    # 动作三要素
    if ab in ("BUY", "SELL"):
        missing = [f for f in ["price_range","position_limit","time_window"] if not obj.get(f)]
        if missing:
            findings.append({"check": "动作三要素", "result": "BLOCK", "detail": f"强动作缺少: {', '.join(missing)}"})
            status = "BLOCK"

    # 模板污染
    combined = json.dumps(obj, ensure_ascii=False)
    blk_hits = [(p, r) for p, r in POLLUTION["BLOCK"] if p in combined]
    wrn_hits = [(p, r) for p, r in POLLUTION["WARN"] if p in combined]
    if blk_hits:
        findings.append({"check": "模板污染-BLOCK", "result": "BLOCK",
                         "detail": f"禁用表达: {[p for p,_ in blk_hits]}"})
        status = "BLOCK"
    if wrn_hits:
        findings.append({"check": "模板污染-WARN", "result": "WARN",
                         "detail": f"建议替换: {[p for p,_ in wrn_hits]}"})
        if status == "PASS": status = "WARN"
    if len(wrn_hits) >= 3 and status == "PASS":
        status = "WARN"

    # 动作可执行性
    if ab in ("BUY","SELL","WATCH") and not obj.get("trigger_condition") and not obj.get("time_window"):
        findings.append({"check": "动作可执行性", "result": "WARN", "detail": "缺触发条件和时间窗口"})
        if status == "PASS": status = "WARN"

    return status, findings


def run_extra_checks(obj):
    """P0-1 + P0-B: 强动作知识引用 + L5禁强动作"""
    findings = []
    ab = obj.get("action_bias", "")
    if ab in ("BUY", "SELL"):
        # P0-1: 需 knowledge_refs 或 signal_refs
        has_krefs = bool(obj.get("knowledge_refs"))
        has_srefs = bool(obj.get("signal_refs"))
        if not has_krefs and not has_srefs:
            findings.append({"check": "强动作知识引用", "result": "BLOCK",
                             "detail": "BUY/SELL 需 knowledge_refs 或 signal_refs"})

        # P0-B: L5禁强动作 — supporting_evidence 至少1条为 L1/L2/L3
        evidence = obj.get("supporting_evidence", [])
        high_confidence_levels = {"L1", "L2", "L3"}
        has_high = any(e.get("source_level", "L5") in high_confidence_levels for e in evidence)
        all_l5 = all(e.get("source_level", "L5") in ("L5", "L5-seed") for e in evidence)
        if all_l5 and evidence:
            findings.append({"check": "L5禁强动作", "result": "BLOCK",
                             "detail": "BUY/SELL 的全部 supporting_evidence 为 L5/L5-seed，至少需1条 L1/L2/L3"})

        # P0-B: L5-seed 信号不得用于动作升级
        sig_refs = obj.get("signal_refs", [])
        if sig_refs and ab in ("BUY", "SELL"):
            # 检查是否有 L1-L4 主证据支撑（非 L5-seed）
            has_main_evidence = any(
                e.get("source_level", "L5") not in ("L5", "L5-seed")
                for e in evidence
            )
            if not has_main_evidence:
                findings.append({"check": "L5-seed动作升级", "result": "WARN",
                                 "detail": "signal_refs 中如有 L5-seed 信号，需有 L1-L4 主证据支撑方可升级。当前无 L1-L4 主证据"})
            # 若有 L1-L4 主证据，不触发 WARN
    # P0-G: knowledge_refs 硬校验
    krefs = obj.get("knowledge_refs", [])
    registry_ids = _load_registry_ids()

    if not krefs:
        findings.append({"check": "知识引用检查", "result": "BLOCK",
                         "detail": "knowledge_refs 为空，必须引用 knowledge_registry.json 中的知识ID"})
    else:
        unregistered = [k for k in krefs if k not in registry_ids]
        if unregistered:
            findings.append({"check": "知识引用检查", "result": "BLOCK",
                             "detail": f"knowledge_refs 未注册: {unregistered}"})

        # 强动作时检查 knowledge_refs 来源等级
        if ab in ("BUY", "SELL"):
            k_levels = []
            for k in krefs:
                entry = _find_registry_entry(k)
                if entry:
                    k_levels.append(entry.get("source_level", "L5"))
            if k_levels and all(sl in ("L4", "L5", "L5-seed") for sl in k_levels):
                findings.append({"check": "知识引用检查", "result": "BLOCK",
                                 "detail": f"BUY/SELL 的 knowledge_refs 全部为 L4/L5/L5-seed({k_levels})，至少需1条L1/L2/L3"})
            if k_levels and all(sl in ("L5", "L5-seed") for sl in k_levels):
                findings.append({"check": "知识引用检查", "result": "BLOCK",
                                 "detail": "BUY/SELL 的 knowledge_refs 全部为 L5/L5-seed，禁止强动作"})

    # rule_refs 检查
    rrefs = obj.get("rule_refs", [])
    if not rrefs:
        findings.append({"check": "规则引用检查", "result": "WARN",
                         "detail": "rule_refs 为空"})

    # signal_refs 检查
    srefs = obj.get("signal_refs", [])
    if srefs:
        sig_ids = _load_signal_ids()
        unregistered_sig = [s for s in srefs if s not in sig_ids]
        if unregistered_sig:
            findings.append({"check": "信号引用检查", "result": "WARN",
                             "detail": f"signal_refs 未在信号胜率库注册: {unregistered_sig}"})

    return findings


def run_d07_v12_checks(obj):
    """D07 v1.2 增强校验：多假设、证据缺口、长期机构资金、结论强度"""
    findings = []
    fw = obj.get("framework_version", "")
    if fw != "D07_v1.2":
        return findings  # 非 v1.2 框架不触发

    # ============================================================
    # 1. 多假设检查
    # ============================================================
    hypos = obj.get("hypotheses", [])
    if len(hypos) < 2:
        findings.append({"check": "D07_v1.2-多假设", "result": "WARN",
                         "detail": f"framework_version=D07_v1.2 但 hypotheses 仅 {len(hypos)} 条，至少需 2 条"})
    for h in hypos:
        for req in ["hypothesis_id", "statement", "status", "conclusion_strength"]:
            if not h.get(req):
                findings.append({"check": "D07_v1.2-假设结构", "result": "WARN",
                                 "detail": f"hypothesis {h.get('hypothesis_id','?')} 缺少 {req}"})
        if h.get("status") == "active" and not h.get("counter_evidence_refs") and not h.get("missing_data"):
            findings.append({"check": "D07_v1.2-反证检查", "result": "WARN",
                             "detail": f"hypothesis {h.get('hypothesis_id','?')} active 但无 counter_evidence_refs 或 missing_data"})

    # 仅一条假设 + 强动作
    ab = obj.get("action_bias", "")
    if len(hypos) <= 1 and ab in ("BUY", "SELL"):
        findings.append({"check": "D07_v1.2-单一假设强动作", "result": "WARN",
                         "detail": "仅 1 条 hypothesis 但 action_bias 为 BUY/SELL"})

    # ============================================================
    # 2. 证据缺口检查
    # ============================================================
    lie = obj.get("long_term_institutional_evidence", {})
    gaps = obj.get("evidence_gap_requests", [])
    p1_status = lie.get("p1_verification_status", "") if isinstance(lie, dict) else ""

    if p1_status == "warn_pending":
        if not gaps:
            findings.append({"check": "D07_v1.2-证据缺口", "result": "WARN",
                             "detail": "long_term_institutional_evidence.p1_verification_status=warn_pending 但 evidence_gap_requests 为空"})
        else:
            open_gaps = [g for g in gaps if g.get("status") == "open"]
            if open_gaps:
                for g in open_gaps:
                    if not g.get("requested_fields"):
                        findings.append({"check": "D07_v1.2-缺口字段", "result": "WARN",
                                         "detail": f"gap {g.get('gap_id','?')} open 但缺少 requested_fields"})
                    if not g.get("impact"):
                        findings.append({"check": "D07_v1.2-缺口影响", "result": "WARN",
                                         "detail": f"gap {g.get('gap_id','?')} open 但缺少 impact"})
                # open gap → conclusion_strength 不得为"可定性"
                cs = obj.get("conclusion_strength", "")
                if cs == "可定性":
                    findings.append({"check": "D07_v1.2-结论强度与缺口", "result": "BLOCK",
                                     "detail": f"evidence_gap_requests 有 open gap 但 conclusion_strength='可定性'"})
                # open gap 存在 → 显式报告 P1 待补证 WARN（正面的合规确认）
                findings.append({"check": "D07_v1.2-P1原始披露待补证", "result": "WARN",
                                 "detail": "P1原始披露单篇URL/PDF未闭合，已进入evidence_gap_requests；结论强度必须限制为风险假设或数据不足，不得声明P1 PASS。"})

    # ============================================================
    # 3. 长期机构资金检查
    # ============================================================
    if isinstance(lie, dict) and lie.get("status") == "present" and lie.get("records"):
        records = lie.get("records", [])
        for i, rec in enumerate(records):
            rid = rec.get("report_period", f"records[{i}]")
            for req in ["report_period", "shareholder_name_raw", "institution_type", "source_refs", "limitation_note"]:
                if not rec.get(req):
                    findings.append({"check": "D07_v1.2-机构资金记录", "result": "WARN",
                                     "detail": f"{rid}: 缺少必填字段 {req}"})
            # limitation_note 必须包含指定关键词
            ln = rec.get("limitation_note", "")
            required_kw = ["滞后", "退出", "不得作为买卖信号"]
            missing_kw = [kw for kw in required_kw if kw not in ln]
            if missing_kw or ("清仓" not in ln and "不等于" not in ln):
                findings.append({"check": "D07_v1.2-限制说明", "result": "WARN",
                                 "detail": f"{rid}: limitation_note 缺少必要关键词。需含：滞后、退出、不等于清仓/不等于xxx、不得作为买卖信号"})

            # source_refs 只含 secondary_organization → p1 不能是 verified
            srefs = rec.get("source_refs", [])
            if srefs and all(s.get("source_level") == "secondary_organization" for s in srefs):
                if p1_status == "verified":
                    findings.append({"check": "D07_v1.2-来源等级", "result": "BLOCK",
                                     "detail": f"{rid}: source_refs 仅含 secondary_organization 但 p1_verification_status=verified"})

    # ============================================================
    # 4. 社保/养老金过度解释检查
    # ============================================================
    text_full = json.dumps(obj, ensure_ascii=False)
    for phrase in SOCIAL_SECURITY_OVERUSE:
        if phrase in text_full:
            findings.append({"check": "D07_v1.2-社保过度解释", "result": "BLOCK",
                             "detail": f"发现过度解释表达: '{phrase}'。长期机构资金证据不得直接作为买卖信号。"})
            break  # 一条足以 BLOCK

    # ============================================================
    # 5. 强动作限制
    # ============================================================
    if ab in ("BUY", "SELL"):
        # P1 warn_pending → 强动作 BLOCK
        if p1_status == "warn_pending":
            findings.append({"check": "D07_v1.2-强动作+P1未验", "result": "BLOCK",
                             "detail": "action_bias=BUY/SELL 但 long_term_institutional_evidence.p1_verification_status=warn_pending"})

        # 检查 supporting_evidence 是否主要来自长期机构资金
        evidence = obj.get("supporting_evidence", [])
        if isinstance(lie, dict) and lie.get("status") == "present":
            # 主要证据来自机构资金的判断：看是否 mentioning evidence 与机构资金相关
            ev_text = " ".join(e.get("evidence", "") for e in evidence)
            lie_keywords = ["社保", "养老金", "养老保险", "年金", "险资", "长期机构", "机构资金"]
            lie_hits = sum(1 for kw in lie_keywords if kw in ev_text)
            if lie_hits >= 2 and len(evidence) >= 1 and lie_hits / max(len(evidence), 1) >= 0.5:
                findings.append({"check": "D07_v1.2-机构资金强动作", "result": "BLOCK",
                                 "detail": "支持证据主要来自长期机构资金，但 action_bias=BUY/SELL。长期机构资金最多辅助 WATCH/HOLD/NEUTRAL。"})

    # ============================================================
    # 6. 结论强度检查
    # ============================================================
    cs = obj.get("conclusion_strength", "")
    if cs:
        if p1_status == "warn_pending" and cs not in ("风险假设", "数据不足"):
            findings.append({"check": "D07_v1.2-结论强度与P1", "result": "WARN",
                             "detail": f"p1_verification_status=warn_pending 但 conclusion_strength='{cs}'，应为'风险假设'或'数据不足'"})

        # 仅 P0 索引，无 P1 或 gap → 不得可定性
        if isinstance(lie, dict) and lie.get("status") == "present" and p1_status != "verified":
            has_p0 = any(s.get("source_level") == "original_disclosure"
                         for rec in lie.get("records", [])
                         for s in rec.get("source_refs", []))
            if not has_p0 and cs == "可定性":
                findings.append({"check": "D07_v1.2-结论强度与P0", "result": "WARN",
                                 "detail": "仅 P0 辅助索引，无 P1 原始披露 verified，但 conclusion_strength='可定性'"})

    # ============================================================
    # 7. P1 verified 防伪检查
    # ============================================================
    if p1_status == "verified" and isinstance(lie, dict) and lie.get("status") == "present":
        records = lie.get("records", [])
        for i, rec in enumerate(records):
            srefs = rec.get("source_refs", [])
            official = [s for s in srefs if s.get("source_level") in ("original_disclosure", "exchange_announcement")]
            if not official:
                findings.append({"check": "D07_v1.2-P1伪verified", "result": "BLOCK",
                                 "detail": f"声明 p1_verification_status=verified 但无 source_level=original_disclosure/exchange_announcement 的来源记录"})
            else:
                for s in official:
                    missing = []
                    if not s.get("source_url"): missing.append("source_url")
                    if not s.get("local_pdf_path"): missing.append("local_pdf_path")
                    if not s.get("sha256"): missing.append("sha256")
                    if s.get("verification_status") != "verified":
                        missing.append("verification_status!=verified")
                    if missing:
                        findings.append({"check": "D07_v1.2-P1伪verified", "result": "BLOCK",
                                         "detail": f"声明 verified 但官方来源缺少: {', '.join(missing)}"})

    return findings


# ============================================================
# P0-G: Registry/Signal helpers
# ============================================================
_registry_cache = None
_signal_cache = None

def _load_registry_ids():
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "knowledge_registry.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _registry_cache = {e["knowledge_id"] for e in data.get("entries", [])}
    except Exception:
        _registry_cache = set()
    return _registry_cache


def _find_registry_entry(kid):
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "knowledge_registry.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for e in data.get("entries", []):
            if e["knowledge_id"] == kid:
                return e
    except Exception:
        pass
    return None


def _load_signal_ids():
    """读取已注册信号ID列表。
    优先从 interpretation_rules.json 读取，失败时 fallback 到 信号胜率库_v1.0.md。"""
    global _signal_cache
    if _signal_cache is not None:
        return _signal_cache
    import os as _os
    _signal_cache = set()

    # 尝试从 interpretation_rules.json 读取（结构化优先）
    rules_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "interpretation_rules.json")
    if _os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_data = json.load(f)
            signals = rules_data.get("signal_winrate_rules", {}).get("signals", [])
            for sig in signals:
                sid = sig.get("signal_id", "")
                if sid:
                    _signal_cache.add(sid)
            if _signal_cache:
                return _signal_cache
        except Exception:
            pass

    # Fallback: 从旧 信号胜率库_v1.0.md 读取
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "六库", "信号胜率库_v1.0.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            import re
            for line in f:
                m = re.match(r"\| (SIG-\d{3}) ", line)
                if m:
                    _signal_cache.add(m.group(1))
    except Exception:
        pass
    return _signal_cache


# ============================================================
# main
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="统一解读闸门验证 (含内置schema校验)")
    parser.add_argument("path", help="解释对象JSON路径")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    parser.add_argument("--skip-schema", action="store_true", help="跳过schema校验")
    args = parser.parse_args()

    obj = load_json(args.path)
    # P0-D: 双对象格式 → 提取内层 interpretation
    if "interpretation" in obj and "unified_interpretation" in obj:
        obj = obj["interpretation"]

    # Step 0: Schema 校验
    schema_errs, schema_warns = [], []
    if not args.skip_schema and os.path.exists(SCHEMA_PATH):
        sv = SchemaValidator(SCHEMA_PATH)
        schema_errs, schema_warns = sv.validate(obj)
    elif not args.skip_schema:
        schema_errs.append(f"Schema文件不存在: {SCHEMA_PATH}")

    # Step 1: 额外检查
    extra_findings = run_extra_checks(obj)
    for f in extra_findings:
        if f["result"] == "BLOCK":
            schema_errs.append(f["detail"])

    # Step 2: D07 v1.2 校验
    d07_findings = run_d07_v12_checks(obj)
    for f in d07_findings:
        if f["result"] == "BLOCK":
            schema_errs.append(f["detail"])

    # Step 3: U-9
    u9_status, u9_findings = run_u9(obj) if not args.skip_schema else ("SKIP", [])

    # Step 4: U-10
    u10_status, u10_findings = run_u10(obj) if not args.skip_schema else ("SKIP", [])

    # 合并结果
    overall = "PASS"
    if schema_errs:
        overall = "BLOCK"
    if u9_status == "BLOCK" or u10_status == "BLOCK":
        overall = "BLOCK"
    elif u9_status == "WARN" or u10_status == "WARN" or schema_warns:
        overall = "WARN"
    # D07 v1.2 的 WARN 也能升级整体
    if overall == "PASS" and any(f["result"] == "WARN" for f in d07_findings):
        overall = "WARN"
    result = {
        "interpretation_id": obj.get("interpretation_id", "UNKNOWN"),
        "timestamp": datetime.now().isoformat(),
        "schema_validation": {
            "errors": schema_errs,
            "warnings": schema_warns
        },
        "d07_v12_checks": d07_findings,
        "u9": {"status": u9_status, "findings": u9_findings} if u9_status != "SKIP" else None,
        "u10": {"status": u10_status, "findings": u10_findings} if u10_status != "SKIP" else None,
        "extra_checks": extra_findings,
        "overall": overall
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"解释对象: {result['interpretation_id']}")
        print(f"整体结果: {overall}")
        if schema_errs:
            print(f"\nSchema 错误 ({len(schema_errs)}):")
            for e in schema_errs:
                print(f"  [BLOCK] {e}")
        if schema_warns:
            print(f"\nSchema 警告 ({len(schema_warns)}):")
            for w in schema_warns:
                print(f"  [WARN] {w}")
        if result["u9"]:
            print(f"\nU-9 事实审计: {u9_status}")
            for f in u9_findings:
                print(f"  [{f['result']}] {f['check']}: {f['detail']}")
        if result["u10"]:
            print(f"\nU-10 动作审计: {u10_status}")
            for f in u10_findings:
                print(f"  [{f['result']}] {f['check']}: {f['detail']}")
        if d07_findings:
            print(f"\nD07 v1.2 校验:")
            for f in d07_findings:
                print(f"  [{f['result']}] {f['check']}: {f['detail']}")
        if extra_findings:
            print(f"\n额外检查:")
            for f in extra_findings:
                print(f"  [{f['result']}] {f['check']}: {f['detail']}")

    sys.exit(0 if overall == "PASS" else (1 if overall == "WARN" else 2))


if __name__ == "__main__":
    main()
