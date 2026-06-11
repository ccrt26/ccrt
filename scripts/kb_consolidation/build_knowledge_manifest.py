#!/usr/bin/env python3
"""
build_knowledge_manifest.py — 扫描现有知识源，生成 knowledge manifest.json 和 README。

幂等：重复执行不会重复写入条目。
"""

import json
import os
import sys
import glob as glob_module

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "00_项目地基", "07_知识进化", "knowledge")
MANIFEST_PATH = os.path.join(OUT_DIR, "manifest.json")
README_PATH = os.path.join(OUT_DIR, "README_KRM_知识入口.md")


def scan_agent_files():
    """Scan .claude/agents/*.md for role entry points."""
    entries = []
    pattern = os.path.join(BASE_DIR, ".claude", "agents", "*.md")
    for fp in sorted(glob_module.glob(pattern)):
        fname = os.path.basename(fp)
        role_id = fname.replace(".md", "").split("-")[-1] if "-" in fname else fname.replace(".md", "")
        entries.append({
            "file_id": f"agent-entry-{role_id}",
            "source_path": fp,
            "target_path": fp,  # stays in place
            "file_type": "role_entry",
            "read_level": "L0",
            "owner_role": role_id,
            "scenario": "all",
            "is_execution_rule": True,
            "is_process_archive": False,
            "is_external_source": False,
            "enter_startup_context": True,
            "migration_action": "keep_in_place",
            "status": "active",
        })
    return entries


def scan_role_knowledge():
    """Scan knowledge/roles/<role>/ for each of the 6 roles."""
    entries = []
    roles_map = {
        "yuye": "玉夜", "qingshan": "青山", "liujin": "流金",
        "xinge": "信鸽", "shanmao": "山猫", "yaozi": "腰子",
    }
    for rid, rname in roles_map.items():
        role_dir = os.path.join(BASE_DIR, "knowledge", "roles", rid)
        if os.path.isdir(role_dir):
            for fn in sorted(os.listdir(role_dir)):
                if fn.endswith(".md") and fn != "README_README.md":
                    fp = os.path.join(role_dir, fn)
                    fname_short = fn.replace(".md", "")
                    entries.append({
                        "file_id": f"kb-{rid}-{fname_short}",
                        "source_path": fp,
                        "target_path": fp,
                        "file_type": "role_knowledge",
                        "read_level": "L2",
                        "owner_role": rid,
                        "scenario": "all",
                        "is_execution_rule": False,
                        "is_process_archive": False,
                        "is_external_source": False,
                        "enter_startup_context": False,
                        "migration_action": "keep_in_place",
                        "status": "active",
                    })
            # Add README entry
            readme = os.path.join(role_dir, f"README_{rname}知识入口.md")
            if os.path.exists(readme):
                entries.append({
                    "file_id": f"kb-{rid}-readme",
                    "source_path": readme,
                    "target_path": readme,
                    "file_type": "role_entry_readme",
                    "read_level": "L0",
                    "owner_role": rid,
                    "scenario": "all",
                    "is_execution_rule": True,
                    "is_process_archive": False,
                    "is_external_source": False,
                    "enter_startup_context": True,
                    "migration_action": "keep_in_place",
                    "status": "active",
                })
    return entries


def scan_governance():
    """Scan knowledge/governance/ for shared policy files."""
    entries = []
    gov_dir = os.path.join(BASE_DIR, "knowledge", "governance")
    if os.path.isdir(gov_dir):
        for fn in sorted(os.listdir(gov_dir)):
            if fn.endswith(".md"):
                fp = os.path.join(gov_dir, fn)
                fname_short = fn.replace(".md", "")
                entries.append({
                    "file_id": f"gov-{fname_short}",
                    "source_path": fp,
                    "target_path": fp,
                    "file_type": "shared_policy",
                    "read_level": "L3",
                    "owner_role": "all",
                    "scenario": "knowledge_evolution",
                    "is_execution_rule": True,
                    "is_process_archive": False,
                    "is_external_source": False,
                    "enter_startup_context": False,
                    "migration_action": "keep_in_place",
                    "status": "active",
                })
    return entries


