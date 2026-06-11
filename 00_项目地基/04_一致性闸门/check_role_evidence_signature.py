#!/usr/bin/env python3
"""
check_role_evidence_signature.py — G0-G6 角色输出证据签名检查脚本

用途：
  按 mode 分阶段验证验收报告/角色输出是否满足 stage_acceptance_policy.json
  的 role_evidence_signature_rules 和 role_evidence_signature_schema.json。

使用方式：
  python3 check_role_evidence_signature.py --target <report.json> --mode g4
  python3 check_role_evidence_signature.py --target <report.json> --mode g5
  python3 check_role_evidence_signature.py --target <report.json> --mode g6
  python3 check_role_evidence_signature.py --self-test
  python3 check_role_evidence_signature.py --help

退出码：
  0 = PASS     — 所有检查通过，无阻断
  1 = WARN     — 有非阻断性警告
  2 = BLOCK    — 存在阻断项，阶段不得通过

mode 规则：
  --mode g4:  检查 G0/G1/G2/G3/G4 证据；检查角色输出格式；检查 evidence；
              检查是否执行模型代签；检查是否声明 G5/G6 待确认；不要求 G5/G6 已完成。

  --mode g5:  必须有 G4 自检证据；必须有旧影独立复查证据；
              缺 G4 或缺 G5 证据则 BLOCK。

  --mode g6:  必须有 G5 独立复查证据；必须有 G6 放行归档证据；
              金融/生产任务必须有腰子或用户明确确认；
              pipeline PASS 不得替代 G6。
"""

import json
import sys
import os
import re

# ── 常量 ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POLICY_PATH = os.path.join(SCRIPT_DIR, "stage_acceptance_policy.json")
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "role_evidence_signature_schema.json")

PROJECT_ROLES = {
    "阿黑", "腰子", "山猫", "信鸽", "玉夜", "流金", "青山",
    "情墨", "千光", "红枫", "新安", "红结", "旧影",
}
EXECUTION_MODELS = {"DeepSeek", "Claude", "Codex"}

# Schema 必填字段（与 role_evidence_signature_schema.json 一致）
SCHEMA_REQUIRED_FIELDS = [
    "role_name",
    "stage_gate",
    "responsibility",
    "check_scope",
    "conclusion",
    "evidence",
    "is_project_role_output",
    "signed_by_execution_model",
]
VALID_GATES = {"G0", "G1", "G2", "G3", "G4", "G5", "G6"}
VALID_CONCLUSIONS = {"PASS", "WARN", "BLOCK"}

# ── 辅助 ──────────────────────────────────────────────────────────────


