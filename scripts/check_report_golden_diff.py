#!/usr/bin/env python3
"""
check_report_golden_diff.py — 第6-A阶段：日报专用 Golden Diff

检查项：
1. canonical.render_snapshot.md_text 与原 MD 字节级一致
2. canonical.render_snapshot.sidecar_payload 与原 sidecar JSON 语义一致
3. canonical.source_hashes 与原文件哈希一致

通过输出 → REPORT_GOLDEN_DIFF: PASS (退出码0)
失败输出 → REPORT_GOLDEN_DIFF: BLOCK (退出码2)

--all 强制股票池完全覆盖：
- 优先读取 代码文件/信鸽信息采集/pigeon_config.json
- fallback 扫描 重点股票/股票报告/
- 缺任意一只 → BLOCK，退出码 2

约束：不得 import golden_master_diff.py / sync_report_json.py
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
    # fallback
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


def deep_diff_dict(expected, actual, path=""):
    """比较两个 dict 的差异，返回差异列表"""
    diffs = []
    for key in expected:
        full_path = f"{path}.{key}" if path else key
        if key not in actual:
            diffs.append(f"MISSING: {full_path}")
            continue
        ev = expected[key]
        av = actual[key]
        if isinstance(ev, dict) and isinstance(av, dict):
            diffs.extend(deep_diff_dict(ev, av, full_path))
        else:
            if ev != av:
                diffs.append(f"DIFF: {full_path}")
    for key in actual:
        full_path = f"{path}.{key}" if path else key
        if key not in expected:
            diffs.append(f"EXTRA: {full_path}")
    return diffs


def check_golden_diff(canonical_path: str, md_path: str, sidecar_path: str) -> list:
    """执行 golden diff 检查，返回差异列表（空 = PASS）"""
    diffs = []

    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical = json.load(f)

    md_bytes = open(md_path, "rb").read()
    md_text = md_bytes.decode("utf-8")
    sidecar = json.load(open(sidecar_path, "r", encoding="utf-8"))

    # 1. render_snapshot.md_text 字节级一致
    render_md = canonical.get("render_snapshot", {}).get("md_text", "")
    if render_md != md_text:
        diffs.append("render_snapshot.md_text 字节级不一致")

    # 2. render_snapshot.sidecar_payload 语义一致
    render_sidecar = canonical.get("render_snapshot", {}).get("sidecar_payload", {})
    sidecar_diffs = deep_diff_dict(sidecar, render_sidecar, "render_snapshot.sidecar_payload")
    diffs.extend(sidecar_diffs)

    # 3. source_hashes 一致
    ch_sidecar = canonical.get("source_hashes", {}).get("sidecar_sha256", "")
    actual_sidecar_hash = sha256_of_file(sidecar_path)
    if ch_sidecar != actual_sidecar_hash:
        diffs.append(f"source_hashes.sidecar_sha256 不一致: canonical={ch_sidecar[:16]}... actual={actual_sidecar_hash[:16]}...")

    ch_md = canonical.get("source_hashes", {}).get("md_sha256", "")
    actual_md_hash = sha256_of_file(md_path)
    if ch_md != actual_md_hash:
        diffs.append(f"source_hashes.md_sha256 不一致: canonical={ch_md[:16]}... actual={actual_md_hash[:16]}...")

    return diffs


def main():
    parser = argparse.ArgumentParser(description="日报专用 Golden Diff 校验")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", type=str, help="股票代码（单票）")
    group.add_argument("--all", action="store_true", help="全池校验")
    parser.add_argument("--name", type=str, help="股票名称（单票模式必需）")
    parser.add_argument("--date", type=str, required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--canonical", type=str, help="canonical 文件路径（单票）")
    parser.add_argument("--canonical-dir", type=str, help="canonical 目录（全池）")

    args = parser.parse_args()
    date = args.date.replace("-", "")

    if args.code:
        # --- 单票模式 ---
        if not args.name or not args.canonical:
            print("ERROR: 单票模式必须提供 --name 和 --canonical", file=sys.stderr)
            sys.exit(2)

        _, _, stock_dir = find_stock_by_code(args.code)
        if not stock_dir:
            print(f"REPORT_GOLDEN_DIFF: BLOCK — 未找到 {args.code}")
            sys.exit(2)

        md_path, sidecar_path = find_report_files(stock_dir, args.name, args.code, date)
        if not md_path:
            print(f"REPORT_GOLDEN_DIFF: BLOCK — 未找到 {args.name}({args.code}) {date} 报告")
            sys.exit(2)

        diffs = check_golden_diff(args.canonical, md_path, sidecar_path)
        if diffs:
            print("REPORT_GOLDEN_DIFF: BLOCK")
            for d in diffs:
                print(f"  - {d}")
            sys.exit(2)
        else:
            print(f"REPORT_GOLDEN_DIFF: PASS")
            sys.exit(0)

    else:
        # --- 全池模式 ---
        if not args.canonical_dir:
            print("ERROR: 全池模式必须提供 --canonical-dir", file=sys.stderr)
            sys.exit(2)

        # 读取股票池
        pool = read_stock_pool()
        pool_codes = {c: n for n, c in pool}
        expected_count = len(pool)

        if expected_count == 0:
            print(f"REPORT_GOLDEN_DIFF: BLOCK — 股票池为空", file=sys.stderr)
            sys.exit(2)

        # 检查缺失
        pattern = os.path.join(args.canonical_dir, f"*_{date}_canonical_report.json")
        disk_files = sorted(glob.glob(pattern))
        disk_codes = set()
        for fpath in disk_files:
            basename = os.path.basename(fpath)
            try:
                code = basename.split("_")[0]
                disk_codes.add(code)
            except Exception:
                pass

        missing = []
        for code in sorted(pool_codes):
            if code not in disk_codes:
                missing.append(code)

        if missing:
            print(f"REPORT_GOLDEN_DIFF: BLOCK")
            print(f"  缺失 {len(missing)} 只 canonical 文件:")
            for c in missing:
                print(f"    - {pool_codes[c]}({c})")
            sys.exit(2)

        # 检查多余
        extra = sorted(disk_codes - set(pool_codes.keys()))
        if extra:
            print(f"REPORT_GOLDEN_DIFF: BLOCK")
            print(f"  多余 {len(extra)} 只 canonical 文件:")
            for c in extra:
                print(f"    - ({c})")
            sys.exit(2)

        # 按股票池顺序检查每只
        all_failures = []
        for name, code in pool:
            _, _, stock_dir = find_stock_by_code(code)
            if not stock_dir:
                all_failures.append({"stock": f"{name}({code})", "diffs": ["报告目录不存在"]})
                continue

            md_path, sidecar_path = find_report_files(stock_dir, name, code, date)
            if not md_path:
                all_failures.append({"stock": f"{name}({code})", "diffs": [f"未找到 {date} 报告"]})
                continue

            canonical_path = os.path.join(args.canonical_dir, f"{code}_{date}_canonical_report.json")
            if not os.path.isfile(canonical_path):
                all_failures.append({"stock": f"{name}({code})", "diffs": ["canonical 文件不存在"]})
                continue

            diffs = check_golden_diff(canonical_path, md_path, sidecar_path)
            if diffs:
                all_failures.append({"stock": f"{name}({code})", "diffs": diffs})

        if all_failures:
            print("REPORT_GOLDEN_DIFF: BLOCK")
            for f in all_failures:
                print(f"  {f['stock']}:")
                for d in f["diffs"]:
                    print(f"    - {d}")
            sys.exit(2)
        else:
            print("REPORT_GOLDEN_DIFF: PASS")
            sys.exit(0)


if __name__ == "__main__":
    main()
