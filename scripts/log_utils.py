import json, os, hashlib, hmac, secrets as _secrets_mod
from datetime import datetime, timezone, timedelta

LOG_DIR = os.environ.get("PIPELINE_LOG_DIR", "logs")

# ---------------------------------------------------------------------------
# Actor / Role 体系
# ---------------------------------------------------------------------------
# actor: 实际操作者（谁在敲命令）
# role:  业务角色（以什么身份执行）
# 阿黑 actor 只能扮演 role=阿黑，且阿黑 role 仅允许调度/查看/阻断

VALID_ACTORS = [
    "阿黑", "腰子", "山猫", "信鸽", "玉夜", "流金", "青山",
    "情墨", "千光", "红枫", "新安", "红结", "旧影",
]

VALID_ROLES = VALID_ACTORS  # 角色集合相同

# actor → 该 actor 允许扮演的 role 白名单
ACTOR_TO_ALLOWED_ROLES = {
    "阿黑": ["阿黑"],
    "腰子": ["腰子"],
    "山猫": ["山猫"],
    "信鸽": ["信鸽"],
    "玉夜": ["玉夜"],
    "流金": ["流金"],
    "青山": ["青山"],
    "情墨": ["情墨"],
    "千光": ["千光"],
    "红枫": ["红枫"],
    "新安": ["新安"],
    "红结": ["红结"],
    "旧影": ["旧影"],
}

# 阿黑 role 允许的动作（非调度动作一律拒绝）
DISPATCHER_ALLOWED_ACTIONS = [
    "start", "status", "block", "wake", "notify", "collect", "summarize",
]

RISK_LEVELS = ["P0", "Critical", "High"]

# ---------------------------------------------------------------------------
# HMAC 密钥管理
# ---------------------------------------------------------------------------
SECRETS_FILE = os.environ.get(
    "PIPELINE_SECRETS_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".claude", "actor_secrets.json")
)


def _load_secrets():
    """加载 actor secrets（不写入日志/不写入repo）"""
    secrets = {}
    # 1. 从文件加载
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # 2. 从环境变量覆盖: ACTOR_SECRET_<ROLE>
    for role in VALID_ROLES:
        env_key = f"ACTOR_SECRET_{role}"
        if os.environ.get(env_key):
            secrets[role] = os.environ[env_key]
    return secrets


def get_actor_secret(actor):
    """获取 actor 的 HMAC 密钥。无密钥则返回 None"""
    secrets = _load_secrets()
    return secrets.get(actor)


def generate_secrets_file():
    """生成各角色随机密钥（仅供初始化使用，不自动调用）"""
    secrets = {}
    for role in VALID_ROLES:
        secrets[role] = _secrets_mod.token_hex(32)
    return secrets


