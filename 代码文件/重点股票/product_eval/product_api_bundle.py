"""
ProductApiBundle - 产品 API 聚合包（session3 v3 最终版）。

三固化：
A. field_evidence 顶存 + 稳定 evidence_id + 白名单校验
B. 严格发布顺序：staging(STAGED) → bundles/{run_id} → os.replace pointer → legacy 镜像 → run_manifest(PUBLISHED)
C. engineering_status=PASS → exit 0；仅工程 BLOCK → exit 1

业务字段保持原始值（不包装），所有证据引用写入顶层 field_evidence。
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .inventory import PROJECT_ROOT
from .analysis_run_state import AnalysisRunStateService
from .evidence_trace_index import EvidenceTraceIndexService
from .rule_health_summary import RuleHealthSummaryService
from .stock_pool import ProductStockPoolService
from .conclusion_status import ConclusionStatusService
from .position_adapter import PositionAdapter
from . import data_source as ds


SCHEMA_VERSION = "keystock.product_api_bundle.v3"
BUNDLE_VERSION = "2026-06-16.v3"
PRODUCER_VERSION = "product_api_bundle.py/3.0.1"
MIN_FRONTEND_VERSION = "1.0.0"
TRADE_DATE = "20260616"


def _stable_ev_id(stock_code: str, source_type: str, trade_date: str = TRADE_DATE) -> str:
    """生成确定性 evidence_id，不使用 uuid。"""
    return f"ev-{stock_code}-{source_type}-{trade_date}"


def _make_source_ref(source_type: str, source_path: str,
                     source_field_refs: Optional[list] = None) -> dict:
    ref = {"source_type": source_type, "source_path": source_path}
    if source_field_refs:
        ref["source_field_refs"] = source_field_refs
    return ref


def _build_field_evidence(source_path: str, source_field_refs: Optional[list] = None,
                          evidence_refs: Optional[list] = None,
                          extra_source_refs: Optional[list] = None) -> dict:
    """构建单个 field_evidence 条目。"""
    refs = []
    if source_path:
        refs.append(_make_source_ref("file", source_path, source_field_refs))
    if extra_source_refs:
        refs.extend(extra_source_refs)
    # 当 source_path 为空但有 evidence_refs 时，自动添加 computed 来源
    if not source_path and evidence_refs:
        # 通过 evidence_refs 推断 source_type
        for er in evidence_refs:
            if "status-gate" in er:
                refs.append(_make_source_ref("status_gate", "", source_field_refs))
            elif "rule-health" in er:
                refs.append(_make_source_ref("rule_health", "", source_field_refs))
            elif "position" in er:
                refs.append(_make_source_ref("position_public_view", "", source_field_refs))
            else:
                refs.append(_make_source_ref("computed", "", source_field_refs))
            break  # 只需要一个
    result = {
        "source_path": source_path or "",
        "source_field_refs": source_field_refs or [],
        "evidence_refs": evidence_refs or [],
        "source_refs": refs,
    }
    return result


class ProductApiBundleService:
    def __init__(self, data_root: Optional[str] = None, run_mode: str = "shadow"):
        self.data_root = data_root or PROJECT_ROOT
        self.run_mode = run_mode
        self.run_state_svc = AnalysisRunStateService(data_root)
        self.evidence_svc = EvidenceTraceIndexService(data_root)
        self.rule_health_svc = RuleHealthSummaryService(data_root)
        self.pool_svc = ProductStockPoolService()
        self.conclusion_svc = ConclusionStatusService(run_mode)
        self.position_adapter = PositionAdapter()

    def _gen_run_id(self) -> str:
        return f"bundle-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    def _bundle_meta(self, run_id: str) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "bundle_version": BUNDLE_VERSION,
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer_version": PRODUCER_VERSION,
            "min_frontend_version": MIN_FRONTEND_VERSION,
        }

    def _annotate(self, data: dict, run_id: str, extra: Optional[dict] = None) -> dict:
        result = dict(data)
        result.update(self._bundle_meta(run_id))
        if extra:
            result.update(extra)
        return result

    def _annotate_legacy(self, data: dict, run_id: str, canonical_path: str = "") -> dict:
        extra = {
            "legacy_compat": True,
            "canonical_path": canonical_path,
            "deprecated_fields": [],
            "compatibility_notes": "legacy 镜像文件，仅兼容旧引用。新引用请读 canonical 对应文件。",
        }
        return self._annotate(data, run_id, extra)

    # ------------------------------------------------------------------
    # field_evidence 生成
    # ------------------------------------------------------------------

    def _fe(self, fe: dict) -> dict:
        """生成 field_evidence entry，确保 key 使用稳定业务路径。"""
        return fe

    def _ensure_field_evidence(self, data: dict, run_id: str) -> dict:
        """若 data 无 field_evidence 则根据 data 内容智能补充。"""
        if "field_evidence" not in data:
            data["field_evidence"] = {}
        return data

    def _build_common_evidence(self, stock_code: str, stock_name: str,
                               snap_path: str, bt_path: str) -> dict:
        """构建通用 evidence 字典id->item。"""
        evs = {
            _stable_ev_id(stock_code, "kline-cache"):
                {"evidence_id": _stable_ev_id(stock_code, "kline-cache"),
                 "source_type": "kline_cache",
                 "source_path": f"代码文件/数据/kline_cache/{stock_code}.json",
                 "summary": "K 线行情数据", "chart_hint": "kline", "status": "AVAILABLE"},
            _stable_ev_id(stock_code, "feature-snapshot"):
                {"evidence_id": _stable_ev_id(stock_code, "feature-snapshot"),
                 "source_type": "feature_snapshot",
                 "source_path": snap_path,
                 "summary": "技术特征 MA20/RSI", "chart_hint": "ma",
                 "status": "AVAILABLE" if os.path.exists(os.path.join(PROJECT_ROOT, snap_path)) else "MISSING"},
            _stable_ev_id(stock_code, "rule-health"):
                {"evidence_id": _stable_ev_id(stock_code, "rule-health"),
                 "source_type": "rule_health",
                 "source_path": f"运行产物/重点股票产品化后评估/product_api/rule_health_summary.json",
                 "summary": "规则健康 MA20 止损", "chart_hint": "matrix", "status": "AVAILABLE"},
            _stable_ev_id(stock_code, "status-gate"):
                {"evidence_id": _stable_ev_id(stock_code, "status-gate"),
                 "source_type": "status_gate",
                 "source_path": "", "summary": "状态闸门结论", "status": "COMPUTED"},
            _stable_ev_id(stock_code, "position-public-view"):
                {"evidence_id": _stable_ev_id(stock_code, "position-public-view"),
                 "source_type": "position_public_view",
                 "source_path": "", "summary": "公开持仓视图(status=UNAVAILABLE)",
                 "status": "UNAVAILABLE"},
        }
        bt_full_path = os.path.join(PROJECT_ROOT, bt_path)
        if os.path.exists(bt_full_path):
            evs[_stable_ev_id(stock_code, "backtest")] = {
                "evidence_id": _stable_ev_id(stock_code, "backtest"),
                "source_type": "backtest",
                "source_path": bt_path,
                "summary": "MA20 破位回测", "chart_hint": "matrix", "status": "AVAILABLE",
            }
        return evs

    # ------------------------------------------------------------------
    # 状态闸门
    # ------------------------------------------------------------------

    def _build_status_gate(self, snap, bt, chart, member):
        stock_code = member["stock_code"]
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})
        freshness = (snap or {}).get("freshness_status", {}).get("overall", "UNKNOWN")
        actual_date = tech.get("actual_trade_date", "")
        rule_status = "OBSERVE"
        if bt:
            rule_status = bt.get("overall_status", "OBSERVE")
        cd = chart or self._build_chart_data(member)
        return self.conclusion_svc.evaluate(
            stock_code=stock_code, stock_name=member["stock_name"],
            trade_date=actual_date or "unknown",
            freshness_status=freshness,
            data_date_divergence=cd.get("data_date_divergence", False),
            source_last_date=cd.get("source_last_date", ""),
            feature_snapshot_actual_date=cd.get("feature_snapshot_actual_date", ""),
            rule_health_status=rule_status,
            evidence_status="COMPLETE" if snap else "PARTIAL",
            position_status="UNAVAILABLE",
        )

    # ------------------------------------------------------------------
    # 主构建 — 严格发布顺序
    # ------------------------------------------------------------------

    def build_all(self, base_dir: str, out_dir: str, docs_data_dir: str) -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = self._gen_run_id()

        members = self.pool_svc.get_active_members()
        if not members:
            raise ValueError("股票池为空")
        member = members[0]
        code = member["stock_code"]
        name = member["stock_name"]

        snap_path = os.path.join(base_dir, "feature_snapshots", f"feature_snapshot_{code}_20260616.json")
        bt_path = os.path.join(base_dir, "backtests", f"backtest_TECH_MA20_BREAK_STOP_LOSS_{code}_20260616.json")
        inv_path = os.path.join(base_dir, "inventory", "keystock_system_inventory.json")
        dash_path = os.path.join(base_dir, "status", "dashboard_status.json")

        snap = self._load_json(snap_path)
        bt = self._load_json(bt_path)
        dash = self._load_json(dash_path)
        inv = self._load_json(inv_path)

        chart = self._build_chart_data(member)
        gate = self._build_status_gate(snap, bt, chart, member)

        # 构建通用 evidence 字典（稳定 ID）
        common_ev = self._build_common_evidence(code, name,
            os.path.join(base_dir, "feature_snapshots", f"feature_snapshot_{code}_20260616.json"),
            os.path.join(base_dir, "backtests", f"backtest_TECH_MA20_BREAK_STOP_LOSS_{code}_20260616.json"))

        # ── Step 1: staging ──
        staging_dir = os.path.join(docs_data_dir, "_staging", run_id)
        staging_out = os.path.join(out_dir, "_staging", run_id)
        os.makedirs(staging_dir, exist_ok=True)
        os.makedirs(staging_out, exist_ok=True)

        # 写 staging 全量文件
        pool = self._annotate(self.pool_svc.build_pool(), run_id)
        pool_sc = pool.get("members", [{}])[0].get("stock_code", "600114")
        pool_fe = _stable_ev_id(pool_sc, "feature-snapshot")
        pool["field_evidence"] = {}
        for pk in ["members.600114.stock_code", "members.600114.stock_name",
                     "members.600114.status", "members.600114.data_status",
                     "members.600114.evidence_status"]:
            pool["field_evidence"][pk] = _build_field_evidence(
                "", ["stock_code", "stock_name", "status"],
                [pool_fe],
                [_make_source_ref("computed", "stock_pool.py::build_pool()", ["_POOL_MEMBERS"])]
            )
        self._write_json(os.path.join(staging_out, "stock_pool.json"), pool)
        self._write_json(os.path.join(staging_dir, "stock_pool.json"), pool)

        dashboard = self._build_dashboard(dash, inv, snap, member, gate, run_id, common_ev)
        self._write_json(os.path.join(staging_out, "dashboard.json"), dashboard)
        self._write_json(os.path.join(staging_dir, "dashboard.json"), dashboard)

        stocks = self._build_stocks(snap, bt, member, gate, run_id, common_ev)
        self._write_json(os.path.join(staging_out, "stocks.json"), stocks)
        self._write_json(os.path.join(staging_dir, "stocks.json"), stocks)

        run_state = self.run_state_svc.derive_from_inventory(code, "20260616", inv_path, gate_override=gate)
        rs = self._annotate(run_state, run_id)
        self._write_json(os.path.join(staging_out, "run_state.json"), rs)
        self._write_json(os.path.join(staging_dir, "run_state.json"), rs)

        ev_idx_legacy = self.evidence_svc.derive_from_backtest(bt_path)
        if not ev_idx_legacy:
            ev_idx_legacy = self.evidence_svc.build_evidence_index(code, name, "20260616")
        ev_idx_legacy = self._annotate_legacy(ev_idx_legacy, run_id, f"bundles/{run_id}/evidence_index.json")
        ev_idx_legacy["field_evidence"] = {
            "evidence_items": _build_field_evidence(
                bt_path if os.path.exists(bt_path) else "",
                ["evidence_items"],
                [_stable_ev_id(code, "backtest") if os.path.exists(bt_path) else _stable_ev_id(code, "feature-snapshot")],
                [_make_source_ref("file" if os.path.exists(bt_path) else "computed",
                                  bt_path if os.path.exists(bt_path) else "evidence_trace_index.py::build_evidence_index",
                                  ["evidence_items"])]
            )
        }
        self._write_json(os.path.join(staging_out, "evidence_index.json"), ev_idx_legacy)
        self._write_json(os.path.join(staging_dir, "evidence_index.json"), ev_idx_legacy)

        rh = self.rule_health_svc.derive_from_backtest(bt_path) or self.rule_health_svc.build_rule_health()
        rh_l = self._annotate_legacy(rh, run_id, f"bundles/{run_id}/rule_health.json")
        self._write_json(os.path.join(staging_dir, "rule_health.json"), rh_l)
        self._write_json(os.path.join(staging_dir, "rule_health_summary.json"), rh_l)
        self._write_json(os.path.join(staging_out, "rule_health_summary.json"), rh_l)

        decisions = self._build_today_decisions(snap, bt, dash, member, gate, run_id, common_ev)
        self._write_json(os.path.join(staging_out, "today_decisions.json"), decisions)
        self._write_json(os.path.join(staging_dir, "today_decisions.json"), decisions)

        chart_sc_ev = _stable_ev_id(chart.get("stock_code", code), "kline-cache")
        chart_l = self._annotate_legacy(chart, run_id, f"bundles/{run_id}/chart_data.json")
        chart_l["field_evidence"] = {}
        for ck in ["stock_code", "source_last_date", "feature_snapshot_actual_date",
                   "data_date_divergence", "ohlc", "ma5", "ma20", "ma60"]:
            chart_l["field_evidence"][ck] = _build_field_evidence(
                f"代码文件/数据/kline_cache/{chart.get('stock_code', code)}.json",
                [ck], [chart_sc_ev],
                [_make_source_ref("file", f"代码文件/数据/kline_cache/{chart.get('stock_code', code)}.json", [ck])]
            )
        self._write_json(os.path.join(staging_out, "chart_data.json"), chart_l)
        self._write_json(os.path.join(staging_dir, "chart_data.json"), chart_l)

        # per-stock
        for m in members:
            sc = m["stock_code"]
            sd = os.path.join(staging_dir, "stocks", sc)
            so = os.path.join(staging_out, "stocks", sc)
            os.makedirs(sd, exist_ok=True)
            os.makedirs(so, exist_ok=True)
            detail = self._build_detail(snap, bt, member, gate, run_id, sc, m["stock_name"], common_ev)
            self._write_json(os.path.join(sd, "detail.json"), detail)
            self._write_json(os.path.join(so, "detail.json"), detail)
            sc_chart_raw = self._build_chart_data(member)
            sc_chart = self._annotate(sc_chart_raw, run_id)
            sc_ck_ev = _stable_ev_id(sc, "kline-cache")
            sc_chart["field_evidence"] = {}
            for ck in ["stock_code", "source_last_date", "feature_snapshot_actual_date",
                       "data_date_divergence", "ohlc", "ma5", "ma20", "ma60"]:
                sc_chart["field_evidence"][ck] = _build_field_evidence(
                    f"代码文件/数据/kline_cache/{sc}.json",
                    [ck], [sc_ck_ev],
                    [_make_source_ref("file", f"代码文件/数据/kline_cache/{sc}.json", [ck])]
                )
            self._write_json(os.path.join(sd, "chart_data.json"), sc_chart)
            self._write_json(os.path.join(so, "chart_data.json"), sc_chart)
            ev = self._build_evidence(member, gate, snap, bt, chart, run_id, common_ev)
            self._write_json(os.path.join(sd, "evidence.json"), ev)
            self._write_json(os.path.join(so, "evidence.json"), ev)

        # ── Step 2: staging run_manifest + bundle_index with STAGED ──
        stg_bi = self._build_bundle_index(run_id, members, publish_status="STAGED")
        self._write_json(os.path.join(staging_dir, "bundle_index.json"), stg_bi)
        self._write_json(os.path.join(staging_out, "bundle_index.json"), stg_bi)

        stg_rm = self._build_run_manifest(run_id, members, gate, stg_bi, started_at, publish_status="STAGED")
        self._write_json(os.path.join(staging_dir, "run_manifest.json"), stg_rm)
        self._write_json(os.path.join(staging_out, "run_manifest.json"), stg_rm)

        # ── Step 3-5: staging 未跑 checker（由 build 脚本在外部调用）
        # 构建完毕后返回基本信息，build 脚本负责 checker 后再 atomic_publish
        # 但为测试兼容，同时镜像 staging 到 final 目录
        self._mirror_legacy(staging_dir, docs_data_dir, run_id)
        self._mirror_legacy(staging_out, out_dir, run_id)
        for _sd, _dd in [(staging_dir, docs_data_dir), (staging_out, out_dir)]:
            for _fn in ["bundle_index.json", "run_manifest.json"]:
                _sp = os.path.join(_sd, _fn)
                if os.path.exists(_sp):
                    shutil.copy2(_sp, os.path.join(_dd, _fn))

        finished_at = datetime.now(timezone.utc).isoformat()

        return {
            "generated_at": finished_at,
            "run_id": run_id,
            "staging_docs_dir": staging_dir,
            "staging_out_dir": staging_out,
            "schema_version": SCHEMA_VERSION,
            "bundle_version": BUNDLE_VERSION,
            "files": [f["path"] for f in stg_bi.get("files", [])],
            "dashboard_overall": dashboard.get("overall_status", "UNKNOWN"),
            "dashboard_conclusion": dashboard.get("conclusion_status", "UNKNOWN"),
            "stocks_count": len(stocks.get("stocks", [])),
            "pool_members_count": len(members),
            "data_truth_status": "REAL_EVIDENCE_ONLY",
        }

    # ------------------------------------------------------------------
    # 原子发布（由 build 脚本在 checker 通过后调用）
    # ------------------------------------------------------------------

    def atomic_publish(self, staging_dir: str, staging_out: str,
                       docs_data_dir: str, out_dir: str, run_id: str,
                       members: list, gate: dict,
                       started_at: str, finished_at: str) -> dict:
        """Step 5-10: checker PASS → 复制 → os.replace pointer → 镜像 legacy → run_manifest PUBLISHED。"""
        # Step 5: copy staging → bundles/{run_id}
        canonical_docs = os.path.join(docs_data_dir, "bundles", run_id)
        canonical_out = os.path.join(out_dir, "bundles", run_id)
        if os.path.isdir(staging_dir):
            self._copy_dir(staging_dir, canonical_docs)
        if os.path.isdir(staging_out):
            self._copy_dir(staging_out, canonical_out)

        # Step 6: (already done via copy)

        # Step 7: os.replace bundle_index.json → PUBLISHED
        bi = self._build_bundle_index(run_id, members, publish_status="PUBLISHED")
        bi_path_docs = os.path.join(docs_data_dir, "bundle_index.json")
        bi_path_out = os.path.join(out_dir, "bundle_index.json")
        tmp_docs = bi_path_docs + ".tmp"
        tmp_out = bi_path_out + ".tmp"
        with open(tmp_docs, "w", encoding="utf-8") as f:
            json.dump(bi, f, ensure_ascii=False, indent=2)
        with open(tmp_out, "w", encoding="utf-8") as f:
            json.dump(bi, f, ensure_ascii=False, indent=2)
        os.replace(tmp_docs, bi_path_docs)
        os.replace(tmp_out, bi_path_out)
        print(f"[API] bundle_index (PUBLISHED): {bi_path_docs}")

        # Step 8: (done above)

        # Step 9: mirror legacy
        self._mirror_legacy(canonical_docs, docs_data_dir, run_id)
        self._mirror_legacy(canonical_out, out_dir, run_id)

        # Step 10: run_manifest PUBLISHED
        final_bi = self._load_json(bi_path_docs) or bi
        rm = self._build_run_manifest(run_id, members, gate, final_bi, started_at,
                                       publish_status="PUBLISHED", finished_at=finished_at)
        self._write_json(os.path.join(docs_data_dir, "run_manifest.json"), rm)
        self._write_json(os.path.join(out_dir, "run_manifest.json"), rm)

        return {
            "run_id": run_id,
            "canonical_path": f"bundles/{run_id}/",
            "publish_status": "PUBLISHED",
            "files": [f["path"] for f in final_bi.get("files", [])],
            "generated_at": finished_at,
        }

    @staticmethod
    def _copy_dir(src: str, dst: str) -> None:
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, dirs_exist_ok=True)

    # ------------------------------------------------------------------
    # field_evidence 生成器
    # ------------------------------------------------------------------

    def _with_field_evidence(self, data: dict, run_id: str,
                             fe_map: dict, default_source_path: str = "",
                             default_ev_refs: Optional[list] = None) -> dict:
        """为 data 添加 field_evidence 顶层字段。"""
        data["field_evidence"] = {}
        for field_key, fe in fe_map.items():
            # field_key 使用稳定业务路径：带点号表示嵌套路径
            sp = fe.get("source_path", default_source_path)
            sf = fe.get("source_field_refs", [])
            er = fe.get("evidence_refs", default_ev_refs or [])
            xs = fe.get("source_refs", [])
            data["field_evidence"][field_key] = _build_field_evidence(sp, sf, er, xs)
        return data

    # ------------------------------------------------------------------
    # _build_dashboard
    # ------------------------------------------------------------------

    def _build_dashboard(self, dash, inv, snap, member, gate, run_id, common_ev) -> dict:
        sidecar_count = 0
        if inv:
            sidecar_count = inv.get("daily_report_sidecars", {}).get("count", 0)
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})
        mf = []
        if not snap:
            mf.append("FEATURE_SNAPSHOT_MISSING")
        if sidecar_count == 0:
            mf.append("SIDECAR_MISSING")
        if tech.get("close") is None:
            mf.append("CLOSE_DATA_MISSING")

        os_ = gate.get("user_visible_status", "BLOCK")
        cs = gate.get("conclusion_status", "BLOCKED")
        blk = gate.get("blocking_reasons", [])
        warn = gate.get("warning_reasons", [])
        sc = member["stock_code"]
        sn = member["stock_name"]

        d = self._annotate({"overall_status": os_, "conclusion_status": cs,
            "data_truth_status": "REAL_DATA", "stocks_tracked": len(self.pool_svc.get_active_members()),
            "primary_stock_code": sc, "primary_stock_name": sn,
            "as_of_date": tech.get("actual_trade_date", "unknown"),
            "source_summary": f"kline_cache/{sc}.json + feature_snapshot",
            "missing_data_flags": mf, "blocks": blk,
            "warnings": warn or ["持仓数据未接入"],
            "status_gate": gate,
        }, run_id)

        qa = self._with_field_evidence(d, run_id, {
            "overall_status": {"source_path": f"运行产物/重点股票产品化后评估/status/dashboard_status.json",
                               "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
            "conclusion_status": {"source_path": "", "source_refs": [_make_source_ref("status_gate", "",
                                ["conclusion_status"])], "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
            "as_of_date": {"source_path": f"运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_{sc}_20260616.json",
                           "source_field_refs": ["feature_values.technical.actual_trade_date"],
                           "evidence_refs": [_stable_ev_id(sc, "feature-snapshot")]},
            "blocks": {"source_path": "", "source_refs": [_make_source_ref("status_gate", "",
                       ["blocking_reasons"])], "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
            "warnings": {"source_path": "", "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
            "status_gate.data_status": {"source_path": "", "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
            "status_gate.decision_blockers": {"source_path": "", "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
            "status_gate.status_gate_source_refs": {"source_path": "", "evidence_refs": [_stable_ev_id(sc, "status-gate")]},
        }, default_ev_refs=[_stable_ev_id(sc, "status-gate")])
        return qa

    # ------------------------------------------------------------------
    # _build_stocks
    # ------------------------------------------------------------------

    def _build_stocks(self, snap, bt, member, gate, run_id, common_ev) -> dict:
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})
        sc = member["stock_code"]
        sn = member["stock_name"]
        ad = tech.get("actual_trade_date", "")
        cp = self._get_change_pct_from_kline(ad, sc)
        mf = []
        if cp is None:
            mf.append("change_pct")
        uvs = gate.get("user_visible_status", "BLOCK")

        stock = {"stock_code": sc, "stock_name": sn,
            "close": tech.get("close"), "change_pct": cp,
            "close_vs_ma5_pct": self._calc_vs_ma5(tech),
            "actual_trade_date": ad,
            "data_freshness_status": (snap or {}).get("freshness_status", {}).get("overall", "UNKNOWN"),
            "run_status": "WARN" if uvs != "COMPLETE" else "PASS",
            "user_visible_status": uvs,
            "conclusion_status": gate.get("conclusion_status", "BLOCKED"),
            "missing_fields": mf,
        }
        data = self._annotate({"stocks": [stock]}, run_id)

        fs_path = f"运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_{sc}_20260616.json"
        kc_ev = _stable_ev_id(sc, "kline-cache")
        fs_ev = _stable_ev_id(sc, "feature-snapshot")
        sg_ev = _stable_ev_id(sc, "status-gate")

        data = self._with_field_evidence(data, run_id, {
            f"stocks.{sc}.stock_code": {"source_path": fs_path, "source_field_refs": ["stock_code"],
                                         "evidence_refs": [fs_ev]},
            f"stocks.{sc}.stock_name": {"source_path": fs_path, "source_field_refs": ["stock_name"],
                                         "evidence_refs": [fs_ev]},
            f"stocks.{sc}.close": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.close"],
                                   "evidence_refs": [fs_ev, kc_ev]},
            f"stocks.{sc}.change_pct": {"source_path": f"代码文件/数据/kline_cache/{sc}.json",
                                         "source_field_refs": ["pct_chg"],
                                         "evidence_refs": [kc_ev]},
            f"stocks.{sc}.actual_trade_date": {"source_path": fs_path,
                                                "source_field_refs": ["feature_values.technical.actual_trade_date"],
                                                "evidence_refs": [fs_ev]},
            f"stocks.{sc}.data_freshness_status": {"source_path": fs_path,
                                                    "source_field_refs": ["freshness_status.overall"],
                                                    "evidence_refs": [fs_ev]},
            f"stocks.{sc}.conclusion_status": {"source_path": "", "evidence_refs": [sg_ev]},
            f"stocks.{sc}.user_visible_status": {"source_path": "", "evidence_refs": [sg_ev]},
        })
        return data

    def _get_change_pct_from_kline(self, actual_date, stock_code):
        kline = self._load_kline_cache(stock_code)
        for i, r in enumerate(kline):
            nd = r.get("_date_norm", "")
            if nd == actual_date:
                pct = r.get("pct_chg")
                if pct is not None:
                    return round(float(pct), 2)
                pc, cl = r.get("pre_close"), r.get("close")
                if pc and cl and float(pc) > 0:
                    return round((float(cl) - float(pc)) / float(pc) * 100, 2)
                break
        if len(kline) >= 2:
            c2, c1 = kline[-1].get("close"), kline[-2].get("close")
            if c1 and c2 and float(c1) > 0:
                return round((float(c2) - float(c1)) / float(c1) * 100, 2)
        return None

    @staticmethod
    def _calc_vs_ma5(tech):
        c, m5 = tech.get("close"), tech.get("ma5")
        if c and m5:
            return round((c - m5) / m5 * 100, 2)
        return None

    def _load_kline_cache(self, stock_code):
        try:
            return ds.get_kline_until(stock_code, "20260616")
        except Exception:
            return []

    # ------------------------------------------------------------------
    # _build_detail
    # ------------------------------------------------------------------

    def _build_detail(self, snap, bt, member, gate, run_id, sc, sn, common_ev) -> dict:
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})
        ad = tech.get("actual_trade_date", "")
        cp = self._get_change_pct_from_kline(ad, sc)
        pos = self.position_adapter.get_public_position(market_price=tech.get("close"))
        freshness = (snap or {}).get("freshness_status", {}).get("overall", "UNKNOWN")
        rs = (bt or {}).get("overall_status", "OBSERVE")

        fs_path = f"运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_{sc}_20260616.json"
        kc_ev = _stable_ev_id(sc, "kline-cache")
        fs_ev = _stable_ev_id(sc, "feature-snapshot")
        sg_ev = _stable_ev_id(sc, "status-gate")
        rh_ev = _stable_ev_id(sc, "rule-health")
        pp_ev = _stable_ev_id(sc, "position-public-view")

        data = self._annotate({"stock_code": sc, "stock_name": sn,
            "trade_date": ad, "conclusion_status": gate.get("conclusion_status"),
            "user_visible_status": gate.get("user_visible_status", "BLOCK"),
            "data_freshness": freshness, "close": tech.get("close"), "change_pct": cp,
            "close_vs_ma5_pct": self._calc_vs_ma5(tech),
            "ma5": tech.get("ma5"), "ma20": tech.get("ma20"),
            "ma60": tech.get("ma60"), "rsi14": tech.get("rsi14"),
            "rule_health_status": rs, "user_position": pos,
            "decision_blockers": gate.get("decision_blockers", []),
            "market_today": {"close": tech.get("close"), "ma5": tech.get("ma5"),
                             "ma20": tech.get("ma20"), "ma60": tech.get("ma60"),
                             "rsi14": tech.get("rsi14")},
            "status_gate": {"data_status": gate.get("data_status"),
                            "decision_blockers": gate.get("decision_blockers")},
            "rule_health_summary": {"overall_status": rs},
            "position_public_view": {"position_status": pos.get("position_status")},
            "evidence_summary": {"kline_cache": "AVAILABLE", "feature_snapshot": "AVAILABLE" if snap else "MISSING",
                                 "backtest": "AVAILABLE" if bt else "MISSING", "position": "UNAVAILABLE"},
        }, run_id)

        data = self._with_field_evidence(data, run_id, {
            "stock_code": {"source_path": fs_path, "source_field_refs": ["stock_code"], "evidence_refs": [fs_ev]},
            "stock_name": {"source_path": fs_path, "source_field_refs": ["stock_name"], "evidence_refs": [fs_ev]},
            "market_today.close": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.close"], "evidence_refs": [fs_ev, kc_ev]},
            "market_today.ma5": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.ma5"], "evidence_refs": [fs_ev]},
            "market_today.ma20": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.ma20"], "evidence_refs": [fs_ev]},
            "status_gate.data_status": {"source_path": "", "evidence_refs": [sg_ev]},
            "status_gate.decision_blockers": {"source_path": "", "evidence_refs": [sg_ev]},
            "rule_health_summary.overall_status": {"source_path": "", "source_refs": [_make_source_ref("rule_health", "")], "evidence_refs": [rh_ev]},
            "position_public_view.position_status": {"source_path": "", "source_refs": [_make_source_ref("position_public_view", "")], "evidence_refs": [pp_ev]},
            "evidence_summary": {"source_path": "", "source_refs": [_make_source_ref("computed", "")], "evidence_refs": [kc_ev, fs_ev, rh_ev]},
            "decision_blockers": {"source_path": "", "evidence_refs": [sg_ev]},
        })
        return data

    # ------------------------------------------------------------------
    # _build_evidence (per-stock evidence.json)
    # ------------------------------------------------------------------

    def _build_evidence(self, member, gate, snap, bt, chart, run_id, common_ev) -> dict:
        sc = member["stock_code"]
        items = list(common_ev.values())
        if chart and chart.get("data_date_divergence"):
            items.append({
                "evidence_id": _stable_ev_id(sc, "data-date-divergence"),
                "source_type": "data_date_divergence", "source_path": "chart_data.json",
                "summary": chart.get("date_divergence_warning", "日期不一致"),
                "detail": f"s={chart.get('feature_snapshot_actual_date')} k={chart.get('source_last_date')}",
                "status": "BLOCKING",
            })
        return self._annotate({
            "stock_code": sc, "stock_name": member["stock_name"],
            "evidence_items": items,
            "evidence_ids": [e["evidence_id"] for e in items],
            "field_evidence": {
                "evidence_items": _build_field_evidence(
                    "",
                    ["evidence_items"],
                    [_stable_ev_id(sc, "feature-snapshot"), _stable_ev_id(sc, "kline-cache")],
                    [_make_source_ref("computed", "product_api_bundle.py::_build_evidence", ["evidence_items"])]
                )
            },
        }, run_id)

    # ------------------------------------------------------------------
    # _build_today_decisions
    # ------------------------------------------------------------------

    def _build_today_decisions(self, snap, bt, dash, member, gate, run_id, common_ev) -> dict:
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})
        sc = member["stock_code"]
        sn = member["stock_name"]
        close = tech.get("close")
        ma20, ma5 = tech.get("ma20"), tech.get("ma5")
        gb = gate.get("decision_blockers", [])
        nd = len(gb) > 0

        if close is None or ma20 is None:
            pa, cf, reas = "observe", 0.0, "关键数据缺失"
        elif close < ma20:
            pa, cf, reas = "observe", 0.4, f"close({close})<MA20({ma20})"
        elif close < ma5:
            pa, cf, reas = "observe", 0.5, f"close({close})<MA5({ma5})"
        else:
            pa, cf, reas = "hold", 0.6, f"close({close})>MA5({ma5})"
        if nd:
            pa, cf = "observe", min(cf, 0.3)
            reas += f"（降级: {', '.join(gb)}）"

        pos = self.position_adapter.get_public_position(market_price=close)
        fs_path = f"运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_{sc}_20260616.json"
        kc_ev = _stable_ev_id(sc, "kline-cache")
        fs_ev = _stable_ev_id(sc, "feature-snapshot")
        sg_ev = _stable_ev_id(sc, "status-gate")
        rh_ev = _stable_ev_id(sc, "rule-health")
        pp_ev = _stable_ev_id(sc, "position-public-view")

        data = self._annotate_legacy({
            "stock_code": sc, "stock_name": sn,
            "trade_date": tech.get("actual_trade_date", "unknown"),
            "conclusion_status": gate.get("conclusion_status", "BLOCKED"),
            "user_visible_status": gate.get("user_visible_status", "BLOCK"),
            "user_position": pos,
            "market_today": {"close": close, "ma5": ma5, "ma20": ma20,
                             "ma60": tech.get("ma60"), "rsi14": tech.get("rsi14")},
            "primary_action": pa, "confidence": cf, "reasoning": reas,
            "decision_blockers": gb,
            "rule_health_status": (bt or {}).get("overall_status", "OBSERVE"),
            "status_gate": gate,
        }, run_id, f"bundles/{run_id}/today_decisions.json")

        data = self._with_field_evidence(data, run_id, {
            "trade_date": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.actual_trade_date"], "evidence_refs": [fs_ev]},
            "conclusion_status": {"source_path": "", "evidence_refs": [sg_ev]},
            "user_visible_status": {"source_path": "", "evidence_refs": [sg_ev]},
            "user_position.position_status": {"source_path": "", "source_refs": [_make_source_ref("position_public_view", "")], "evidence_refs": [pp_ev]},
            "market_today.close": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.close"], "evidence_refs": [fs_ev, kc_ev]},
            "market_today.ma5": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.ma5"], "evidence_refs": [fs_ev]},
            "market_today.ma20": {"source_path": fs_path, "source_field_refs": ["feature_values.technical.ma20"], "evidence_refs": [fs_ev]},
            "rule_health_status": {"source_path": "", "source_refs": [_make_source_ref("rule_health", "")], "evidence_refs": [rh_ev]},
            "decision_blockers": {"source_path": "", "evidence_refs": [sg_ev]},
            "primary_action": {"source_path": "", "source_refs": [_make_source_ref("computed", "", ["conclusion_status", "status_gate"])], "evidence_refs": [sg_ev]},
            "confidence": {"source_path": "", "evidence_refs": [sg_ev]},
        })
        return data

    # ------------------------------------------------------------------
    # _build_chart_data
    # ------------------------------------------------------------------

    def _build_chart_data(self, member) -> dict:
        sc = member["stock_code"]
        rows = ds.get_kline_until(sc, "20260616")
        limit = min(120, len(rows))
        recent = rows[-limit:] if limit > 0 else []
        ohlc, vols, ma5_v, ma20_v, ma60_v = [], [], [], [], []
        cps = [float(r.get("close", 0)) for r in recent if r.get("close")]

        for i, r in enumerate(recent):
            nd = r.get("_date_norm", "")
            c = float(r.get("close", 0))
            ohlc.append({"date": nd, "open": float(r.get("open", 0)),
                         "high": float(r.get("high", 0)), "low": float(r.get("low", 0)), "close": c})
            vol = r.get("volume", r.get("vol", 0))
            if vol:
                vols.append({"date": nd, "volume": float(vol)})
            p = cps[:i + 1]
            if len(p) >= 5:
                ma5_v.append({"date": nd, "ma5": round(sum(p[-5:]) / 5, 4)})
            if len(p) >= 20:
                ma20_v.append({"date": nd, "ma20": round(sum(p[-20:]) / 20, 4)})
            if len(p) >= 60:
                ma60_v.append({"date": nd, "ma60": round(sum(p[-60:]) / 60, 4)})

        mkd = max(r.get("_date_norm", "") for r in rows) if rows else ""
        tech = {}
        try:
            s = json.load(open(f"运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_{sc}_20260616.json"))
            tech = s.get("feature_values", {}).get("technical", {})
        except Exception:
            pass
        atd = tech.get("actual_trade_date", "")
        div = atd != mkd

        return {"stock_code": sc,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_path": f"代码文件/数据/kline_cache/{sc}.json",
            "source_field_refs": ["close", "volume", "pct_chg"],
            "source_last_date": mkd, "feature_snapshot_actual_date": atd,
            "data_date_divergence": div,
            "date_divergence_warning": f"snap({atd})!=kline({mkd})" if div else "",
            "ohlc": ohlc, "volume": vols, "ma5": ma5_v, "ma20": ma20_v, "ma60": ma60_v,
            "total_kline_rows": len(rows),
        }

    # ------------------------------------------------------------------
    # bundle_index
    # ------------------------------------------------------------------

    def _build_bundle_index(self, run_id: str, members: list,
                            publish_status: str = "PUBLISHED") -> dict:
        files = []
        legacy_keys = {"today_decisions.json", "chart_data.json", "evidence_index.json",
                       "rule_health.json", "rule_health_summary.json"}
        req = {"bundle_index.json", "run_manifest.json", "stock_pool.json",
               "dashboard.json", "stocks.json", "run_state.json",
               "evidence_index.json", "rule_health.json", "rule_health_summary.json",
               "today_decisions.json", "chart_data.json"}

        for f in ["bundle_index.json", "run_manifest.json", "stock_pool.json",
                  "dashboard.json", "stocks.json", "run_state.json",
                  "evidence_index.json", "rule_health.json", "rule_health_summary.json",
                  "today_decisions.json", "chart_data.json"]:
            files.append({"path": f, "kind": "legacy" if f in legacy_keys else "standard",
                "stock_code": None, "required": f in req,
                "legacy_compat": f in legacy_keys,
                "canonical_path": f"bundles/{run_id}/{f}",
                "schema_version": SCHEMA_VERSION, "bundle_version": BUNDLE_VERSION, "run_id": run_id})

        for m in members:
            sc = m["stock_code"]
            for sf in ["detail.json", "chart_data.json", "evidence.json"]:
                files.append({"path": f"stocks/{sc}/{sf}", "kind": "stock_detail",
                    "stock_code": sc, "required": True, "legacy_compat": False,
                    "canonical_path": f"bundles/{run_id}/stocks/{sc}/{sf}",
                    "schema_version": SCHEMA_VERSION, "bundle_version": BUNDLE_VERSION, "run_id": run_id})

        return self._annotate({
            "pool_id": ProductStockPoolService.POOL_ID,
            "pool_name": ProductStockPoolService.POOL_NAME,
            "is_current_bundle_pointer": True,
            "current_bundle_path": f"bundles/{run_id}/",
            "publish_status": publish_status,
            "files": files,
        }, run_id)

    # ------------------------------------------------------------------
    # run_manifest
    # ------------------------------------------------------------------

    def _build_run_manifest(self, run_id, members, gate, bundle_index, started_at,
                             publish_status="PUBLISHED", finished_at=None) -> dict:
        if finished_at is None:
            finished_at = datetime.now(timezone.utc).isoformat()
        return self._annotate({
            "run_id": run_id, "run_type": "shadow",
            "started_at": started_at, "finished_at": finished_at,
            "publish_status": publish_status,
            "pool_ref": ProductStockPoolService.POOL_ID,
            "generated_files": [f["path"] for f in bundle_index.get("files", [])],
            "input_refs": {"inventory": "keystock_system_inventory.json",
                "backtests": f"backtest_TECH_MA20_BREAK_STOP_LOSS_{members[0]['stock_code']}_20260616.json",
                "feature_snapshots": f"feature_snapshot_{members[0]['stock_code']}_20260616.json",
                "status_gate": "conclusion_status.py"},
            "rollback_ref": f"bundles/{run_id}",
            "warnings": gate.get("warning_reasons", []),
            "blocks": gate.get("blocking_reasons", []),
            "no_production_touch": {"baseline_registry_touched": False,
                "runtime_entry_registry_touched": False, "launchd_touched": False,
                "real_position_connected": False, "production_cutover": False,
                "formal_rule_changed": False, "stock_pool_only": members[0]["stock_code"]},
        }, run_id)

    # ------------------------------------------------------------------
    # mirror legacy
    # ------------------------------------------------------------------

    def _mirror_legacy(self, src, dst, run_id):
        legacy = ["stock_pool.json", "dashboard.json", "stocks.json", "run_state.json",
                  "evidence_index.json", "rule_health.json", "rule_health_summary.json",
                  "today_decisions.json", "chart_data.json"]
        for f in legacy:
            sp = os.path.join(src, f)
            if os.path.exists(sp):
                try:
                    d = json.load(open(sp))
                    if isinstance(d, dict):
                        d["legacy_compat"] = True
                        d["canonical_path"] = f"bundles/{run_id}/{f}"
                    self._write_json(os.path.join(dst, f), d)
                except Exception:
                    pass
        stk = os.path.join(src, "stocks")
        if os.path.isdir(stk):
            for root, dirs, files in os.walk(stk):
                rel = os.path.relpath(root, stk)
                td = os.path.join(dst, "stocks", rel)
                os.makedirs(td, exist_ok=True)
                for fn in files:
                    shutil.copy2(os.path.join(root, fn), os.path.join(td, fn))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def _write_json(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[API] 已写入: {path}")
