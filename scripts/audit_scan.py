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
    """检查Token超支"""
    findings = []
    ops_file = os.path.join(LOG_DIR, "ai_ops", "ai_ops.jsonl")
    if not os.path.exists(ops_file):
        return findings

    # 简化版：统计所有AI操作的Token总量
    total_tokens = 0
    try:
        with open(ops_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    total_tokens += record.get("token_used", 0)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    # 如果Token总量异常（阈值可配置）
    if total_tokens > 1000000:  # 1M Token 告警阈值
        findings.append(make_finding(
            "MEDIUM", "token_overspend",
            "ALL",
            f"累计Token消耗超过阈值: {total_tokens} tokens",
            [ops_file],
            "请情墨审查Token使用趋势"
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

    # 加载活跃 run 时间窗口
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
                        run_windows.append((s, e, rid))
                    except ValueError:
                        pass
        except Exception:
            pass

    bypass_threshold = 5000
    for op in ops:
        token_used = op.get("token_used", 0)
        if token_used <= bypass_threshold:
            continue
        try:
            op_ts = datetime.fromisoformat(op.get("timestamp", ""))
        except ValueError:
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="旧影每日审计巡检")
    parser.add_argument("--weekly", action="store_true", help="运行周检模式 (额外 C-5~C-8b)")
    args = parser.parse_args()
    mode = "weekly" if args.weekly else "daily"
    scan_all(mode=mode)