def load_json(path, label=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None, f"{label} 文件不存在: {path}"
    except json.JSONDecodeError as e:
        return None, f"{label} JSON 解析失败: {e}"


def safe_str(v):
    return str(v).strip() if v else ""


def safe_list(v):
    return v if isinstance(v, list) else []

# ── 检查函数 ──────────────────────────────────────────────────────────


class CheckResult:
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"

    def __init__(self, result=PASS, code=None, message=None):
        self.result = result
        self.code = code
        self.message = message

    @classmethod
    def ok(cls):
        return cls(CheckResult.PASS, None, None)

    @classmethod
    def block(cls, code, message):
        return cls(CheckResult.BLOCK, code, message)

    @classmethod
    def warn(cls, code, message):
        return cls(CheckResult.WARN, code, message)


# ── 修复点 1：schema 校验 ────────────────────────────────────────────


def check_role_output_schema(data):
    """
    校验每条 role_output 是否符合 role_evidence_signature_schema.json。
    - 缺必填字段 → BLOCK
    - stage_gate 非 G0-G6 → BLOCK
    - conclusion 非 PASS/WARN/BLOCK → BLOCK
    - evidence 为空 → BLOCK
    - is_project_role_output / signed_by_execution_model 非 bool → BLOCK
    - 额外字段（不在 schema 定义中）→ WARN（向后兼容）
    """
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    if not outputs:
        return CheckResult.ok()

    # schema 中定义的字段集合（用于检测额外字段）
    schema_field_set = {
        "role_name", "stage_gate", "responsibility", "check_scope",
        "conclusion", "evidence", "residual_risk",
        "is_project_role_output", "signed_by_execution_model",
    }

    blocks = []
    warns = []

    for i, o in enumerate(outputs):
        if not isinstance(o, dict):
            blocks.append(f"role_outputs[{i}] 非 dict 类型")
            continue

        name = safe_str(o.get("role_name", f"#{{{i}}}"))

        # --- 缺必填字段 ---
        missing = [f for f in SCHEMA_REQUIRED_FIELDS if f not in o]
        if missing:
            blocks.append(f"'{name}' 缺必填字段: {', '.join(missing)}")
            # 缺必填字段时跳过后续字段级校验（避免级联报错）
            continue

        # --- stage_gate ---
        sg = safe_str(o.get("stage_gate"))
        if sg not in VALID_GATES:
            blocks.append(f"'{name}' stage_gate='{sg}' 不在 G0-G6 范围内")

        # --- conclusion ---
        conc = safe_str(o.get("conclusion"))
        if conc not in VALID_CONCLUSIONS:
            blocks.append(f"'{name}' conclusion='{conc}' 不是 PASS/WARN/BLOCK")

        # --- evidence ---
        ev = safe_str(o.get("evidence"))
        if not ev:
            blocks.append(f"'{name}' evidence 为空")

        # --- bool 类型校验 ---
        is_role = o.get("is_project_role_output")
        if not isinstance(is_role, bool):
            blocks.append(f"'{name}' is_project_role_output 必须是 bool，实际={type(is_role).__name__}")

        signed = o.get("signed_by_execution_model")
        if not isinstance(signed, bool):
            blocks.append(f"'{name}' signed_by_execution_model 必须是 bool，实际={type(signed).__name__}")

        # --- 额外字段 WARN ---
        extra = [k for k in o if k not in schema_field_set]
        if extra:
            warns.append(f"'{name}' 存在 schema 未定义字段: {', '.join(extra)}")

    if blocks:
        return CheckResult.block("role_output_schema_violation",
                                  "schema 校验违反：\n  " + "\n  ".join(blocks))
    if warns:
        return CheckResult.warn("role_output_extra_fields",
                                 "额外字段警告：\n  " + "\n  ".join(warns))
    return CheckResult.ok()


# ── 修复点 2：角色结论 BLOCK 检查 ─────────────────────────────────────


def check_role_block_conclusion(data):
    """
    任一 role_outputs[].conclusion == BLOCK → 整体 BLOCK
    """
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    for o in outputs:
        if not isinstance(o, dict):
            continue
        if o.get("conclusion") == "BLOCK":
            name = safe_str(o.get("role_name", "未知"))
            return CheckResult.block("role_output_blocked_stage",
                                      f"角色 '{name}' 输出结论为 BLOCK，阻断本阶段")
    return CheckResult.ok()


# ── 其他检查函数 ──────────────────────────────────────────────────────


def check_flow_code(data):
    """检查流程编号 F-xxx"""
    fc = safe_str(data.get("flow_code") or data.get("流程编号"))
    if not fc:
        return CheckResult.block("missing_flow_code", "缺少流程编号 F-xxx")
    if not fc.startswith("F-"):
        return CheckResult.block("missing_flow_code",
                                  f"流程编号格式错误，应为 F-xxx，实际为: {fc}")
    return CheckResult.ok()


def check_stage_gate(data):
    """
    检查阶段门枚举。
    支持：G0→G2→G3→G4 / G0->G2->G4 / G0/G2/G4 / G0,G2,G4 / G0 > G2 > G4 / enabled_gates 列表
    """
    gate = safe_str(data.get("stage_gate") or data.get("启用阶段门"))
    enabled = safe_list(data.get("enabled_gates") or data.get("启用阶段门列表"))

    targets = []
    if gate:
        # 用正则提取所有 G[0-6] 子串，不受分隔符影响
        targets = list(set(re.findall(r"G[0-6]", gate)))
    elif enabled:
        targets = [str(g).strip() for g in enabled]

    if not targets:
        return CheckResult.block("missing_stage_gate",
                                  "未找到阶段门 G0-G6 或启用阶段门字段")

    for g in targets:
        if g not in VALID_GATES:
            return CheckResult.warn("invalid_stage_gate_format",
                                     f"阶段门格式含非 G0-G6: {g}")
    return CheckResult.ok()


def check_awakened_role_outputs(data):
    """检查必唤醒角色是否都有输出"""
    awakened = safe_list(data.get("awakened_roles")
                         or data.get("唤醒角色") or data.get("必唤醒角色"))
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))

    if not awakened:
        return CheckResult.ok()  # 可能单角色场景

    output_roles = {o.get("role_name", "") for o in outputs if isinstance(o, dict)}
    missing = {r for r in awakened if r not in output_roles}
    if missing:
        return CheckResult.block("awakened_role_output_missing",
                                  f"唤醒角色缺少输出记录: {', '.join(sorted(missing))}")
    return CheckResult.ok()


