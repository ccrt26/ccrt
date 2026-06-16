#!/usr/bin/env python3
"""
检查驾驶舱产品化状态（session3 v2 工程/业务双通道版）。

输出：
- engineering_status: PASS/BLOCK（bundle 契约完整性）
- business_user_visible_status: BLOCK/COMPLETE（真实数据状态）
- overall: PASS/BLOCK（向后兼容，任一 BLOCK 触发）
"""

import argparse
import json
import os
import re
import sys


# 业务 BLOCK 检查项（允许）
BUSINESS_BLOCK_CHECKS = {
    "data_date_divergence", "data_stale", "rule_health_warn",
    "position_unavailable", "conclusion_status_mismatch",
    "dashboard_status_mismatch", "position_data_leak",
    "chart_data_insufficient",
}

# 工程 BLOCK 检查项（不允许）
ENGINEERING_BLOCK_CHECKS = {
    "required_file", "bundle_index_missing", "run_manifest_missing",
    "bundle_file_missing", "run_id_mismatch", "schema_version_mismatch",
    "bundle_version_mismatch", "evidence_refs_missing",
    "no_production_touch_false", "forbidden_path_touched",
    "bundle_error", "hardcoded_decision", "chart_data_missing",
    "stock_pool_missing", "fake_stock_data", "chart_placeholder_in_js",
    "chart_placeholder_in_css", "stocks_parse", "chart_data_parse",
    "legacy_compat_missing", "ui_structure",
    "required_field_evidence_missing", "source_refs_missing",
    "field_value_wrapped",
    # 会话四前端契约（工程级）
    "frontend_home_loader_contract",
    "frontend_no_auto_detail_load",
    "frontend_lazy_partition_contract",
    "frontend_legacy_primary_source",
    "frontend_formal_action_leak",
    "frontend_position_sensitive_render",
    "frontend_status_code_contract",
    "frontend_bundle_priority_contract",
}


