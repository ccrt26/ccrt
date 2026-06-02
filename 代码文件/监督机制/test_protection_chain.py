#!/usr/bin/env python3
"""test_protection_chain.py — 保护链路最小回归测试 (5 scenarios).

直接调用 pipeline_auth.test_pipeline_authorization() 验证全链路授权逻辑。
每个场景写入对应 token 后断言结果，不依赖人工判断。

Usage: python3 代码文件/监督机制/test_protection_chain.py
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / ".claude" / "hooks" / "shared"))
import pipeline_auth  # noqa: E402

TOKEN_PATH = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")
TEST_FILE = "代码文件/tools/health_check.py"

failed = 0
total = 0


def run_scenario(name, token_state, expect_authorized, expect_reason_keyword):
    global failed, total
    total += 1

    # Deploy token
    if token_state is None:
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
    else:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(token_state, f, indent=2)

    # Call auth
    result = pipeline_auth.test_pipeline_authorization(TEST_FILE, PROJECT_ROOT)

    # Verify
    ok = True
    if result["authorized"] != expect_authorized:
        ok = False
    if expect_reason_keyword and expect_reason_keyword not in result["reason"]:
        ok = False

    if ok:
        print(f"[PASS] {name}")
        print(f"       authorized={result['authorized']}, reason={result['reason']}")
    else:
        failed += 1
        print(f"[FAIL] {name}")
        print(f"       expected authorized={expect_authorized}, reason contains '{expect_reason_keyword}'")
        print(f"       got      authorized={result['authorized']}, reason={result['reason']}")


def main():
    global failed

    # Backup original token
    backup = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            backup = f.read()

    try:
        print("=" * 60)
        print("  保护链路最小回归测试")
        print(f"  测试文件: {TEST_FILE}")
        print("=" * 60)
        print()

        # S1: No pipeline token
        run_scenario(
            "S1: 无 pipeline token",
            None,
            False,
            "No pipeline token found"
        )

        # S2: Token inactive
        run_scenario(
            "S2: token active=false",
            {"active": False, "executor": "", "gate_1": "", "files_scope": []},
            False,
            "Pipeline not active"
        )

        # S3: Invalid executor
        run_scenario(
            "S3: executor 不合法 (腰子)",
            {"active": True, "executor": "腰子", "gate_1": "PASS", "files_scope": ["代码文件/tools/health_check.py"]},
            False,
            "Invalid executor"
        )

        # S4: gate_1 not PASS
        run_scenario(
            "S4: gate_1 != PASS",
            {"active": True, "executor": "红结", "gate_1": "FAIL", "files_scope": ["代码文件/tools/health_check.py"]},
            False,
            "Gate_1 not PASS"
        )

        # S5: All valid
        run_scenario(
            "S5: active=true, executor=红结, gate_1=PASS, scope 命中",
            {"active": True, "executor": "红结", "gate_1": "PASS", "files_scope": ["代码文件/tools/health_check.py"]},
            True,
            "Pipeline authorized"
        )

    finally:
        # Restore original token
        if backup is not None:
            os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
            with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                f.write(backup)
        elif os.path.exists(TOKEN_PATH):
            # If token was created by test but didn't exist before, clean up
            # Actually in S1 we remove it, and backup is None if it didn't exist
            # After S5 it exists again, so we should remove it
            if backup is None:
                os.remove(TOKEN_PATH)

    print()
    print("=" * 60)
    if failed == 0:
        print(f"  全部 {total}/{total} PASS")
    else:
        print(f"  {failed}/{total} FAIL")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
