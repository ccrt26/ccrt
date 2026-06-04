#!/usr/bin/env python3
"""
check_canonical_report_shadow.py — 第6-A阶段：canonical_report 影子对象校验

检查项：
1. canonical JSON 可解析
2. canonical_version 存在
3. shadow_only == true
4. source_hashes.sidecar_sha256 == 原 sidecar sha256
5. source_hashes.md_sha256 == 原 MD sha256
6. source_payloads.sidecar_payload 与原 sidecar JSON 完全一致
7. source_payloads.md_text 与原 MD 完全一致
8. render_snapshot.sidecar_payload 与原 sidecar JSON 完全一致
9. render_snapshot.md_text 与原 MD 完全一致

任一失败 → BLOCK，退出码 2
全部通过 → PASS，退出码 0

--all 强制股票池完全覆盖：
- 优先读取 代码文件/信鸽信息采集/pigeon_config.json
- fallback 扫描 重点股票/股票报告/
- 缺任意一只 → BLOCK，退出码 2
- 多出不属于池的文件 → BLOCK，退出码 2
--json 输出单一合法 JSON 对象，含 summary.total/pass/block/missing/extra
"""

import argparse
import hashlib
import json
import os
import sys
import glob


REPORT_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "重点股票", "股票报告")

PIGEON_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "代码文件", "信鸽信息采集", "pigeon_config.json"
)