def scan_role_configs():
    """Scan configs/role_routing.yaml for role routing."""
    entries = []
    route_path = os.path.join(BASE_DIR, "configs", "role_routing.yaml")
    if os.path.exists(route_path):
        entries.append({
            "file_id": "config-role-routing",
            "source_path": route_path,
            "target_path": route_path,
            "file_type": "routing_config",
            "read_level": "L0",
            "owner_role": "all",
            "scenario": "all",
            "is_execution_rule": True,
            "is_process_archive": False,
            "is_external_source": False,
            "enter_startup_context": True,
            "migration_action": "keep_in_place",
            "status": "active",
        })
    lit_path = os.path.join(BASE_DIR, "configs", "literature_observation.yaml")
    if os.path.exists(lit_path):
        entries.append({
            "file_id": "config-literature-observer",
            "source_path": lit_path,
            "target_path": lit_path,
            "file_type": "observation_config",
            "read_level": "L2",
            "owner_role": "all",
            "scenario": "literature_review",
            "is_execution_rule": True,
            "is_process_archive": False,
            "is_external_source": False,
            "enter_startup_context": False,
            "migration_action": "keep_in_place",
            "status": "active",
        })
    return entries


def scan_six_libraries():
    """Reference the six libraries (统一解读/六库/) — reference only."""
    entries = []
    six_dir = os.path.join(BASE_DIR, "统一解读", "六库")
    if os.path.isdir(six_dir):
        for fn in sorted(os.listdir(six_dir)):
            if fn.endswith(".md"):
                fp = os.path.join(six_dir, fn)
                fname_short = fn.replace(".md", "")
                entries.append({
                    "file_id": f"sixlib-{fname_short}",
                    "source_path": fp,
                    "target_path": fp,  # stays in place
                    "file_type": "external_source",
                    "read_level": "L3",
                    "owner_role": "all",
                    "scenario": "audit",
                    "is_execution_rule": False,
                    "is_process_archive": False,
                    "is_external_source": True,
                    "enter_startup_context": False,
                    "migration_action": "reference_only",
                    "status": "legacy_ref",
                })
    return entries


def scan_interp_packs():
    """Reference 统一解读/角色解释包/ — reference only."""
    entries = []
    ip_dir = os.path.join(BASE_DIR, "统一解读", "角色解释包")
    if os.path.isdir(ip_dir):
        for fn in sorted(os.listdir(ip_dir)):
            if fn.endswith(".md"):
                fp = os.path.join(ip_dir, fn)
                fname_short = fn.replace(".md", "")
                entries.append({
                    "file_id": f"interp-{fname_short}",
                    "source_path": fp,
                    "target_path": fp,
                    "file_type": "external_source",
                    "read_level": "L3",
                    "owner_role": "all",
                    "scenario": "audit",
                    "is_execution_rule": False,
                    "is_process_archive": False,
                    "is_external_source": True,
                    "enter_startup_context": False,
                    "migration_action": "reference_only",
                    "status": "legacy_ref",
                })
    return entries


def scan_external_literature():
    """Scan external literature indexes."""
    entries = []
    ext_dir = os.path.join(BASE_DIR, "knowledge", "external_literature", "indexes")
    if os.path.isdir(ext_dir):
        for fn in sorted(os.listdir(ext_dir)):
            fp = os.path.join(ext_dir, fn)
            if os.path.isfile(fp):
                fname_short = fn.replace(".json", "").replace(".md", "")
                entries.append({
                    "file_id": f"extlit-{fname_short}",
                    "source_path": fp,
                    "target_path": fp,
                    "file_type": "external_source",
                    "read_level": "L3",
                    "owner_role": "all",
                    "scenario": "literature_review",
                    "is_execution_rule": False,
                    "is_process_archive": False,
                    "is_external_source": True,
                    "enter_startup_context": False,
                    "migration_action": "reference_only",
                    "status": "legacy_ref",
                })
    return entries


