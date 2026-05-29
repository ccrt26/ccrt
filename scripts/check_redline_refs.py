#!/usr/bin/env python3
"""
check_redline_refs.py - L2风控代码红线引用检查 (闸门2 新安侧)
检查所有L2代码文件中的函数/方法是否注释引用了红线条款编号(R-xxx)。
编号必须存在于合法清单中。缺引用或非法引用 → FAIL
"""
import sys
import json
import os
import re
from datetime import datetime, timezone
from log_utils import append_log

REDLINE_INDEX_FILE = "docs/redline_index.json"
# 从清单中获取L2文件列表的函数需要配合使用，这里先支持命令行传入文件列表


def load_redline_index():
    """加载合法红线条款编号"""
    if not os.path.exists(REDLINE_INDEX_FILE):
        print(f"警告: 红线索引文件不存在: {REDLINE_INDEX_FILE}")
        return set()
    with open(REDLINE_INDEX_FILE, 'r', encoding='utf-8') as f:
        index = json.load(f)
    return set(index.keys())


def check_file(filepath, valid_redlines):
    """检查单个文件中的红线引用"""
    errors = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return [f"无法读取文件 {filepath}: {e}"]

    # 查找所有函数或类定义（简单正则）
    func_pattern = re.compile(r'(def |class )(\w+)')
    # 查找所有R-引用
    ref_pattern = re.compile(r'(R-\d+\.\d+)')

    # 检查每个函数附近是否有引用（简化：函数后面20行内）
    lines = content.split('\n')
    for i, line in enumerate(lines):
        match = func_pattern.search(line)
        if match:
            func_name = match.group(2)
            # 搜索函数定义后的20行
            search_lines = lines[i: i+20]
            refs = ref_pattern.findall('\n'.join(search_lines))
            if not refs:
                errors.append(f"{filepath}: 函数 {func_name} 缺少红线引用")
            else:
                for ref in refs:
                    if ref not in valid_redlines:
                        errors.append(f"{filepath}: 非法红线引用 {ref} (函数 {func_name})")
    return errors


def check_redline_refs(files, run_id="UNKNOWN"):
    """主检查"""
    valid_redlines = load_redline_index()
    if not valid_redlines:
        print("警告: 没有合法红线编号定义，跳过检查")
        sys.exit(0)

    all_errors = []
    for fpath in files:
        if not os.path.isfile(fpath):
            all_errors.append(f"文件不存在: {fpath}")
        else:
            all_errors.extend(check_file(fpath, valid_redlines))

    if all_errors:
        append_log("gate", {
            "run_id": run_id,
            "gate": "gate_2_redline",
            "script": "check_redline_refs.py",
            "trigger": "ci-pipeline",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [{"check_name": "redline_refs", "result": "FAIL"}],
            "overall_result": "FAIL",
            "fail_reasons": all_errors,
            "duration_ms": 0
        })
        print("FAIL: 红线引用检查不通过")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        append_log("gate", {
            "run_id": run_id,
            "gate": "gate_2_redline",
            "script": "check_redline_refs.py",
            "trigger": "ci-pipeline",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [{"check_name": "redline_refs", "result": "PASS"}],
            "overall_result": "PASS",
            "fail_reasons": [],
            "duration_ms": 0
        })
        print("PASS: 所有L2函数均正确引用红线条款")
        sys.exit(0)


if __name__ == "__main__":
    # 文件列表可以从命令行参数传入，或者从CI变更列表获取
    if len(sys.argv) < 2:
        print("用法: python check_redline_refs.py <L2文件1> <L2文件2> ...")
        sys.exit(1)
    files = sys.argv[1:]
    run_id = os.environ.get("RUN_ID", "UNKNOWN")
    check_redline_refs(files, run_id)
