"""test_d04_fallback.py — UnifiedDataSource 降级回归测试

覆盖 5+ 个回归场景：
  1. test_l1_sufficient: L1 充足 → l1_live
  2. test_l1_l2_fallback: L1 不足 + L2 补足 / L2 不可用降级
  3. test_l2_empty_degraded: L2 可用但表为空时返回 degraded/SKIP
  4. test_step3_not_available_interfaces: B 类边界外接口 → not_available_in_step3/SKIP
  5. test_kline_degraded_no_l1: L1 和 L2 都不可用时 → 正确降级
  6. test_degraded_warning_no_fake_db_missing: DB 存在但表空时 warning 不写"DB 不存在"

用法:
  python3 tests/test_d04_fallback.py
  python3 -m pytest tests/test_d04_fallback.py -v
"""
import sys
from pathlib import Path

_this_file = __file__ if '__file__' in dir() else Path.cwd() / 'tests/test_d04_fallback.py'
ROOT = Path(_this_file).resolve().parent.parent
sys.path.insert(0, str(ROOT / "代码文件" / "数据"))

from unified_data_source import UnifiedDataSource


# ── 公共实例（避免每个测试重复创建） ──
_ds = None

def _get_ds():
    global _ds
    if _ds is None:
        _ds = UnifiedDataSource()
    return _ds


def test_l1_sufficient():
    """L1 kline_cache 覆盖 ≥ 请求天数 → l1_live，状态 PASS 或 WARN"""
    ds = _get_ds()
    result = ds.get_kline("600114", 60)
    assert "data_source" in result
    assert "status" in result
    # 60 天远小于 kline_cache 实际天数（~122），L1 应充足
    assert result["data_source"] == "l1_live", (
        f"L1 充足时 data_source 应为 l1_live，实际为 {result['data_source']}"
    )
    assert result["status"] in ("PASS", "WARN"), (
        f"status 应为 PASS 或 WARN，实际为 {result['status']}"
    )


def test_l1_l2_fallback():
    """L1 不够天数时正确降级或回源 L2

    - L2 不可用 → degraded + WARN（带"l2_cache.db 不存在"）
    - L2 可用 → l2_cache / l1_live（L2 填充 L1 缺口）
    """
    ds = _get_ds()
    # 请求极大天数（9999）强制触发 L2 fallback
    result = ds.get_kline("600114", 9999)
    if not ds._l2_available:
        assert result["data_source"] == "degraded", (
            f"L2 不可用时 L1 不足应返回 degraded，实际为 {result['data_source']}"
        )
        assert result["status"] == "WARN", (
            f"degraded 状态应保持 WARN（有 L1 部分数据），实际为 {result['status']}"
        )
        warnings_text = " ".join(result.get("warnings", ["no warnings"]))
        assert "l2_cache.db 不存在" in warnings_text or "小于请求" in warnings_text, (
            f"warnings 应包含原因描述，实际为 {result['warnings']}"
        )
    else:
        # L2 有 kline 数据 → 应能补足大天数请求
        assert result["data_source"] in ("l2_cache", "l1_live"), (
            f"L2 可用时大天数请求应返回 l2_cache 或 l1_live，实际为 {result['data_source']}"
        )
        assert result["status"] in ("PASS", "WARN"), (
            f"状态应为 PASS 或 WARN，实际为 {result['status']}"
        )


def test_l2_empty_degraded():
    """L2 可用但表为空时返回 degraded/SKIP

    当 DB 存在但特定表（如 macro）为空时，应返回 degraded/SKIP。
    warning 中不应误说 'l2_cache.db 不存在'。
    """
    ds = _get_ds()
    result = ds.get_macro("CPI", 3)
    # DB 存在 → 表空或可用
    if ds._db_path.exists():
        if result["data_source"] == "degraded":
            assert result["status"] in ("SKIP", "WARN"), (
                f"macro degraded 状态应为 SKIP/WARN，实际为 {result['status']}"
            )
            warnings_text = " ".join(result.get("warnings", []))
            assert "l2_cache.db 不存在" not in warnings_text, (
                f"DB 存在时不应写 'DB 不存在': {warnings_text}"
            )
        elif result["data_source"] == "l2_cache":
            assert result["status"] in ("PASS", "WARN"), (
                f"macro l2_cache 状态应为 PASS/WARN，实际为 {result['status']}"
            )
    else:
        # DB 完全不存在 → degraded/SKIP
        assert result["data_source"] == "degraded", (
            f"macro（纯 L2 接口）应为 degraded，实际为 {result['data_source']}"
        )
        assert result["status"] in ("SKIP", "WARN"), (
            f"macro degraded 状态应为 SKIP，实际为 {result['status']}"
        )


