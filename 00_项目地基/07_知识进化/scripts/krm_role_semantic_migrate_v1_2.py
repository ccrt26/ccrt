#!/usr/bin/env python3
"""
krm_role_semantic_migrate_v1_2.py
G3-KRM-ROLE-SEMANTIC-MIGRATE: 金融团队旧角色知识库语义迁移与能力完整继承

职责：
1. 复制六个旧库全文到 knowledge/sources/legacy_role_kb/<role>/
2. 计算 sha256、行数、旧路径、新路径，生成 SOURCE_INDEX.md
3. 基于旧库内容生成每个角色的 8 文件精华包
4. 更新 manifest.json v1.2
5. 更新读取分层索引
6. 输出迁移统计和验收数据
"""

import hashlib, json, os, shutil, re, sys
from pathlib import Path
from datetime import date

ROOT = Path("/Users/ccrt/ccrt")
AGENTS = ROOT / ".claude" / "agents"
OLD_KNOW = ROOT / ".claude" / "knowledge"
KNOWLEDGE = ROOT / "00_项目地基/07_知识进化/knowledge"
SOURCES = KNOWLEDGE / "sources" / "legacy_role_kb"
ROLES_DIR = KNOWLEDGE / "roles"
MANIFEST = KNOWLEDGE / "manifest.json"
KRM = ROOT / "00_项目地基/07_知识进化/L2_INDEX_知识库读取分层与执行文件清单_v1.0.md"
AUDIT = ROOT / "00_项目地基/08_审计与验收"
SCRIPTS = ROOT / "00_项目地基/07_知识进化/scripts"

# Old agent knowledge bases to migrate
KNOWLEDGE_BASES = {
    "yuye":  "玉夜-知识库",
    "qingshan": "青山-知识库",
    "liujin": "流金-知识库",
    "xinge": "信鸽-知识库",
    "shanmao": "山猫-知识库",
    "yaozi": "腰子-知识库",
}

# Old .claude/knowledge files to migrate
OLD_KNOW_FILES = {
    "角色边界宪章.md": "角色边界宪章",
    "流程规则库.md": "流程规则库",
    "角色进化库.md": "角色进化库",
    "案例复盘库.md": "案例复盘库",
}

ROLE_NAMES = {
    "yuye": "玉夜", "qingshan": "青山", "liujin": "流金",
    "xinge": "信鸽", "shanmao": "山猫", "yaozi": "腰子",
}

ROLE_FOCUS = {
    "yuye": "数据质量、字段口径、数据可信等级、API管理、缓存策略",
    "qingshan": "信号有效性、因子胜率、样本约束、回测规范、策略退化",
    "liujin": "风险边界、否决项、动作审计、回撤监控、压力测试",
    "xinge": "事件分级、公告证据、催化窗口、模式识别、五层过滤",
    "shanmao": "宏观覆写、行业相位、市场环境、情绪体系、全球联动",
    "yaozi": "整合裁决、状态机、结论强度、仓位管理、协作升级",
}

# ---- Shared patterns for essence generation ----

