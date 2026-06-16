"""Test that orchestrator preflight BLOCK produces structured evidence (no UnboundLocalError)."""

import json
import subprocess
import sys
import tempfile
import unittest
from json import JSONDecoder
from pathlib import Path


# Prepend the langgraph-orchestrator module path to sys.path so we can import
ORCHESTRATOR_DIR = Path(__file__).resolve().parents[1] / "代码文件" / "tools"
sys.path.insert(0, str(ORCHESTRATOR_DIR))
ROOT = Path(__file__).resolve().parents[1]

# Minimal langgraph stub for environments where langgraph is not installed
try:
    from ccrt_langgraph_orchestrator import g3_g4_execution, utc_now, write_json
except ImportError:
    g3_g4_execution = None
    utc_now = None
    write_json = None


@unittest.skipIf(g3_g4_execution is None, "ccrt_langgraph_orchestrator not importable")
class TestOrchestratorPreflightBlock(unittest.TestCase):
    """Preflight BLOCK evidence tests — import-based (requires langgraph)."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(dir="/private/tmp"))

    def test_preflight_block_produces_structured_evidence(self):
        """When preflight status is BLOCK, g3_g4_execution must return
        structured G4 evidence without crashing (UnboundLocalError regression)."""
        state = {
            "task_id": "TST-PREFLIGHT-BLOCK",
            "mode": "dry_run",
            "output_dir": str(self.tmpdir),
            "config": {
                "runtime": {"python": sys.executable},
                "orchestration_tools": {},
                "stage_gate_tools": {},
                "terminal_streaming": {},
            },
            "precise_requirement": {"goal": "test preflight block"},
            "g0_route": {},
            "role_design": {
                "materialized_role_outputs": [],
                "role_outputs_required_for_g3": False,
            },
            "preflight": {
                "status": "BLOCK",
                "reason": "role_boundary: Codex assigned to G3; Codex must not execute G3/G4",
            },
            "hygiene_preflight": {
                "status": "BLOCK",
                "reason": "hygiene_check_failed",
            },
        }

        # This should NOT raise UnboundLocalError
        result = g3_g4_execution(state)

        g3_g4 = result.get("g3_g4", {})
        self.assertIn("evidence", g3_g4, "g3_g4 must contain evidence key")
        evidence = g3_g4["evidence"]
        self.assertEqual(evidence.get("result"), "BLOCK")
        self.assertTrue(evidence.get("preflight_blocked"))
        self.assertIn("preflight_reason", evidence)
        self.assertIsInstance(evidence.get("changed_files"), list)
        self.assertIsInstance(evidence.get("commands"), list)
        self.assertIsInstance(evidence.get("tool_calls"), list)
        self.assertEqual(evidence.get("artifact_type"), "candidate")

    def test_preflight_hygiene_block_only(self):
        """When only hygiene blocks, evidence is still structured."""
        state = {
            "task_id": "TST-HYGIENE-BLOCK",
            "mode": "dry_run",
            "output_dir": str(self.tmpdir),
            "config": {
                "runtime": {"python": sys.executable},
                "orchestration_tools": {},
                "stage_gate_tools": {},
                "terminal_streaming": {},
            },
            "precise_requirement": {"goal": "test hygiene block"},
            "g0_route": {},
            "role_design": {
                "materialized_role_outputs": [],
                "role_outputs_required_for_g3": False,
            },
            "preflight": {"status": "PASS", "reason": "ok"},
            "hygiene_preflight": {
                "status": "BLOCK",
                "reason": "dirty_workspace",
                "blockers": ["uncommitted_changes"],
            },
        }

        result = g3_g4_execution(state)
        g3_g4 = result.get("g3_g4", {})
        evidence = g3_g4.get("evidence", {})
        self.assertEqual(evidence.get("result"), "BLOCK")
        self.assertTrue(evidence.get("preflight_blocked"))


def _parse_last_json(text):
    """Extract the last valid JSON object from orchestrator stdout (NDJSON stream + final JSON)."""
    decoder = JSONDecoder()
    last_valid = None
    pos = 0
    while pos < len(text):
        try:
            obj, end = decoder.raw_decode(text, pos)
            last_valid = obj
            pos = end
            while pos < len(text) and text[pos] in ' \t\n\r':
                pos += 1
        except json.JSONDecodeError:
            break
    return last_valid


class TestOrchestratorDryRunNoCrash(unittest.TestCase):
    """Standalone dry_run test — does NOT require langgraph import.

    Runs the orchestrator via subprocess and verifies parseable JSON evidence.
    Orchestrator returns exit code 2 when stage gate returns BLOCK (correct
    stage-gate semantics), so assertions must not require returncode == 0.
    """

    ORCHESTRATOR_DIR = Path(__file__).resolve().parents[1] / "代码文件" / "tools"
    ROOT = Path(__file__).resolve().parents[1]

    def test_orchestrator_dry_run_produces_parseable_evidence(self):
        """Full orchestrator dry_run: verify stdout has parseable JSON evidence fields."""
        proc = subprocess.run([
            sys.executable,
            str(self.ORCHESTRATOR_DIR / "ccrt_langgraph_orchestrator.py"),
            "--mode", "dry_run",
            "--json",
        ], cwd=str(self.ROOT), capture_output=True, text=True, timeout=120)
        self.assertTrue(proc.stdout.strip(),
                        f"orchestrator produced no stdout; stderr={proc.stderr[:500]}")
        state = _parse_last_json(proc.stdout)
        self.assertIsNotNone(state, f"no valid JSON found in orchestrator output; stderr={proc.stderr[:500]}")
        self.assertIn("run_record", state, "state must contain run_record path")
        g3_g4 = state.get("g3_g4", {})
        evidence = g3_g4.get("evidence", {})
        self.assertIn("artifact_type", evidence)
        self.assertIn("result", evidence)
        self.assertIn("changed_files", evidence)
        self.assertIn("commands", evidence)
        self.assertIn("tool_calls", evidence)
        self.assertIsInstance(evidence.get("changed_files"), list)
        self.assertIsInstance(evidence.get("commands"), list)


if __name__ == "__main__":
    unittest.main()
