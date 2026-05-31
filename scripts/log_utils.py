import json, os, hashlib, hmac, secrets as _secrets_mod
from datetime import datetime, timezone

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
        "signature": ("signatures/signature_events.jsonl", ["timestamp","run_id","stage","role","action","checklist_version","signature","comment"]),
        "checklist_chg": ("checklist/checklist_changelog.jsonl", ["timestamp","run_id","modified_by","operation","diff_summary","previous_hash","new_hash"]),
        "ai_ops": ("ai_ops/ai_ops.jsonl", ["timestamp","run_id","stage","role","task_type","input_context_hash","output_summary","token_used","model","duration_ms","result","error_msg"]),
        "engine": ("engine/engine_events.jsonl", ["timestamp","run_id","event_type","from_stage","to_stage","target_role","package_files","override_reason"]),
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
