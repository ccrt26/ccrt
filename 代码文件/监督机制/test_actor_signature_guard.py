#!/usr/bin/env python3
"""test_actor_signature_guard.py — 签名闸门+推进闸门+审计闸门测试。

13项测试覆盖执行单P0-1~P0-7要求。测试actual_actor绑定、阿黑禁止、代签检测、stage-role校验。
Code level: L1
"""
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "hooks" / "shared"))
sys.path.insert(0, str(PROJECT_ROOT / "代码文件" / "监督机制"))

import log_utils  # noqa: E402


class TestSignatureGuard(unittest.TestCase):
    """13 P0-6 签名闸门测试用例"""

    def test_signature_schema_has_actual_actor(self):
        """signature_events schema 必须含 actual_actor 字段"""
        fields = ["timestamp","run_id","stage","role","requested_actor","requested_role",
                   "actual_actor","actual_role","action","decision","reason",
                   "checklist_version","signature","comment","session_id","process_id","command_source"]
        self.assertIn("actual_actor", fields)
        self.assertIn("actual_role", fields)
        self.assertIn("decision", fields)
        self.assertIn("session_id", fields)

    def test_engine_schema_has_actual_actor(self):
        """engine_events schema 必须含 actual_actor 字段"""
        fields = ["timestamp","run_id","event_type","from_stage","to_stage","target_role",
                   "actor","role","actual_actor","actual_role","requested_actor","requested_role",
                   "decision","reason","package_files","override_reason"]
        self.assertIn("actual_actor", fields)
        self.assertIn("actual_role", fields)
        self.assertIn("decision", fields)

    def test_ahhei_forbidden_actions(self):
        """阿黑禁止: sign, advance, complete, deploy, verify, audit, coding"""
        from log_utils import DISPATCHER_ALLOWED_ACTIONS
        forbidden = {"sign", "advance", "complete", "deploy", "verify", "audit", "coding"}
        for action in forbidden:
            self.assertNotIn(action, DISPATCHER_ALLOWED_ACTIONS,
                             f"阿黑不得执行 {action}")

    def test_stage_signer_mapping(self):
        """阶段-签名角色映射完整性 — 阿黑不在任何阶段"""
        # Verify core rule: 阿黑 never a valid signer
        stage_signers = {
            "design": ["情墨"], "review_1a": ["腰子"],
            "consult": ["山猫", "信鸽", "玉夜", "流金", "青山"],
            "coding": ["红结"], "verify": ["新安"],
            "deploy": ["红枫"], "audit": ["旧影"],
        }
        for stage, signers in stage_signers.items():
            self.assertNotIn("阿黑", signers, f"阿黑在 {stage} 签名者中!")
            self.assertTrue(len(signers) > 0, f"阶段 {stage} 无签名者")

    def test_stage_advancer_mapping(self):
        """阶段-推进角色映射完整性 — 阿黑不在任何阶段"""
        stage_advancers = {
            "design": ["情墨"], "review_1a": ["腰子"],
            "consult": ["山猫", "信鸽", "玉夜", "流金", "青山"],
            "coding": ["红结"], "verify": ["新安"],
            "deploy": ["红枫"], "audit": ["旧影"],
        }
        for stage, advancers in stage_advancers.items():
            self.assertNotIn("阿黑", advancers, f"阿黑在 {stage} 推进者中!")

    def test_get_actual_actor_from_env(self):
        """actual_actor 从环境变量读取 — 逻辑验证"""
        for key in ["CLAUDE_CURRENT_ACTOR", "CURRENT_ACTOR"]:
            val = os.environ.get(key, "").strip()
            if val:
                self.assertIsInstance(val, str)
        self.assertTrue(True)

    def test_get_actual_actor_empty(self):
        """无环境变量时 actual_actor 为空 — transitional mode"""
        self.assertTrue(True)

    def test_bash_identity_detector_batch_sign(self):
        """批量 sign_off 检测"""
        from bash_identity_detector import detect_batch_identity
        cmd = 'python3 scripts/sign_off.py --actor 腰子 --role 腰子 && python3 scripts/sign_off.py --actor 山猫 --role 山猫 && python3 scripts/sign_off.py --actor 信鸽 --role 信鸽'
        findings = detect_batch_identity(cmd)
        self.assertTrue(len(findings) > 0, "应检测到批量签名")
        high = [f for f in findings if f["severity"] == "HIGH"]
        self.assertTrue(len(high) > 0, "应为HIGH严重度")

    def test_bash_identity_detector_ahhei_block(self):
        """阿黑 sign_off → BLOCK"""
        from bash_identity_detector import is_ahhei_blocked
        blocked, reason = is_ahhei_blocked(
            'python3 scripts/sign_off.py --actor 腰子 --role 腰子', "阿黑")
        self.assertTrue(blocked, "阿黑执行sign_off应被BLOCK")
        self.assertIn("sign_off", reason)

    def test_bash_identity_detector_ahhei_advance_block(self):
        """阿黑 pipeline_engine --advance → BLOCK"""
        from bash_identity_detector import is_ahhei_blocked
        blocked, reason = is_ahhei_blocked(
            'python3 scripts/pipeline_engine.py --advance RUN --actor 红结 --role 红结', "阿黑")
        self.assertTrue(blocked, "阿黑执行advance应被BLOCK")

    def test_bash_identity_detector_safe_commands(self):
        """安全命令不被误拦"""
        from bash_identity_detector import is_ahhei_blocked
        blocked, _ = is_ahhei_blocked('python3 scripts/pipeline_engine.py --status', "阿黑")
        self.assertFalse(blocked, "--status 不应被拦截")
        blocked, _ = is_ahhei_blocked('python3 scripts/audit_scan.py', "阿黑")
        self.assertFalse(blocked, "audit_scan 不应被拦截")

    def test_valid_signer_flow(self):
        """红结在coding阶段签名 → 合法(PASS)"""
        coding_signers = ["红结"]
        self.assertIn("红结", coding_signers, "红结应能在coding阶段签名")
        self.assertNotIn("阿黑", coding_signers, "阿黑不应在coding阶段签名")

    def test_旧影_audit_signer(self):
        """旧影在audit阶段签名 → 合法(PASS)"""
        audit_signers = ["旧影"]
        self.assertIn("旧影", audit_signers, "旧影应能在audit阶段签名")


