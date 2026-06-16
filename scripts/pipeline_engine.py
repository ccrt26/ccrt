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
import sys, json, os, hashlib, argparse, subprocess
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
    issue_auth_token, verify_auth_token, load_auth_tokens, save_auth_tokens,
    log_auth_token_event, token_canonical_hash,
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


def get_actual_actor():
    """Read actual_actor from non-forgeable context (env var)."""
    for key in ["CLAUDE_CURRENT_ACTOR", "CURRENT_ACTOR"]:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    id_file = os.path.join(PROJECT_ROOT, ".claude", "current_actor")
    if os.path.exists(id_file):
        try:
            with open(id_file, 'r') as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass
    return ""


# Stage → allowed advancement roles (who can push to next stage)
STAGE_ADVANCERS = {
    "design": ["情墨"],
    "review_1a": ["腰子"],
    "consult": ["山猫", "信鸽", "玉夜", "流金", "青山"],
    "review_1b": ["旧影", "新安"],
    "coding": ["红结"],
    "verify": ["新安"],
    "deploy": ["红枫"],
    "deploy_verify": ["旧影"],
    "audit": ["旧影"],
    "post_audit": ["旧影"],
}


def check_actor_role(actor, role, action="advance"):
    """验证 actor→role 映射。阿黑只能做调度动作。返回 (ok, err)"""
    actual = get_actual_actor()
    effective_actor = actual or actor

    # 1. 阿黑在任何情况下不得 advance/complete
    if effective_actor == "阿黑" and action in ("advance", "complete"):
        return False, f"阿黑不得执行 '{action}' 动作"

    # 2. actual_actor 与 CLI actor 不一致
    if actual and actual != actor:
        return False, f"actual_actor({actual}) != requested_actor({actor})。不能代签。"

    # 3. actual_actor != role
    if actual and actual != role:
        return False, f"actual_actor({actual}) != role({role})。不能以他人身份推进。"

    if actor not in VALID_ACTORS:
        return False, f"非法 actor: {actor}"
    allowed = ACTOR_TO_ALLOWED_ROLES.get(effective_actor, [])
    if role not in allowed:
        return False, f"actor '{effective_actor}' 无权扮演 role '{role}'"
    if effective_actor == "阿黑" and action not in DISPATCHER_ALLOWED_ACTIONS:
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
# --start (核心，被 cmd_start 和 cmd_route 共用)
# ---------------------------------------------------------------------------
def cmd_start_internal(event_type, task_description, p0_data=None):
    """核心启动逻辑：查规则→加载模板→创建run→保存状态。"""
    rules_path = os.path.join(PROJECT_ROOT, EVENT_RULES_FILE)
    rules = parse_event_rules(rules_path)
    matched = next((e for e in rules.get("events", []) if e.get("name") == event_type), None)
    if not matched:
        print(f"错误: 未知事件类型 '{event_type}'")
        sys.exit(1)
    ft = load_flow_template(matched["flow_template"])
    stages = ft.get("stages", [])
    if not stages:
        print("错误: 流程模板无阶段")
        sys.exit(1)
    rid = gen_run_id(ft.get("flow_type", event_type), task_description)
    now = datetime.now(timezone.utc).isoformat()
    ss = [{"stage": s.get("stage"), "status": "pending", "started_at": None, "completed_at": None} for s in stages]
    ss[0]["status"], ss[0]["started_at"] = "in_progress", now
    run = {
        "run_id": rid, "flow_type": ft.get("flow_type", event_type),
        "flow_template": matched["flow_template"],
        "task_description": task_description, "current_stage": stages[0]["stage"],
        "checklist_path": None, "stages": ss,
        "created_at": now, "updated_at": now,
        "blocked": False, "block_reason": None, "override_reason": None,
        "financial_impact": None, "status": "active",
        "incident_id": None, "p0_reason": None, "impact_scope": None,
        "risk_level": None, "temp_fix": None, "rollback_point": None,
        "post_audit_deadline": None, "user_confirmed_p0": False,
        "audit_report_hash": None,
    }
    if p0_data:
        for k, v in p0_data.items():
            run[k] = v
        run["user_confirmed_p0"] = p0_data.get("user_confirmed_p0", False)
        if p0_data.get("user_confirmed_p0"):
            run["override_reason"] = "用户明确指定P0"
    state = load_state()
    state.setdefault("runs", {})[rid] = run
    save_state(state)
    actual = get_actual_actor()
    append_log("engine", {"run_id": rid, "event_type": "start", "from_stage": None,
               "to_stage": stages[0]["stage"], "target_role": stages[0].get("role", ""),
               "actor": "阿黑", "role": "阿黑",
               "actual_actor": actual or "阿黑", "actual_role": "阿黑",
               "requested_actor": "", "requested_role": "",
               "decision": "PASS", "reason": "",
               "package_files": [], "override_reason": run.get("override_reason") or ""})
    print(f"✓ 流程已创建\n  run_id: {rid}\n  事件: {event_type}\n  阶段: {stages[0]['stage']}\n  任务: {task_description}")
    if p0_data:
        print(f"  incident_id: {p0_data.get('incident_id')}")
    return rid


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
        if p0d is not None:
            p0d["user_confirmed_p0"] = args.user_confirmed_p0
    if et in ("NEW_REQUIREMENT", "FIX"):
        overdue = check_overdue_p0()
        if overdue:
            print(f"错误: 存在超期未完成审计的 P0，禁止启动非P0发布: {overdue}")
            sys.exit(1)
    return cmd_start_internal(et, td, p0d)


