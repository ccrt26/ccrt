#!/usr/bin/env python3
"""
check_canonical_render_diff.py — 第6-B阶段：canonical 渲染产物与原日报/sidecar 对比校验

检查项：
1. 渲染产物 MD 与原正式日报 MD 字节级一致
2. 渲染产物 JSON 与原 sidecar JSON 语义一致

全池模式强制股票池覆盖（优先 pigeon_config.json，fallback 扫描报告目录）：
- 缺任意一只预期渲染产物 → BLOCK，退出码 2
- 多余 code 渲染产物 → BLOCK，退出码 2

约束：不得 import golden_master_diff.py / sync_report_json.py
"""

import argparse
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


def deep_diff_dict(expected, actual, path=""):
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


def check_render_diff(render_md_path: str, render_json_path: str, md_path: str, sidecar_path: str) -> list:
    """比较渲染产物与原文件，返回差异列表"""
    diffs = []

    # MD 字节级一致
    with open(render_md_path, "rb") as f:
        render_md_bytes = f.read()
    with open(md_path, "rb") as f:
        orig_md_bytes = f.read()
    if render_md_bytes != orig_md_bytes:
        diffs.append("渲染 MD 与原 MD 字节级不一致")

    # JSON 语义一致
    with open(render_json_path, "r", encoding="utf-8") as f:
        render_json = json.load(f)
    with open(sidecar_path, "r", encoding="utf-8") as f:
        orig_sidecar = json.load(f)
    json_diffs = deep_diff_dict(orig_sidecar, render_json, "rendered_json")
    diffs.extend(json_diffs)

    return diffs


def main():
    parser = argparse.ArgumentParser(description="canonical 渲染产物与原日报/sidecar 对比校验")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", type=str, help="股票代码（单票）")
    group.add_argument("--all", action="store_true", help="全池校验")
    parser.add_argument("--name", type=str, help="股票名称（单票模式必需）")
    parser.add_argument("--date", type=str, required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--render-dir", type=str, required=True, help="渲染产物目录")

    args = parser.parse_args()
    date = args.date.replace("-", "")

    if args.code:
        # --- 单票模式 ---
        if not args.name:
            print("ERROR: 单票模式必须提供 --name", file=sys.stderr)
            sys.exit(2)
        if not args.render_dir:
            print("ERROR: 必须提供 --render-dir", file=sys.stderr)
            sys.exit(2)

        _, _, stock_dir = find_stock_by_code(args.code)
        if not stock_dir:
            print(f"CANONICAL_RENDER_DIFF: BLOCK — 未找到 {args.code}")
            sys.exit(2)

        md_path, sidecar_path = find_report_files(stock_dir, args.name, args.code, date)
        if not md_path:
            print(f"CANONICAL_RENDER_DIFF: BLOCK — 未找到 {args.name}({args.code}) {date} 报告")
            sys.exit(2)

        render_md = os.path.join(args.render_dir, f"{args.code}_{date}_rendered.md")
        render_json = os.path.join(args.render_dir, f"{args.code}_{date}_rendered.json")

        if not os.path.isfile(render_md):
            print(f"CANONICAL_RENDER_DIFF: BLOCK — 渲染产物 MD 不存在: {render_md}")
            sys.exit(2)
        if not os.path.isfile(render_json):
            print(f"CANONICAL_RENDER_DIFF: BLOCK — 渲染产物 JSON 不存在: {render_json}")
            sys.exit(2)

        diffs = check_render_diff(render_md, render_json, md_path, sidecar_path)
        if diffs:
            print("CANONICAL_RENDER_DIFF: BLOCK")
            for d in diffs:
                print(f"  - {d}")
            sys.exit(2)
        else:
            print("CANONICAL_RENDER_DIFF: PASS")
            sys.exit(0)

    else:
        # --- 全池模式 ---
        if not args.render_dir:
            print("ERROR: 必须提供 --render-dir", file=sys.stderr)
            sys.exit(2)

        pool = read_stock_pool()
        pool_codes = {c: n for n, c in pool}

        if not pool:
            print("CANONICAL_RENDER_DIFF: BLOCK — 股票池为空")
            sys.exit(2)

        # 收集目录中渲染产物
        md_pattern = os.path.join(args.render_dir, f"*_{date}_rendered.md")
        json_pattern = os.path.join(args.render_dir, f"*_{date}_rendered.json")
        md_files = sorted(glob.glob(md_pattern))
        json_files = sorted(glob.glob(json_pattern))

        # 解析渲染产物中的 code
        render_codes = set()
        for fpath in md_files:
            basename = os.path.basename(fpath)
            try:
                code = basename.split("_")[0]
                render_codes.add(code)
            except Exception:
                pass
        for fpath in json_files:
            basename = os.path.basename(fpath)
            try:
                code = basename.split("_")[0]
                render_codes.add(code)
            except Exception:
                pass

        # 检查缺失
        missing = []
        for code in sorted(pool_codes):
            if code not in render_codes:
                missing.append(code)

        if missing:
            print("CANONICAL_RENDER_DIFF: BLOCK")
            print(f"  缺失 {len(missing)} 只渲染产物:")
            for c in missing:
                print(f"    - {pool_codes[c]}({c})")
            sys.exit(2)

        # 检查多余
        extra = sorted(render_codes - set(pool_codes.keys()))
        if extra:
            print("CANONICAL_RENDER_DIFF: BLOCK")
            print(f"  多余 {len(extra)} 只渲染产物:")
            for c in extra:
                print(f"    - ({c})")
            sys.exit(2)

        # 按股票池顺序逐一检查
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

            render_md = os.path.join(args.render_dir, f"{code}_{date}_rendered.md")
            render_json = os.path.join(args.render_dir, f"{code}_{date}_rendered.json")

            if not os.path.isfile(render_md):
                all_failures.append({"stock": f"{name}({code})", "diffs": ["渲染 MD 不存在"]})
                continue
            if not os.path.isfile(render_json):
                all_failures.append({"stock": f"{name}({code})", "diffs": ["渲染 JSON 不存在"]})
                continue

            diffs = check_render_diff(render_md, render_json, md_path, sidecar_path)
            if diffs:
                all_failures.append({"stock": f"{name}({code})", "diffs": diffs})

        if all_failures:
            print("CANONICAL_RENDER_DIFF: BLOCK")
            for f in all_failures:
                print(f"  {f['stock']}:")
                for d in f["diffs"]:
                    print(f"    - {d}")
            sys.exit(2)
        else:
            print("CANONICAL_RENDER_DIFF: PASS")
            sys.exit(0)


if __name__ == "__main__":
    main()
