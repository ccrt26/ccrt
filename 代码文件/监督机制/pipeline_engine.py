#!/usr/bin/env python3
"""pipeline_engine.py — 流程状态机引擎 v1.1

Replaces pipeline_engine.ps1 + pipeline_token.ps1.
Manages §七 6-stage lifecycle, outputs executor instructions.
Code level: L1
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
TOKEN_FILE = os.path.join(ROOT, ".claude", "pipeline_active.json")
HISTORY_DIR = os.path.join(ROOT, ".claude", "pipeline_history")
DESIGN_DIR = os.path.join(ROOT, "审计报告", "架构设计")
AUDIT_DIR = os.path.join(ROOT, "审计报告")

STAGE_EXECUTORS = ["情墨", "新安+旧影", "红结", "新安", "红枫", "腰子+青山"]
STAGE_NAMES = ["架构设计", "架构审查", "编码实现", "上线前验证", "灰度部署", "后评估"]

SCRIPT_NAME = "pipeline_engine.py"


def utc_now():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def read_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return json.loads(content) if content else None
    except (json.JSONDecodeError, IOError):
        return None


def write_token(token):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token, f, ensure_ascii=False, indent=2)


def write_history(token):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"pipeline_{ts}_stage{token.get('stage', 0)}.json"
    with open(os.path.join(HISTORY_DIR, fname), "w", encoding="utf-8") as f:
        json.dump(token, f, ensure_ascii=False, indent=2)


def create_token(task, scope=None):
    return {
        "schema_version": "1.0",
        "active": True,
        "task": task,
        "stage": 0,
        "stage_name": "",
        "executor": "",
        "gate_1": "PENDING",
        "gate_2": "PENDING",
        "gate_3": "PENDING",
        "next_action": "invoke_role",
        "attempts": 0,
        "max_attempts": 3,
        "l3_triggered": False,
        "l3_reason": "",
        "loop_context": "",
        "files_scope": scope or [],
        "started": utc_now(),
        "updated": utc_now(),
        "stage_history": [],
    }


def get_status():
    """Return current pipeline status for 阿黑 consumption."""
    token = read_token()
    if not token:
        return {"active": False, "next_action": "done", "message": "No active pipeline"}
    return {
        "active": token.get("active", False),
        "task": token.get("task", ""),
        "stage": token.get("stage", 0),
        "stage_name": token.get("stage_name", ""),
        "executor": token.get("executor", ""),
        "next_action": token.get("next_action", "done"),
        "gate_1": token.get("gate_1", "PENDING"),
        "gate_2": token.get("gate_2", "PENDING"),
        "gate_3": token.get("gate_3", "PENDING"),
        "l3_triggered": token.get("l3_triggered", False),
        "l3_reason": token.get("l3_reason", ""),
    }


def cmd_status():
    print(json.dumps(get_status(), ensure_ascii=False, indent=2))


def cmd_start(task, scope=None):
    token = read_token()
    if token and token.get("active"):
        print(json.dumps({"error": True, "message": "Pipeline already active", "task": token.get("task")}))
        sys.exit(1)
    token = create_token(task, scope)
    token["stage"] = 1
    token["stage_name"] = STAGE_NAMES[0]
    token["executor"] = STAGE_EXECUTORS[0]
    token["next_action"] = "invoke_role"
    token["stage_history"].append({"stage": 1, "name": STAGE_NAMES[0], "status": "started", "time": utc_now()})
    write_token(token)
    write_history(token)
    print(json.dumps(get_status(), ensure_ascii=False, indent=2))


def cmd_advance():
    token = read_token()
    if not token or not token.get("active"):
        print(json.dumps({"error": True, "message": "No active pipeline"}))
        sys.exit(1)

    stage = token.get("stage", 0)
    if stage >= 6:
        token["active"] = False
        token["next_action"] = "done"
        token["updated"] = utc_now()
        token["stage_history"].append({"stage": stage, "name": token.get("stage_name", ""), "status": "complete", "time": utc_now()})
        write_token(token)
        write_history(token)
        print(json.dumps({"next_action": "done", "message": "Pipeline complete"}))
        return

    # Mark current stage complete
    token["stage_history"].append({"stage": stage, "name": token.get("stage_name", ""), "status": "complete", "time": utc_now()})

    # Advance
    stage += 1
    token["stage"] = stage
    token["stage_name"] = STAGE_NAMES[stage - 1]
    token["executor"] = STAGE_EXECUTORS[stage - 1]
    token["attempts"] = 0
    token["next_action"] = "invoke_role"
    token["updated"] = utc_now()
    token["stage_history"].append({"stage": stage, "name": STAGE_NAMES[stage - 1], "status": "started", "time": utc_now()})
    write_token(token)
    write_history(token)
    print(json.dumps(get_status(), ensure_ascii=False, indent=2))


def find_design_doc():
    """Find the most recent design doc with pipeline_stage: complete marker."""
    if not os.path.isdir(DESIGN_DIR):
        return None
    best = None
    for f in sorted(os.listdir(DESIGN_DIR), reverse=True):
        if f.startswith("design_") and f.endswith(".md"):
            fpath = os.path.join(DESIGN_DIR, f)
            try:
                with open(fpath, "r", encoding="utf-8") as df:
                    if "pipeline_stage: complete" in df.read():
                        best = fpath
                        break
            except Exception:
                continue
    return best


def extract_checklist(design_path):
    """Extract checklist JSON from the last ```json block in a design doc."""
    if not design_path or not os.path.exists(design_path):
        return None, "Design doc not found"
    try:
        with open(design_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return None, f"Cannot read design doc: {e}"

    import re as _re
    blocks = list(_re.finditer(r'```json\s*\n(.*?)```', content, _re.DOTALL))
    if not blocks:
        return None, "No checklist JSON found in design doc"
    try:
        return json.loads(blocks[-1].group(1)), None
    except json.JSONDecodeError as e:
        return None, f"Checklist JSON parse error: {e}"


def cmd_validate(output_path, design_doc=None):
    token = read_token()
    if not token or not token.get("active"):
        print(json.dumps({"error": True, "message": "No active pipeline"}))
        sys.exit(1)

    stage = token.get("stage", 0)

    if stage == 1:
        # Gate 1: 情墨 design → check for design doc + checklist signoffs
        if design_doc:
            design_path = design_doc
        else:
            design_path = find_design_doc()
        if not design_path:
            print(json.dumps({"valid": False, "gate": "gate_1",
                   "message": "No design doc with pipeline_stage: complete found"}))
        else:
            checklist, err = extract_checklist(design_path)
            if err:
                # No checklist JSON — allow but warn (backward compat)
                token["gate_1"] = "PASS"
                print(json.dumps({"valid": True, "gate": "gate_1",
                       "message": f"Design doc found (no checklist JSON, WARN): {os.path.basename(design_path)}"}))
            else:
                signoffs = checklist.get("signoffs", {})
                unsigned = []
                if not signoffs.get("情墨", {}).get("signed", False):
                    unsigned.append("情墨")
                if not signoffs.get("腰子", {}).get("signed", False):
                    unsigned.append("腰子")
                if unsigned:
                    print(json.dumps({"valid": False, "gate": "gate_1",
                           "message": f"Checklist unsigned: {', '.join(unsigned)}"}))
                else:
                    token["gate_1"] = "PASS"
                    token["design_doc"] = design_path
                    print(json.dumps({"valid": True, "gate": "gate_1",
                           "message": f"Design doc + checklist OK: {os.path.basename(design_path)}"}))

    elif stage == 4:
        # Gate 2: 红结 coding done → check checklist code_ref backfill
        design_path = token.get("design_doc", "") or find_design_doc()
        checklist, err = extract_checklist(design_path) if design_path else (None, "No design")
        if err or not checklist:
            # Fallback to old behavior
            if output_path and os.path.exists(output_path):
                token["gate_2"] = "PASS"
                print(json.dumps({"valid": True, "gate": "gate_2", "message": f"Output exists: {output_path}"}))
            else:
                print(json.dumps({"valid": False, "message": f"Output not found: {output_path}"}))
        else:
            signoffs = checklist.get("signoffs", {})
            rb = signoffs.get("红结", {})
            if not rb.get("signed", False):
                print(json.dumps({"valid": False, "gate": "gate_2",
                       "message": "红结未签核对清单"}))
            else:
                sections = checklist.get("sections", {})
                empty_refs = []
                for sec_name in ["A_选股规则", "B_评分算法", "C_风控阈值",
                                 "D_否决条件", "E_数据源合规", "F_报告输出"]:
                    for item in sections.get(sec_name, []):
                        if item.get("coder_ok") and not item.get("code_ref", "").strip():
                            empty_refs.append(item.get("id", "?"))
                if empty_refs:
                    print(json.dumps({"valid": False, "gate": "gate_2",
                           "message": f"Missing code_ref for: {', '.join(empty_refs)}"}))
                else:
                    token["gate_2"] = "PASS"
                    print(json.dumps({"valid": True, "gate": "gate_2",
                           "message": "红结已签 + code_ref回填完成"}))

    elif stage == 6:
        # Gate 3: 红枫 deployed → check G section
        design_path = token.get("design_doc", "") or find_design_doc()
        checklist, err = extract_checklist(design_path) if design_path else (None, "No design")
        if err or not checklist:
            if output_path and os.path.exists(output_path):
                token["gate_3"] = "PASS"
                print(json.dumps({"valid": True, "gate": "gate_3", "message": f"Output exists: {output_path}"}))
            else:
                print(json.dumps({"valid": False, "message": f"Output not found: {output_path}"}))
        else:
            signoffs = checklist.get("signoffs", {})
            hf = signoffs.get("红枫", {})
            if not hf.get("signed", False):
                print(json.dumps({"valid": False, "gate": "gate_3",
                       "message": "红枫未签核对清单"}))
            else:
                g_items = checklist.get("sections", {}).get("G_部署验证", [])
                undeployed = [item.get("id", "?") for item in g_items
                              if not item.get("deployer_ok", False)]
                if undeployed:
                    print(json.dumps({"valid": False, "gate": "gate_3",
                           "message": f"G段未部署: {', '.join(undeployed)}"}))
                else:
                    token["gate_3"] = "PASS"
                    print(json.dumps({"valid": True, "gate": "gate_3",
                           "message": "红枫已签 + G段部署完成"}))

    elif stage == 5:
        # Stage 5 (红枫灰度部署): keep old behavior
        if output_path and os.path.exists(output_path):
            token["gate_3"] = "PASS"
            print(json.dumps({"valid": True, "gate": "gate_3", "message": f"Output exists: {output_path}"}))
        else:
            print(json.dumps({"valid": False, "message": f"Output not found: {output_path}"}))

    token["updated"] = utc_now()
    write_token(token)


def cmd_complete():
    token = read_token()
    if not token:
        print(json.dumps({"error": True, "message": "No active pipeline"}))
        sys.exit(1)
    token["active"] = False
    token["next_action"] = "done"
    token["stage"] = 7
    token["stage_name"] = "完成"
    token["updated"] = utc_now()
    token["stage_history"].append({"stage": 7, "name": "完成", "status": "complete", "time": utc_now()})
    write_token(token)
    write_history(token)
    print(json.dumps({"next_action": "done", "message": "Pipeline marked complete"}))


def main():
    parser = argparse.ArgumentParser(description="Pipeline Engine v1.1")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    parser.add_argument("--start", action="store_true", help="Start new pipeline")
    parser.add_argument("--advance", action="store_true", help="Advance to next stage")
    parser.add_argument("--validate", action="store_true", help="Validate current stage")
    parser.add_argument("--complete", action="store_true", help="Mark pipeline complete")
    parser.add_argument("--task", default="", help="Task name (for --start)")
    parser.add_argument("--output-path", default="", help="Output path (for --validate)")
    parser.add_argument("--design-doc", default="", help="Design doc path (for --validate)")
    parser.add_argument("--scope", nargs="*", default=[], help="Files in scope")
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.start:
        cmd_start(args.task, args.scope)
    elif args.advance:
        cmd_advance()
    elif args.validate:
        cmd_validate(args.output_path, args.design_doc)
    elif args.complete:
        cmd_complete()
    else:
        # Default: show status
        cmd_status()


if __name__ == "__main__":
    main()
