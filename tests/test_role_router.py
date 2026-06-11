#!/usr/bin/env python3
"""
test_role_router.py — 全角色协作链路程序化自动测试
"""

import json
import os
import sys
import unittest

# Ensure tools is on path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "tools"))

import role_router  # noqa

CONFIG_PATH = role_router.CONFIG_PATH


class TestRoleRoutingConfig(unittest.TestCase):
    """Test configuration integrity."""

    @classmethod
    def setUpClass(cls):
        cls.config = role_router.load_config()

    def test_default_order(self):
        """comprehensive_analysis 顺序必须为完整六角色链."""
        sc = role_router.get_scenario(self.config, 'comprehensive_analysis')
        expected = ['xinge', 'yuye', 'shanmao', 'qingshan', 'liujin', 'yaozi']
        self.assertEqual(sc['order'], expected,
                         "comprehensive_analysis order incorrect")

    def test_all_role_entries_exist(self):
        """六角色的 entry 和 modules 文件必须全部存在."""
        errors = role_router.check_paths_exist(self.config)
        self.assertEqual(len(errors), 0, f"Path errors: {errors}")

    def test_forbidden_roots_not_in_manifest(self):
        """Manifest 不得包含禁止读取路径."""
        sc = role_router.get_scenario(self.config, 'comprehensive_analysis')
        manifest = role_router.build_read_manifest(self.config, sc['order'])
        errors = role_router.check_forbidden_roots_in_manifest(
            self.config, manifest)
        self.assertEqual(len(errors), 0,
                         f"Forbidden root errors: {errors}")

    def test_yuye_warn_suppresses_buy(self):
        """玉夜WARN + 腰子请求BUY → 最高WATCH，禁止BUY/SELL/ADD_POSITION."""
        rules = self.config.get('suppression_rules', [])
        result = role_router.resolve_final_output(
            rules,
            {'yuye': 'WARN'},
            {},
            'BUY',
        )
        self.assertIn('BUY', result['forbidden_actions'])
        self.assertIn('SELL', result['forbidden_actions'])
        self.assertIn('ADD_POSITION', result['forbidden_actions'])
        self.assertEqual(result['final_output'], 'WATCH')
        self.assertIn('SR-YUYE-WARN', result['applied_rules'])

    def test_yuye_block_blocks_final(self):
        """玉夜BLOCK → final_output BLOCK，禁止强动作."""
        rules = self.config.get('suppression_rules', [])
        result = role_router.resolve_final_output(
            rules,
            {'yuye': 'BLOCK'},
            {},
            'BUY',
        )
        self.assertEqual(result['final_output'], 'BLOCK')
        self.assertIn('BUY', result['forbidden_actions'])
        self.assertIn('SELL', result['forbidden_actions'])
        self.assertIn('SR-YUYE-BLOCK', result['applied_rules'])

    def test_liujin_block_blocks_action(self):
        """流金BLOCK → final_output BLOCK，禁止所有动作."""
        rules = self.config.get('suppression_rules', [])
        result = role_router.resolve_final_output(
            rules,
            {'liujin': 'BLOCK'},
            {},
            'BUY',
        )
        self.assertEqual(result['final_output'], 'BLOCK')
        self.assertIn('BUY', result['forbidden_actions'])
        self.assertIn('SELL', result['forbidden_actions'])
        self.assertIn('ADD_POSITION', result['forbidden_actions'])
        self.assertIn('SR-LIUJIN-BLOCK', result['applied_rules'])

    def test_qingshan_l5_seed_no_action_upgrade(self):
        """青山L5-seed → 禁止ACTION_UPGRADE/BUY/SELL/ADD_POSITION."""
        rules = self.config.get('suppression_rules', [])
        result = role_router.resolve_final_output(
            rules,
            {},
            {'qingshan': ['L5-seed']},
            'BUY',
        )
        self.assertIn('ACTION_UPGRADE', result['forbidden_actions'])
        self.assertIn('BUY', result['forbidden_actions'])
        self.assertIn('SELL', result['forbidden_actions'])
        self.assertIn('ADD_POSITION', result['forbidden_actions'])
        self.assertIn('SR-QINGSHAN-L5-SEED', result['applied_rules'])

    def test_xinge_wait_not_confirmed_fact(self):
        """信鸽WAIT → 禁止CONFIRMED_EVENT/EVENT_AS_FACT."""
        rules = self.config.get('suppression_rules', [])
        result = role_router.resolve_final_output(
            rules,
            {'xinge': 'WAIT'},
            {},
            'CONFIRMED_EVENT',
        )
        self.assertIn('CONFIRMED_EVENT', result['forbidden_actions'])
        self.assertIn('EVENT_AS_FACT', result['forbidden_actions'])
        self.assertIn('SR-XINGE-WAIT', result['applied_rules'])

    def test_shanmao_context_only_not_stock_action(self):
        """山猫MACRO_CONTEXT_ONLY → 禁止STOCK_ACTION_FROM_MACRO_ONLY."""
        rules = self.config.get('suppression_rules', [])
        result = role_router.resolve_final_output(
            rules,
            {},
            {'shanmao': ['MACRO_CONTEXT_ONLY']},
            'WATCH',
        )
        self.assertIn('STOCK_ACTION_FROM_MACRO_ONLY',
                      result['forbidden_actions'])
        self.assertIn('SR-SHANMAO-CONTEXT', result['applied_rules'])

    def test_e2e_virtual_case(self):
        """TEST-E2E-001: 六角色虚拟演练."""
        # fact_missing=false: 期望 WATCH
        result_normal = role_router.simulate_e2e_001(
            self.config, fact_missing=False)
        output = result_normal['output']
        self.assertIn(output['final_output'], ['WATCH', 'INSUFFICIENT_DATA'],
                      f"Expected WATCH/INSUFFICIENT_DATA, got {output['final_output']}")
        self.assertIn('BUY', output['forbidden_actions'])
        self.assertIn('SELL', output['forbidden_actions'])
        self.assertIn('ADD_POSITION', output['forbidden_actions'])
        for rule in ['SR-YUYE-WARN', 'SR-QINGSHAN-L5-SEED',
                     'SR-XINGE-WAIT', 'SR-SHANMAO-CONTEXT']:
            self.assertIn(rule, output['applied_rules'],
                          f"Missing expected rule: {rule}")

        # fact_missing=true: 期望 BLOCK
        result_block = role_router.simulate_e2e_001(
            self.config, fact_missing=True)
        block_output = result_block['output']
        self.assertEqual(block_output['final_output'], 'BLOCK',
                         f"Expected BLOCK when fact_missing=true, got {block_output['final_output']}")
        self.assertIn('SR-LIUJIN-WARN-WITH-FACT-MISSING',
                      block_output['applied_rules'])