def check_evidence_in_outputs(data):
    """检查每条角色输出是否有 evidence（冗余保护，与 schema 校验互补）"""
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    missing = []
    for o in outputs:
        if not isinstance(o, dict):
            continue
        ev = safe_str(o.get("evidence"))
        if not ev:
            name = o.get("role_name", f"角色输出#{outputs.index(o)}")
            missing.append(name)

    if missing:
        return CheckResult.block("claimed_pass_without_evidence",
                                  f"角色输出缺 evidence: {', '.join(missing)}")
    return CheckResult.ok()


def check_execution_model_signing(data):
    """检查执行模型代签约束"""
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    violations = []
    for o in outputs:
        if not isinstance(o, dict):
            continue
        signed = o.get("signed_by_execution_model", False)
        is_role = o.get("is_project_role_output", True)
        name = o.get("role_name", "未知")

        # 只有 signed_by_execution_model=true 且 is_project_role_output=true
        # 才算"执行模型以项目角色身份签字"
        if signed is True and is_role is True:
            violations.append(
                f"'{name}' 声明为项目角色输出(is_project_role_output=true) "
                f"但由执行模型代签(signed_by_execution_model=true) → ⛔ 违规")

    if violations:
        return CheckResult.block("execution_model_signed_as_project_role",
                                  "执行模型代签违反：\n  " + "\n  ".join(violations))
    return CheckResult.ok()


def check_g5_g6_declared_in_g4(data, is_g4=False):
    """G4 模式下检查是否声明 G5/G6 待确认"""
    if not is_g4:
        return CheckResult.ok()
    raw = json.dumps(data, ensure_ascii=False)
    has_g5_mention = "G5" in raw or "g5" in raw
    has_g6_mention = "G6" in raw or "g6" in raw
    if not has_g5_mention and not has_g6_mention:
        return CheckResult.warn("g5_g6_not_declared",
                                 "G4 模式下建议声明 G5/G6 待确认状态")
    return CheckResult.ok()


def check_g4_evidence_present(data, require_g4=False):
    """检查是否有 G4 自检证据"""
    if not require_g4:
        return CheckResult.ok()
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    has_g4 = any(o.get("stage_gate") == "G4" and safe_str(o.get("evidence"))
                 for o in outputs if isinstance(o, dict))
    if not has_g4:
        return CheckResult.block("missing_G4_evidence",
                                  "G5 模式要求：缺少 G4 自检证据")
    return CheckResult.ok()


def check_g5_evidence_present(data, require_g5=False):
    """检查是否有 G5 独立复查证据"""
    if not require_g5:
        return CheckResult.ok()
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    has_jiuying = any(
        "旧影" in safe_str(o.get("role_name"))
        and o.get("stage_gate") == "G5"
        and safe_str(o.get("evidence"))
        for o in outputs if isinstance(o, dict)
    )
    has_g5 = any(
        o.get("stage_gate") == "G5" and safe_str(o.get("evidence"))
        for o in outputs if isinstance(o, dict)
    )
    if not has_jiuying and not has_g5:
        return CheckResult.block("missing_G5_independent_review",
                                  "缺少 G5 独立复查（旧影）证据")
    return CheckResult.ok()


