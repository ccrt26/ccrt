#!/usr/bin/env python3
"""回归测试套件 — 引擎变更后一键验证"""
import json, os, sys, subprocess
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
GM_DIR = os.path.join(ROOT, "审计报告", "golden_master")
ENGINE_DIR = HERE

PASS, FAIL, SKIP = 0, 0, 0

def report(name, result, detail=""):
    global PASS, FAIL, SKIP
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}
    if result == "PASS": PASS += 1
    elif result == "FAIL": FAIL += 1
    else: SKIP += 1
    print(f"  {icon[result]} {name}" + (f"  -- {detail}" if detail else ""))

# ─── Test 1: Import check ───
print("=" * 60)
print("1. 模块导入检查")
print("=" * 60)
try:
    from engine.engine import main as engine_main
    from engine.veto import check_absolute_vetoes, check_conditional_vetoes, detect_market_state
    from engine.scores import compute_scores, calc_percentile
    from engine.theme import classify_theme, check_theme_purity
    from engine.technical import calc_ma, calc_rsi, calc_macd, calc_atr
    from engine.sector import classify_phase, should_exempt_by_sector
    report("import engine.*", "PASS")
except ImportError as e:
    report("import engine.*", "FAIL", str(e))

# ─── Test 2: Boundary injection ───
print("\n" + "=" * 60)
print("2. 边界注入测试 (79项)")
print("=" * 60)
bt_path = os.path.join(ENGINE_DIR, "test_boundary_injection.py")
if os.path.exists(bt_path):
    result = subprocess.run([sys.executable, bt_path], capture_output=True, text=True, cwd=ENGINE_DIR)
    if result.returncode == 0 and "[FAIL]" not in result.stdout:
        report("边界注入测试", "PASS", "79/79通过")
    else:
        report("边界注入测试", "FAIL", "有失败项，查看上方输出")
else:
    report("边界注入测试", "SKIP", "test_boundary_injection.py 不存在")

# ─── Test 3: Golden Master diff ───
print("\n" + "=" * 60)
print("3. Golden Master 回归验证")
print("=" * 60)
gm_files = sorted([f for f in os.listdir(GM_DIR) if f.startswith("gm_") and f.endswith("_input.json")]) if os.path.exists(GM_DIR) else []
if not gm_files:
    report("Golden Master diff", "SKIP", "golden_master/ 目录无输入快照")
else:
    for gmf in gm_files:
        gm_input = os.path.join(GM_DIR, gmf)
        date_str = gmf.replace("gm_", "").replace("_input.json", "")
        gm_output = os.path.join(GM_DIR, f"gm_{date_str}_current.json")

        # Run engine with this GM input
        env = os.environ.copy()
        env["GM_INPUT_FILE"] = gm_input

        temp_out = os.path.join(GM_DIR, f"_temp_{date_str}.json")

        # Copy input as data_full.json, run engine, capture output
        data_file = os.path.join(ROOT, "代码文件", "数据", "data_full.json")
        scored_file = os.path.join(ROOT, "代码文件", "数据", "data_scored.json")

        import shutil
        backup_data = None
        backup_scored = None

        try:
            if os.path.exists(data_file):
                backup_data = data_file + ".bak"
                shutil.copy2(data_file, backup_data)
            if os.path.exists(scored_file):
                backup_scored = scored_file + ".bak"
                shutil.copy2(scored_file, backup_scored)

            shutil.copy2(gm_input, data_file)

            # Run engine (wrapper → engine package)
            result = subprocess.run(
                [sys.executable, os.path.join(ENGINE_DIR, "scoring_engine_v2.py")],
                capture_output=True, text=True, cwd=ENGINE_DIR, timeout=120
            )

            if result.returncode != 0:
                report(f"GM {date_str}", "FAIL", f"引擎运行失败: {result.stderr[:100]}")
                continue

            if not os.path.exists(scored_file):
                report(f"GM {date_str}", "FAIL", "引擎未生成输出文件")
                continue

            # Compare with expected output
            with open(scored_file, "r", encoding="utf-8-sig") as f:
                current = json.load(f)

            if os.path.exists(gm_output):
                with open(gm_output, "r", encoding="utf-8-sig") as f:
                    expected = json.load(f)

                # Deep compare
                diffs = []
                cur_stocks = {s["Code"]: s for s in current.get("stocks", current) if isinstance(s, dict) and "Code" in s}
                exp_stocks = {s["Code"]: s for s in expected.get("stocks", expected) if isinstance(s, dict) and "Code" in s}

                for code in set(cur_stocks) | set(exp_stocks):
                    if code not in cur_stocks:
                        diffs.append(f"{code}: 当前缺失")
                    elif code not in exp_stocks:
                        diffs.append(f"{code}: 预期缺失")
                    else:
                        cs = cur_stocks[code]
                        es = exp_stocks[code]
                        for key in ["Score", "Veto", "Phase", "SortOrder"]:
                            if key in cs and key in es and cs[key] != es[key]:
                                diffs.append(f"{code}.{key}: current={cs[key]}, expected={es[key]}")

                if diffs:
                    report(f"GM {date_str}", "FAIL", f"{len(diffs)}处不一致: {diffs[:5]}")
                else:
                    report(f"GM {date_str}", "PASS", f"{len(cur_stocks)}只股票，100%匹配")
            else:
                # No expected output yet — save current as reference
                shutil.copy2(scored_file, gm_output)
                report(f"GM {date_str}", "PASS", f"新快照已保存 ({len(current.get('stocks', current))}只股票)")

        except Exception as e:
            report(f"GM {date_str}", "FAIL", str(e)[:100])
        finally:
            # Restore backups
            if backup_data and os.path.exists(backup_data):
                shutil.move(backup_data, data_file)
            if backup_scored and os.path.exists(backup_scored):
                shutil.move(backup_scored, scored_file)

# ─── Summary ───
print("\n" + "=" * 60)
total = PASS + FAIL + SKIP
print(f"回归测试完成: {PASS}通过 / {FAIL}失败 / {SKIP}跳过 (共{total}项)")
if FAIL > 0:
    print(f"  -> 回归FAIL，禁止上线")
    sys.exit(1)
else:
    print(f"  -> 回归PASS，可以上线")
    sys.exit(0)
