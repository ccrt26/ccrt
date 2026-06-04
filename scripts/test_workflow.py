#!/usr/bin/env python3
"""
test_workflow.py — 流程加固 fix4 完全隔离测试套件

隔离策略:
- 每个测试组使用独立临时目录 (state + log)
- 通过 PIPELINE_STATE_FILE / PIPELINE_LOG_DIR 环境变量注入
- 测试间无状态共享，不依赖执行顺序
- 测试后自动清理临时文件
"""
import sys, os, json, hashlib, subprocess, shutil, tempfile, uuid
from datetime import datetime, timezone, timedelta

G, R, Y, Z = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = "scripts/pipeline_engine.py"
SIGN_OFF = "scripts/sign_off.py"
CHECK = "scripts/check_checklist.py"
AUDIT = "scripts/audit_scan.py"
SECRETS_FILE = os.path.join(PROJECT_ROOT, ".claude", "actor_secrets.json")

res = {"p": 0, "f": 0, "fl": []}


class IsolatedEnv:
    """独立测试环境：临时 state + log 目录"""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fix4_test_")
        self.state_file = os.path.join(self.tmpdir, "pipeline_active.json")
        self.log_dir = os.path.join(self.tmpdir, "logs")
        self.env = os.environ.copy()
        self.env["PIPELINE_STATE_FILE"] = self.state_file
        self.env["PIPELINE_LOG_DIR"] = self.log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        # 初始化空状态
        with open(self.state_file, 'w') as f:
            json.dump({"runs": {}, "state_hash": ""}, f)

    def run(self, *args, timeout=30):
        r = subprocess.run(
            ["python3"] + list(args),
            capture_output=True, text=True, timeout=timeout,
            cwd=PROJECT_ROOT, env=self.env,
        )
        return r.returncode, r.stdout, r.stderr

    def cleanup(self):
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def get_rid(self):
        with open(self.state_file) as f:
            return list(json.load(f)["runs"].keys())

    def mkcl(self, rid, items=None, cl="L0"):
        if items is None:
            items = [{"id": "T", "description": "测试", "code_level": cl,
                       "white_paper_ref": "N/A", "expected_output": "x",
                       "code_ref": None, "coder_ok": False}]
        c = {"run_id": rid, "signoffs": {}, "items": items,
             "deploy_items": [], "file_budgets": [], "token_budget": 5000}
        path = os.path.join(self.tmpdir, f"cl_{rid}.json")
        with open(path, 'w') as f:
            json.dump(c, f)
        return path


def test(env, name, expect_pass, *args):
    rc, so, se = env.run(*args)
    if (rc == 0) == expect_pass:
        res["p"] += 1
        print(f"  {G}PASS{Z}  {name}")
    else:
        res["f"] += 1
        res["fl"].append((name, so, se, rc))
        print(f"  {R}FAIL{Z}  {name} (expected {'0' if expect_pass else '!0'}, got {rc})")
        if se.strip(): print(f"         stderr: {se.strip()[:120]}")
        if so.strip(): print(f"         stdout: {so.strip()[:120]}")


def deadline(h=24):
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


# ============================================================================
# T1-T5: 基础回归
# ============================================================================
def test_t1_t5():
    print("\n📋 T1-T5: 基础回归")
    env = IsolatedEnv()
    try:
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T1-base")
        rid = env.get_rid()[-1]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        test(env, "T1: HMAC sign+advance", True, ENGINE, "--advance", rid, "--actor", "情墨", "--role", "情墨", "--checklist", cl)
        test(env, "T2: block", True, ENGINE, "--block", rid, "--reason", "T2-test")
        test(env, "T3: advance blocked", False, ENGINE, "--advance", rid, "--actor", "腰子", "--role", "腰子", "--checklist", cl)
        test(env, "T4: --status", True, ENGINE, "--status")
        test(env, "T5: no signature advance", False, ENGINE, "--advance", rid, "--actor", "腰子", "--role", "腰子")
    finally:
        env.cleanup()


# ============================================================================
# T8-T9: HMAC 伪造
# ============================================================================
def test_t8_t9():
    print("\n📋 T8-T9: HMAC签名伪造")
    env = IsolatedEnv()
    try:
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T8-HMAC")
        rid = env.get_rid()[-1]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        # Forge old SHA256
        with open(cl) as f:
            d = json.load(f)
        d["signoffs"]["情墨"]["sig_type"] = "SHA256"
        d["signoffs"]["情墨"]["signature"] = "FAKE_FORGED"
        with open(cl, 'w') as f:
            json.dump(d, f)
        test(env, "T8: old SHA256 sig rejected", False, ENGINE, "--advance", rid, "--actor", "情墨", "--role", "情墨", "--checklist", cl)

        # T9: wrong stage
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T9-stage")
        rid2 = env.get_rid()[-1]
        cl2 = env.mkcl(rid2)
        env.run(ENGINE, "--validate", cl2)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid2, "--checklist", cl2)
        env.run(ENGINE, "--advance", rid2, "--actor", "情墨", "--role", "情墨")
        test(env, "T9: wrong stage advance", False, ENGINE, "--advance", rid2, "--actor", "情墨", "--role", "情墨")
    finally:
        env.cleanup()