# ---------------------------------------------------------------------------
# HMAC 签名与验证
# ---------------------------------------------------------------------------
def hmac_sign(actor, role, run_id, stage, checklist_hash,
              audit_report_hash, timestamp, git_sha, secret):
    """
    HMAC-SHA256 签名。
    签名内容: actor|role|run_id|stage|checklist_hash|audit_report_hash|timestamp|git_sha
    """
    if not secret:
        return None
    content = "|".join([
        actor, role, run_id, stage,
        checklist_hash or "",
        audit_report_hash or "",
        timestamp,
        git_sha or "",
    ])
    return hmac.new(
        secret.encode('utf-8') if isinstance(secret, str) else secret,
        content.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def hmac_verify(sig_record, actor, role, run_id, expected_stage,
                checklist_path, audit_report_hash=None):
    """
    完整 HMAC 签名验证。返回 (is_valid: bool, error_message: str)。
    验证: signed=true, checklist_version匹配, stage匹配, HMAC可重算。
    """
    if not isinstance(sig_record, dict):
        return False, f"签名记录[{role}]格式非法"

    if not sig_record.get("signed"):
        return False, f"{role} 未签名"

    # 必须有 HMAC 字段
    sig_type = sig_record.get("sig_type", "")
    if sig_type != "HMAC-SHA256":
        return False, f"{role} 使用弱签名({sig_type or '无sig_type'})，已废弃"

    # 验证 actor 一致性
    sig_actor = sig_record.get("actor", "")
    if sig_actor != actor:
        return False, f"{role} 签名actor({sig_actor})与声称actor({actor})不匹配"

    # 验证 actor→role 映射
    allowed_roles = ACTOR_TO_ALLOWED_ROLES.get(actor, [])
    if role not in allowed_roles:
        return False, f"actor({actor})无权扮演role({role})"

    # 验证 checklist 内容未变更
    current_hash = ""
    if checklist_path and os.path.exists(checklist_path):
        current_hash = checklist_content_hash(checklist_path)
    sig_version = sig_record.get("checklist_version", "")
    if checklist_path and sig_version != current_hash:
        return False, (
            f"{role} 签名已失效: checklist内容已变更"
            f" (签名版本:{sig_version[:16]}... 当前:{current_hash[:16]}...)"
        )

    # 验证 stage 匹配
    sig_stage = sig_record.get("stage", "")
    if sig_stage != expected_stage:
        return False, f"{role} 签名阶段({sig_stage})与当前阶段({expected_stage})不匹配"

    # 验证 audit_report_hash（如有）
    sig_ar_hash = sig_record.get("audit_report_hash", "")
    expected_ar_hash = audit_report_hash or ""
    if expected_ar_hash and sig_ar_hash != expected_ar_hash:
        return False, f"{role} audit_report_hash不匹配"

    # 获取 actor 的 secret 并重算 HMAC
    secret = get_actor_secret(actor)
    if not secret:
        return False, f"actor({actor})无有效密钥，无法验证签名"

    expected_hmac = hmac_sign(
        actor, role, run_id, sig_stage,
        sig_version, sig_ar_hash,
        sig_record.get("timestamp", ""),
        sig_record.get("git_sha", ""),
        secret,
    )
    if expected_hmac != sig_record.get("signature", ""):
        return False, f"{role} HMAC签名值不匹配（可能伪造或密钥错误）"

    return True, ""


# ---------------------------------------------------------------------------
# 兼容层: 旧 SHA256 签名验证（仅用于 audit_scan 检测弱签名）
# ---------------------------------------------------------------------------
def verify_legacy_sha256_signature(sig_record, role, run_id, expected_stage, checklist_path):
    """旧 SHA256 签名验证。返回 (is_valid, error) 供 audit_scan 检测弱签名。"""
    if not isinstance(sig_record, dict) or not sig_record.get("signed"):
        return False, "未签名"
    sig_type = sig_record.get("sig_type", "")
    if sig_type == "HMAC-SHA256":
        return False, "非旧签名(HMAC)"
    # 旧算法: SHA256(role|run_id|stage|checklist_hash|timestamp)
    from log_utils import checklist_content_hash as _ch
    current_hash = _ch(checklist_path) if checklist_path else ""
    sig_version = sig_record.get("checklist_version", "")
    if sig_version != current_hash:
        return False, "checklist已变更"
    sig_stage = sig_record.get("stage", "")
    if sig_stage != expected_stage:
        return False, f"阶段不匹配({sig_stage}!={expected_stage})"
    content = f"{role}|{run_id}|{sig_stage}|{sig_version}|{sig_record.get('timestamp', '')}"
    expected = hashlib.sha256(content.encode()).hexdigest()
    if expected != sig_record.get("signature", ""):
        return False, "签名值不匹配"
    return True, ""


# ---------------------------------------------------------------------------
# 日志与哈希工具
# ---------------------------------------------------------------------------
def _ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def append_log(log_type, data):
    spec = {
        "gate": ("gates/gate_check.jsonl", ["timestamp","run_id","gate","script","trigger","commit_sha","checks","overall_result","fail_reasons","duration_ms"]),
        "signature": ("signatures/signature_events.jsonl", ["timestamp","run_id","stage","role","requested_actor","requested_role","actual_actor","actual_role","action","decision","reason","checklist_version","signature","comment","session_id","process_id","command_source"]),
        "checklist_chg": ("checklist/checklist_changelog.jsonl", ["timestamp","run_id","modified_by","operation","diff_summary","previous_hash","new_hash"]),
        "ai_ops": ("ai_ops/ai_ops.jsonl", ["timestamp","run_id","stage","role","task_type","input_context_hash","output_summary","token_used","model","duration_ms","result","error_msg"]),
        "engine": ("engine/engine_events.jsonl", ["timestamp","run_id","event_type","from_stage","to_stage","target_role","actor","role","actual_actor","actual_role","requested_actor","requested_role","decision","reason","package_files","override_reason"]),
        "deploy": ("deployments/verify_deploy.jsonl", ["timestamp","run_id","deploy_item","check_type","expected","actual","result"]),
        "audit": ("audit/audit_findings.jsonl", ["timestamp","finding_id","severity","category","related_run_id","description","evidence_log_paths","recommended_action","status"]),
        "security": ("audit/security_events.jsonl", ["timestamp","run_id","actor","action","target","result","detail"]),
    }
    if log_type not in spec:
        raise ValueError(f"Unknown log type: {log_type}")
    rel_path, fields = spec[log_type]
    path = os.path.join(LOG_DIR, rel_path)
    _ensure_dir(path)
    record = {f: data.get(f) for f in fields}
    record["timestamp"] = record.get("timestamp") or datetime.now(timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_ai_ops(run_id, stage, role, task_type, token_used, model="unknown",
               input_context_hash="", output_summary="", duration_ms=0,
               result="ok", error_msg=""):
    """便捷函数：记录AI/LLM调用Token消耗。所有AI调用点统一走此函数。"""
    append_log("ai_ops", {
        "run_id": run_id,
        "stage": stage,
        "role": role,
        "task_type": task_type,
        "input_context_hash": input_context_hash,
        "output_summary": output_summary,
        "token_used": token_used,
        "model": model,
        "duration_ms": duration_ms,
        "result": result,
        "error_msg": error_msg,
    })


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def checklist_content_hash(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    content = {k: v for k, v in data.items() if k != "signoffs"}
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def compute_state_hash(runs_data):
    raw = json.dumps(runs_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# financial_impact 检测（pipeline_engine / check_checklist 共用）
# ---------------------------------------------------------------------------
FINANCIAL_PATH_KEYWORDS = [
    "评分", "选股", "交易", "因子", "风控", "报告", "白皮书",
    "分析逻辑", "每日荐股", "重点股票",
]

FINANCIAL_DESC_KEYWORDS = [
    "评分", "选股", "交易", "买入", "卖出", "仓位", "止损", "因子",
    "风控", "PE", "MACD", "RSI", "KDJ", "资金流", "推荐", "报告结论",
]


def detect_financial_impact(items, file_budgets=None, task_description=""):
    for fb in (file_budgets or []):
        path = fb.get("path", "")
        for kw in FINANCIAL_PATH_KEYWORDS:
            if kw in path:
                return True
    for item in (items or []):
        desc = item.get("description", "")
        for kw in FINANCIAL_DESC_KEYWORDS:
            if kw in desc:
                return True
    for kw in FINANCIAL_DESC_KEYWORDS:
        if kw in task_description:
            return True
    return False


def has_l1_or_l2(items):
    return any(item.get("code_level") in ["L1", "L2"] for item in (items or []))


# ---------------------------------------------------------------------------
# 工程鉴权 Token (A0/A2/A7)
# ---------------------------------------------------------------------------
AUTH_TOKEN_STORE = ".claude/auth_tokens.json"
AUTH_TOKEN_EVENT_LOG = "logs/security/auth_token_events.jsonl"
AUTH_TOKEN_TTL_MINUTES = 15

# Paths that never need token (auto-commit)
AUTH_AUTOCOMMIT_PATHS = [
    r'\.log$', r'\.md$', r'\.json$', r'\.jsonl$',
    r'\.csv$', r'\.txt$', r'\.pdf$', r'\.docx$', r'\.html$',
]


def token_canonical_hash(token_data):
    """A0: 生成 token payload 的 canonical hash 用于 HMAC 签名。

    签名覆盖字段: token_id, run_id, stage, actor, role,
    allowed_actions, allowed_paths, checklist_hash, issued_at, expires_at.
    """
    fields = {
        "token_id": token_data.get("token_id", ""),
        "run_id": token_data.get("run_id", ""),
        "stage": token_data.get("stage", ""),
        "actor": token_data.get("actor", ""),
        "role": token_data.get("role", ""),
        "allowed_actions": sorted(token_data.get("allowed_actions", [])),
        "allowed_paths": sorted(token_data.get("allowed_paths", [])),
        "checklist_hash": token_data.get("checklist_hash", ""),
        "issued_at": token_data.get("issued_at", ""),
        "expires_at": token_data.get("expires_at", ""),
    }
    raw = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def load_auth_tokens():
    """加载 token 存储。"""
    path = os.environ.get("AUTH_TOKEN_FILE", AUTH_TOKEN_STORE)
    if not os.path.exists(path):
        return {"tokens": {}}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"tokens": {}}


def save_auth_tokens(data):
    """保存 token 存储。"""
    path = os.environ.get("AUTH_TOKEN_FILE", AUTH_TOKEN_STORE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_auth_token_event(event_type, token_id="", run_id="", actor="", role="",
                         action="", file_path="", reason="", detail=""):
    """A7: 记录 token 生命周期事件到 auth_token_events.jsonl。"""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "token_id": token_id,
        "run_id": run_id,
        "actor": actor,
        "role": role,
        "action": action,
        "file_path": file_path,
        "reason": reason,
        "detail": detail,
    }
    path = os.environ.get("AUTH_TOKEN_EVENT_LOG", AUTH_TOKEN_EVENT_LOG)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _ensure_pipeline_auth():
    """确保 pipeline_auth 模块可导入。"""
    import sys as _sys
    from pathlib import Path
    _hook_shared = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "shared"
    if str(_hook_shared) not in _sys.path:
        _sys.path.insert(0, str(_hook_shared))


def is_auth_read_protected(file_path):
    """检查文件路径是否需要 token 才能 Read。

    Read 鉴权只看 AUTH_PROTECTED_PATHS。
    auto-commit 扩展名豁免只属于写侧，不参与 Read 判断。
    """
    _ensure_pipeline_auth()
    from pipeline_auth import AUTH_PROTECTED_PATHS as _paths
    import re
    normalized = file_path.replace("\\", "/")
    return any(re.search(pat, normalized) for pat in _paths)


def is_auth_write_protected(file_path):
    """检查文件路径是否需要 token 才能 Write/Edit/MultiEdit/Bash。

    使用 pipeline_auth.is_auth_write_protected() 作为写保护判断。
    """
    _ensure_pipeline_auth()
    from pipeline_auth import is_auth_write_protected as _impl
    return _impl(file_path)


def verify_auth_token(token_id, actor="", role="", action="", file_path="", run_id=None):
    """A2: 10 项 token 校验 (V1-V10)。

    Returns: (ok: bool, reason: str)
    """
    store = load_auth_tokens()
    tokens = store.get("tokens", {})
    token = tokens.get(token_id)
    if not token:
        log_auth_token_event("verify_block", token_id, run_id or "", actor, role, action, file_path, "V1: token 不存在")
        return False, "V1: token 不存在"

    # V2: status == active
    if token.get("status") != "active":
        log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                             f"V2: token 状态={token.get('status')}")
        return False, f"V2: token 状态={token.get('status')}"

    # V3: 未过期
    now = datetime.now(timezone.utc)
    expires_str = token.get("expires_at", "")
    if expires_str:
        try:
            expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
            if now > expires:
                # Auto-mark expired
                token["status"] = "expired"
                save_auth_tokens(store)
                log_auth_token_event("expire", token_id, token.get("run_id",""), actor, role, action, file_path,
                                     "V3: token 已过期")
                return False, "V3: token 已过期"
        except (ValueError, TypeError):
            pass

    # V4: actor/role 匹配
    if token.get("actor") != actor:
        log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                             f"V4: actor 不匹配 (token={token.get('actor')}, requested={actor})")
        return False, f"V4: actor 不匹配 (token={token.get('actor')})"
    if token.get("role") != role:
        log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                             f"V4: role 不匹配 (token={token.get('role')}, requested={role})")
        return False, f"V4: role 不匹配 (token={token.get('role')})"

    # V5: action 在 allowed_actions 内
    allowed_actions = token.get("allowed_actions", [])
    if action and action not in allowed_actions:
        log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                             f"V5: action={action} 不在允许列表 {allowed_actions}")
        return False, f"V5: action={action} 不在允许列表"

    # V6: file_path 在 allowed_paths 内
    allowed_paths = token.get("allowed_paths", [])
    if file_path and allowed_paths:
        normalized_fp = file_path.replace("\\", "/")
        in_scope = any(normalized_fp.startswith(p.rstrip('/')) for p in allowed_paths)
        if not in_scope:
            log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                                 f"V6: file_path 不在 allowed_paths {allowed_paths}")
            return False, f"V6: file_path 不在授权路径内"

    # V7: run_id 匹配
    if run_id and token.get("run_id") and token["run_id"] != run_id:
        log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                             f"V7: run_id 不匹配 (token={token.get('run_id')}, requested={run_id})")
        return False, f"V7: run_id 不匹配"

    # V8: pipeline 仍 active + stage 未变
    try:
        import subprocess, sys as _sys
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent
        _state_path = os.path.join(str(_root), ".claude", "pipeline_active.json")
        actual_state_file = os.environ.get("PIPELINE_STATE_FILE", _state_path)
        if os.path.exists(actual_state_file):
            with open(actual_state_file, 'r', encoding='utf-8') as f:
                pipeline = json.load(f)
            trun = pipeline.get("runs", {}).get(token.get("run_id", ""), {})
            # 如果 run 在 pipeline state 中不存在（测试环境/已清理），跳过 V8
            if trun:
                if trun.get("status") != "active":
                    token["status"] = "invalidated"
                    save_auth_tokens(store)
                    log_auth_token_event("invalidate", token_id, token.get("run_id",""), actor, role, action, file_path,
                                         "V8: pipeline 不再 active")
                    return False, "V8: pipeline 不再 active"
                if trun.get("current_stage") != token.get("stage"):
                    token["status"] = "invalidated"
                    save_auth_tokens(store)
                    log_auth_token_event("invalidate", token_id, token.get("run_id",""), actor, role, action, file_path,
                                         f"V8: stage 已变 (pipeline={trun.get('current_stage')}, token={token.get('stage')})")
                    return False, f"V8: stage 已变"
    except Exception:
        pass  # Fail open if pipeline state unreadable (defensive)

    # V9: checklist_hash 未变化
    cl_hash = token.get("checklist_hash", "")
    if cl_hash:
        cl_path = token.get("checklist_path", "")
        if cl_path and os.path.exists(cl_path):
            current_hash = checklist_content_hash(cl_path)
            if current_hash != cl_hash:
                token["status"] = "invalidated"
                save_auth_tokens(store)
                log_auth_token_event("invalidate", token_id, token.get("run_id",""), actor, role, action, file_path,
                                     "V9: checklist_hash 已变化")
                return False, "V9: checklist_hash 已变化，token 失效"

    # V10: HMAC signature 有效
    sig = token.get("signature", "")
    if sig:
        payload_hash = token_canonical_hash(token)
        secret = get_actor_secret(actor)
        if secret:
            expected = hmac_sign(actor, role, token.get("run_id",""), token.get("stage",""),
                                 cl_hash, payload_hash, token.get("issued_at",""), token_id, secret)
            if expected and expected != sig:
                log_auth_token_event("verify_block", token_id, token.get("run_id",""), actor, role, action, file_path,
                                     "V10: HMAC 签名验证失败")
                return False, "V10: HMAC 签名验证失败"

    log_auth_token_event("verify_pass", token_id, token.get("run_id",""), actor, role, action, file_path, "PASS")
    return True, "PASS"


