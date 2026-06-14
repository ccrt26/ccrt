#!/usr/bin/env python3
"""
G3-QINGSHAN-FIRST-LITERATURE-CARD-VALIDATOR-FIX-v1.0 增强验证脚本 v3
literature_cards 不再一票否决，改用边界检查；
rule_candidates 仍然一票否决。
"""
import json, hashlib, sys, re
from pathlib import Path

STAGE = "G3-QINGSHAN-FIRST-LITERATURE-CARD-VALIDATOR-FIX-v1.0"
ROOT = Path("/Users/ccrt/ccrt")
AGENTS_DIR = ROOT / ".claude" / "agents"
KNOWLEDGE = ROOT / "00_项目地基/07_知识进化/knowledge"
LEGACY_DIR = KNOWLEDGE / "sources" / "legacy_role_kb"
ROLES_DIR = KNOWLEDGE / "roles"
RULES_DIR = KNOWLEDGE / "rules"
ROUTING_DIR = KNOWLEDGE / "routing"
LIT_DIR = KNOWLEDGE / "literature"
LIT_CARDS_DIR = KNOWLEDGE / "literature_cards"
REPORTS_DIR = KNOWLEDGE / "reports"
MANIFEST_PATH = KNOWLEDGE / "manifest.json"
ROUTER_PATH = ROUTING_DIR / "krm_task_router_v1.0.json"
WRITE_REPORT = "--write-report" in sys.argv
if WRITE_REPORT:
    sys.argv = [x for x in sys.argv if x != "--write-report"]

FINANCIAL_ROLES_CN = ["玉夜", "青山", "流金", "信鸽", "山猫", "腰子"]
FINANCIAL_ROLES_LATIN = ["yuye", "qingshan", "liujin", "xinge", "shanmao", "yaozi"]

ENGLISH_LEGACY_TOKENS = [f"legacy_role_kb/{la}" for la in FINANCIAL_ROLES_LATIN]
PLACEHOLDER_TOKENS = [f"{{{la}" for la in FINANCIAL_ROLES_LATIN]
VALID_QUALITY_STATUSES = {"quality_pass", "quality_pass_with_cross_check"}
FORBIDDEN_CARD_FIELDS = {"rule_candidate", "active_rule", "parameter_update", "core_knowledge_update"}
REQUIRED_ROUTES_CN = {"flow_issue","knowledge_routing_issue","financial_redline","evidence_quality_issue",
                      "signal_validity_issue","event_catalyst_issue","macro_environment_issue",
                      "integration_decision_issue","post_evaluation_issue","output_format_issue"}
SHARED_DIRS_SET = {"risk_rules","evidence_rules","output_rules","routing_rules","post_evaluation_rules","parameter_rules"}
QINGSHAN_THREE = ["qingshan_source_selection_policy_v1.0.json","qingshan_literature_quality_schema_v1.0.json","qingshan_literature_card_to_rule_candidate_flow_v1.0.json"]