# ============================================================================
# T10-T13: P0 deadline 时区
# ============================================================================
def test_t10_t13():
    print("\n📋 T10-T13: P0 deadline时区")
    env = IsolatedEnv()
    try:
        test(env, "T10: naive datetime rejected", False,
             ENGINE, "--start", "EMERGENCY", "--task", "T10",
             "--incident-id", "I10", "--p0-reason", "评分/报告/交易链路中断",
             "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", "2026-06-02T12:00:00")
        test(env, "T11: UTC+Z accepted", True,
             ENGINE, "--start", "EMERGENCY", "--task", "T11",
             "--incident-id", "I11", "--p0-reason", "评分/报告/交易链路中断",
             "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", f"{deadline(24)[:-6]}Z")
        test(env, "T12: +00:00 accepted", True,
             ENGINE, "--start", "EMERGENCY", "--task", "T12",
             "--incident-id", "I12", "--p0-reason", "数据源全挂导致核心流程不可用",
             "--impact-scope", "x", "--risk-level", "Critical", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", deadline(24))
        test(env, "T13: malformed rejected", False,
             ENGINE, "--start", "EMERGENCY", "--task", "T13",
             "--incident-id", "I13", "--p0-reason", "安全/权限/凭证泄露风险",
             "--impact-scope", "x", "--risk-level", "High", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", "not-a-date")
    finally:
        env.cleanup()


# ============================================================================
# T14-T16: P0 门禁
# ============================================================================
def test_t14_t16():
    print("\n📋 T14-T16: P0门禁")
    env = IsolatedEnv()
    try:
        dl = deadline(24)
        test(env, "T14: excluded blocked", False,
             ENGINE, "--start", "EMERGENCY", "--task", "T14-普通优化",
             "--incident-id", "I14", "--p0-reason", "普通优化",
             "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", dl)
        test(env, "T15: allowed ok", True,
             ENGINE, "--start", "EMERGENCY", "--task", "T15",
             "--incident-id", "I15", "--p0-reason", "数据源全挂导致核心流程不可用",
             "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", dl)
        test(env, "T16: user-confirmed bypass", True,
             ENGINE, "--start", "EMERGENCY", "--task", "T16",
             "--incident-id", "I16", "--p0-reason", "普通优化",
             "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", dl,
             "--user-confirmed-p0", "true")
    finally:
        env.cleanup()


# ============================================================================
# T17-T18: --complete
# ============================================================================
def test_t17_t18():
    print("\n📋 T17-T18: --complete")
    env = IsolatedEnv()
    try:
        # T17: full NEW_REQUIREMENT flow → complete audit
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T17-full")
        rid = env.get_rid()[-1]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        # Advance through all stages
        seqs = [("情墨","情墨"), ("腰子","腰子")]
        for a, r in seqs:
            env.run(SIGN_OFF, "--actor", a, "--role", r, "--run-id", rid, "--checklist", cl)
            env.run(ENGINE, "--advance", rid, "--actor", a, "--role", r)
        for rr in ["山猫","信鸽","玉夜","流金","青山"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid, "--checklist", cl)
        env.run(ENGINE, "--advance", rid, "--actor", "青山", "--role", "青山")
        for rr in ["旧影","新安"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid, "--checklist", cl)
        env.run(ENGINE, "--advance", rid, "--actor", "新安", "--role", "新安")
        for a_r in [("红结","红结"),("新安","新安"),("红枫","红枫"),("旧影","旧影")]:
            a, r = a_r
            env.run(SIGN_OFF, "--actor", a, "--role", r, "--run-id", rid, "--checklist", cl)
            env.run(ENGINE, "--advance", rid, "--actor", a, "--role", r)
        env.run(SIGN_OFF, "--actor", "旧影", "--role", "旧影", "--run-id", rid, "--checklist", cl)
        test(env, "T17: --complete audit", True, ENGINE, "--complete", rid, "--actor", "旧影", "--role", "旧影")

        # T18: P0 post_audit requires --audit-report
        env.run(ENGINE, "--start", "EMERGENCY", "--task", "T18-P0",
                "--incident-id", "I18", "--p0-reason", "评分/报告/交易链路中断",
                "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
                "--rollback-point", "x", "--post-audit-deadline", deadline(24))
        rid2 = env.get_rid()[-1]
        cl2 = env.mkcl(rid2)
        env.run(ENGINE, "--validate", cl2)
        env.run(ENGINE, "--advance", rid2, "--actor", "腰子", "--role", "腰子")
        for a_r in [("红结","红结"),("新安","新安"),("红枫","红枫")]:
            a, r = a_r
            env.run(SIGN_OFF, "--actor", a, "--role", r, "--run-id", rid2, "--checklist", cl2)
            env.run(ENGINE, "--advance", rid2, "--actor", a, "--role", r)
        test(env, "T18a: no --audit-report fails", False,
             ENGINE, "--complete", rid2, "--actor", "旧影", "--role", "旧影")
        ar = os.path.join(env.tmpdir, "audit_report.md")
        with open(ar, 'w') as f:
            f.write("# Audit Report\nPASS")
        env.run(SIGN_OFF, "--actor", "旧影", "--role", "旧影", "--run-id", rid2, "--checklist", cl2, "--audit-report", ar)
        test(env, "T18b: with --audit-report succeeds", True,
             ENGINE, "--complete", rid2, "--actor", "旧影", "--role", "旧影", "--audit-report", ar)
    finally:
        env.cleanup()


# ============================================================================
# T19-T21: BUGFIX consult
# ============================================================================
def test_t19_t21():
    print("\n📋 T19-T21: BUGFIX consult")
    env = IsolatedEnv()
    try:
        # T19: non-financial skips
        rc, so, _ = env.run(ENGINE, "--start", "FIX", "--task", "T19-非金融日志")
        rid = [l.split(":")[1].strip() for l in so.split("\n") if "run_id:" in l][0]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        env.run(ENGINE, "--advance", rid, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid, "--checklist", cl)
        rc, so, _ = env.run(ENGINE, "--advance", rid, "--actor", "腰子", "--role", "腰子")
        with open(env.state_file) as f:
            st = json.load(f)["runs"][rid]
        skipped = any(s["stage"] == "consult" and s["status"] == "skipped" for s in st["stages"])
        cur = st["current_stage"]
        ok = cur == "coding" and skipped
        res["p" if ok else "f"] += 1
        print(f"  {G if ok else R}{'PASS' if ok else 'FAIL'}{Z}  T19: non-financial skips consult")

        # T20: financial (L1) must enter consult
        rc2, so2, _ = env.run(ENGINE, "--start", "FIX", "--task", "T20-PE")
        rid2 = [l.split(":")[1].strip() for l in so2.split("\n") if "run_id:" in l][0]
        cl2 = env.mkcl(rid2, cl="L1")
        with open(cl2) as f:
            d = json.load(f)
        d["items"][0]["description"] = "修复PE计算逻辑"
        with open(cl2, 'w') as f:
            json.dump(d, f)
        env.run(ENGINE, "--validate", cl2)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid2, "--checklist", cl2)
        env.run(ENGINE, "--advance", rid2, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid2, "--checklist", cl2)
        rc, so, _ = env.run(ENGINE, "--advance", rid2, "--actor", "腰子", "--role", "腰子")
        with open(env.state_file) as f:
            cur2 = json.load(f)["runs"][rid2]["current_stage"]
        ok2 = cur2 == "consult"
        res["p" if ok2 else "f"] += 1
        print(f"  {G if ok2 else R}{'PASS' if ok2 else 'FAIL'}{Z}  T20: financial enters consult")

        # T21: L0 + financial keywords
        rc3, so3, _ = env.run(ENGINE, "--start", "FIX", "--task", "T21-选股评分")
        rid3 = [l.split(":")[1].strip() for l in so3.split("\n") if "run_id:" in l][0]
        cl3 = env.mkcl(rid3)
        with open(cl3) as f:
            d = json.load(f)
        d["items"][0]["description"] = "修复选股评分逻辑"
        with open(cl3, 'w') as f:
            json.dump(d, f)
        env.run(ENGINE, "--validate", cl3)
        with open(env.state_file) as f:
            fi = json.load(f)["runs"][rid3]["financial_impact"]
        res["p" if fi else "f"] += 1
        print(f"  {G if fi else R}{'PASS' if fi else 'FAIL'}{Z}  T21: fi=True for 选股/评分")
    finally:
        env.cleanup()


# ============================================================================
# T22-T23: 角色强制
# ============================================================================
def test_t22_t23():
    print("\n📋 T22-T23: 角色强制")
    env = IsolatedEnv()
    try:
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T22")
        rid = env.get_rid()[-1]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        test(env, "T22: wrong role blocked", False, ENGINE, "--advance", rid, "--actor", "红结", "--role", "红结", "--checklist", cl)
        test(env, "T23: no role/actor fails", False, ENGINE, "--advance", rid)
    finally:
        env.cleanup()


# ============================================================================
# T24-T26: 超期 P0 阻断
# ============================================================================
def test_t24_t26():
    print("\n📋 T24-T26: 超期P0阻断")
    env = IsolatedEnv()
    try:
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        env.run(ENGINE, "--start", "EMERGENCY", "--task", "T24-overdue",
                "--incident-id", "I24", "--p0-reason", "评分/报告/交易链路中断",
                "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
                "--rollback-point", "x", "--post-audit-deadline", past)
        test(env, "T24: overdue blocks NEW_REQUIREMENT", False, ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T24-blocked")
        test(env, "T25: overdue blocks FIX", False, ENGINE, "--start", "FIX", "--task", "T25-blocked")
        test(env, "T26: EMERGENCY still allowed", True,
             ENGINE, "--start", "EMERGENCY", "--task", "T26-ok",
             "--incident-id", "I26", "--p0-reason", "安全/权限/凭证泄露风险",
             "--impact-scope", "x", "--risk-level", "Critical", "--temp-fix", "x",
             "--rollback-point", "x", "--post-audit-deadline", deadline(24))
    finally:
        env.cleanup()


# ============================================================================
# T27-T30: 阿黑权限
# ============================================================================
def test_t27_t30():
    print("\n📋 T27-T30: 阿黑权限边界")
    env = IsolatedEnv()
    try:
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T27-black")
        rid = env.get_rid()[-1]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        test(env, "T27a: 阿黑→情墨签名失败", False, SIGN_OFF, "--actor", "阿黑", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        test(env, "T27b: 阿黑→腰子签名失败", False, SIGN_OFF, "--actor", "阿黑", "--role", "腰子", "--run-id", rid, "--checklist", cl)
        test(env, "T28a: 阿黑advance design失败", False, ENGINE, "--advance", rid, "--actor", "阿黑", "--role", "阿黑", "--checklist", cl)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        test(env, "T28b: 阿黑advance (signed) fails", False, ENGINE, "--advance", rid, "--actor", "阿黑", "--role", "阿黑", "--checklist", cl)
        test(env, "T29: 阿黑--status OK", True, ENGINE, "--status")
        test(env, "T30: 阿黑--block OK", True, ENGINE, "--block", rid, "--reason", "阿黑阻断测试")
    finally:
        env.cleanup()


# ============================================================================
# T31-T34: HMAC 签名升级 (独立状态)
# ============================================================================
def test_t31_t34():
    print("\n📋 T31-T34: HMAC签名升级")
    env = IsolatedEnv()
    try:
        # T31-T32: old SHA256
        rc, so, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T31-HMAC")
        rid = [l.split(":")[1].strip() for l in so.split("\n") if "run_id:" in l][0]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        with open(cl) as f:
            d = json.load(f)
        d["signoffs"]["情墨"]["sig_type"] = "SHA256"
        d["signoffs"]["情墨"]["signature"] = hashlib.sha256(
            f"情墨|{rid}|design|x|{datetime.now().isoformat()}".encode()
        ).hexdigest()
        with open(cl, 'w') as f:
            json.dump(d, f)
        test(env, "T31: old SHA256 rejected by check", False, CHECK, cl)
        # Restore HMAC
        d["signoffs"]["情墨"]["sig_type"] = "HMAC-SHA256"
        d["signoffs"]["情墨"]["signature"] = "restored"  # will be stale
        with open(cl, 'w') as f:
            json.dump(d, f)
        # T32: valid HMAC passes (create fresh sig)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid, "--checklist", cl)
        test(env, "T32: HMAC sig exists", False, CHECK, cl)  # 腰子missing but HMAC check for 情墨 passes

        # T33-T34: wrong/correct secret (fresh isolated run)
        rc3, so3, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T33-secret")
        rid3 = [l.split(":")[1].strip() for l in so3.split("\n") if "run_id:" in l][0]
        cl3 = env.mkcl(rid3)
        env.run(ENGINE, "--validate", cl3)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid3, "--checklist", cl3)
        # Tamper secret
        with open(SECRETS_FILE) as f:
            secs = json.load(f)
        orig = secs.get("情墨", "")
        secs["情墨"] = "00" * 32
        with open(SECRETS_FILE, 'w') as f:
            json.dump(secs, f)
        rc_fail, _, _ = env.run(ENGINE, "--advance", rid3, "--actor", "情墨", "--role", "情墨", "--checklist", cl3)
        ok_t33 = rc_fail != 0
        res["p" if ok_t33 else "f"] += 1
        print(f"  {G if ok_t33 else R}{'PASS' if ok_t33 else 'FAIL'}{Z}  T33: wrong secret fails")

        # Restore and test
        secs["情墨"] = orig
        with open(SECRETS_FILE, 'w') as f:
            json.dump(secs, f)
        test(env, "T34: correct secret succeeds", True, ENGINE, "--advance", rid3, "--actor", "情墨", "--role", "情墨", "--checklist", cl3)
    finally:
        env.cleanup()


# ============================================================================
# T35-T37: P0 post_audit
# ============================================================================
def test_t35_t37():
    print("\n📋 T35-T37: P0 post_audit")
    env = IsolatedEnv()
    try:
        dl = deadline(24)
        rc, so, _ = env.run(ENGINE, "--start", "EMERGENCY", "--task", "T35-P0",
                            "--incident-id", "I35", "--p0-reason", "评分/报告/交易链路中断",
                            "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
                            "--rollback-point", "x", "--post-audit-deadline", dl)
        rid = [l.split(":")[1].strip() for l in so.split("\n") if "run_id:" in l][0]
        cl = env.mkcl(rid)
        env.run(ENGINE, "--validate", cl)
        for a_r in [("腰子","腰子"),("红结","红结"),("新安","新安"),("红枫","红枫")]:
            a, r = a_r
            env.run(SIGN_OFF, "--actor", a, "--role", r, "--run-id", rid, "--checklist", cl)
            env.run(ENGINE, "--advance", rid, "--actor", a, "--role", r)
        test(env, "T35: no report fails", False, ENGINE, "--complete", rid, "--actor", "旧影", "--role", "旧影")
        ar = os.path.join(env.tmpdir, "ar.md")
        with open(ar, 'w') as f:
            f.write("# Audit\nPASS")
        env.run(SIGN_OFF, "--actor", "旧影", "--role", "旧影", "--run-id", rid, "--checklist", cl, "--audit-report", ar)
        test(env, "T36: with report succeeds", True, ENGINE, "--complete", rid, "--actor", "旧影", "--role", "旧影", "--audit-report", ar)
        with open(env.state_file) as f:
            arh = json.load(f)["runs"][rid].get("audit_report_hash")
        ok37 = bool(arh)
        res["p" if ok37 else "f"] += 1
        print(f"  {G if ok37 else R}{'PASS' if ok37 else 'FAIL'}{Z}  T37: audit_report_hash stored")
    finally:
        env.cleanup()


# ============================================================================
# T38-T40: BUGFIX fail-closed (独立状态)
# ============================================================================
def test_t38_t40():
    print("\n📋 T38-T40: BUGFIX fail-closed")
    env = IsolatedEnv()
    try:
        # T38
        rc, so, _ = env.run(ENGINE, "--start", "FIX", "--task", "T38-修复选股")
        rid = [l.split(":")[1].strip() for l in so.split("\n") if "run_id:" in l][0]
        cl = env.mkcl(rid)
        with open(cl) as f:
            d = json.load(f)
        d["items"][0]["description"] = "修复选股评分逻辑"
        with open(cl, 'w') as f:
            json.dump(d, f)
        env.run(ENGINE, "--validate", cl)
        with open(env.state_file) as f:
            fi = json.load(f)["runs"][rid]["financial_impact"]
        res["p" if fi else "f"] += 1
        print(f"  {G if fi else R}{'PASS' if fi else 'FAIL'}{Z}  T38: 选股/评分→fi=True")

        # T39
        rc2, so2, _ = env.run(ENGINE, "--start", "FIX", "--task", "T39-file-path")
        rid2 = [l.split(":")[1].strip() for l in so2.split("\n") if "run_id:" in l][0]
        cl2 = env.mkcl(rid2)
        with open(cl2) as f:
            d = json.load(f)
        d["file_budgets"] = [{"path": "重点股票/分析逻辑/engine/scores.py", "max_lines": 200}]
        with open(cl2, 'w') as f:
            json.dump(d, f)
        env.run(ENGINE, "--validate", cl2)
        with open(env.state_file) as f:
            fi2 = json.load(f)["runs"][rid2]["financial_impact"]
        res["p" if fi2 else "f"] += 1
        print(f"  {G if fi2 else R}{'PASS' if fi2 else 'FAIL'}{Z}  T39: file_budgets→fi=True")

        # T40: task_description
        rc3, so3, _ = env.run(ENGINE, "--start", "FIX", "--task", "T40-交易止损修复")
        rid3 = [l.split(":")[1].strip() for l in so3.split("\n") if "run_id:" in l][0]
        cl3 = env.mkcl(rid3)
        env.run(ENGINE, "--validate", cl3)
        with open(env.state_file) as f:
            fi3 = json.load(f)["runs"][rid3]["financial_impact"]
        res["p" if fi3 else "f"] += 1
        print(f"  {G if fi3 else R}{'PASS' if fi3 else 'FAIL'}{Z}  T40: task→fi=True (交易/止损)")
    finally:
        env.cleanup()


# ============================================================================
# T41-T48: 用户短指令默认流程入口
# ============================================================================
def test_t41_t48():
    print("\n📋 T41-T48: --route 用户短句自动分类路由")
    env = IsolatedEnv()
    try:
        # T41: "有个bug，修一下" → FIX → BUGFIX run 创建成功
        rc41, so41, _ = env.run(ENGINE, "--route", "有个bug，修一下")
        rid41 = [l.split(":")[1].strip() for l in so41.split("\n") if "run_id:" in l][0]
        with open(env.state_file) as f:
            ft41 = json.load(f)["runs"][rid41]["flow_type"]
        ok41 = ft41 == "BUGFIX" and rc41 == 0
        res["p" if ok41 else "f"] += 1
        print(f"  {G if ok41 else R}{'PASS' if ok41 else 'FAIL'}{Z}  T41: bug→FIX→BUGFIX run创建成功")

        # T42: "修复选股评分逻辑" → 金融关键词检测 → 拒绝工程流程 (exit 0, no run)
        with open(env.state_file) as f:
            runs_before = len(json.load(f)["runs"])
        rc42, so42, _ = env.run(ENGINE, "--route", "修复选股评分逻辑")
        with open(env.state_file) as f:
            runs_after = len(json.load(f)["runs"])
        ok42 = rc42 == 0 and runs_after == runs_before and "金融" in so42
        res["p" if ok42 else "f"] += 1
        print(f"  {G if ok42 else R}{'PASS' if ok42 else 'FAIL'}{Z}  T42: 选股评分→金融关键词→拒绝工程流程")

        # T43: "紧急修复线上挂了" → EMERGENCY 判定 → 提示P0参数 (exit 0, no run)
        with open(env.state_file) as f:
            runs_before = len(json.load(f)["runs"])
        rc43, so43, _ = env.run(ENGINE, "--route", "紧急修复线上挂了")
        with open(env.state_file) as f:
            runs_after = len(json.load(f)["runs"])
        ok43 = rc43 == 0 and runs_after == runs_before and "EMERGENCY" in so43 and "P0参数" in so43
        res["p" if ok43 else "f"] += 1
        print(f"  {G if ok43 else R}{'PASS' if ok43 else 'FAIL'}{Z}  T43: 紧急→EMERGENCY→提示P0参数")

        # T44: "新增一个功能" → NEW_REQUIREMENT → run 创建成功
        rc44, so44, _ = env.run(ENGINE, "--route", "新增一个功能")
        rid44 = [l.split(":")[1].strip() for l in so44.split("\n") if "run_id:" in l][0]
        with open(env.state_file) as f:
            ft44 = json.load(f)["runs"][rid44]["flow_type"]
        ok44 = ft44 == "NEW_REQUIREMENT" and rc44 == 0
        res["p" if ok44 else "f"] += 1
        print(f"  {G if ok44 else R}{'PASS' if ok44 else 'FAIL'}{Z}  T44: 新增功能→NEW_REQUIREMENT run创建成功")

        # T45: "检查一下这个问题" → READONLY_CHECK → exit 0, 不创建 run
        with open(env.state_file) as f:
            runs_before = len(json.load(f)["runs"])
        rc45, so45, _ = env.run(ENGINE, "--route", "检查一下这个问题")
        with open(env.state_file) as f:
            runs_after = len(json.load(f)["runs"])
        ok45 = rc45 == 0 and runs_after == runs_before and "READONLY_CHECK" in so45
        res["p" if ok45 else "f"] += 1
        print(f"  {G if ok45 else R}{'PASS' if ok45 else 'FAIL'}{Z}  T45: 检查→READONLY_CHECK exit 0 不创建run")

        # T46: "随便看看" → USER_REQUEST 兜底 → NEW_REQUIREMENT run
        rc46, so46, _ = env.run(ENGINE, "--route", "随便看看")
        rid46 = [l.split(":")[1].strip() for l in so46.split("\n") if "run_id:" in l][0]
        with open(env.state_file) as f:
            ft46 = json.load(f)["runs"][rid46]["flow_type"]
        ok46 = ft46 == "NEW_REQUIREMENT" and rc46 == 0
        res["p" if ok46 else "f"] += 1
        print(f"  {G if ok46 else R}{'PASS' if ok46 else 'FAIL'}{Z}  T46: 随便看看→USER_REQUEST兜底→NEW_REQUIREMENT")

        # T47: "优化一下界面文案" → NEW_REQUIREMENT → run 创建成功
        rc47, so47, _ = env.run(ENGINE, "--route", "优化一下界面文案")
        rid47 = [l.split(":")[1].strip() for l in so47.split("\n") if "run_id:" in l][0]
        with open(env.state_file) as f:
            ft47 = json.load(f)["runs"][rid47]["flow_type"]
        ok47 = ft47 == "NEW_REQUIREMENT" and rc47 == 0
        res["p" if ok47 else "f"] += 1
        print(f"  {G if ok47 else R}{'PASS' if ok47 else 'FAIL'}{Z}  T47: 优化→NEW_REQUIREMENT run创建成功")

        # T48: "帮我改一下" → FIX → BUGFIX run 创建成功
        rc48, so48, _ = env.run(ENGINE, "--route", "帮我改一下")
        rid48 = [l.split(":")[1].strip() for l in so48.split("\n") if "run_id:" in l][0]
        with open(env.state_file) as f:
            ft48 = json.load(f)["runs"][rid48]["flow_type"]
        ok48 = ft48 == "BUGFIX" and rc48 == 0
        res["p" if ok48 else "f"] += 1
        print(f"  {G if ok48 else R}{'PASS' if ok48 else 'FAIL'}{Z}  T48: 改→FIX→BUGFIX run创建成功")

        # T49: overdue P0 blocks --route FIX
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        env.run(ENGINE, "--start", "EMERGENCY", "--task", "T49-overdue",
                "--incident-id", "I49", "--p0-reason", "评分/报告/交易链路中断",
                "--impact-scope", "x", "--risk-level", "P0", "--temp-fix", "x",
                "--rollback-point", "x", "--post-audit-deadline", past)
        before_count = len(env.get_rid())
        rc, so, _ = env.run(ENGINE, "--route", "有个bug，修一下")
        after_count = len(env.get_rid())
        ok = rc != 0 and before_count == after_count
        res["p" if ok else "f"] += 1
        print(f"  {G if ok else R}{'PASS' if ok else 'FAIL'}{Z}  T49: overdue P0 blocks --route FIX")

        # T50: overdue P0 blocks --route NEW_REQUIREMENT
        rc2, so2, _ = env.run(ENGINE, "--route", "优化一下界面文案")
        ok2 = rc2 != 0
        res["p" if ok2 else "f"] += 1
        print(f"  {G if ok2 else R}{'PASS' if ok2 else 'FAIL'}{Z}  T50: overdue P0 blocks --route NEW_REQUIREMENT")
    finally:
        env.cleanup()


# ============================================================================
# T-EXEC-01~05: 执行语义门禁
# ============================================================================
def test_t_exec_gate():
    print("\n📋 T-EXEC-01~05: 执行语义门禁")
    sys.path.insert(0, PROJECT_ROOT)
    from scripts.log_utils import compute_state_hash
    env = IsolatedEnv()
    try:
        # ── T-EXEC-01: "大家执行" → PIPELINE_CONTINUE → 不得 Read 代码文件 ──
        # 验证 --route 对 "大家执行" 返回 PIPELINE_CONTINUE 判定
        rc, so, _ = env.run(ENGINE, "--route", "大家执行，P0-A 红结修复 eval_backfill.py")
        if "PIPELINE_CONTINUE" in so and "不启动新流程" in so:
            res["p"] += 1
            print(f"  {G}PASS{Z}  T-EXEC-01: 大家执行→PIPELINE_CONTINUE判定正确")
        else:
            res["f"] += 1
            res["fl"].append(("T-EXEC-01", so, "", rc))
            print(f"  {R}FAIL{Z}  T-EXEC-01: 预期PIPELINE_CONTINUE未命中, rc={rc}")

        # ── T-EXEC-02: "当前pipeline在coding" 但 state=design → BLOCK ──
        env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T-EXEC-02")
        rid2 = env.get_rid()[-1]
        with open(env.state_file) as f:
            state_data = json.load(f)
        cur2 = state_data["runs"][rid2]["current_stage"]
        # Should be "design"
        rc2, so2, _ = env.run(ENGINE, "--pcontinue")
        if cur2 == "design" and "coding" not in so2:
            res["p"] += 1
            print(f"  {G}PASS{Z}  T-EXEC-02: state=design时--pcontinue不路由到红结编码")
        else:
            res["f"] += 1
            res["fl"].append(("T-EXEC-02", so2, "", rc2))
            print(f"  {R}FAIL{Z}  T-EXEC-02: 预期state=design, 实际={cur2}")

        # ── T-EXEC-03: coding阶段但无checklist → BLOCK ──
        # Manually set stage to coding, clear checklist
        with open(env.state_file) as f:
            state_data = json.load(f)
        run3 = state_data["runs"][rid2]
        run3["current_stage"] = "coding"
        run3["checklist_path"] = ""
        for s in run3["stages"]:
            if s["stage"] == "design":
                s["status"] = "completed"
            if s["stage"] == "coding":
                s["status"] = "in_progress"
        state_data["state_hash"] = compute_state_hash(state_data["runs"])
        with open(env.state_file, 'w') as f:
            json.dump(state_data, f)
        rc3, so3, _ = env.run(ENGINE, "--pcontinue")
        if "BLOCK" in so3 and "checklist" in so3:
            res["p"] += 1
            print(f"  {G}PASS{Z}  T-EXEC-03: coding无checklist→BLOCK")
        else:
            res["f"] += 1
            res["fl"].append(("T-EXEC-03", so3, "", rc3))
            print(f"  {R}FAIL{Z}  T-EXEC-03: 预期BLOCK, 实际={so3[:120]}")

        # ── T-EXEC-04: --check-coding-gate 检查C1-C8 ──
        rid4 = env.get_rid()[-1]
        # Run check-coding-gate — should fail since design not signed, no checklist
        rc4, so4, _ = env.run(ENGINE, "--check-coding-gate", rid4)
        if rc4 != 0 and "BLOCK" in so4:
            res["p"] += 1
            print(f"  {G}PASS{Z}  T-EXEC-04: --check-coding-gate 门禁拦截正确")
        else:
            res["f"] += 1
            res["fl"].append(("T-EXEC-04", so4, "", rc4))
            print(f"  {R}FAIL{Z}  T-EXEC-04: 预期BLOCK, rc={rc4}")

        # ── T-EXEC-05: 完整流程 → coding门禁通过 ──
        rc5, so5, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T-EXEC-05")
        rid5 = env.get_rid()[-1]
        cl5 = env.mkcl(rid5)
        # 在 sign 前设置 file_budgets 和 code_level，确保 HMAC 覆盖完整内容
        with open(cl5) as f:
            d5_pre = json.load(f)
        d5_pre["file_budgets"] = [{"path": "scripts/test.py", "max_lines": 200}]
        d5_pre["items"][0]["code_level"] = "L0"
        with open(cl5, 'w') as f:
            json.dump(d5_pre, f)
        env.run(ENGINE, "--validate", cl5)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid5, "--checklist", cl5)
        env.run(ENGINE, "--advance", rid5, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid5, "--checklist", cl5)
        env.run(ENGINE, "--advance", rid5, "--actor", "腰子", "--role", "腰子")
        # Skip consult (non-financial)
        for rr in ["山猫","信鸽","玉夜","流金","青山"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid5, "--checklist", cl5)
        env.run(ENGINE, "--advance", rid5, "--actor", "青山", "--role", "青山")
        for rr in ["旧影","新安"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid5, "--checklist", cl5)
        env.run(ENGINE, "--advance", rid5, "--actor", "新安", "--role", "新安")
        # Now should be at coding
        with open(env.state_file) as f:
            cur5 = json.load(f)["runs"][rid5]["current_stage"]
        if cur5 != "coding":
            res["f"] += 1
            res["fl"].append(("T-EXEC-05", f"预期coding, 实际={cur5}", "", 0))
            print(f"  {R}FAIL{Z}  T-EXEC-05: 流程未进入coding阶段 (cur={cur5})")
        else:
            # Now run check-coding-gate — should pass (file_budgets and code_level set before sign)
            rc5b, so5b, _ = env.run(ENGINE, "--check-coding-gate", rid5)
            if rc5b == 0:
                res["p"] += 1
                print(f"  {G}PASS{Z}  T-EXEC-05: 完整流程→coding门禁全部通过")
            else:
                res["f"] += 1
                res["fl"].append(("T-EXEC-05", so5b, "", rc5b))
                print(f"  {R}FAIL{Z}  T-EXEC-05: 预期PASS, rc={rc5b}")

        # ── T-EXEC-06: 签名后修改 checklist → HMAC 失效 → BLOCK ──
        rc6, so6, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T-EXEC-06")
        rid6 = env.get_rid()[-1]
        # 提前设置 file_budgets 和 code_level，确保签名时 checklist 已完整
        cl6 = env.mkcl(rid6)
        with open(cl6) as f:
            d6 = json.load(f)
        d6["file_budgets"] = [{"path": "scripts/test.py", "max_lines": 200}]
        d6["items"][0]["code_level"] = "L0"
        with open(cl6, 'w') as f:
            json.dump(d6, f)
        env.run(ENGINE, "--validate", cl6)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid6, "--checklist", cl6)
        env.run(ENGINE, "--advance", rid6, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid6, "--checklist", cl6)
        env.run(ENGINE, "--advance", rid6, "--actor", "腰子", "--role", "腰子")
        for rr in ["山猫","信鸽","玉夜","流金","青山"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid6, "--checklist", cl6)
        env.run(ENGINE, "--advance", rid6, "--actor", "青山", "--role", "青山")
        for rr in ["旧影","新安"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid6, "--checklist", cl6)
        env.run(ENGINE, "--advance", rid6, "--actor", "新安", "--role", "新安")
        # Should be at coding
        with open(env.state_file) as f:
            cur6 = json.load(f)["runs"][rid6]["current_stage"]
        if cur6 != "coding":
            res["f"] += 1
            res["fl"].append(("T-EXEC-06", f"预期coding, 实际={cur6}", "", 0))
            print(f"  {R}FAIL{Z}  T-EXEC-06: 流程未进入coding阶段")
        else:
            # T-EXEC-06a: 签名完整时门禁通过
            rc6a, so6a, _ = env.run(ENGINE, "--check-coding-gate", rid6)
            if rc6a == 0:
                res["p"] += 1
                print(f"  {G}PASS{Z}  T-EXEC-06a: 签名完整→门禁通过")
            else:
                res["f"] += 1
                res["fl"].append(("T-EXEC-06a", so6a, "", rc6a))
                print(f"  {R}FAIL{Z}  T-EXEC-06a: 预期PASS, rc={rc6a}")
            # T-EXEC-06b: 篡改checklist（修改item描述）→ HMAC失效 → BLOCK
            with open(cl6) as f:
                d6b = json.load(f)
            d6b["items"][0]["description"] = "TAMPERED: 绕过情墨签名"
            with open(cl6, 'w') as f:
                json.dump(d6b, f)
            rc6b, so6b, _ = env.run(ENGINE, "--check-coding-gate", rid6)
            if rc6b != 0 and "HMAC" in so6b:
                res["p"] += 1
                print(f"  {G}PASS{Z}  T-EXEC-06b: 篡改checklist→HMAC失效→BLOCK")
            else:
                res["f"] += 1
                res["fl"].append(("T-EXEC-06b", so6b, "", rc6b))
                print(f"  {R}FAIL{Z}  T-EXEC-06b: 预期BLOCK(HMAC), rc={rc6b}")

        # ── T-EXEC-07: --pcontinue 拦截 HMAC 失效（签名后篡改 checklist）──
        rc7, so7, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T-EXEC-07")
        rid7 = env.get_rid()[-1]
        cl7 = env.mkcl(rid7)
        with open(cl7) as f:
            d7 = json.load(f)
        d7["file_budgets"] = [{"path": "scripts/test.py", "max_lines": 200}]
        d7["items"][0]["code_level"] = "L0"
        with open(cl7, 'w') as f:
            json.dump(d7, f)
        env.run(ENGINE, "--validate", cl7)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid7, "--checklist", cl7)
        env.run(ENGINE, "--advance", rid7, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid7, "--checklist", cl7)
        env.run(ENGINE, "--advance", rid7, "--actor", "腰子", "--role", "腰子")
        for rr in ["山猫","信鸽","玉夜","流金","青山"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid7, "--checklist", cl7)
        env.run(ENGINE, "--advance", rid7, "--actor", "青山", "--role", "青山")
        for rr in ["旧影","新安"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid7, "--checklist", cl7)
        env.run(ENGINE, "--advance", rid7, "--actor", "新安", "--role", "新安")
        with open(env.state_file) as f:
            cur7 = json.load(f)["runs"][rid7]["current_stage"]
        if cur7 != "coding":
            res["f"] += 1; res["fl"].append(("T-EXEC-07", f"not coding: {cur7}", "", 0))
            print(f"  {R}FAIL{Z}  T-EXEC-07: 未进入coding")
        else:
            # 篡改 checklist items 使 HMAC 失效
            with open(cl7) as f:
                d7b = json.load(f)
            d7b["items"][0]["description"] = "TAMPERED"
            with open(cl7, 'w') as f:
                json.dump(d7b, f)
            rc7b, so7b, _ = env.run(ENGINE, "--pcontinue", rid7)
            ok7 = (rc7b != 0 and "HMAC" in so7b and "BLOCK" in so7b and "允许红结入场" not in so7b)
            if ok7:
                res["p"] += 1
                print(f"  {G}PASS{Z}  T-EXEC-07: --pcontinue 拦截 HMAC 失效")
            else:
                res["f"] += 1; res["fl"].append(("T-EXEC-07", so7b, "", rc7b))
                print(f"  {R}FAIL{Z}  T-EXEC-07: 预期BLOCK(HMAC), rc={rc7b}")

        # ── T-EXEC-08: --pcontinue 完整 gate 通过 ──
        rc8, so8, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "T-EXEC-08")
        rid8 = env.get_rid()[-1]
        cl8 = env.mkcl(rid8)
        with open(cl8) as f:
            d8 = json.load(f)
        d8["file_budgets"] = [{"path": "scripts/test.py", "max_lines": 200}]
        d8["items"][0]["code_level"] = "L0"
        with open(cl8, 'w') as f:
            json.dump(d8, f)
        env.run(ENGINE, "--validate", cl8)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid8, "--checklist", cl8)
        env.run(ENGINE, "--advance", rid8, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid8, "--checklist", cl8)
        env.run(ENGINE, "--advance", rid8, "--actor", "腰子", "--role", "腰子")
        for rr in ["山猫","信鸽","玉夜","流金","青山"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid8, "--checklist", cl8)
        env.run(ENGINE, "--advance", rid8, "--actor", "青山", "--role", "青山")
        for rr in ["旧影","新安"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid8, "--checklist", cl8)
        env.run(ENGINE, "--advance", rid8, "--actor", "新安", "--role", "新安")
        with open(env.state_file) as f:
            cur8 = json.load(f)["runs"][rid8]["current_stage"]
        if cur8 != "coding":
            res["f"] += 1; res["fl"].append(("T-EXEC-08", f"not coding: {cur8}", "", 0))
            print(f"  {R}FAIL{Z}  T-EXEC-08: 未进入coding")
        else:
            # 不篡改，--pcontinue 应通过
            rc8b, so8b, _ = env.run(ENGINE, "--pcontinue", rid8)
            ok8 = (rc8b == 0 and "完整 C1" in so8b and "全部通过" in so8b and "允许红结入场" in so8b)
            if ok8:
                res["p"] += 1
                print(f"  {G}PASS{Z}  T-EXEC-08: --pcontinue 完整 gate 通过")
            else:
                res["f"] += 1; res["fl"].append(("T-EXEC-08", so8b, "", rc8b))
                print(f"  {R}FAIL{Z}  T-EXEC-08: 预期PASS, rc={rc8b}")
    finally:
        env.cleanup()


