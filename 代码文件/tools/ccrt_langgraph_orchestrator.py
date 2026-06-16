#!/usr/bin/env python3
"""CCRT LangGraph orchestrator.

This is the local orchestration layer for the CCRT role workflow. The default
mode is dry-run: it executes the graph, validates local CCRT wiring, and calls
the existing stage-gate evaluator with synthetic G4 evidence. Live mode must be
selected explicitly and routes G3/G4 to Claude Code streaming.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from check_temp_analysis_force_route import classify_request as classify_temp_analysis_request
DEFAULT_CONFIG = ROOT / "代码文件" / "tools" / "ccrt_langgraph_config.json"
DEFAULT_OUTPUT_ROOT = Path("/private/tmp/ccrt_langgraph_orchestrator")

FLOW_HINTS = {
    "F-FIX": ["修复", "bug", "错误", "不一致", "失败", "报错", "补修", "闸门已抓到"],
    "F-ANALYSIS": ["金融分析", "分析逻辑", "风控规则", "操作规则", "白皮书", "股票分析"],
    "F-ROLE": ["角色", "协作", "统一解读", "职责", "唤醒"],
    "F-GATE": ["闸门", "验收脚本", "check_", "schema", "policy", "检查脚本"],
    "F-SCHEDULE": ["调度", "定时", "运行入口", "自动化编排", "LangGraph", "编排"],
    "F-ARCH": ["架构", "地基", "目录", "契约", "阶段制度", "流程"],
    "F-REPORT": ["日报", "报告", "模板", "生成逻辑", "MD", "JSON"],
    "F-DATA": ["数据", "字段", "日期", "来源", "sidecar", "事实"],
    "F-EVAL": ["后评估", "T+1", "T+5", "回填", "评分", "复盘"],
    "F-KNOW": ["知识库", "信号库", "L5", "L2", "知识条目"],
    "F-MIGRATE": ["迁移", "归档", "搬家", "索引"],
    "F-FEATURE": ["新增功能", "新增指标", "新增模块", "能力新增"],
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cmd(cmd, timeout=120):
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def run_cmd_passthrough(cmd, timeout=300):
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": "",
        "stderr": "",
    }


def safe_task_id(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value or "").strip("-")
    if cleaned:
        return cleaned[:80]
    return "CCRT-LANGGRAPH-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def build_run_record(task_id, mode, config_path, state):
    stage_gate_parsed = state.get("stage_gate", {}).get("parsed", {})
    g3_g4 = state.get("g3_g4", {})
    g4_evidence = g3_g4.get("evidence", {})
    user_report = state.get("user_report", {})
    dry_run = mode == "dry_run"
    return {
        "task_id": task_id,
        "generated_at": utc_now(),
        "mode": mode,
        "config": rel(config_path),
        "orchestration_status": "COMPLETE",
        "dry_run_not_implementation": dry_run,
        "stage_gate_status": stage_gate_parsed.get("status", ""),
        "implementation_status": g4_evidence.get("result", ""),
        "actual_actor": g4_evidence.get("actual_actor", ""),
        "implementation_actor": g4_evidence.get("implementation_actor", ""),
        "live_model_call": bool(g4_evidence.get("live_model_call")),
        "changed_files": g4_evidence.get("changed_files", []),
        "g4_evidence_path": g3_g4.get("evidence_path", ""),
        "user_report": user_report,
        "g3_g4_summary": {
            "mode": g3_g4.get("mode", ""),
            "role_runtime": g3_g4.get("role_runtime", ""),
            "terminal_stream_summary": g3_g4.get("terminal_stream_summary", {}),
        },
        "state": state,
    }


def git_changed_paths():
    """Return list of files different from HEAD (staged + unstaged + untracked).

    Uses 'git diff --name-only HEAD' for tracked file changes and
    'git ls-files --others --exclude-standard' for untracked files.
    This is robust even when the working tree starts dirty.
    """
    diff = run_cmd(["git", "diff", "--name-only", "HEAD"], timeout=60)
    paths = [p.strip() for p in diff.get("stdout", "").splitlines() if p.strip()]
    untracked = run_cmd(
        ["git", "ls-files", "--others", "--exclude-standard"], timeout=60
    )
    paths.extend(
        p.strip() for p in untracked.get("stdout", "").splitlines() if p.strip()
    )
    return sorted(set(paths))


def git_status_paths():
    """Return list of changed file paths from git status --short."""
    result = run_cmd(["git", "status", "--short"], timeout=60)
    paths = []
    for line in result.get("stdout", "").splitlines():
        if not line.strip():
            continue
        paths.append(line[3:].strip())
    return paths


def classify_requirement(text):
    force_policy = load_json(ROOT / "00_项目地基/05_流程与角色/temp_analysis_force_route_policy_v0.1.json")
    temp_route = classify_temp_analysis_request(text, force_policy)
    if temp_route.get("decision") == "TEMP_ANALYSIS_REQUIRED":
        return "F-ANALYSIS", "命中临时分析强制路由 TEMP_ANALYSIS_REQUIRED；必须走 TemporaryAnalysisBrief -> gate -> renderer；D07_v1.2 默认内置砺石校准"

    scores = {}
    for flow, hints in FLOW_HINTS.items():
        score = 0
        for hint in hints:
            if hint.lower() in text.lower():
                score += 1
        if score:
            scores[flow] = score

    if not scores:
        return "F-ARCH", "未命中明确关键词，按架构/流程设计类任务保守路由"

    # Match CCRT priority: FIX first, then analysis/data, then report/feature,
    # then arch/migrate. The numeric order keeps equal scores stable.
    priority = {
        "F-FIX": 100,
        "F-ANALYSIS": 90,
        "F-DATA": 90,
        "F-REPORT": 80,
        "F-FEATURE": 80,
        "F-GATE": 78,
        "F-SCHEDULE": 76,
        "F-ROLE": 75,
        "F-ARCH": 70,
        "F-EVAL": 60,
        "F-KNOW": 55,
        "F-MIGRATE": 50,
    }
    flow = sorted(scores, key=lambda f: (scores[f], priority.get(f, 0)), reverse=True)[0]
    return flow, f"命中关键词分数 {scores[flow]}，按路由优先级选择 {flow}"


def get_flow(flow_routes, flow_code):
    for flow in flow_routes.get("flows", []):
        if flow.get("flow_code") == flow_code:
            return flow
    return {}


def role_mapping(role_matrix, flow_code):
    mapping = role_matrix.get("flow_role_mapping", {})
    return mapping.get(flow_code, [])


def compact_role_outputs(roles, gates, precise_requirement):
    outputs = []
    target = precise_requirement.get("goal", "")
    for role in roles:
        role_name = role
        if role in ("问题所属角色", "玉夜/旧影", "全部解释角色"):
            role_name = role
        gate = "G0" if role == "阿黑" else "G2"
        result = "PASS"
        status_note = "本阶段角色输出候选"
        if role in ("腰子", "青山", "流金", "山猫", "信鸽", "玉夜") and "G1" in gates:
            gate = "G1"
        if role == "旧影":
            gate = "G5"
            result = "SCHEDULED"
            status_note = "后续 G5 独立复查角色，G1/G2 不提前给结论"
        outputs.append({
            "role": role_name,
            "role_runtime": f"{role_name}@Codex" if role_name != "红结" else "红结@DeepSeek",
            "gate": gate,
            "responsibility": "按角色职责生成本阶段输出",
            "target": target,
            "result": result,
            "status_note": status_note,
            "formal_signoff": False,
            "candidate_only": True,
        })
    return outputs


def flow_needs_financial_team(flow_code, requirement):
    text = requirement.get("goal", "")
    if any(word in text for word in ("重点股票", "日报", "深度分析", "金融分析", "分析逻辑", "金融团队", "全团")):
        return True
    if flow_code in ("F-ANALYSIS", "F-ROLE"):
        return True
    if flow_code == "F-REPORT" and any(word in text for word in ("日报", "报告", "股票", "金融", "分析逻辑")):
        return True
    return False


def materialize_role_outputs(flow_code, roles, precise_requirement):
    """Create structured G1/G2 role outputs for the executor.

    These are stage artifacts generated by the Codex/GPT planning side. They are
    not formal signatures and must not be treated as G5/G6 signoff.
    """
    target = precise_requirement.get("goal", "")
    outputs = []
    if flow_needs_financial_team(flow_code, precise_requirement):
        finance_roles = [
            ("山猫", "宏观/大盘/板块相位", "检查板块相位和宏观背景只作背景约束，不单独触发交易动作。"),
            ("信鸽", "事件/公告/消息面", "检查是否存在强制否决事件；无事件时不得编造催化。"),
            ("玉夜", "行情/K线/资金/融资/数据一致性", "检查数据新鲜度、缺失项和降级披露；融资缺失按规则进入 evidence_gap_requests。"),
            ("流金", "风控/仓位/止损/红黄绿灯", "检查仓位上限、止损线和禁止动作是否服从 baseline。"),
            ("青山", "信号/胜率/样本/技术结构", "检查信号不得脱离样本和胜率，未确认时不得升级为强动作。"),
            ("砺石", "D07_v1.2 内置方法校准/反证审查", "检查强动作、追买卖、破位处理是否经过反证和边界校准；不得作为按需可选角色。"),
            ("腰子", "整合分歧并给出最终明日动作", "整合全团意见，输出 P0 动作、触发条件、失效条件和 conclusion_strength。"),
        ]
        for role, duty, conclusion in finance_roles:
            outputs.append({
                "角色名": role,
                "参与阶段门": "G1",
                "本阶段职责": duty,
                "检查对象": target,
                "结论": "PASS",
                "依据": [
                    "重点股票跟踪分析逻辑白皮书_v3.6.3",
                    "统一解读/interpretation_schema.json",
                    "00_项目地基/05_流程与角色/role_matrix.json",
                ],
                "遗留问题": "",
                "执行要求": conclusion,
                "candidate_only": True,
                "formal_signoff": False,
            })
    if "情墨" in roles or flow_code in ("F-REPORT", "F-SCHEDULE", "F-ARCH"):
        outputs.append({
            "角色名": "情墨",
            "参与阶段门": "G2",
            "本阶段职责": "架构/入口/自动化设计",
            "检查对象": target,
            "结论": "PASS",
            "依据": [
                "00_项目地基/05_流程与角色/flow_routes.json",
                "scripts/run_daily_report_one_by_one.py",
                "scripts/run_daily_report_html_only.py",
            ],
            "遗留问题": "",
            "执行要求": "优先复用现有入口和验收脚本，不绕开 D07_v1.2 闸门。",
            "candidate_only": True,
            "formal_signoff": False,
        })
    return outputs


def run_terminal_stream(config, task_id, prompt, stream_mode):
    adapter = config.get("orchestration_tools", {}).get(
        "ccrt_terminal_stream_adapter",
        "代码文件/tools/ccrt_terminal_stream_adapter.py",
    )
    python_bin = config["runtime"]["python"]
    return run_cmd_passthrough([
        python_bin,
        adapter,
        "--task-id",
        task_id,
        "--mode",
        stream_mode,
        "--prompt",
        prompt,
        "--summary-json",
    ], timeout=300)


def parse_stream_summary(result):
    stdout = result.get("stdout", "")
    if not stdout:
        return {}
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "summary" in data:
            return data["summary"]
    return {}


def parse_stream_end_reason(config, task_id):
    path = Path(stream_log_path(config, task_id))
    if not path.exists():
        return ""
    reason = ""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("event") == "stream_end" and payload.get("reason"):
                reason = payload.get("reason", "")
            if payload.get("event") == "live_model_preflight" and payload.get("diagnosis"):
                reason = payload.get("diagnosis", "")
    except Exception:
        return reason
    return reason


def stream_log_path(config, task_id):
    log_root = Path(config.get("terminal_streaming", {}).get("log_root", "/private/tmp/ccrt_langgraph_streams"))
    keep = []
    for ch in task_id or "stream":
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("-")
    safe = "".join(keep).strip("-")[:100] or "stream"
    return str(log_root / safe / f"{safe}_terminal_stream.jsonl")


def hygiene_preflight(state):
    """Git workspace hygiene preflight — runs before G3/G4 live execution.

    In dry_run mode: always PASS (no workspace check needed).
    In live mode: calls git_workspace_hygiene.py --report.
    """
    live = state.get("mode") == "live"
    if not live:
        return {
            **state,
            "hygiene_preflight": {
                "status": "PASS",
                "reason": "dry_run_mode_no_hygiene_check",
                "hygiene_checked": False,
            },
        }

    config = state["config"]
    python_bin = config["runtime"]["python"]
    hygiene_script = config.get("orchestration_tools", {}).get(
        "git_workspace_hygiene",
        "scripts/git_workspace_hygiene.py",
    )

    result = run_cmd([python_bin, hygiene_script, "--report"], timeout=30)
    if result["returncode"] != 0:
        return {
            **state,
            "hygiene_preflight": {
                "status": "BLOCK",
                "reason": f"hygiene_script_error: returncode={result['returncode']}",
                "hygiene_checked": True,
                "cmd_result": result,
            },
        }

    try:
        report = json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        return {
            **state,
            "hygiene_preflight": {
                "status": "BLOCK",
                "reason": f"hygiene_report_parse_error: {exc}",
                "hygiene_checked": True,
                "cmd_result": result,
            },
        }

    hygiene_status = report.get("status", "BLOCK")
    blockers = report.get("blockers", [])
    allow_dirty = report.get("allow_dirty_index", False)

    if hygiene_status == "BLOCK" and not allow_dirty:
        return {
            **state,
            "hygiene_preflight": {
                "status": "BLOCK",
                "reason": "; ".join(blockers) if blockers else "hygiene_check_failed",
                "hygiene_checked": True,
                "blockers": blockers,
                "report": report,
            },
        }

    return {
        **state,
        "hygiene_preflight": {
            "status": "PASS",
            "reason": "workspace_hygiene_ok",
            "hygiene_checked": True,
            "report": report,
            "warnings": blockers if allow_dirty else [],
        },
    }


def preflight_role_boundary(state):
    """Preflight check: confirm role assignments respect the role boundary
    before entering G3/G4 live execution.

    Rules:
    - Codex actor → only G0, G1, G2, G5 gates
    - DeepSeek actor → only G3, G4 gates
    - G3_IMPL_ALLOWED_BY_USER env var overrides the Codex-in-G3 check
    """
    live = state.get("mode") == "live"
    if not live:
        return {
            **state,
            "preflight": {
                "status": "PASS",
                "reason": "dry_run_mode_no_role_enforcement",
                "role_boundary_validated": False,
            },
        }

    role_design = state.get("role_design", {})
    active_roles = role_design.get("active_roles", [])

    issues = []
    for role_item in active_roles:
        role_runtime = role_item.get("role_runtime", "")
        gate = role_item.get("gate", "")
        actor = role_runtime.split("@")[-1] if "@" in role_runtime else role_runtime
        try:
            gate_num = int(gate.replace("G", "")) if gate.startswith("G") else 0
        except ValueError:
            gate_num = 0

        if actor == "Codex" and gate_num in (3, 4):
            issues.append(f"role_violation: Codex assigned to {gate}; Codex must not execute G3/G4")
        if actor == "DeepSeek" and gate_num not in (3, 4):
            issues.append(f"role_violation: DeepSeek assigned to {gate}; DeepSeek must be G3/G4 only")

    g3_override = os.environ.get("G3_IMPL_ALLOWED_BY_USER", "").lower() == "true"

    if issues and g3_override:
        return {
            **state,
            "preflight": {
                "status": "PASS",
                "warnings": issues,
                "reason": "G3_IMPL_ALLOWED_BY_USER override applied",
                "role_boundary_validated": True,
                "override_applied": True,
            },
        }

    if issues:
        return {
            **state,
            "preflight": {
                "status": "BLOCK",
                "reason": "; ".join(issues),
                "role_boundary_validated": False,
                "issues": issues,
                "how_to_fix": (
                    "Set G3_IMPL_ALLOWED_BY_USER=true to override, or "
                    "reassign role runtime so Codex handles G0-G2/G5 "
                    "and DeepSeek handles G3/G4."
                ),
            },
        }

    return {
        **state,
        "preflight": {
            "status": "PASS",
            "reason": "role_boundary_compliant",
            "role_boundary_validated": True,
        },
    }


def make_live_execution_prompt(state):
    req = state["precise_requirement"]
    route = state["g0_route"]
    role_design = state["role_design"]
    role_lines = []
    for item in role_design.get("active_roles", []):
        role_lines.append(
            f"- {item.get('role_runtime')}: gate={item.get('gate')} result={item.get('result')} note={item.get('status_note')}"
        )
    materialized = role_design.get("materialized_role_outputs", [])
    materialized_text = json.dumps(materialized, ensure_ascii=False, indent=2)
    return f"""已调用 skill: ccrt-standard-flow
