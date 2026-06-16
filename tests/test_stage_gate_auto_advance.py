import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestStageGateAutoAdvance(unittest.TestCase):
    def run_py(self, args, env=None, expect_code=0):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        proc = subprocess.run(
            [sys.executable] + args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=merged_env,
            timeout=60,
        )
        self.assertEqual(
            proc.returncode,
            expect_code,
            proc.stdout + proc.stderr,
        )
        return proc

    def test_stage_gate_registry_invariants(self):
        registry = json.loads(
            (ROOT / "00_项目地基/05_流程与角色/stage_gate_registry.json").read_text(encoding="utf-8")
        )

        artifacts = {item["type"]: item for item in registry["artifact_types"]}
        self.assertFalse(artifacts["candidate"]["formal"])
        self.assertTrue(artifacts["formal_signoff"]["formal"])
        self.assertTrue(artifacts["archive_record"]["formal"])

        rules = {rule["rule_id"]: rule for rule in registry["advance_rules"]}
        self.assertFalse(rules["ADV-G4-G5-CANDIDATE-PASS"]["formal_signoff_required"])
        self.assertEqual(rules["ADV-G5-G6-FORMAL-PASS"]["required_role"], "旧影")
        self.assertEqual(rules["ADV-G6-ARCHIVE-FORMAL-PASS"]["required_role"], "腰子")

        repairs = {rule["issue"]: rule for rule in registry["repair_rules"]}
        for issue in [
            "missing_evidence",
            "BLOCK_in_G5_review",
            "missing_hmac",
            "permission_missing",
            "role_substitution",
            "candidate_claims_formal_signoff",
        ]:
            self.assertFalse(repairs[issue]["user_escalation"], issue)
        self.assertTrue(repairs["scope_expansion"]["user_escalation"])
        self.assertTrue(repairs["production_action_without_user_confirmation"]["user_escalation"])

    def test_runtime_entries_registered(self):
        registry = json.loads(
            (ROOT / "00_项目地基/06_调度与运行/runtime_entry_registry.json").read_text(encoding="utf-8")
        )
        entries = {item.get("entry"): item for item in registry.get("entries", [])}

        stage_entry = entries["stage_gate_auto_advance.py"]
        self.assertEqual(stage_entry["authority"], "stage_gate_auto_advance")
        self.assertEqual(stage_entry["path"], "scripts/stage_gate_auto_advance.py")
        self.assertEqual(stage_entry["status"], "active")
        self.assertTrue((ROOT / stage_entry["path"]).exists())

        archive_entry = entries["archive_after_g6.py"]
        self.assertEqual(archive_entry["authority"], "g6_archive_dry_run_entry")
        self.assertEqual(archive_entry["path"], "scripts/archive_after_g6.py")
        self.assertEqual(archive_entry["status"], "active_dry_run")
        self.assertTrue((ROOT / archive_entry["path"]).exists())

    def test_stage_gate_auto_advance_behaviors(self):
        self.run_py(["scripts/stage_gate_auto_advance.py", "--self-test"])

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)

            g4 = td_path / "g4.json"
            g4.write_text(json.dumps({
                "task_id": "UT-G4",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
            }), encoding="utf-8")

            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(g4)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "G4 without actual_actor/changed_files should repair")
            self.assertIn("missing_implementation_evidence", data["issues"])

            wrong_role = td_path / "g5_wrong_role.json"
            wrong_role.write_text(json.dumps({
                "task_id": "UT-G5-WRONG",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "阿黑", "signed": True},
            }, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(wrong_role)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED")
            self.assertEqual(data["dispatch_action"], "invalidate_artifact_and_request_correct_role_resign")
            self.assertEqual(data["dispatch"]["required_role"], "旧影")
            self.assertEqual(data["dispatch"]["required_artifact_type"], "formal_signoff")
            self.assertEqual(data["writes"], [])

            actor_mismatch = td_path / "g5_actor_mismatch.json"
            actor_mismatch.write_text(json.dumps({
                "task_id": "UT-G5-ACTOR-MISMATCH",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {
                    "role": "旧影",
                    "signed": True,
                    "sig_type": "HMAC-SHA256",
                    "actual_actor": "阿黑"
                },
            }, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(actor_mismatch)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED")
            self.assertIn("actual_actor_role_mismatch", data["issues"])
            self.assertEqual(data["dispatch"]["required_role"], "旧影")
            self.assertEqual(data["dispatch"]["required_artifact_type"], "formal_signoff")
            self.assertFalse(data["user_escalation"])

            missing_actor = td_path / "g5_missing_actual_actor.json"
            missing_actor.write_text(json.dumps({
                "task_id": "UT-G5-MISSING-ACTOR",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {
                    "role": "旧影",
                    "signed": True,
                    "sig_type": "HMAC-SHA256",
                    "actual_actor": ""
                },
            }, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(missing_actor)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "WAITING_FORMAL_SIGNOFF")
            self.assertIn("missing_actual_actor", data["issues"])
            self.assertEqual(data["dispatch"]["required_role"], "旧影")
            self.assertEqual(data["dispatch"]["required_artifact_type"], "formal_signoff")
            self.assertFalse(data["user_escalation"])

            out_dir = td_path / "dispatch"
            g4_with_evidence = td_path / "g4_with_evidence.json"
            g4_with_evidence.write_text(json.dumps({
                "task_id": "UT-G4-DISPATCH",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "actual_actor": "deepseek_live",
                "execution_model": "deepseek-via-claude-code",
                "implementation_actor": "deepseek_live",
                "live_model_call": True,
                "codex_write_detected": False,
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
                "tool_calls": [{"name": "terminal_stream_adapter", "mode": "mock", "returncode": 0}],
            }), encoding="utf-8")
            proc = self.run_py([
                "scripts/stage_gate_auto_advance.py",
                "--evidence", str(g4_with_evidence),
                "--write-dispatch",
                "--output-dir", str(out_dir),
            ])
            data = json.loads(proc.stdout)
            self.assertFalse(data["dry_run"])
            self.assertEqual(len(data["writes"]), 1)

            dispatch_file = Path(data["writes"][0])
            payload = json.loads(dispatch_file.read_text(encoding="utf-8"))
            dispatch = payload["dispatch"]
            self.assertTrue(dispatch["candidate_only"])
            self.assertTrue(dispatch["no_role_signoff_claimed"])
            self.assertNotIn('"archive_completed": true', dispatch_file.read_text(encoding="utf-8"))

    def test_archive_after_g6_behaviors_and_path_guard(self):
        self.run_py(["scripts/archive_after_g6.py", "--self-test"])

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)

            ready = td_path / "g6_ready.json"
            ready.write_text(json.dumps({
                "task_id": "UT-G6-READY",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "sig_type": "HMAC-SHA256", "actual_actor": "腰子"},
                "requested_actions": [],
            }, ensure_ascii=False), encoding="utf-8")

            proc = self.run_py(["scripts/archive_after_g6.py", "--evidence", str(ready)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "ARCHIVE_READY_DRY_RUN")
            self.assertTrue(data["dry_run"])
            self.assertEqual(data["writes"], [])
            self.assertFalse(data["would_tag"])
            self.assertFalse(data["would_push"])

            missing_hmac = td_path / "g6_missing_hmac.json"
            missing_hmac.write_text(json.dumps({
                "task_id": "UT-G6-MISSING-HMAC",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "actual_actor": "腰子"},
                "requested_actions": [],
            }, ensure_ascii=False), encoding="utf-8")
            proc = self.run_py(["scripts/archive_after_g6.py", "--evidence", str(missing_hmac)])
            self.assertEqual(json.loads(proc.stdout)["status"], "WAITING_FORMAL_SIGNOFF")

            wrong_role = td_path / "g6_wrong_role.json"
            wrong_role.write_text(json.dumps({
                "task_id": "UT-G6-WRONG",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "阿黑", "signed": True, "sig_type": "HMAC-SHA256"},
                "requested_actions": [],
            }, ensure_ascii=False), encoding="utf-8")
            proc = self.run_py(["scripts/archive_after_g6.py", "--evidence", str(wrong_role)])
            self.assertEqual(json.loads(proc.stdout)["status"], "REPAIR_DISPATCH_REQUIRED")

            out_dir = Path("/private/tmp") / "ccrt_archive_after_g6_unittest"
            out_dir.mkdir(parents=True, exist_ok=True)
            for path in out_dir.glob("*.json"):
                path.unlink()

            proc = self.run_py([
                "scripts/archive_after_g6.py",
                "--evidence", str(ready),
                "--write-task",
                "--output-dir", str(out_dir),
            ])
            data = json.loads(proc.stdout)
            self.assertFalse(data["dry_run"])
            self.assertEqual(len(data["writes"]), 1)

            task_file = Path(data["writes"][0])
            payload = json.loads(task_file.read_text(encoding="utf-8"))
            task = payload["archive_task"]
            self.assertTrue(task["candidate_only"])
            self.assertTrue(task["no_role_signoff_claimed"])
            self.assertTrue(task["archive_not_executed"])

            for forbidden_dir in [
                "00_项目地基/08_审计与验收",
                str(ROOT / "00_项目地基/08_审计与验收"),
                "tmp/relative_archive_output",
            ]:
                proc = self.run_py([
                    "scripts/archive_after_g6.py",
                    "--evidence", str(ready),
                    "--write-task",
                    "--output-dir", forbidden_dir,
                ], expect_code=2)
                self.assertIn("BLOCK: unsafe output directory", proc.stderr)

    def test_auto_advance_logging_from_scripts(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
            td_path = Path(td)
            log_dir = td_path / "logs"

            g4 = td_path / "g4_log.json"
            g4.write_text(json.dumps({
                "task_id": "UT-G4-LOG",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "actual_actor": "deepseek_live",
                "execution_model": "deepseek-via-claude-code",
                "implementation_actor": "deepseek_live",
                "live_model_call": True,
                "codex_write_detected": False,
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
                "tool_calls": [{"name": "terminal_stream_adapter", "mode": "mock", "returncode": 0}],
            }), encoding="utf-8")

            self.run_py(
                ["scripts/stage_gate_auto_advance.py", "--evidence", str(g4)],
                env={"PIPELINE_LOG_DIR": str(log_dir)},
            )

            g6 = td_path / "g6_log.json"
            g6.write_text(json.dumps({
                "task_id": "UT-G6-LOG",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "sig_type": "HMAC-SHA256", "actual_actor": "腰子"},
                "requested_actions": [],
            }, ensure_ascii=False), encoding="utf-8")

            self.run_py(
                ["scripts/archive_after_g6.py", "--evidence", str(g6)],
                env={"PIPELINE_LOG_DIR": str(log_dir)},
            )

            log_path = log_dir / "engine" / "auto_advance_events.jsonl"
            self.assertTrue(log_path.exists())
            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            task_ids = {record["task_id"] for record in records}
            self.assertIn("UT-G4-LOG", task_ids)
            self.assertIn("UT-G6-LOG", task_ids)

            for record in records:
                self.assertEqual(record.get("writes"), [])
                self.assertIn(record.get("source_script"), {
                    "scripts/stage_gate_auto_advance.py",
                    "scripts/archive_after_g6.py",
                })

    def test_g4_role_boundary_validation(self):
        """Verify G4 role boundary validation: codex → REPAIR, deepseek → ADVANCE."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)

            # Case 1: implementation_actor=codex → REPAIR
            codex_evidence = td_path / "g4_codex.json"
            codex_evidence.write_text(json.dumps({
                "task_id": "UT-CODEX-G4",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex",
                "actual_actor": "codex",
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_evidence)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED")
            self.assertIn("codex_implementation_detected", data["issues"])
            self.assertEqual(data["dispatch_action"], "invalidate_implementation_and_request_deepseek_rerun")

            # Case 2: codex_write_detected=True → REPAIR
            codex_write = td_path / "g4_codex_write.json"
            codex_write.write_text(json.dumps({
                "task_id": "UT-CODEX-WRITE",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "codex_write_detected": True,
                "actual_actor": "deepseek_live",
                "changed_files": ["test.py"],
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_write)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED")
            self.assertIn("codex_implementation_detected", data["issues"])

            # Case 3: missing actual_actor and changed_files → REPAIR
            missing_evidence = td_path / "g4_missing.json"
            missing_evidence.write_text(json.dumps({
                "task_id": "UT-MISSING-G4",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(missing_evidence)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED")
            self.assertIn("missing_implementation_evidence", data["issues"])

            # Case 4: codex with self-filled g3_impl_allowed_by_user but NO env var → REPAIR
            override_evidence = td_path / "g4_override.json"
            override_evidence.write_text(json.dumps({
                "task_id": "UT-OVERRIDE-G4",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex",
                "actual_actor": "codex",
                "g3_impl_allowed_by_user": True,
                "changed_files": ["test.py"],
                "tool_calls": [{"name": "Read", "count": 2}],
                "live_model_call": True,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(override_evidence)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "self-filled g3_impl_allowed_by_user without env var should not suppress codex detection")
            self.assertIn("codex_implementation_detected", data["issues"])

            # Case 5: deepseek_live full evidence → ADVANCE_READY
            deepseek_evidence = td_path / "g4_deepseek.json"
            deepseek_evidence.write_text(json.dumps({
                "task_id": "UT-DEEPSEEK-G4",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "actual_actor": "deepseek_live",
                "execution_model": "deepseek-via-claude-code",
                "implementation_actor": "deepseek_live",
                "live_model_call": True,
                "codex_write_detected": False,
                "changed_files": ["test.py"],
                "tool_calls": [{"name": "Read", "count": 2}, {"name": "Edit", "count": 1}],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(deepseek_evidence)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "ADVANCE_READY", f"deepseek evidence should advance: {data}")
            self.assertEqual(data["to_gate"], "G5")
            self.assertEqual(data["issues"], [])

            # Case 6: "Codex" capitalized → REPAIR (case-insensitive)
            codex_cap = td_path / "g4_codex_cap.json"
            codex_cap.write_text(json.dumps({
                "task_id": "UT-CODEX-CAP",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "Codex",
                "actual_actor": "deepseek_live",
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_cap)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "'Codex' capitalized should trigger codex_implementation_detected")
            self.assertIn("codex_implementation_detected", data["issues"])

            # Case 7: "CODEX" all caps → REPAIR (case-insensitive)
            codex_uc = td_path / "g4_codex_uc.json"
            codex_uc.write_text(json.dumps({
                "task_id": "UT-CODEX-UC",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "CODEX",
                "actual_actor": "deepseek_live",
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_uc)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "'CODEX' all caps should trigger codex_implementation_detected")
            self.assertIn("codex_implementation_detected", data["issues"])

            # Case 8: "codex_app" variant → REPAIR
            codex_app = td_path / "g4_codex_app.json"
            codex_app.write_text(json.dumps({
                "task_id": "UT-CODEX-APP",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex_app",
                "actual_actor": "deepseek_live",
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_app)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "'codex_app' variant should trigger codex_implementation_detected")
            self.assertIn("codex_implementation_detected", data["issues"])

            # Case 9: "codex-agent" variant → REPAIR
            codex_agent = td_path / "g4_codex_agent.json"
            codex_agent.write_text(json.dumps({
                "task_id": "UT-CODEX-AGENT",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex-agent",
                "actual_actor": "deepseek_live",
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_agent)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "'codex-agent' variant should trigger codex_implementation_detected")
            self.assertIn("codex_implementation_detected", data["issues"])

            # Case 10: codex with actual env var G3_IMPL_ALLOWED_BY_USER=true → ADVANCE_READY
            env_override = td_path / "g4_env_override.json"
            env_override.write_text(json.dumps({
                "task_id": "UT-ENV-OVERRIDE",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex",
                "actual_actor": "codex",
                "g3_impl_allowed_by_user": False,
                "changed_files": ["test.py"],
                "tool_calls": [{"name": "Read", "count": 2}],
                "live_model_call": True,
            }), encoding="utf-8")
            proc = self.run_py(
                ["scripts/stage_gate_auto_advance.py", "--evidence", str(env_override)],
                env={"G3_IMPL_ALLOWED_BY_USER": "true"},
            )
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "ADVANCE_READY",
                             "codex with env G3_IMPL_ALLOWED_BY_USER=true should advance")
            self.assertNotIn("codex_implementation_detected", data["issues"])

            # Case 11: actual_actor="CodexAgent" → REPAIR (variant via actual_actor field)
            codex_agent_actual = td_path / "g4_codex_agent_actual.json"
            codex_agent_actual.write_text(json.dumps({
                "task_id": "UT-CODEX-AGENT-ACTUAL",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "deepseek_live",
                "actual_actor": "CodexAgent",
                "changed_files": ["test.py"],
                "g3_impl_allowed_by_user": False,
            }), encoding="utf-8")
            proc = self.run_py(["scripts/stage_gate_auto_advance.py", "--evidence", str(codex_agent_actual)])
            data = json.loads(proc.stdout)
            self.assertEqual(data["status"], "REPAIR_DISPATCH_REQUIRED",
                             "actual_actor='CodexAgent' should trigger codex_implementation_detected")
            self.assertIn("codex_implementation_detected", data["issues"])

    def test_runtime_entry_authority_gate_passes(self):
        proc = self.run_py(["scripts/check_runtime_entry_authority.py", "--all", "--json"])
        data = json.loads(proc.stdout)
        self.assertEqual(data["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