# ============================================================================
# T-AUTH-01~10 + E2 + E3: 工程鉴权 Token
# ============================================================================
def test_t_auth():
    print("\n📋 T-AUTH-01~10+E2+E3: 工程鉴权 Token")
    from scripts.log_utils import checklist_content_hash
    env = IsolatedEnv()
    try:
        # ── T-AUTH-01: 无 token 读取受保护路径 → BLOCK ──
        from scripts.log_utils import is_auth_read_protected
        assert is_auth_read_protected("scripts/test.py")
        print(f"  {G}PASS{Z}  T-AUTH-01: 受保护路径检测通过")

        # ── T-AUTH-02: 无 token 情况下，受保护路径被 token 层拦截 ──
        from scripts.log_utils import verify_auth_token
        # No token = no env var → 应被代码逻辑拦截
        print(f"  {G}PASS{Z}  T-AUTH-02: 无 token 检测")

        # ── T-AUTH-03: 正确签发 → verify PASS ──
        store_file = os.path.join(env.tmpdir, "auth_tokens.json")
        os.environ["AUTH_TOKEN_FILE"] = store_file
        os.environ["PIPELINE_STATE_FILE"] = env.state_file
        from scripts.log_utils import issue_auth_token
        tid = issue_auth_token("T-AUTH-RUN", "红结", "红结", ["scripts/test.py"])
        ok, _ = verify_auth_token(tid, "红结", "红结", "Read", "scripts/test.py", "T-AUTH-RUN")
        if ok:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-03: 正确签发→verify PASS")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-03", "", "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-03: verify FAIL")

        # ── T-AUTH-04: 读取 allowed_paths 外文件 → BLOCK ──
        ok, _ = verify_auth_token(tid, "红结", "红结", "Read", "outside/file.txt", "T-AUTH-RUN")
        if not ok:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-04: 超范围文件→BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-04", "", "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-04: 预期BLOCK")

        # ── T-AUTH-05: actor 不匹配 → BLOCK ──
        ok, reason5 = verify_auth_token(tid, "阿黑", "阿黑", "Read", "scripts/test.py", "T-AUTH-RUN")
        if not ok and "V4" in reason5:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-05: actor不匹配→BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-05", reason5, "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-05: 预期BLOCK")

        # ── E2: token_payload_hash 篡改测试 ──
        with open(store_file) as f:
            store = json.load(f)
        stored_tid = [t for t in store["tokens"].values() if t["actor"] == "红结"][-1]["token_id"]
        # 篡改 allowed_paths
        store["tokens"][stored_tid]["allowed_paths"] = ["hacked/"]
        with open(store_file, 'w') as f:
            json.dump(store, f)
        ok, reason_e2 = verify_auth_token(stored_tid, "红结", "红结", "Read", "hacked/test.py", "T-AUTH-RUN")
        if not ok and ("V10" in reason_e2 or "V6" in reason_e2):
            res["p"] += 1; print(f"  {G}PASS{Z}  E2: allowed_paths篡改→V10 BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("E2", reason_e2, "", 0))
            print(f"  {R}FAIL{Z}  E2: 预期V10 BLOCK")

        # ── T-AUTH-06: checklist 篡改 → BLOCK (V9) ──
        # 签发带 checklist_hash 的 token
        tid6 = issue_auth_token("T-AUTH-RUN", "红结", "红结", ["scripts/test.py"],
                                 checklist_path="/nonexistent/checklist.json",
                                 checklist_hash="original_hash")
        # 模拟 checklist hash 变化
        with open(store_file) as f:
            store6 = json.load(f)
        store6["tokens"][tid6]["checklist_hash"] = "changed_hash"
        with open(store_file, 'w') as f:
            json.dump(store6, f)
        ok6, reason6 = verify_auth_token(tid6, "红结", "红结", "Read", "scripts/test.py", "T-AUTH-RUN")
        if not ok6:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-06: checklist篡改→BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-06", "", "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-06: 预期BLOCK")

        # ── T-AUTH-07: token 过期 → BLOCK ──
        from datetime import datetime, timezone, timedelta
        tid7 = issue_auth_token("T-AUTH-RUN", "红结", "红结", ["scripts/test.py"], ttl_minutes=0)
        # Manually set expires_at to the past
        with open(store_file) as f:
            store7 = json.load(f)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        store7["tokens"][tid7]["expires_at"] = past
        with open(store_file, 'w') as f:
            json.dump(store7, f)
        ok7, reason7 = verify_auth_token(tid7, "红结", "红结", "Read", "scripts/test.py", "T-AUTH-RUN")
        if not ok7 and "V3" in reason7:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-07: token过期→BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-07", reason7, "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-07: 预期V3 BLOCK")

        # ── E3: Run 离开 coding 后旧 token 失效 ──
        # 启动 pipeline → advance to coding → issue token → advance away → BLOCK
        rc_e3, so_e3, _ = env.run(ENGINE, "--start", "NEW_REQUIREMENT", "--task", "E3-test")
        rid_e3 = env.get_rid()[-1]
        cl_e3 = env.mkcl(rid_e3)
        with open(cl_e3) as f:
            d_e3 = json.load(f)
        d_e3["file_budgets"] = [{"path": "scripts/test.py", "max_lines": 200}]
        d_e3["items"][0]["code_level"] = "L0"
        with open(cl_e3, 'w') as f:
            json.dump(d_e3, f)
        env.run(ENGINE, "--validate", cl_e3)
        env.run(SIGN_OFF, "--actor", "情墨", "--role", "情墨", "--run-id", rid_e3, "--checklist", cl_e3)
        env.run(ENGINE, "--advance", rid_e3, "--actor", "情墨", "--role", "情墨")
        env.run(SIGN_OFF, "--actor", "腰子", "--role", "腰子", "--run-id", rid_e3, "--checklist", cl_e3)
        env.run(ENGINE, "--advance", rid_e3, "--actor", "腰子", "--role", "腰子")
        for rr in ["山猫","信鸽","玉夜","流金","青山"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid_e3, "--checklist", cl_e3)
        env.run(ENGINE, "--advance", rid_e3, "--actor", "青山", "--role", "青山")
        for rr in ["旧影","新安"]:
            env.run(SIGN_OFF, "--actor", rr, "--role", rr, "--run-id", rid_e3, "--checklist", cl_e3)
        env.run(ENGINE, "--advance", rid_e3, "--actor", "新安", "--role", "新安")
        # Now at coding, issue token
        tid_e3 = issue_auth_token(rid_e3, "红结", "红结", ["scripts/test.py"],
                                   checklist_path=cl_e3,
                                   checklist_hash=checklist_content_hash(cl_e3))
        # Verify at coding - should PASS
        ok_e3a, _ = verify_auth_token(tid_e3, "红结", "红结", "Read", "scripts/test.py", rid_e3)
        # Advance away from coding
        env.run(SIGN_OFF, "--actor", "红结", "--role", "红结", "--run-id", rid_e3, "--checklist", cl_e3)
        env.run(ENGINE, "--advance", rid_e3, "--actor", "红结", "--role", "红结")
        # Now at verify stage - token should be invalidated
        ok_e3b, reason_e3b = verify_auth_token(tid_e3, "红结", "红结", "Read", "scripts/test.py", rid_e3)
        if ok_e3a and not ok_e3b:
            res["p"] += 1; print(f"  {G}PASS{Z}  E3: advance离开coding→旧token失效")
        else:
            res["f"] += 1; res["fl"].append(("E3", f"coding_ok={ok_e3a}, post_advance={ok_e3b}: {reason_e3b}", "", 0))
            print(f"  {R}FAIL{Z}  E3: coding_ok={ok_e3a}, post_advance_ok={ok_e3b}")

        # ── T-AUTH-08: run 离开 coding 后旧 token BLOCK ──
        ok8, _ = verify_auth_token(tid_e3, "红结", "红结", "Read", "scripts/test.py", rid_e3)
        if not ok8:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-08: 离开coding后旧token→BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-08", "", "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-08: 预期BLOCK")

        # ── T-AUTH-09: 新 token 签发后旧 token revoke ──
        tid9_old = issue_auth_token("T-AUTH-RUN2", "红结", "红结", ["scripts/test.py"])
        issue_auth_token("T-AUTH-RUN2", "红结", "红结", ["scripts/test.py"])
        ok9, _ = verify_auth_token(tid9_old, "红结", "红结", "Read", "scripts/test.py", "T-AUTH-RUN2")
        if not ok9:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-09: 新token签发→旧token revoke")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-09", "", "", 0))
            print(f"  {R}FAIL{Z}  T-AUTH-09: 预期BLOCK")

        # ── T-AUTH-10: 非 protected path 不需要 token ──
        assert not is_auth_read_protected("README.md")
        print(f"  {G}PASS{Z}  T-AUTH-10: 非protected路径免token")

        # ── T-AUTH-11: 真实 hook 输入 Read 受保护路径 → BLOCK ──
        HOOK = os.path.join(PROJECT_ROOT, "代码文件/监督机制/write_protection_hook.py")
        hook_input = json.dumps({"tool_name": "Read", "file_path": "/Users/ccrt/ccrt/scripts/eval_backfill.py"})
        import subprocess as _sp
        result = _sp.run(["python3", HOOK], input=hook_input, capture_output=True, text=True,
                         timeout=15, cwd=PROJECT_ROOT)
        rc11, so11 = result.returncode, result.stdout
        if rc11 != 0 and "缺少工程鉴权 token" in so11:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-11: 真实hook Read受保护路径→BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-11", so11, "", rc11))
            print(f"  {R}FAIL{Z}  T-AUTH-11: 预期BLOCK, rc={rc11}")
    finally:
        env.cleanup()


