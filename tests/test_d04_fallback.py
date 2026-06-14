import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "代码文件/数据"))

from unified_data_source import UnifiedDataSource

def test_d04_health_contract_uses_kline():
    ds = UnifiedDataSource()
    h = ds.health()
    assert h["status"] == "PASS"
    assert h["target_table"] == "kline"
    assert h["kline_rows"] > 0
    assert h["kline_quality_rows"] > 0
    assert h["release_state"] == "g6_released", f"release_state={h['release_state']}"

def test_d04_l1_snapshot_contract():
    ds = UnifiedDataSource()
    s = ds.load_l1_snapshot()
    assert s["quality_flag"] in {"complete", "invalid"}
    assert "source" in s

def test_d04_kline_contract_has_quality_metadata():
    ds = UnifiedDataSource()
    rows = ds.get_kline("600114", limit=5)
    assert isinstance(rows, list)
    assert rows
    assert "quality_flag" in rows[0]
    assert "source_tier" in rows[0]

def test_d04_score_history_contract():
    ds = UnifiedDataSource()
    rows = ds.get_score_history("600114", limit=5)
    assert isinstance(rows, list)
