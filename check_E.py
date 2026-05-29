#!/usr/bin/env python3
"""
check_E.py - Token与文件规模门禁 (用于 pre-commit 和 CI)
检查：
1. Agent/Command文件行数/KB限制
2. Python文件不超过500行 (新文件)
3. Python脚本print()数量 (stdout正常模式不超过8个)
4. 大文件直接读取检测 (禁止AI读取 >500KB 数据)
"""
import sys
import os
import re

MAX_LINES = 500
MAX_AGENT_LINES = 250
MAX_COMMAND_LINES = 40
MAX_COMMAND_SIZE_KB = 2
MAX_PRINT_COUNT = 8
MAX_AI_READ_SIZE_KB = 500


def check_file(path):
    """对单个文件执行所有检查"""
    if not os.path.isfile(path):
        return

    # 读取文件内容
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        lines = content.split('\n')
        line_count = len(lines)
        size_kb = os.path.getsize(path) / 1024
    except Exception as e:
        print(f"WARNING: 无法读取文件 {path}: {e}")
        return

    # 1. Agent文件限制
    if ".claude/agents/" in path.replace("\\", "/"):
        if line_count > MAX_AGENT_LINES or size_kb > 12:
            print(f"BLOCKED: Agent文件 {path} 超标 ({line_count}行, {size_kb:.1f}KB)")
            sys.exit(1)

    # 2. Command文件限制
    if ".claude/commands/" in path.replace("\\", "/"):
        if line_count > MAX_COMMAND_LINES or size_kb > MAX_COMMAND_SIZE_KB:
            print(f"BLOCKED: Command文件 {path} 超标 ({line_count}行, {size_kb:.1f}KB)")
            sys.exit(1)

    # 3. Python文件行数限制 (跳过已有超大文件的白名单)
    if path.endswith(".py"):
        # 可配置豁免列表
        exempt_files = ["scoring_engine_v2.py"]  # 已纳入拆分计划
        if os.path.basename(path) not in exempt_files:
            if line_count > MAX_LINES:
                print(f"BLOCKED: Python文件 {path} 超过 {MAX_LINES} 行 ({line_count}行)")
                sys.exit(1)

        # 4. Print数量检查 (只对核心脚本目录)
        if "scripts/" in path or "src/" in path:
            print_count = len(re.findall(r'^\s*print\(', content, re.MULTILINE))
            # 排除测试文件
            if "test" not in path and print_count > MAX_PRINT_COUNT:
                print(f"WARNING: {path} 有 {print_count} 个print()，正常模式应 ≤ {MAX_PRINT_COUNT}")
                # 不阻断，仅警告（可根据需要改为阻断）

        # 5. 大文件读取检测
        if line_count > 0:
            # 查找 open 读取操作，检查是否有硬编码的大文件路径
            # 简单正则匹配 open(...) 中包含 data_ 等字样
            open_pattern = re.findall(r'open\(["\']([^"\']+)["\']', content)
            for file_ref in open_pattern:
                if file_ref.startswith("data_") or file_ref.endswith(".json"):
                    # 检查该文件是否存在且大小超标
                    if os.path.exists(file_ref) and os.path.getsize(file_ref) / 1024 > MAX_AI_READ_SIZE_KB:
                        print(f"WARNING: {path} 可能尝试读取大文件 {file_ref}")
                        # 不阻断，仅警告


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python check_E.py <文件列表>")
        sys.exit(1)

    for file_path in sys.argv[1:]:
        check_file(file_path)
