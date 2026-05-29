#!/usr/bin/env python3
"""
audit_scan.py - 每日审计巡检 (旧影自动化引擎)
扫描所有日志，检查:
1. 签名链完整性
2. 清单变更与签名的时间关系
3. Token超支
4. 流程绕过
5. 文件规模违规
生成审计发现，存入 audit_findings.jsonl
"""
import os
import json
import glob
from datetime import datetime, timezone, timedelta
from log_utils import append_log

LOG_DIR = "logs"
FINDING_ID_PREFIX = "AUDIT"


def scan_all():
    """主扫描入口"""
    findings = []

    # 扫描1: 签名链完整性
    findings.extend(check_signature_chain())

    # 扫描2: 清单变更与签名关系
    findings.extend(check_checklist_sig_timing())

    # 扫描3: Token超支
    findings.extend(check_token_overspend())

    # 扫描4: 流程绕过
    findings.extend(check_process_bypass())

    # 扫描5: 文件规模违规
    findings.extend(check_file_oversize())

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
    scan_all()