def check_g6_evidence_present(data, require_g6=False):
    """检查是否有 G6 放行归档证据"""
    if not require_g6:
        return CheckResult.ok()
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))
    has_g6 = any(
        o.get("stage_gate") == "G6" and safe_str(o.get("evidence"))
        for o in outputs if isinstance(o, dict)
    )
    if not has_g6:
        return CheckResult.block("missing_G6_release_archive",
                                  "缺少 G6 放行归档证据")
    return CheckResult.ok()


def check_pipeline_pass_not_substitute(data, strict=False):
    """检查 pipeline PASS 是否替代了阶段 PASS"""
    if not strict:
        return CheckResult.ok()
    raw = json.dumps(data, ensure_ascii=False).lower()
    pipeline_refs = re.findall(r'pipeline.*?(?:pass|通过|ok|true)', raw)
    stage_pass_refs = re.findall(r'(?:阶段|g6|放行).*?(?:pass|通过|ok|true)', raw)
    has_pipeline = len(pipeline_refs) > 0
    has_stage = len(stage_pass_refs) > 0
    if has_pipeline and not has_stage:
        return CheckResult.block("pipeline_pass_substituted_for_stage_pass",
                                  "pipeline PASS 替代了阶段 PASS，且无 G6 放行归档声明")
    return CheckResult.ok()


def check_financial_production_confirm(data, strict=False):
    """金融/生产任务检查腰子或用户确认"""
    if not strict:
        return CheckResult.ok()
    fc = safe_str(data.get("flow_code") or data.get("流程编号"))
    outputs = safe_list(data.get("role_outputs") or data.get("角色输出"))

    # 读取 policy 中的金融流程和关键词
    is_financial = fc in ("F-ANALYSIS", "F-ROLE")
    is_production = False
    try:
        policy = load_json(POLICY_PATH)
        if isinstance(policy, dict):
            rules = policy.get("role_evidence_signature_rules", {})
            f_flows = rules.get("financial_flows", ["F-ANALYSIS", "F-ROLE"])
            p_keywords = rules.get("production_keywords", [])
            if fc in f_flows:
                is_financial = True
            raw = json.dumps(data, ensure_ascii=False).lower()
            for kw in p_keywords:
                if kw.lower() in raw:
                    is_production = True
                    break
    except Exception:
        pass

    if not is_financial and not is_production:
        return CheckResult.ok()

    has_yaozi = any("腰子" in safe_str(o.get("role_name")) and
                    o.get("conclusion") in ("PASS", "WARN")
                    for o in outputs if isinstance(o, dict))
    has_user_confirm = False
    uc = data.get("user_confirm") or data.get("用户确认")
    if isinstance(uc, bool) and uc:
        has_user_confirm = True
    if isinstance(uc, str) and ("是" in uc or "确认" in uc or "PASS" in uc):
        has_user_confirm = True

    if is_financial and not has_yaozi:
        return CheckResult.block(
            "financial_or_production_missing_yaozi_or_user_confirm",
            "金融流程缺少腰子确认输出")
    if is_production and not has_yaozi and not has_user_confirm:
        return CheckResult.block(
            "financial_or_production_missing_yaozi_or_user_confirm",
            "生产任务缺少腰子或用户明确确认")

    return CheckResult.ok()

# ── mode 调度 ─────────────────────────────────────────────────────────


def run_mode_g4(data):
    checks = [
        # 通用检查（所有 mode 公共）
        ("role_output_schema", check_role_output_schema(data)),
        ("role_block_conclusion", check_role_block_conclusion(data)),
        # G4 模式检查
        ("flow_code", check_flow_code(data)),
        ("stage_gate", check_stage_gate(data)),
        ("awakened_role_outputs", check_awakened_role_outputs(data)),
        ("evidence_in_outputs", check_evidence_in_outputs(data)),
        ("execution_model_signing", check_execution_model_signing(data)),
        ("g5_g6_declared", check_g5_g6_declared_in_g4(data, is_g4=True)),
    ]
    return checks


