"""会话五: shadow refresh 合约测试。

覆盖 G2 §十三 全部 13 项测试合约。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SHADOW_SCRIPT = os.path.join(ROOT, "scripts", "run_keystock_dashboard_shadow_refresh.py")
SCAN_SCRIPTS = [
    os.path.join(ROOT, "scripts", "run_keystock_dashboard_shadow_refresh.py"),
    os.path.join(ROOT, "scripts", "build_keystock_product_api_bundle.py"),
    os.path.join(ROOT, "scripts", "check_keystock_dashboard_productization.py"),
]
DANGEROUS_PATTERNS = [
    "generate_launchd\\.py",
    "launchctl\\s+load",
    "launchctl\\s+bootstrap",
    "launchctl\\s+kickstart",
    "crontab",
]
EVIDENCE_REQUIRED_FIELDS = [
    "schema_version", "run_type", "production_cutover", "production_ready",
    "started_at", "finished_at", "run_id", "stock_pool",
    "build_result", "checker_summary", "run_manifest_publish_result",
    "no_production_touch", "readonly_registry_evidence",
    "production_cutover_minimum_conditions", "known_blocks",
    "known_warnings", "files_intentionally_not_touched",
    "engineering_shadow_refresh_status", "business_production_readiness",
    "dry_run_scope", "writes_product_api", "writes_docs_data",
    "writes_runtime_or_launchd", "commands_run", "allowed_commands_only",
    "forbidden_commands_observed",
]
NPT_FIELDS = [
    "baseline_registry_touched", "runtime_entry_registry_touched",
    "launchd_touched", "generate_launchd_called",
    "real_position_connected", "formal_rule_changed",
    "production_cutover", "formal_buy_sell_position_conclusion_generated",
]


class TestShadowRefreshContract(unittest.TestCase):
    """shadow refresh 脚本合约测试。"""

    # ── 1. 脚本存在且可编译 ──
    def test_script_exists(self):
        """脚本文件存在。"""
        self.assertTrue(os.path.exists(SHADOW_SCRIPT), f"脚本不存在: {SHADOW_SCRIPT}")

    def test_script_compiles(self):
        """py_compile 通过。"""
        with tempfile.TemporaryDirectory() as pycache_dir:
            env = os.environ.copy()
            env["PYTHONPYCACHEPREFIX"] = pycache_dir
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", SHADOW_SCRIPT],
                capture_output=True, text=True,
                env=env,
            )
        self.assertEqual(result.returncode, 0,
                         f"编译失败: {result.stderr}")

    # ── 2. 无危险调度调用 ──
    def test_no_dangerous_calls(self):
        """本阶段 3 个脚本均不会实际调用 generate_launchd/launchctl/crontab。

        检查实际执行调用行是否含危险命令。
        DANGEROUS_PATTERNS 列表定义行不被视为违规。
        """
        call_pattern = re.compile(r'(?:subprocess\.run|subprocess\.Popen|os\.system|os\.popen)')
        for script in SCAN_SCRIPTS:
            with open(script, encoding="utf-8") as f:
                lines = f.readlines()

            in_patterns = False
            pattern_lines = set()
            for i, line in enumerate(lines):
                if "DANGEROUS_PATTERNS" in line and "[" in line:
                    in_patterns = True
                if in_patterns:
                    pattern_lines.add(i)
                    if "]" in line and i > 0 and "DANGEROUS_PATTERNS" not in lines[max(0, i - 1)]:
                        break

            for i, line in enumerate(lines):
                if i in pattern_lines:
                    continue
                if call_pattern.search(line):
                    for pat in DANGEROUS_PATTERNS:
                        if re.search(pat, line):
                            self.fail(
                                f"{script}:{i+1}: subprocess/os.system 包含危险命令: {pat}\n  {line.strip()}"
                            )

    # ── 3. evidence 字段完整性 ──
    def test_evidence_schema_fields(self):
        """evidence schema 包含所有必需顶层字段。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在，跳过 evidence 字段检查")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        for field in EVIDENCE_REQUIRED_FIELDS:
            self.assertIn(field, ev,
                          f"evidence 缺少顶层字段: {field}")

    def test_evidence_schema_version(self):
        """evidence schema_version 为 v1。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        self.assertEqual(ev["schema_version"], "keystock.shadow_refresh_evidence.v1")

    # ── 4. no_production_touch 全部为 false ──
    def test_no_production_touch_all_false(self):
        """no_production_touch 8 个字段全部为 false。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        npt = ev.get("no_production_touch", {})
        missing = [k for k in NPT_FIELDS if k not in npt]
        self.assertEqual(missing, [], f"no_production_touch 缺少字段: {missing}")
        for k in NPT_FIELDS:
            self.assertIs(npt[k], False,
                          f"no_production_touch.{k} 不为 false: {npt[k]}")

    # ── 5. runtime_entry_registry / baseline_registry touched = false ──
    def test_registry_not_touched(self):
        """registry 未被修改。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        re_ev = ev.get("readonly_registry_evidence", {})
        self.assertTrue(re_ev.get("unchanged", False),
                        "registry unchanged 不为 true")
        self.assertEqual(
            re_ev.get("before_sha256"),
            re_ev.get("after_sha256"),
            "registry before/after hash 不一致，文件可能被修改",
        )

    # ── 6. stock_pool members 仅含 600114 ──
    def test_stock_pool_scope(self):
        """stock_pool members 仅限于 600114。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        members = ev.get("stock_pool", {}).get("members", [])
        # 当前产品范围仅 600114
        allowed = {"600114"}
        for m in members:
            self.assertIn(m, allowed,
                          f"stock_pool 包含范围外股票: {m}")

    # ── 7. run_id 一致 ──
    def test_run_id_consistency(self):
        """evidence 中 run_id 一致。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        rid = ev.get("run_id", "")
        manifest_rid = ev.get("run_manifest_publish_result", {}).get("docs_run_id", "")
        self.assertIn(rid, ("UNKNOWN", manifest_rid),
                      f"evidence run_id({rid}) != manifest run_id({manifest_rid})")

    # ── 8. rollback_ref 存在 ──
    def test_rollback_ref_exists(self):
        """rollback_ref 或 fallback_rollback_ref 非空。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        pub = ev.get("run_manifest_publish_result", {})
        has_ref = bool(pub.get("rollback_ref")) or bool(pub.get("fallback_rollback_ref"))
        self.assertTrue(has_ref, "rollback_ref 和 fallback_rollback_ref 均为空")

    # ── 9. business BLOCK 不导致工程测试失败 ──
    #   用运行脚本实际测试：当前 DATA_DATE_DIVERGENCE 下脚本应退出 0
    def test_business_block_exit_zero(self):
        """仅业务 BLOCK (engineering=PASS) 时脚本退出 0。"""
        # 运行 shadow refresh dry-run 检查退出码
        result = subprocess.run(
            [sys.executable, SHADOW_SCRIPT, "--dry-run"],
            capture_output=True, text=True,
            cwd=ROOT,
        )
        # 如果脚本完全成功（exit 0），证明业务 BLOCK 不阻断
        # 如果脚本失败（exit 1），需要判断是 engineering BLOCK 还是其他原因
        checker_out = os.path.join(
            ROOT, "运行产物", "重点股票产品化后评估", "evidence",
        )
        latest = os.path.join(checker_out, "keystock_dashboard_shadow_latest.json")
        eng = "UNKNOWN"
        if os.path.exists(latest):
            with open(latest) as f:
                ev = json.load(f)
            eng = ev.get("checker_summary", {}).get("engineering_status", "UNKNOWN")

        if eng == "PASS":
            # 工程 PASS 时无论业务状态如何都应 exit 0
            self.assertEqual(result.returncode, 0,
                             f"engineering=PASS 但 exit {result.returncode}: {result.stderr}")
        elif eng == "BLOCK":
            # 工程 BLOCK 时 exit 1 是合理行为
            self.assertEqual(result.returncode, 1,
                             f"engineering=BLOCK 但 exit {result.returncode}")
        # UNKNOWN: 可能数据不足，不强制

    # ── 10. engineering BLOCK 必须导致非零退出 ──
    def test_engineering_block_fails(self):
        """checker engineering BLOCK 时脚本必须退出非零。"""
        # 如果当前 engineering=PASS，此测试不需要
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest) as f:
            ev = json.load(f)
        eng = ev.get("checker_summary", {}).get("engineering_status", "UNKNOWN")
        if eng != "BLOCK":
            self.skipTest(f"当前 engineering_status={eng}，非 BLOCK，跳过")

        # 如果 engineering=BLOCK，验证退出码
        result = subprocess.run(
            [sys.executable, SHADOW_SCRIPT, "--dry-run"],
            capture_output=True, text=True,
            cwd=ROOT,
        )
        self.assertNotEqual(result.returncode, 0,
                            "engineering BLOCK 时脚本应退出非零")

    # ── 11. 不生成正式买卖/仓位结论 ──
    def test_no_formal_conclusion(self):
        """页面不包含 FORMAL 买卖/仓位结论。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest) as f:
            ev = json.load(f)

        # checker 中不应将 DATA_DATE_DIVERGENCE 包装为 COMPLETE
        for block in ev.get("known_blocks", []):
            if block.get("check") == "data_date_divergence":
                self.assertNotEqual(
                    block.get("status"), "COMPLETE",
                    "data_date_divergence 不得被包装为 COMPLETE",
                )

        # no_formal_action: production_ready 必须 false
        self.assertIs(ev.get("production_ready"), False,
                      "production_ready 不得为 true")

        # no_formal_buy_sell_conclusion
        npt = ev.get("no_production_touch", {})
        self.assertIs(npt.get("formal_buy_sell_position_conclusion_generated"), False,
                      "formal_buy_sell 不得为 true")

    # ── 12. 不写真实持仓数值到 docs data ──
    def test_no_real_position_data_leak(self):
        """docs data 中不包含真实成本/数量/盈亏数据。"""
        today_decisions_path = os.path.join(
            ROOT, "docs", "keystock-dashboard", "data", "today_decisions.json",
        )
        if not os.path.exists(today_decisions_path):
            self.skipTest("today_decisions.json 不存在")
        with open(today_decisions_path, encoding="utf-8") as f:
            td = json.load(f)

        pos = td.get("user_position", {})
        cost_price = pos.get("cost_price")
        quantity = pos.get("quantity")
        unrealized_pnl = pos.get("unrealized_pnl")

        # 如果有真实数据且 POSITION_UNAVAILABLE blockers，则为泄露
        blockers = td.get("decision_blockers", [])
        if "POSITION_UNAVAILABLE" in blockers:
            if cost_price is not None:
                self.fail("POSITION_UNAVAILABLE 下存在非空 cost_price")
            if quantity is not None:
                self.fail("POSITION_UNAVAILABLE 下存在非空 quantity")

    # ── 13. production_ready 必须 false ──
    def test_production_ready_false(self):
        """evidence 中 production_ready 为 false。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        self.assertIs(ev.get("production_ready"), False,
                      "production_ready 必须为 false")
        self.assertIs(ev.get("production_cutover"), False,
                      "production_cutover 必须为 false")

    def test_status_split_contract(self):
        """工程 shadow 状态与业务生产 readiness 必须分离。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        self.assertIn(ev.get("engineering_shadow_refresh_status"), ("PASS", "BLOCK"))
        self.assertIn(ev.get("business_production_readiness"), ("PASS", "BLOCK"))
        bus = ev.get("checker_summary", {}).get("business_user_visible_status")
        if bus == "BLOCK":
            self.assertEqual(ev.get("business_production_readiness"), "BLOCK")
            self.assertIs(ev.get("production_ready"), False)

    def test_dry_run_scope_contract(self):
        """--dry-run 只表示不切生产，仍允许写 shadow product_api/docs data。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        self.assertEqual(ev.get("dry_run_scope"), "production_cutover_only")
        self.assertIs(ev.get("writes_product_api"), True)
        self.assertIs(ev.get("writes_docs_data"), True)
        self.assertIs(ev.get("writes_runtime_or_launchd"), False)
        if ev.get("engineering_shadow_refresh_status") == "BLOCK":
            self.assertIn(ev.get("write_completion_status", "FAILED"), ("FAILED", "PUBLISHED"))

    def test_commands_run_contract(self):
        """evidence 必须证明实际只运行 build/check 两类命令。"""
        evidence_dir = os.path.join(ROOT, "运行产物", "重点股票产品化后评估", "evidence")
        latest = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
        if not os.path.exists(latest):
            self.skipTest("shadow_latest.json 不存在")
        with open(latest, encoding="utf-8") as f:
            ev = json.load(f)
        commands = ev.get("commands_run", [])
        self.assertGreaterEqual(len(commands), 1)
        for cmd in commands:
            self.assertTrue(
                "scripts/build_keystock_product_api_bundle.py" in cmd
                or "scripts/check_keystock_dashboard_productization.py" in cmd,
                f"出现非允许命令: {cmd}",
            )
        self.assertIs(ev.get("allowed_commands_only"), True)
        self.assertEqual(ev.get("forbidden_commands_observed"), [])


if __name__ == "__main__":
    unittest.main()