def scan_knowledge_evolution():
    """Scan 00_项目地基/07_知识进化/ for evolution framework files."""
    entries = []
    evo_dir = os.path.join(BASE_DIR, "00_项目地基", "07_知识进化")
    # Top-level files
    if os.path.isdir(evo_dir):
        for fn in sorted(os.listdir(evo_dir)):
            fp = os.path.join(evo_dir, fn)
            if os.path.isfile(fn) and fn.endswith(".md"):
                continue  # handled in sub-scans
            # Skip knowledge/ subdir (our output dir)
            if fn == "knowledge":
                continue
        # Specific known files
        known = [
            "L2_INDEX_知识进化总账_v1.0.md",
            "L2_SCHEMA_KnowledgeUpdateCandidate_v1.0.md",
            "L2_INDEX_知识库读取分层与执行文件清单_v1.0.md",
        ]
        for fn in known:
            fp = os.path.join(evo_dir, fn)
            if os.path.exists(fp):
                fname_short = fn.replace(".md", "")
                entries.append({
                    "file_id": f"evo-{fname_short}",
                    "source_path": fp,
                    "target_path": fp,
                    "file_type": "execution_rule",
                    "read_level": "L1",
                    "owner_role": "all",
                    "scenario": "knowledge_evolution",
                    "is_execution_rule": True,
                    "is_process_archive": False,
                    "is_external_source": False,
                    "enter_startup_context": False,
                    "migration_action": "keep_in_place",
                    "status": "active",
                })
    return entries


def scan_adapters():
    """Scan scenario adapters."""
    entries = []
    ad_dir = os.path.join(BASE_DIR, "00_项目地基", "07_知识进化", "scenario_adapters")
    if os.path.isdir(ad_dir):
        for fn in sorted(os.listdir(ad_dir)):
            if fn.endswith(".md"):
                fp = os.path.join(ad_dir, fn)
                fname_short = fn.replace(".md", "")
                entries.append({
                    "file_id": f"adapter-{fname_short}",
                    "source_path": fp,
                    "target_path": fp,
                    "file_type": "scenario_adapter",
                    "read_level": "L1",
                    "owner_role": "all",
                    "scenario": fn.replace("L2_ADAPTER_", "").replace("_v1.0.md", ""),
                    "is_execution_rule": True,
                    "is_process_archive": False,
                    "is_external_source": False,
                    "enter_startup_context": False,
                    "migration_action": "keep_in_place",
                    "status": "active",
                })
    return entries


def scan_old_agent_knowledge():
    """Scan .claude/agents/*-知识库/ — mark as legacy refs."""
    entries = []
    agent_kb_dir = os.path.join(BASE_DIR, ".claude", "agents")
    if os.path.isdir(agent_kb_dir):
        for d in sorted(os.listdir(agent_kb_dir)):
            if d.endswith("-知识库"):
                full = os.path.join(agent_kb_dir, d)
                if os.path.isdir(full):
                    for fn in sorted(os.listdir(full)):
                        if fn.endswith(".md"):
                            fp = os.path.join(full, fn)
                            fname_short = fn.replace(".md", "")
                            entries.append({
                                "file_id": f"oldkb-{d}-{fname_short}",
                                "source_path": fp,
                                "target_path": fp,
                                "file_type": "external_source",
                                "read_level": "L3",
                                "owner_role": d.replace("-知识库", ""),
                                "scenario": "audit",
                                "is_execution_rule": False,
                                "is_process_archive": False,
                                "is_external_source": True,
                                "enter_startup_context": False,
                                "migration_action": "legacy_ref",
                                "status": "legacy_ref",
                            })
    return entries


def build_manifest():
    """Build the complete manifest."""
    all_entries = []
    all_entries.extend(scan_agent_files())
    all_entries.extend(scan_role_knowledge())
    all_entries.extend(scan_governance())
    all_entries.extend(scan_role_configs())
    all_entries.extend(scan_six_libraries())
    all_entries.extend(scan_interp_packs())
    all_entries.extend(scan_external_literature())
    all_entries.extend(scan_knowledge_evolution())
    all_entries.extend(scan_adapters())
    all_entries.extend(scan_old_agent_knowledge())

    # Remove duplicates by file_id
    seen = set()
    unique = []
    for e in all_entries:
        if e["file_id"] not in seen:
            seen.add(e["file_id"])
            unique.append(e)

    manifest = {
        "meta": {
            "version": "1.0",
            "generated": "2026-06-11",
            "total_entries": len(unique),
            "description": "KRM unified knowledge manifest — maps all knowledge sources to target roles, types, and read levels",
        },
        "entries": unique,
    }
    return manifest


