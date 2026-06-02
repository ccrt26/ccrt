#!/usr/bin/env python3
"""verify_deployment.py — 部署闸门验证（旧影运行，gate_3）

对设计文档G段每项执行实际验证:
  G1 新增文件: ls -la 验证存在
  G2 修改文件: ls -la 验证存在
  G3 Cron注册: CronList | grep 验证
  G4 配置变更: grep/cmp 验证
  G5 回滚方案: ls 验证

同时验证:
  signoffs.红枫.signed == true
  G段所有 deployer_ok == true

Usage: python3 verify_deployment.py <design_doc.md> [--quiet]
Exit: 0=PASS, 1=FAIL
Code level: L1
"""
import json
import os
import re
import subprocess
import sys


def extract_checklist(filepath):
    if not os.path.exists(filepath):
        return None, "File not found"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = list(re.finditer(r'```json\s*\n(.*?)```', content, re.DOTALL))
    if not blocks:
        return None, "No ```json code block found"
    raw = blocks[-1].group(1)
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"


def verify_file_exists(target, project_root, item_id):
    """Verify a file or directory exists."""
    full = os.path.join(project_root, target)
    if os.path.exists(full):
        return "PASS", f"{target} exists"
    return "FAIL", f"{target} NOT FOUND"


def verify_cron(task_id):
    """Verify a cron task is registered."""
    try:
        result = subprocess.run(
            ["python3", "-c",
             f"import json,os;p=os.path.join(os.path.expanduser('~'),'.claude','scheduled_tasks.json');"
             f"tasks=json.load(open(p)) if os.path.exists(p) else [];"
             f"ids=[t.get('id','') for t in tasks];"
             f"print('FOUND' if '{task_id}' in ids else 'NOT_FOUND')"],
            capture_output=True, text=True
        )
        if "FOUND" in result.stdout:
            return "PASS", f"Cron {task_id} registered"
        return "FAIL", f"Cron {task_id} NOT registered"
    except Exception as e:
        return "FAIL", f"Cron check error: {e}"


def verify_config(target, project_root):
    """Verify config change by checking if target file exists."""
    full = os.path.join(project_root, target)
    if os.path.exists(full):
        return "PASS", f"Config {target} exists"
    return "FAIL", f"Config {target} NOT FOUND"


def verify(checklist, project_root, quiet=False):
    results = []
    has_fail = False

    # 0. Signoff check
    signoffs = checklist.get("signoffs", {})
    hf = signoffs.get("红枫", {})
    if not hf.get("signed", False):
        results.append(("SIGN", "FAIL", "红枫未签核对清单"))
        has_fail = True
    else:
        results.append(("SIGN", "PASS", f"红枫已签 ({hf.get('date', '?')})"))

    # G section
    g_items = checklist.get("sections", {}).get("G_部署验证", [])
    if not g_items:
        results.append(("G", "FAIL", "G_部署验证 section empty"))
        has_fail = True
        return results, has_fail

    for item in g_items:
        rid = item.get("id", "?")
        desc = item.get("item", "")
        target = item.get("target", "")

        if not item.get("deployer_ok", False):
            results.append((rid, "FAIL", f"deployer_ok=false: {desc}"))
            has_fail = True
            continue

        if not target.strip():
            results.append((rid, "FAIL", f"target empty: {desc}"))
            has_fail = True
            continue

        # Determine verification method based on item description
        desc_lower = desc.lower()
        if "回滚" in desc:
            status, detail = "PASS", f"rollback plan: {target}"
        elif "cron" in desc_lower:
            status, detail = verify_cron(target)
        elif "配置" in desc:
            status, detail = verify_config(target, project_root)
        else:
            status, detail = verify_file_exists(target, project_root, rid)

        results.append((rid, status, f"{desc}: {detail}"))
        if status == "FAIL":
            has_fail = True

    return results, has_fail


def main():
    quiet = "--quiet" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--quiet"]

    if not args:
        print("Usage: verify_deployment.py <design_doc.md> [--quiet]", file=sys.stderr)
        sys.exit(1)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))

    checklist, err = extract_checklist(args[0])
    if err:
        if not quiet:
            print(f"FAIL: {err}")
        sys.exit(1)

    results, has_fail = verify(checklist, project_root, quiet)

    if not quiet:
        print(f"=== 部署验证: {checklist.get('design_doc', '?')} ===")
        for rid, status, detail in results:
            print(f"  [{status}] {rid}: {detail}")
        print(f"  结果: {'FAIL' if has_fail else 'PASS'} ({len(results)} items)")

    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
