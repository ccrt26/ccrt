#!/usr/bin/env python3
"""trace_requirements.py — 需求→代码追溯验证（新安运行，gate_2）

自动全量验证:
  1. signoffs.红结.signed == true
  2. A-F段所有 coder_ok == true
  3. A-F段所有 code_ref 非空
  4. 所有 code_ref 指向的文件存在
  5. 若 code_ref 含行号(:L45-L78)，行号范围有效

人工抽查:
  随机抽取3-5项，新安手动读代码验语义，通过 --manual 参数录入结果

Usage: python3 trace_requirements.py <design_doc.md> [--manual A1=PASS B2=FAIL]
Exit: 0=PASS, 1=FAIL
Code level: L1
"""
import json
import os
import random
import re
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


def parse_code_ref(code_ref):
    """Parse 'path/to/file.py:L45-L78' into (path, start, end)."""
    m = re.match(r'^(.+?):L?(\d+)(?:-L?(\d+))?$', code_ref)
    if m:
        path = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return path, start, end
    return code_ref, None, None


def auto_verify(checklist, project_root):
    results = []
    has_fail = False

    # 1. 红结 signed
    signoffs = checklist.get("signoffs", {})
    rb = signoffs.get("红结", {})
    if not rb.get("signed", False):
        results.append(("SIGN", "FAIL", "红结未签核对清单"))
        has_fail = True
    else:
        results.append(("SIGN", "PASS", f"红结已签 ({rb.get('date', '?')})"))

    sections = checklist.get("sections", {})

    # 2-3. A-F items: coder_ok + code_ref
    for sec_name in ["A_选股规则", "B_评分算法", "C_风控阈值",
                     "D_否决条件", "E_数据源合规", "F_报告输出"]:
        items = sections.get(sec_name, [])
        for item in items:
            rid = item.get("id", "?")
            coder_ok = item.get("coder_ok", False)
            code_ref = item.get("code_ref", "")

            if not coder_ok:
                results.append((rid, "FAIL", "coder_ok=false"))
                has_fail = True
                continue

            if not code_ref.strip():
                results.append((rid, "FAIL", "code_ref empty"))
                has_fail = True
                continue

            # 4. File exists
            path, start, end = parse_code_ref(code_ref)
            full_path = os.path.join(project_root, path)
            if not os.path.exists(full_path):
                results.append((rid, "FAIL", f"file not found: {path}"))
                has_fail = True
                continue

            # 5. Line range valid
            if start is not None:
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        line_count = sum(1 for _ in f)
                    if start < 1:
                        results.append((rid, "FAIL", f"invalid start line: {start}"))
                        has_fail = True
                        continue
                    if end > line_count:
                        results.append((rid, "WARN",
                                       f"line range exceeds file ({end} > {line_count} lines)"))
                        continue
                except Exception:
                    results.append((rid, "FAIL", f"cannot read file: {path}"))
                    has_fail = True
                    continue

            results.append((rid, "PASS", f"{code_ref}"))

    return results, has_fail


def pick_sample(items, n=4):
    """Pick n random items for manual review."""
    pool = [(item["id"], item["item"], item.get("code_ref", ""))
            for item in items if item.get("coder_ok")]
    if len(pool) <= n:
        return pool
    return random.sample(pool, n)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--manual")]
    manual_args = [a for a in sys.argv[1:] if a.startswith("--manual")]

    if not args:
        print("Usage: trace_requirements.py <design_doc.md> [--manual A1=PASS B2=FAIL]",
              file=sys.stderr)
        sys.exit(1)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))

    checklist, err = extract_checklist(args[0])
    if err:
        print(f"FAIL: {err}")
        sys.exit(1)

    # Auto verify
    results, has_fail = auto_verify(checklist, project_root)

    print(f"=== 自动验证: {checklist.get('design_doc', '?')} ===")
    for rid, status, detail in results:
        print(f"  [{status}] {rid}: {detail}")
    print(f"  结果: {'FAIL' if has_fail else 'PASS'} ({len(results)} items)")

    if has_fail:
        print()
        sys.exit(1)

    # Manual sample suggestions
    sections = checklist.get("sections", {})
    all_items = []
    for sec_name in ["A_选股规则", "B_评分算法", "C_风控阈值",
                     "D_否决条件", "E_数据源合规", "F_报告输出"]:
        all_items.extend(sections.get(sec_name, []))

    sample = pick_sample(all_items)

    # Parse manual results
    manual_results = {}
    for ma in manual_args:
        _, kv = ma.split(" ", 1) if " " in ma else ("", ma.replace("--manual=", ""))
        for pair in kv.split():
            if "=" in pair:
                k, v = pair.split("=", 1)
                manual_results[k] = v

    if sample:
        print(f"\n=== 人工抽查 ({len(sample)} items) ===")
        print("请新安手动验证以下项，然后运行:")
        manual_cmd = " ".join(f"{item[0]}=<PASS|FAIL>" for item in sample)
        print(f"  python3 trace_requirements.py {args[0]} --manual {manual_cmd}")
        print()
        for rid, desc, ref in sample:
            status = manual_results.get(rid, "PENDING")
            print(f"  [{status}] {rid}: {desc}")
            print(f"       code_ref: {ref}")

        pending = [item[0] for item in sample if item[0] not in manual_results]
        if pending:
            print(f"\n  ⚠  {len(pending)} items pending manual review: {', '.join(pending)}")
            print("  人工抽查未完成，不阻塞但请补签。")
        else:
            fails = [k for k, v in manual_results.items() if v == "FAIL"]
            if fails:
                print(f"\n  ❌ Manual review FAIL: {', '.join(fails)}")
                sys.exit(1)
            else:
                print(f"\n  ✅ Manual review PASS ({len(sample)}/{len(sample)})")

    print()
    if not has_fail:
        print("[PASS] trace_requirements complete")
    sys.exit(0 if not has_fail else 1)


if __name__ == "__main__":
    main()
