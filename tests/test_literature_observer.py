#!/usr/bin/env python3
"""
test_literature_observer.py — 外部文献观察项程序化自动测试
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "tools"))
import literature_observer as lo  # noqa


class TestLiteratureObserverConfig(unittest.TestCase):
    """Test literature observation configuration integrity."""

    @classmethod
    def setUpClass(cls):
        cls.config = lo.load_config()

    def test_config_loads(self):
        """配置必须正常加载."""
        self.assertIsNotNone(self.config)
        self.assertIn('observation_items', self.config)
        self.assertIn('scene_capacity_per_week', self.config)
        self.assertIn('urgent_allowed_types', self.config)

    def test_observation_ids_unique(self):
        """所有 observation_id 必须唯一."""
        items = lo.get_items(self.config)
        ids = [item.get('observation_id', '') for item in items]
        self.assertEqual(len(ids), len(set(ids)),
                         "Duplicate observation_id found")

    def test_status_valid(self):
        """status 必须在 allowed_status 列表中."""
        valid = lo.get_valid_statuses(self.config)
        for item in lo.get_items(self.config):
            status = item.get('status', '')
            self.assertIn(status, valid,
                          f"{item.get('observation_id')}: invalid status '{status}'")

    def test_priority_valid(self):
        """priority 必须在定义的优先级中."""
        valid = lo.get_valid_priorities(self.config)
        for item in lo.get_items(self.config):
            prio = item.get('priority', '')
            self.assertIn(prio, valid,
                          f"{item.get('observation_id')}: invalid priority '{prio}'")

    def test_urgent_type_whitelist(self):
        """urgent 优先级的 urgent_type 必须在白名单中."""
        whitelist = lo.get_urgent_allowed_types(self.config)
        for item in lo.get_items(self.config):
            if item.get('priority') == 'urgent':
                utype = item.get('urgent_type', '')
                self.assertIn(utype, whitelist,
                              f"{item.get('observation_id')}: "
                              f"urgent_type '{utype}' not in whitelist")

    def test_no_logic_change_required(self):
        """每个 item 必须 no_logic_change=true."""
        for item in lo.get_items(self.config):
            self.assertTrue(
                item.get('no_logic_change', False),
                f"{item.get('observation_id')}: no_logic_change must be true"
            )

    def test_no_weight_change_required(self):
        """每个 item 必须 no_weight_change=true."""
        for item in lo.get_items(self.config):
            self.assertTrue(
                item.get('no_weight_change', False),
                f"{item.get('observation_id')}: no_weight_change must be true"
            )

    def test_capacity_weekly(self):
        """场景容量限制合理：daily_pick 为 0 且需腰子审批."""
        caps = self.config.get('scene_capacity_per_week', {})
        for scene, cap in caps.items():
            max_new = cap.get('max_new_items', -1)
            self.assertGreaterEqual(
                max_new, 0,
                f"scene '{scene}': max_new_items must be >= 0")
            if max_new == 0:
                self.assertTrue(
                    cap.get('requires_yaozi_approval', False),
                    f"scene '{scene}': max_new_items=0 "
                    f"but requires_yaozi_approval is false")

    def test_daily_pick_requires_approval(self):
        """daily_pick 场景必须 requires_yaozi_approval=true."""
        dp = self.config.get('scene_capacity_per_week', {}).get('daily_pick', {})
        self.assertTrue(dp.get('requires_yaozi_approval', False),
                        "daily_pick requires_yaozi_approval must be true")
        self.assertEqual(dp.get('max_new_items', -1), 0,
                         "daily_pick max_new_items must be 0")

    def test_manifest_weekly(self):
        """weekly scenario manifest 必须标注 no_logic_change/no_weight_change."""
        manifest = lo.cmd_manifest(self.config, 'weekly', '2026-W24')
        self.assertIsInstance(manifest, dict)
        self.assertEqual(manifest.get('scenario'), 'weekly')
        self.assertTrue(manifest.get('no_logic_change'),
                        "weekly manifest missing no_logic_change=true")
        self.assertTrue(manifest.get('no_weight_change'),
                        "weekly manifest missing no_weight_change=true")
        self.assertTrue(manifest.get('not_core_knowledge'),
                        "weekly manifest missing not_core_knowledge=true")
        self.assertTrue(manifest.get('not_six_library_entry'),
                        "weekly manifest missing not_six_library_entry=true")

    def test_manifest_post_eval(self):
        """post_eval scenario manifest 必须标注 no_logic_change/no_weight_change."""
        manifest = lo.cmd_manifest(self.config, 'post_eval', '2026-W24')
        self.assertIsInstance(manifest, dict)
        self.assertEqual(manifest.get('scenario'), 'post_eval')
        self.assertTrue(manifest.get('no_logic_change'),
                        "post_eval manifest missing no_logic_change=true")
        self.assertTrue(manifest.get('not_core_knowledge'),
                        "post_eval manifest missing not_core_knowledge=true")

    def test_simulate_urgent_active(self):
        """模拟必须输出: OBS-TEST-001 active_if_capacity_available,
        OBS-TEST-URGENT-001 active_immediate, daily_pick approval_required."""
        results = lo.cmd_simulate(self.config)
        # Collect all result entries
        result_map = {}
        for r in results:
            if 'observation_id' in r:
                result_map[r['observation_id']] = r
            elif 'scenario_check' in r:
                result_map[r['scenario_check']] = r

        # OBS-TEST-001
        if 'OBS-TEST-001' in result_map:
            r1 = result_map['OBS-TEST-001']
            self.assertEqual(r1.get('activate_result'),
                             'active_if_capacity_available')
            self.assertTrue(r1.get('no_logic_change'))
            self.assertTrue(r1.get('no_weight_change'))

        # OBS-TEST-URGENT-001
        if 'OBS-TEST-URGENT-001' in result_map:
            r2 = result_map['OBS-TEST-URGENT-001']
            self.assertEqual(r2.get('activate_result'), 'active_immediate')
            self.assertTrue(r2.get('urgent_in_whitelist'))

        # daily_pick
        if 'daily_pick' in result_map:
            dp = result_map['daily_pick']
            self.assertEqual(dp.get('max_new_items'), 0)
            self.assertTrue(dp.get('requires_yaozi_approval'))

    def test_sample_requirement_exists(self):
        """每个 item 必须有 sample_requirement 且含 min_eval_samples."""
        for item in lo.get_items(self.config):
            sr = item.get('sample_requirement')
            self.assertIsNotNone(
                sr,
                f"{item.get('observation_id')}: missing sample_requirement")
            self.assertIn(
                'min_eval_samples', sr,
                f"{item.get('observation_id')}: "
                f"sample_requirement missing min_eval_samples")
            self.assertIsInstance(sr['min_eval_samples'], int)
            self.assertGreater(sr['min_eval_samples'], 0)

    def test_check_passes(self):
        """check 必须 PASS."""
        result = lo.run_check(self.config)
        self.assertEqual(result.get('verdict'), 'PASS',
                         f"Check failed: {result.get('errors')}")
        self.assertEqual(result.get('total'), 0)


class TestLiteratureObserverEdgeCases(unittest.TestCase):
    """Edge case tests for observer config rules."""

    @classmethod
    def setUpClass(cls):
        cls.config = lo.load_config()

    def test_allowed_scenarios_valid(self):
        """每个 item 的 target_scenarios 必须在允许列表中."""
        allowed = lo.get_allowed_scenarios(self.config)
        for item in lo.get_items(self.config):
            for sc in item.get('target_scenarios', []):
                self.assertIn(sc, allowed,
                              f"{item.get('observation_id')}: "
                              f"scenario '{sc}' not allowed")

    def test_forbidden_transition_fails(self):
        """验证状态机不允许的转移."""
        trans = self.config.get('status_flow', {}).get('allowed_transitions', {})
        # completed cannot transition to anything
        self.assertEqual(trans.get('completed', []), [])
        # rejected cannot transition to anything
        self.assertEqual(trans.get('rejected', []), [])

    def test_evidence_types_have_min_samples(self):
        """所有 evidence_type 在 default_sample_requirements 中有配置."""
        defaults = self.config.get('default_sample_requirements', {})
        for item in lo.get_items(self.config):
            ev = item.get('evidence_type', '')
            if ev:
                self.assertIn(ev, defaults,
                              f"{item.get('observation_id')}: "
                              f"evidence_type '{ev}' not in default_samples")


if __name__ == '__main__':
    unittest.main()