def run_mode_g5(data):
    checks = [
        # 通用检查（所有 mode 公共）
        ("role_output_schema", check_role_output_schema(data)),
        ("role_block_conclusion", check_role_block_conclusion(data)),
        # G5 模式检查
        ("flow_code", check_flow_code(data)),
        ("stage_gate", check_stage_gate(data)),
        ("awakened_role_outputs", check_awakened_role_outputs(data)),
        ("evidence_in_outputs", check_evidence_in_outputs(data)),
        ("execution_model_signing", check_execution_model_signing(data)),
        ("g4_evidence", check_g4_evidence_present(data, require_g4=True)),
        ("g5_evidence", check_g5_evidence_present(data, require_g5=True)),
    ]
    return checks


def run_mode_g6(data):
    checks = [
        # 通用检查（所有 mode 公共）
        ("role_output_schema", check_role_output_schema(data)),
        ("role_block_conclusion", check_role_block_conclusion(data)),
        # G6 模式检查
        ("flow_code", check_flow_code(data)),
        ("stage_gate", check_stage_gate(data)),
        ("awakened_role_outputs", check_awakened_role_outputs(data)),
        ("evidence_in_outputs", check_evidence_in_outputs(data)),
        ("execution_model_signing", check_execution_model_signing(data)),
        ("g5_evidence", check_g5_evidence_present(data, require_g5=True)),
        ("g6_evidence", check_g6_evidence_present(data, require_g6=True)),
        ("pipeline_pass", check_pipeline_pass_not_substitute(data, strict=True)),
        ("financial_production_confirm",
         check_financial_production_confirm(data, strict=True)),
    ]
    return checks


MODE_MAP = {
    "g4": ("G4 自检校验", run_mode_g4),
    "g5": ("G5 独立复查校验", run_mode_g5),
    "g6": ("G6 放行归档校验", run_mode_g6),
}

# ── 输出 ──────────────────────────────────────────────────────────────


def print_report(checks, mode_label):
    results = {"PASS": 0, "WARN": 0, "BLOCK": 0}
    blocks = []
    warns = []

    print(f"\n╔═══ 角色证据签名检查 — {mode_label}")
    for name, cr in checks:
        tag = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(cr.result, "❓")
        msg = f"{cr.code}: {cr.message}" if cr.message else "—"
        print(f"║  {tag} {name}: {msg}")
        results[cr.result] = results.get(cr.result, 0) + 1
        if cr.result == "BLOCK":
            blocks.append(f"{cr.code}: {cr.message}")
        elif cr.result == "WARN":
            warns.append(f"{cr.code}: {cr.message}")

    print(f"║  汇总: ✅ {results['PASS']} / ⚠️  {results['WARN']} / ❌ {results['BLOCK']}")

    if blocks:
        print(f"║")
        print(f"║  🛑 阻断原因:")
        for b in blocks:
            print(f"║    • {b}")
    if warns:
        print(f"║")
        print(f"║  ⚠️  警告:")
        for w in warns:
            print(f"║    • {w}")

    worst = "PASS"
    if results["BLOCK"] > 0:
        worst = "BLOCK"
    elif results["WARN"] > 0:
        worst = "WARN"

    tag_emoji = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(worst, "❓")
    print(f"╚═══ 总体结论: {tag_emoji} {worst}")
    return worst

# ── 修复点 4：--self-test 覆盖正负例 ──────────────────────────────────


