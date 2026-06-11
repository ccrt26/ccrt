#!/usr/bin/env python3
"""
role_router.py — 全角色协作链路程序化路由

功能：
  list-roles                     列出所有角色
  plan --scenario <name>         生成 KRM 读取清单
  check --scenario <name>        检查路径完整性和路由规则
  simulate --case <case_id>      虚拟演练（应用压制规则）

用法：
  python3 tools/role_router.py list-roles
  python3 tools/role_router.py plan --scenario comprehensive_analysis
  python3 tools/role_router.py check --scenario comprehensive_analysis
  python3 tools/role_router.py simulate --case TEST-E2E-001
"""

import json
import os
import sys
import glob as glob_module

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "configs", "role_routing.yaml")

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------------
# 最小 YAML 解析（纯 Python，无外部依赖）
# 仅处理 role_routing.yaml 使用的 YAML 子集：顶层 mapping、nested mapping、
# 列表、多行字符串。不做完整 YAML 规范兼容。
# ---------------------------------------------------------------------------
def _minimal_yaml_load(text):
    """Parse the YAML subset used in role_routing.yaml."""
    import re

    # Normalize line endings
    text = text.replace('\r\n', '\n')

    # Remove BOM
    text = text.lstrip('﻿')

    lines = text.split('\n')

    # State: indent stack
    result = {}
    key_path = []
    indent_stack = [-1]  # -1 = root level
    value_stack = [result]
    last_key = [None]
    in_block_string = False
    block_string_lines = []
    block_string_indent = 0
    block_string_key_path = None
    block_string_mode = False  # '|' style

    i = 0
    while i < len(lines):
        line = lines[i]
        raw_line = line
        stripped = line.strip()

        # --- Handle block scalar (| style) ---
        if in_block_string:
            if stripped == '' or (len(line) - len(line.lstrip(' '))) > block_string_indent:
                block_string_lines.append(line)
                i += 1
                continue
            else:
                # End of block string
                in_block_string = False
                # Set value
                _set_nested(value_stack[0], block_string_key_path,
                            '\n'.join(block_string_lines))
                block_string_lines = []
                block_string_key_path = None
                # Fall through to process this line

        # Skip empty lines and comments
        if stripped == '' or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip(' '))

        # Pop indent stack back to appropriate level
        while indent_stack and indent <= indent_stack[-1] and indent_stack[-1] >= 0:
            indent_stack.pop()
            if key_path:
                key_path.pop()
            if value_stack:
                value_stack.pop()
            if last_key:
                last_key.pop()

        indent_stack.append(indent)

        # Detect block scalar (|)
        if stripped.endswith(':|') or stripped.endswith(': |'):
            key_name = stripped.rstrip(':|').rstrip(': ').strip()
            key_path.append(key_name)
            last_key.append(key_name)
            # Create parent object
            parent = value_stack[-1] if value_stack else result
            parent[key_name] = ''
            value_stack.append(parent[key_name])
            block_string_key_path = list(key_path)
            block_string_lines = []
            in_block_string = True
            block_string_indent = indent + 2
            i += 1
            continue

        # List item
        if stripped.startswith('- '):
            item = stripped[2:].strip()
            # Find the list in the parent
            parent = value_stack[-1] if value_stack else result
            list_key = key_path[-1] if key_path else None
            if list_key and list_key in parent:
                if not isinstance(parent[list_key], list):
                    parent[list_key] = []
                if item:
                    parent[list_key].append(item)
                else:
                    # Sub-item list entry
                    parent[list_key].append({})
                    value_stack.append(parent[list_key][-1])
                    key_path.append('__last__')
                    last_key.append('__last__')
            else:
                # Root level list
                if list_key is None:
                    result.setdefault('__root_list__', [])
                    if item:
                        result['__root_list__'].append(item)
            i += 1
            continue

        # Key-value pair
        if ':' in stripped:
            colon_pos = stripped.index(':')
            key_name = stripped[:colon_pos].rstrip()
            value_part = stripped[colon_pos + 1:].strip()

            # Handle nested mapping
            if value_part == '':
                key_path.append(key_name)
                last_key.append(key_name)
                parent = value_stack[-1] if value_stack else result
                if key_name not in parent:
                    parent[key_name] = {}
                value_stack.append(parent[key_name])
            else:
                # Scalar value
                parent = value_stack[-1] if value_stack else result
                # Parse typed values
                parsed = _parse_yaml_scalar(value_part)
                parent[key_name] = parsed
                last_key.append(key_name)
        else:
            # Key on its own line with value on next lines (block style)
            key_name = stripped.rstrip(':')
            key_path.append(key_name)
            last_key.append(key_name)
            parent = value_stack[-1] if value_stack else result
            if key_name not in parent:
                parent[key_name] = {}
            value_stack.append(parent[key_name])

        i += 1

    # Flush block string if still pending
    if in_block_string and block_string_key_path:
        _set_nested(result, block_string_key_path,
                    '\n'.join(block_string_lines))

    # Clean up root_list
    if '__root_list__' in result:
        val = result.pop('__root_list__')
        # Merge into result if only keys and values
        pass

    return result


