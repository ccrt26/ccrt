#!/usr/bin/env python3
"""
generate_role_entry_patch.py — 为 .claude/agents/*.md 生成瘦身入口补丁。

如果文件已包含 KRM 启动协议（## 0. 启动协议），则跳过（幂等）。
如果文件未包含，在文件头部插入启动协议段。

安全：输出待替换 diff 但不强制修改原文件（--apply 标志可执行实际修改）。
"""

import os
import sys
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
AGENTS_DIR = os.path.join(BASE_DIR, ".claude", "agents")

# 角色知识正文路径映射
ROLE_KNOWLEDGE_PATHS = {
    "玉夜": "knowledge/roles/yuye/README_玉夜知识入口.md",
    "青山": "knowledge/roles/qingshan/README_青山知识入口.md",
    "流金": "knowledge/roles/liujin/README_流金知识入口.md",
    "信鸽": "knowledge/roles/xinge/README_信鸽知识入口.md",
    "山猫": "knowledge/roles/shanmao/README_山猫知识入口.md",
    "腰子": "knowledge/roles/yaozi/README_腰子知识入口.md",
}

# 协作组入口映射
COLLAB_PATHS = {
    "金融团队-协作协议": "knowledge/roles/yaozi/README_腰子知识入口.md",
    "工程团队-协作协议": "knowledge/roles/",
}

STARTUP_PROTOCOL_BLOCK = """## 0. 启动协议

本文件是本角色被唤醒时的唯一启动入口。

本角色参与正式任务时，必须先完成以下启动动作：

1. 确认身份、职责、能力边界与禁止事项。
2. 读取项目级 FLOW / ROLE / TASK，确认当前任务流程编号与阶段门。
3. 读取 KRM 知识库读取清单，按须装配知识读取包。
4. 知识正文从 knowledge/ 统一入口按角色目录读取，不从本入口文件读取大段知识正文。
5. 输出时声明：已读文件、未读文件、未读原因、结论依据。

禁止默认全量读取角色知识库、项目地基、历史归档、G4/G5/G6 过程文件或外部原文。
禁止代签其他角色，禁止越权到其他角色职责范围，禁止跳过 KRM 直接读取知识库。

若本文件与 FLOW / ROLE / TASK / KRM 冲突，以项目级规则和 KRM 为准。

"""


def scan_agent_files():
    """Scan .claude/agents/*.md files."""
    files = []
    if not os.path.isdir(AGENTS_DIR):
        print(f"Agent directory not found: {AGENTS_DIR}")
        return files
    for fn in sorted(os.listdir(AGENTS_DIR)):
        if fn.endswith(".md"):
            fp = os.path.join(AGENTS_DIR, fn)
            files.append((fn, fp))
    return files


def has_startup_section(content):
    """Check if file already has ## 0. 启动协议."""
    return "## 0. 启动协议" in content or "## 0. 启动协议" in content


def extract_role_name(fname):
    """Extract Chinese role name from filename."""
    # Pattern: 角色名-昵称.md or simply 角色名.md
    # Known role files
    known = {
        "代码工匠-红结": "红结",
        "信息采集-信鸽": "信鸽",
        "宏观巡检-山猫": "山猫",
        "审计官-旧影": "旧影",
        "工程团队-协作协议": "工程团队",
        "构建工程师-千光": "千光",
        "数据监理-玉夜": "玉夜",
        "策略研究员-青山": "青山",
        "系统架构师-情墨": "情墨",
        "质量工程师-新安": "新安",
        "部署工程师-红枫": "红枫",
        "金融专家-腰子": "腰子",
        "金融团队-协作协议": "金融团队",
        "项目总监-阿黑": "阿黑",
        "风控官-流金": "流金",
    }
    for key, val in known.items():
        if fname.startswith(key) or fname == f"{key}.md":
            return val
    # Fallback: extract second part after -
    name_no_ext = fname.replace(".md", "")
    if "-" in name_no_ext:
        return name_no_ext.split("-", 1)[-1]
    return name_no_ext


def get_knowledge_path(role_name):
    """Get the knowledge README path for a role."""
    path = ROLE_KNOWLEDGE_PATHS.get(role_name)
    if not path:
        # Try COLLAB_PATHS
        for key, val in COLLAB_PATHS.items():
            if role_name in key or key in role_name:
                path = val
                break
    return path


def generate_patch(fname, fp, apply=False):
    """Generate or apply patch for a single agent file."""
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()

    if has_startup_section(content):
        return {"file": fp, "status": "skipped", "reason": "已包含启动协议"}

    role_name = extract_role_name(fname)
    kb_path = get_knowledge_path(role_name)

    # Insert launch protocol after YAML front matter or at top
    # Check for YAML front matter
    yaml_match = re.match(r'^---\n.*?\n---\n', content, re.DOTALL)
    if yaml_match:
        insert_pos = yaml_match.end()
        prefix = content[:insert_pos]
        suffix = content[insert_pos:]
    else:
        prefix = ""
        suffix = content

    new_content = prefix + STARTUP_PROTOCOL_BLOCK + suffix

    if kb_path:
        knowledge_note = f"\n> **知识正文路径**: `{kb_path}`\n"
        # Insert after the first section header or after startup_protocol
        new_content = new_content.replace(
            STARTUP_PROTOCOL_BLOCK,
            STARTUP_PROTOCOL_BLOCK + knowledge_note
        )

    diff_lines = []
    old_lines = content.split("\n")
    new_lines = new_content.split("\n")
    added_lines = len(new_lines) - len(old_lines)

    if apply:
        with open(fp, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"file": fp, "status": "applied", "added_lines": added_lines}

    return {"file": fp, "status": "patch_ready", "added_lines": added_lines, "role": role_name}


def main():
    apply = "--apply" in sys.argv
    dry_run = "--dry-run" in sys.argv or not apply

    files = scan_agent_files()
    print(f"Scanned {len(files)} agent files")
    print()

    results = []
    for fname, fp in files:
        result = generate_patch(fname, fp, apply=apply)
        results.append(result)

    # Report
    patched = [r for r in results if r["status"] == "applied"]
    skipped = [r for r in results if r["status"] == "skipped"]
    ready = [r for r in results if r["status"] == "patch_ready"]

    if patched:
        print(f"=== Applied patches: {len(patched)} ===")
        for r in patched:
            print(f"  {r['file']}: +{r['added_lines']} lines")
    if ready:
        print(f"\n=== Patches ready to apply (use --apply): {len(ready)} ===")
        for r in ready:
            print(f"  [{r['role']}] {r['file']}: +{r['added_lines']} lines")
    if skipped:
        print(f"\n=== Already patched (skipped): {len(skipped)} ===")
        for r in skipped:
            print(f"  {r['file']}")

    print(f"\nTotal: {len(results)} files")
    if dry_run and not apply:
        print("\nDry run: use --apply to write changes. Script is idempotent; re-running with --apply only patches unpatched files.")


if __name__ == "__main__":
    main()
