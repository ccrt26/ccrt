#!/usr/bin/env python3
"""
build_canonical_report.py — 第6-A阶段：构建 canonical_report 影子对象

功能：
- 读取日报 MD + JSON sidecar
- 输出 canonical_report JSON（shadow_only=true）
- 单票模式：--code --name --date --out
- 全池模式：--all --date --out-dir

约束：
- 不修改任何输入文件
- 不写入正式报告目录
- 不引用 golden_master_diff.py / sync_report_json.py
- 不引用 临时报告/ / 历史数据/ / _win32_legacy/ / .ps1
"""

import argparse
import hashlib
import json
import os
import sys
import glob


CANONICAL_VERSION = "v1.0"

# 股票报告基目录
REPORT_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "重点股票", "股票报告")


def sha256_of_file(filepath: str) -> str:
    """计算文件的 SHA-256"""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_sidecar(sidecar_path: str) -> dict:
    """读取 JSON sidecar"""
    with open(sidecar_path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_md(md_path: str) -> str:
    """读取 MD 文件全文"""
    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()


def build_canonical(md_path: str, sidecar_path: str) -> dict:
    """构建 canonical_report 影子对象"""
    md_text = read_md(md_path)
    sidecar = read_sidecar(sidecar_path)
    md_sha256 = sha256_of_file(md_path)
    sidecar_sha256 = sha256_of_file(sidecar_path)

    # 计算映射字段
    report_identity = {
        "stock_code": sidecar.get("stock_code", ""),
        "stock_name": sidecar.get("stock_name", ""),
        "trade_date": sidecar.get("trade_date", ""),
    }
    authority_refs = {
        "baseline_id": sidecar.get("baseline_id", ""),
    }
    data_snapshot = {
        "delta": sidecar.get("delta", {}),
        "fund_flow_4level": sidecar.get("fund_flow_4level", {}),
        "sector_phase": sidecar.get("sector_phase", {}),
        "source_snapshot": sidecar.get("source_snapshot", {}),
    }
    decision_snapshot = {
        "p0_decision_card": sidecar.get("p0_decision_card", {}),
    }
    risk_snapshot = {
        "risk_light": sidecar.get("risk_light", {}),
    }
    interpretation_snapshot = {
        "role_interpretations": sidecar.get("role_interpretations", {}),
        "yaozi_integration": sidecar.get("yaozi_integration", {}),
    }
    eval_snapshot = {
        "eval_hooks": sidecar.get("eval_hooks", {}),
    }

    # render_snapshot 必须等于源文件
    render_snapshot = {
        "md_text": md_text,
        "sidecar_payload": sidecar,
    }
    source_hashes = {
        "md_sha256": md_sha256,
        "sidecar_sha256": sidecar_sha256,
    }
    source_payloads = {
        "md_text": md_text,
        "sidecar_payload": sidecar,
    }

    canonical = {
        "canonical_version": CANONICAL_VERSION,
        "shadow_only": True,
        "report_identity": report_identity,
        "authority_refs": authority_refs,
        "data_snapshot": data_snapshot,
        "decision_snapshot": decision_snapshot,
        "risk_snapshot": risk_snapshot,
        "interpretation_snapshot": interpretation_snapshot,
        "eval_snapshot": eval_snapshot,
        "render_snapshot": render_snapshot,
        "source_hashes": source_hashes,
        "source_payloads": source_payloads,
    }
    return canonical


def find_stock_dirs() -> list:
    """扫描重点股票/股票报告/ 目录，返回 (name, code, dirpath) 列表"""
    result = []
    if not os.path.isdir(REPORT_BASE):
        return result
    for entry in os.listdir(REPORT_BASE):
        dirpath = os.path.join(REPORT_BASE, entry)
        if not os.path.isdir(dirpath):
            continue
        # 目录名格式：名称(代码)
        if "(" not in entry or not entry.endswith(")"):
            continue
        name = entry.split("(")[0]
        code = entry.split("(")[1].rstrip(")")
        result.append((name, code, dirpath))
    return result


def find_report_files(stock_dir: str, name: str, code: str, date: str) -> tuple:
    """查找指定日期的 MD 和 sidecar 文件"""
    # MD 文件名格式：名称(代码)日报_{date}.md
    md_filename = f"{name}({code})日报_{date}.md"
    sidecar_filename = f"{name}({code})日报_{date}.json"

    md_path = os.path.join(stock_dir, md_filename)
    sidecar_path = os.path.join(stock_dir, sidecar_filename)

    if not os.path.isfile(md_path):
        return None, None
    if not os.path.isfile(sidecar_path):
        return None, None
    return md_path, sidecar_path


def find_stock_by_code(code: str) -> tuple:
    """按股票代码查找目录"""
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


def try_read_pigeon_config() -> list:
    """尝试读取 pigeon_config.json 获取股票池"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "代码文件", "信鸽信息采集", "pigeon_config.json"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        stocks = config.get("target_stocks", [])
        if stocks:
            return [(s["name"], s["code"]) for s in stocks]
    except Exception:
        pass
    return []


def read_pigeon_config_safe():
    """尝试读取 pigeon_config，失败时回退到目录扫描"""
    result = try_read_pigeon_config()
    if result:
        return result
    # fallback: 扫描报告目录
    dirs = find_stock_dirs()
    return [(n, c) for n, c, _ in dirs]


def main():
    parser = argparse.ArgumentParser(description="构建 canonical_report 影子对象")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", type=str, help="股票代码")
    group.add_argument("--all", action="store_true", help="全池处理")

    parser.add_argument("--name", type=str, help="股票名称（单票模式必需）")
    parser.add_argument("--date", type=str, required=True, help="交易日，格式 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--out", type=str, help="输出文件路径（单票模式）")
    parser.add_argument("--out-dir", type=str, help="输出目录（全池模式）")

    args = parser.parse_args()

    # 归一化日期：移除横线
    date = args.date.replace("-", "")
    # 显示日期格式（保留横线用于文件名）
    display_date = f"{date[:4]}-{date[4:6]}-{date[6:]}"

    if args.code:
        # 单票模式
        if not args.name:
            print("ERROR: 单票模式必须提供 --name", file=sys.stderr)
            sys.exit(1)
        if not args.out:
            print("ERROR: 单票模式必须提供 --out", file=sys.stderr)
            sys.exit(1)

        name, code, stock_dir = find_stock_by_code(args.code)
        if not stock_dir:
            print(f"ERROR: 未找到股票代码 {args.code} 的报告目录", file=sys.stderr)
            sys.exit(1)

        md_path, sidecar_path = find_report_files(stock_dir, args.name, args.code, date)
        if not md_path:
            print(f"ERROR: 未找到 {args.name}({args.code}) 交易日 {display_date} 的报告文件", file=sys.stderr)
            sys.exit(1)

        canonical = build_canonical(md_path, sidecar_path)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(canonical, f, ensure_ascii=False, indent=2)
        print(f"OUTPUT: {args.out}")

    else:
        # 全池模式
        if not args.out_dir:
            print("ERROR: 全池模式必须提供 --out-dir", file=sys.stderr)
            sys.exit(1)

        os.makedirs(args.out_dir, exist_ok=True)
        stocks = read_pigeon_config_safe()
        if not stocks:
            print("ERROR: 无可处理的股票", file=sys.stderr)
            sys.exit(1)

        success, failed = 0, 0
        for stock_name, stock_code in stocks:
            _, _, stock_dir = find_stock_by_code(stock_code)
            if not stock_dir:
                print(f"WARN: 未找到 {stock_name}({stock_code}) 目录，跳过", file=sys.stderr)
                failed += 1
                continue

            md_path, sidecar_path = find_report_files(stock_dir, stock_name, stock_code, date)
            if not md_path:
                print(f"WARN: {stock_name}({stock_code}) {display_date} 无报告文件，跳过", file=sys.stderr)
                failed += 1
                continue

            canonical = build_canonical(md_path, sidecar_path)
            out_path = os.path.join(args.out_dir, f"{stock_code}_{date}_canonical_report.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(canonical, f, ensure_ascii=False, indent=2)
            print(f"OUTPUT: {out_path}")
            success += 1

        print(f"\n全池处理完成: SUCCESS={success} FAILED={failed}")
        if failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