def _parse_yaml_scalar(val):
    """Parse a YAML scalar value."""
    if val == 'true' or val == 'True':
        return True
    if val == 'false' or val == 'False':
        return False
    if val == 'null' or val == '~':
        return None
    # Try int
    try:
        return int(val)
    except ValueError:
        pass
    # Try float
    try:
        return float(val)
    except ValueError:
        pass
    # Try list
    if val.startswith('[') and val.endswith(']'):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            pass
    return val


def _set_nested(d, path, value):
    """Set a value in nested dict by path list."""
    current = d
    for i, key in enumerate(path):
        if i == len(path) - 1:
            current[key] = value
        else:
            current = current.setdefault(key, {})
    return d


def _strip_value(val):
    """Strip whitespace from a parsed YAML value."""
    if isinstance(val, str):
        return val.strip()
    return val


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def load_config(path=None):
    """Load role_routing config, supporting YAML or minimal fallback."""
    p = path or CONFIG_PATH
    if not os.path.exists(p):
        # Try .json fallback
        json_path = p.replace('.yaml', '.json')
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        raise FileNotFoundError(f"Config not found: {p}")

    with open(p, 'r', encoding='utf-8') as f:
        raw = f.read()

    if _HAS_YAML:
        try:
            return yaml.safe_load(raw)
        except Exception:
            pass

    # Minimal fallback
    return _minimal_yaml_load(raw)


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------
def get_role_ids(config):
    """Return list of role IDs."""
    return list(config.get('roles', {}).keys())


def get_scenario(config, name):
    """Get scenario by name."""
    scenarios = config.get('scenarios', {})
    if name not in scenarios:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(scenarios.keys())}")
    return scenarios[name]


def build_read_manifest(config, scenario_order):
    """Build KRM reading manifest for given role order."""
    roles = config.get('roles', {})
    manifest = []
    for role_id in scenario_order:
        if role_id not in roles:
            continue
        role_info = roles[role_id]
        files = [role_info['entry']]
        for mod_key in ['duties', 'evidence', 'signal', 'degradation',
                        'framework', 'output']:
            if mod_key in role_info.get('modules', {}):
                files.append(role_info['modules'][mod_key])
        manifest.append({
            'role': role_id,
            'name': role_info['name'],
            'layer': role_info['layer'],
            'files': files,
        })
    return manifest


def check_paths_exist(config):
    """Check all registered role entries and module files exist."""
    errors = []
    roles = config.get('roles', {})
    for rid, rinfo in roles.items():
        entry = rinfo.get('entry', '')
        if not os.path.exists(entry):
            errors.append(f"MISSING entry [{rid}]: {entry}")
        for mkey, mpath in rinfo.get('modules', {}).items():
            if not os.path.exists(mpath):
                errors.append(f"MISSING module [{rid}.{mkey}]: {mpath}")
    return errors


def check_scenario_routes(config, sc_name, sc_config):
    """Verify a scenario's route is valid."""
    errors = []
    roles = config.get('roles', {})
    for rid in sc_config.get('order', []):
        if rid not in roles:
            errors.append(f"Scenario '{sc_name}' references unknown role: {rid}")
    for rid in sc_config.get('required_roles', []):
        if rid not in sc_config.get('order', []):
            errors.append(
                f"Scenario '{sc_name}': required role '{rid}' not in order")
    return errors


def check_default_order(config):
    """Verify default_order roles all exist."""
    errors = []
    roles = config.get('roles', {})
    for rid in config.get('default_order', []):
        if rid not in roles:
            errors.append(f"default_order references unknown role: {rid}")
    expected = ['xinge', 'yuye', 'shanmao', 'qingshan', 'liujin', 'yaozi']
    actual = config.get('default_order', [])
    if actual != expected:
        errors.append(
            f"default_order mismatch: expected {expected}, got {actual}")
    return errors


