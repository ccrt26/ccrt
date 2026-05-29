#!/usr/bin/env python3
"""
verify_deployment.py - 部署验收核查 (闸门3 旧影侧)
G1: 新增文件存在  G2: Cron已注册  G3: 配置已生效  G4: 回滚方案就位
任一项FAIL → 打回红枫
"""
import sys
import json
import os
import subprocess
from log_utils import append_log

def verify_deployment(checklist_path):
    """主核查逻辑"""
    if not os.path.exists(checklist_path):
        print(f"FAIL: 清单文件不存在: {checklist_path}")
        sys.exit(1)

    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"FAIL: JSON格式非法: {e}")
        sys.exit(1)

    run_id = data.get("run_id", "UNKNOWN")
    deploy_items = data.get("deploy_items", [])
    errors = []

    if not deploy_items:
        errors.append("清单G段为空: 没有任何部署项")

    for item in deploy_items:
        item_id = item.get("id", "未知项")
        deploy_type = item.get("type", "")

        # G1: 新增文件存在
        if deploy_type == "file":
            target_path = item.get("target", "")
            if not os.path.exists(target_path):
                errors.append(f"G1[{item_id}]: 文件不存在: {target_path}")
            else:
                print(f"  ✓ G1[{item_id}]: 文件存在 {target_path}")

        # G2: Cron已注册
        elif deploy_type == "cron":
            cron_pattern = item.get("target", "")
            try:
                result = subprocess.run(
                    ["crontab", "-l"],
                    capture_output=True, text=True, timeout=10
                )
                if cron_pattern not in result.stdout:
                    errors.append(f"G2[{item_id}]: Cron未注册: {cron_pattern}")
                else:
                    print(f"  ✓ G2[{item_id}]: Cron已注册")
            except Exception as e:
                errors.append(f"G2[{item_id}]: Cron检查失败: {str(e)}")

        # G3: 配置变更已生效
        elif deploy_type == "config":
            config_file = item.get("target", "")
            expected_value = item.get("expected_value", "")
            if not os.path.exists(config_file):
                errors.append(f"G3[{item_id}]: 配置文件不存在: {config_file}")
            elif expected_value:
                try:
                    with open(config_file, 'r') as f:
                        content = f.read()
                    if expected_value not in content:
                        errors.append(f"G3[{item_id}]: 配置值未找到: {expected_value}")
                    else:
                        print(f"  ✓ G3[{item_id}]: 配置已生效")
                except Exception as e:
                    errors.append(f"G3[{item_id}]: 配置检查失败: {str(e)}")

        # G4: 回滚方案就位
        elif deploy_type == "rollback":
            rollback_path = item.get("target", "")
            if not os.path.exists(rollback_path):
                errors.append(f"G4[{item_id}]: 回滚脚本/文档不存在: {rollback_path}")
            else:
                print(f"  ✓ G4[{item_id}]: 回滚方案就位")

        else:
            errors.append(f"[{item_id}]: 未知部署类型: {deploy_type}")

    # 判定
    if errors:
        for deploy_item in deploy_items:
            append_log("deploy", {
                "run_id": run_id,
                "deploy_item": deploy_item.get("id", "?"),
                "check_type": deploy_item.get("type", "?"),
                "expected": deploy_item.get("target", "?"),
                "actual": "FAIL" if any(deploy_item.get("id") in e for e in errors) else "PASS",
                "result": "FAIL" if any(deploy_item.get("id") in e for e in errors) else "PASS"
            })
        print("FAIL: 部署验收不通过")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        for deploy_item in deploy_items:
            append_log("deploy", {
                "run_id": run_id,
                "deploy_item": deploy_item.get("id", "?"),
                "check_type": deploy_item.get("type", "?"),
                "expected": deploy_item.get("target", "?"),
                "actual": "PASS",
                "result": "PASS"
            })
        print("PASS: 所有部署项验收通过")
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        verify_deployment(sys.argv[1])
    else:
        print("用法: python verify_deployment.py <清单JSON路径>")
        sys.exit(1)
