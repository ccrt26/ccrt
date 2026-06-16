"""
AssetInventory - 重点股票系统资产盘点模块。

只读扫描 baseline_registry.json、日报 sidecar、深度分析报告、
现有后评估脚本和数据资产。不修改任何生产文件。
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

# 项目根目录 (可被测试 mock)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _resolve(path: str) -> str:
    """相对项目根 → 绝对路径"""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(PROJECT_ROOT, path))


# ---------------------------------------------------------------------------
# 核心扫描
# ---------------------------------------------------------------------------

def scan_baseline_registry(registry_path: str = "00_项目地基/02_权威注册表/baseline_registry.json") -> dict:
    """读取 baseline_registry.json，返回解析结果或错误状态。"""
    full = _resolve(registry_path)
    if not os.path.exists(full):
        return {"status": "MISSING", "path": registry_path, "error": "文件不存在"}
    try:
        with open(full, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"status": "FOUND", "path": registry_path, "entries": len(data) if isinstance(data, (list, dict)) else 0, "data": data}
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "ERROR", "path": registry_path, "error": str(e)}


def scan_daily_report_sidecars(
    report_root: str = "重点股票/股票报告",
    max_files: int = 50,
) -> list:
    """扫描日报目录下的 sidecar JSON 文件。

    支持格式：
      - *日报_YYYYMMDD.json
      - *日报_YYYY-MM-DD.json
    排除：
      - *深度分析_baseline*.json（baseline 注入文件）
    """
    full = _resolve(report_root)
    result = []
    if not os.path.isdir(full):
        return result
    # 匹配日报 JSON（支持 YYYYMMDD 和 YYYY-MM-DD 两种日期格式）
    pattern = re.compile(r"日报_\d{8}\.json$|日报_\d{4}-\d{2}-\d{2}\.json$")
    exclude_pattern = re.compile(r"深度分析_baseline")
    for entry in sorted(os.listdir(full)):
        entry_path = os.path.join(full, entry)
        if not os.path.isdir(entry_path):
            continue
        for fname in sorted(os.listdir(entry_path)):
            if not pattern.search(fname):
                continue
            if exclude_pattern.search(fname):
                continue
            result.append({
                "stock_dir": entry,
                "file": fname,
                "path": os.path.join(report_root, entry, fname),
            })
            if len(result) >= max_files:
                return result
    return result


def scan_deep_analysis_reports(
    report_root: str = "重点股票/深度分析",
    max_files: int = 20,
) -> list:
    """扫描深度分析报告目录下的 MD 文件。"""
    full = _resolve(report_root)
    result = []
    if not os.path.isdir(full):
        return result
    for entry in sorted(os.listdir(full)):
        entry_path = os.path.join(full, entry)
        if not os.path.isdir(entry_path):
            continue
        for fname in sorted(os.listdir(entry_path)):
            if fname.endswith(".md"):
                result.append({
                    "stock_dir": entry,
                    "file": fname,
                    "path": os.path.join(report_root, entry, fname),
                })
                if len(result) >= max_files:
                    return result
    return result


def scan_eval_scripts(
    script_root: str = "scripts",
    prefix: str = "post_eval",
) -> list:
    """扫描后评估相关脚本。"""
    full = _resolve(script_root)
    result = []
    if not os.path.isdir(full):
        return result
    for fname in sorted(os.listdir(full)):
        if fname.startswith(prefix) or "eval" in fname:
            result.append({
                "file": fname,
                "path": os.path.join(script_root, fname),
            })
    return result


def scan_analysis_pipeline_status(
    candidate_paths: Optional[List[str]] = None,
) -> dict:
    """扫描分析生产线状态 JSON 文件，只读检查是否存在候选输出。

    Phase 1 可能尚无正式流水线状态文件，此处只作探测。
    """
    if candidate_paths is None:
        candidate_paths = [
            "运行产物/重点股票产品化后评估/inventory",
            "运行产物/重点股票产品化后评估/ledger",
        ]
    results = {}
    for p in candidate_paths:
        full = _resolve(p)
        if os.path.isdir(full):
            results[p] = {"status": "FOUND", "files": sorted(os.listdir(full))}
        else:
            results[p] = {"status": "NOT_FOUND"}
    return results


def scan_data_assets(data_roots: Optional[List[str]] = None) -> list:
    """扫描数据资产目录。"""
    if data_roots is None:
        data_roots = ["运行产物"]
    result = []
    for root in data_roots:
        full = _resolve(root)
        if not os.path.isdir(full):
            continue
        for dirpath, _dirnames, filenames in os.walk(full):
            for f in filenames:
                rel = os.path.relpath(os.path.join(dirpath, f), _resolve("."))
                result.append({"root": root, "file": rel})
    return result


def scan_runtime_entries(
    registry_path: str = "00_项目地基/06_调度与运行/runtime_entry_registry.json",
) -> dict:
    """只读检查 runtime_entry_registry.json 是否存在。"""
    full = _resolve(registry_path)
    if not os.path.exists(full):
        return {"status": "MISSING", "path": registry_path}
    return {"status": "FOUND", "path": registry_path}


# ---------------------------------------------------------------------------
# 综合盘点
# ---------------------------------------------------------------------------

def build_inventory(
    scan_root: Optional[str] = None,
    out_dir: Optional[str] = None,
) -> dict[str, Any]:
    """执行完整资产盘点，返回库存字典。

    Args:
        scan_root: 扫描根路径，默认项目根。
        out_dir: 可选输出目录（仅用于记录，不在此写入）。

    Returns:
        完整盘点结果字典，符合 AssetInventory 最低字段要求。
    """
    if scan_root is None:
        scan_root = _resolve(".")

    baseline_info = scan_baseline_registry()
    sidecars = scan_daily_report_sidecars()
    deep_reports = scan_deep_analysis_reports()
    eval_scripts = scan_eval_scripts()
    status_info = scan_analysis_pipeline_status()
    data_assets = scan_data_assets()
    runtime_info = scan_runtime_entries()

    inventory: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_root": str(scan_root),
        "analysis_production_contract_refs": [],
        "analysis_pipeline_status_refs": status_info,
        "baseline_registry": baseline_info,
        "baseline_files": [],
        "daily_report_sidecars": {
            "count": len(sidecars),
            "files": sidecars,
        },
        "deep_analysis_reports": {
            "count": len(deep_reports),
            "files": deep_reports,
        },
        "eval_scripts": {
            "count": len(eval_scripts),
            "files": eval_scripts,
        },
        "data_assets": {
            "count": len(data_assets),
            "files": data_assets,
        },
        "rule_assets": {
            "count": 0,
            "description": "Phase 1 只读，不枚举正式规则资产",
        },
        "runtime_entries": runtime_info,
        "detected_gaps": [],
        "candidate_pilot_rules": [
            {
                "rule_id": "TECH_MA20_BREAK_STOP_LOSS",
                "description": "MA20 破位止损",
                "status": "candidate",
                "phase": "Phase 1",
            }
        ],
        "no_production_write_evidence": "所有扫描均为只读，未修改任何生产文件。",
    }

    # 检测缺口
    if baseline_info.get("status") != "FOUND":
        inventory["detected_gaps"].append(
            f"baseline_registry.json 状态异常: {baseline_info.get('status')}"
        )
    if not sidecars:
        inventory["detected_gaps"].append("未找到日报 sidecar JSON 文件")
    if not deep_reports:
        inventory["detected_gaps"].append("未找到深度分析报告")
    if runtime_info.get("status") != "FOUND":
        inventory["detected_gaps"].append("runtime_entry_registry.json 未找到")

    return inventory


# ---------------------------------------------------------------------------
# 主入口 (脚本直接调用)
# ---------------------------------------------------------------------------

def main(out_dir: Optional[str] = None) -> dict:
    """CLI 入口点。"""
    inventory = build_inventory(out_dir=out_dir)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "keystock_system_inventory.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, ensure_ascii=False, indent=2)
        print(f"[INVENTORY] 已写入: {out_path}")
    return inventory


if __name__ == "__main__":
    import sys
    out_dir = sys.argv[1] if len(sys.argv) > 1 else None
    main(out_dir=out_dir)