def sha256_of_file(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def find_stock_by_code(code: str) -> tuple:
    for entry in os.listdir(REPORT_BASE):
        dirpath = os.path.join(REPORT_BASE, entry)
        if not os.path.isdir(dirpath):
            continue
        if "(" not in entry or not entry.endswith(")"):
            continue
        e_code = entry.split("(")[1].rstrip(")")
        if e_code == code:
            name = entry.split("(")[0]
            return name, code, dirpath
    return None, None, None


def find_report_files(stock_dir: str, name: str, code: str, date: str) -> tuple:
    md_filename = f"{name}({code})日报_{date}.md"
    sidecar_filename = f"{name}({code})日报_{date}.json"
    md_path = os.path.join(stock_dir, md_filename)
    sidecar_path = os.path.join(stock_dir, sidecar_filename)
    if not os.path.isfile(md_path) or not os.path.isfile(sidecar_path):
        return None, None
    return md_path, sidecar_path


def read_stock_pool() -> list:
    """读取股票池，优先 pigeon_config.json，失败时 fallback 扫描报告目录。返回 [(name, code), ...]"""
    try:
        if os.path.isfile(PIGEON_CONFIG):
            with open(PIGEON_CONFIG, "r", encoding="utf-8") as f:
                config = json.load(f)
            stocks = config.get("target_stocks", [])
            if stocks:
                return [(s["name"], s["code"]) for s in stocks]
    except Exception:
        pass
    # fallback: 扫描报告目录
    result = []
    if os.path.isdir(REPORT_BASE):
        for entry in sorted(os.listdir(REPORT_BASE)):
            dirpath = os.path.join(REPORT_BASE, entry)
            if not os.path.isdir(dirpath):
                continue
            if "(" not in entry or not entry.endswith(")"):
                continue
            name = entry.split("(")[0]
            code = entry.split("(")[1].rstrip(")")
            result.append((name, code))
    return result


def check_canonical(canonical_path: str, md_path: str, sidecar_path: str, json_output: bool = False) -> tuple:
    """检查单个 canonical 报告。返回 (passed: bool, results: list)"""
    results = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "BLOCK"
        results.append({"check": name, "status": status, "detail": detail})

    # 1. canonical JSON 可解析
    try:
        with open(canonical_path, "r", encoding="utf-8") as f:
            canonical = json.load(f)
        check("canonical_json_parseable", True)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        check("canonical_json_parseable", False, str(e))
        return False, results

    # 2. canonical_version 存在
    cv = canonical.get("canonical_version")
    check("canonical_version_exists", bool(cv), str(cv))

    # 3. shadow_only == true
    shadow = canonical.get("shadow_only")
    check("shadow_only_is_true", shadow is True, str(shadow))

    # 读取原始文件
    md_bytes = open(md_path, "rb").read()
    md_text = md_bytes.decode("utf-8")
    sidecar = json.load(open(sidecar_path, "r", encoding="utf-8"))

    # 4. source_hashes.sidecar_sha256
    ch_sidecar = canonical.get("source_hashes", {}).get("sidecar_sha256", "")
    actual_sidecar_hash = sha256_of_file(sidecar_path)
    check("source_hashes_sidecar_sha256", ch_sidecar == actual_sidecar_hash,
          f"expected={actual_sidecar_hash[:16]}... got={ch_sidecar[:16]}...")

    # 5. source_hashes.md_sha256
    ch_md = canonical.get("source_hashes", {}).get("md_sha256", "")
    actual_md_hash = sha256_of_file(md_path)
    check("source_hashes_md_sha256", ch_md == actual_md_hash,
          f"expected={actual_md_hash[:16]}... got={ch_md[:16]}...")

    # 6. source_payloads.sidecar_payload == 原 sidecar
    sp_sidecar = canonical.get("source_payloads", {}).get("sidecar_payload", {})
    check("source_payloads_sidecar_payload", sp_sidecar == sidecar, "deep_equal")

    # 7. source_payloads.md_text == 原 MD
    sp_md = canonical.get("source_payloads", {}).get("md_text", "")
    check("source_payloads_md_text", sp_md == md_text,
          f"len_expected={len(md_text)} len_got={len(sp_md)}")

    # 8. render_snapshot.sidecar_payload == 原 sidecar
    rs_sidecar = canonical.get("render_snapshot", {}).get("sidecar_payload", {})
    check("render_snapshot_sidecar_payload", rs_sidecar == sidecar, "deep_equal")

    # 9. render_snapshot.md_text == 原 MD
    rs_md = canonical.get("render_snapshot", {}).get("md_text", "")
    check("render_snapshot_md_text", rs_md == md_text,
          f"len_expected={len(md_text)} len_got={len(rs_md)}")

    all_pass = all(r["status"] == "PASS" for r in results)
    return all_pass, results


def main():
    parser = argparse.ArgumentParser(description="校验 canonical_report 影子对象")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", type=str, help="股票代码（单票）")
    group.add_argument("--all", action="store_true", help="全池校验")
    parser.add_argument("--name", type=str, help="股票名称（单票模式必需）")
    parser.add_argument("--date", type=str, required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--canonical", type=str, help="canonical 文件路径（单票）")
    parser.add_argument("--canonical-dir", type=str, help="canonical 目录（全池）")
    parser.add_argument("--json", action="store_true", help="JSON 输出（全池模式输出单一对象）")

    args = parser.parse_args()
    date = args.date.replace("-", "")

    if args.code:
        # --- 单票模式 ---
        if not args.name:
            print("ERROR: 单票模式必须提供 --name", file=sys.stderr)
            sys.exit(2)
        if not args.canonical:
            print("ERROR: 单票模式必须提供 --canonical", file=sys.stderr)
            sys.exit(2)

        _, _, stock_dir = find_stock_by_code(args.code)
        if not stock_dir:
            print(f"ERROR: 未找到股票代码 {args.code}", file=sys.stderr)
            sys.exit(2)

        md_path, sidecar_path = find_report_files(stock_dir, args.name, args.code, date)
        if not md_path:
            print(f"ERROR: 未找到 {args.name}({args.code}) {date} 报告文件", file=sys.stderr)
            sys.exit(2)

        passed, results = check_canonical(args.canonical, md_path, sidecar_path, args.json)

        label = args.canonical.split("/")[-1]
        if args.json:
            out = {
                "mode": "single",
                "stock": {"code": args.code, "name": args.name},
                "path": args.canonical,
                "results": results,
                "summary": {
                    "total": len(results),
                    "pass": sum(1 for r in results if r["status"] == "PASS"),
                    "block": sum(1 for r in results if r["status"] == "BLOCK"),
                }
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== SHADOW CHECK: {label} ===")
            for r in results:
                icon = "✅" if r["status"] == "PASS" else "❌"
                print(f"  {icon} {r['status']}: {r['check']}  {r['detail']}")

        sys.exit(0 if passed else 2)

    else:
        # --- 全池模式 ---
        if not args.canonical_dir:
            print("ERROR: 全池模式必须提供 --canonical-dir", file=sys.stderr)
            sys.exit(2)

        # 读取股票池
        pool = read_stock_pool()
        pool_codes = {c: n for n, c in pool}
        pool_names = {n: c for n, c in pool}
        expected_count = len(pool)

        if expected_count == 0:
            if args.json:
                print(json.dumps({
                    "mode": "all", "date": date, "canonical_dir": args.canonical_dir,
                    "stock_pool": [], "expected_count": 0,
                    "stocks": [], "results": [],
                    "summary": {"total": 0, "pass": 0, "block": 0, "missing": [], "extra": []},
                    "verdict": "BLOCK", "reason": "股票池为空"
                }, ensure_ascii=False, indent=2))
            else:
                print(f"ERROR: 股票池为空", file=sys.stderr)
            sys.exit(2)

        # 收集目录中存在的 canonical 文件
        pattern = os.path.join(args.canonical_dir, f"*_{date}_canonical_report.json")
        disk_files = sorted(glob.glob(pattern))

        # 解析磁盘文件中的 code
        disk_codes = set()
        for fpath in disk_files:
            basename = os.path.basename(fpath)
            try:
                code = basename.split("_")[0]
                disk_codes.add(code)
            except Exception:
                pass

        # 检查缺失：股票池中有但目录中没有
        missing = []
        for code in sorted(pool_codes):
            if code not in disk_codes:
                missing.append(code)

        # 检查多余：目录中有但股票池中没有
        extra = []
        for code in sorted(disk_codes):
            if code not in pool_codes:
                extra.append(code)

        # 缺票或多票 → 直接 BLOCK
        if missing or extra:
            verdict = "BLOCK"
            reason_parts = []
            if missing:
                reason_parts.append(f"缺失{len(missing)}只: {','.join(missing)}")
            if extra:
                reason_parts.append(f"多余{len(extra)}只: {','.join(extra)}")
            reason = "; ".join(reason_parts)

            if args.json:
                out = {
                    "mode": "all", "date": date, "canonical_dir": args.canonical_dir,
                    "stock_pool": [{"code": c, "name": n} for n, c in pool],
                    "expected_count": expected_count,
                    "stocks": [], "results": [],
                    "summary": {
                        "total": 0, "pass": 0, "block": 0,
                        "missing": sorted(missing), "extra": sorted(extra)
                    },
                    "verdict": verdict, "reason": reason
                }
                print(json.dumps(out, ensure_ascii=False, indent=2))
            else:
                print(f"\n=== SHADOW CHECK ALL: BLOCK ===")
                if missing:
                    for c in sorted(missing):
                        print(f"  ❌ MISSING: {pool_codes[c]}({c}) — canonical 文件缺失")
                if extra:
                    for c in sorted(extra):
                        print(f"  ❌ EXTRA: ({c}) — 不在股票池中")
                print(f"\n  期望 {expected_count} 只，缺失 {len(missing)} 只，多余 {len(extra)} 只")
                print(f"  原因: {reason}")
            sys.exit(2)

        # 检查每只股票
        results_list = []
        total_pass, total_block = 0, 0
        stock_results = []

        # 按股票池顺序遍历（确保一致性）
        for name, code in pool:
            _, _, stock_dir = find_stock_by_code(code)
            if not stock_dir:
                if args.json:
                    stock_results.append({"code": code, "name": name, "status": "BLOCK", "reason": "报告目录不存在"})
                else:
                    print(f"  ❌ {name}({code}): 报告目录不存在", file=sys.stderr)
                total_block += 1
                continue

            md_path, sidecar_path = find_report_files(stock_dir, name, code, date)
            if not md_path:
                if args.json:
                    stock_results.append({"code": code, "name": name, "status": "BLOCK", "reason": f"未找到 {date} 报告文件"})
                else:
                    print(f"  ❌ {name}({code}): 未找到 {date} 报告文件", file=sys.stderr)
                total_block += 1
                continue

            canonical_path = os.path.join(args.canonical_dir, f"{code}_{date}_canonical_report.json")
            if not os.path.isfile(canonical_path):
                if args.json:
                    stock_results.append({"code": code, "name": name, "status": "BLOCK", "reason": "canonical文件不存在"})
                else:
                    print(f"  ❌ {name}({code}): canonical文件不存在", file=sys.stderr)
                total_block += 1
                continue

            passed, results = check_canonical(canonical_path, md_path, sidecar_path, args.json)
            if passed:
                total_pass += 1
            else:
                total_block += 1
            stock_results.append({
                "code": code, "name": name,
                "status": "PASS" if passed else "BLOCK",
                "path": canonical_path,
                "results": results if args.json else None,
            })
            results_list.append({"path": canonical_path, "passed": passed})

        verdict = "PASS" if total_block == 0 else "BLOCK"

        if args.json:
            out = {
                "mode": "all", "date": date, "canonical_dir": args.canonical_dir,
                "stock_pool": [{"code": c, "name": n} for n, c in pool],
                "expected_count": expected_count,
                "stocks": stock_results,
                "summary": {
                    "total": total_pass + total_block,
                    "pass": total_pass,
                    "block": total_block,
                    "missing": [],
                    "extra": []
                },
                "verdict": verdict
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== SHADOW CHECK ALL: {verdict} ===")
            print(f"  PASS: {total_pass}")
            print(f"  BLOCK: {total_block}")
            print(f"  期望 {expected_count} 只，全覆盖")

        sys.exit(0 if verdict == "PASS" else 2)


if __name__ == "__main__":
    main()
