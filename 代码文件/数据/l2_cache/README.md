# D04 L2 Cache Runbook

D04 L2 cache stores historical market data for cross-period analysis.

## Commands

```bash
python3 代码文件/每日荐股/scripts/build_l2_cache.py
python3 代码文件/每日荐股/scripts/rebuild_score_history.py
python3 代码文件/每日荐股/scripts/update_l2_cache.py --health-check
python3 -m pytest tests/test_d04_fallback.py
```

## Rules

- D03 owns data quality.
- D04 stores, indexes and retrieves L1/L2/L3 data.
- New temporary data cannot enter conclusions before validation.
- C-D04-0001 remains active only while health checks pass.
