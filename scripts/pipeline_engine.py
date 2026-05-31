#!/usr/bin/env python3
"""
pipeline_engine.py — 流程状态机引擎 (fix3)

用法:
  python3 scripts/pipeline_engine.py --start <event> --task "<desc>" [P0参数...]
  python3 scripts/pipeline_engine.py --status [--run-id <id>] [--all]
  python3 scripts/pipeline_engine.py --advance <run_id> --actor <操作者> --role <角色> [--checklist <path>]
  python3 scripts/pipeline_engine.py --complete <run_id> --actor <操作者> --role <角色> [--audit-report <path>]
  python3 scripts/pipeline_engine.py --block <run_id> --reason "<原因>"
  python3 scripts/pipeline_engine.py --validate <checklist_path> [--run-id <id>]

P0启动必填: --incident-id --p0-reason --impact-scope --risk-level --temp-fix
              --rollback-point --post-audit-deadline [--user-confirmed-p0]
"""
import sys, json, os, hashlib, argparse
from datetime import datetime, timezone, timedelta

try:
    import yaml
except ImportError:
    yaml = None

from log_utils import (
    append_log, checklist_content_hash, hmac_verify, sha256_file,
    compute_state_hash, detect_financial_impact, has_l1_or_l2,
    ACTOR_TO_ALLOWED_ROLES, VALID_ACTORS, VALID_ROLES, RISK_LEVELS,
    FINANCIAL_PATH_KEYWORDS, FINANCIAL_DESC_KEYWORDS,
    DISPATCHER_ALLOWED_ACTIONS,
)

STATE_FILE = os.environ.get("PIPELINE_STATE_FILE", ".claude/pipeline_active.json")
EVENT_RULES_FILE = "events/event_rules.yaml"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P0_EXCLUDED_KEYWORDS = ["普通优化", "样式调整", "非阻断性bug", "实验性功能", "性能微调"]


# ---------------------------------------------------------------------------
# YAML
# ---------------------------------------------------------------------------
def parse_event_rules(filepath):
    if yaml is not None:
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    result = {"events": [], "domains": {}, "domain_keywords": {}}
    current_section = current_event = None
    in_kw = False
    for raw_line in content.split('\n'):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if indent == 0 and stripped.endswith(':') and not stripped.startswith('-'):
            current_section = stripped[:-1]
            continue
        if current_section == "events":
            if stripped.startswith("- name:"):
                current_event = {"name": stripped.split(":", 1)[1].strip()}
                result["events"].append(current_event)
            elif current_event:
                if ':' in stripped:
                    k, _, v = stripped.partition(':')
                    k, v = k.strip(), v.strip()
                    if k == "keywords":
                        current_event[k] = []
                        in_kw = True
                        if v.startswith("[") and v.endswith("]"):
                            current_event[k] = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
                            in_kw = False
                    elif k in ("flow_template", "starter", "description"):
                        current_event[k] = v
                elif stripped.startswith('- ') and in_kw:
                    current_event.setdefault("keywords", []).append(stripped[2:].strip().strip('"').strip("'"))
        if current_section in ("domains", "domain_keywords"):
            if ':' in stripped:
                k, _, v = stripped.partition(':')
                k, v = k.strip(), v.strip()
                if v.startswith("[") and v.endswith("]"):
                    result[current_section][k] = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
    return result


# ---------------------------------------------------------------------------
# 状态 I/O
# ---------------------------------------------------------------------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"runs": {}, "state_hash": ""}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {"runs": {}, "state_hash": ""}
    if "runs" not in data:
        data["runs"] = {}
    stored = data.get("state_hash", "")
    if stored and compute_state_hash(data["runs"]) != stored:
        print("错误: 状态文件完整性检查失败。拒绝操作。")
        sys.exit(1)
    return data