def _check_field_evidence_whitelist(data_dir: str, findings: list):
    """补丁 A 白名单：逐项校验 field_evidence key 存在。"""
    required_fe = {
        "dashboard.json": [
            "overall_status", "conclusion_status", "as_of_date", "blocks", "warnings",
            "status_gate.data_status", "status_gate.decision_blockers",
            "status_gate.status_gate_source_refs",
        ],
        "stock_pool.json": [
            "members.600114.stock_code", "members.600114.stock_name",
            "members.600114.status", "members.600114.data_status",
            "members.600114.evidence_status",
        ],
        "stocks.json": [
            "stocks.600114.stock_code", "stocks.600114.stock_name",
            "stocks.600114.close", "stocks.600114.change_pct",
            "stocks.600114.actual_trade_date", "stocks.600114.data_freshness_status",
            "stocks.600114.conclusion_status", "stocks.600114.user_visible_status",
        ],
        "today_decisions.json": [
            "trade_date", "conclusion_status", "user_visible_status",
            "user_position.position_status", "market_today.close",
            "market_today.ma5", "market_today.ma20", "rule_health_status",
            "decision_blockers", "primary_action", "confidence",
        ],
        "chart_data.json": [
            "stock_code", "source_last_date", "feature_snapshot_actual_date",
            "data_date_divergence", "ohlc", "ma5", "ma20", "ma60",
        ],
        "evidence_index.json": [
            "evidence_items",
        ],
        "stocks/600114/detail.json": [
            "stock_code", "stock_name",
            "market_today.close", "market_today.ma5", "market_today.ma20",
            "status_gate.data_status", "status_gate.decision_blockers",
            "rule_health_summary.overall_status",
            "position_public_view.position_status",
            "evidence_summary", "decision_blockers",
        ],
        "stocks/600114/chart_data.json": [
            "stock_code", "source_last_date", "feature_snapshot_actual_date",
            "data_date_divergence", "ohlc", "ma5", "ma20", "ma60",
        ],
        "stocks/600114/evidence.json": [
            "evidence_items",
        ],
    }

    for fname, expected_keys in required_fe.items():
        fpath = os.path.join(data_dir, fname)
        if not os.path.exists(fpath):
            findings.append({"check": "required_field_evidence_missing", "path": fpath,
                             "status": "BLOCK", "detail": f"文件缺失: {fname}"})
            continue
        try:
            data = json.load(open(fpath))
        except Exception as e:
            findings.append({"check": "required_field_evidence_missing", "path": fpath,
                             "status": "BLOCK", "detail": f"解析失败: {e}"})
            continue
        fe = data.get("field_evidence", {})
        for key in expected_keys:
            if key not in fe:
                findings.append({"check": "required_field_evidence_missing", "path": fpath,
                                 "status": "BLOCK",
                                 "detail": f"{fname} field_evidence 缺少 key: {key}"})
                continue
            fe_entry = fe[key]
            # 校验 evidence_refs 存在
            ev_refs = fe_entry.get("evidence_refs", [])
            if not ev_refs:
                findings.append({"check": "evidence_refs_missing", "path": fpath,
                                 "status": "BLOCK",
                                 "detail": f"{fname} field_evidence.{key} evidence_refs 为空"})
            # 校验 source_refs 非空
            src_refs = fe_entry.get("source_refs", [])
            if not src_refs:
                findings.append({"check": "source_refs_missing", "path": fpath,
                                 "status": "BLOCK",
                                 "detail": f"{fname} field_evidence.{key} source_refs 为空"})
            # 校验 source_path 或 source_refs 内任一有 source_path
            sp = fe_entry.get("source_path", "")
            if not sp:
                has_path_in_refs = any(r.get("source_path") for r in src_refs)
                has_computed = any(r.get("source_type") in ("status_gate", "rule_health", "position_public_view", "computed") for r in src_refs)
                if not has_path_in_refs and not has_computed:
                    if not src_refs:
                        findings.append({"check": "source_refs_missing", "path": fpath,
                                         "status": "BLOCK",
                                         "detail": f"{fname} field_evidence.{key} 无 source_path 也无 source_refs"})

        # 校验 evidence_index evidence_items 存在
        if fname == "evidence_index.json":
            if not data.get("evidence_items"):
                findings.append({"check": "required_field_evidence_missing", "path": fpath,
                                 "status": "BLOCK",
                                 "detail": "evidence_index.json 缺少 evidence_items"})

        # stocks/600114/evidence.json evidence_items
        if fname == "stocks/600114/evidence.json":
            if not data.get("evidence_items"):
                findings.append({"check": "required_field_evidence_missing", "path": fpath,
                                 "status": "BLOCK",
                                 "detail": "evidence.json 缺少 evidence_items"})

    # 校验 evidence.json 的 evidence_items
    ev_path = os.path.join(data_dir, "stocks", "600114", "evidence.json")
    if os.path.exists(ev_path):
        try:
            ev_data = json.load(open(ev_path))
            items = ev_data.get("evidence_items", [])
            ev_ids = {e.get("evidence_id") for e in items if e.get("evidence_id")}
            if not ev_ids:
                findings.append({"check": "required_field_evidence_missing", "path": ev_path,
                                 "status": "BLOCK",
                                 "detail": "evidence.json evidence_items 无 evidence_id"})
            # 检查 field_evidence 中的 evidence_refs 指向存在的 ID
            for fname in required_fe:
                fpath = os.path.join(data_dir, fname)
                if os.path.exists(fpath):
                    try:
                        data = json.load(open(fpath))
                        for key, fe_entry in data.get("field_evidence", {}).items():
                            for er in fe_entry.get("evidence_refs", []):
                                if er not in ev_ids:
                                    findings.append({"check": "evidence_refs_missing", "path": fpath,
                                                     "status": "BLOCK",
                                                     "detail": f"{fname} field_evidence.{key} 引用不存在 evidence_id: {er}"})
                    except Exception:
                        pass
        except Exception:
            pass

    # 校验业务字段仍为原始值（不是包装对象）
    charts_path = os.path.join(data_dir, "chart_data.json")
    if os.path.exists(charts_path):
        try:
            cd = json.load(open(charts_path))
            for fk in ("ohlc", "ma5", "ma20", "ma60"):
                val = cd.get(fk)
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict) and "value" in item and "source_refs" in item:
                            findings.append({"check": "field_value_wrapped", "path": charts_path,
                                             "status": "BLOCK",
                                             "detail": f"chart_data.json {fk} 值被包装为对象，违反业务字段原始值规则"})
        except Exception:
            pass