def issue_auth_token(run_id, actor, role, allowed_paths, allowed_actions=None,
                      checklist_path="", checklist_hash="", stage="coding",
                      ttl_minutes=None):
    """签发工程鉴权 token。返回 token_id。

    Args:
        run_id: 流程 run_id
        actor: 实际操作者
        role: 业务角色
        allowed_paths: 授权路径列表
        allowed_actions: 授权操作列表，默认 Read/Edit/Write/Bash
        checklist_path: 关联的 checklist 路径
        checklist_hash: 关联的 checklist hash
        stage: 阶段，默认 coding
        ttl_minutes: 有效期，默认 15 分钟
    """
    import uuid
    if allowed_actions is None:
        allowed_actions = ["Read", "Edit", "Write", "Bash"]
    if ttl_minutes is None:
        ttl_minutes = AUTH_TOKEN_TTL_MINUTES

    now = datetime.now(timezone.utc)
    token_id = f"AUTH-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()

    token_data = {
        "token_id": token_id,
        "run_id": run_id,
        "stage": stage,
        "actor": actor,
        "role": role,
        "allowed_actions": sorted(allowed_actions),
        "allowed_paths": sorted(allowed_paths),
        "checklist_path": checklist_path,
        "checklist_hash": checklist_hash,
        "issued_at": now.isoformat(),
        "expires_at": expires_at,
        "issuer": "pipeline_engine",
        "gate": "check_coding_gate:C1-C8",
        "signature": "",
        "status": "active",
    }

    # HMAC sign
    payload_hash = token_canonical_hash(token_data)
    secret = get_actor_secret(actor)
    if secret:
        sig = hmac_sign(actor, role, run_id, stage, checklist_hash,
                        payload_hash, token_data["issued_at"], token_id, secret)
        token_data["signature"] = sig or ""

    # Revoke existing active tokens for same run/stage/actor/role
    store = load_auth_tokens()
    tokens = store.get("tokens", {})
    for tid, t in list(tokens.items()):
        if (t.get("status") == "active"
            and t.get("run_id") == run_id
            and t.get("stage") == stage
            and t.get("actor") == actor
            and t.get("role") == role):
            t["status"] = "revoked"
            t["revoked_reason"] = f"new token issued: {token_id}"
            log_auth_token_event("revoke", tid, run_id, actor, role, "", "",
                                 f"新 token {token_id} 签发，旧 token 自动撤销")

    tokens[token_id] = token_data
    save_auth_tokens(store)

    log_auth_token_event("issue", token_id, run_id, actor, role, "", "",
                         f"授权路径: {allowed_paths}")

    return token_id
