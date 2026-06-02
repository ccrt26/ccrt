#!/usr/bin/env python3
"""check_checklist.py — 核对清单结构+双签校验（旧影运行，gate_1b）

校验设计文档中嵌入的核对清单JSON：
  1. JSON格式合法
  2. sections A-G 全部存在
  3. A-F段所有 item 字段非空
  4. G段所有 item 字段非空
  5. signoffs.情墨.signed == true
  6. signoffs.腰子.signed == true

Usage: python3 check_checklist.py <design_doc_path> [--quiet]
Exit: 0=PASS, 1=FAIL
Code level: L1
"""
import json
import os
import re
import sys


REQUIRED_SECTIONS = ["A_选股规则", "B_评分算法", "C_风控阈值",
                     "D_否决条件", "E_数据源合规", "F_报告输出", "G_部署验证"]


def extract_checklist(filepath):
    """Extract the last ```json code block from a markdown file."""
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


def validate(checklist, quiet=False):
    errors = []

    # 1. Sections exist
    sections = checklist.get("sections", {})
    for sec in REQUIRED_SECTIONS:
        if sec not in sections:
            errors.append(f"MISSING section: {sec}")

    # 2. A-F items non-empty (allow empty if 腰子 signed = pure engineering)
    af_all_empty = True
    af_has_content = False
    for sec in REQUIRED_SECTIONS[:6]:
        items = sections.get(sec, [])
        if items:
            af_all_empty = False
        for item in items:
            if not item.get("item", "").strip():
                errors.append(f"EMPTY item: {sec}/{item.get('id', '?')}")
            else:
                af_has_content = True
    if af_all_empty and not af_has_content:
        # All A-F sections empty — check if 腰子 confirmed as pure engineering
        so_yaozi = checklist.get("signoffs", {}).get("腰子", {})
        if so_yaozi.get("signed", False):
            pass  # Pure engineering, A-F empty is acceptable
        else:
            errors.append("A-F sections all empty but 腰子 unsigned")

    # 3. G items non-empty
    g_items = sections.get("G_部署验证", [])
    if not g_items:
        errors.append("EMPTY section: G_部署验证")
    else:
        for item in g_items:
            if not item.get("item", "").strip():
                errors.append(f"EMPTY item: G/{item.get('id', '?')}")

    # 4. Signoffs
    signoffs = checklist.get("signoffs", {})
    for role in ["情墨", "腰子"]:
        so = signoffs.get(role, {})
        if not so.get("signed", False):
            errors.append(f"UNSIGNED: {role}")

    if errors:
        if not quiet:
            print(f"FAIL: {len(errors)} error(s) in {checklist.get('design_doc', '?')}:")
            for e in errors:
                print(f"  - {e}")
        return False, errors

    if not quiet:
        print(f"PASS: checklist valid for {checklist.get('design_doc', '?')}")
    return True, []


def main():
    quiet = "--quiet" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--quiet"]

    if not args:
        print("Usage: check_checklist.py <design_doc.md> [--quiet]", file=sys.stderr)
        sys.exit(1)

    filepath = args[0]
    checklist, err = extract_checklist(filepath)
    if err:
        if not quiet:
            print(f"FAIL: {err}")
        sys.exit(1)

    ok, _ = validate(checklist, quiet)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