def save_state(data):
    data["state_hash"] = compute_state_hash(data["runs"])
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_flow_template(path):
    fp = os.path.join(PROJECT_ROOT, path)
    if not os.path.exists(fp):
        # 尝试从 event_rules 推断正确路径
        # path 可能是 event name (如 "NEW_REQUIREMENT") 或 flow_type (如 "P0_EMERGENCY")
        rules_path = os.path.join(PROJECT_ROOT, EVENT_RULES_FILE)
        if os.path.exists(rules_path):
            rules = parse_event_rules(rules_path)
            for evt in rules.get("events", []):
                evt_name = evt.get("name", "")
                evt_ft = evt.get("flow_template", "")
                if path in (evt_name, evt_ft):
                    fp = os.path.join(PROJECT_ROOT, evt_ft)
                    break
                # Also try loading template to check flow_type
                candidate = os.path.join(PROJECT_ROOT, evt_ft)
                if os.path.exists(candidate):
                    try:
                        with open(candidate, 'r', encoding='utf-8') as f:
                            tmpl = json.load(f)
                        if tmpl.get("flow_type") == path:
                            fp = candidate
                            break
                    except Exception:
                        pass
    if not os.path.exists(fp):
        print(f"错误: 模板不存在: {path}")
        sys.exit(1)
    with open(fp, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def gen_run_id(ft, task):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"RUN-{ts}-{hashlib.sha256(f'{ft}|{task}|{ts}'.encode()).hexdigest()[:6]}"


def get_stage_roles(ft, sn):
    for s in ft.get("stages", []):
        if s.get("stage") == sn:
            r = s.get("roles")
            if r:
                return r if isinstance(r, list) else [r]
            r = s.get("role")
            return [r] if r else []
    return []


def get_stage_idx(ft, sn):
    for i, s in enumerate(ft.get("stages", [])):
        if s.get("stage") == sn:
            return i
    return -1


def check_actor_role(actor, role, action="advance"):
    """验证 actor→role 映射。阿黑只能做调度动作。返回 (ok, err)"""
    if actor not in VALID_ACTORS:
        return False, f"非法 actor: {actor}"
    allowed = ACTOR_TO_ALLOWED_ROLES.get(actor, [])
    if role not in allowed:
        return False, f"actor '{actor}' 无权扮演 role '{role}'"
    if actor == "阿黑" and action not in DISPATCHER_ALLOWED_ACTIONS:
        return False, f"阿黑不得执行 '{action}' 动作（仅限: {DISPATCHER_ALLOWED_ACTIONS}）"
    return True, ""


def parse_iso_datetime(s):
    """解析 ISO datetime，拒绝 naive（无时区）"""
    if not s:
        return None, "空值"
    # 必须有时区标识
    has_tz = False
    for tz_mark in ('+', 'Z', 'z'):
        if tz_mark in s.replace('T', ' ')[-6:]:
            has_tz = True
            break
    if not has_tz and s.count('-') == 2 and 'T' in s and s.count(':') >= 2:
        return None, f"naive datetime 不允许（缺少时区）: {s}。请使用 +00:00 或 Z 后缀"
    try:
        # Replace Z with +00:00 for fromisoformat compatibility
        normalized = s
        if s.endswith('Z') or s.endswith('z'):
            normalized = s[:-1] + '+00:00'
        return datetime.fromisoformat(normalized), None
    except (ValueError, TypeError) as e:
        return None, f"datetime 格式非法: {s} ({e})"


def recompute_financial_from_checklist(run):
    """从 checklist 实时重算 financial_impact。None 时 fail closed"""
    cl_path = run.get("checklist_path")
    if not cl_path or not os.path.exists(cl_path):
        return None  # fail closed
    try:
        with open(cl_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    items = data.get("items", [])
    fb = data.get("file_budgets", [])
    td = run.get("task_description", "")
    return detect_financial_impact(items, fb, td)


def has_financial_bypass(run, items):
    """BUGFIX: 检查是否存在金融关键词但可能绕过consult"""
    fi = run.get("financial_impact")
    if fi is None:
        fi = detect_financial_impact(items, run.get("file_budgets", []), run.get("task_description", ""))
    has_l = has_l1_or_l2(items)
    return (fi and not has_l) or has_l


def validate_stage_signatures(checklist_path, required_roles, run_id, expected_stage, actor):
    """HMAC 签名验证。返回 (ok, errors)"""
    if not required_roles:
        return True, []
    if not checklist_path or not os.path.exists(checklist_path):
        return False, ["未注册 checklist"]
    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"checklist 格式非法: {e}"]
    signoffs = data.get("signoffs", {})
    errors = []
    for role in required_roles:
        sig = signoffs.get(role, {})
        ok, err = hmac_verify(sig, sig.get("actor", ""), role, run_id, expected_stage, checklist_path)
        if not ok:
            errors.append(f"{role}: {err}")
            continue
        # 阿黑签名不能用于业务阶段
        if sig.get("actor") == "阿黑":
            errors.append(f"{role}: 签名actor为阿黑，阿黑不得对业务阶段产生有效签名")
    return len(errors) == 0, errors


def check_overdue_p0():
    state = load_state()
    overdue = []
    now = datetime.now(timezone.utc)
    for rid, r in state.get("runs", {}).items():
        if r.get("flow_type") != "P0_EMERGENCY" or r.get("status") == "completed":
            continue
        dl = r.get("post_audit_deadline", "")
        if not dl:
            continue
        dt, _ = parse_iso_datetime(dl)
        if dt and now > dt:
            pa_done = any(s.get("stage") == "post_audit" and s.get("status") == "completed" for s in r.get("stages", []))
            if not pa_done:
                overdue.append(rid)
    return overdue


def load_p0_rules():
    tp = os.path.join(PROJECT_ROOT, "templates", "flow_p0.json")
    if not os.path.exists(tp):
        return {"allowed_reasons": [], "excluded": []}
    with open(tp, 'r', encoding='utf-8') as f:
        d = json.load(f)
    e = d.get("p0_eligibility", {})
    return {"allowed_reasons": e.get("allowed_reasons", []), "excluded": e.get("excluded", [])}


def validate_p0_fields(args):
    errors, p0d = [], {}
    for field, label in [
        ("incident_id", "incident_id"), ("p0_reason", "触发原因"),
        ("impact_scope", "影响范围"), ("risk_level", "风险等级"),
        ("temp_fix", "临时处置方案"), ("rollback_point", "回滚点"),
        ("post_audit_deadline", "post_audit_deadline"),
    ]:
        val = getattr(args, field.replace('-', '_'), None)
        if not val:
            errors.append(f"P0 必填字段缺失: {label} (--{field})")
        p0d[field] = val
    if errors:
        return False, errors, None
    if args.risk_level not in RISK_LEVELS:
        errors.append(f"risk_level 必须是 {RISK_LEVELS}，收到: {args.risk_level}")
    dt, dt_err = parse_iso_datetime(args.post_audit_deadline)
    if dt_err:
        errors.append(dt_err)
    elif dt:
        now = datetime.now(timezone.utc)
        if dt > now + timedelta(hours=48):
            errors.append(f"post_audit_deadline 不得超过创建时间+48h")
    if not errors:
        p0_rules = load_p0_rules()
        allowed = p0_rules.get("allowed_reasons", [])
        excluded = p0_rules.get("excluded", [])
        is_excl = any(kw in (args.p0_reason or "") for kw in excluded) or \
                  any(kw in (args.task or "") for kw in excluded)
        if is_excl and not args.user_confirmed_p0:
            errors.append(f"P0原因/任务命中排除词({excluded})，需 --user-confirmed-p0 true")
        elif args.p0_reason not in allowed and not args.user_confirmed_p0:
            errors.append(f"P0原因不在允许列表({allowed})，需 --user-confirmed-p0 true")
    return len(errors) == 0, errors, p0d


# ---------------------------------------------------------------------------
# --start
# ---------------------------------------------------------------------------
def cmd_start(args):
    et = args.start
    td = args.task
    p0d = None
    if et == "EMERGENCY":
        ok, errs, p0d = validate_p0_fields(args)
        if not ok:
            print("错误: P0 启动条件不满足:")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)
    if et in ("NEW_REQUIREMENT", "FIX"):
        overdue = check_overdue_p0()
        if overdue:
            print(f"错误: 存在超期未完成审计的 P0，禁止启动非P0发布: {overdue}")
            sys.exit(1)
    rules_path = os.path.join(PROJECT_ROOT, EVENT_RULES_FILE)
    rules = parse_event_rules(rules_path)
    matched = next((e for e in rules.get("events", []) if e.get("name") == et), None)
    if not matched:
        print(f"错误: 未知事件类型 '{et}'")
        sys.exit(1)
    ft = load_flow_template(matched["flow_template"])
    stages = ft.get("stages", [])
    if not stages:
        print("错误: 流程模板无阶段")
        sys.exit(1)
    rid = gen_run_id(ft.get("flow_type", et), td)
    now = datetime.now(timezone.utc).isoformat()
    ss = [{"stage": s.get("stage"), "status": "pending", "started_at": None, "completed_at": None} for s in stages]
    ss[0]["status"], ss[0]["started_at"] = "in_progress", now
    run = {
        "run_id": rid, "flow_type": ft.get("flow_type", et),
        "flow_template": matched["flow_template"],
        "task_description": td, "current_stage": stages[0]["stage"],
        "checklist_path": None, "stages": ss,
        "created_at": now, "updated_at": now,
        "blocked": False, "block_reason": None, "override_reason": None,
        "financial_impact": None, "status": "active",
        "incident_id": None, "p0_reason": None, "impact_scope": None,
        "risk_level": None, "temp_fix": None, "rollback_point": None,
        "post_audit_deadline": None, "user_confirmed_p0": False,
        "audit_report_hash": None,
    }
    if p0d:
        for k, v in p0d.items():
            run[k] = v
        run["user_confirmed_p0"] = args.user_confirmed_p0
        if args.user_confirmed_p0:
            run["override_reason"] = "用户明确指定P0"
    state = load_state()
    state.setdefault("runs", {})[rid] = run
    save_state(state)
    append_log("engine", {"run_id": rid, "event_type": "start", "from_stage": None,
               "to_stage": stages[0]["stage"], "target_role": stages[0].get("role", ""),
               "package_files": [], "override_reason": run.get("override_reason") or ""})
    print(f"✓ 流程已创建\n  run_id: {rid}\n  事件: {et}\n  阶段: {stages[0]['stage']}\n  任务: {td}")
    if p0d:
        print(f"  incident_id: {p0d['incident_id']}")
    return rid


