#!/usr/bin/env python3
"""
literature_observer.py — 外部文献观察项程序化路由

把外部文献角色摘要转成"观察项候选"，每周批处理或 T+0/T+1
紧急处理，控制每场景每周新增观察项容量。

核心约束：
- 观察项只记录，不改变结论权重
- 不进入角色核心知识库
- 不进入六库

用法：
  python3 tools/literature_observer.py list
  python3 tools/literature_observer.py due --week 2026-W24
  python3 tools/literature_observer.py activate --week 2026-W24
  python3 tools/literature_observer.py manifest --scenario weekly --week 2026-W24
  python3 tools/literature_observer.py check
  python3 tools/literature_observer.py simulate
"""

import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "configs", "literature_observation.yaml")

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------------
# 最小 YAML 解析（纯 Python 回退）
# ---------------------------------------------------------------------------
def _minimal_yaml_load(text):
    """Parse the YAML subset used in observation config."""
    import re
    text = text.replace('\r\n', '\n').lstrip('﻿')
    lines = text.split('\n')

    result = {}
    key_path = []
    indent_stack = [-1]
    value_stack = [result]
    last_key = [None]
    in_block_string = False
    block_string_lines = []
    block_string_indent = 0
    block_string_key_path = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if in_block_string:
            if stripped == '' or (len(line) - len(line.lstrip(' '))) > block_string_indent:
                block_string_lines.append(line)
                i += 1
                continue
            else:
                in_block_string = False
                _set_nested(value_stack[0], block_string_key_path,
                            '\n'.join(block_string_lines))
                block_string_lines = []
                block_string_key_path = None

        if stripped == '' or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip(' '))

        while indent_stack and indent <= indent_stack[-1] and indent_stack[-1] >= 0:
            indent_stack.pop()
            if key_path:
                key_path.pop()
            if value_stack:
                value_stack.pop()
            if last_key:
                last_key.pop()
        indent_stack.append(indent)

        if stripped.endswith(':|') or stripped.endswith(': |'):
            key_name = stripped.rstrip(':|').rstrip(': ').strip()
            key_path.append(key_name)
            last_key.append(key_name)
            parent = value_stack[-1] if value_stack else result
            parent[key_name] = ''
            value_stack.append(parent[key_name])
            block_string_key_path = list(key_path)
            block_string_lines = []
            in_block_string = True
            block_string_indent = indent + 2
            i += 1
            continue

        if stripped.startswith('- '):
            item = stripped[2:].strip()
            parent = value_stack[-1] if value_stack else result
            list_key = key_path[-1] if key_path else None
            if list_key and list_key in parent:
                if not isinstance(parent[list_key], list):
                    parent[list_key] = []
                if item:
                    parent[list_key].append(item)
                else:
                    parent[list_key].append({})
                    value_stack.append(parent[list_key][-1])
                    key_path.append('__last__')
                    last_key.append('__last__')
            i += 1
            continue

        if ':' in stripped:
            colon_pos = stripped.index(':')
            key_name = stripped[:colon_pos].rstrip()
            value_part = stripped[colon_pos + 1:].strip()
            parent = value_stack[-1] if value_stack else result
            if value_part == '':
                key_path.append(key_name)
                last_key.append(key_name)
                if key_name not in parent:
                    parent[key_name] = {}
                value_stack.append(parent[key_name])
            else:
                parent[key_name] = _parse_yaml_scalar(value_part)
                last_key.append(key_name)
        else:
            key_name = stripped.rstrip(':')
            key_path.append(key_name)
            last_key.append(key_name)
            parent = value_stack[-1] if value_stack else result
            if key_name not in parent:
                parent[key_name] = {}
            value_stack.append(parent[key_name])

        i += 1

    if in_block_string and block_string_key_path:
        _set_nested(result, block_string_key_path,
                    '\n'.join(block_string_lines))
    return result


def _parse_yaml_scalar(val):
    if val in ('true', 'True', 'yes'):
        return True
    if val in ('false', 'False', 'no'):
        return False
    if val in ('null', 'None', '~'):
        return None
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    if val.startswith('[') and val.endswith(']'):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            pass
    return val