# ---------------------------------------------------------------------------
# --route
# ---------------------------------------------------------------------------
def cmd_route(user_text):
    """从用户自然语言判定事件类型并创建流程。"""
    # 1. 金融关键词 → 拒绝工程流程，转腰子
    financial_kw = ["评分","选股","交易","买入","卖出","仓位","止损","因子","风控",
                    "PE","MACD","RSI","KDJ","资金流","推荐","报告结论"]
    if any(kw in user_text for kw in financial_kw):
        print("[金融线] 含金融关键词，转腰子全团咨询。不启动工程流程。")
        sys.exit(0)

    # 2. PIPELINE_CONTINUE（执行类口令——最高优先级，避免"执行P0"被P0/修复等误匹配）
    #    注意：必须在 EMERGENCY/FIX 之前，因为"执行P0-A"含P0但意图是继续流程而非新紧急
    execute_kw = ["执行","大家执行","按顺序执行","按计划推进","继续推进","开始做","继续流程"]
    if any(kw in user_text for kw in execute_kw):
        print("判定: PIPELINE_CONTINUE — 不启动新流程，请使用 --pcontinue 查询当前 pipeline 状态并路由。")
        sys.exit(0)

    # 3. EMERGENCY → 提示需要完整P0参数
    emergency_kw = ["紧急","P0","立刻","线上挂了","马上"]
    if any(kw in user_text for kw in emergency_kw):
        print("判定: EMERGENCY")
        print("EMERGENCY需要完整P0参数，请使用 --start EMERGENCY 并提供:")
        print("  --incident-id --p0-reason --impact-scope --risk-level")
        print("  --temp-fix --rollback-point --post-audit-deadline")
        sys.exit(0)

    # 3. READONLY_CHECK（优先级高于 FIX/NEW_REQ，避免"检查这个问题"被"问题"误匹配为 FIX）
    readonly_kw = ["检查","查一下","确认","验证","审查","诊断","排查"]
    if any(kw in user_text for kw in readonly_kw):
        print("判定: READONLY_CHECK — 只读检查，不启动流程，不修改文件。")
        sys.exit(0)

    # 4. FIX
    fix_kw = ["修复","bug","修","问题","改","坏了","异常"]
    # 5. NEW_REQUIREMENT
    req_kw = ["新增","新功能","开发","优化","改版","改进","添加","加一个"]

    if any(kw in user_text for kw in fix_kw):
        event = "FIX"
    elif any(kw in user_text for kw in req_kw):
        event = "NEW_REQUIREMENT"
    # 6. USER_REQUEST 兜底
    else:
        event = "NEW_REQUIREMENT"

    # 超期 P0 阻断检查（与 cmd_start 一致）
    if event in ("NEW_REQUIREMENT", "FIX"):
        overdue = check_overdue_p0()
        if overdue:
            print(f"错误: 存在超期未完成审计的 P0 流程，禁止启动非P0发布:")
            for rid in overdue:
                print(f"  - {rid}")
            print("请先完成 P0 post_audit 后再启动新流程。")
            sys.exit(1)

    # 启动流程
    print(f"判定: {event}")
    return cmd_start_internal(event, user_text)


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
# Token 联动失效 (A6)
# ---------------------------------------------------------------------------
def _invalidate_run_tokens(run_id, reason):
    """使指定 run_id 的所有 active token 失效。"""
    store = load_auth_tokens()
    tokens = store.get("tokens", {})
    changed = False
    for tid, t in list(tokens.items()):
        if t.get("run_id") == run_id and t.get("status") == "active":
            t["status"] = "invalidated"
            t["invalidated_reason"] = reason
            log_auth_token_event("invalidate", tid, run_id, t.get("actor",""),
                                 t.get("role",""), "", "", reason)
            changed = True
    if changed:
        save_auth_tokens(store)