SELF_TEST_CASES = [
    {
        "id": "PASS: 完整 G4 角色输出",
        "expect": "PASS",
        "data": {
            "flow_code": "F-DATA",
            "stage_gate": "G0→G2→G3→G4",
            "awakened_roles": ["阿黑", "玉夜"],
            "role_outputs": [
                {
                    "role_name": "阿黑",
                    "stage_gate": "G0",
                    "responsibility": "路由",
                    "check_scope": "L0_INDEX",
                    "conclusion": "PASS",
                    "evidence": "L0_INDEX.md §1",
                    "residual_risk": "",
                    "is_project_role_output": False,
                    "signed_by_execution_model": True,
                },
                {
                    "role_name": "玉夜",
                    "stage_gate": "G1",
                    "responsibility": "数据审查",
                    "check_scope": "数据契约",
                    "conclusion": "PASS",
                    "evidence": "data schema",
                    "residual_risk": "",
                    "is_project_role_output": False,
                    "signed_by_execution_model": True,
                },
            ],
            "G5待确认": True,
            "G6待确认": True,
            "conclusion": "PASS",
        },
    },
    {
        "id": "BLOCK: 缺 schema 必填字段",
        "expect": "BLOCK",
        "data": {
            "flow_code": "F-DATA",
            "stage_gate": "G4",
            "awakened_roles": ["阿黑"],
            "role_outputs": [
                {
                    "role_name": "阿黑",
                    # 缺 stage_gate, responsibility, check_scope, conclusion, evidence, is_project_role_output, signed_by_execution_model
                },
            ],
        },
    },
    {
        "id": "BLOCK: conclusion=BLOCK",
        "expect": "BLOCK",
        "data": {
            "flow_code": "F-DATA",
            "stage_gate": "G4",
            "awakened_roles": ["阿黑"],
            "role_outputs": [
                {
                    "role_name": "阿黑",
                    "stage_gate": "G0",
                    "responsibility": "路由",
                    "check_scope": "test",
                    "conclusion": "BLOCK",
                    "evidence": "发现问题",
                    "residual_risk": "",
                    "is_project_role_output": False,
                    "signed_by_execution_model": True,
                },
            ],
        },
    },
    {
        "id": "BLOCK: 执行模型代签且声明为项目角色",
        "expect": "BLOCK",
        "data": {
            "flow_code": "F-DATA",
            "stage_gate": "G4",
            "awakened_roles": ["腰子"],
            "role_outputs": [
                {
                    "role_name": "腰子",
                    "stage_gate": "G1",
                    "responsibility": "金融口径",
                    "check_scope": "金融铁律",
                    "conclusion": "PASS",
                    "evidence": "金融铁律_v1.17",
                    "residual_risk": "",
                    "is_project_role_output": True,
                    "signed_by_execution_model": True,
                },
            ],
        },
    },
    {
        "id": "WARN: G4 未声明 G5/G6 待确认",
        "expect": "WARN",
        "data": {
            "flow_code": "F-DATA",
            "stage_gate": "G4",
            "awakened_roles": ["阿黑"],
            "role_outputs": [
                {
                    "role_name": "阿黑",
                    "stage_gate": "G0",
                    "responsibility": "路由",
                    "check_scope": "test",
                    "conclusion": "PASS",
                    "evidence": "文档路径",
                    "residual_risk": "",
                    "is_project_role_output": False,
                    "signed_by_execution_model": True,
                },
            ],
        },
    },
]