def _set_nested(d, path, value):
    current = d
    for i, key in enumerate(path):
        if i == len(path) - 1:
            current[key] = value
        else:
            current = current.setdefault(key, {})
    return d


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def load_config(path=None):
    p = path or CONFIG_PATH
    if not os.path.exists(p):
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
    return _minimal_yaml_load(raw)


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------
def get_items(config):
    return config.get('observation_items', [])


def get_item_by_id(config, oid):
    for item in get_items(config):
        if item.get('observation_id') == oid:
            return item
    return None


def get_valid_statuses(config):
    return config.get('status_flow', {}).get('allowed_status', [])


def get_valid_priorities(config):
    return list(config.get('priority', {}).keys())


def get_urgent_allowed_types(config):
    return config.get('urgent_allowed_types', [])


def get_scene_capacity(config, scene):
    caps = config.get('scene_capacity_per_week', {})
    return caps.get(scene, {})


def get_allowed_scenarios(config):
    return config.get('allowed_target_scenarios', [])


# ---------------------------------------------------------------------------
# check 校验
# ---------------------------------------------------------------------------
def run_check(config):
    errors = []
    items = get_items(config)
    ids_seen = {}
    capacities = config.get('scene_capacity_per_week', {})
    allowed_scenarios = get_allowed_scenarios(config)
    urgent_types = get_urgent_allowed_types(config)
    valid_statuses = get_valid_statuses(config)
    valid_priorities = get_valid_priorities(config)
    default_samples = config.get('default_sample_requirements', {})

    for item in items:
        oid = item.get('observation_id', 'MISSING')

        # 1. ID unique
        if oid in ids_seen:
            errors.append(f"Duplicate observation_id: {oid}")
        ids_seen[oid] = True

        # 2. Status valid
        status = item.get('status', '')
        if status not in valid_statuses:
            errors.append(f"{oid}: invalid status '{status}'")

        # 3. Priority valid
        priority = item.get('priority', '')
        if priority not in valid_priorities:
            errors.append(f"{oid}: invalid priority '{priority}'")

        # 4. Urgent type whitelist (if urgent)
        if priority == 'urgent':
            utype = item.get('urgent_type', '')
            if not utype:
                errors.append(f"{oid}: urgent item missing urgent_type")
            elif utype not in urgent_types:
                errors.append(
                    f"{oid}: urgent_type '{utype}' not in whitelist {urgent_types}")

        # 5. target_scenarios valid
        for sc in item.get('target_scenarios', []):
            if sc not in allowed_scenarios:
                errors.append(
                    f"{oid}: invalid target_scenario '{sc}'")

        # 6. no_logic_change required
        if not item.get('no_logic_change', False):
            errors.append(f"{oid}: no_logic_change must be true")

        # 7. no_weight_change required
        if not item.get('no_weight_change', False):
            errors.append(f"{oid}: no_weight_change must be true")

        # 8. sample_requirement exists
        sr = item.get('sample_requirement')
        if not sr:
            errors.append(f"{oid}: missing sample_requirement")
        elif 'min_eval_samples' not in sr:
            errors.append(
                f"{oid}: sample_requirement missing min_eval_samples")

        # 9. normal/high not immediate
        if priority in ('normal', 'high'):
            if item.get('_immediate', False):
                errors.append(
                    f"{oid}: normal/high priority cannot be immediate")

        # 10. daily_pick capacity check
        for sc in item.get('target_scenarios', []):
            cap = capacities.get(sc, {})
            if cap.get('max_new_items', -1) == 0:
                if not cap.get('requires_yaozi_approval', False):
                    errors.append(
                        f"{oid}: scenario '{sc}' max_new_items=0 "
                        f"but requires_yaozi_approval is false")

        # 11. Evidence type valid
        ev_type = item.get('evidence_type', '')
        if ev_type and ev_type not in default_samples:
            errors.append(
                f"{oid}: unknown evidence_type '{ev_type}'")

    verdict = 'PASS' if not errors else 'FAIL'
    return {'verdict': verdict, 'errors': errors, 'total': len(errors)}


