#!/usr/bin/env python3
"""
外部文献知识库治理工具 — knowledge_guard.py

职责：字段检查、状态机校验、索引生成、过期复审提醒、越级拦截。
禁止：阅读文献、总结文献、解释金融含义、替角色判断、替腰子统一口径、自动升级规则。

用法：
    python3 tools/knowledge_guard.py lint
    python3 tools/knowledge_guard.py index
    python3 tools/knowledge_guard.py check CARD-YYYYMMDD-001
    python3 tools/knowledge_guard.py transition CARD-YYYYMMDD-001 --to ACTIVE
    python3 tools/knowledge_guard.py due

支持 --base-dir PATH 参数，用于测试自定义目录结构。
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 默认路径 ──────────────────────────────────────────────────────
DEFAULT_BASE = Path(__file__).resolve().parent.parent / "knowledge" / "external_literature"


# ── 根据 base_dir 生成子路径的函数 ────────────────────────────────

def _make_paths(base_dir: Path):
    """根据 base_dir 生成所有子目录路径字典。"""
    return {
        "raw": base_dir / "raw",
        "cards": base_dir / "cards",
        "role_summaries": base_dir / "role_summaries",
        "validations": base_dir / "validations",
        "candidates": base_dir / "candidates",
        "param": base_dir / "candidates" / "parameters",
        "counterexamples": base_dir / "candidates" / "counterexamples",
        "core": base_dir / "candidates" / "core_knowledge",
        "active": base_dir / "active",
        "active_param": base_dir / "active" / "parameters",
        "active_counterexamples": base_dir / "active" / "counterexamples",
        "active_knowledge": base_dir / "active" / "role_knowledge",
        "deprecated": base_dir / "deprecated",
        "indexes": base_dir / "indexes",
    }


# ── 常量 ──────────────────────────────────────────────────────────
VALID_ROLES = [
    "山猫", "信鸽", "青山", "流金", "玉夜",
    "腰子", "阿黑", "旧影", "情墨", "新安", "红结", "红枫", "千光",
]

VALID_STATUSES = [
    "RAW_RECEIVED", "ROUTED", "CARD_DRAFTED", "FINANCE_ALIGNED",
    "REFERENCE_ONLY", "VALIDATION_PENDING", "PARAM_CANDIDATE",
    "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE", "ACTIVE", "DEPRECATED",
]

ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    "RAW_RECEIVED": ["ROUTED"],
    "ROUTED": ["CARD_DRAFTED"],
    "CARD_DRAFTED": ["FINANCE_ALIGNED"],
    "FINANCE_ALIGNED": ["REFERENCE_ONLY"],
    "REFERENCE_ONLY": ["VALIDATION_PENDING"],
    "VALIDATION_PENDING": ["PARAM_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE"],
    "PARAM_CANDIDATE": ["ACTIVE"],
    "COUNTEREXAMPLE_CANDIDATE": ["ACTIVE"],
    "CORE_CANDIDATE": ["ACTIVE"],
    "ACTIVE": ["DEPRECATED"],
    "DEPRECATED": [],
}

FORBIDDEN_TRANSITIONS: List[Tuple[str, str]] = [
    ("RAW_RECEIVED", "ACTIVE"),
    ("CARD_DRAFTED", "ACTIVE"),
    ("REFERENCE_ONLY", "ACTIVE"),
    ("CARD_DRAFTED", "CORE_CANDIDATE"),
]

# 卡片必填字段（卡片/候选/ACTIVE 文件适用）
REQUIRED_FIELDS_CARD = [
    "doc_type", "source_id", "card_id", "title", "source",
    "publish_date", "version", "url_or_path", "material_type",
    "primary_role", "reading_scope", "status", "evidence_level",
    "review_date", "finance_owner", "finance_aligned",
    "validated", "confirmed_roles", "created_date", "updated_date",
]

# raw 文件只要求的最小字段
RAW_REQUIRED_FIELDS = [
    "doc_type", "source_id", "title", "source",
    "publish_date", "version", "url_or_path", "status",
]

# raw 文件不得被强制检查的字段（卡片专有）
RAW_EXEMPT_FIELDS = {
    "card_id", "material_type", "primary_role", "support_roles",
    "reading_scope", "evidence_level", "review_date",
    "finance_owner", "finance_aligned", "validated",
    "confirmed_roles", "created_date", "updated_date",
}

REQUIRED_SECTIONS = [
    "核心结论", "适用范围", "适用条件", "不适用条件",
    "对哪些角色有参考价值", "可能转化方向",
    "风险提示", "复审要求",
]

TODAY = date.today()


# ── 工具函数 ──────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """从 Markdown content 中解析 YAML frontmatter 和正文。"""
    text = content
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1].strip()
            body = parts[2].strip()
            return _parse_yaml_simple(raw_yaml), body
    return None, text


def _parse_yaml_simple(raw_yaml: str) -> Dict[str, Any]:
    """简易 YAML 解析器（仅处理 frontmatter 常用格式）。"""
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for line in raw_yaml.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\w[\w_-]*)\s*:\s*(.*?)$', line)
        if m:
            current_key = m.group(1)
            raw_val = m.group(2).strip()
            if raw_val == "" or raw_val == "''" or raw_val == '""':
                result[current_key] = ""
            elif raw_val.startswith("[") and raw_val.endswith("]"):
                items = raw_val[1:-1].split(",")
                result[current_key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            elif raw_val == "true":
                result[current_key] = True
            elif raw_val == "false":
                result[current_key] = False
            else:
                result[current_key] = raw_val.strip('"').strip("'")
        elif current_key:
            if isinstance(result.get(current_key), list):
                val = line.strip("- ").strip('"').strip("'")
                if val:
                    result[current_key].append(val)
            elif isinstance(result.get(current_key), str) and result[current_key]:
                result[current_key] += " " + line
    return result


def _yaml_value(val: Any) -> str:
    """将 Python 值转为 YAML 值字符串，用于诊断输出。"""
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, list):
        items = ", ".join(repr(v) for v in val)
        return f"[{items}]"
    return str(val)


def _is_raw_file(filepath: Path, base_dir: Path) -> bool:
    """判断文件是否属于 raw 目录。"""
    return "raw" in filepath.parts


def collect_markdown_files(directory: Path, recursive: bool = True) -> List[Path]:
    """收集目录中所有 .md 文件（不含 README.md）。"""
    if not directory.exists():
        return []
    pattern = "**/*.md" if recursive else "*.md"
    files = []
    for f in sorted(directory.glob(pattern)):
        if f.name == "README.md":
            continue
        if "role_summaries" in f.parts:
            continue
        files.append(f)
    return files


def get_card_file(card_id: str, base_dir: Path) -> Optional[Path]:
    """根据 card_id 查找卡片文件（基于 base_dir）。"""
    paths = _make_paths(base_dir)
    search_dirs = [
        paths["cards"],
        paths["active_param"], paths["active_counterexamples"], paths["active_knowledge"],
        paths["param"], paths["counterexamples"], paths["core"],
        paths["deprecated"],
    ]
    for d in search_dirs:
        f = d / f"{card_id}.md"
        if f.exists():
            return f
    return None


def get_validation_files_for_card(card_id: str, base_dir: Path) -> List[Path]:
    """查找与卡片关联的验证文件。"""
    paths = _make_paths(base_dir)
    files = []
    if paths["validations"].exists():
        for f in paths["validations"].glob("VAL-*.md"):
            front, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            if front and front.get("card_id") == card_id:
                files.append(f)
    return files


def check_sections(body: str, required: List[str]) -> List[str]:
    """检查正文是否包含必要章节。"""
    missing = []
    for section in required:
        if section not in body:
            missing.append(section)
    return missing


def is_expired(valid_until: str) -> bool:
    """检查有效期是否已过。"""
    if not valid_until:
        return True
    try:
        d = datetime.strptime(str(valid_until), "%Y-%m-%d").date()
        return d < TODAY
    except (ValueError, TypeError):
        return True


def is_due_for_review(review_date: str) -> bool:
    """检查是否已到复审日期。"""
    if not review_date:
        return True
    try:
        d = datetime.strptime(str(review_date), "%Y-%m-%d").date()
        return d <= TODAY
    except (ValueError, TypeError):
        return True


# ── 检查规则 ──────────────────────────────────────────────────────

class LintResult:
    def __init__(self):
        self.violations: List[Dict[str, Any]] = []
        self.checked_count = 0

    def add(self, file: str, severity: str, rule: str, message: str):
        self.violations.append({
            "file": str(file),
            "severity": severity,
            "rule": rule,
            "message": message,
        })

    def to_dict(self) -> Dict:
        errors = [v for v in self.violations if v["severity"] == "ERROR"]
        warnings = [v for v in self.violations if v["severity"] == "WARN"]
        return {
            "scan_date": TODAY.isoformat(),
            "checked_files": self.checked_count,
            "total_violations": len(self.violations),
            "errors": len(errors),
            "warnings": len(warnings),
            "violations": self.violations,
        }


def lint_file(filepath: Path, result: LintResult, base_dir: Path):
    """对单个文件执行 lint 检查。

    raw 目录下的文件（doc_type=source）只检查最小字段集，
    不强制要求卡片专有字段。
    """
    result.checked_count += 1
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        result.add(str(filepath), "ERROR", "L-READ", f"文件读取失败: {e}")
        return

    front, body = parse_frontmatter(content)
    if front is None:
        result.add(str(filepath), "ERROR", "L-FRONT", "无 YAML frontmatter")
        return

    rel_path = str(filepath.relative_to(base_dir.parent.parent))

    is_raw = _is_raw_file(filepath, base_dir)
    doc_type = front.get("doc_type", "")

    # ── raw 文件（doc_type=source）─ 只检查最小字段集 ──
    if is_raw or doc_type == "source":
        for field in RAW_REQUIRED_FIELDS:
            if not front.get(field):
                result.add(rel_path, "ERROR", "L-RAW", f"raw 文件缺少必填字段 '{field}'")

        # raw 文件的 status 必须是 RAW_RECEIVED
        raw_status = front.get("status", "")
        if raw_status and raw_status != "RAW_RECEIVED":
            result.add(rel_path, "WARN", "L-RAW-STATUS", f"raw 文件 status 应为 RAW_RECEIVED，实际为 '{raw_status}'")

        # raw 文件不检查卡片专有字段 — 直接返回
        return

    # ── 非 raw 文件：完整检查 ──

    # R1: doc_type
    if not doc_type:
        result.add(rel_path, "ERROR", "L-R01", "doc_type 缺失")

    # R2: source_id/card_id
    if not front.get("source_id"):
        result.add(rel_path, "ERROR", "L-R02a", "source_id 缺失")
    if not front.get("card_id"):
        result.add(rel_path, "WARN", "L-R02b", "card_id 缺失")

    # R3: 基本信息
    for field in ["title", "source", "publish_date", "version", "url_or_path"]:
        if not front.get(field):
            result.add(rel_path, "ERROR", "L-R03", f"{field} 缺失")

    # R4: material_type
    if not front.get("material_type") and "cards" in filepath.parts:
        result.add(rel_path, "ERROR", "L-R04", "material_type 缺失（卡片文件）")

    # R5: primary_role
    primary = front.get("primary_role", "")
    if not primary:
        result.add(rel_path, "ERROR", "L-R05a", "primary_role 缺失")
    elif primary not in VALID_ROLES:
        result.add(rel_path, "ERROR", "L-R05b", f"primary_role '{primary}' 不在合法角色列表中")

    # R6: support_roles
    support_roles = front.get("support_roles", [])
    if isinstance(support_roles, str):
        support_roles = [support_roles]
    for r in support_roles:
        if r not in VALID_ROLES:
            result.add(rel_path, "ERROR", "L-R06", f"support_role '{r}' 不在合法角色列表中")

    # R7: reading_scope
    front_reading_scope = front.get("reading_scope", "")
    if not front_reading_scope and "cards" in filepath.parts:
        result.add(rel_path, "WARN", "L-R07", "reading_scope 缺失（卡片文件建议填写）")

    # R8: status
    status = front.get("status", "")
    if not status:
        result.add(rel_path, "ERROR", "L-R08a", "status 缺失")
    elif status not in VALID_STATUSES:
        result.add(rel_path, "ERROR", "L-R08b", f"status '{status}' 不是合法状态")
    elif status == "ACTIVE":
        missing_sections = check_sections(body, REQUIRED_SECTIONS)
        for sec in ["适用范围", "适用条件", "不适用条件"]:
            if sec in missing_sections:
                result.add(rel_path, "ERROR", "L-R15", f"ACTIVE 缺少正文章节 '{sec}'（适用条件/不适用条件必须记载）")
        vu = front.get("valid_until", "")
        if not vu:
            result.add(rel_path, "ERROR", "L-R16a", "ACTIVE 缺少 valid_until")
        elif is_expired(vu):
            result.add(rel_path, "ERROR", "L-R17", f"ACTIVE 已过期 (valid_until={vu})")
        confirmed = front.get("confirmed_roles", [])
        if isinstance(confirmed, str):
            confirmed = [confirmed] if confirmed else []
        if not confirmed:
            result.add(rel_path, "ERROR", "L-R14", "ACTIVE 缺少 confirmed_roles（角色确认）")

    # R9: evidence_level
    if not front.get("evidence_level") and "cards" in filepath.parts:
        result.add(rel_path, "WARN", "L-R09", "evidence_level 缺失（卡片文件）")

    # R10: review_date
    rd = front.get("review_date", "")
    if not rd:
        result.add(rel_path, "WARN", "L-R10", "review_date 缺失")

    # R11: finance_owner
    fo = front.get("finance_owner", "")
    if fo and fo != "腰子":
        result.add(rel_path, "ERROR", "L-R11", f"finance_owner 应为'腰子'，实际为'{fo}'")

    # R12: finance_aligned
    fa = front.get("finance_aligned", False)
    if status in ["PARAM_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE", "ACTIVE"]:
        if fa is not True:
            result.add(rel_path, "ERROR", "L-R12",
                       f"状态 {status} 需要 finance_aligned=true，当前为 {_yaml_value(fa)}")

    # R13: validated
    validated = front.get("validated", False)
    if status in ["PARAM_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE", "ACTIVE"]:
        if validated is not True:
            result.add(rel_path, "ERROR", "L-R13",
                       f"状态 {status} 需要 validated=true，当前为 {_yaml_value(validated)}")

    # 正文检查（卡片文件）
    if "cards" in filepath.parts:
        missing_sections = check_sections(body, REQUIRED_SECTIONS)
        for sec in missing_sections:
            result.add(rel_path, "WARN", "L-BODY", f"卡片正文缺少章节 '{sec}'")

    # review_date 过期
    if rd:
        if is_due_for_review(rd):
            result.add(rel_path, "WARN", "L-REVIEW", f"超过复审日期 (review_date={rd})")


def check_transition_allowed(current_status: str, target_status: str) -> Tuple[bool, str]:
    """检查状态流转是否允许。"""
    for (frm, to) in FORBIDDEN_TRANSITIONS:
        if current_status == frm and target_status == to:
            return False, f"禁止流转：{frm} → {to}（越级）"
    allowed = ALLOWED_TRANSITIONS.get(current_status, [])
    if target_status in allowed:
        return True, ""
    if allowed:
        return False, f"未定义流转：{current_status} → {target_status}（允许的下一状态：{', '.join(allowed)}）"
    else:
        return False, f"未定义流转：{current_status} → {target_status}（{current_status} 无下一状态）"


def check_transition_prerequisites(filepath: Path, front: Dict, body: str, target: str, base_dir: Path) -> List[str]:
    """检查流转前置条件。"""
    blockers = []
    status = front.get("status", "")

    # 候选层
    if target in ["PARAM_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE"]:
        if front.get("finance_aligned") is not True:
            blockers.append("finance_aligned != true（未经腰子统一口径）")
        if front.get("validated") is not True:
            blockers.append("validated != true（未经项目验证）")
        if status != "VALIDATION_PENDING":
            blockers.append(f"当前状态为 {status}，需要 VALIDATION_PENDING")
        card_id = front.get("card_id", "")
        if card_id:
            vfiles = get_validation_files_for_card(card_id, base_dir)
            if not vfiles:
                blockers.append(f"未找到对应的验证文件（需 VAL-{card_id}）")

    # ACTIVE
    if target == "ACTIVE":
        if front.get("finance_aligned") is not True:
            blockers.append("finance_aligned != true（未经腰子统一口径）")
        if front.get("validated") is not True:
            blockers.append("validated != true（未经项目验证）")
        confirmed = front.get("confirmed_roles", [])
        if isinstance(confirmed, str):
            confirmed = [confirmed] if confirmed else []
        if not confirmed:
            blockers.append("confirmed_roles 为空（未经角色确认）")
        if not front.get("valid_until"):
            blockers.append("valid_until 缺失")
        elif is_expired(str(front.get("valid_until", ""))):
            blockers.append(f"valid_until ({front.get('valid_until')}) 已过期")
        if not front.get("review_date"):
            blockers.append("review_date 缺失")
        missing_secs = check_sections(body, ["适用范围", "适用条件", "不适用条件"])
        for sec in missing_secs:
            blockers.append(f"正文缺少章节 '{sec}'（ACTIVE 必须记载）")

    # DEPRECATED
    if target == "DEPRECATED":
        if status != "ACTIVE":
            blockers.append(f"只有 ACTIVE 可进入 DEPRECATED，当前为 {status}")

    return blockers


# ── 获取扫描目录 ──────────────────────────────────────────────────

def _get_scan_dirs(base_dir: Path) -> Tuple[Dict[str, Path], List[Path], List[Path]]:
    """返回 (路径字典, 非active扫描目录列表, active扫描目录列表)。"""
    paths = _make_paths(base_dir)

    # active 目录 — 唯一允许产生 active_index 的入口
    active_dirs = [
        paths["active_param"],
        paths["active_counterexamples"],
        paths["active_knowledge"],
    ]

    # 非 active 目录
    non_active_dirs = [
        paths["cards"],
        paths["param"],
        paths["counterexamples"],
        paths["core"],
        paths["deprecated"],
    ]

    return paths, non_active_dirs, active_dirs


# ── LINT 命令 ─────────────────────────────────────────────────────

def cmd_lint(args, base_dir: Path):
    """执行 lint 检查，输出 violations.json。"""
    result = LintResult()
    paths, non_active_dirs, active_dirs = _get_scan_dirs(base_dir)

    all_dirs = [
        paths["raw"],
        paths["cards"],
        paths["validations"],
        paths["param"],
        paths["counterexamples"],
        paths["core"],
        paths["active_param"],
        paths["active_counterexamples"],
        paths["active_knowledge"],
        paths["deprecated"],
    ]
    for d in all_dirs:
        for f in collect_markdown_files(d):
            lint_file(f, result, base_dir)

    out_dir = paths["indexes"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "violations.json"
    out_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[LINT] 检查文件 {result.checked_count} 个")
    print(f"[LINT] 违规总计 {len(result.violations)} 个")
    errs = [v for v in result.violations if v["severity"] == "ERROR"]
    warns = [v for v in result.violations if v["severity"] == "WARN"]
    print(f"[LINT] ERROR: {len(errs)} 个")
    print(f"[LINT] WARN: {len(warns)} 个")
    if errs:
        print(f"[LINT] 首次 ERROR 示例: {errs[0]['file']} — {errs[0]['message']}")
    print(f"[LINT] 输出: {out_path}")

    return 1 if errs else 0


# ── INDEX 命令 ────────────────────────────────────────────────────

def cmd_index(args, base_dir: Path):
    """生成全部索引文件。

    active_index.json 只从 active/ 子目录扫描，且强制复用 ACTIVE 前置条件校验。
    非 active 目录中出现 status=ACTIVE 的文件被拦截为 IDX-ACTIVE-PATH 违规。
    """
    paths, non_active_dirs, active_dirs = _get_scan_dirs(base_dir)
    results = LintResult()

    sources = []
    cards = []
    active_entries = []
    pending_review = []
    expired = []

    # 1. 扫描 raw
    for f in collect_markdown_files(paths["raw"]):
        content = f.read_text(encoding="utf-8")
        front, _ = parse_frontmatter(content)
        if front:
            sources.append({
                "file": str(f.relative_to(base_dir)),
                "source_id": front.get("source_id", ""),
                "title": front.get("title", ""),
                "source": front.get("source", ""),
                "publish_date": front.get("publish_date", ""),
                "version": front.get("version", ""),
                "url_or_path": front.get("url_or_path", ""),
            })

    # 2. 扫描非 active 目录（cards/candidates/deprecated）
    for d in non_active_dirs:
        if not d.exists():
            continue
        for f in collect_markdown_files(d):
            front, body = parse_frontmatter(f.read_text(encoding="utf-8"))
            if not front:
                continue
            status = front.get("status", "")

            # IDX-ACTIVE-PATH: 非 active 目录中出现 ACTIVE → 拦截
            if status == "ACTIVE":
                rel_path = str(f.relative_to(base_dir.parent.parent))
                v_msg = f"ACTIVE 文件位于非 active 目录，禁止进入 active_index: {rel_path}"
                results.add(rel_path, "ERROR", "IDX-ACTIVE-PATH", v_msg)
                pending_review.append({
                    "file": rel_path,
                    "card_id": front.get("card_id", ""),
                    "title": front.get("title", ""),
                    "status": status,
                    "reason": v_msg,
                })
                continue  # 不进入 cards_index 也不进入 active_index

            # 正常非 ACTIVE → 进入 cards_index
            entry = _make_entry(f, front, base_dir)
            cards.append(entry)
            _add_pending_checks(entry, front, pending_review)

    # 3. 扫描 active 目录 — 唯一允许进入 active_index 的入口
    for d in active_dirs:
        if not d.exists():
            continue
        for f in collect_markdown_files(d):
            front, body = parse_frontmatter(f.read_text(encoding="utf-8"))
            if not front:
                continue
            status = front.get("status", "")
            rel_path = str(f.relative_to(base_dir.parent.parent))

            if status != "ACTIVE":
                # IDX-ACTIVE-STATUS: active 目录中文件状态不是 ACTIVE
                v_msg = f"active 目录中文件状态不是 ACTIVE: {rel_path} (status={status})"
                results.add(rel_path, "WARN", "IDX-ACTIVE-STATUS", v_msg)
                pending_review.append({
                    "file": rel_path,
                    "card_id": front.get("card_id", ""),
                    "title": front.get("title", ""),
                    "status": status,
                    "reason": v_msg,
                })
                cards.append(_make_entry(f, front, base_dir))
                continue

            # status == ACTIVE: 强制复用 ACTIVE 前置条件校验
            blockers = check_transition_prerequisites(f, front, body, "ACTIVE", base_dir)
            if blockers:
                v_msg = f"ACTIVE 前置条件不满足: {'; '.join(blockers)}"
                results.add(rel_path, "ERROR", "IDX-ACTIVE-PREREQ", v_msg)
                pending_review.append({
                    "file": rel_path,
                    "card_id": front.get("card_id", ""),
                    "title": front.get("title", ""),
                    "status": status,
                    "reason": v_msg,
                })
                continue

            # 额外确保核心字段
            extra_blockers = []
            if front.get("finance_aligned") is not True:
                extra_blockers.append("finance_aligned != true")
            if front.get("validated") is not True:
                extra_blockers.append("validated != true")
            confirmed = front.get("confirmed_roles", [])
            if isinstance(confirmed, str):
                confirmed = [confirmed] if confirmed else []
            if not confirmed:
                extra_blockers.append("confirmed_roles 为空")
            if not front.get("valid_until") or is_expired(str(front.get("valid_until", ""))):
                extra_blockers.append("valid_until 不存在或已过期")
            if not front.get("review_date"):
                extra_blockers.append("review_date 缺失")
            missing_secs = check_sections(body, ["适用范围", "适用条件", "不适用条件"])
            for sec in missing_secs:
                extra_blockers.append(f"正文缺少 '{sec}'")
            if extra_blockers:
                v_msg = "ACTIVE 前置条件不满足: " + "; ".join(extra_blockers)
                results.add(rel_path, "ERROR", "IDX-ACTIVE-PREREQ", v_msg)
                pending_review.append({
                    "file": rel_path,
                    "card_id": front.get("card_id", ""),
                    "title": front.get("title", ""),
                    "status": status,
                    "reason": v_msg,
                })
                continue

            # 全部通过后检查过期
            valid_until = str(front.get("valid_until", ""))
            if not is_expired(valid_until):
                active_entries.append(_make_entry(f, front, base_dir))
            else:
                entry = _make_entry(f, front, base_dir)
                expired.append(entry)
                pending_review.append({
                    **entry,
                    "reason": f"ACTIVE 已过期 (valid_until={valid_until})",
                })

    # 写入索引
    write_json(paths["indexes"] / "sources_index.json", {
        "generated_at": TODAY.isoformat(),
        "total": len(sources),
        "sources": sources,
        "warning": "此索引中的内容不得直接加载到角色启动上下文",
    })

    write_json(paths["indexes"] / "cards_index.json", {
        "generated_at": TODAY.isoformat(),
        "total": len(cards),
        "cards": cards,
        "warning": "此索引中的内容不得直接加载到角色启动上下文",
    })

    write_json(paths["indexes"] / "active_index.json", {
        "generated_at": TODAY.isoformat(),
        "total": len(active_entries),
        "note": "此索引是角色启动上下文唯一允许读取的知识入口",
        "active_knowledge": active_entries,
        "rules": [
            "角色启动上下文只读此索引指向的内容",
            "不得加载 raw/cards/candidates/deprecated 内容",
        ],
    })

    write_json(paths["indexes"] / "pending_review.json", {
        "generated_at": TODAY.isoformat(),
        "total": len(pending_review),
        "pending_items": pending_review,
    })

    write_json(paths["indexes"] / "expired_index.json", {
        "generated_at": TODAY.isoformat(),
        "total": len(expired),
        "expired_items": expired,
    })

    # 写入 violations（追加 index 阶段的违规）
    if results.violations:
        v_path = paths["indexes"] / "violations.json"
        if v_path.exists():
            try:
                existing = json.loads(v_path.read_text(encoding="utf-8"))
                existing["violations"].extend(results.violations)
                existing["total_violations"] = len(existing["violations"])
                existing["errors"] = len([v for v in existing["violations"] if v["severity"] == "ERROR"])
                existing["warnings"] = len([v for v in existing["violations"] if v["severity"] == "WARN"])
                write_json(v_path, existing)
            except (json.JSONDecodeError, Exception):
                write_json(v_path, results.to_dict())
        else:
            write_json(v_path, results.to_dict())

    print(f"[INDEX] sources_index.json: {len(sources)} 条")
    print(f"[INDEX] cards_index.json: {len(cards)} 条")
    print(f"[INDEX] active_index.json: {len(active_entries)} 条")
    print(f"[INDEX] pending_review.json: {len(pending_review)} 条")
    print(f"[INDEX] expired_index.json: {len(expired)} 条")

    if results.violations:
        for v in results.violations:
            print(f"[INDEX] {v['severity']} {v['rule']}: {v['message']}")
        return 1
    return 0


def _make_entry(f: Path, front: Dict, base_dir: Path) -> Dict:
    """从 frontmatter 构建标准条目。"""
    return {
        "file": str(f.relative_to(base_dir)),
        "card_id": front.get("card_id", ""),
        "source_id": front.get("source_id", ""),
        "title": front.get("title", ""),
        "status": front.get("status", ""),
        "primary_role": front.get("primary_role", ""),
        "finance_aligned": front.get("finance_aligned", False),
        "validated": front.get("validated", False),
        "confirmed_roles": front.get("confirmed_roles", []),
        "valid_until": front.get("valid_until", ""),
        "review_date": front.get("review_date", ""),
        "material_type": front.get("material_type", ""),
        "evidence_level": front.get("evidence_level", ""),
    }


def _add_pending_checks(entry: Dict, front: Dict, pending_review: List):
    """向 pending_review 添加待办项（辅助函数）。"""
    card_id = front.get("card_id", "")
    status = front.get("status", "")
    finance_aligned = front.get("finance_aligned", False)
    validated = front.get("validated", False)
    confirmed_roles = front.get("confirmed_roles", [])
    review_date = front.get("review_date", "")
    valid_until = front.get("valid_until", "")

    # 复审到期
    if review_date and is_due_for_review(review_date):
        _add_pending_unique(pending_review, entry, f"已达复审日期 (review_date={review_date})")

    # 待验证
    if status == "VALIDATION_PENDING" and not validated:
        _add_pending_unique(pending_review, entry, "待验证 (VALIDATION_PENDING 但 validated=false)")

    # 待确认
    if status in ["PARAM_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE"]:
        confirmed = confirmed_roles if isinstance(confirmed_roles, list) else []
        if not confirmed:
            _add_pending_unique(pending_review, entry, "待角色确认 (confirmed_roles 为空)")

    # 待腰子
    if status in ["PARAM_CANDIDATE", "COUNTEREXAMPLE_CANDIDATE", "CORE_CANDIDATE", "ACTIVE"]:
        if not finance_aligned:
            _add_pending_unique(pending_review, entry, "待腰子统一口径 (finance_aligned=false)")

    # 过期
    if valid_until and is_expired(valid_until):
        _add_pending_unique(pending_review, entry, f"已过期 (valid_until={valid_until})")


def _add_pending_unique(pending_review: List, entry: Dict, reason: str):
    """去重添加 pending 项。"""
    card_id = entry.get("card_id", "")
    for p in pending_review:
        if p.get("card_id") == card_id and reason in str(p.get("reason", "")):
            return
    pending_review.append({**entry, "reason": reason})


def write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── CHECK 命令 ────────────────────────────────────────────────────

def cmd_check(args, base_dir: Path):
    """检查单张卡片状态。"""
    card_id = args.card_id
    paths = _make_paths(base_dir)
    filepath = get_card_file(card_id, base_dir)
    if not filepath:
        print(f"[CHECK] 未找到卡片: {card_id}")
        return 1

    content = filepath.read_text(encoding="utf-8")
    front, body = parse_frontmatter(content)
    if not front:
        print(f"[CHECK] {card_id} 无法解析 frontmatter")
        return 1

    status = front.get("status", "")
    print(f"╔══ {card_id} ═══")
    print(f"║ 文件: {filepath.relative_to(base_dir.parent.parent)}")
    print(f"║ 当前状态: {status}")
    print(f"║ 主责角色: {front.get('primary_role', '(未指定)')}")
    print(f"║ 腰子口径: {_yaml_value(front.get('finance_aligned', False))}")
    print(f"║ 验证状态: {_yaml_value(front.get('validated', False))}")
    print(f"║ 角色确认: {front.get('confirmed_roles', [])}")
    print(f"║ 有效期至: {front.get('valid_until', '(未设置)')}")
    print(f"║ 复审日期: {front.get('review_date', '(未设置)')}")
    print(f"╚══")

    # 缺失字段（跳过 raw 文件的卡片字段）
    is_raw = _is_raw_file(filepath, base_dir)
    missing_fields = []
    for field in REQUIRED_FIELDS_CARD:
        val = front.get(field)
        if val is None or val == "" or (isinstance(val, list) and not val):
            if field == "card_id" and is_raw:
                continue
            missing_fields.append(field)
    if missing_fields:
        print(f"[CHECK] 缺失字段: {', '.join(missing_fields)}")

    if body:
        missing_secs = check_sections(body, REQUIRED_SECTIONS)
        if missing_secs:
            print(f"[CHECK] 正文缺失章节: {', '.join(missing_secs)}")

    allowed = ALLOWED_TRANSITIONS.get(status, [])
    if allowed:
        print(f"[CHECK] 可进入的下一状态: {', '.join(allowed)}")
    else:
        print(f"[CHECK] 当前状态无允许的下一状态（终态）")

    if allowed:
        target = allowed[0]
        blockers = check_transition_prerequisites(filepath, front, body, target, base_dir)
        if blockers:
            print(f"[CHECK] → {target} 阻塞原因:")
            for b in blockers:
                print(f"         ⛔ {b}")
        else:
            print(f"[CHECK] → {target} 无阻塞")
    else:
        print("[CHECK] 当前已是终态")

    return 0


# ── TRANSITION 命令 ───────────────────────────────────────────────

def cmd_transition(args, base_dir: Path):
    """检查状态流转是否允许。"""
    card_id = args.card_id
    target = args.to

    filepath = get_card_file(card_id, base_dir)
    if not filepath:
        print(f"[TRANSITION] 未找到卡片: {card_id}")
        return 1

    content = filepath.read_text(encoding="utf-8")
    front, body = parse_frontmatter(content)
    if not front:
        print(f"[TRANSITION] {card_id} 无法解析 frontmatter")
        return 1

    current = front.get("status", "")
    print(f"[TRANSITION] {card_id}: {current} → {target}")

    allow, reason = check_transition_allowed(current, target)
    if not allow:
        print(f"[TRANSITION] ⛔ 拒绝: {reason}")
        return 1

    blockers = check_transition_prerequisites(filepath, front, body, target, base_dir)
    if blockers:
        print(f"[TRANSITION] ⛔ 前置条件不满足:")
        for b in blockers:
            print(f"              ⛔ {b}")
        return 1

    print(f"[TRANSITION] ✅ 允许: {current} → {target}")
    print(f"[TRANSITION] 确认可由对应角色修改 status 字段后流转。")
    print(f"[TRANSITION] 程序不替角色写结论，请手动更新文件 frontmatter。")
    return 0


# ── DUE 命令 ──────────────────────────────────────────────────────

def cmd_due(args, base_dir: Path):
    """查找过期或即将过期的内容。"""
    due_items = []
    _, non_active_dirs, active_dirs = _get_scan_dirs(base_dir)
    all_dirs = non_active_dirs + active_dirs

    for d in all_dirs:
        if not d.exists():
            continue
        for f in collect_markdown_files(d):
            front, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            if not front:
                continue
            card_id = front.get("card_id", "")
            status = front.get("status", "")
            review_date = front.get("review_date", "")
            valid_until = front.get("valid_until", "")
            title = front.get("title", "")

            item = {
                "file": str(f.relative_to(base_dir)),
                "card_id": card_id,
                "title": title,
                "status": status,
                "review_date": review_date,
                "valid_until": valid_until,
            }

            if review_date and is_due_for_review(review_date):
                due_items.append({**item, "issue": "复审到期", "due_date": review_date})
            if valid_until and is_expired(valid_until):
                due_items.append({**item, "issue": "已过期", "due_date": valid_until})

    seen = set()
    unique_items = []
    for item in due_items:
        key = (item["card_id"], item["issue"])
        if key not in seen:
            seen.add(key)
            unique_items.append(item)

    paths = _make_paths(base_dir)
    out_path = paths["indexes"] / "pending_review.json"
    paths["indexes"].mkdir(parents=True, exist_ok=True)
    write_json(out_path, {
        "generated_at": TODAY.isoformat(),
        "total": len(unique_items),
        "note": "due 命令生成的复审/过期提醒",
        "pending_items": unique_items,
    })

    print(f"[DUE] 复审/过期提醒: {len(unique_items)} 项")
    for item in unique_items:
        print(f"  [{item['issue']}] {item['card_id']} — {item.get('title', '')} ({item['due_date']})")
    print(f"[DUE] 输出: {out_path}")
    return 0


# ── 主入口 ────────────────────────────────────────────────────────

def _get_base_dir(args) -> Path:
    """获取 base_dir：优先使用 --base-dir 参数，否则使用默认路径。"""
    if hasattr(args, "base_dir") and args.base_dir:
        return Path(args.base_dir).resolve()
    return DEFAULT_BASE


def main():
    parser = argparse.ArgumentParser(
        description="外部文献知识库治理工具 — knowledge_guard.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令:
  lint        检查所有文件字段、状态、角色合法性
  index       生成全部索引文件
  check       检查单张卡片状态和阻塞原因
  transition  检查状态流转是否允许
  due         查找过期/复审到期内容

使用示例:
  python3 tools/knowledge_guard.py lint
  python3 tools/knowledge_guard.py index
  python3 tools/knowledge_guard.py check CARD-20260610-001
  python3 tools/knowledge_guard.py transition CARD-20260610-001 --to ACTIVE
  python3 tools/knowledge_guard.py due
        """,
    )
    parser.add_argument("command", nargs="?", help="lint|index|check|transition|due")
    parser.add_argument("card_id", nargs="?", help="卡片 ID，用于 check 命令")
    parser.add_argument("--to", help="目标状态，用于 transition 命令")
    parser.add_argument("--base-dir", help="知识库根目录（默认为 knowledge/external_literature）")

    args = parser.parse_args()
    base_dir = _get_base_dir(args)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "lint": cmd_lint,
        "index": cmd_index,
        "check": cmd_check,
        "transition": cmd_transition,
        "due": cmd_due,
    }

    cmd = commands.get(args.command)
    if not cmd:
        print(f"未知命令: {args.command}")
        parser.print_help()
        return 1

    if args.command == "check" and not args.card_id:
        print("check 命令需要 card_id 参数")
        print("用法: python3 tools/knowledge_guard.py check CARD-YYYYMMDD-001")
        return 1
    if args.command == "transition":
        if not args.card_id:
            print("transition 命令需要 card_id 参数")
            return 1
        if not args.to:
            print("transition 命令需要 --to 参数")
            print("用法: python3 tools/knowledge_guard.py transition CARD-YYYYMMDD-001 --to ACTIVE")
            return 1

    if args.base_dir:
        print(f"[BASE-DIR] 使用自定义路径: {base_dir}")

    return cmd(args, base_dir)


if __name__ == "__main__":
    sys.exit(main())
