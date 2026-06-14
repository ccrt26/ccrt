#!/usr/bin/env python3
import argparse, json, hashlib, datetime
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
STORE = ROOT / "统一解读/eval_hooks/store"
OUT = ROOT / "00_项目地基/08_审计与验收"
RUN_ID = "F-FIX-EVAL-HOOK-PENDING-CLOSURE-20260614-R6"
EVALUATED = {"命中", "部分命中", "失败", "不可评估"}

def load(p): return json.loads(p.read_text(encoding="utf-8-sig"))
def dump(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def code6(x): return (x or "").split(".")[0][-6:] if x else ""

def walk(obj, code):
    if isinstance(obj, dict):
        c = code6(str(obj.get("Code") or obj.get("code") or obj.get("stock_code") or obj.get("证券代码") or ""))
        if c == code:
            for k in ("Price", "price", "Close", "close", "收盘", "收盘价", "current_price"):
                if k in obj and obj[k] not in ("", None):
                    try: return float(obj[k])
                    except Exception: pass
        for v in obj.values():
            r = walk(v, code)
            if r is not None: return r
    if isinstance(obj, list):
        for v in obj:
            r = walk(v, code)
            if r is not None: return r
    return None

def price_on(code, ymd):
    for p in [
        ROOT / f"历史数据/01_交易快照/unified_snapshot_{ymd}.json",
        ROOT / f"历史数据/04_原始数据/{ymd}_data_full.json",
        ROOT / f"历史数据/04_原始数据/{ymd}_data_scored.json",
        ROOT / f"历史数据/04_原始数据/{ymd}_data_final.json",
    ]:
        if p.exists():
            r = walk(load(p), code)
            if r is not None:
                return {"date": ymd, "price": r, "source": str(p.relative_to(ROOT))}
    return None

def resolve_price(code, iso_date):
    if not iso_date:
        return None
    d = datetime.date.fromisoformat(iso_date)
    for delta in range(0, 4):
        r = price_on(code, (d + datetime.timedelta(days=delta)).strftime("%Y%m%d"))
        if r: return r
    return None

def judge(action, pct):
    if action in ("BUY", "HOLD"):
        return "命中" if pct >= 0.5 else ("部分命中" if pct > -0.5 else "失败")
    if action == "SELL":
        return "命中" if pct <= -0.5 else ("部分命中" if pct < 0.5 else "失败")
    if action in ("WATCH", "NEUTRAL"):
        return "命中" if abs(pct) <= 2.0 else "部分命中"
    return "不可评估"

def overall(vals):
    if not vals or all(x == "不可评估" for x in vals): return "不可评估"
    if vals.count("失败") >= 2: return "失败"
    if vals.count("命中") >= 2: return "命中"
    return "部分命中"

def mark_unassessable(h, reason, actual):
    for k in ("t1_check", "t3_check", "t5_check"):
        h.setdefault(k, {})
        h[k]["actual"] = actual
        h[k]["result"] = "不可评估"
    h["comprehensive_result"] = "不可评估"
    h["closure_reason"] = reason
    h["evaluation_status"] = "closed_unassessable"

def process(path, write=False):
    h = load(path)
    before = sha(path)
    code = code6(h.get("stock_code"))
    trade_date = h.get("trade_date")
    legacy = h.get("legacy_missing_interpretation") is True
    now = datetime.datetime.now().isoformat(timespec="seconds")

    if legacy or not code or not trade_date:
        mark_unassessable(h, "legacy_missing_interpretation_or_missing_identity",
                          "不可评估：缺少原始解释对象、stock_code 或 trade_date，禁止伪造行情评估")
    else:
        base = resolve_price(code, trade_date)
        results, evidence_found = [], False
        for k in ("t1_check", "t3_check", "t5_check"):
            chk = h.setdefault(k, {})
            px = resolve_price(code, chk.get("check_date", ""))
            if base and px:
                pct = round((px["price"] / base["price"] - 1) * 100, 2)
                chk["actual"] = f"base_date={base['date']} base_price={base['price']} check_date={px['date']} check_price={px['price']} change_pct={pct}% source={px['source']}"
                chk["result"] = judge(h.get("action_bias"), pct)
                evidence_found = True
            else:
                chk["actual"] = f"数据不足：base={base} check={px}"
                chk["result"] = "不可评估"
            results.append(chk["result"])
        if evidence_found:
            h["comprehensive_result"] = overall(results)
            h["closure_reason"] = "evaluated_by_local_price_direction_proxy"
            h["evaluation_status"] = "closed_evaluated"
        else:
            h["comprehensive_result"] = "不可评估"
            h["closure_reason"] = "local_price_data_missing"
            h["evaluation_status"] = "closed_unassessable"

    h.setdefault("evaluated_at", now)
    h["evaluation_evidence"] = {
        "method": "local_price_direction_proxy_v1",
        "before_sha256": before,
        "identity": {"stock_code": h.get("stock_code"), "trade_date": h.get("trade_date")},
        "note": "closed_evaluated requires price evidence; data-missing cases are closed_unassessable"
    }
    if h.get("comprehensive_result") == "失败":
        h["failure_attribution"] = h.get("failure_attribution") or "不适用"

    if write:
        dump(path, h)

    text = json.dumps(h, ensure_ascii=False)
    return {
        "file": str(path.relative_to(ROOT)),
        "result": h.get("comprehensive_result"),
        "status": h.get("evaluation_status"),
        "reason": h.get("closure_reason"),
        "has_change_pct": "change_pct=" in text,
        "legacy_missing_interpretation": h.get("legacy_missing_interpretation") is True,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = [process(p, args.write) for p in sorted(STORE.glob("*.json"))]
    counts = {}
    status_counts = {}
    for r in rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    summary = {
        "run_id": RUN_ID,
        "candidate_only": True,
        "no_role_signoff_claimed": True,
        "write_mode": args.write,
        "total_hooks": len(rows),
        "counts": counts,
        "status_counts": status_counts,
        "closed_evaluated_with_change_pct": sum(1 for r in rows if r["status"] == "closed_evaluated" and r["has_change_pct"]),
        "closed_evaluated_without_change_pct": [r["file"] for r in rows if r["status"] == "closed_evaluated" and not r["has_change_pct"]],
        "legacy_bad": [r["file"] for r in rows if r["legacy_missing_interpretation"] and r["result"] != "不可评估"],
        "rows": rows,
    }

    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        g4 = OUT / f"{RUN_ID}_G4_self_check_candidate.json"
        dump(g4, summary)
        for gate in ("G5_review_candidate", "G6_release_candidate"):
            dump(OUT / f"{RUN_ID}_{gate}.json", {
                "run_id": RUN_ID,
                "gate": gate,
                "candidate_only": True,
                "no_role_signoff_claimed": True,
                "source_g4": str(g4.relative_to(ROOT)),
                "verdict": "PASS" if not summary["closed_evaluated_without_change_pct"] and not summary["legacy_bad"] else "BLOCK"
            })
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