# ---------------------------------------------------------------------------
# --status
# ---------------------------------------------------------------------------
def cmd_status(run_id=None, show_all=False):
    state = load_state()
    filtered = {rid: r for rid, r in state.get("runs", {}).items()
                if show_all or r.get("status") != "completed"}
    if run_id:
        if run_id not in state.get("runs", {}):
            print(f"错误: run_id 不存在: {run_id}")
            sys.exit(1)
        filtered = {run_id: state["runs"][run_id]}
    if not filtered:
        print("暂无活跃流程。")
        return
    print(f"\n{'='*60}\n流程状态 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n{'='*60}")
    for rid, r in filtered.items():
        icon = "✓" if r.get("status") == "completed" else ("⏸" if r.get("blocked") else "▶")
        print(f"\n{icon} {rid} ({r.get('flow_type')})")
        print(f"  任务: {r.get('task_description','')}")
        print(f"  阶段: {r.get('current_stage')}  checklist: {r.get('checklist_path') or '未注册'}")
        marks = {"completed": "✓", "in_progress": "●", "blocked": "✗", "skipped": "⏭"}
        ss = " → ".join(f"{marks.get(s['status'],'○')}{s['stage']}" for s in r.get("stages", []))
        print(f"  {ss}")
    print(f"\n{'='*60}\n共 {len(filtered)} 个流程")