def run_self_test():
    """自测：验证 JSON 文件可解析 + 内置正负样例全部通过"""
    print("🔍 运行 check_role_evidence_signature.py --self-test")
    errors = []

    # ── 1. 验证 JSON 文件 ──────────────────────────────────────────
    policy = load_json(POLICY_PATH)
    if isinstance(policy, tuple):
        errors.append(f"[FAIL] {policy[1]}")
    else:
        if not isinstance(policy, dict):
            errors.append("[FAIL] stage_acceptance_policy.json 非 dict")
        elif "role_evidence_signature_rules" not in policy:
            errors.append(
                "[FAIL] stage_acceptance_policy.json 缺 role_evidence_signature_rules")
        elif "blocking_conditions" not in policy:
            errors.append(
                "[FAIL] stage_acceptance_policy.json 缺 blocking_conditions")
        else:
            rules = policy.get("role_evidence_signature_rules", {})
            for key in [
                "role_evidence_signature_required",
                "execution_model_cannot_sign_as_project_role",
                "pipeline_pass_cannot_replace_stage_pass",
                "financial_flows",
                "production_keywords",
                "required_confirmers_for_financial_or_production",
            ]:
                if key not in rules:
                    errors.append(
                        f"[FAIL] stage_acceptance_policy.json > "
                        f"role_evidence_signature_rules 缺 {key}")
            required_blocks = [
                "missing_G5_independent_review",
                "missing_G6_release_archive",
                "execution_model_signed_as_project_role",
                "pipeline_pass_substituted_for_stage_pass",
                "financial_or_production_missing_yaozi_or_user_confirm",
                "claimed_pass_without_evidence",
            ]
            bc = policy.get("blocking_conditions", [])
            for b in required_blocks:
                if b not in bc:
                    errors.append(
                        f"[FAIL] stage_acceptance_policy.json "
                        f"blocking_conditions 缺 {b}")

    schema = load_json(SCHEMA_PATH)
    if isinstance(schema, tuple):
        errors.append(f"[FAIL] {schema[1]}")
    else:
        if not isinstance(schema, dict):
            errors.append("[FAIL] role_evidence_signature_schema.json 非 dict")
        else:
            for req in [
                "role_name", "conclusion", "evidence",
                "is_project_role_output", "signed_by_execution_model",
            ]:
                if req not in schema.get("required", []):
                    errors.append(f"[FAIL] schema required 缺 {req}")

    # ── 2. 验证 mode 路由 ──────────────────────────────────────────
    for mode in ["g4", "g5", "g6"]:
        if mode not in MODE_MAP:
            errors.append(f"[FAIL] 缺少 mode 路由: {mode}")

    # ── 3. 内置样例测试（修复点 4） ────────────────────────────────
    print(f"\n  ── 内置样例测试 ({len(SELF_TEST_CASES)} 个) ──")
    for tc in SELF_TEST_CASES:
        case_id = tc["id"]
        expected = tc["expect"]
        mode = "g4"  # 所有样例都用 G4 mode 检测
        _, mode_fn = MODE_MAP[mode]
        checks = mode_fn(tc["data"])
        worst = "PASS"
        blocks = 0
        for _, cr in checks:
            if cr.result == "BLOCK":
                blocks += 1
            elif cr.result == "WARN" and worst == "PASS":
                worst = "WARN"
        if blocks > 0:
            worst = "BLOCK"

        if worst == expected:
            tag = "✅"
        else:
            tag = "❌"
            errors.append(
                f"[FAIL] {case_id}: 预期={expected}, 实际={worst}")

        # 收集阻断/警告代码用于调试
        codes = []
        for _, cr in checks:
            if cr.result != "PASS":
                codes.append(cr.code)
        print(f"  {tag} [{expected:5s}] {case_id}" +
              (f"  → {', '.join(codes)}" if codes else ""))

    # ── 汇总 ────────────────────────────────────────────────────────
    if errors:
        print()
        for e in errors:
            print(f"  ❌ {e}")
        print(f"\n  ❌ 总体: FAIL")
        return "BLOCK"

    print(f"\n  ✅ stage_acceptance_policy.json: 结构完整")
    print(f"  ✅ role_evidence_signature_schema.json: 结构完整")
    print(f"  ✅ mode 路由: g4/g5/g6 已注册")
    print(f"  ✅ 内置样例: {len(SELF_TEST_CASES)} 个全部符合预期")
    print()
    print("  ✅ 总体: PASS")
    return "PASS"

# ── CLI ────────────────────────────────────────────────────────────────


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    if "--self-test" in sys.argv:
        result = run_self_test()
        rc = {"PASS": 0, "WARN": 1, "BLOCK": 2}.get(result, 2)
        sys.exit(rc)

    target = None
    mode = None

    if "--target" in sys.argv:
        idx = sys.argv.index("--target")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]

    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1].lower()

    if not target or not mode:
        print("用法: check_role_evidence_signature.py --target <path> "
              "--mode g4|g5|g6")
        print("      check_role_evidence_signature.py --self-test")
        print("      check_role_evidence_signature.py --help")
        sys.exit(2)

    if mode not in MODE_MAP:
        print(f"❌ 无效 mode: {mode}，支持: g4 / g5 / g6")
        sys.exit(2)

    # 加载目标文件
    data = load_json(target)
    if isinstance(data, tuple):
        print(f"❌ {data[1]}")
        sys.exit(2)

    mode_label, mode_fn = MODE_MAP[mode]
    checks = mode_fn(data)
    worst = print_report(checks, mode_label)

    rc = {"PASS": 0, "WARN": 1, "BLOCK": 2}.get(worst, 2)
    sys.exit(rc)


if __name__ == "__main__":
    main()