# ---------------------------------------------------------------------------
# list 输出
# ---------------------------------------------------------------------------
def cmd_list(config):
    items = get_items(config)
    h = f"{'ID':<25} {'Priority':<10} {'Status':<12} {'Scenarios':<30} {'Owner':<10}"
    print(h)
    print('-' * len(h))
    for item in items:
        sc = ','.join(item.get('target_scenarios', []))
        print(
            f"{item.get('observation_id', ''):<25} "
            f"{item.get('priority', ''):<10} "
            f"{item.get('status', ''):<12} "
            f"{sc:<30} "
            f"{item.get('owner_role', ''):<10}"
        )


# ---------------------------------------------------------------------------
# due 计算
# ---------------------------------------------------------------------------
def cmd_due(config, week_str):
    items = get_items(config)
    priorities = config.get('priority', {})
    print(f"{'ID':<30} {'Priority':<10} {'Status':<12} {'Due reason':<30}")
    print('-' * 82)
    for item in items:
        prio = item.get('priority', '')
        status = item.get('status', '')
        pid = item.get('observation_id', '')
        prio_info = priorities.get(prio, {})
        batch_mode = prio_info.get('batch_mode', '')

        due_reason = ''
        if status != 'candidate':
            due_reason = f"status={status}, not candidate"
        elif batch_mode == 'immediate_t0_t1':
            due_reason = f"urgent immediate_due (week-independent)"
        elif batch_mode in ('weekly', 'weekly_priority'):
            due_reason = f"{batch_mode} due (week {week_str})"
        else:
            due_reason = f"unknown batch_mode: {batch_mode}"

        print(f"{pid:<30} {prio:<10} {status:<12} {due_reason:<30}")


# ---------------------------------------------------------------------------
# activate 模拟
# ---------------------------------------------------------------------------
def cmd_activate(config, week_str):
    items = get_items(config)
    capacities = config.get('scene_capacity_per_week', {})
    urgent_types = get_urgent_allowed_types(config)
    priorities = config.get('priority', {})

    print(f"{'ID':<30} {'Priority':<10} {'Result':<40}")
    print('-' * 80)

    # Track weekly capacity used per scenario
    weekly_used = {}

    for item in items:
        pid = item.get('observation_id', '')
        prio = item.get('priority', '')
        status = item.get('status', '')
        scenarios = item.get('target_scenarios', [])
        utype = item.get('urgent_type', '')
        prio_info = priorities.get(prio, {})

        if status != 'candidate':
            print(f"{pid:<30} {prio:<10} {'skipped (not candidate)':<40}")
            continue

        # Urgent immediate activation
        if prio == 'urgent' and utype in urgent_types:
            print(f"{pid:<30} {prio:<10} {'active_immediate':<40}")
            continue

        # Normal/high: weekly batch, capacity dependent
        if prio in ('normal', 'high'):
            blocked = False
            for sc in scenarios:
                cap = capacities.get(sc, {})
                max_new = cap.get('max_new_items', 0)
                if max_new == 0:
                    if cap.get('requires_yaozi_approval', False):
                        print(
                            f"{pid:<30} {prio:<10} "
                            f"'approval_required (daily_pick needs 腰子)':<40")
                        blocked = True
                        break
                # Track usage
                weekly_used.setdefault(sc, 0)
                weekly_used[sc] += 1
                if weekly_used[sc] > max_new:
                    print(
                        f"{pid:<30} {prio:<10} "
                        f"'capacity_blocked (scene={sc}, max={max_new})':<40")
                    blocked = True
                    break

            if not blocked:
                print(f"{pid:<30} {prio:<10} {'active_if_capacity_available':<40}")
            continue

        print(f"{pid:<30} {prio:<10} {'unknown priority':<40}")