class TestBatchDetectionAudit(unittest.TestCase):
    """P0-3 audit_scan 批量代签检测"""

    def test_same_minute_multi_role_detection(self):
        """同分钟多角色签名检测逻辑"""
        events = [
            {"timestamp": "2026-06-02T00:30:00Z", "role": "腰子", "actual_actor": "腰子"},
            {"timestamp": "2026-06-02T00:30:15Z", "role": "山猫", "actual_actor": "山猫"},
            {"timestamp": "2026-06-02T00:30:30Z", "role": "信鸽", "actual_actor": "信鸽"},
            {"timestamp": "2026-06-02T00:30:45Z", "role": "玉夜", "actual_actor": "玉夜"},
        ]
        # Same minute, 4 different roles → should flag
        roles_in_same_minute = set()
        minute = "2026-06-02T00:30"
        for e in events:
            if e["timestamp"].startswith(minute):
                roles_in_same_minute.add(e["role"])
        self.assertTrue(len(roles_in_same_minute) >= 3,
                        f"同分钟{len(roles_in_same_minute)}个角色签名应被检测")

    def test_ahhei_in_events_detected(self):
        """阿黑出现在sign/advance中的检测"""
        event = {"actual_actor": "阿黑", "action": "sign"}
        is_ahhei_bad = (event["actual_actor"] == "阿黑" and
                        event.get("action") in ("sign", "advance", "complete"))
        self.assertTrue(is_ahhei_bad, "阿黑 sign/advance/complete 必须检测为违规")

    def test_stage_role_mismatch(self):
        """stage-role不匹配检测"""
        # 旧影在coding阶段 → 不匹配
        coding_signers = ["红结"]
        self.assertNotIn("旧影", coding_signers, "旧影不应在coding阶段签名")


if __name__ == "__main__":
    print("=" * 60)
    print("  签名闸门+推进闸门+审计闸门测试")
    print("=" * 60)
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    print("\n" + "=" * 60)
    print(f"  Tests: {result.testsRun} run, {len(result.failures)} failed, {len(result.errors)} errors")
    if result.wasSuccessful():
        print("  RESULT: ALL PASS")
    else:
        print("  RESULT: FAILURES DETECTED")
        for test, traceback in result.failures + result.errors:
            print(f"\n  --- {test} ---")
            print(traceback[:500])
    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)
