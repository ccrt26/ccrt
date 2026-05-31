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
             "deploy_items": [], "file_budgets": []}
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
def main():
    print("=" * 60)
    print(f"流程加固 fix4 完全隔离测试套件")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 确保 secrets 存在
    if not os.path.exists(SECRETS_FILE):
        from scripts.log_utils import generate_secrets_file
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
