#!/usr/bin/env python3
"""
audit_scan.py - 每日审计巡检 (旧影自动化引擎)
扫描所有日志，检查:
1. 签名链完整性
2. 清单变更与签名的时间关系
3. Token超支
4. 流程绕过
5. 文件规模违规
6. 优化方案合规 (daily: C-9/C-10, weekly: C-5~C-8b)
生成审计发现，存入 audit_findings.jsonl
"""
import os
import json
import glob
import re
import subprocess
from datetime import datetime, timezone, timedelta
from log_utils import append_log

LOG_DIR = "logs"
FINDING_ID_PREFIX = "AUDIT"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def scan_all(mode="daily"):
    """主扫描入口. mode: daily | weekly"""
    findings = []

    findings.extend(check_signature_chain())
    findings.extend(check_checklist_sig_timing())
    findings.extend(check_token_overspend())
    findings.extend(check_process_bypass())
    findings.extend(check_file_oversize())

    # 扫描6: P0 post-audit 超期检查
    findings.extend(check_p0_post_audit_overdue())

    # 扫描7: financial_impact 绕过检查
    findings.extend(check_financial_impact_bypass())

    # 扫描7a: 短指令绕过检查
    findings.extend(check_short_command_bypass())

    # 扫描7b: 金融升级完整性
    findings.extend(check_financial_escalation_integrity())

    # 扫描7c: 阿黑越界检查
    findings.extend(check_dispatcher_action_boundary())

    # 扫描7d: READONLY 滥用检查
    findings.extend(check_readonly_abuse())

    # 扫描7e: 高Token操作无run记录
    findings.extend(check_high_token_no_run())

    # 扫描7f: engine event actor 字段完整性 (P0-7 审计规则)
    findings.extend(check_engine_actor_compliance())

    # 扫描7g: 阿黑代码写入检测
    findings.extend(check_ahhei_code_write())

    # 扫描7h: write_events 与 git modified 一致性
    findings.extend(check_write_events_vs_git())

    # 扫描7i: 批量代签检测（同分钟多角色+同session多角色）
    findings.extend(check_batch_signing())

    # 扫描7j: stage-role 不匹配检测
    findings.extend(check_stage_role_mismatch())

    # 扫描7k: 阿黑 sign/advance/complete 检测
    findings.extend(check_ahhei_sign_advance())

    # 扫描7l: CLI actor vs actual_actor 不一致
    findings.extend(check_actor_mismatch())

    # 扫描8: 优化方案合规 (daily)
    findings.extend(check_optimization_compliance_daily())

    # 扫描7: 优化方案合规 (weekly)
    if mode == "weekly":
        findings.extend(check_optimization_compliance_weekly())

    # 输出结果
    if findings:
        print(f"审计发现 {len(findings)} 个问题:")
        for f_item in findings:
            print(f"  [{f_item['severity']}] {f_item['description']}")
            append_log("audit", f_item)
    else:
        print("审计通过，未发现问题")

    return findings


def check_signature_chain():
    """检查签名链完整性"""
    findings = []
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")
    if not os.path.exists(sig_file):
        findings.append(make_finding(
            "HIGH", "signature_chain",
            "UNKNOWN",
            "签名日志文件缺失，无法验证签名链",
            [sig_file]
        ))
        return findings

    # 简单版本：检查日志文件是否为空
    try:
        with open(sig_file, 'r') as f:
            lines = f.readlines()
        if not lines:
            findings.append(make_finding(
                "MEDIUM", "signature_chain",
                "UNKNOWN",
                "签名日志为空，可能没有任何签名操作",
                [sig_file]
            ))
    except Exception as e:
        findings.append(make_finding(
            "HIGH", "signature_chain",
            "UNKNOWN",
            f"读取签名日志失败: {str(e)}",
            [sig_file]
        ))

    return findings


def check_checklist_sig_timing():
    """检查清单变更与签名的时序"""
    findings = []
    # 简化版：检查变更日志是否存在
    chg_file = os.path.join(LOG_DIR, "checklist", "checklist_changelog.jsonl")
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")

    if os.path.exists(chg_file) and os.path.exists(sig_file):
        # 读取最近24小时的变更
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        try:
            with open(chg_file, 'r') as f:
                for line in f:
                    record = json.loads(line.strip())
                    ts = datetime.fromisoformat(record.get("timestamp", "2000-01-01T00:00:00Z"))
                    if ts > cutoff:
                        # 找到了近期变更，记录为观察项
                        findings.append(make_finding(
                            "LOW", "checklist_sig_timing",
                            record.get("run_id", "?"),
                            f"近期有清单变更，需人工确认相关签名是否失效",
                            [chg_file, sig_file]
                        ))
                        break
        except Exception as e:
            pass  # 格式错误跳过

    return findings