def write_manifest(manifest):
    """Write manifest.json idempotently."""
    existing = []
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f).get("entries", [])
        existing_ids = {e["file_id"] for e in existing}
        new_count = 0
        for e in manifest["entries"]:
            if e["file_id"] not in existing_ids:
                existing.append(e)
                existing_ids.add(e["file_id"])
                new_count += 1
        if new_count > 0:
            # Re-sort
            existing.sort(key=lambda x: x["file_id"])
            manifest["entries"] = existing
            manifest["meta"]["total_entries"] = len(existing)
            with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            print(f"manifest.json: added {new_count} new entries, total {len(existing)}")
        else:
            print(f"manifest.json: unchanged, {len(existing)} entries (idempotent)")
    else:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"manifest.json: created with {len(manifest['entries'])} entries")


def write_readme():
    """Write README_KRM_知识入口.md idempotently."""
    content = """# KRM 知识统一入口

> **知识正文统一管理位置**
> 版本：v1.0 | 更新日期：2026-06-11

---

## 1. 架构

```
.claude/agents/               ← 只做角色启动入口（身份+职责+KRM规则+禁止事项）
  ↓
knowledge/                    ← 知识正文统一入口
  ├── manifest.json           ← 全知识源清单
  ├── roles/<role>/           ← 角色知识（六个角色各一个目录）
  ├── shared/                 ← 共享规则（证据/风控/输出/协作/反例/参数）
  └── legacy_refs/            ← 历史文件引用索引（不进入启动上下文）
```

## 2. 读取规则

| 层级 | 读取方式 | 说明 |
|:-----|:---------|:-----|
| .claude/agents/*.md | 启动时必读 | 角色身份、启动协议、KRM规则 |
| roles/<role>/README | 任务装配时读 | 当前角色的知识路由 |
| roles/<role>/01-05 | 按任务类型按需读 | 具体知识正文 |
| shared/ | 跨角色共享时读 | 不默认加载 |
| manifest.json | 索引/审计时读 | 定位任何知识源 |
| legacy_refs/ | 历史追溯时读 | 不进启动上下文 |

> **外部原文、六库原始文件、旧角色解释包**保持原地，不作为启动上下文内容。
> 需要通过 manifest.json 中的 migration_action 判断其用途。

## 3. 与 .claude/agents 的关系

- `.claude/agents/*.md` 是**角色启动入口**，不是知识仓库
- 每个启动入口必须声明：
  - 角色身份与职责边界
  - 本角色知识正文路径 (`knowledge/roles/<role>/`)
  - KRM 读取流程
  - 本次不得全量读取声明
  - 输出格式
  - 禁止代签、禁止越权、禁止跳过 KRM
- 大段知识正文应迁移至 `knowledge/roles/<role>/`

## 4. 与六库和历史解释包的关系

| 来源 | 位置 | 启动上下文 |
|:-----|:-----|:-----------|
| 六库原始文件 | 统一解读/六库/ | ❌ 不进 |
| 角色解释包原始文件 | 统一解读/角色解释包/ | ❌ 不进 |
| 旧知识库 | .claude/agents/*-知识库/ | ❌ 不进 |
| 外部文献原文 | knowledge/external_literature/raw/ | ❌ 不进 |
| 文献摘要卡片 | knowledge/external_literature/cards/ | ✅ 摘要可进 |
| manifest.json | 本目录 | ✅ 审计/索引时可进 |

## 5. 禁止事项

| 禁止项 | 说明 |
|:-------|:------|
| ⛔ 不把知识正文留在 .claude/agents 入口 | 迁移至 knowledge/roles/<role>/ |
| ⛔ 不把所有知识合并成一个超大 md | 按角色和任务拆分 |
| ⛔ 不让角色启动时全量读取 knowledge | 按 KRM 装配读取包 |
| ⛔ 不把外部原文塞进启动上下文 | 按三层结构处理 |
| ⛔ 不修改生产入口 | 日报/周报/荐股/模拟交易不动 |
| ⛔ 不生成真实 KnowledgeUpdateCandidate | 本阶段只做集中治理 |
| ⛔ 不声称 formal pipeline PASS | 本阶段未创建 formal pipeline |
"""
    if os.path.exists(README_PATH):
        with open(README_PATH, "r", encoding="utf-8") as f:
            existing = f.read()
        if existing.strip() == content.strip():
            print("README_KRM_知识入口.md: unchanged (idempotent)")
            return
        # Append version note if modified
        print("README_KRM_知识入口.md: updated")
    else:
        print("README_KRM_知识入口.md: created")

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    print("Building knowledge manifest...")
    manifest = build_manifest()
    write_manifest(manifest)
    write_readme()
    print("Done.")


if __name__ == "__main__":
    main()