# ---------------------------------------------------------------------------
# --issue-auth-token (A3)
# ---------------------------------------------------------------------------
def cmd_issue_auth_token(args):
    """签发工程鉴权 token。coding gate 通过后方可签发。"""
    rid = args.issue_auth_token
    actor = args.actor
    role = args.role

    if not actor or not role:
        print("错误: --issue-auth-token 需要 --actor 和 --role"); sys.exit(1)

    # 仅红结可持有编码 token（P1 门禁）
    ok_ar, err_ar = check_actor_role(actor, role, "advance")
    if not ok_ar:
        print(f"错误: {err_ar}"); sys.exit(1)
    if actor != "红结" or role != "红结":
        print(f"错误: --issue-auth-token 仅限红结，收到 actor={actor} role={role}"); sys.exit(1)

    state = load_state()
    run = state.get("runs", {}).get(rid)
    if not run:
        print(f"错误: run_id 不存在: {rid}"); sys.exit(1)
    if run.get("blocked"):
        print(f"错误: run 已阻断"); sys.exit(1)
    if run.get("status") != "active":
        print(f"错误: run 不活跃"); sys.exit(1)

    # 必须处于 coding 阶段
    if run.get("current_stage") != "coding":
        print(f"错误: 当前阶段={run.get('current_stage')}，仅 coding 阶段可签发 token"); sys.exit(1)

    # 必须通过 coding gate
    ok, failures, _ = check_coding_gate(rid, verbose=False)
    if not ok:
        print(f"错误: coding gate 未通过")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    # 从 checklist file_budgets 取最后写入路径（全量）
    cl_path = run.get("checklist_path", "")
    if not cl_path or not os.path.exists(cl_path):
        print("错误: checklist_path 不存在"); sys.exit(1)
    try:
        with open(cl_path, 'r', encoding='utf-8') as f:
            cl_data = json.load(f)
    except Exception as e:
        print(f"错误: checklist 读取失败: {e}"); sys.exit(1)

    file_budgets = cl_data.get("file_budgets", [])
    allowed_paths = [fb["path"] for fb in file_budgets if fb.get("path")] if file_budgets else []
    # 若 file_budgets 为空，fallback 至 run.files_scope
    if not allowed_paths:
        allowed_paths = run.get("files_scope", [])
    if not allowed_paths:
        print("错误: 无授权路径 (file_budgets/files_scope 均为空)"); sys.exit(1)

    cl_hash = checklist_content_hash(cl_path) if cl_path else ""

    token_id = issue_auth_token(rid, actor, role, allowed_paths,
                                 checklist_path=cl_path, checklist_hash=cl_hash)
    print(f"AUTH_TOKEN={token_id}")
    print(f"expires_at={(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}")
    print(f"allowed_paths={allowed_paths}")
    return token_id


# ---------------------------------------------------------------------------
# --revoke-auth-token (A4)
# ---------------------------------------------------------------------------
def cmd_revoke_auth_token(args):
    """撤销指定 token。"""
    token_id = args.revoke_auth_token
    reason = args.reason or "手动撤销"
    store = load_auth_tokens()
    tokens = store.get("tokens", {})
    token = tokens.get(token_id)
    if not token:
        print(f"错误: token 不存在: {token_id}"); sys.exit(1)
    old_status = token.get("status", "")
    token["status"] = "revoked"
    token["revoked_reason"] = reason
    save_auth_tokens(store)
    log_auth_token_event("revoke", token_id, token.get("run_id",""),
                         token.get("actor",""), token.get("role",""),
                         "", "", f"手动撤销 (原状态: {old_status})")
    print(f"✓ token {token_id} 已撤销 (原状态: {old_status})")