流程阶段: G3/G4
本输出性质: 红结@DeepSeek 执行包

你现在是 Claude Code CLI 中接入的 DeepSeek 执行模型，运行实例记为“红结@DeepSeek”。
身份边界：你只执行 G3，并生成 G4 自检候选；不得声称 G5 旧影 PASS、G6 放行、归档、推送或任何 formal_signoff。

【标准需求】
目标：{req.get('goal')}
边界：{req.get('boundary')}
输入：{json.dumps(req.get('inputs', []), ensure_ascii=False)}
输出：{json.dumps(req.get('outputs', []), ensure_ascii=False)}
验收：{json.dumps(req.get('acceptance', []), ensure_ascii=False)}
禁止事项：{json.dumps(req.get('forbidden', []), ensure_ascii=False)}
时效：{req.get('timeliness')}
风险等级：{req.get('risk_level')}

【G0 路由】
flow_code：{route.get('flow_code')}
flow_name：{route.get('flow_name')}
required_gates：{json.dumps(route.get('required_gates', []), ensure_ascii=False)}
required_roles：{json.dumps(route.get('required_roles', []), ensure_ascii=False)}

【G1/G2 角色运行计划候选】
{chr(10).join(role_lines)}

【G1/G2 已物化角色输出】
{materialized_text}