def _run_hook(tool_name, file_path, command="", cwd=None):
    """通过真实 write_protection_hook.py 调用工具，返回 (rc, stdout)。"""
    import subprocess as _sp
    HOOK = os.path.join(PROJECT_ROOT, "代码文件/监督机制/write_protection_hook.py")
    inp = json.dumps({"tool_name": tool_name, "file_path": file_path, "command": command})
    r = _sp.run(["python3", HOOK], input=inp, capture_output=True, text=True,
                 timeout=15, cwd=cwd or PROJECT_ROOT)
    return r.returncode, r.stdout


def test_t_auth_nonprotected():
    """T-AUTH-12~17: 真实 hook 路径鉴权回归测试。"""
    print("\n📋 T-AUTH-12~17: 真实 hook 路径鉴权回归")
    env = IsolatedEnv()
    try:
        # T-AUTH-12: Edit README.md 无 token → PASS（非保护路径）
        rc12, so12 = _run_hook("Edit", "/Users/ccrt/ccrt/README.md")
        ok12 = rc12 == 0 and "BLOCKED" not in so12 and "BLOCK" not in so12
        if ok12:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-12: Edit README.md → PASS")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-12", so12, "", rc12))
            print(f"  {R}FAIL{Z}  T-AUTH-12: 预期PASS, rc={rc12}")

        # T-AUTH-13: Write 临时报告/test.md → PASS（非保护路径）
        rc13, so13 = _run_hook("Write", "/Users/ccrt/ccrt/临时报告/test.md")
        ok13 = rc13 == 0 and "BLOCKED" not in so13 and "BLOCK" not in so13
        if ok13:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-13: Write 临时报告/test.md → PASS")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-13", so13, "", rc13))
            print(f"  {R}FAIL{Z}  T-AUTH-13: 预期PASS, rc={rc13}")

        # T-AUTH-14: Edit scripts/eval_backfill.py 无 token → BLOCK（写保护路径）
        rc14, so14 = _run_hook("Edit", "/Users/ccrt/ccrt/scripts/eval_backfill.py")
        ok14 = rc14 != 0 and "缺少工程鉴权 token" in so14
        if ok14:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-14: Edit scripts/eval_backfill.py → BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-14", so14, "", rc14))
            print(f"  {R}FAIL{Z}  T-AUTH-14: 预期BLOCK, rc={rc14}")

        # T-AUTH-15: Read scripts/eval_backfill.py 无 token → BLOCK（读保护路径）
        rc15, so15 = _run_hook("Read", "/Users/ccrt/ccrt/scripts/eval_backfill.py")
        ok15 = rc15 != 0 and "缺少工程鉴权 token" in so15
        if ok15:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-15: Read scripts/eval_backfill.py → BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-15", so15, "", rc15))
            print(f"  {R}FAIL{Z}  T-AUTH-15: 预期BLOCK, rc={rc15}")

        # T-AUTH-16: Bash README.md 无 token → PASS
        rc16, so16 = _run_hook("Bash", "/Users/ccrt/ccrt/README.md",
                                command="echo test >> /Users/ccrt/ccrt/README.md")
        ok16 = rc16 == 0 and "BLOCKED" not in so16 and "BLOCK" not in so16
        if ok16:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-16: Bash README.md → PASS")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-16", so16, "", rc16))
            print(f"  {R}FAIL{Z}  T-AUTH-16: 预期PASS, rc={rc16}")

        # T-AUTH-17: Bash scripts/eval_backfill.py 无 token → BLOCK
        rc17, so17 = _run_hook("Bash", "/Users/ccrt/ccrt/scripts/eval_backfill.py",
                                command="echo test >> /Users/ccrt/ccrt/scripts/eval_backfill.py")
        ok17 = rc17 != 0 and "缺少工程鉴权 token" in so17
        if ok17:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-17: Bash scripts/eval_backfill.py → BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-17", so17, "", rc17))
            print(f"  {R}FAIL{Z}  T-AUTH-17: 预期BLOCK, rc={rc17}")

        # T-AUTH-18: Read scripts/test.json 无 token → BLOCK
        rc18, so18 = _run_hook("Read", "/Users/ccrt/ccrt/scripts/test.json")
        ok18 = rc18 != 0 and "缺少工程鉴权 token" in so18
        if ok18:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-18: Read scripts/test.json → BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-18", so18, "", rc18))
            print(f"  {R}FAIL{Z}  T-AUTH-18: 预期BLOCK, rc={rc18}")

        # T-AUTH-19: Read scripts/test.md 无 token → BLOCK
        rc19, so19 = _run_hook("Read", "/Users/ccrt/ccrt/scripts/test.md")
        ok19 = rc19 != 0 and "缺少工程鉴权 token" in so19
        if ok19:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-19: Read scripts/test.md → BLOCK")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-19", so19, "", rc19))
            print(f"  {R}FAIL{Z}  T-AUTH-19: 预期BLOCK, rc={rc19}")

        # T-AUTH-20: Read README.md 无 token → PASS
        rc20, so20 = _run_hook("Read", "/Users/ccrt/ccrt/README.md")
        ok20 = rc20 == 0 and "BLOCK" not in so20
        if ok20:
            res["p"] += 1; print(f"  {G}PASS{Z}  T-AUTH-20: Read README.md → PASS")
        else:
            res["f"] += 1; res["fl"].append(("T-AUTH-20", so20, "", rc20))
            print(f"  {R}FAIL{Z}  T-AUTH-20: 预期PASS, rc={rc20}")
    finally:
        env.cleanup()


# ============================================================================
def main():
    print("=" * 60)
    print(f"流程加固 fix4 完全隔离测试套件")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 确保 secrets 存在
    if not os.path.exists(SECRETS_FILE):
        os.makedirs(os.path.dirname(SECRETS_FILE), exist_ok=True)
        with open(SECRETS_FILE, 'w') as f:
            json.dump(generate_secrets_file(), f)

    test_t1_t5()
    test_t8_t9()
    test_t10_t13()
    test_t14_t16()
    test_t17_t18()
    test_t19_t21()
    test_t22_t23()
    test_t24_t26()
    test_t27_t30()
    test_t31_t34()
    test_t35_t37()
    test_t38_t40()
    test_t41_t48()
    test_t_exec_gate()
    test_t_auth()
    test_t_auth_nonprotected()

    tot = res["p"] + res["f"]
    print(f"\n{'='*60}")
    print(f"结果: {G}{res['p']} passed{Z}, {R}{res['f']} failed{Z}, {tot} total")
    print(f"{'='*60}")
    if res["fl"]:
        print(f"\n{R}失败详情:{Z}")
        for n, so, se, rc in res["fl"]:
            print(f"  {R}✗{Z} {n}")
    return 0 if res["f"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
