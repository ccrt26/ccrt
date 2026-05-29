#!/usr/bin/env python3
"""
golden_master_diff.py - 评分引擎变更后精确比对 (闸门2 新安侧)
用5个历史快照运行评分引擎，比对评分/排序/否决标记/相位分类四项完全一致。
不一致 → FAIL, 打回红结
"""
import sys
import json
import os
import subprocess
import hashlib
from datetime import datetime, timezone
from log_utils import append_log

SNAPSHOT_DIR = "test_data/golden_master"
ENGINE_SCRIPT = "scripts/run_scoring_engine.py"  # 假设的评分引擎入口
COMPARE_FIELDS = ["score", "ranking", "veto_flag", "phase"]


def run_engine_on_snapshot(snapshot_path):
    """用快照文件作为输入运行评分引擎，返回输出"""
    try:
        result = subprocess.run(
            ["python", ENGINE_SCRIPT, "--input", snapshot_path],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"引擎运行失败: {result.stderr.strip()}")
        return json.loads(result.stdout)
    except Exception as e:
        print(f"运行引擎失败: {e}")
        sys.exit(1)


def compare_results(expected, actual):
    """比较两个结果中的关键字段"""
    diffs = []
    # 假设 expected 和 actual 都是 list of dict，按股票代码对齐
    # 这里用简单方式：转为按 code 排序后逐项比对
    def to_dict_by_code(items):
        return {item.get("code"): item for item in items}

    exp_map = to_dict_by_code(expected)
    act_map = to_dict_by_code(actual)

    all_codes = set(exp_map.keys()) | set(act_map.keys())
    for code in sorted(all_codes):
        exp_item = exp_map.get(code, {})
        act_item = act_map.get(code, {})
        for field in COMPARE_FIELDS:
            if exp_item.get(field) != act_item.get(field):
                diffs.append(
                    f"股票{code} 字段{field}: 期望={exp_item.get(field)} 实际={act_item.get(field)}"
                )
    return diffs


def golden_master_diff(run_id="UNKNOWN"):
    """主比对流程"""
    snapshot_files = [
        "snapshot_bull.json",
        "snapshot_bear.json",
        "snapshot_volatile.json",
        "snapshot_earnings.json",
        "snapshot_pre_holiday.json"
    ]

    all_errors = []

    for fname in snapshot_files:
        snap_path = os.path.join(SNAPSHOT_DIR, fname)
        if not os.path.exists(snap_path):
            all_errors.append(f"快照文件不存在: {snap_path}")
            continue

        # 运行引擎得到新结果
        new_result = run_engine_on_snapshot(snap_path)
        # 期望结果是快照文件本身（假设快照里保存了旧的引擎输出）
        try:
            with open(snap_path, 'r', encoding='utf-8') as f:
                expected_result = json.load(f)
        except Exception as e:
            all_errors.append(f"读取快照失败 {fname}: {e}")
            continue

        # 比对
        diffs = compare_results(expected_result, new_result)
        if diffs:
            all_errors.extend([f"[{fname}] {d}" for d in diffs])

    # 记录日志
    if all_errors:
        append_log("gate", {
            "run_id": run_id,
            "gate": "gate_2_golden_master",
            "script": "golden_master_diff.py",
            "trigger": "ci-pipeline",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [{"check_name": "golden_master", "result": "FAIL"}],
            "overall_result": "FAIL",
            "fail_reasons": all_errors,
            "duration_ms": 0
        })
        print("FAIL: Golden Master 比对不通过")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        append_log("gate", {
            "run_id": run_id,
            "gate": "gate_2_golden_master",
            "script": "golden_master_diff.py",
            "trigger": "ci-pipeline",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [{"check_name": "golden_master", "result": "PASS"}],
            "overall_result": "PASS",
            "fail_reasons": [],
            "duration_ms": 0
        })
        print("PASS: 所有快照比对一致，Golden Master 验证通过")
        sys.exit(0)


if __name__ == "__main__":
    # 可以从命令行传入 run_id，或从环境变量获取
    run_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RUN_ID", "UNKNOWN")
    golden_master_diff(run_id)
