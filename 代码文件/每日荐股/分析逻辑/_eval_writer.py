#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""post_eval_engine.py 的 CSV 输出辅助 — L0 工具层"""
import csv, os
from datetime import date

DIM_CONFIG = {
    "tech":   {"label": "技术面", "max": 20, "key": "S_Tech"},
    "money":  {"label": "资金面", "max": 20, "key": "S_Money"},
    "fund":   {"label": "基本面", "max": 15, "key": "S_Fund"},
    "news":   {"label": "消息面", "max": 15, "key": "S_News"},
    "sector": {"label": "板块趋势", "max": 20, "key": "S_SectorTrend"},
}


def write_records_csv(recs, report_date, records_path):
    """追加逐股记录到 records.csv"""
    os.makedirs(os.path.dirname(records_path), exist_ok=True)

    fieldnames = [
        "eval_date", "report_date", "stock_code", "stock_name",
        "total_score", "rating", "tier", "c8_blocked", "market_stage",
        "buy_price", "sell_price", "return_pct", "profit",
        "misjudge_dim", "misjudge_subtype",
        "tech_expected", "money_expected", "sector_expected", "news_expected",
        "veto_type", "exemption_flag", "volume_ratio",
        "bellwether_code", "bellwether_return", "notes",
        "ret_t3", "ret_t5",
    ]

    file_exists = os.path.exists(records_path)
    today = date.today().strftime("%Y%m%d")

    with open(records_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()

        for r in recs:
            ret = r.get("ret_t1")
            profit = "盈利" if (ret or 0) > 0 else ("亏损" if (ret or 0) < 0 else "持平")
            row = {
                "eval_date": today,
                "report_date": report_date.replace("-", ""),
                "stock_code": r.get("code", ""),
                "stock_name": r.get("name", ""),
                "total_score": r.get("TotalScore", 0),
                "rating": r.get("rating", ""),
                "tier": r.get("tier", ""),
                "c8_blocked": "Y" if r.get("c8_blocked") else "",
                "return_pct": round(ret, 2) if ret is not None else "",
                "profit": profit,
                "ret_t3": round(r.get("ret_t3"), 2) if r.get("ret_t3") is not None else "",
                "ret_t5": round(r.get("ret_t5"), 2) if r.get("ret_t5") is not None else "",
                "notes": "-",
            }
            if ret is not None and ret < -3:
                for dim_key, cfg in DIM_CONFIG.items():
                    if r.get(cfg["key"], 0) >= cfg["max"] * 0.6:
                        row["misjudge_dim"] = f"{cfg['label']}误判"
                        break
            writer.writerow(row)


def write_summary_csv(core, dim_misjudge, veto, summary_path):
    """追加汇总统计到 summary.csv"""
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    fieldnames = [
        "period", "start_date", "end_date", "total_recommendations",
        "wins", "losses", "win_rate", "total_profit", "total_loss",
        "profit_loss_ratio", "portfolio_return", "hs300_return", "excess_return",
        "tech_misjudge_rate", "money_misjudge_rate",
        "sector_misjudge_rate", "news_misjudge_rate",
        "veto_kill_rate", "exemption_win_rate",
        "recommended_win_rate", "vetoed_win_rate",
        "market_win_rate", "veto_effectiveness", "score_distinction",
    ]

    file_exists = os.path.exists(summary_path)
    today = date.today().strftime("%Y%m%d")
    pl_ratio = core.get("profit_loss_ratio", 0)

    with open(summary_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()

        row = {
            "period": "single",
            "start_date": today, "end_date": today,
            "total_recommendations": core.get("total_recs", 0),
            "wins": core.get("wins", 0), "losses": core.get("losses", 0),
            "win_rate": core.get("win_rate", 0),
            "total_profit": round(core.get("portfolio_return", 0), 2),
            "total_loss": round(abs(core.get("portfolio_return", 0)), 2) if core.get("portfolio_return", 0) < 0 else 0,
            "profit_loss_ratio": pl_ratio,
            "portfolio_return": core.get("portfolio_return", 0),
            "hs300_return": core.get("hs300_return", 0),
            "excess_return": core.get("excess_return", 0),
            "tech_misjudge_rate": dim_misjudge.get("技术面", {}).get("rate", 0),
            "money_misjudge_rate": dim_misjudge.get("资金面", {}).get("rate", 0),
            "sector_misjudge_rate": dim_misjudge.get("板块趋势", {}).get("rate", 0),
            "news_misjudge_rate": dim_misjudge.get("消息面", {}).get("rate", 0),
            "veto_kill_rate": veto.get("miskill_rate", 0),
            "recommended_win_rate": veto.get("recommended_win_rate", 0),
            "vetoed_win_rate": veto.get("veto_win_rate", 0),
            "veto_effectiveness": veto.get("veto_effectiveness", 0),
            "score_distinction": core.get("score_distinction_70", 0),
        }
        writer.writerow(row)
