#!/usr/bin/env python3
"""
render_report_from_canonical.py — 第6-B阶段：canonical_report → 展示层影子渲染

功能：
- 输入 canonical_report JSON
- 输出 MD 文件和 sidecar JSON 到指定 out-dir
- MD 内容来自 canonical.render_snapshot.md_text
- sidecar 来自 canonical.render_snapshot.sidecar_payload
- 禁止从正式报告目录重新读取 MD/sidecar
- 禁止修改 canonical 输入文件
- 禁止写入 重点股票/股票报告/
- --all 强制股票池覆盖（优先 pigeon_config.json，fallback 扫描报告目录）
"""

import argparse
import json
import os
import sys
import glob


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

PIGEON_CONFIG = os.path.join(PROJECT_ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")

# 正式报告目录（用于安全阻断检查）
REPORT_BASE = os.path.join(PROJECT_ROOT, "重点股票", "股票报告")


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


def check_out_dir_safe(out_dir: str):
    """检查 out-dir 是否等于或位于正式报告目录内部。若不安全则退出。"""
    real_out = os.path.realpath(os.path.abspath(out_dir))
    real_report = os.path.realpath(os.path.abspath(REPORT_BASE))
    if real_out == real_report or real_out.startswith(real_report + os.sep):
        print("ERROR: 禁止写入正式报告目录", file=sys.stderr)
        sys.exit(1)


def render_from_canonical(canonical_path: str, out_dir: str) -> tuple:
    """从 canonical JSON 渲染 MD 和 sidecar。返回 (md_path, json_path) 或 raise"""
    if not os.path.isfile(canonical_path):
        raise FileNotFoundError(f"canonical 文件不存在: {canonical_path}")

    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical = json.load(f)

    render_snapshot = canonical.get("render_snapshot")
    if not render_snapshot:
        raise ValueError(f"canonical 缺少 render_snapshot: {canonical_path}")

    md_text = render_snapshot.get("md_text")
    sidecar_payload = render_snapshot.get("sidecar_payload")

    if md_text is None:
        raise ValueError(f"canonical.render_snapshot 缺少 md_text: {canonical_path}")
    if sidecar_payload is None:
        raise ValueError(f"canonical.render_snapshot 缺少 sidecar_payload: {canonical_path}")

    # 从 report_identity 获取 code 和 date
    report_identity = canonical.get("report_identity", {})
    stock_code = report_identity.get("stock_code", "unknown")
    trade_date_raw = report_identity.get("trade_date", "")
    trade_date = trade_date_raw.replace("-", "")

    md_path = os.path.join(out_dir, f"{stock_code}_{trade_date}_rendered.md")
    json_path = os.path.join(out_dir, f"{stock_code}_{trade_date}_rendered.json")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_payload, f, ensure_ascii=False, indent=2)

    return md_path, json_path


def main():
    parser = argparse.ArgumentParser(description="canonical_report → 展示层影子渲染")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--canonical", type=str, help="单个 canonical JSON 路径")
    group.add_argument("--all", action="store_true", help="全池渲染")

    parser.add_argument("--date", type=str, help="交易日（全池模式必需）")
    parser.add_argument("--canonical-dir", type=str, help="canonical 目录（全池模式）")
    parser.add_argument("--out-dir", type=str, required=True, help="输出目录")

    args = parser.parse_args()

    # ===== out-dir 安全阻断 =====
    check_out_dir_safe(args.out_dir)

    if args.canonical:
        # ===== 单票模式 =====
        os.makedirs(args.out_dir, exist_ok=True)
        try:
            md_path, json_path = render_from_canonical(args.canonical, args.out_dir)
            print(f"RENDER_MD: {md_path}")
            print(f"RENDER_JSON: {json_path}")
            sys.exit(0)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        # ===== 全池模式 =====
        if not args.date:
            print("ERROR: 全池模式必须提供 --date", file=sys.stderr)
            sys.exit(2)
        if not args.canonical_dir:
            print("ERROR: 全池模式必须提供 --canonical-dir", file=sys.stderr)
            sys.exit(2)

        date = args.date.replace("-", "")

        # 读取股票池
        pool = read_stock_pool()
        pool_codes = {c: n for n, c in pool}
        if not pool:
            print("ERROR: 股票池为空", file=sys.stderr)
            sys.exit(1)

        # 收集 canonical-dir 中的 code
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

        # 检查缺失
        expected_codes = set(pool_codes.keys())
        missing = sorted(expected_codes - disk_codes)
        if missing:
            print(f"ERROR: 缺失 {len(missing)} 只 canonical 文件:")
            for c in missing:
                print(f"  - {pool_codes[c]}({c})", file=sys.stderr)
            sys.exit(1)

        # 检查多余
        extra = sorted(disk_codes - expected_codes)
        if extra:
            print(f"ERROR: 多余 {len(extra)} 只 canonical 文件:")
            for c in extra:
                print(f"  - ({c})", file=sys.stderr)
            sys.exit(1)

        # 按股票池顺序渲染
        os.makedirs(args.out_dir, exist_ok=True)
        success, failed = 0, 0
        for name, code in pool:
            canonical_path = os.path.join(args.canonical_dir, f"{code}_{date}_canonical_report.json")
            try:
                md_path, json_path = render_from_canonical(canonical_path, args.out_dir)
                print(f"RENDER_MD: {md_path}")
                print(f"RENDER_JSON: {json_path}")
                success += 1
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
                print(f"ERROR: {e}", file=sys.stderr)
                failed += 1

        print(f"\n全池渲染完成: SUCCESS={success} FAILED={failed}")
        if failed > 0:
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