def check_forbidden_roots_in_manifest(config, manifest):
    """Verify read_manifest doesn't use forbidden roots."""
    errors = []
    forbidden = config.get('forbidden_read_roots', [])
    for entry in manifest:
        for fp in entry.get('files', []):
            for root in forbidden:
                # Convert glob-like patterns
                pattern = root.replace('*', '')
                if pattern in fp:
                    errors.append(
                        f"Forbidden root match: '{fp}' contains '{root}'")
    return errors


def resolve_final_output(suppression_rules, role_statuses, role_flags,
                         requested_output):
    """Apply suppression rules and determine final output."""
    forbidden_actions = set()
    applied_rules = []
    final_output_max = None  # 'BLOCK' > 'WATCH' > ...; BLOCK is highest

    output_rank = {
        'BLOCK': 5,
        'RISK_BLOCK': 5,
        'DATA_BLOCK': 5,
        'WATCH': 4,
        'INSUFFICIENT_DATA': 4,
        'RISK_WARN': 3,
        'DATA_WARN': 3,
        'WARN': 3,
        'MACRO_CONTEXT_ONLY': 2,
        'DATA_OK': 1,
        'RISK_PASS': 1,
        'REFERENCE_ONLY': 1,
    }

    for rule in suppression_rules:
        rid = rule.get('id', '')
        target = rule.get('if_role', '')
        status_in = rule.get('if_status_in', [])
        flags_include = rule.get('if_flags_include', [])
        effect = rule.get('effect', {})

        # Check if role has matching status or flags
        status = role_statuses.get(target)
        flags = role_flags.get(target, [])

        match = False
        if status_in and status in status_in:
            match = True
        if flags_include:
            for flag in flags_include:
                if flag in flags:
                    match = True

        if not match:
            continue

        applied_rules.append(rid)

        # Forbid actions
        for action in effect.get('forbid', []):
            forbidden_actions.add(action)

        # Adjust final_output_max
        max_out = effect.get('final_output_max', '')
        if max_out:
            rank = output_rank.get(max_out, 0)
            current_rank = output_rank.get(final_output_max, 0)
            if rank > current_rank:
                final_output_max = max_out

    # Determine final output
    if final_output_max:
        final_output = final_output_max
        # Also check if requested_output rank is higher than allowed
        req_rank = output_rank.get(requested_output, 0)
        max_rank = output_rank.get(final_output_max, 0)
        if req_rank > max_rank:
            final_output = final_output_max
    else:
        # No suppression, use requested output if allowed
        final_output = requested_output or 'INSUFFICIENT_DATA'

    # Re-check: if forbidden actions include key financial actions,
    # force INSUFFICIENT_DATA
    key_forbidden = {'BUY', 'SELL', 'ADD_POSITION'}
    if key_forbidden & forbidden_actions:
        if final_output not in ('BLOCK', 'INSUFFICIENT_DATA', 'WATCH'):
            final_output = 'WATCH'

    return {
        'final_output': final_output,
        'forbidden_actions': sorted(forbidden_actions),
        'applied_rules': sorted(applied_rules),
    }


# ---------------------------------------------------------------------------
# 虚拟演练（TEST-E2E-001 内置）
# ---------------------------------------------------------------------------
def simulate_e2e_001(config, fact_missing=False):
    """Run the TEST-E2E-001 virtual case."""
    role_statuses = {
        'xinge': 'WAIT',
        'yuye': 'WARN',
        'shanmao': None,
        'qingshan': None,
        'liujin': 'WARN' if not fact_missing else None,
    }
    role_flags = {
        'xinge': [],
        'yuye': [],
        'shanmao': ['MACRO_CONTEXT_ONLY'],
        'qingshan': ['L5-seed'],
        'liujin': ['fact_missing'] if fact_missing else [],
    }
    requested_output = 'BUY'

    rules = config.get('suppression_rules', [])
    result = resolve_final_output(rules, role_statuses, role_flags,
                                  requested_output)

    # Build detail
    expected_rules = ['SR-YUYE-WARN', 'SR-QINGSHAN-L5-SEED',
                      'SR-XINGE-WAIT', 'SR-SHANMAO-CONTEXT']
    if fact_missing:
        expected_rules.append('SR-LIUJIN-WARN-WITH-FACT-MISSING')

    status_detail = {}
    for rid, s in role_statuses.items():
        info = {'status': s}
        if rid in role_flags and role_flags[rid]:
            info['flags'] = role_flags[rid]
        status_detail[rid] = info

    return {
        'case': 'TEST-E2E-001',
        'fact_missing': fact_missing,
        'input': {
            'role_statuses': role_statuses,
            'role_flags': role_flags,
            'requested_output': requested_output,
        },
        'output': result,
        'expected_rules': sorted(expected_rules),
        'expected_forbidden': sorted([
            'BUY', 'SELL', 'ADD_POSITION',
            'ACTION_UPGRADE', 'CONFIRMED_EVENT', 'EVENT_AS_FACT',
            'STOCK_ACTION_FROM_MACRO_ONLY',
        ] + (['REDUCE_POSITION_STRONG'] if fact_missing else [])),
    }