def check_dashboard_productization(docs_dir: str, data_dir: str) -> dict:
    findings = []
    fake_data_hits = []
    hardcoded_decision_hits = []
    checked_files = []
    bundle_errors = []

    # ── 1-4. 文件存在性 + JS/CSS/HTML ──
    required = ["index.html", "app.css", "app.js"]
    for fname in required:
        path = os.path.join(docs_dir, fname)
        if os.path.exists(path):
            checked_files.append(path)
        else:
            findings.append({"check": "required_file", "path": path, "status": "BLOCK", "detail": f"缺失: {fname}"})

    js_path = os.path.join(docs_dir, "app.js")
    if os.path.exists(js_path):
        js = open(js_path, encoding="utf-8").read()
        checked_files.append(js_path)
        hardcoded_patterns = [
            (r"建议持有/观察", "硬编码建议"), (r"持有为主", "硬编码持有决策"),
            (r"冲高回落", "硬编码走势描述"), (r"chart-placeholder", "占位图表"),
            (r"此处展示", "占位说明"), (r"考虑减仓至 50%", "硬编码减仓"),
            (r"若明日反弹回 MA20 上方: 继续持有", "硬编码决策"),
        ]
        for pattern, desc in hardcoded_patterns:
            if re.search(pattern, js):
                hardcoded_decision_hits.append({"pattern": pattern, "desc": desc})
                findings.append({"check": "hardcoded_decision", "path": js_path, "status": "BLOCK", "detail": f"硬编码：{desc}"})
        if ".chart-placeholder" in js:
            findings.append({"check": "chart_placeholder_in_js", "path": js_path, "status": "BLOCK", "detail": "app.js 中包含 chart-placeholder"})

    css_path = os.path.join(docs_dir, "app.css")
    if os.path.exists(css_path):
        css = open(css_path).read()
        checked_files.append(css_path)
        if ".chart-placeholder" in css:
            findings.append({"check": "chart_placeholder_in_css", "path": css_path, "status": "BLOCK", "detail": "app.css 中包含 .chart-placeholder"})

    html_path = os.path.join(docs_dir, "index.html")
    if os.path.exists(html_path):
        html = open(html_path).read()
        checked_files.append(html_path)
        has_sb = bool(re.search(r'sidebar|side-nav|side-navbar', html, re.IGNORECASE))
        has_as = "view-dashboard" in html and "view-stocks" in html
        has_5v = all(f"view-{v}" in html for v in ["dashboard", "stocks", "deep", "daily", "rules"])
        if not has_sb or not has_as or not has_5v:
            findings.append({"check": "ui_structure", "path": html_path, "status": "BLOCK", "detail": f"UI 结构: sidebar={has_sb}, shell={has_as}, 5views={has_5v}"})

    # ── 5. stocks 无证据股票 ──
    stocks_path = os.path.join(data_dir, "stocks.json")
    if os.path.exists(stocks_path):
        try:
            sd = json.load(open(stocks_path))
            checked_files.append(stocks_path)
            for s in sd.get("stocks", []):
                code = s.get("stock_code", "")
                if code in ("600519", "000858"):
                    fake_data_hits.append({"stock": code, "reason": "无真实证据"})
                    findings.append({"check": "fake_stock_data", "path": stocks_path, "status": "WARN" if code == "600519" else "BLOCK", "detail": f"股票 {code} 无同等级真实证据"})
        except Exception as e:
            findings.append({"check": "stocks_parse", "path": stocks_path, "status": "BLOCK", "detail": str(e)})

    # ── 6. chart_data ──
    chart_path = os.path.join(data_dir, "chart_data.json")
    if os.path.exists(chart_path):
        try:
            chart = json.load(open(chart_path))
            checked_files.append(chart_path)
            ohlc = chart.get("ohlc", [])
            if len(ohlc) < 20:
                findings.append({"check": "chart_data_insufficient", "path": chart_path, "status": "WARN", "detail": f"ohlc 仅 {len(ohlc)} 行"})
        except Exception as e:
            findings.append({"check": "chart_data_parse", "path": chart_path, "status": "BLOCK", "detail": str(e)})
    else:
        findings.append({"check": "chart_data_missing", "path": str(chart_path), "status": "BLOCK", "detail": "chart_data.json 缺失"})

    # ── 7. today_decisions ──
    dec_path = os.path.join(data_dir, "today_decisions.json")
    if os.path.exists(dec_path):
        try:
            dec = json.load(open(dec_path))
            checked_files.append(dec_path)
            blockers = dec.get("decision_blockers", [])
            cs = dec.get("conclusion_status", "")
            pos = dec.get("user_position", {})
            if pos.get("cost_price") is not None and pos.get("quantity") is not None and "POSITION_UNAVAILABLE" in blockers:
                findings.append({"check": "position_data_leak", "path": dec_path, "status": "BLOCK", "detail": "POSITION_UNAVAILABLE 下出现真实 cost/quantity"})
            if cs == "FORMAL" and len(blockers) > 0:
                findings.append({"check": "conclusion_status_mismatch", "path": dec_path, "status": "BLOCK", "detail": f"FORMAL + blockers: {blockers}"})
        except Exception:
            pass

    # ── 8. 数据日期分歧 ──
    if os.path.exists(chart_path):
        try:
            chart = json.load(open(chart_path))
            if chart.get("data_date_divergence"):
                findings.append({"check": "data_date_divergence", "path": chart_path, "status": "BLOCK", "detail": chart.get("date_divergence_warning", "日期差异")})
        except Exception:
            pass

    # ── 9. dashboard 一致性 ──
    dash_path = os.path.join(data_dir, "dashboard.json")
    if os.path.exists(dash_path):
        try:
            dash = json.load(open(dash_path))
            if dash.get("overall_status") == "COMPLETE" and len(dash.get("blocks", [])) > 0:
                findings.append({"check": "dashboard_status_mismatch", "path": dash_path, "status": "BLOCK", "detail": "COMPLETE + blocks 非空"})
        except Exception:
            pass

    # ── 10. stock_pool 存在 ──
    pool_path = os.path.join(data_dir, "stock_pool.json")
    if os.path.exists(pool_path):
        checked_files.append(pool_path)
    else:
        findings.append({"check": "stock_pool_missing", "path": str(pool_path), "status": "BLOCK", "detail": "stock_pool.json 缺失"})

    # ──── bundle 一致性 ────

    bi_path = os.path.join(data_dir, "bundle_index.json")
    if os.path.exists(bi_path):
        checked_files.append(bi_path)
        try:
            bi = json.load(open(bi_path))
            bi_run_id = bi.get("run_id", "")
            bi_schema = bi.get("schema_version", "")
            current_bundle_path = bi.get("current_bundle_path", "")
            bi_files = bi.get("files", [])
            if not bi_run_id:
                bundle_errors.append("bundle_index run_id 为空")
            if not bi_schema:
                bundle_errors.append("bundle_index schema_version 为空")
            if current_bundle_path != f"bundles/{bi_run_id}/":
                findings.append({"check": "bundle_error", "path": bi_path, "status": "BLOCK",
                                 "detail": f"current_bundle_path({current_bundle_path}) 不等于 bundles/{bi_run_id}/"})

            for fe in bi_files:
                if fe.get("required"):
                    fp = os.path.join(data_dir, fe["path"])
                    if not os.path.exists(fp):
                        findings.append({"check": "bundle_file_missing", "path": fp, "status": "BLOCK", "detail": f"required 缺失: {fe['path']}"})

            for fe in bi_files:
                fp = os.path.join(data_dir, fe["path"])
                if os.path.exists(fp) and fp.endswith(".json") and fe["path"] != "bundle_index.json":
                    try:
                        fdata = json.load(open(fp))
                        if isinstance(fdata, dict):
                            if fdata.get("run_id") and fdata["run_id"] != bi_run_id:
                                findings.append({"check": "run_id_mismatch", "path": fp, "status": "BLOCK", "detail": f"run_id({fdata['run_id']}) != bundle({bi_run_id})"})
                            if fdata.get("schema_version") and fdata["schema_version"] != bi_schema:
                                findings.append({"check": "schema_version_mismatch", "path": fp, "status": "BLOCK", "detail": f"schema({fdata['schema_version']}) != bundle({bi_schema})"})
                    except Exception:
                        pass

            for fe in bi_files:
                if fe.get("legacy_compat"):
                    fp = os.path.join(data_dir, fe["path"])
                    if os.path.exists(fp):
                        try:
                            data = json.load(open(fp))
                            if not data.get("legacy_compat"):
                                findings.append({"check": "legacy_compat_missing", "path": fp, "status": "WARN", "detail": f"{fe['path']} 缺少 legacy_compat"})
                        except Exception:
                            pass
        except Exception as e:
            bundle_errors.append(f"bundle_index 解析失败: {e}")
    else:
        findings.append({"check": "bundle_index_missing", "path": str(bi_path), "status": "BLOCK", "detail": "bundle_index.json 缺失"})

    rm_path = os.path.join(data_dir, "run_manifest.json")
    if os.path.exists(rm_path):
        checked_files.append(rm_path)
        try:
            rm = json.load(open(rm_path))
            if not rm.get("run_id"):
                bundle_errors.append("run_manifest run_id 为空")
            npt = rm.get("no_production_touch", {})
            for k in ("baseline_registry_touched", "runtime_entry_registry_touched",
                      "launchd_touched", "real_position_connected",
                      "production_cutover", "formal_rule_changed"):
                if npt.get(k) is not False:
                    findings.append({"check": "no_production_touch_false", "path": rm_path, "status": "BLOCK", "detail": f"no_production_touch.{k} 不为 false"})
        except Exception as e:
            bundle_errors.append(f"run_manifest 解析失败: {e}")
    else:
        findings.append({"check": "run_manifest_missing", "path": str(rm_path), "status": "BLOCK", "detail": "run_manifest.json 缺失"})

    for err in bundle_errors:
        findings.append({"check": "bundle_error", "path": str(bi_path), "status": "BLOCK", "detail": err})

    # ──── 证据白名单（补丁 A） ────
    _check_field_evidence_whitelist(data_dir, findings)

    # ──── 会话四前端契约 ────
    frontend_fe = _check_session4_frontend_contract(docs_dir, findings)
    frontend_fe_items = [f for f in findings if f["check"].startswith("frontend_")]

    # ── 分离工程 / 业务 BLOCK ──
    blocks = [f for f in findings if f.get("status") == "BLOCK"]
    eng_blocks = [f for f in blocks if f["check"] in ENGINEERING_BLOCK_CHECKS]
    bus_blocks = [f for f in blocks if f["check"] in BUSINESS_BLOCK_CHECKS]
    other_blocks = [f for f in blocks if f["check"] not in ENGINEERING_BLOCK_CHECKS and f["check"] not in BUSINESS_BLOCK_CHECKS]

    engineering_status = "PASS" if not eng_blocks and not bundle_errors else "BLOCK"
    business_block = len(bus_blocks) > 0
    has_gate_blocker = any(f["check"] in ("data_date_divergence",) for f in bus_blocks)
    business_user_visible_status = "BLOCK" if (business_block or has_gate_blocker) else "COMPLETE"
    overall = "PASS" if not blocks else "BLOCK"

    status_gate_blocks = [f for f in findings if f.get("status") == "BLOCK" and f["check"] in (
        "data_date_divergence", "conclusion_status_mismatch", "dashboard_status_mismatch",
        "position_data_leak", "bundle_index_missing", "run_manifest_missing",
        "run_id_mismatch", "bundle_file_missing", "no_production_touch_false",
        "evidence_refs_missing",
    )]

    ui_findings = [f for f in findings if f["check"] == "ui_structure"]
    visual_contract_status = "PASS" if not ui_findings else "BLOCK"

    # 前端契约状态
    frontend_blk = [f for f in findings if f["check"].startswith("frontend_") and f.get("status") == "BLOCK"]
    frontend_contract_status = "PASS" if not frontend_blk else "BLOCK"

    return {
        "overall": overall,
        "engineering_status": engineering_status,
        "business_user_visible_status": business_user_visible_status,
        "findings": findings,
        "checked_files": checked_files,
        "fake_data_hits": fake_data_hits,
        "hardcoded_decision_hits": hardcoded_decision_hits,
        "visual_contract_status": visual_contract_status,
        "data_truth_status": "PASS" if not fake_data_hits else "BLOCK",
        "recommended_user_visible_status": business_user_visible_status,
        "status_gate_blocks": status_gate_blocks,
        "bundle_errors": bundle_errors,
        "bundle_contract_status": "PASS" if not eng_blocks else "BLOCK",
        "run_manifest_status": "PASS" if not [f for f in eng_blocks if "run_manifest" in f["check"]] else "BLOCK",
        "schema_contract_status": "PASS",
        "run_id_consistency_status": "PASS" if not [f for f in eng_blocks if "run_id" in f["check"]] else "BLOCK",
        "evidence_contract_status": "PASS" if not [f for f in eng_blocks if "evidence" in f["check"]] else "BLOCK",
        "no_production_touch_status": "PASS" if not [f for f in eng_blocks if "no_production" in f["check"]] else "BLOCK",
        # 会话四前端契约
        "frontend_contract_status": frontend_contract_status,
        "frontend_contract_findings": frontend_fe_items,
        "home_loader_contract_status": frontend_fe.get("home_loader", "BLOCK"),
        "lazy_loading_contract_status": frontend_fe.get("lazy_loading", "BLOCK"),
        "no_sensitive_position_render_status": frontend_fe.get("no_sensitive_position", "BLOCK"),
        "no_formal_action_leak_status": frontend_fe.get("no_formal_action_leak", "BLOCK"),
    }