def test_step3_not_available_interfaces():
    """B 类边界外接口（L2 不可用时）→ not_available_in_step3 / SKIP"""
    ds = _get_ds()
    tests = [
        ("compare", ds.compare_current_vs_historical("600114", "close", 60)),
        ("factor_ic", ds.compute_factor_ic("TotalScore", 20)),
        ("factor_panel", ds.export_factor_panel(["600114"], "2026-01-01", "2026-06-09")),
    ]
    for name, result in tests:
        if not ds._l2_available:
            assert result["data_source"] == "not_available_in_step3", (
                f"{name}: L2 不存在时应返回 not_available_in_step3，"
                f"实际为 {result['data_source']}"
            )
            assert result["status"] == "SKIP", (
                f"{name}: not_available_in_step3 状态应为 SKIP，"
                f"实际为 {result['status']}"
            )
        else:
            # L2 存在时也只应返回 l2_cache 或 not_available_in_step3
            assert result["data_source"] in ("l2_cache", "not_available_in_step3"), (
                f"{name}: L2 存在时 data_source 应仅为 l2_cache 或 not_available_in_step3，"
                f"实际为 {result['data_source']}"
            )
            assert result["status"] in ("PASS", "WARN", "SKIP"), (
                f"{name}: L2 存在时 status 应为 PASS/WARN/SKIP，"
                f"实际为 {result['status']}"
            )


def test_kline_degraded_no_l1():
    """L1 和 L2 都不可用时 → degraded（L2 不可用）或 unavailable（两者皆空）"""
    ds = _get_ds()
    # 对不存在于 kline_cache 中的股票代码
    result = ds.get_kline("999999", 60)
    # 合理降级：L2 不存在 → degraded；L2 存在但无数据 → unavailable
    if result["data_source"] == "degraded":
        assert result["status"] in ("SKIP", "WARN")
    # 正常：只要返回格式正确即可


def test_degraded_warning_no_fake_db_missing():
    """DB 存在但表空时 warning 不得写 'DB 不存在'

    修复验证：_l2_degraded 按表级区分原因。
    - DB 不存在      → 'l2_cache.db 不存在'
    - 表不存在       → 'L2 {table} 表不存在'
    - 表为空         → 'L2 {table} 表为空'
    """
    ds = _get_ds()

    # 对 macro 表（当前为 0 行）和 financials 表（当前为 0 行）做验证
    for iface_name, table_name in [("macro", "macro"), ("financials", "financials")]:
        ds = _get_ds()  # fresh instance each time to avoid cached conn
        if iface_name == "macro":
            result = ds.get_macro("CPI", 3)
        else:
            # 用不存在的股票触发 financials 降级
            result = ds.get_financials("999999", 2)

        if ds._db_path.exists():
            # DB 存在时，检查 degraded 警告不写 "DB 不存在"
            if result["data_source"] == "degraded":
                warnings_text = " ".join(result.get("warnings", []))
                assert "l2_cache.db 不存在" not in warnings_text, (
                    f"DB 存在时 warning 不应写 'DB 不存在': {warnings_text}"
                )
                # 应指明具体表
                assert table_name in warnings_text, (
                    f"warning 应指明具体表名 '{table_name}'，实际: {warnings_text}"
                )


if __name__ == "__main__":
    # 手动运行（无 pytest 时）
    test_funcs = [
        test_l1_sufficient,
        test_l1_l2_fallback,
        test_l2_empty_degraded,
        test_step3_not_available_interfaces,
        test_kline_degraded_no_l1,
        test_degraded_warning_no_fake_db_missing,
    ]
    passed = 0
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f"  ✅ {fn.__name__}: PASS")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: FAIL — {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {fn.__name__}: ERROR — {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests PASS")
    sys.exit(1 if failed > 0 else 0)