# ---------------------------------------------------------------------------
# --list-auth-tokens (A5)
# ---------------------------------------------------------------------------
def cmd_list_auth_tokens(args):
    """列出 token（可指定 run_id 过滤）。"""
    run_id = args.list_auth_tokens
    store = load_auth_tokens()
    tokens = store.get("tokens", {})
    filtered = {tid: t for tid, t in tokens.items()
                if not run_id or t.get("run_id") == run_id}
    if not filtered:
        print("暂无 token 记录。")
        return
    for tid, t in sorted(filtered.items(), key=lambda x: x[1].get("issued_at", "")):
        print(f"  {tid}")
        print(f"    run_id: {t.get('run_id','?')}  stage: {t.get('stage','?')}")
        print(f"    actor: {t.get('actor','?')}  role: {t.get('role','?')}")
        print(f"    status: {t.get('status','?')}")
        print(f"    issued: {t.get('issued_at','?')}  expires: {t.get('expires_at','?')}")
        print(f"    paths: {t.get('allowed_paths', [])}")
        reason = t.get("revoked_reason", t.get("invalidated_reason", ""))
        if reason:
            print(f"    reason: {reason}")
        print()


# ---------------------------------------------------------------------------
# --advance (含 actor/role 校验 + A6 token 联动)
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

    # 额外检查: role 必须在 STAGE_ADVANCERS 中
    stage_advancers = STAGE_ADVANCERS.get(cur, [])
    if stage_advancers and role not in stage_advancers:
        print(f"错误: role '{role}' 无权推进阶段 '{cur}'。阶段推进者: {stage_advancers}")
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
                actual_skip = get_actual_actor()
                append_log("engine", {"run_id": rid, "event_type": "skip", "from_stage": cur,
                           "to_stage": stages[nidx-1]["stage"], "target_role": "",
                           "actor": actor, "role": role,
                           "actual_actor": actual_skip or actor, "actual_role": actual_skip or role,
                           "requested_actor": actor, "requested_role": role,
                           "decision": "PASS", "reason": "非金融BUGFIX，跳过consult",
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
    # P2: 离开 coding 阶段 → 使 token 失效
    if cur == "coding" and nxt["stage"] != "coding":
        _invalidate_run_tokens(rid, f"advance: {cur}→{nxt['stage']}")
    actual = get_actual_actor()
    append_log("engine", {"run_id": rid, "event_type": "advance", "from_stage": cur,
               "to_stage": nxt["stage"], "target_role": nxt.get("role", ""),
               "actor": actor, "role": role,
               "actual_actor": actual or actor, "actual_role": actual or role,
               "requested_actor": actor, "requested_role": role,
               "decision": "PASS", "reason": "",
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
    _invalidate_run_tokens(rid, "流程完成")
    actual = get_actual_actor()
    append_log("engine", {"run_id": rid, "event_type": "complete", "from_stage": cur,
               "to_stage": None, "target_role": role, "actor": actor, "role": role,
               "actual_actor": actual or actor, "actual_role": actual or role,
               "requested_actor": actor, "requested_role": role,
               "decision": "PASS", "reason": "",
               "package_files": [cpath] if cpath else [], "override_reason": ""})
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
    _invalidate_run_tokens(rid, f"流程阻断: {reason}")
    actual_blk = get_actual_actor()
    append_log("engine", {"run_id": rid, "event_type": "block", "from_stage": run["current_stage"],
               "to_stage": run["current_stage"], "target_role": "", "actor": "阿黑", "role": "阿黑",
               "actual_actor": actual_blk or "阿黑", "actual_role": "阿黑",
               "requested_actor": "", "requested_role": "",
               "decision": "PASS", "reason": reason,
               "package_files": [],
               "override_reason": reason})
    print(f"✓ 已阻断 {rid}: {reason}")


def cmd_hygiene_check(args):
    """--hygiene-check: run git workspace hygiene preflight."""
    script = os.path.join(PROJECT_ROOT, "scripts", "git_workspace_hygiene.py")
    if not os.path.exists(script):
        print(f"FAIL: hygiene script not found: {script}")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, script, "--verify"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)
    sys.exit(0)


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
    # token_budget 硬校验（严格模式）
    budget_warnings = []
    tb = data.get("token_budget")
    if tb is None:
        errors.append("Missing: token_budget（必填，单位：token数）")
    elif isinstance(tb, bool) or not isinstance(tb, int):
        errors.append(f"token_budget 必须为整数，收到: {type(tb).__name__} {tb}")
    elif tb <= 0:
        errors.append(f"token_budget 需为正整数，收到: {tb}")
    else:
        if tb > 30000:
            bj = data.get("budget_justification")
            if not bj:
                errors.append("token_budget > 30000 需提供 budget_justification 字段说明理由")
            else:
                budget_warnings.append(f"token_budget={tb} 为超大需求档(>30000)，已提供 justification")
        elif tb > 15000:
            budget_warnings.append(f"token_budget={tb} 为大型需求档(15000-30000)")
        elif tb < 1000:
            budget_warnings.append(f"token_budget={tb} 偏低(<1000)，仅适合微修复")
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
    for w in budget_warnings:
        print(f"  ⚠ {w}")
    if fi:
        print("  ⚠ 检测到金融影响")
        if has_l1_or_l2(data.get("items", [])):
            print("  ⚠ L1/L2变更，需五角色咨询")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_pcontinue(run_id=None):
    """检查当前 pipeline 状态并输出下一阶段路由（执行类口令门禁核心）。"""
    state = load_state()
    runs = state.get("runs", {})

    if run_id:
        if run_id not in runs:
            print(f"错误: run_id 不存在: {run_id}")
            sys.exit(1)
        filtered = {run_id: runs[run_id]}
    else:
        # 查找未完成的活跃 run（优先非 blocked）
        filtered = {}
        for rid, r in runs.items():
            if r.get("status") == "active" and not r.get("blocked"):
                filtered[rid] = r
        if not filtered:
            # 退而求其次：找任何活跃的
            for rid, r in runs.items():
                if r.get("status") == "active":
                    filtered[rid] = r

    if not filtered:
        print("无活跃流程。请先启动新流程（--start 或 --route）。")
        sys.exit(0)

    if len(filtered) > 1:
        print(f"存在多个活跃流程（{len(filtered)}个），请指定 run_id：")
        for rid, r in filtered.items():
            print(f"  {rid} ({r.get('flow_type')}) — {r.get('current_stage')}")
        sys.exit(1)

    rid = list(filtered.keys())[0]
    run = filtered[rid]
    stage = run.get("current_stage", "")
    status = run.get("status", "")
    blocked = run.get("blocked", False)
    block_reason = run.get("block_reason", "")
    checklist = run.get("checklist_path", "")

    print(f"PIPELINE_CONTINUE — 当前流程状态:")
    print(f"  run_id: {rid}")
    print(f"  flow_type: {run.get('flow_type', '?')}")
    print(f"  task: {run.get('task_description', '')}")
    print(f"  stage: {stage}")
    print(f"  status: {status}")
    print(f"  blocked: {blocked}" + (f" — {block_reason}" if blocked else ""))
    print(f"  checklist: {checklist or '未注册'}")

    # Stage → 角色映射
    STAGE_ROLES = {
        "design": "情墨",
        "review_1a": "腰子",
        "review_1b": "旧影/新安",
        "consult": "山猫→信鸽→玉夜→流金→青山",
        "coding": "红结",
        "verify": "新安",
        "deploy": "红枫",
        "deploy_verify": "旧影",
        "audit": "旧影",
        "post_audit": "旧影",
    }
    role = STAGE_ROLES.get(stage, "未知")
    print(f"  路由: 下一阶段负责人 → {role}")

    # Coding 入场门禁 — 调用统一 check_coding_gate()
    if stage == "coding":
        print("  检测到 current_stage=coding，执行完整 C1-C8 coding 入场门禁...")
        ok, failures, _ = check_coding_gate(rid, verbose=True)
        if ok:
            print(f"  coding门禁: ✅ 全部通过，允许红结入场")
            return rid
        else:
            print(f"  BLOCK：红结未获得 coding 入场条件，退回阿黑/情墨补齐流程。")
            sys.exit(1)
    return rid


def check_coding_gate(run_id, verbose=True):
    """统一 C1-C8 coding 入场门禁。纯函数，不 exit。

    Args:
        run_id: 流程 run_id
        verbose: 是否 print 失败信息

    Returns: (ok: bool, failures: list[str], cl_data: dict)
    """
    state = load_state()
    runs = state.get("runs", {})

    failures = []
    cl_data = {}

    if run_id not in runs:
        failures.append("run_id 不存在")
        return False, failures, cl_data

    run = runs[run_id]
    stage = run.get("current_stage", "")
    status = run.get("status", "")
    blocked = run.get("blocked", False)
    checklist = run.get("checklist_path", "")
    stages_list = run.get("stages", [])

    # C1: current_stage == coding
    c1 = stage == "coding"
    if not c1:
        msg = f"C1: current_stage={stage} (需要 coding)"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C2: status == active, not blocked
    c2 = status == "active" and not blocked
    if not c2:
        msg = f"C2: status={status}, blocked={blocked}"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C3: checklist_path registered
    c3 = bool(checklist)
    if not c3:
        msg = "C3: checklist_path 未注册"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C4: checklist structure + token_budget + 情墨HMAC记录存在
    c4 = False
    if c3:
        try:
            with open(checklist, 'r', encoding='utf-8') as f:
                cl_data = json.load(f)
            c4 = all(fld in cl_data for fld in ["run_id", "items", "token_budget"])
            qm_sig = cl_data.get("signoffs", {}).get("情墨", {})
            if qm_sig.get("sig_type") != "HMAC-SHA256":
                c4 = False
        except Exception:
            pass
    if not c4:
        msg = "C4: checklist 结构不完整或情墨签名缺失（必须包含 run_id/items/token_budget + 情墨 HMAC-SHA256）"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C5: 情墨 design 阶段已完成 + HMAC 签名有效
    c5 = False
    if c4:
        design_completed = any(
            s.get("stage") == "design" and s.get("status") == "completed"
            for s in stages_list
        )
        if design_completed:
            sig_ok, sig_err = _verify_checklist_signoff(checklist, "情墨", run_id, "design")
            if sig_ok:
                c5 = True
                if verbose: print(f"  ✓ C5: 情墨 HMAC 签名验证通过")
            else:
                msg = f"C5: 情墨 HMAC 签名验证失败 — {sig_err}（checklist 已被篡改？）"
                failures.append(msg)
                if verbose: print(f"  FAIL {msg}")
        else:
            msg = "C5: 情墨 design 阶段未完成"
            failures.append(msg)
            if verbose: print(f"  FAIL {msg}")
    else:
        msg = "C5: 跳过（C4 未通过，无法验证签名）"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C6: coding 前置阶段 completed/skipped
    coding_idx = -1
    for i, s in enumerate(stages_list):
        if s.get("stage") == stage:
            coding_idx = i
            break
    preceding_stages = [s for i, s in enumerate(stages_list) if i < coding_idx] if coding_idx >= 0 else []
    c6 = all(s.get("status") in ("completed", "skipped") for s in preceding_stages) if preceding_stages else True
    if not c6:
        failed_stages = [s.get("stage") for s in preceding_stages if s.get("status") not in ("completed", "skipped")]
        msg = f"C6: 前置阶段未完成: {failed_stages}"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C7: file_budgets/files_scope 非空
    fb = cl_data.get("file_budgets", []) if c3 and c4 else []
    fs = run.get("files_scope", [])
    c7 = bool(fb) or bool(fs)
    if not c7:
        msg = "C7: file_budgets/files_scope 为空"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    # C8: items[].code_level 完整
    items = cl_data.get("items", []) if c3 and c4 else []
    c8 = all("code_level" in item for item in items) if items else False
    if not c8:
        msg = "C8: code_level 未完全标注"
        failures.append(msg)
        if verbose: print(f"  FAIL {msg}")

    ok = len(failures) == 0
    return ok, failures, cl_data


def _verify_checklist_signoff(checklist_path, role, run_id, expected_stage):
    """验证 checklist 中指定角色的 HMAC 签名是否有效且内容未被篡改。

    Args:
        checklist_path: checklist JSON 路径
        role: 要检查的角色（如 "情墨"）
        run_id: 流程 run_id
        expected_stage: 签名对应的阶段（如 "design"）

    Returns: (ok: bool, err: str)
    """
    if not checklist_path or not os.path.exists(checklist_path):
        return False, "checklist 不存在"
    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return False, f"checklist 读取失败: {e}"
    sig = data.get("signoffs", {}).get(role, {})
    if not sig:
        return False, f"{role} 无签名记录"
    sig_actor = sig.get("actor", role)
    from log_utils import hmac_verify as _hmac_verify
    return _hmac_verify(sig, sig_actor, role, run_id, expected_stage, checklist_path)


def cmd_check_coding_gate(args):
    """红结入场门禁 — 8条件全检查（委托 check_coding_gate）。"""
    rid = args.check_coding_gate
    ok, failures, _ = check_coding_gate(rid)
    if ok:
        print("PASS: 全部8项coding入场门禁通过，红结可入场编码。")
        sys.exit(0)
    else:
        print("BLOCK：红结未获得 coding 入场条件，退回阿黑/情墨补齐流程。")
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="铁律量化 - 流程状态机 (fix3)")
    p.add_argument("--start", metavar="EVENT"); p.add_argument("--route", metavar="TEXT")
    p.add_argument("--task", metavar="DESC")
    p.add_argument("--status", action="store_true"); p.add_argument("--all", action="store_true")
    p.add_argument("--run-id"); p.add_argument("--advance", metavar="RUN_ID")
    p.add_argument("--complete", metavar="RUN_ID"); p.add_argument("--actor"); p.add_argument("--role")
    p.add_argument("--checklist"); p.add_argument("--audit-report")
    p.add_argument("--block", metavar="RUN_ID"); p.add_argument("--reason")
    p.add_argument("--validate", metavar="PATH")
    p.add_argument("--pcontinue", metavar="RUN_ID", nargs="?", const="__auto__", default=None,
                   help="继续流程判定：检查pipeline状态并路由到当前阶段负责人")
    p.add_argument("--check-coding-gate", metavar="RUN_ID",
                   help="红结入场门禁全检查(C1-C8)，通过exit0，不通过exit1")
    p.add_argument("--hygiene-check", action="store_true",
                   help="Git workspace hygiene preflight (检查 ahead/staged/unstaged/untracked)")
    # Token (A3-A5)
    p.add_argument("--issue-auth-token", metavar="RUN_ID",
                   help="签发工程鉴权 token (coding gate PASS 后)")
    p.add_argument("--revoke-auth-token", metavar="TOKEN_ID",
                   help="撤销 token")
    p.add_argument("--list-auth-tokens", metavar="RUN_ID", nargs="?", const=None,
                   help="列出 token（可指定 run_id 过滤）")
    # P0
    p.add_argument("--incident-id"); p.add_argument("--p0-reason"); p.add_argument("--impact-scope")
    p.add_argument("--risk-level"); p.add_argument("--temp-fix"); p.add_argument("--rollback-point")
    p.add_argument("--post-audit-deadline"); p.add_argument("--user-confirmed-p0", type=lambda x: x.lower()=="true", default=False)
    args = p.parse_args()

    if args.start:
        if not args.task:
            print("错误: --start 需要 --task"); sys.exit(1)
        cmd_start(args)
    elif args.route:
        cmd_route(args.route)
    elif args.status:
        cmd_status(args.run_id, args.all)
    elif args.pcontinue is not None:
        rid = args.pcontinue if args.pcontinue != "__auto__" else None
        cmd_pcontinue(rid)
    elif args.issue_auth_token:
        cmd_issue_auth_token(args)
    elif args.revoke_auth_token:
        cmd_revoke_auth_token(args)
    elif args.list_auth_tokens is not None:
        cmd_list_auth_tokens(args)
    elif args.check_coding_gate:
        cmd_check_coding_gate(args)
    elif args.hygiene_check:
        cmd_hygiene_check(args)
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