class TestRoleRoutingCLI(unittest.TestCase):
    """Test CLI output formats."""

    @classmethod
    def setUpClass(cls):
        cls.config = role_router.load_config()

    def test_list_roles_output(self):
        """list-roles 输出六角色."""
        roles = self.config.get('roles', {})
        self.assertGreaterEqual(len(roles), 6)
        for rid in ['xinge', 'yuye', 'shanmao', 'qingshan', 'liujin', 'yaozi']:
            self.assertIn(rid, roles)

    def test_plan_output_format(self):
        """plan 输出含 read_manifest."""
        sc = role_router.get_scenario(self.config, 'signal_interpretation')
        manifest = role_router.build_read_manifest(self.config, sc['order'])
        self.assertIsInstance(manifest, list)
        self.assertGreaterEqual(len(manifest), 2)
        for entry in manifest:
            self.assertIn('role', entry)
            self.assertIn('files', entry)
            self.assertIsInstance(entry['files'], list)

    def test_suppression_rules_all_have_id(self):
        """所有压制规则必须有 id."""
        rules = self.config.get('suppression_rules', [])
        for rule in rules:
            self.assertIn('id', rule, f"Rule missing id: {rule}")
            self.assertTrue(rule['id'].startswith('SR-'),
                            f"Rule id should start with SR-: {rule['id']}")


if __name__ == '__main__':
    unittest.main()