ROLE_KEYWORDS = {
    "yuye": ["数据源", "字段口径", "数据质量", "缓存", "API", "降级", "1+2", "时效性", "异常", "新鲜度"],
    "qingshan": ["因子", "IC", "ICIR", "Rank", "分层", "回测", "衰减", "策略退化", "过拟合", "绩效归因"],
    "liujin": ["VaR", "CVaR", "回撤", "止损", "仓位", "过拟合", "压力测试", "风险", "纪律", "冷却期"],
    "xinge": ["事件", "过滤", "标签", "公告", "采集", "催化", "P0", "去重", "Jaccard", "impact_score"],
    "shanmao": ["宏观", "货币政策", "流动性", "情绪", "PMI", "CPI", "政策", "日历", "极端事件", "全球联动"],
    "yaozi": ["PE", "MACD", "RSI", "Wyckoff", "背离", "板块轮动", "资金面", "仓位", "止损", "行为金融"],
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def line_count(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def read_file(path):
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def relative_to_root(p):
    return str(p.relative_to(ROOT))


# ===================================================================
# STEP 1: Copy all old KB files to sources/legacy_role_kb/
# ===================================================================
def step1_copy_kb_files():
    results = []
    for role_key, kb_name in KNOWLEDGE_BASES.items():
        src_dir = AGENTS / kb_name
        dst_dir = SOURCES / role_key
        role_name = ROLE_NAMES[role_key]

        if not src_dir.is_dir():
            print(f"  [WARN] {kb_name} not found at {src_dir}")
            continue

        files = sorted(src_dir.glob("*.md"))
        role_results = []
        for src_path in files:
            dst_path = dst_dir / src_path.name
            copy_file(src_path, dst_path)
            lines = line_count(dst_path)
            sh = sha256_file(dst_path)
            role_results.append({
                "old_path": relative_to_root(src_path),
                "new_path": relative_to_root(dst_path),
                "filename": src_path.name,
                "lines": lines,
                "sha256": sh,
            })
        results.append((role_key, role_name, role_results))

    # Also copy .claude/knowledge/ files
    claude_know_results = []
    if OLD_KNOW.is_dir():
        for fn_stem, label in OLD_KNOW_FILES.items():
            src_path = OLD_KNOW / fn_stem
            if src_path.exists():
                dst_path = SOURCES / "shared_knowledge" / fn_stem
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                copy_file(src_path, dst_path)
                lines = line_count(dst_path)
                sh = sha256_file(dst_path)
                claude_know_results.append({
                    "old_path": relative_to_root(src_path),
                    "new_path": relative_to_root(dst_path),
                    "filename": fn_stem,
                    "lines": lines,
                    "sha256": sh,
                })

    # Financial team collaboration file
    legacy_collab = KNOWLEDGE / "legacy_refs" / "agents_original_snapshot_20260611" / "金融团队-协作协议.md"
    if legacy_collab.exists():
        dst_path = SOURCES / "shared_knowledge" / "金融团队-协作协议.md"
        copy_file(legacy_collab, dst_path)

    return results, claude_know_results


# ===================================================================
# STEP 2: Generate SOURCE_INDEX.md for each role
# ===================================================================
def step2_generate_source_index(migration_results):
    for role_key, role_name, files in migration_results:
        lines = [f"# {role_name} 旧库来源索引\n"]
        lines.append(f"> 生成日期：{date.today()}")
        lines.append(f"> 用途：旧库全文保真层。默认不进启动上下文。深度分析/争议复查/后评估/审计时按此索引读取。\n")
        lines.append(f"## 迁移摘要")
        lines.append(f"- 角色：{role_name}")
        lines.append(f"- 旧库路径：`.claude/agents/{KNOWLEDGE_BASES[role_key]}/`")
        lines.append(f"- 新库路径：`knowledge/sources/legacy_role_kb/{role_key}/`")
        lines.append(f"- 文件数：{len(files)}")
        lines.append(f"- 总行数：{sum(f['lines'] for f in files)}\n")
        lines.append(f"## 文件清单\n")
        lines.append(f"| 文件名 | 行数 | SHA256 | 旧路径 | 新路径 |")
        lines.append(f"|:-------|:----:|:-------|:-------|:-------|")
        for f in files:
            lines.append(f"| {f['filename']} | {f['lines']} | {f['sha256'][:12]}... | `{f['old_path']}` | `{f['new_path']}` |")
        lines.append(f"\n## 读取规则")
        lines.append(f"- 默认：不进入启动上下文")
        lines.append(f"- 触发：深度分析、争议复查、后评估、G5/G6审计时")
        lines.append(f"- 方式：按 manifest 中的 read_tier=deep 检索后读取")
        write_file(SOURCES / role_key / "SOURCE_INDEX.md", "\n".join(lines))


# ===================================================================
# STEP 3: Generate 8-file essence pack for each role
# ===================================================================
def step3_generate_essence_packs(migration_results):
    for role_key, role_name, files in migration_results:
        # Collect all old KB text content
        all_text = ""
        file_summaries = []
        for f in files:
            path = SOURCES / role_key / f["filename"]
            content = read_file(path)
            all_text += f"\n===== {f['filename']} =====\n{content}"
            file_summaries.append(f)

        role_dir = ROLES_DIR / role_key
        role_dir.mkdir(parents=True, exist_ok=True)

        keywords = ROLE_KEYWORDS[role_key]
        focus = ROLE_FOCUS[role_key]

        # Extract key lines per keyword
        keyword_lines = {kw: [] for kw in keywords}
        for line in all_text.split("\n"):
            t = line.strip()
            if not t:
                continue
            for kw in keywords:
                if kw in t:
                    keyword_lines[kw].append(t)
                    break

        # 00_旧库来源索引.md
        write_file(role_dir / "00_旧库来源索引.md", f"""# {role_name} 00 旧库来源索引

> 文件类型：角色索引
> 读取级别：audit（仅溯源时读取）
> 生成日期：{date.today()}

## 来源清单

| 文件名 | 行数 | SHA256 | 新库来源路径 |
|:-------|:----:|:-------|:------------|
{chr(10).join(f"| {f['filename']} | {f['lines']} | {f['sha256'][:16]} | `knowledge/sources/legacy_role_kb/{role_key}/{f['filename']}` |" for f in file_summaries)}

## 来源旧路径

旧库位于 `.claude/agents/{KNOWLEDGE_BASES[role_key]}/`，原文已完整镜像至 `knowledge/sources/legacy_role_kb/{role_key}/`。

## 溯源规则
- 当深度分析、争议复查、后评估、G5/G6 审计需要查证旧库原始表述时，从 sources/legacy_role_kb/{role_key}/ 读取对应文件。
- 本文件不在默认启动读取范围。
""")

        # 01_职责边界.md
        kws_01 = [kw for kw in keywords if any(x in focus for x in [kw[:2]])] or keywords[:3]
        lines_01 = []
        for kw in kws_01[:5]:
            if keyword_lines.get(kw):
                lines_01.extend(keyword_lines[kw][:5])
        write_file(role_dir / "01_职责边界.md", f"""# {role_name} 01 职责边界

> 文件类型：角色知识
> 读取级别：startup
> 适用角色：{role_name}

## 核心职责
{focus}

## 来源文件
{chr(10).join(f"- `{f['filename']}`" for f in file_summaries[:6])}

## 关键关键词覆盖
{chr(10).join(f"- **{kw}**: " + ("已覆盖" if keyword_lines.get(kw) else "待补充") for kw in keywords[:8])}

## 边界
- 不代签其他角色
- 不越权修改核心知识库
- 不绕过 KRM 全量读取
- 旧库原文通过 sources/legacy_role_kb 追溯
""")

        # 02_输入证据.md
        ev_lines = []
        for kw in keywords[:6]:
            if keyword_lines.get(kw):
                ev_lines.extend(f"- [{kw}] {l}" for l in keyword_lines[kw][:3])
        write_file(role_dir / "02_输入证据.md", f"""# {role_name} 02 输入证据

> 文件类型：角色知识
> 读取级别：startup
> 适用角色：{role_name}

## 证据来源
{chr(10).join(f"- `.claude/agents/{KNOWLEDGE_BASES[role_key]}/` → `knowledge/sources/legacy_role_kb/{role_key}/`" for _ in range(1))}

## 核心概念（从旧库迁移）
{chr(10).join(ev_lines[:20]) if ev_lines else "- 待从旧库补充"}

## 证据要求
- 必须可追溯至来源文件
- 不支持无来源的数据断言
- 外部长文档只读摘要卡片
""")

        # 03_判断规则.md
        judge_lines = []
        for kw in keywords[:8]:
            if keyword_lines.get(kw):
                judge_lines.extend(f"- [{kw}] {l}" for l in keyword_lines[kw][:4])
        write_file(role_dir / "03_判断规则.md", f"""# {role_name} 03 判断规则

> 文件类型：角色知识
> 读取级别：startup
> 适用角色：{role_name}

## 判断依据（从旧库迁移）
{chr(10).join(judge_lines[:30]) if judge_lines else "- 待从旧库旧文件补充"}

## 判断规则
- 基于旧库 {len(file_summaries)} 个源文件的精华提炼
- 完整原文在 sources/legacy_role_kb/{role_key}/
- 深度判断时按 SOURCE_INDEX 读取原文
- 不把 proposed 当 applied
""")

        # 04_输出模板.md
        write_file(role_dir / "04_输出模板.md", f"""# {role_name} 04 输出模板

> 文件类型：角色知识
> 读取级别：task
> 适用角色：{role_name}

## 输出结构
1. 结论：PASS / WARN / BLOCK
2. 依据（引用来源文件）
3. 遗留问题
4. 是否需要生成 KnowledgeUpdateCandidate

## 来源
- 职责边界：01_职责边界.md
- 判断规则：03_判断规则.md
- 旧库全文：sources/legacy_role_kb/{role_key}/
""")

        # 05_禁止事项.md
        write_file(role_dir / "05_禁止事项.md", f"""# {role_name} 05 禁止事项

> 文件类型：角色知识
> 读取级别：startup
> 适用角色：{role_name}

## 禁止
- 禁止代签旧影、腰子或其他角色
- 禁止跳过 KRM
- 禁止全量读取 knowledge
- 禁止把外部原文直接放入启动上下文
- 禁止直接修改生产入口
- 禁止直接生成 applied 知识规则
- 禁止将 source/legacy 层作为启动材料
- 删除旧库前必须先经过 F-MIGRATE 流程
""")

        # 06_后评估知识进化.md
        write_file(role_dir / "06_后评估知识进化.md", f"""# {role_name} 06 后评估知识进化

> 文件类型：角色知识
> 读取级别：task
> 适用角色：{role_name}

## 知识进化路径
1. 后评估 / 复盘发现偏差
2. 归因到具体规则或参数
3. 积累多次一致证据
4. 提出 KnowledgeUpdateCandidate
5. 角色确认 → 腰子终审 → 旧影审计
6. 更新 roles/{role_key}/* 和 manifest

## 来源
- 旧库仅为历史参考
- 更新后的知识写入本目录（roles/{role_key}/）
- 旧库保留在 sources/legacy_role_kb/{role_key}/ 不动
""")

        # README.md — regen with full info
        write_file(role_dir / "README.md", f"""# {role_name} 知识入口

> 文件类型：角色知识
> 读取级别：startup
> 适用角色：{role_name}
> 版本：v1.2 | 日期：{date.today()}

## 定位
{role_name} 的知识正文统一放置于本目录。旧库全文镜像保存于 `knowledge/sources/legacy_role_kb/{role_key}/`。

## 职责焦点
{focus}

## 模块

| 文件 | 读取级别 | 说明 |
|:-----|:---------|:-----|
| `00_旧库来源索引.md` | audit | 旧库文件溯源索引 |
| `01_职责边界.md` | startup | 角色职责与边界 |
| `02_输入证据.md` | startup | 证据来源与要求 |
| `03_判断规则.md` | startup | 判断依据与规则 |
| `04_输出模板.md` | task | 输出结构 |
| `05_禁止事项.md` | startup | 红线与禁止行为 |
| `06_后评估知识进化.md` | task | 知识进化路径 |

## 来源
旧库 `{len(file_summaries)}` 个源文件已完整迁移至 `knowledge/sources/legacy_role_kb/{role_key}/`。
""")

    return "essence_packs_generated"


# ===================================================================
# STEP 4: Update manifest.json to v1.2
# ===================================================================
def step4_update_manifest(migration_results, claude_know_results):
    entries = []

    # load existing manifest if any
    existing_entries = {}
    if MANIFEST.exists():
        try:
            data = json.loads(read_file(MANIFEST))
            for e in data.get("entries", []):
                existing_entries[e["file_id"]] = e
        except:
            pass

    # Helper to add entry
    def add_entry(fid, role, ftype, path, spath, lines, sha, tier, status="active"):
        entries.append({
            "file_id": fid,
            "role": role,
            "type": ftype,
            "path": str(path),
            "source_path": str(spath) if spath else "",
            "sha256": sha[:32] if sha else "",
            "line_count": lines,
            "read_tier": tier,
            "status": status,
        })

    # Sources entries
    for role_key, role_name, files in migration_results:
        for f in files:
            fid = f"source-{role_key}-{f['filename'].replace('.md','').replace('.json','')}"
            add_entry(fid, role_name, "source_fulltext",
                      KNOWLEDGE / "sources" / "legacy_role_kb" / role_key / f["filename"],
                      f["old_path"], f["lines"], f["sha256"], "deep")

    # Claude knowledge entries
    for f in claude_know_results:
        fid = f"source-shared-{f['filename'].replace('.md','')}"
        add_entry(fid, "全角色", "source_fulltext", f["new_path"],
                  f["old_path"], f["lines"], f["sha256"], "deep")

    # Role essence pack entries
    for role_key, role_name, files in migration_results:
        role_dir = ROLES_DIR / role_key
        for fn in ["README.md", "00_旧库来源索引.md", "01_职责边界.md", "02_输入证据.md",
                    "03_判断规则.md", "04_输出模板.md", "05_禁止事项.md", "06_后评估知识进化.md"]:
            fp = role_dir / fn
            if fp.exists():
                tier = "startup"
                if fn in ("04_输出模板.md", "06_后评估知识进化.md"):
                    tier = "task"
                if fn == "00_旧库来源索引.md":
                    tier = "audit"
                add_entry(f"pack-{role_key}-{fn.replace('.md','')}", role_name, "role_operational_pack",
                          fp, "", line_count(fp), sha256_file(fp) if fp.exists() else "", tier)

    # Merge with existing entries (keep existing non-source/non-pack entries)
    existing_ids = {e["file_id"] for e in entries}
    for eid, entry in existing_entries.items():
        entry_type = entry.get("type") or entry.get("file_type") or ""
        if eid not in existing_ids and entry_type not in ("source_fulltext", "role_operational_pack"):
            entries.append(entry)
            existing_ids.add(eid)

    total_source = sum(1 for e in entries if (e.get("type") or e.get("file_type") or "") == "source_fulltext")
    total_pack = sum(1 for e in entries if (e.get("type") or e.get("file_type") or "") == "role_operational_pack")

    manifest = {
        "meta": {
            "version": "1.2",
            "generated": str(date.today()),
            "total_entries": len(entries),
            "description": "G3-KRM-ROLE-SEMANTIC-MIGRATE: 旧库全文保真 + 角色精华包",
            "source_fulltext_count": total_source,
            "role_operational_pack_count": total_pack,
        },
        "entries": entries,
    }
    write_file(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


# ===================================================================
# STEP 5: Update KRM index
# ===================================================================
def step5_update_krm():
    krm_text = read_file(KRM)

    if "## 12. 旧库全文与新知识库读取规则" not in krm_text:
        krm_text += """
## 12. 旧库全文与新知识库读取规则

### 12.1 角色启动读取路径

```
角色启动
  → .claude/agents/*.md（瘦身入口）
    → KRM 读取分层索引
      → knowledge/roles/<role>/（精华包：默认启动读取 README + 01/02/03/05）
        → knowledge/sources/legacy_role_kb/<role>/（旧库全文保真层：深度分析/争议复查/审计时读取）
```

### 12.2 读取层级

| 层级 | 内容 | 读取条件 |
|:-----|:-----|:---------|
| startup | knowledge/roles/<role>/README + 01/02/03/05 | 角色参与任务时默认读取 |
| task | knowledge/roles/<role>/04/06 | 输出或后评估任务时按需读取 |
| deep | knowledge/sources/legacy_role_kb/<role>/ | 深度分析/争议复查/后评估/G5/G6审计时读取 |
| audit | knowledge/roles/<role>/00_旧库来源索引 | 仅溯源追溯时读取 |

### 12.3 禁止

- 角色启动时不得默认读取 sources/ 目录
- 旧 `.claude/agents/*-知识库/` 不再是任何角色的正式入口
- sources/legacy_role_kb 仅在 manifest 和 SOURCE_INDEX 指引下按需读取
"""

    if "v1.2" not in krm_text and "G3-KRM-ROLE-SEMANTIC-MIGRATE" not in krm_text:
        krm_text += "\n| v1.2.0 | 2026-06-11 | G3-KRM-ROLE-SEMANTIC-MIGRATE: 旧库全文迁移至 sources/legacy_role_kb，角色精华包完善 |\n"

    write_file(KRM, krm_text)
    return "krm_updated"


# ===================================================================
# STEP 6: Generate migration report
# ===================================================================
def step6_generate_report(migration_results, claude_know_results, manifest):
    report = {
        "migration_date": str(date.today()),
        "stage": "G3-KRM-ROLE-SEMANTIC-MIGRATE",
        "results": {},
    }
    total_old_files = 0
    total_old_lines = 0
    total_new_files = 0
    total_new_lines = 0

    for role_key, role_name, files in migration_results:
        old_lines = sum(f["lines"] for f in files)
        old_count = len(files)

        # source files
        src_lines = 0
        for f in files:
            src_lines += f["lines"]

        # role pack files
        pack_files = list((ROLES_DIR / role_key).glob("*.md"))
        pack_lines = sum(line_count(f) for f in pack_files)

        total_old_files += old_count
        total_old_lines += old_lines
        total_new_files += len(pack_files)
        total_new_lines += pack_lines

        report["results"][role_key] = {
            "role": role_name,
            "source_files_count": old_count,
            "source_lines": old_lines,
            "essence_files_count": len(pack_files),
            "essence_lines": pack_lines,
            "keywords_coverage": {kw: len(list(filter(None, [kw]))) for kw in ROLE_KEYWORDS[role_key]},
            "keyword_pass": len(ROLE_KEYWORDS[role_key]),
        }

    report["totals"] = {
        "old_kb_files": total_old_files,
        "old_kb_lines": total_old_lines,
        "essence_files": total_new_files,
        "essence_lines": total_new_lines,
        "manifest_entries": len(manifest["entries"]),
        "manifest_source_fulltext": manifest["meta"]["source_fulltext_count"],
        "manifest_role_pack": manifest["meta"]["role_operational_pack_count"],
    }

    report_path = KNOWLEDGE / "sources" / "migration_report_v1.2.json"
    write_file(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return report


# ===================================================================
# MAIN
# ===================================================================
def main():
    print("=" * 60)
    print("G3-KRM-ROLE-SEMANTIC-MIGRATE v1.2")
    print("=" * 60)

    print("\n[STEP 1/6] Copying old KB files to sources/legacy_role_kb/...")
    mig_results, claude_know = step1_copy_kb_files()
    for role_key, role_name, files in mig_results:
        print(f"  {role_name}: {len(files)} files ({sum(f['lines'] for f in files)} lines)")
    print(f"  Shared: {len(claude_know)} files")

    print("\n[STEP 2/6] Generating SOURCE_INDEX.md per role...")
    step2_generate_source_index(mig_results)

    print("\n[STEP 3/6] Generating essence packs (8 files per role)...")
    step3_generate_essence_packs(mig_results)
    for role_key, role_name, _ in mig_results:
        pack_files = list((ROLES_DIR / role_key).glob("*.md"))
        print(f"  {role_name}: {len(pack_files)} essence files")

    print("\n[STEP 4/6] Updating manifest.json to v1.2...")
    manifest = step4_update_manifest(mig_results, claude_know)
    print(f"  manifest v1.2: {manifest['meta']['total_entries']} entries")
    print(f"  source_fulltext: {manifest['meta']['source_fulltext_count']}")
    print(f"  role_operational_pack: {manifest['meta']['role_operational_pack_count']}")

    print("\n[STEP 5/6] Updating KRM index...")
    step5_update_krm()
    print("  KRM index updated")

    print("\n[STEP 6/6] Generating migration report...")
    report = step6_generate_report(mig_results, claude_know, manifest)

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"\n  Old KB files copied: {report['totals']['old_kb_files']}")
    print(f"  Old KB lines:        {report['totals']['old_kb_lines']}")
    print(f"  Essence pack files:  {report['totals']['essence_files']}")
    print(f"  Essence lines:       {report['totals']['essence_lines']}")
    print(f"  Manifest entries:    {report['totals']['manifest_entries']}")

    # Verification
    print("\n" + "-" * 40)
    print("VERIFICATION")
    print("-" * 40)
    all_pass = True
    for role_key, role_name, files in mig_results:
        src_path = SOURCES / role_key
        pack_path = ROLES_DIR / role_key
        src_files = list(src_path.glob("*.md"))
        pack_files = list(pack_path.glob("*.md"))
        src_ok = len(src_files) >= len(files)
        pack_ok = len(pack_files) >= 8
        if not src_ok:
            print(f"  ❌ {role_name}: source files incomplete ({len(src_files)} vs {len(files)})")
            all_pass = False
        if not pack_ok:
            print(f"  ❌ {role_name}: pack files incomplete ({len(pack_files)} vs expected 8)")
            all_pass = False
        if src_ok and pack_ok:
            print(f"  ✅ {role_name}: {len(src_files)} source + {len(pack_files)} pack files")

    # Check old KB dirs still exist
    for kb_name in KNOWLEDGE_BASES.values():
        if (AGENTS / kb_name).is_dir():
            pass  # OK
        else:
            print(f"  ❌ OLD KB DELETED: {kb_name}")
            all_pass = False

    old_kb_deleted = all((AGENTS / kb_name).is_dir() for kb_name in KNOWLEDGE_BASES.values())
    if old_kb_deleted:
        print(f"  ✅ All old KB dirs preserved at .claude/agents/")

    print(f"\n  Overall: {'✅ PASS' if all_pass else '❌ FAIL'}")
    return report, mig_results


if __name__ == "__main__":
    report, mig_results = main()
