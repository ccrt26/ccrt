# D04 常规审计接入报告

> **流程编号**：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G3（实施阶段）
> **日期**：2026-06-09
> **适用**：旧影（常规审计）、新安（自检）

---

## 一、接入概览

自 STEP4 起，D04 数据中台（C-D04-0001）纳入项目常规审计体系。

### 1.1 审计范围

| 审计对象 | 范围 |
|:---------|:------|
| D04 目录完整性 | L2 目录（l2_cache/）是否存在 |
| L2 DB 状态 | l2_cache.db 是否存在、Schema 完整性 |
| L2 哨兵新鲜度 | last_update.json 是否 <24h 更新 |
| L2 备份完整性 | backup/ 目录备份文件 <7 天 |
| 生产安全 | 日报/深度分析入口是否引用 UnifiedDataSource |
| 闸门子项 | freshness/numeric kline_l2 子项不阻断 |

### 1.2 审计频率

| 频率 | 检查项 | 命令 |
|:-----|:-------|:-----|
| 日检 | D04 目录完整性 + 生产安全 | `python3 scripts/check_d04_health.py --dry-run` |
| 日检 | Freshness L2 子项 | `check_freshness_degradation.py --tier l2 --json \| grep -A5 kline_l2` |
| 日检 | Numeric kline_l2 子项 | `check_numeric_source_consistency.py --json \| grep -A5 kline_l2` |
| 周检 | UDS 接口连通性 | `python3 scripts/run_shadow_diff.py --all-stocks --date <最近交易日>` |
| 周检 | 注册表 JSON 一致性 | `python3 -m json.tool` 两个注册表 |
| 月检 | L2 备份完整性 | `python3 scripts/check_d04_health.py` |
| 月检 | 五步优化状态保持 | 全部验收命令 |

### 1.3 审计模板

已更新至 `00_项目地基/08_审计与验收/AUDIT_验收规则与模板_v1.0.md` §4。

---

## 二、审计字段定义

每次审计记录至少包含：

| 字段 | 示例 |
|:-----|:------|
| 审计日期 | 2026-06-09 |
| 审计范围 | D04 常规日检 |
| 执行命令 | `scripts/check_d04_health.py --dry-run` |
| 结果 | ✅ PASS / ⚠️ WARN / ❌ BLOCK |
| 异常说明 | 如：L2 DB 不存在（Phase 2 前预期状态） |

---

## 三、已知的预期 WARN

以下 WARN 在 Phase 2 启用前为**预期状态**，不视为异常：

| WARN 项 | 原因 | 预计解除 |
|:--------|:------|:---------|
| check_d04_health.py DB_EXISTS WARN | l2_cache.db 未创建 | Phase 2 用户授权后 |
| check_d04_health.py SENTINEL WARN | 哨兵文件不存在 | Phase 2 L2 启用后 |
| check_d04_health.py BACKUP_DIR WARN | 备份目录空 | Phase 2 L2 启用后 |
| Freshness kline_l2 SKIP | enabled=false, phase=2 | Phase 2 启用后 |

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 阶段门：G3*
*formal pipeline actor/HMAC 明示例外*