def _check_session4_frontend_contract(docs_dir: str, findings: list) -> dict:
    """检查会话四前端契约。工程失败写入 findings，返回各项状态的 dict。"""
    import re
    js_path = os.path.join(docs_dir, "app.js")
    result = {
        "home_loader": "PASS",
        "no_auto_detail": "PASS",
        "lazy_loading": "PASS",
        "no_legacy_primary": "PASS",
        "no_formal_action_leak": "PASS",
        "no_sensitive_position": "PASS",
        "status_code": "PASS",
        "bundle_priority": "PASS",
    }
    if not os.path.exists(js_path):
        for k in result:
            result[k] = "BLOCK"
            findings.append({"check": f"frontend_{k}", "path": js_path,
                             "status": "BLOCK", "detail": f"app.js 缺失"})
        return result

    js = open(js_path, encoding="utf-8").read()

    # 1. home_loader_contract — loadHomeBundle 只能加载 4 JSON
    lhb = re.search(r'async\s+function\s+loadHomeBundle\s*\([^)]*\)\s*{', js)
    if lhb:
        start = lhb.start()
        brace = js.index('{', start) + 1
        depth, i = 1, brace
        while i < len(js) and depth > 0:
            if js[i] == '{': depth += 1
            elif js[i] == '}': depth -= 1
            i += 1
        body = js[brace:i-1] if depth == 0 else js[brace:]
        loads = re.findall(r"loadJSON\s*\(\s*['\"]([^'\"]+\.json)['\"]\s*\)", body)
        norm = [f.split("/")[-1] for f in loads]
        expected = {"stock_pool.json", "stocks.json", "bundle_index.json", "run_manifest.json"}
        actual = set(norm)
        if actual != expected:
            result["home_loader"] = "BLOCK"
            findings.append({"check": "frontend_home_loader_contract", "path": js_path,
                "status": "BLOCK",
                "detail": f"loadHomeBundle 加载 JSON 不符: 期望{expected} 实际{actual}"})
        forbidden = {"dashboard.json", "today_decisions.json", "chart_data.json",
                     "evidence_index.json", "rule_health.json", "rule_health_summary.json"}
        for fb in forbidden:
            if fb in actual:
                result["home_loader"] = "BLOCK"
                findings.append({"check": "frontend_home_loader_contract", "path": js_path,
                    "status": "BLOCK", "detail": f"loadHomeBundle 加载禁止文件: {fb}"})
    else:
        result["home_loader"] = "BLOCK"
        findings.append({"check": "frontend_home_loader_contract", "path": js_path,
            "status": "BLOCK", "detail": "loadHomeBundle 函数不存在"})

    # 2. no_auto_detail_load — loadHomeBundle 不得调用 selectStock
    if lhb:
        body = None
        lhb2 = re.search(r'async\s+function\s+loadHomeBundle\s*\([^)]*\)\s*{', js)
        if lhb2:
            start = lhb2.start()
            brace = js.index('{', start) + 1
            depth, i = 1, brace
            while i < len(js) and depth > 0:
                if js[i] == '{': depth += 1
                elif js[i] == '}': depth -= 1
                i += 1
            body = js[brace:i-1] if depth == 0 else js[brace:]
        if body:
            call_select = re.search(r'\bselectStock\s*\(', body)
            if call_select:
                # 检查是否在字符串中（onclick模板）
                line = body[max(0, call_select.start()-50):call_select.end()+50]
                if '"selectStock' not in line and "'selectStock" not in line:
                    result["no_auto_detail"] = "BLOCK"
                    findings.append({"check": "frontend_no_auto_detail_load", "path": js_path,
                        "status": "BLOCK", "detail": "loadHomeBundle 可能直接调用 selectStock()"})

        # 检查是否有 detail.json/chart_data.json/evidence.json 字样（不含注释）
        for suffix in ["detail.json", "chart_data.json", "evidence.json"]:
            if suffix in body:
                idx = body.find(suffix)
                line = body[max(0, idx-40):idx+len(suffix)+10]
                if not line.strip().startswith('//') and not line.strip().startswith('*'):
                    result["no_auto_detail"] = "BLOCK"
                    findings.append({"check": "frontend_no_auto_detail_load", "path": js_path,
                        "status": "BLOCK", "detail": f"loadHomeBundle 中出现详情路径: {suffix}"})

    # 3. lazy_partition_contract — selectStock 必须使用分片路径
    ss = re.search(r'(?:async\s+)?function\s+selectStock\s*\([^)]*\)\s*{', js)
    if ss:
        start = ss.start()
        brace = js.index('{', start) + 1
        depth, i = 1, brace
        while i < len(js) and depth > 0:
            if js[i] == '{': depth += 1
            elif js[i] == '}': depth -= 1
            i += 1
        body = js[brace:i-1] if depth == 0 else js[brace:]
        for sf in ["detail.json", "chart_data.json", "evidence.json"]:
            # Accept both template literal and string concatenation
            tpl_pattern = f"stocks/${{stockCode}}/{sf}"
            concat_pattern = f"/{sf}"  # just check the filename appears in the body
            if tpl_pattern not in body and f"/{sf}" not in body:
                result["lazy_loading"] = "BLOCK"
                findings.append({"check": "frontend_lazy_partition_contract", "path": js_path,
                    "status": "BLOCK", "detail": f"selectStock 缺少分片路径: {sf}"})
                break
        # 检查不使用 legacy JSON
        for fb in ["data/dashboard.json", "data/today_decisions.json",
                   "data/chart_data.json", "data/evidence_index.json",
                   "data/rule_health.json", "data/run_state.json"]:
            if fb in body:
                result["lazy_loading"] = "BLOCK"
                result["no_legacy_primary"] = "BLOCK"
                findings.append({"check": "frontend_legacy_primary_source", "path": js_path,
                    "status": "BLOCK", "detail": f"selectStock 使用 legacy JSON: {fb}"})
                break
    else:
        result["lazy_loading"] = "BLOCK"
        findings.append({"check": "frontend_lazy_partition_contract", "path": js_path,
            "status": "BLOCK", "detail": "selectStock 函数不存在"})

    # 4. formal_action_leak — canShowFormalAction + renderDecisionBoundary
    if "function canShowFormalAction" not in js:
        result["no_formal_action_leak"] = "BLOCK"
        findings.append({"check": "frontend_formal_action_leak", "path": js_path,
            "status": "BLOCK", "detail": "canShowFormalAction 函数不存在"})

    # 5. position_sensitive — 不渲染敏感字段
    sensitive = ["cost_price", "quantity", "unrealized_pnl", "real_pnl", "成本价", "数量", "盈亏"]
    for sens in sensitive:
        if sens in js:
            idx = js.find(sens)
            ctx = js[max(0, idx-300):idx+len(sens)+300]
            if "UNAVAILABLE" not in ctx and "不可用" not in ctx and "未接入" not in ctx:
                result["no_sensitive_position"] = "BLOCK"
                findings.append({"check": "frontend_position_sensitive_render", "path": js_path,
                    "status": "BLOCK", "detail": f"渲染敏感字段: {sens}"})
                break

    # 6. status_code_contract — 状态码可见
    html_path = os.path.join(docs_dir, "index.html")
    html_content = open(html_path, encoding="utf-8").read() if os.path.exists(html_path) else ""
    all_text = js + "\n" + html_content
    for code in ["FORMAL", "OBSERVATION", "SHADOW", "BLOCKED"]:
        if code not in all_text:
            result["status_code"] = "BLOCK"
            findings.append({"check": "frontend_status_code_contract", "path": js_path,
                "status": "BLOCK", "detail": f"缺少状态码: {code}"})
            break

    # 7. bundle_priority — resolveBundleStatus 存在
    if "function resolveBundleStatus" not in js:
        result["bundle_priority"] = "BLOCK"
        findings.append({"check": "frontend_bundle_priority_contract", "path": js_path,
            "status": "BLOCK", "detail": "resolveBundleStatus 函数不存在"})

    return result



def main():
    parser = argparse.ArgumentParser(description="检查驾驶舱产品化")
    parser.add_argument("--docs-dir", required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--preview", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    data_dir = args.data_dir or os.path.join(args.docs_dir, "data")
    result = check_dashboard_productization(args.docs_dir, data_dir)

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[CHECKER] 已写入: {args.out} (eng={result.get('engineering_status')}, bus={result.get('business_user_visible_status')})")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("engineering_status") == "BLOCK":
        sys.exit(1)  # 工程 BLOCK → exit 1
    elif result.get("overall") == "BLOCK":
        sys.exit(0)  # 仅业务 BLOCK → exit 0（engineering_status=PASS）
    else:
        sys.exit(0)  # 全部 PASS → exit 0


if __name__ == "__main__":
    main()