def main():
    errors = []
    all_pass = True

    def check(label, ok, note=""):
        nonlocal all_pass
        if not ok:
            all_pass = False
            errors.append(f"{label}: {note}")

    # ----- 1-3: legacy_role_kb -----
    dirs_ok = all((LEGACY_DIR / c).exists() for c in FINANCIAL_ROLES_CN)
    check("legacy_kb_dirs", dirs_ok, f"all {len(FINANCIAL_ROLES_CN)} exist")
    total_legacy = sum(len(list((LEGACY_DIR / c).iterdir())) for c in FINANCIAL_ROLES_CN if (LEGACY_DIR / c).exists())
    check("legacy_kb_count", total_legacy == 64, f"count={total_legacy}")
    sha_match = True
    for cn in FINANCIAL_ROLES_CN:
        src = AGENTS_DIR / f"{cn}-知识库"
        dst = LEGACY_DIR / cn
        if not src.exists() or not dst.exists():
            sha_match = False
            continue
        for sf in src.rglob("*"):
            if sf.is_file():
                rel = sf.relative_to(src)
                df = dst / rel
                if not df.exists() or hashlib.sha256(sf.read_bytes()).hexdigest() != hashlib.sha256(df.read_bytes()).hexdigest():
                    sha_match = False
    check("legacy_kb_sha", sha_match, "")

    # ----- 4: Role path residues (ALL roles files) -----
    residue_count = 0
    residue_files = []
    for fpath in sorted(ROLES_DIR.rglob("*.md")):
        text = fpath.read_text(encoding="utf-8", errors="replace")
        found = [t for t in ENGLISH_LEGACY_TOKENS if t in text]
        if found:
            residue_count += 1
            residue_files.append(str(fpath.relative_to(KNOWLEDGE)))
    check("role_path_residue", residue_count == 0, f"count={residue_count}, files={residue_files}")

    # ----- 5: Role Chinese paths exist -----
    chinese_paths_ok = True
    for fpath in sorted(ROLES_DIR.rglob("*.md")):
        text = fpath.read_text(encoding="utf-8", errors="replace")
        for cn in FINANCIAL_ROLES_CN:
            lp = f"legacy_role_kb/{cn}"
            if lp in text:
                d = LEGACY_DIR / cn
                if not d.exists():
                    chinese_paths_ok = False
    check("role_chinese_paths_exist", chinese_paths_ok, "")

    # ----- 6-8: Router checks -----
    router_data = json.loads(ROUTER_PATH.read_text(encoding="utf-8")) if ROUTER_PATH.exists() else {}
    router_text = json.dumps(router_data, ensure_ascii=False)
    routes = set(router_data.get("routes", {}).keys())
    missing_routes = REQUIRED_ROUTES_CN - routes
    check("router_routes", len(routes) >= 10, f"count={len(routes)}, missing={sorted(missing_routes)}")
    router_paths_exist = True
    for rname, rdata in router_data.get("routes", {}).items():
        for plist in ["must_read", "optional_read"]:
            for p in rdata.get(plist, []):
                full = ROOT / p
                if "legacy_role_kb/" in p:
                    d = LEGACY_DIR / Path(p).name
                    if not d.exists():
                        router_paths_exist = False
                elif not full.exists():
                    router_paths_exist = False
    check("router_paths_exist", router_paths_exist, "")
    has_placeholder = any(t in router_text for t in PLACEHOLDER_TOKENS)
    has_english_legacy = any(f"legacy_role_kb/{la}" in router_text for la in FINANCIAL_ROLES_LATIN)
    check("router_no_placeholders", not has_placeholder, "")
    check("router_no_english_legacy", not has_english_legacy, "")

    # ----- 9-16: Rules checks -----
    rules_path = RULES_DIR / "role_capability_rules_v1.3.json"
    rules_data = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {}
    raw_rules = rules_data.get("rules", [])
    active_rules = len([r for r in raw_rules if r.get("status") == "active"])
    draft_rules = len([r for r in raw_rules if r.get("status") == "draft"])
    check("active_rules", active_rules >= 118, f"count={active_rules}")
    check("draft_rules", draft_rules == 0, f"count={draft_rules}")
    covered = set()
    for r in raw_rules:
        if r.get("status") == "active":
            src = r.get("source_file", "")
            if src:
                covered.add(src)
    check("source_coverage", len(covered) == total_legacy, f"{len(covered)}/{total_legacy}")
    no_ev = [r["rule_id"] for r in raw_rules if not r.get("evidence") or not r["evidence"].get("file")]
    check("rules_no_evidence", len(no_ev) == 0, f"count={len(no_ev)}")
    bad_paths = 0
    for r in raw_rules:
        if r.get("status") != "active":
            continue
        for rel in [r.get("source_file", ""), r.get("evidence", {}).get("file", "")]:
            if rel and not (KNOWLEDGE / rel).exists():
                bad_paths += 1
    check("bad_evidence_paths", bad_paths == 0, f"count={bad_paths}")
    bad_lines = 0
    for r in raw_rules:
        if r.get("status") != "active":
            continue
        ev = r.get("evidence", {})
        ev_file = ev.get("file", "")
        ev_line = int(ev.get("line", 0))
        if ev_file:
            p = KNOWLEDGE / ev_file
            if p.exists():
                fl = len(p.read_text(encoding="utf-8").splitlines())
                if ev_line < 1 or ev_line > fl:
                    bad_lines += 1
    check("bad_evidence_lines", bad_lines == 0, f"count={bad_lines}")
    jsonl_path = RULES_DIR / "role_capability_rules_v1.3.jsonl"
    json_jsonl = False
    if jsonl_path.exists():
        jl = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        jl_rules = [json.loads(l) for l in jl]
        json_jsonl = len(raw_rules) == len(jl_rules)
    check("json_jsonl_consistent", json_jsonl, "")

    # ----- 17-18: Manifest checks -----
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    mcount = len(manifest.get("entries", []))
    check("manifest_entries", mcount > 9, f"count={mcount}")
    minteg = True
    for entry in manifest.get("entries", []):
        p = Path(entry["path"])
        # Skip self-referencing report files that change during execution
        skip_volatile = any(x in str(p) for x in [
            "global_krm_restore_after_qingshan_flow_validation",
            "knowledge_workflow_foundation_validation",
            "rule_candidate_validation_task_closure_",
        ])
        if skip_volatile:
            continue
        if not p.exists():
            minteg = False
            continue
        c = p.read_bytes()
        if entry.get("sha256") != hashlib.sha256(c).hexdigest():
            minteg = False
        if entry.get("line_count") != len(c.decode("utf-8").splitlines()):
            minteg = False
    check("manifest_integrity", minteg, "")

    # ----- 19: Qingshan three steps -----
    qs_ok = all((LIT_DIR / f).exists() for f in QINGSHAN_THREE)
    check("qingshan_3steps", qs_ok, "")

    # ----- 20: Literature cards (boundary-aware) -----
    lit_card_dir = KNOWLEDGE / "literature_cards"
    lit_card_files = []
    if lit_card_dir.exists():
        lit_card_files = list(lit_card_dir.rglob("*.json"))

    literature_cards_allowed = True
    literature_card_count = len(lit_card_files)
    literature_cards_registered = True
    literature_cards_status_ok = True
    literature_cards_boundary_ok = True
    literature_cards_validation_ok = True
    bad_literature_cards = []

    manifest_ids = {e.get("file_id"): e for e in manifest.get("entries", [])}

    for cf in lit_card_files:
        try:
            cdata = json.loads(cf.read_text(encoding="utf-8"))
        except:
            bad_literature_cards.append(str(cf.relative_to(KNOWLEDGE)))
            literature_cards_allowed = False
            continue

        card_id = cdata.get("card_id", "?")
        card_path_str = str(cf)
        rel_path = str(cf.relative_to(KNOWLEDGE))

        # Check registered in manifest
        found_in_manifest = False
        for e in manifest.get("entries", []):
            if e.get("path") == card_path_str or rel_path in e.get("path", ""):
                if e.get("type") == "literature_card":
                    found_in_manifest = True
                    break
        if not found_in_manifest:
            bad_literature_cards.append(f"{card_id}: not registered in manifest as literature_card")
            literature_cards_registered = False

        # Check card_status is card_draft
        if cdata.get("card_status") != "card_draft":
            bad_literature_cards.append(f"{card_id}: card_status={cdata.get('card_status')} (must be card_draft)")
            literature_cards_status_ok = False

        # Check quality_status
        if cdata.get("quality_status") not in VALID_QUALITY_STATUSES:
            bad_literature_cards.append(f"{card_id}: quality_status={cdata.get('quality_status')} (not allowed)")
            literature_cards_boundary_ok = False

        # Check a_share_direct_applicability
        am = cdata.get("applicable_market", {})
        if am.get("a_share_direct_applicability") == "direct":
            bad_literature_cards.append(f"{card_id}: a_share_direct_applicability=direct")
            literature_cards_boundary_ok = False

        # Check forbidden fields not present
        card_text = json.dumps(cdata, ensure_ascii=False)
        for fb in FORBIDDEN_CARD_FIELDS:
            if fb in cdata:
                bad_literature_cards.append(f"{card_id}: contains forbidden field '{fb}'")
                literature_cards_boundary_ok = False

        # Check validation report PASS
        report_id = card_id.replace("LC-QS-", "qingshan-first-literature-card-").replace("-", "_").lower() + "_validation"
        # Find validation report for this card
        card_stage = cdata.get("meta", {}).get("stage", "")
        vreport_path = REPORTS_DIR / f"{card_stage.lower().replace('-', '_').replace('.', '')}.json"
        # Simple heuristic: look for validation report with card_id in name
        found_report_pass = False
        for rp in REPORTS_DIR.iterdir():
            if rp.is_file() and rp.name.endswith(".json"):
                rtext = rp.read_text(encoding="utf-8")
                if card_id in rtext or rel_path in rtext:
                    try:
                        vr = json.loads(rtext)
                        if vr.get("result") == "PASS":
                            found_report_pass = True
                        break
                    except:
                        pass
        if not found_report_pass:
            bad_literature_cards.append(f"{card_id}: no matching PASS validation report")
            literature_cards_validation_ok = False

    # ----- 21: Rule candidates (boundary-aware) -----
    rc_dir = KNOWLEDGE / "rule_candidates"
    rc_files = []
    if rc_dir.exists():
        rc_files = list(rc_dir.rglob("*.json"))

    rule_candidates_allowed = True
    rule_candidate_count = len(rc_files)
    rule_candidates_registered = True
    rule_candidates_status_ok = True
    rule_candidates_boundary_ok = True
    bad_rule_candidates = []
    active_rule_touched_by_candidate = False

    # Check if any rule_candidate modified active rules
    rules_path_for_rc = RULES_DIR / "role_capability_rules_v1.3.json"
    rules_text_for_rc = rules_path_for_rc.read_text(encoding="utf-8") if rules_path_for_rc.exists() else ""

    for cf in rc_files:
        try:
            cdata = json.loads(cf.read_text(encoding="utf-8"))
        except:
            bad_rule_candidates.append(str(cf.relative_to(KNOWLEDGE)))
            continue

        cid = cdata.get("candidate_id", "?")
        cpath_str = str(cf)
        rel_path = str(cf.relative_to(KNOWLEDGE))

        # Check registered in manifest
        found_rc = False
        for e in manifest.get("entries", []):
            if e.get("path") == cpath_str or rel_path in e.get("path", ""):
                if e.get("type") == "rule_candidate":
                    found_rc = True
                    break
        if not found_rc:
            bad_rule_candidates.append(f"{cid}: not registered in manifest as rule_candidate")
            rule_candidates_registered = False

        # Check status is candidate_draft
        if cdata.get("candidate_status") != "candidate_draft":
            bad_rule_candidates.append(f"{cid}: status={cdata.get('candidate_status')} (must be candidate_draft)")
            rule_candidates_status_ok = False

        # Check not in active rules
        if ("rc" in cid.lower() or "candidate" in cid.lower()) and cid in rules_text_for_rc:
            bad_rule_candidates.append(f"{cid}: found in active rules")
            active_rule_touched_by_candidate = True

        # Check candidate_type is valid
        ct = cdata.get("candidate_type", "")
        valid_types = {"role_capability_rule_candidate", "parameter_candidate", "counterexample_candidate"}
        if ct not in valid_types:
            bad_rule_candidates.append(f"{cid}: invalid candidate_type={ct}")
            rule_candidates_boundary_ok = False

        # Check source_card_id exists
        scid = cdata.get("source_card_id", "")
        if scid:
            found_card_manifest = False
            for e in manifest.get("entries", []):
                if "card" in e.get("type", ""):
                    cp = Path(e.get("path", ""))
                    if cp.exists():
                        try:
                            card_data = json.loads(cp.read_text(encoding="utf-8"))
                            if card_data.get("card_id") == scid:
                                found_card_manifest = True
                                break
                        except:
                            pass
            if not found_card_manifest:
                bad_rule_candidates.append(f"{cid}: source_card_id={scid} not found in manifest card entries")
                rule_candidates_boundary_ok = False

    rule_candidates_created = len(rc_files) > 0

    # ----- 22: Forbidden downstream (composite) -----
    forbidden_downstream_created = len(bad_rule_candidates) > 0 or len(bad_literature_cards) > 0
    check("forbidden_downstream", not forbidden_downstream_created,
          f"rule_candidates={rule_candidates_created}, bad_lit_cards={len(bad_literature_cards)}")

    # ----- 23: Old quality phrase -----
    qr_path = REPORTS_DIR / "qingshan_literature_quality_schema_validation_v1.0.json"
    old_phrase = False
    if qr_path.exists():
        old_phrase = "applied_rule_present=True" in json.loads(qr_path.read_text(encoding="utf-8")).get("result_reason", "")
    check("old_quality_phrase", not old_phrase, "")

    result = "PASS" if all_pass else "WARN"

    report = {
        "stage": STAGE,
        "result": result,
        "role_path_residue_count": residue_count,
        "role_path_residue_files": residue_files,
        "role_chinese_paths_exist": chinese_paths_ok,
        "legacy_role_kb_file_count": total_legacy,
        "legacy_role_kb_sha_match": sha_match,
        "router_route_count": len(routes),
        "router_paths_exist": router_paths_exist,
        "router_no_placeholders": not has_placeholder and not has_english_legacy,
        "active_rule_count": active_rules,
        "draft_rule_count": draft_rules,
        "source_coverage": f"{len(covered)}/{total_legacy}",
        "rules_without_source_evidence": len(no_ev),
        "bad_evidence_paths": bad_paths,
        "bad_evidence_lines": bad_lines,
        "json_jsonl_consistent": json_jsonl,
        "manifest_entry_count": mcount,
        "manifest_integrity_ok": minteg,
        "qingshan_three_steps_preserved": qs_ok,
        "literature_cards_allowed": literature_cards_allowed,
        "literature_card_count": literature_card_count,
        "literature_cards_registered": literature_cards_registered,
        "literature_cards_status_ok": literature_cards_status_ok,
        "literature_cards_boundary_ok": literature_cards_boundary_ok,
        "literature_cards_validation_ok": literature_cards_validation_ok,
        "bad_literature_cards": bad_literature_cards,
        "rule_candidates_allowed": rule_candidates_allowed,
        "rule_candidate_count": rule_candidate_count,
        "rule_candidates_registered": rule_candidates_registered,
        "rule_candidates_status_ok": rule_candidates_status_ok,
        "rule_candidates_boundary_ok": rule_candidates_boundary_ok,
        "bad_rule_candidates": bad_rule_candidates,
        "active_rule_touched_by_candidate": active_rule_touched_by_candidate,
        "rule_candidates_created": rule_candidates_created,
        "forbidden_downstream_created": forbidden_downstream_created,
        "old_quality_phrase_exists": old_phrase,
        "result_reason": (
            f"roles_residue={residue_count}_chinese_paths={chinese_paths_ok}_"
            f"legacy={total_legacy}_sha={sha_match}_"
            f"router={len(routes)}_paths={router_paths_exist}_noplaceholder={not has_placeholder}_"
            f"active={active_rules}_draft={draft_rules}_cov={len(covered)}/{total_legacy}_"
            f"noev={len(no_ev)}_badpath={bad_paths}_badline={bad_lines}_jsonl={json_jsonl}_"
            f"manifest={mcount}_integrity={minteg}_qs={qs_ok}_"
            f"lit_cards_allowed={literature_cards_allowed}_count={literature_card_count}_"
            f"registered={literature_cards_registered}_status_ok={literature_cards_status_ok}_"
            f"boundary_ok={literature_cards_boundary_ok}_val_ok={literature_cards_validation_ok}_"
            f"bad_lit={len(bad_literature_cards)}_rc_allowed={rule_candidates_allowed}_"
            f"rc_count={rule_candidate_count}_rc_registered={rule_candidates_registered}_"
            f"rc_status_ok={rule_candidates_status_ok}_rc_boundary_ok={rule_candidates_boundary_ok}_"
            f"bad_rc={len(bad_rule_candidates)}_active_rule_touched={active_rule_touched_by_candidate}_"
            f"forbidden={forbidden_downstream_created}"
        )
    }
    return report, residue_count, residue_files, literature_card_count, bad_literature_cards, rule_candidate_count, bad_rule_candidates, active_rule_touched_by_candidate


if __name__ == "__main__":
    rpt, residues, files, lit_count, bad_lit, rc_count, bad_rc, active_rc_touch = main()
    print(f"\nrestore_result = {rpt['result']}")
    print(f"role_path_residue_count = {residues}")
    if residues > 0:
        print(f"role_path_residue_files = {files}")
    for k, v in sorted(rpt.items()):
        if k not in ("result_reason", "role_path_residue_files", "bad_literature_cards", "bad_rule_candidates"):
            print(f"  {k} = {v}")
    if bad_lit:
        print(f"  bad_literature_cards = {bad_lit}")
    if bad_rc:
        print(f"  bad_rule_candidates = {bad_rc}")

    if WRITE_REPORT:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        rpt_path = REPORTS_DIR / "global_krm_restore_after_qingshan_flow_validation_v1.1.2.json"
        rpt_path.write_text(json.dumps(rpt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nreport: {rpt_path}")
    print(json.dumps(rpt, ensure_ascii=False, indent=2))