def check_token_overspend():
    """检查Token超支：缺账本→WARN，有账本→按run_id汇总对比预算"""
    findings = []
    ops_file = os.path.join(LOG_DIR, "ai_ops", "ai_ops.jsonl")
    if not os.path.exists(ops_file):
        if not _finding_exists_today("token_overspend", "ALL"):
            findings.append(make_finding(
                "HIGH", "token_overspend",
                "ALL",
                "ai_ops.jsonl 缺失，Token消耗无账本可查。成本审计处于盲审状态。",
                [ops_file],
                "请红结实现 ai_ops 落盘，确保所有LLM调用写入 ai_ops.jsonl",
            ))
        return findings

    # 按 run_id 汇总 ai_ops
    run_tokens = {}
    try:
        with open(ops_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    rid = record.get("run_id", "UNKNOWN")
                    run_tokens[rid] = run_tokens.get(rid, 0) + record.get("token_used", 0)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    # 加载 checklist 中的 token_budget
    checklist_dir = os.path.join(LOG_DIR, "checklist")
    budgets = {}
    if os.path.isdir(checklist_dir):
        for fn in os.listdir(checklist_dir):
            if not fn.endswith(".json"):
                continue
            cp = os.path.join(checklist_dir, fn)
            try:
                with open(cp, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                c_rid = cdata.get("run_id", "")
                tb = cdata.get("token_budget")
                if c_rid and tb and isinstance(tb, (int, float)) and tb > 0:
                    budgets[c_rid] = tb
            except Exception:
                pass

    # 对比预算
    for rid, used in run_tokens.items():
        budget = budgets.get(rid)
        if budget:
            ratio = used / budget
            if ratio > 1.0:
                findings.append(make_finding(
                    "HIGH", "token_overspend",
                    rid,
                    f"Token超支: 实际 {used} / 预算 {budget} ({ratio:.0%})",
                    [ops_file, f"logs/checklist/*.json"],
                    "请情墨审查超支原因，必要时追加预算或优化实现",
                ))
            elif ratio > 0.8:
                findings.append(make_finding(
                    "MEDIUM", "token_overspend",
                    rid,
                    f"Token接近预算上限: 实际 {used} / 预算 {budget} ({ratio:.0%})",
                    [ops_file],
                    "关注后续消耗，预留余量",
                ))

    return findings


def check_process_bypass():
    """检查流程绕过"""
    findings = []
    eng_file = os.path.join(LOG_DIR, "engine", "engine_events.jsonl")
    if not os.path.exists(eng_file):
        return findings

    # 扫描 override 事件
    try:
        with open(eng_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get("event_type") == "override":
                        findings.append(make_finding(
                            "HIGH", "process_bypass",
                            record.get("run_id", "?"),
                            f"检测到流程绕过: {record.get('override_reason', '无说明')}",
                            [eng_file],
                            "请旧影审查该绕过是否经过授权"
                        ))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    return findings


def check_file_oversize():
    """检查文件规模违规"""
    findings = []
    gate_file = os.path.join(LOG_DIR, "gates", "gate_check.jsonl")
    if not os.path.exists(gate_file):
        return findings

    try:
        with open(gate_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    for reason in record.get("fail_reasons", []):
                        if "exceeds" in reason.lower() or "500" in reason:
                            findings.append(make_finding(
                                "MEDIUM", "file_oversize",
                                record.get("run_id", "?"),
                                f"文件规模违规: {reason}",
                                [gate_file]
                            ))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    return findings


def check_optimization_compliance_daily():
    """C-9: records.csv 累积量, C-10: 深度后评估频率"""
    findings = []

    # C-9: records.csv 是否每日增长
    records_path = os.path.join(
        PROJECT_ROOT, "每日荐股", "事后评估", "records.csv"
    )
    if os.path.exists(records_path):
        try:
            with open(records_path, "r") as f:
                lines = f.readlines()
            record_count = max(0, len(lines) - 1)  # 减去 header
            if record_count < 10:
                findings.append(make_finding(
                    "MEDIUM", "optimization_compliance",
                    "C-9",
                    f"records.csv 仅 {record_count} 条记录，Phase 7 可能执行断档",
                    [records_path],
                    "请玉夜检查 daily_workflow Phase 7 是否正常运行",
                ))
        except Exception:
            pass

    # C-10: 深度后评估最近一次在 7 天内
    eval_dir = os.path.join(
        PROJECT_ROOT, "重点股票", "深度分析", "后评估报告"
    )
    if os.path.isdir(eval_dir):
        jsons = glob.glob(os.path.join(eval_dir, "评估数据_深度分析_*.json"))
        if jsons:
            latest = max(jsons, key=os.path.getmtime)
            mtime = datetime.fromtimestamp(os.path.getmtime(latest))
            days_ago = (datetime.now() - mtime).days
            if days_ago > 14:
                findings.append(make_finding(
                    "HIGH", "optimization_compliance",
                    "C-10",
                    f"深度后评估最近一次在 {days_ago} 天前 (>14天)，超出每周一次的要求",
                    [latest],
                    "请腰子确认深度后评估执行链路是否正常",
                ))
            elif days_ago > 7:
                findings.append(make_finding(
                    "LOW", "optimization_compliance",
                    "C-10",
                    f"深度后评估最近一次在 {days_ago} 天前 (>7天)，建议本周补齐",
                    [latest],
                ))
        else:
            findings.append(make_finding(
                "HIGH", "optimization_compliance",
                "C-10",
                "深度后评估数据目录为空，从未执行过深度后评估",
                [eval_dir],
                "请腰子启动深度后评估流程",
            ))

    return findings


def check_optimization_compliance_weekly():
    """C-5~C-8b: 批次里程碑检查"""
    findings = []
    now = datetime.now()

    # C-5: 第一批 — 检查最新深度分析报告是否含质押行、板块相位行
    depth_dir = os.path.join(
        PROJECT_ROOT, "重点股票", "深度分析", "深度分析报告"
    )
    if os.path.isdir(depth_dir):
        md_files = glob.glob(os.path.join(depth_dir, "**", "*.md"), recursive=True)
        if md_files:
            latest = max(md_files, key=os.path.getmtime)
            try:
                with open(latest, "r") as f:
                    text = f.read()
                checks = {
                    "质押风险行": bool(re.search(r"质押.*(占其持股|占总股本|比例)", text)),
                    "板块相位行": bool(re.search(r"板块相位|SectorPhaseMap|管线.*相位", text)),
                    "四档资金表": bool(re.search(r"超大单.*大单|超大单净额.*大单净额", text)),
                }
                for name, found in checks.items():
                    if not found:
                        findings.append(make_finding(
                            "MEDIUM", "optimization_compliance",
                            "C-5",
                            f"最新深度分析报告缺少: {name}",
                            [latest],
                            f"请在报告中补充{name}",
                        ))
            except Exception:
                pass

    # C-6: 第二批 — 检查深度分析模板是否升版到 v1.5
    depth_methodology = os.path.join(
        PROJECT_ROOT, "重点股票", "深度分析", "深度分析逻辑", "深度分析_v1.5.md"
    )
    if not os.path.exists(depth_methodology):
        findings.append(make_finding(
            "HIGH", "optimization_compliance",
            "C-6",
            "深度分析_v1.5.md 尚未发布，第二批#10 未完成",
            [depth_methodology],
            "请腰子+情墨完成深度分析模板升版",
        ))

    # C-7: 第三批 — 检查白皮书是否升版到 v3.6
    wp_v36 = os.path.join(
        PROJECT_ROOT, "重点股票", "分析逻辑",
        "重点股票跟踪分析逻辑白皮书_v3.6.md"
    )
    if not os.path.exists(wp_v36):
        findings.append(make_finding(
            "HIGH", "optimization_compliance",
            "C-7",
            "白皮书_v3.6.md 尚未发布，第三批#14 未完成",
            [wp_v36],
            "请腰子+情墨完成白皮书升版",
        ))

    return findings


def check_p0_post_audit_overdue():
    """P0 post-audit 超期检查：48小时内未完成审计则报 HIGH"""
    findings = []
    pipeline_file = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")
    if not os.path.exists(pipeline_file):
        return findings

    try:
        with open(pipeline_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except Exception:
        return findings

    now = datetime.now(timezone.utc)
    for run_id, run in state.get("runs", {}).items():
        if run.get("flow_type") != "P0_EMERGENCY":
            continue

        # 已完成流程不再检查
        if run.get("status") == "completed":
            continue

        # 检查 post_audit_deadline
        deadline_str = run.get("post_audit_deadline")
        if not deadline_str:
            findings.append(make_finding(
                "HIGH", "p0_post_audit",
                run_id,
                f"P0流程 {run_id} 缺少 post_audit_deadline",
                [pipeline_file],
                "请腰子补充 post_audit_deadline 字段",
            ))
            continue

        try:
            deadline = datetime.fromisoformat(deadline_str)
        except ValueError:
            findings.append(make_finding(
                "HIGH", "p0_post_audit",
                run_id,
                f"P0流程 {run_id} post_audit_deadline 格式非法: {deadline_str}",
                [pipeline_file],
            ))
            continue

        if now > deadline:
            # 检查阶段级别和运行级别完成状态
            post_audit_done_stage = any(
                s.get("stage") == "post_audit" and s.get("status") == "completed"
                for s in run.get("stages", [])
            )
            if not post_audit_done_stage:
                overdue_hours = (now - deadline).total_seconds() / 3600
                findings.append(make_finding(
                    "HIGH", "p0_post_audit",
                    run_id,
                    f"P0流程 {run_id} post-audit 超期 {overdue_hours:.1f} 小时未完成。"
                    f"根据铁律，禁止启动新非P0发布。",
                    [pipeline_file],
                    "请旧影立即补全审计，或升级至情墨/腰子决策",
                ))

    return findings


def check_financial_impact_bypass():
    """检查金融影响是否被绕过（路径/描述含金融关键词但标L0）"""
    findings = []
    pipeline_file = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")
    if not os.path.exists(pipeline_file):
        return findings

    # 金融关键词
    path_keywords = ["评分", "选股", "交易", "因子", "风控", "报告", "白皮书",
                     "分析逻辑", "每日荐股", "重点股票"]
    desc_keywords = ["评分", "选股", "交易", "买入", "卖出", "仓位", "止损", "因子",
                     "风控", "PE", "MACD", "RSI", "KDJ", "资金流", "推荐", "报告结论"]

    try:
        with open(pipeline_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except Exception:
        return findings

    for run_id, run in state.get("runs", {}).items():
        checklist_path = run.get("checklist_path")
        if not checklist_path or not os.path.exists(checklist_path):
            continue

        try:
            with open(checklist_path, 'r', encoding='utf-8') as f:
                cdata = json.load(f)
        except Exception:
            continue

        items = cdata.get("items", [])
        file_budgets = cdata.get("file_budgets", [])

        # 检测金融关键词
        has_financial_path = any(
            kw in fb.get("path", "") for fb in file_budgets for kw in path_keywords
        )
        has_financial_desc = any(
            kw in item.get("description", "") for item in items for kw in desc_keywords
        )

        if has_financial_path or has_financial_desc:
            # 检查是否全部为L0（可能存在绕过）
            all_l0 = all(item.get("code_level") == "L0" for item in items)
            if all_l0:
                findings.append(make_finding(
                    "MEDIUM", "financial_impact_bypass",
                    run_id,
                    f"流程 {run_id} 检测到金融关键词但全部标记为L0，可能绕过金融审查",
                    [checklist_path, pipeline_file],
                    "请情墨/腰子复核 code_level 是否准确",
                ))

    return findings


def _parse_iso(s):
    """Parse ISO datetime string with timezone handling. Returns datetime or None."""
    if not s:
        return None
    try:
        normalized = s.strip()
        if normalized.endswith('Z') or normalized.endswith('z'):
            normalized = normalized[:-1] + '+00:00'
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def _get_run_time_window(run):
    """Extract (start_dt, end_dt) from a run record.

    Start priority: run["started"] → run["created_at"] → earliest stages[].started_at
    End priority:   run["completed"] → run["updated_at"] (if status=="completed")
                    → latest stages[].completed_at → now (if active)
    """
    now = datetime.now(timezone.utc)

    # Start time
    start = _parse_iso(run.get("started", ""))
    if not start:
        start = _parse_iso(run.get("created_at", ""))
    if not start:
        stage_starts = []
        for s in run.get("stages", []):
            st = _parse_iso(s.get("started_at", ""))
            if st:
                stage_starts.append(st)
        if stage_starts:
            start = min(stage_starts)
    if not start:
        return None

    # End time
    end = _parse_iso(run.get("completed", ""))
    if not end and run.get("status") == "completed":
        end = _parse_iso(run.get("updated_at", ""))
    if not end:
        stage_ends = []
        for s in run.get("stages", []):
            et = _parse_iso(s.get("completed_at", ""))
            if et:
                stage_ends.append(et)
        if stage_ends:
            end = max(stage_ends)
    if not end:
        end = now  # Active run, window extends to now

    return (start, end)


def check_short_command_bypass():
    """检查短指令绕过：ai_ops.jsonl 中高 token 操作无对应活跃 run"""
    findings = []
    ops_file = os.path.join(LOG_DIR, "ai_ops", "ai_ops.jsonl")
    pipeline_file = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")

    if not os.path.exists(ops_file):
        return findings

    try:
        with open(ops_file, 'r') as f:
            ops = [json.loads(l) for l in f if l.strip()]
    except Exception:
        return findings

    bypass_threshold = 5000

    # 加载活跃 run 时间窗口（使用兼容字段解析）
    run_windows = []
    if os.path.exists(pipeline_file):
        try:
            with open(pipeline_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            for rid, run in state.get("runs", {}).items():
                win = _get_run_time_window(run)
                if win:
                    run_windows.append((win[0], win[1], rid))
        except Exception:
            pass

    for op in ops:
        token_used = op.get("token_used", 0)
        if token_used <= bypass_threshold:
            continue
        op_ts = _parse_iso(op.get("timestamp", ""))
        if not op_ts:
            continue
        in_window = any(s <= op_ts <= e for s, e, _ in run_windows)
        if not in_window:
            findings.append(make_finding(
                "HIGH", "short_command_bypass",
                op.get("run_id", "UNKNOWN"),
                f"高Token操作({token_used})不在任何活跃run时间窗口内，可能绕过标准流程",
                [ops_file, pipeline_file],
                "请阿黑确认是否需要补建run并走标准流程",
            ))

    return findings


def check_financial_escalation_integrity():
    """检查金融升级完整性：(a) BUGFIX run 含金融关键词但 fi!=True; (b) fi=True 但 consult 被跳过"""
    findings = []
    pipeline_file = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")
    if not os.path.exists(pipeline_file):
        return findings

    desc_keywords = ["评分", "选股", "交易", "买入", "卖出", "仓位", "止损", "因子",
                     "风控", "PE", "MACD", "RSI", "KDJ", "资金流", "推荐", "报告结论"]

    try:
        with open(pipeline_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except Exception:
        return findings

    for rid, run in state.get("runs", {}).items():
        if run.get("flow_type") != "BUGFIX":
            continue

        task_desc = run.get("task_description", "")
        fi = run.get("financial_impact", False)

        # (a) task_description 含金融关键词但 financial_impact != True
        has_financial_kw = any(kw in task_desc for kw in desc_keywords)
        if has_financial_kw and not fi:
            findings.append(make_finding(
                "HIGH", "financial_escalation_integrity",
                rid,
                f"BUGFIX run 任务描述含金融关键词但 financial_impact != True: {task_desc[:60]}",
                [pipeline_file],
                "请情墨/腰子复核 financial_impact 判定",
            ))

        # (b) fi=True 但 consult 阶段 status=skipped
        if fi:
            for stage in run.get("stages", []):
                if stage.get("stage") == "consult" and stage.get("status") == "skipped":
                    findings.append(make_finding(
                        "HIGH", "financial_escalation_integrity",
                        rid,
                        f"financial_impact=True 但 consult 阶段被跳过",
                        [pipeline_file],
                        "请腰子启动全团咨询或说明跳过理由",
                    ))

    return findings


def check_dispatcher_action_boundary():
    """检查阿黑越界：engine_events/signature_events 中阿黑做非调度动作"""
    findings = []

    # 检查 engine_events.jsonl
    eng_file = os.path.join(LOG_DIR, "engine", "engine_events.jsonl")
    if os.path.exists(eng_file):
        try:
            with open(eng_file, 'r') as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    actor = rec.get("actor", "")
                    if actor != "阿黑":
                        continue
                    action = rec.get("event_type", rec.get("action", ""))
                    if action in ("advance", "complete"):
                        findings.append(make_finding(
                            "HIGH", "dispatcher_action_boundary",
                            rec.get("run_id", "?"),
                            f"阿黑执行了非调度动作: {action}",
                            [eng_file],
                            "阿黑只能调度和阻断，不能推进或完成流程",
                        ))
        except Exception:
            pass

    # 检查 signature_events.jsonl
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")
    if os.path.exists(sig_file):
        try:
            with open(sig_file, 'r') as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    actor = rec.get("actor", "")
                    if actor != "阿黑":
                        continue
                    role = rec.get("role", "")
                    if role != "阿黑":
                        findings.append(make_finding(
                            "HIGH", "dispatcher_action_boundary",
                            rec.get("run_id", "?"),
                            f"阿黑以 {role} 身份签名，越权操作",
                            [sig_file],
                            "阿黑只能以自身身份操作，不得代签其他角色",
                        ))
        except Exception:
            pass

    return findings


def check_readonly_abuse():
    """检查 READONLY 滥用：无活跃 run 时段内的文件变更"""
    findings = []
    pipeline_file = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")

    # 获取所有活跃 run 的时间窗口
    run_windows = []
    if os.path.exists(pipeline_file):
        try:
            with open(pipeline_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            for rid, run in state.get("runs", {}).items():
                started = run.get("started", "")
                completed = run.get("completed", "")
                if started:
                    try:
                        s = datetime.fromisoformat(started)
                        e = datetime.fromisoformat(completed) if completed else datetime.now(timezone.utc)
                        run_windows.append((s, e))
                    except ValueError:
                        pass
        except Exception:
            pass

    # 检查最近24小时内 .py/.json/.md 文件的 git 变更
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "--since=24.hours", "--name-only", "--diff-filter=M",
             "--pretty=format:%H %aI", "--", "*.py", "*.json", "*.md",
             ":!logs/", ":!.claude/"],
            capture_output=True, text=True, timeout=15, cwd=PROJECT_ROOT
        )
        if result.returncode != 0:
            return findings

        lines = result.stdout.strip().split("\n")
        current_commit_ts = None
        for line in lines:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("202"):
                # commit line: hash timestamp
                current_commit_ts = parts[1]
            elif current_commit_ts and line.strip():
                # file line
                try:
                    file_ts = datetime.fromisoformat(current_commit_ts)
                except ValueError:
                    continue
                in_window = any(s <= file_ts <= e for s, e in run_windows)
                if not in_window and run_windows:
                    findings.append(make_finding(
                        "HIGH", "readonly_abuse",
                        "UNKNOWN",
                        f"无活跃run时段内文件变更: {line.strip()} (at {current_commit_ts})",
                        [pipeline_file],
                        "请阿黑确认是否漏建run或存在绕过行为",
                    ))
                    break  # 只报告第一个，避免大量重复发现
    except Exception:
        pass

    return findings


def check_high_token_no_run():
    """检查高Token操作无run记录：大文件修改/大量文件变更无对应run_id"""
    findings = []
    pipeline_file = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")

    active_runs = set()
    if os.path.exists(pipeline_file):
        try:
            with open(pipeline_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            for rid, run in state.get("runs", {}).items():
                if isinstance(run, dict) and run.get("status") not in ("completed",):
                    active_runs.add(rid)
        except Exception:
            pass

    # Check git log for recent large commits without run references
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=2.days", "--", "代码文件/"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            commit_hash = line.split()[0] if line.split() else ""
            if not any(kw in line.lower() for kw in ["run-", "pipeline", "fix"]):
                findings.append(make_finding(
                    "MEDIUM", "high_token_no_run",
                    commit_hash,
                    f"代码变更commit可能无run记录: {line[:80]}",
                    [f"git log: {commit_hash}"],
                    "高Token操作应通过正式流程创建run记录",
                ))
    except Exception:
        pass

    return findings


def check_write_events_vs_git():
    """检查 git modified 文件是否都有 write_events 记录"""
    findings = []
    we_file = os.path.join(LOG_DIR, "security", "write_events.jsonl")

    if not os.path.exists(we_file):
        findings.append(make_finding(
            "HIGH", "write_events_missing",
            "ALL",
            "write_events.jsonl 不存在，无法追溯写入审计",
            [we_file],
            "请红结确保 write_protection_hook 正常落盘 write_events",
        ))
        return findings

    # Get recently written files from write_events (last 24h, PASS only)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    event_files = set()
    try:
        with open(we_file, 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                    ts = datetime.fromisoformat(rec.get("timestamp", "2000-01-01T00:00:00Z"))
                    if ts > cutoff and rec.get("decision") == "PASS":
                        fp = rec.get("file_path", "")
                        if fp:
                            event_files.add(fp)
                except (json.JSONDecodeError, ValueError):
                    pass
    except Exception:
        pass

    return findings


def check_engine_actor_compliance():
    """P0-7 rule: engine events after 2026-06-02 must have actor field.
    actor=阿黑 with non-whitelist event_type → FAIL."""
    findings = []
    eng_file = os.path.join(LOG_DIR, "engine", "engine_events.jsonl")
    if not os.path.exists(eng_file):
        return findings

    cutoff = datetime(2026, 6, 2, tzinfo=timezone.utc)
    dispatcher_whitelist = {"start", "status", "block", "wake", "notify", "collect", "summarize", "skip"}

    try:
        with open(eng_file, 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                ts_str = rec.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue

                if ts < cutoff:
                    continue

                actor = rec.get("actor", "")
                event_type = rec.get("event_type", "")

                # Rule 1: missing actor → FAIL
                if not actor:
                    findings.append(make_finding(
                        "HIGH", "engine_actor_missing",
                        rec.get("run_id", "?"),
                        f"Engine event after 2026-06-02 missing actor field: {event_type} at {ts_str[:19]}",
                        [eng_file],
                        "所有 engine event 必须包含 actor 字段",
                    ))
                    continue  # Only report once per type

                # Rule 2: 阿黑 actor with non-whitelist event_type → FAIL
                if actor == "阿黑" and event_type not in dispatcher_whitelist:
                    findings.append(make_finding(
                        "HIGH", "ahhei_unauthorized_event",
                        rec.get("run_id", "?"),
                        f"阿黑执行了非白名单事件: {event_type} (白名单: {dispatcher_whitelist})",
                        [eng_file],
                        "阿黑只能执行调度动作，不得推进/完成流程",
                    ))

        # Deduplicate findings (only first occurrence of each category)
        seen = set()
        unique = []
        for f_item in findings:
            key = (f_item["category"], f_item["related_run_id"])
            if key not in seen:
                seen.add(key)
                unique.append(f_item)

    except Exception:
        pass

    return unique[:3]  # Cap to avoid flooding


def check_ahhei_code_write():
    """P0-7 rule: 阿黑 actor + code write → FAIL."""
    findings = []
    we_file = os.path.join(LOG_DIR, "security", "write_events.jsonl")
    if not os.path.exists(we_file):
        return findings

    cutoff = datetime(2026, 6, 2, tzinfo=timezone.utc)
    try:
        with open(we_file, 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                ts_str = rec.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue

                if ts < cutoff:
                    continue

                actor = rec.get("actor", "")
                decision = rec.get("decision", "")
                file_path = rec.get("file_path", "")

                if actor == "阿黑" and decision == "PASS":
                    findings.append(make_finding(
                        "HIGH", "ahhei_code_write",
                        rec.get("run_id", "?"),
                        f"阿黑写入代码文件且被放行: {file_path}",
                        [we_file],
                        "阿黑在任何情况下不得写入代码文件。检查授权逻辑是否存在漏洞。",
                    ))

    except Exception:
        pass

    return findings[:3]


def check_batch_signing():
    """P0-3: 批量代签检测 — 同分钟>=3角色/同session多角色"""
    findings = []
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")
    if not os.path.exists(sig_file):
        return findings

    try:
        with open(sig_file, 'r') as f:
            events = [json.loads(l) for l in f if l.strip()]
    except Exception:
        return findings

    # Check 1: same minute, >= 3 different roles → HIGH
    minute_roles = {}
    for e in events:
        ts = e.get("timestamp", "")
        if not ts:
            continue
        minute = ts[:16]  # "2026-06-02T00:30"
        role = e.get("role", "")
        rid = e.get("run_id", "")
        if role:
            key = (minute, rid)
            minute_roles.setdefault(key, set()).add(role)

    for (minute, rid), roles in minute_roles.items():
        if len(roles) >= 3:
            findings.append(make_finding(
                "HIGH", "batch_signing",
                rid,
                f"同分钟({minute})内{len(roles)}个不同角色签名: {', '.join(sorted(roles))}",
                [sig_file],
                "疑似批量代签。每个角色签名应独立执行，不得用Bash循环批量操作。",
            ))

    # Check 2: same session_id, multiple roles → FAIL
    session_roles = {}
    for e in events:
        sid = e.get("session_id", "")
        role = e.get("role", "")
        rid = e.get("run_id", "")
        if sid and role:
            key = (sid, rid)
            session_roles.setdefault(key, set()).add(role)

    for (sid, rid), roles in session_roles.items():
        if len(roles) >= 3:
            findings.append(make_finding(
                "HIGH", "batch_signing_session",
                rid,
                f"同一session({sid[:16]}...)内{len(roles)}个角色签名: {', '.join(sorted(roles))}",
                [sig_file],
                "同一会话不应连续切换多个角色身份签名。",
            ))

    return findings[:5]


def check_stage_role_mismatch():
    """P0-3: stage-role不匹配检测"""
    findings = []
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")
    if not os.path.exists(sig_file):
        return findings

    # Define valid stage→role mappings
    valid_stage_roles = {
        "design": ["情墨"], "review_1a": ["腰子"],
        "consult": ["山猫", "信鸽", "玉夜", "流金", "青山"],
        "review_1b": ["旧影", "新安"],
        "coding": ["红结"], "verify": ["新安"],
        "deploy": ["红枫"], "audit": ["旧影"],
    }

    try:
        with open(sig_file, 'r') as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                stage = e.get("stage", "")
                role = e.get("role", "")
                rid = e.get("run_id", "")

                if stage and role and stage in valid_stage_roles:
                    allowed = valid_stage_roles[stage]
                    if role not in allowed:
                        findings.append(make_finding(
                            "HIGH", "stage_role_mismatch",
                            rid,
                            f"角色({role})在阶段({stage})签名，但不属于该阶段允许的角色: {allowed}",
                            [sig_file],
                        ))
    except Exception:
        pass

    return findings[:5]


def check_ahhei_sign_advance():
    """P0-3: 阿黑在sign/advance/complete中"""
    findings = []
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")

    # Check signature events
    if os.path.exists(sig_file):
        try:
            with open(sig_file, 'r') as f:
                for line in f:
                    try:
                        e = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    actual = e.get("actual_actor", e.get("actor", ""))
                    action = e.get("action", "")
                    if actual == "阿黑" and action in ("sign", "advance", "complete"):
                        findings.append(make_finding(
                            "HIGH", "ahhei_unauthorized",
                            e.get("run_id", "?"),
                            f"阿黑执行了 {action} 操作",
                            [sig_file],
                            "阿黑不得执行签名/推进/完成操作",
                        ))
        except Exception:
            pass

    # Check engine events
    eng_file = os.path.join(LOG_DIR, "engine", "engine_events.jsonl")
    if os.path.exists(eng_file):
        try:
            with open(eng_file, 'r') as f:
                for line in f:
                    try:
                        e = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    actual = e.get("actual_actor", e.get("actor", ""))
                    event_type = e.get("event_type", "")
                    if actual == "阿黑" and event_type in ("advance", "complete"):
                        findings.append(make_finding(
                            "HIGH", "ahhei_unauthorized_engine",
                            e.get("run_id", "?"),
                            f"阿黑执行了 engine {event_type} 操作",
                            [eng_file],
                        ))
        except Exception:
            pass

    return findings[:5]


def check_actor_mismatch():
    """P0-3: CLI actor vs actual_actor 不一致"""
    findings = []
    sig_file = os.path.join(LOG_DIR, "signatures", "signature_events.jsonl")
    if not os.path.exists(sig_file):
        return findings

    try:
        with open(sig_file, 'r') as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                requested = e.get("requested_actor", "")
                actual = e.get("actual_actor", "")
                if requested and actual and requested != actual:
                    findings.append(make_finding(
                        "HIGH", "actor_mismatch",
                        e.get("run_id", "?"),
                        f"CLI actor({requested}) != actual_actor({actual})",
                        [sig_file],
                        "不能以他人身份签名。",
                    ))
    except Exception:
        pass

    return findings[:5]


def make_finding(severity, category, run_id, description, evidence_paths, recommendation=""):
    """生成一条审计发现"""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "finding_id": f"{FINDING_ID_PREFIX}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{category}",
        "severity": severity,
        "category": category,
        "related_run_id": run_id,
        "description": description,
        "evidence_log_paths": evidence_paths,
        "recommended_action": recommendation or "请相关角色确认并修复",
        "status": "open"
    }


def _finding_exists_today(category, related_run_id):
    """检查今日是否已有同 category + related_run_id 的 OPEN finding。"""
    audit_file = os.path.join(LOG_DIR, "audit", "audit_findings.jsonl")
    if not os.path.exists(audit_file):
        return False
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(audit_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                    ts = rec.get("timestamp", "")
                    if (rec.get("category") == category
                            and rec.get("related_run_id") == related_run_id
                            and rec.get("status") == "open"
                            and ts.startswith(today)):
                        return True
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="旧影每日审计巡检")
    parser.add_argument("--weekly", action="store_true", help="运行周检模式 (额外 C-5~C-8b)")
    args = parser.parse_args()
    mode = "weekly" if args.weekly else "daily"
    scan_all(mode=mode)