【报告/金融任务强制规则】
1. 若任务涉及重点股票日报、深度分析、金融分析逻辑或角色协作，必须把上述金融团队角色输出写入产物证据链。
2. 日报 sidecar 必须包含 framework_version=D07_v1.2、logic_version 指向 v3.6.3、interpretation_id、hypotheses、evidence_gap_requests、conclusion_strength、rule_refs、knowledge_refs、d07_interpretation、unified_interpretation。
3. 金融团队讨论必须是 materialized 的 daily_discussion，不得只写角色名称占位。
4. 融资/其他可降级数据缺失时，必须按项目 freshness_rules.json 和 D07 evidence_gap_requests 处理，不得静默缺失，也不得随意改金融规则。
5. 完成后必须运行 scripts/check_daily_d07_v12_contract.py；报告任务还要运行 baseline、数值、MD-sidecar、解读质量、数据完整度相关验收。

【执行规则】
1. 先用只读命令定位最新逻辑、目标文件、数据源和验收脚本。
2. 只修改完成目标所需的最小文件范围。
3. 如果目标是报告生成，优先调用项目已有生成脚本，不要手写大段报告。
4. 不要批量处理无关股票。
5. 不要执行 git commit/push/tag/merge。
6. 输出最后必须包含“G4自检候选”，列出 changed_files、commands_run、result、risks。
7. 若缺少关键数据或权限，返回 BLOCK，并说明缺什么。
8. 不要全文读取大文件；优先使用 rg、find、sed 小范围读取和项目已有命令。
9. 已有明确生成脚本时，直接调用脚本并用验收脚本复核，不要自行重写业务逻辑。
10. 如果现有脚本不符合上述已确定规范，只允许做最小程序修复，并在 G4 说明依据；不得自创金融口径。
"""


def g3_g4_execution(state):
    """G3/G4 execution node — module-level for testability.

    Handles the live execution stream (or dry-run mock), collects evidence,
    and produces structured G4 candidate output. Also handles preflight BLOCK
    by generating structured BLOCK evidence without crashing.
    """
    preflight = state.get("preflight", {})
    preflight_status = preflight.get("status", "PASS")
    hygiene = state.get("hygiene_preflight", {})
    hygiene_status = hygiene.get("status", "PASS")

    # Collect all preflight blockers
    preflight_blockers = []
    if preflight_status == "BLOCK":
        preflight_blockers.append(f"role_boundary: {preflight.get('reason', '')}")
    if hygiene_status == "BLOCK":
        preflight_blockers.append(f"hygiene: {hygiene.get('reason', '')}")

    # Initialize output_dir and task_id BEFORE preflight block check
    # (preflight BLOCK path writes evidence using these variables)
    task_id = state["task_id"]
    output_dir = Path(state["output_dir"])

    # If any preflight blocked, produce BLOCK evidence directly (no stream)
    if preflight_blockers:
        block_reason = "; ".join(preflight_blockers)
        blocked_evidence = {
            "task_id": task_id,
            "gate": "G4",
            "artifact_type": "candidate",
            "result": "BLOCK",
            "generated_at": utc_now(),
            "generated_by": "ccrt_langgraph_orchestrator.py",
            "role_runtime": "红结@DeepSeek",
            "actual_actor": "",
            "execution_model": "",
            "implementation_actor": "",
            "live_model_call": False,
            "codex_write_detected": False,
            "preflight_blocked": True,
            "preflight_reason": block_reason,
            "g3_impl_allowed_by_user": False,
            "tool_calls": [],
            "changed_files": [],
            "commands": [],
            "g1_g2_role_outputs": state.get("role_design", {}).get("materialized_role_outputs", []),
            "role_outputs_required_for_g3": state.get("role_design", {}).get("role_outputs_required_for_g3", False),
            "claims_formal_signoff": False,
            "hygiene_report": hygiene.get("report"),
        }
        evidence_path = output_dir / f"{task_id}_G4_self_check_candidate.json"
        write_json(evidence_path, blocked_evidence)
        return {
            **state,
            "g3_g4": {
                "role_runtime": "红结@DeepSeek",
                "mode": state["mode"],
                "terminal_stream_result": {"returncode": 2},
                "terminal_stream_summary": {
                    "status": "BLOCK",
                    "reason": f"preflight_blocked: {block_reason}",
                },
                "evidence_path": str(evidence_path),
                "evidence": blocked_evidence,
            },
        }
    live = state.get("mode") == "live"
    stream_mode = "claude-stream" if live else "mock"
    prompt = make_live_execution_prompt(state) if live else (
        "你现在以红结@DeepSeek运行。"
        "本次为 LangGraph dry-run 直播验证，不修改任何业务文件；"
        "请只确认执行阶段直播通道可用。"
    )
    before_paths = git_status_paths() if live else []
    stream_result = run_terminal_stream(state["config"], task_id, prompt, stream_mode)
    after_paths = git_status_paths() if live else []
    stream_reason = parse_stream_end_reason(state["config"], task_id) if live else ""
    stream_summary = {
        "status": "COMPLETE" if stream_result.get("returncode") == 0 else "BLOCK",
        "task_id": task_id,
        "mode": stream_mode,
        "log_path": stream_log_path(state["config"], task_id),
        "reason": stream_reason,
    }
    passed = stream_result.get("returncode") == 0
    g3_override = os.environ.get("G3_IMPL_ALLOWED_BY_USER", "").lower() == "true"
    actual_actor = "deepseek_live" if live else "mock"

    # Collect hygiene preflight state for evidence
    hygiene_report = hygiene.get("report")
    hygiene_blockers = hygiene.get("blockers", [])
    git_status_before = before_paths
    if hygiene_report:
        git_status_before = {
            "porcelain_count": len(before_paths),
            "hygiene_summary": hygiene_report.get("summary"),
            "hygiene_blockers": hygiene_blockers,
        }

    # Try to parse DeepSeek executor's own G4 output for changed_files
    live_changed_files = git_changed_paths() if live else []
    if live:
        stream_log = Path(stream_log_path(state["config"], task_id))
        if stream_log.exists():
            try:
                for line in stream_log.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    summary = payload.get("summary", {})
                    if summary and isinstance(summary, dict):
                        deepseek_changed = summary.get("changed_files", [])
                        if deepseek_changed and isinstance(deepseek_changed, list):
                            live_changed_files = deepseek_changed
                            break
                    cf = payload.get("changed_files", [])
                    if cf and isinstance(cf, list) and len(cf) > 0:
                        live_changed_files = cf
            except Exception:
                pass

    evidence = {
        "task_id": task_id,
        "gate": "G4",
        "artifact_type": "candidate",
        "result": "PASS" if passed else "BLOCK",
        "generated_at": utc_now(),
        "generated_by": "ccrt_langgraph_orchestrator.py",
        "role_runtime": "红结@DeepSeek",
        "actual_actor": actual_actor,
        "execution_model": "deepseek-via-claude-code" if live else "mock",
        "implementation_actor": actual_actor,
        "live_model_call": live,
        "codex_write_detected": False,
        "codex_read_only_planning": True,
        "g3_impl_allowed_by_user": g3_override,
        "tool_calls": [
            {
                "name": "terminal_stream_adapter",
                "mode": stream_mode,
                "returncode": stream_result.get("returncode"),
                "reason": stream_reason or "completed",
                "log_path": stream_summary.get("log_path", ""),
            },
        ],
        "hygiene_preflight": {
            "status": hygiene_status,
            "blockers": hygiene_blockers,
            "summary": hygiene_report.get("summary") if hygiene_report else None,
        },
        "dry_run": not live,
        "terminal_stream": {
            "enabled": True,
            "mode": stream_mode,
            "returncode": stream_result.get("returncode"),
            "log_path": stream_summary.get("log_path", ""),
            "reason": stream_reason,
        },
        "claims_formal_signoff": False,
        "g1_g2_role_outputs": state.get("role_design", {}).get("materialized_role_outputs", []),
        "role_outputs_required_for_g3": state.get("role_design", {}).get("role_outputs_required_for_g3", False),
        "changed_files": live_changed_files,
        "changed_files_source": "live_executor" if live and live_changed_files else "git_diff",
        "git_status_before": git_status_before,
        "git_status_after": after_paths,
        "commands": [
            {
                "name": "terminal_stream_adapter",
                "result": "PASS" if passed else "BLOCK",
                "note": f"Terminal stream adapter completed in {stream_mode} mode.",
                "log_path": stream_summary.get("log_path", ""),
                "reason": stream_reason,
            },
            {
                "name": "orchestrator_execution_mode",
                "result": "PASS" if passed else "BLOCK",
                "note": f"mode={state['mode']}; live_model_call={live}"
            },
            {
                "name": "git_workspace_hygiene",
                "result": "PASS" if hygiene_status == "PASS" else "BLOCK",
                "note": f"hygiene_status={hygiene_status}; blockers={len(hygiene_blockers)}"
            }
        ],
    }
    evidence_path = output_dir / f"{task_id}_G4_self_check_candidate.json"
    write_json(evidence_path, evidence)
    return {
        **state,
        "g3_g4": {
            "role_runtime": "红结@DeepSeek",
            "mode": state["mode"],
            "terminal_stream_result": stream_result,
            "terminal_stream_summary": stream_summary,
            "evidence_path": str(evidence_path),
            "evidence": evidence,
        },
    }


def make_graph():
    graph = StateGraph(dict)

    def requirement_precision(state):
        raw = state["raw_requirement"]
        live = state.get("mode") == "live"
        precise = {
            "original_requirement": raw,
            "goal": raw.strip(),
            "boundary": "live 模式允许在项目工作区内按目标最小范围真实执行；dry-run 模式不改业务文件。" if live else "仅在本地 LangGraph 编排范围内推进；未显式开启 live mode 时不改业务文件。",
            "inputs": ["用户自然语言需求", "CCRT 本地流程与角色规则", "LangGraph 本地配置", "项目现有脚本和数据"],
            "outputs": ["标准需求", "G0 路由", "角色运行计划", "G3/G4 执行证据", "三态汇报"],
            "acceptance": ["LangGraph 图可执行", "本地配置可读取", "G3/G4 有执行证据", "阶段门脚本可处理证据"],
            "forbidden": ["不得伪造 formal_signoff", "不得执行 git commit/push/tag/merge", "不得批量处理无关股票"],
            "timeliness": "本地配置实时核查；不依赖行情或外部事实。",
            "risk_level": "MEDIUM_LIVE_EXECUTION" if live else "LOW_DRY_RUN",
        }
        return {**state, "precise_requirement": precise}

    def g0_route(state):
        config = state["config"]
        flow_routes = load_json(ROOT / config["ccrt_rules"]["flow_routes"])
        role_matrix = load_json(ROOT / config["ccrt_rules"]["role_matrix"])
        flow_code, reason = classify_requirement(state["precise_requirement"]["goal"])
        flow = get_flow(flow_routes, flow_code)
        roles = role_mapping(role_matrix, flow_code)
        gates = flow.get("stages", {}).get("required_gates", ["G0", "G3", "G4", "G5", "G6"])
        return {
            **state,
            "g0_route": {
                "role_runtime": "阿黑@Codex",
                "flow_code": flow_code,
                "flow_name": flow.get("name", ""),
                "reason": reason,
                "required_gates": gates,
                "required_roles": roles,
                "candidate_only": True,
                "formal_signoff": False,
            },
        }

    def role_design(state):
        route = state["g0_route"]
        roles = route.get("required_roles", [])
        gates = route.get("required_gates", [])
        role_outputs = compact_role_outputs(roles, gates, state["precise_requirement"])
        materialized_outputs = materialize_role_outputs(route.get("flow_code", ""), roles, state["precise_requirement"])
        return {
            **state,
            "role_design": {
                "role_runtime": "对应角色@Codex",
                "active_roles": role_outputs,
                "materialized_role_outputs": materialized_outputs,
                "role_outputs_required_for_g3": bool(materialized_outputs),
                "g1_g2_status": "PASS",
                "candidate_only": True,
                "formal_signoff": False,
            },
        }

    def stage_gate(state):
        config = state["config"]
        python_bin = config["runtime"]["python"]
        script = config["stage_gate_tools"]["stage_gate_auto_advance"]
        result = run_cmd([
            python_bin,
            script,
            "--evidence",
            state["g3_g4"]["evidence_path"],
        ])
        parsed = {}
        if result["stdout"]:
            try:
                parsed = json.loads(result["stdout"])
            except json.JSONDecodeError:
                parsed = {"parse_error": result["stdout"]}
        return {
            **state,
            "stage_gate": {
                "tool": script,
                "result": result,
                "parsed": parsed,
            },
        }

    def normalize_report(state):
        parsed = state.get("stage_gate", {}).get("parsed", {})
        failures = []
        if parsed.get("status") != "ADVANCE_READY":
            failures.append("stage_gate_not_advance_ready")
        status = "COMPLETE" if not failures else "BLOCK"
        if status == "COMPLETE" and state.get("mode") == "live":
            message = "LangGraph live 编排已跑通，G3/G4 已交给 Claude Code/DeepSeek 执行。"
        elif status == "COMPLETE":
            message = "LangGraph 编排器 dry-run 已跑通，未执行真实业务修改。"
        elif state.get("mode") == "dry_run":
            message = "BLOCK: dry-run 只验证编排通道；阶段门未放行真实实现证据。"
        else:
            message = "BLOCK: LangGraph 编排器未通过阶段门。"
        return {
            **state,
            "user_report": {
                "user_visible_status": status,
                "user_visible_message": message,
                "failures": failures,
                "dry_run_not_implementation": state.get("mode") == "dry_run",
                "stage_gate_status": parsed.get("status", ""),
                "internal_stage_evidence_hidden_from_user": True,
            },
        }

    graph.add_node("requirement_precision", requirement_precision)
    graph.add_node("g0_route_ahei_codex", g0_route)
    graph.add_node("g1_g2_role_modes_codex", role_design)
    graph.add_node("preflight_role_boundary", preflight_role_boundary)
    graph.add_node("hygiene_preflight", hygiene_preflight)
    graph.add_node("g3_g4_hongjie_deepseek", g3_g4_execution)
    graph.add_node("stage_gate_auto_advance", stage_gate)
    graph.add_node("user_report_normalize", normalize_report)

    graph.add_edge(START, "requirement_precision")
    graph.add_edge("requirement_precision", "g0_route_ahei_codex")
    graph.add_edge("g0_route_ahei_codex", "g1_g2_role_modes_codex")
    graph.add_edge("g1_g2_role_modes_codex", "preflight_role_boundary")
    graph.add_edge("preflight_role_boundary", "hygiene_preflight")
    graph.add_edge("hygiene_preflight", "g3_g4_hongjie_deepseek")
    graph.add_edge("g3_g4_hongjie_deepseek", "stage_gate_auto_advance")
    graph.add_edge("stage_gate_auto_advance", "user_report_normalize")
    graph.add_edge("user_report_normalize", END)
    return graph.compile()


def run_orchestrator(args):
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = load_json(config_path)
    task_id = args.task_id or safe_task_id("CCRT-LANGGRAPH-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output_dir = Path(args.output_dir) / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    app = make_graph()
    state = app.invoke({
        "task_id": task_id,
        "raw_requirement": args.requirement,
        "mode": args.mode,
        "config": config,
        "config_path": str(config_path),
        "output_dir": str(output_dir),
    })
    run_record = output_dir / f"{task_id}_langgraph_run_record.json"
    write_json(run_record, build_run_record(task_id, args.mode, config_path, state))
    state["run_record"] = str(run_record)
    return state


def main():
    parser = argparse.ArgumentParser(description="CCRT LangGraph orchestrator")
    parser.add_argument("requirement", nargs="?", default="调通 CCRT LangGraph 自动编排流程")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--mode", choices=["dry_run", "live"], default="dry_run")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--json", action="store_true", help="Print full internal JSON")
    args = parser.parse_args()

    state = run_orchestrator(args)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "user_visible_status": state["user_report"]["user_visible_status"],
            "user_visible_message": state["user_report"]["user_visible_message"],
            "task_id": state["task_id"],
            "flow_code": state["g0_route"]["flow_code"],
            "stage_gate_status": state["stage_gate"]["parsed"].get("status", ""),
            "dry_run_not_implementation": state["user_report"].get("dry_run_not_implementation", False),
            "run_record": state["run_record"],
        }, ensure_ascii=False, indent=2))

    return 0 if state["user_report"]["user_visible_status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