# ---------------------------------------------------------------------------
# --advance (含 actor/role 校验)
# ---------------------------------------------------------------------------
def cmd_advance(args):
    rid, actor, role = args.advance, args.actor, args.role
    cl_path = args.checklist

    # actor/role 校验
    ok, err = check_actor_role(actor, role, "advance")
    if not ok:
        print(f"错误: {err}")
        append_log("security", {"run_id": rid, "actor": actor, "action": "advance",
                   "target": role, "result": "DENIED", "detail": err})
        sys.exit(1)

    state = load_state()
    run = state["runs"].get(rid)
    if not run:
        print(f"错误: run_id 不存在: {rid}")
        sys.exit(1)
    if run.get("blocked"):
        print(f"错误: 流程已阻断: {run.get('block_reason')}")
        sys.exit(1)
    if run.get("status") == "completed":
        print("错误: 流程已完成")
        sys.exit(1)

    ft = load_flow_template(run["flow_template"])
    cur = run["current_stage"]
    sidx = get_stage_idx(ft, cur)
    if sidx < 0:
        print(f"错误: 阶段 '{cur}' 不在模板中")
        sys.exit(1)
    stages = ft.get("stages", [])
    cdef = stages[sidx]
    req_roles = get_stage_roles(ft, cur)

    # 角色必须在阶段角色列表中
    if req_roles and role not in req_roles:
        print(f"错误: role '{role}' 无权推进阶段 '{cur}'。允许: {req_roles}")
        sys.exit(1)

    cpath = cl_path or run.get("checklist_path")

    # BUGFIX: 实时重算 financial_impact
    if run["flow_type"] == "BUGFIX":
        live_fi = recompute_financial_from_checklist(run)
        if live_fi is None:
            print("错误: 无法从 checklist 计算 financial_impact（fail closed）。请先执行 --validate")
            sys.exit(1)
        run["financial_impact"] = live_fi
        # 检查 checklist items 中的 code_level
        if cpath and os.path.exists(cpath):
            try:
                with open(cpath) as f:
                    cdata = json.load(f)
                items = cdata.get("items", [])
                if has_l1_or_l2(items):
                    run["financial_impact"] = True
            except Exception:
                pass

    # P0 decide 特殊
    if run["flow_type"] == "P0_EMERGENCY" and cur == "decide":
        p0_ok, p0_errs = True, []
        for fld, lbl in [("incident_id","incident_id"),("p0_reason","触发原因"),
                          ("impact_scope","影响范围"),("risk_level","风险等级"),
                          ("temp_fix","临时处置"),("rollback_point","回滚点"),
                          ("post_audit_deadline","审计截止")]:
            if not run.get(fld):
                p0_errs.append(f"缺失: {lbl}")
                p0_ok = False
        if not p0_ok:
            print(f"错误: P0 decide 阶段必填信息不完整:")
            for e in p0_errs:
                print(f"  - {e}")
            sys.exit(1)
    elif req_roles:
        ok_sig, errs = validate_stage_signatures(cpath, req_roles, rid, cur, actor)
        if not ok_sig:
            print(f"错误: 阶段 '{cur}' 签名验证失败:")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)

    # 确定下一阶段
    nidx = sidx + 1
    # BUGFIX consult 条件
    if run["flow_type"] == "BUGFIX" and nidx < len(stages) and stages[nidx].get("stage") == "consult":
        c_def = stages[nidx]
        if not c_def.get("mandatory", True) and c_def.get("condition"):
            fi = run.get("financial_impact")
            has_l = False
            if cpath and os.path.exists(cpath):
                try:
                    with open(cpath) as f:
                        cd = json.load(f)
                    has_l = has_l1_or_l2(cd.get("items", []))
                except Exception:
                    pass
            # 金融关键词→必须consult；L1/L2→必须consult；fi is None→fail closed→必须consult
            if not fi and not has_l and fi is not None:
                for s in run["stages"]:
                    if s["stage"] == stages[nidx]["stage"]:
                        s["status"] = "skipped"
                nidx += 1
                append_log("engine", {"run_id": rid, "event_type": "skip", "from_stage": cur,
                           "to_stage": stages[nidx-1]["stage"], "target_role": "",
                           "package_files": [], "override_reason": "非金融BUGFIX，跳过consult"})

    if nidx >= len(stages):
        print(f"'{cur}' 是最后阶段，请使用 --complete")
        sys.exit(1)

    nxt = stages[nidx]
    now = datetime.now(timezone.utc).isoformat()
    for s in run["stages"]:
        if s["stage"] == cur:
            s["status"], s["completed_at"] = "completed", now
        if s["stage"] == nxt["stage"]:
            s["status"], s["started_at"] = "in_progress", now
    run["current_stage"] = nxt["stage"]
    run["updated_at"] = now
    if cl_path and not run.get("checklist_path"):
        run["checklist_path"] = os.path.abspath(cl_path)
    save_state(state)
    append_log("engine", {"run_id": rid, "event_type": "advance", "from_stage": cur,
               "to_stage": nxt["stage"], "target_role": nxt.get("role", ""),
               "package_files": [cpath] if cpath else [], "override_reason": run.get("override_reason","")})
    print(f"✓ 已推进 {cur} → {nxt['stage']}\n  角色: {nxt.get('role') or nxt.get('roles')}")


