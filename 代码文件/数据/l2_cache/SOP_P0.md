# L2 故障恢复标准操作流程（SOP_P0）

> 适用范围：L2 SQLite（`代码文件/数据/l2_cache/l2_cache.db`）
> 优先级：P0（当日报告不依赖 L2，L2 故障不影响生产）
> 维护人：玉夜

---

## P0-0：故障发现

故障通过以下方式发现：
- `scripts/check_d04_health.py` 输出 UNHEALTHY
- `update_l2_cache.py` 运行失败（哨兵 status=ERROR）
- `PRAGMA integrity_check` 返回非 OK

## P0-1：DB 损坏恢复

### 场景：integrity_check 失败或查询报错

```bash
# 1. 确认损坏
python3 -c "
import sqlite3
conn = sqlite3.connect('代码文件/数据/l2_cache/l2_cache.db')
cur = conn.execute('PRAGMA integrity_check')
print(cur.fetchall())
"

# 2. 尝试从最新备份恢复
cp 代码文件/数据/l2_cache/backup/l2_cache_最新日期.db 代码文件/数据/l2_cache/l2_cache.db

# 3. 再次健康检查
python3 scripts/check_d04_health.py --strict

# 4. 若无可用备份 → 重建
python3 scripts/build_l2_cache.py --dry-run   # 先 dry-run
python3 scripts/build_l2_cache.py              # 实建
```

### 场景：备份也损坏

```bash
# 1. 从次新备份恢复
ls -lt 代码文件/数据/l2_cache/backup/ | head -5

# 2. 或从 L3 归档重建关键表
python3 scripts/rebuild_score_history.py

# 3. 重建 kline 表（耗时较久）
python3 scripts/build_l2_cache.py --force-rebuild
```

## P0-2：备份缺失恢复

```bash
# 检查备份目录
ls -la 代码文件/数据/l2_cache/backup/

# 若无备份：先 build，再 update 到最新
python3 scripts/build_l2_cache.py
python3 scripts/update_l2_cache.py --date $(date +%Y%m%d)
```

## P0-3：哨兵文件丢失

```bash
# 哨兵丢失不影响 L2 功能，但 check_d04_health 会 WARN
# 手动重建哨兵：
python3 -c "
import json, os, sqlite3
db = '代码文件/数据/l2_cache/l2_cache.db'
if os.path.exists(db):
    conn = sqlite3.connect(db)
    rows = {}
    for t in ['kline','score_history','returns','financials','macro','risk_metrics','historical_percentiles']:
        try:
            rows[t] = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        except: rows[t] = 0
    conn.close()
    sentinel = {
        'status': 'OK', 'db_size': os.path.getsize(db),
        'table_rows': rows, 'updated_at': None
    }
    with open('代码文件/数据/l2_cache/last_update.json','w',encoding='utf-8') as f:
        json.dump(sentinel, f, indent=2, ensure_ascii=False)
    print('Sentinel recreated')
else:
    print('DB not found, skipping')
"
```

## P0-4：数据不一致恢复

### 场景：L1 vs L2 价格差异 ≥ 0.5%

按 D04 权威源决策表 §二——玉夜收集数据事实后上报腰子裁决。L1 为当日权威，差异 < 0.5% 以 L1 为准。

```bash
# 对比指定股票的 close
python3 -c "
import json, sqlite3
code = '600114'
l1 = json.load(open('代码文件/数据/kline_cache/{code}.json'))
l2_conn = sqlite3.connect('代码文件/数据/l2_cache/l2_cache.db')
l2_rows = l2_conn.execute('SELECT date, close FROM kline WHERE code=? ORDER BY date DESC LIMIT 5', (code,)).fetchall()
l1_dates = {r['date']: r['close'] for r in l1 if r['date'][:4]=='2026'}
for d, c in l2_rows:
    l1c = l1_dates.get(d)
    if l1c and abs(c - l1c) / max(abs(c),0.001) > 0.005:
        print(f'WARN: {code} {d} L1={l1c} L2={c} diff={abs(c-l1c)/max(abs(c),0.001)*100:.2f}%')
"
```

## P0-5：升级路径

| 故障类型 | 处理人 | 升级条件 |
|:---------|:-------|:---------|
| DB 损坏 | 玉夜 | 备份也损坏 → 升级腰子 |
| 数据不一致 ≥ 0.5% | 玉夜→腰子 | 腰子裁决 |
| build 脚本失败 | 红结 | 连续 3 次失败 → 升级情墨 |
| update 哨兵 ERROR | 执行模型 | 连续 2 天 ERROR → 升级阿黑 |
