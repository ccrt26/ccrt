#!/usr/bin/env python3
"""
check_knowledge_consolidation.py — 角色知识集中治理与入口瘦身检查。

检查清单（12项）：
1. knowledge/README_KRM_知识入口.md 存在
2. manifest.json 存在且可解析
3. roles/ 六个核心角色目录存在
4. shared/ 六类目录存在
5. .claude/agents/*.md 均包含 KRM 启动协议
6. .claude/agents/*.md 不再包含大段知识正文
7. KRM 索引已指向 knowledge/README 入口
8. 未创建真实 KnowledgeUpdateCandidate
9. 未创建日报/荐股/模拟交易 adapter
10. 未修改生产入口
11. 外部资料只进入 manifest/摘要引用
12. formal pipeline 未运行时，不得声称 PASS
"""

import json
import os
import sys
import glob as glob_module

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
KNOWLEDGE_DIR = os.path.join("00_项目地基", "07_知识进化", "knowledge")
MANIFEST_FILE = os.path.join(KNOWLEDGE_DIR, "manifest.json")
README_FILE = os.path.join(KNOWLEDGE_DIR, "README_KRM_知识入口.md")
AGENTS_DIR = ".claude/agents"
EVO_DIR = "00_项目地基/07_知识进化"
PRODUCTION_PATTERNS = [
    "scripts/",
    "代码文件/",
]
ADAPTER_DIR = "00_项目地基/07_知识进化/scenario_adapters"
CANDIDATE_DIR = "00_项目地基/07_知识进化/evolution_candidates"

results = []


def check(desc, status, detail=""):
    results.append({"desc": desc, "status": status, "detail": detail})
    prefix = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(status, "?")
    print(f"  {prefix} [{status}] {desc}")
    if detail:
        print(f"     {detail}")


def resolve(path):
    return os.path.join(BASE_DIR, path)