# ---------------------------------------------------------------------------
# --complete (含 P0 audit-report 强制)
# ---------------------------------------------------------------------------
def cmd_complete(args):
    rid, actor, role = args.complete, args.actor, args.role
    ar_path = args.audit_report

    ok, err = check_actor_role(actor, role, "complete")
    if not ok:
        print(f"错误: {err}")
        sys.exit(1)

    state = load_state()
    run = state["runs"].get(rid)
    if not run:
        print(f"错误: run_id 不存在: {rid}")
        sys.exit(1)
    if run.get("blocked"):
        print(f"错误: 流程已阻断")
        sys.exit(1)
    if run.get("status") == "completed":
        print("流程已完成")
        sys.exit(0)

    ft = load_flow_template(run["flow_type"])
    cur = run["current_stage"]
    stages = ft.get("stages", [])
    sidx = get_stage_idx(ft, cur)
    if sidx != len(stages) - 1:
        print(f"错误: '{cur}' 不是最后阶段。剩余: {[s['stage'] for s in stages[sidx+1:]]}")
        sys.exit(1)

    req_roles = get_stage_roles(ft, cur)
    if req_roles and role not in req_roles:
        print(f"错误: role '{role}' 无权完成阶段 '{cur}'。允许: {req_roles}")
        sys.exit(1)

    cpath = run.get("checklist_path")

    # P0 post_audit: 强制要求 --audit-report
    ar_hash = ""
    if run["flow_type"] == "P0_EMERGENCY" and cur == "post_audit":
        if not ar_path:
            print("错误: P0 post_audit 完成需要 --audit-report <路径>")
            sys.exit(1)
        if not os.path.exists(ar_path):
            print(f"错误: 审计报告文件不存在: {ar_path}")
            sys.exit(1)
        ar_hash = sha256_file(ar_path)
        run["audit_report_hash"] = ar_hash

    if req_roles:
        ok_sig, errs = validate_stage_signatures(cpath, req_roles, rid, cur, actor)
        if not ok_sig:
            print(f"错误: 签名验证失败:")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    for s in run["stages"]:
        if s["stage"] == cur:
            s["status"], s["completed_at"] = "completed", now
    run["status"] = "completed"
    run["updated_at"] = now
    save_state(state)
    append_log("engine", {"run_id": rid, "event_type": "complete", "from_stage": cur,
               "to_stage": None, "target_role": role, "package_files": [cpath] if cpath else [],
               "override_reason": ""})
    print(f"✓ 流程已完成\n  run_id: {rid}\n  最终阶段: {cur}")