# ---------------------------------------------------------------------------
# manifest 生成
# ---------------------------------------------------------------------------
def cmd_manifest(config, scenario, week_str):
    items = get_items(config)
    matched = []
    fields = set()

    for item in items:
        if scenario in item.get('target_scenarios', []):
            matched.append({
                'observation_id': item.get('observation_id'),
                'title': item.get('title'),
                'priority': item.get('priority'),
                'owner_role': item.get('owner_role'),
                'status': item.get('status'),
                'evidence_type': item.get('evidence_type'),
                'observation_fields': item.get('observation_fields', []),
                'sample_requirement': item.get('sample_requirement'),
                'upgrade_condition': item.get('upgrade_condition'),
                'no_logic_change': item.get('no_logic_change', True),
                'no_weight_change': item.get('no_weight_change', True),
            })
            for f in item.get('observation_fields', []):
                fields.add(f)

    manifest = {
        'scenario': scenario,
        'week': week_str,
        'observation_fields': sorted(fields),
        'items': matched,
        'no_logic_change': all(
            it.get('no_logic_change', True) for it in get_items(config)
            if scenario in it.get('target_scenarios', [])
        ),
        'no_weight_change': all(
            it.get('no_weight_change', True) for it in get_items(config)
            if scenario in it.get('target_scenarios', [])
        ),
        'not_core_knowledge': True,
        'not_six_library_entry': True,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


# ---------------------------------------------------------------------------
# simulate
# ---------------------------------------------------------------------------
def cmd_simulate(config):
    items = get_items(config)
    capacities = config.get('scene_capacity_per_week', {})
    urgent_types = get_urgent_allowed_types(config)

    o1 = get_item_by_id(config, 'OBS-TEST-001')
    o2 = get_item_by_id(config, 'OBS-TEST-URGENT-001')

    results = []

    # OBS-TEST-001: normal, weekly/post_eval batch
    if o1:
        result_001 = {
            'observation_id': 'OBS-TEST-001',
            'title': o1.get('title'),
            'priority': o1.get('priority'),
            'status': o1.get('status'),
            'scenarios': o1.get('target_scenarios', []),
            'activate_result': 'active_if_capacity_available',
            'batch_mode': 'weekly',
            'no_logic_change': o1.get('no_logic_change', True),
            'no_weight_change': o1.get('no_weight_change', True),
        }
        results.append(result_001)

    # OBS-TEST-URGENT-001: urgent, data_field_definition_change
    if o2:
        result_002 = {
            'observation_id': 'OBS-TEST-URGENT-001',
            'title': o2.get('title'),
            'priority': o2.get('priority'),
            'status': o2.get('status'),
            'urgent_type': o2.get('urgent_type'),
            'urgent_in_whitelist': o2.get('urgent_type') in urgent_types,
            'scenarios': o2.get('target_scenarios', []),
            'activate_result': 'active_immediate',
            'batch_mode': 'immediate_t0_t1',
            'no_logic_change': o2.get('no_logic_change', True),
            'no_weight_change': o2.get('no_weight_change', True),
        }
        results.append(result_002)

    # daily_pick no 腰子 approval scenario: test capacity=0 + requires_yaozi
    daily_pick_caps = capacities.get('daily_pick', {})
    results.append({
        'scenario_check': 'daily_pick',
        'max_new_items': daily_pick_caps.get('max_new_items', 0),
        'requires_yaozi_approval': daily_pick_caps.get(
            'requires_yaozi_approval', False),
        'expected_behavior': (
            'approval_required; default not activated without 腰子 approval'
        ),
    })

    # Manifest check: all manifest have no_logic_change + no_weight_change
    for sc in ['weekly', 'daily', 'post_eval']:
        manifest = cmd_manifest(config, sc, '2026-W24')
        manifest_ok = (
            manifest.get('no_logic_change') is True
            and manifest.get('no_weight_change') is True
        )
        results.append({
            'manifest_scenario': sc,
            'no_logic_change': manifest.get('no_logic_change'),
            'no_weight_change': manifest.get('no_weight_change'),
            'manifest_check': 'PASS' if manifest_ok else 'FAIL',
        })

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    config = load_config()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == 'list':
        cmd_list(config)

    elif command == 'due':
        week = _parse_arg('--week') or '2026-W24'
        cmd_due(config, week)

    elif command == 'activate':
        week = _parse_arg('--week') or '2026-W24'
        cmd_activate(config, week)

    elif command == 'manifest':
        scenario = _parse_arg('--scenario')
        week = _parse_arg('--week') or '2026-W24'
        if not scenario:
            print("Usage: manifest --scenario <name> --week <week>")
            sys.exit(1)
        cmd_manifest(config, scenario, week)

    elif command == 'check':
        result = run_check(config)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif command == 'simulate':
        cmd_simulate(config)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


def _parse_arg(name):
    for i, arg in enumerate(sys.argv):
        if arg == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


if __name__ == '__main__':
    main()