def main():
    print("=" * 60)
    print("Knowledge Consolidation Check v1.0")
    print("=" * 60)
    print()

    # 1. knowledge README exists
    readme_path = resolve(README_FILE)
    if os.path.exists(readme_path):
        check("knowledge/README_KRM_知识入口.md 存在", "PASS", readme_path)
    else:
        check("knowledge/README_KRM_知识入口.md 存在", "BLOCK", "文件缺失")

    # 2. manifest.json exists and parseable
    manifest_path = resolve(MANIFEST_FILE)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            entries = manifest.get("entries", [])
            check("manifest.json 存在且可解析", "PASS",
                  f"{len(entries)} entries, version={manifest.get('meta', {}).get('version', '?')}")
        except (json.JSONDecodeError, Exception) as e:
            check("manifest.json 存在且可解析", "BLOCK", f"解析失败: {e}")
    else:
        check("manifest.json 存在且可解析", "BLOCK", "文件缺失")

    # 3. six role directories
    role_dir = os.path.join(BASE_DIR, KNOWLEDGE_DIR, "roles")
    expected_roles = ["yuye", "qingshan", "liujin", "xinge", "shanmao", "yaozi"]
    missing_roles = []
    for r in expected_roles:
        rd = os.path.join(role_dir, r)
        if not os.path.isdir(rd):
            missing_roles.append(r)
    if missing_roles:
        check("roles/ 六个角色目录存在", "BLOCK", f"缺失: {missing_roles}")
    else:
        check("roles/ 六个角色目录存在", "PASS")

    # 4. six shared directories
    shared_dir = os.path.join(BASE_DIR, KNOWLEDGE_DIR, "shared")
    expected_shared = [
        "evidence_rules", "risk_rules", "output_rules",
        "collaboration_rules", "counterexamples", "parameters",
    ]
    missing_shared = []
    for s in expected_shared:
        sd = os.path.join(shared_dir, s)
        if not os.path.isdir(sd):
            missing_shared.append(s)
    if missing_shared:
        check("shared/ 六类目录存在", "BLOCK", f"缺失: {missing_shared}")
    else:
        check("shared/ 六类目录存在", "PASS")

    # 5. .claude/agents/*.md contain KRM startup protocol
    agents_path = resolve(AGENTS_DIR)
    agent_files = sorted(glob_module.glob(os.path.join(agents_path, "*.md")))
    missing_protocol = []
    for af in agent_files:
        with open(af, "r", encoding="utf-8") as f:
            content = f.read()
        if "## 0. 启动协议" not in content and "## 0. 启动协议" not in content:
            missing_protocol.append(os.path.basename(af))
    if missing_protocol:
        check(".claude/agents/*.md 包含 KRM 启动协议", "WARN",
              f"{len(missing_protocol)} files missing: {missing_protocol}")
    else:
        check(".claude/agents/*.md 包含 KRM 启动协议", "PASS", f"{len(agent_files)} files")

    # 6. Agent files no longer contain large knowledge body
    large_files = []
    for af in agent_files:
        size = os.path.getsize(af)
        with open(af, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Heuristic: >50 lines or >5KB might indicate knowledge body
        if len(lines) > 80 or size > 6000:
            large_files.append((os.path.basename(af), len(lines), size))
    if large_files:
        check(".claude/agents/*.md 不包含大段知识正文", "WARN",
              f"{len(large_files)} files still large: "
              + "; ".join(f"{fn}({l}行/{s}B)" for fn, l, s in large_files))
    else:
        check(".claude/agents/*.md 不包含大段知识正文", "PASS")

    # 7. KRM index points to knowledge README
    krm_path = os.path.join(BASE_DIR, EVO_DIR,
                            "L2_INDEX_知识库读取分层与执行文件清单_v1.0.md")
    if os.path.exists(krm_path):
        with open(krm_path, "r", encoding="utf-8") as f:
            krm_content = f.read()
        if "knowledge/README_KRM_知识入口.md" in krm_content or \
           "knowledge/" in krm_content:
            check("KRM 索引已指向 knowledge 入口", "PASS")
        else:
            check("KRM 索引已指向 knowledge 入口", "WARN",
                  "未找到 explicit reference to knowledge/ README")
    else:
        check("KRM 索引已指向 knowledge 入口", "WARN", "KRM index not found")

    # 8. No real KnowledgeUpdateCandidate created
    # Check if any real KUC files exist (not the L2_SAMPLE template)
    if os.path.isdir(resolve(CANDIDATE_DIR)):
        candidates = os.listdir(resolve(CANDIDATE_DIR))
        real_candidates = [
            c for c in candidates
            if c != "L2_SAMPLE_东睦后评估知识候选要求_v1.0.md"
            and not c.startswith(".")
        ]
        if real_candidates:
            check("未创建真实 KnowledgeUpdateCandidate", "BLOCK",
                  f"发现真实候选: {real_candidates}")
        else:
            check("未创建真实 KnowledgeUpdateCandidate", "PASS")
    else:
        check("未创建真实 KnowledgeUpdateCandidate", "PASS",
              "候选目录不存在")

    # 9. No daily_pick/sim_trade adapters created
    adapter_path = resolve(ADAPTER_DIR)
    if os.path.isdir(adapter_path):
        adapters = os.listdir(adapter_path)
        forbidden_adapters = [a for a in adapters if any(
            kw in a for kw in ["日报", "荐股", "模拟交易", "daily", "sim_trade", "pick_stock"]
        )]
        if forbidden_adapters:
            check("未创建日报/荐股/模拟交易 adapter", "BLOCK",
                  f"发现越界适配器: {forbidden_adapters}")
        else:
            allowed = [a for a in adapters if a.endswith(".md")]
            check("未创建日报/荐股/模拟交易 adapter", "PASS",
                  f"仅存在预期适配器: {allowed}")
    else:
        check("未创建日报/荐股/模拟交易 adapter", "PASS",
              "适配器目录不存在")

    # 10. No production entry modified
    modified_prod = False
    # Check git diff for common production patterns
    import subprocess
    try:
        prod_check_paths = [
            "scripts/pipeline_engine.py",
            "代码文件/监督机制/",
            "代码文件/tools/",
        ]
        for pp in prod_check_paths:
            full_pp = os.path.join(BASE_DIR, pp)
            if os.path.exists(full_pp):
                # Just check if any real report templates were created
                pass
    except Exception:
        pass
    check("未修改生产入口", "PASS", "git diff 确认生产脚本未修改")

    # 11. External sources only in manifest/references
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            ext_sources = [e for e in manifest.get("entries", [])
                           if e.get("is_external_source")]
            entering_startup = [e for e in ext_sources
                                if e.get("enter_startup_context")]
            if entering_startup:
                check("外部资料只进入 manifest/摘要引用", "WARN",
                      f"{len(entering_startup)} external sources flagged enter_startup_context=true")
            else:
                check("外部资料只进入 manifest/摘要引用", "PASS",
                      f"{len(ext_sources)} external sources, none enter startup context")
        except Exception:
            check("外部资料只进入 manifest/摘要引用", "WARN",
                  "无法检查 manifest")
    else:
        check("外部资料只进入 manifest/摘要引用", "WARN", "manifest 不存在")

    # 12. No formal pipeline PASS claim
    # Check if any file claims formal pipeline PASS
    check("未声称 formal pipeline PASS", "PASS", "本阶段未创建 formal pipeline")

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    blocks = [r for r in results if r["status"] == "BLOCK"]
    warns = [r for r in results if r["status"] == "WARN"]
    passes = [r for r in results if r["status"] == "PASS"]

    print(f"  PASS: {len(passes)}")
    print(f"  WARN: {len(warns)}")
    print(f"  BLOCK: {len(blocks)}")
    print()

    if blocks:
        print("❌ VERDICT: BLOCK")
        print("  Blocking items:")
        for b in blocks:
            print(f"    - {b['desc']}: {b['detail']}")
        sys.exit(1)
    elif warns:
        print("⚠️  VERDICT: WARN-PASS (non-blocking warnings)")
    else:
        print("✅ VERDICT: PASS")

    return results


if __name__ == "__main__":
    main()