# ---------------------------------------------------------------------------
# --block / --validate
# ---------------------------------------------------------------------------
def cmd_block(args):
    rid, reason = args.block, args.reason
    state = load_state()
    if rid not in state.get("runs", {}):
        print(f"错误: run_id 不存在: {rid}")
        sys.exit(1)
    run = state["runs"][rid]
    run["blocked"], run["block_reason"] = True, reason
    run["updated_at"] = datetime.now(timezone.utc).isoformat()
    for s in run["stages"]:
        if s["stage"] == run["current_stage"]:
            s["status"] = "blocked"
    save_state(state)
    append_log("engine", {"run_id": rid, "event_type": "block", "from_stage": run["current_stage"],
               "to_stage": run["current_stage"], "target_role": "", "package_files": [],
               "override_reason": reason})
    print(f"✓ 已阻断 {rid}: {reason}")


def cmd_validate(args):
    cl_path = args.validate
    if not os.path.exists(cl_path):
        print(f"FAIL: 文件不存在: {cl_path}")
        sys.exit(1)
    try:
        with open(cl_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL: JSON非法: {e}")
        sys.exit(1)
    c_rid = data.get("run_id", "UNKNOWN")
    eff_rid = args.run_id or c_rid
    errors = []
    for fld in ["run_id", "items"]:
        if fld not in data:
            errors.append(f"Missing: {fld}")
    for item in data.get("items", []):
        for f in ["id", "description", "code_level"]:
            if f not in item:
                errors.append(f"Item {item.get('id','?')} missing {f}")
    for fb in data.get("file_budgets", []):
        if fb.get("max_lines", 0) > 500:
            errors.append(f"File budget {fb.get('path','?')} >500 lines")
    state = load_state()
    td = state.get("runs", {}).get(eff_rid, {}).get("task_description", "")
    fi = detect_financial_impact(data.get("items", []), data.get("file_budgets", []), td)
    if eff_rid in state.get("runs", {}):
        run = state["runs"][eff_rid]
        run["checklist_path"] = os.path.abspath(cl_path)
        run["financial_impact"] = fi
        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
    if errors:
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("PASS: 清单校验通过")
    if fi:
        print("  ⚠ 检测到金融影响")
        if has_l1_or_l2(data.get("items", [])):
            print("  ⚠ L1/L2变更，需五角色咨询")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="铁律量化 - 流程状态机 (fix3)")
    p.add_argument("--start", metavar="EVENT"); p.add_argument("--task", metavar="DESC")
    p.add_argument("--status", action="store_true"); p.add_argument("--all", action="store_true")
    p.add_argument("--run-id"); p.add_argument("--advance", metavar="RUN_ID")
    p.add_argument("--complete", metavar="RUN_ID"); p.add_argument("--actor"); p.add_argument("--role")
    p.add_argument("--checklist"); p.add_argument("--audit-report")
    p.add_argument("--block", metavar="RUN_ID"); p.add_argument("--reason")
    p.add_argument("--validate", metavar="PATH")
    # P0
    p.add_argument("--incident-id"); p.add_argument("--p0-reason"); p.add_argument("--impact-scope")
    p.add_argument("--risk-level"); p.add_argument("--temp-fix"); p.add_argument("--rollback-point")
    p.add_argument("--post-audit-deadline"); p.add_argument("--user-confirmed-p0", type=lambda x: x.lower()=="true", default=False)
    args = p.parse_args()

    if args.start:
        if not args.task:
            print("错误: --start 需要 --task"); sys.exit(1)
        cmd_start(args)
    elif args.status:
        cmd_status(args.run_id, args.all)
    elif args.advance:
        if not args.actor or not args.role:
            print("错误: --advance 需要 --actor 和 --role"); sys.exit(1)
        cmd_advance(args)
    elif args.complete:
        if not args.actor or not args.role:
            print("错误: --complete 需要 --actor 和 --role"); sys.exit(1)
        cmd_complete(args)
    elif args.block:
        if not args.reason:
            print("错误: --block 需要 --reason"); sys.exit(1)
        cmd_block(args)
    elif args.validate:
        cmd_validate(args)
    else:
        p.print_help(); sys.exit(1)


if __name__ == "__main__":
    main()