# ---------------------------------------------------------------------------
# CLI 接口
# ---------------------------------------------------------------------------
def cmd_list_roles(config):
    """list-roles: 列出所有角色."""
    roles = config.get('roles', {})
    default_order = config.get('default_order', [])
    print(f"{'ID':<12} {'名称':<8} {'层':<22} {'入口':<50}")
    print("-" * 92)
    for rid in default_order:
        if rid in roles:
            r = roles[rid]
            print(f"{rid:<12} {r['name']:<8} {r['layer']:<22} {r['entry']:<50}")
    # Also print any roles not in default order
    for rid, r in roles.items():
        if rid not in default_order:
            print(f"{rid:<12} {r['name']:<8} {r['layer']:<22} {r['entry']:<50}")


def cmd_plan(config, scenario_name):
    """plan: 生成 KRM 读取清单."""
    sc = get_scenario(config, scenario_name)
    manifest = build_read_manifest(config, sc['order'])
    forbidden = config.get('forbidden_read_roots', [])
    result = {
        'scenario': scenario_name,
        'order': sc['order'],
        'read_manifest': manifest,
        'forbidden_read_roots': forbidden,
        'config_version': config.get('version'),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_check(config, scenario_name):
    """check: 检查路径完整性和路由规则."""
    errors = []
    warnings = []

    # 1. Check all paths
    path_errors = check_paths_exist(config)
    errors.extend(path_errors)

    # 2. Check scenario
    try:
        sc = get_scenario(config, scenario_name)
        sc_errors = check_scenario_routes(config, scenario_name, sc)
        errors.extend(sc_errors)
    except ValueError as e:
        errors.append(str(e))
        sc = None

    # 3. Check default order
    order_errors = check_default_order(config)
    errors.extend(order_errors)

    # 4. Check forbidden roots not in manifest
    if sc:
        manifest = build_read_manifest(config, sc['order'])
        root_errors = check_forbidden_roots_in_manifest(config, manifest)
        errors.extend(root_errors)

    # 5. Special: comprehensive_analysis order must be exact
    if scenario_name == 'comprehensive_analysis' and sc:
        expected = ['xinge', 'yuye', 'shanmao', 'qingshan', 'liujin', 'yaozi']
        if sc.get('order') != expected:
            errors.append(
                f"comprehensive_analysis order must be {expected}, "
                f"got {sc.get('order')}")

    verdict = 'PASS' if not errors else 'FAIL'
    result = {
        'scenario': scenario_name,
        'verdict': verdict,
        'errors': errors,
        'warnings': warnings,
        'total_errors': len(errors),
        'total_warnings': len(warnings),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_simulate(config, case_id):
    """simulate: 运行虚拟演练."""
    if case_id == 'TEST-E2E-001':
        result_normal = simulate_e2e_001(config, fact_missing=False)
        print("=== TEST-E2E-001 (fact_missing=false) ===")
        print(json.dumps(result_normal, ensure_ascii=False, indent=2))

        result_block = simulate_e2e_001(config, fact_missing=True)
        print("\n=== TEST-E2E-001 (fact_missing=true) ===")
        print(json.dumps(result_block, ensure_ascii=False, indent=2))
    else:
        print(f"Unknown case: {case_id}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    config = load_config()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == 'list-roles':
        cmd_list_roles(config)

    elif command == 'plan':
        scenario = _parse_arg('--scenario')
        if not scenario:
            print("Usage: plan --scenario <name>")
            sys.exit(1)
        cmd_plan(config, scenario)

    elif command == 'check':
        scenario = _parse_arg('--scenario')
        if not scenario:
            print("Usage: check --scenario <name>")
            sys.exit(1)
        cmd_check(config, scenario)

    elif command == 'simulate':
        case = _parse_arg('--case')
        if not case:
            print("Usage: simulate --case <case_id>")
            sys.exit(1)
        cmd_simulate(config, case)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


def _parse_arg(name):
    """Parse --key value from sys.argv."""
    for i, arg in enumerate(sys.argv):
        if arg == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


if __name__ == '__main__':
    main()
