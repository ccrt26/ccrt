import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestStageGateReleaseOrchestrator(unittest.TestCase):
    def run_py(self, args, env=None, expect_code=0):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        proc = subprocess.run(
            [sys.executable] + args,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            env=merged,
            timeout=60,
        )
        self.assertEqual(proc.returncode, expect_code, proc.stdout + proc.stderr)
        return proc

    def run_py_internal(self, args, env=None, expect_code=0):
        """Run with --internal-json to get full response for assertions."""
        return self.run_py(args + ["--internal-json"], env=env, expect_code=expect_code)

    def test_self_test(self):
        proc = self.run_py(["scripts/stage_gate_release_orchestrator.py", "--self-test"])
        self.assertEqual(json.loads(proc.stdout)["self_test"], "PASS")

    def test_default_stdout_is_minimal_user_package(self):
        """Default stdout must only have user_visible_status/message and internal_evidence_record."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            checklist = Path(td) / "checklist.json"
            state = Path(td) / "state.json"
            checklist.write_text(json.dumps({"run_id": "UT-STDOUT", "signoffs": {}}), encoding="utf-8")
            state.write_text(json.dumps({"runs": {"UT-STDOUT": {"current_stage": "audit"}}}), encoding="utf-8")

            proc = self.run_py([
                "scripts/stage_gate_release_orchestrator.py",
                "--mode", "signoff",
                "--run-id", "UT-STDOUT",
                "--gate", "G5",
                "--checklist", str(checklist),
                "--state-file", str(state),
                "--output-dir", td,
            ])
            data = json.loads(proc.stdout)

            # Must have user fields
            self.assertIn("user_visible_status", data)
            self.assertIn("user_visible_message", data)
            self.assertIn("internal_evidence_record", data)

            # Must NOT have internal fields
            forbidden = ["forbidden_claims", "dispatch_action", "required_role",
                         "candidate_only", "no_role_signoff_claimed"]
            for f in forbidden:
                self.assertNotIn(f, proc.stdout, f"stdout leaked internal field: {f}")

            # Internal evidence file must exist and contain the full data
            internal_path = Path(data["internal_evidence_record"])
            self.assertTrue(internal_path.exists())
            internal_data = json.loads(internal_path.read_text(encoding="utf-8"))
            self.assertIn("forbidden_claims", json.dumps(internal_data))

    def test_internal_json_flag_shows_full_response(self):
        """With --internal-json, stdout should include full internal fields."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            checklist = Path(td) / "checklist.json"
            state = Path(td) / "state.json"
            checklist.write_text(json.dumps({"run_id": "UT-INTJSON", "signoffs": {}}), encoding="utf-8")
            state.write_text(json.dumps({"runs": {"UT-INTJSON": {"current_stage": "audit"}}}), encoding="utf-8")

            proc = self.run_py([
                "scripts/stage_gate_release_orchestrator.py",
                "--mode", "signoff",
                "--run-id", "UT-INTJSON",
                "--gate", "G5",
                "--checklist", str(checklist),
                "--state-file", str(state),
                "--output-dir", td,
                "--internal-json",
            ])
            data = json.loads(proc.stdout)

            # Must still have user fields
            self.assertIn("user_visible_status", data)
            self.assertIn("user_visible_message", data)
            self.assertTrue(data.get("internal_stage_evidence_hidden_from_user"))

            # Internal fields allowed
            stdout_text = proc.stdout
            self.assertIn("user_visible_status", stdout_text)

    def test_policy_file_invariants(self):
        policy = json.loads((ROOT / "00_项目地基/05_流程与角色/stage_gate_release_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["default_policy"], "archive_and_github_sync")
        gsync = policy["policies"]["archive_and_github_sync"]
        self.assertTrue(gsync["auto_archive"])
        self.assertTrue(gsync["auto_github_sync"])
        self.assertTrue(gsync["auto_commit"])
        self.assertTrue(gsync["auto_push"])
        self.assertFalse(gsync["auto_tag"])
        self.assertFalse(gsync["auto_merge"])
        self.assertEqual(policy["role_signoff"]["G5"]["role"], "旧影")
        self.assertEqual(policy["role_signoff"]["G6"]["role"], "腰子")

    def test_missing_actor_creates_role_dispatch_not_user_escalation(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            checklist = Path(td) / "checklist.json"
            state = Path(td) / "state.json"
            checklist.write_text(json.dumps({"run_id": "UT-ORCH", "signoffs": {}}, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({"runs": {"UT-ORCH": {"current_stage": "audit"}}}, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py_internal([
                "scripts/stage_gate_release_orchestrator.py",
                "--mode", "signoff",
                "--run-id", "UT-ORCH",
                "--gate", "G5",
                "--checklist", str(checklist),
                "--state-file", str(state),
                "--output-dir", td,
            ])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "WAITING_ROLE_SIGNOFF")
            self.assertEqual(data["required_role"], "旧影")
            self.assertFalse(data["user_escalation"])

    def test_archive_with_audit_only_policy(self):
        """audit_archive_only should archive but skip github sync, return ARCHIVED."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            g6 = Path(td) / "g6_signoff.json"
            g6.write_text(json.dumps({
                "task_id": "UT-ORCH",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "PASS",
                "formal_signoff": {
                    "role": "腰子",
                    "actual_actor": "腰子",
                    "sig_type": "HMAC-SHA256",
                    "signed": True,
                }
            }, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py_internal([
                "scripts/stage_gate_release_orchestrator.py",
                "--mode", "archive",
                "--run-id", "UT-ORCH",
                "--g6-signoff", str(g6),
                "--release-policy", "audit_archive_only",
                "--output-dir", td,
            ])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "ARCHIVED")
            self.assertTrue(data["archive_completed"])

            record = json.loads(Path(data["archive_record"]).read_text(encoding="utf-8"))
            self.assertEqual(record["artifact_type"], "archive_record")
            self.assertEqual(record["result"], "CLOSED")
            self.assertFalse(record["tag_completed"])
            self.assertFalse(record["merge_completed"])

    def test_default_policy_archive_creates_valid_record(self):
        """archive_and_github_sync policy: archive step produces valid CLOSED record.

        Note: full G6_COMPLETE requires github sync to succeed against the real project,
        which depends on external git state. This test verifies the archive record itself
        is valid (CLOSED) before the github sync step.
        """
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            g6 = Path(td) / "g6_signoff.json"
            g6.write_text(json.dumps({
                "task_id": "UT-ORCH-ARC",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "PASS",
                "formal_signoff": {
                    "role": "腰子",
                    "actual_actor": "腰子",
                    "sig_type": "HMAC-SHA256",
                    "signed": True,
                }
            }, ensure_ascii=False), encoding="utf-8")

            import scripts.stage_gate_release_orchestrator as orch

            class MockArgs:
                run_id = "UT-ORCH-ARC"
                release_policy = "archive_and_github_sync"
                user_confirmed_release = False
                output_dir = td
                mode = "archive"
                g6_signoff = str(g6)
                gate = None
                checklist = None
                state_file = None
                comment = ""
                internal_json = True

            args = MockArgs()
            output_context = orch.prepare_output_context(args.output_dir, args.run_id)
            _, record = orch.make_archive_record(
                args.run_id,
                Path(args.g6_signoff),
                output_context,
                args.release_policy,
                orch.load_policy(args.release_policy)[1],
            )
            self.assertEqual(record.get("result"), "CLOSED")
            self.assertTrue(record.get("archive_completed"))
            self.assertIn("g6_formal_signoff", record)

    def test_bad_g6_evidence_never_archives(self):
        bad_cases = {
            "missing_formal_signoff": {
                "task_id": "UT-BAD",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "PASS",
            },
            "wrong_actor": {
                "task_id": "UT-BAD",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "PASS",
                "formal_signoff": {
                    "role": "腰子",
                    "actual_actor": "阿黑",
                    "sig_type": "HMAC-SHA256",
                    "signed": True,
                }
            },
            "wrong_gate": {
                "task_id": "UT-BAD",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "PASS",
                "formal_signoff": {
                    "role": "腰子",
                    "actual_actor": "腰子",
                    "sig_type": "HMAC-SHA256",
                    "signed": True,
                }
            },
            "block_result": {
                "task_id": "UT-BAD",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "BLOCK",
                "formal_signoff": {
                    "role": "腰子",
                    "actual_actor": "腰子",
                    "sig_type": "HMAC-SHA256",
                    "signed": True,
                }
            },
        }

        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            for name, payload in bad_cases.items():
                g6 = Path(td) / f"{name}.json"
                g6.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                proc = self.run_py_internal([
                    "scripts/stage_gate_release_orchestrator.py",
                    "--mode", "archive",
                    "--run-id", "UT-BAD",
                    "--g6-signoff", str(g6),
                    "--output-dir", td,
                ], expect_code=2)
                data = json.loads(proc.stdout)
                self.assertEqual(data["status"], "BLOCK", name)
                self.assertFalse(data["archive_completed"], name)
                self.assertFalse(data["push_completed"], name)

    def test_unsafe_output_dir_blocks(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            g6 = Path(td) / "g6_signoff.json"
            g6.write_text(json.dumps({
                "task_id": "UT-ORCH",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "role": "腰子",
                "result": "PASS",
                "formal_signoff": {
                    "role": "腰子",
                    "actual_actor": "腰子",
                    "sig_type": "HMAC-SHA256",
                    "signed": True,
                }
            }, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py_internal([
                "scripts/stage_gate_release_orchestrator.py",
                "--mode", "archive",
                "--run-id", "UT-ORCH",
                "--g6-signoff", str(g6),
                "--output-dir", "relative_output",
            ], expect_code=2)
            self.assertEqual(json.loads(proc.stdout)["status"], "BLOCK")

    def test_unsafe_output_dir_does_not_write_requested_dir(self):
        """Unsafe --output-dir must not create the requested dir; internal evidence goes to tmp fallback."""
        # Ensure relative_output does not exist beforehand
        rel_dir = Path("relative_output")
        if rel_dir.exists():
            for f in rel_dir.glob("*"):
                f.unlink()
            rel_dir.rmdir()

        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            checklist = Path(td) / "cl.json"
            state = Path(td) / "st.json"
            checklist.write_text('{"run_id":"UT-REL","signoffs":{}}')
            state.write_text('{"runs":{"UT-REL":{"current_stage":"audit"}}}')

            proc = self.run_py([
                "scripts/stage_gate_release_orchestrator.py",
                "--mode", "signoff",
                "--run-id", "UT-REL",
                "--gate", "G5",
                "--checklist", str(checklist),
                "--state-file", str(state),
                "--output-dir", "relative_output",
            ], expect_code=2)
            data = json.loads(proc.stdout)
            stdout_text = proc.stdout

            # Must return BLOCK
            self.assertIn("user_visible_status", data)
            self.assertEqual(data["user_visible_status"], "BLOCK")

            # relative_output must NOT exist
            self.assertFalse(Path("relative_output").exists(), "relative_output must not be created")

            # Default stdout must not leak internal fields
            for forbidden in ["forbidden_claims", "dispatch_action", "required_role",
                              "candidate_only", "archive_not_executed"]:
                self.assertNotIn(forbidden, stdout_text, f"stdout leaked: {forbidden}")

            # Must have internal_evidence_record pointing to fallback
            self.assertIn("internal_evidence_record", data)
            internal_path = Path(data["internal_evidence_record"])
            self.assertTrue(internal_path.exists(), f"internal evidence missing: {internal_path}")
            self.assertIn("/private/tmp/ccrt_release_orchestrator_blocked/", str(internal_path))


    def test_check_g6_workspace_hygiene_blocks_on_dirty(self):
        """check_g6_workspace_hygiene must return BLOCK when hygiene check fails."""
        import scripts.stage_gate_release_orchestrator as orch
        from unittest.mock import patch

        # Simulate dirty workspace by mocking run_cmd
        original_run_cmd = orch.run_cmd

        def mock_dirty_run_cmd(cmd, env=None):
            cmd_str = " ".join(cmd)
            if "git_workspace_hygiene.py" in cmd_str and "--quiet" in cmd_str:
                return {"returncode": 2, "stdout": "BLOCK: dirty", "stderr": "", "cmd": cmd}
            return original_run_cmd(cmd, env=env)

        with patch.object(orch, 'run_cmd', side_effect=mock_dirty_run_cmd):
            result = orch.check_g6_workspace_hygiene()
            self.assertIsNotNone(result)
            self.assertEqual(result.get("status"), orch.STATUS_BLOCK)
            self.assertIn("not clean", result.get("reason", ""))

    def test_check_g6_workspace_hygiene_skips_with_env_var(self):
        """check_g6_workspace_hygiene must return None when skip env var is set."""
        import scripts.stage_gate_release_orchestrator as orch
        import os

        os.environ[orch.G6_HYGIENE_SKIP_VAR] = "true"
        try:
            result = orch.check_g6_workspace_hygiene()
            self.assertIsNone(result)
        finally:
            del os.environ[orch.G6_HYGIENE_SKIP_VAR]

    def test_check_g6_workspace_hygiene_passes_on_clean(self):
        """check_g6_workspace_hygiene must return None when hygiene check passes."""
        import scripts.stage_gate_release_orchestrator as orch
        from unittest.mock import patch

        original_run_cmd = orch.run_cmd

        def mock_clean_run_cmd(cmd, env=None):
            cmd_str = " ".join(cmd)
            if "git_workspace_hygiene.py" in cmd_str and "--quiet" in cmd_str:
                return {"returncode": 0, "stdout": "PASS", "stderr": "", "cmd": cmd}
            return original_run_cmd(cmd, env=env)

        with patch.object(orch, 'run_cmd', side_effect=mock_clean_run_cmd):
            result = orch.check_g6_workspace_hygiene()
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
