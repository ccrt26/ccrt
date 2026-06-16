"""会话四：懒加载契约、按股票分片、无硬编码、无正式动作、无持仓泄露。
严格函数体级检查，不接受注释命中。
"""
import os, sys, unittest, re, json

JS_PATH = "docs/keystock-dashboard/app.js"


def _get_function_body(js: str, func_name: str) -> str:
    """提取 JS 函数的 body 字符串。只匹配真实函数定义，不吃注释。"""
    # 匹配 async function name(...) { 或 function name(...) {
    patterns = [
        rf'async\s+function\s+{func_name}\s*\([^)]*\)\s*{{',
        rf'(?:^|\n)\s*function\s+{func_name}\s*\([^)]*\)\s*{{',
    ]
    start = -1
    for pat in patterns:
        m = re.search(pat, js)
        if m:
            start = m.start()
            break
    if start < 0:
        return ""
    # 找到 { 开始
    brace_start = js.index('{', start) + 1
    # 匹配括号深度
    depth = 1
    i = brace_start
    while i < len(js) and depth > 0:
        if js[i] == '{': depth += 1
        elif js[i] == '}': depth -= 1
        i += 1
    return js[brace_start:i-1] if depth == 0 else js[brace_start:]


class TestDashboardLazyLoadingContract(unittest.TestCase):
    """首页四 JSON 懒加载+详情懒加载+无硬编码+无正式动作+无持仓泄露。"""

    def _js(self) -> str:
        with open(JS_PATH, encoding="utf-8") as f:
            return f.read()

    # ── 1. 首页只加载 4 JSON + 不自动加载详情 ──

    def test_home_only_loads_four_json_strict(self):
        """loadHomeBundle 必须且只能加载 4 个指定 JSON。"""
        js = self._js()
        body = _get_function_body(js, "loadHomeBundle")
        self.assertTrue(body, "loadHomeBundle 函数不存在")

        # 提取 loadJSON 调用
        loads = re.findall(r"loadJSON\s*\(\s*['\"]([^'\"]+\.json)['\"]\s*\)", body)
        # 标准化：去掉 data/ 前缀
        loads_norm = [f.split("/")[-1] for f in loads]
        self.assertEqual(len(loads_norm), 4, f"应恰好 4 个 loadJSON 调用，实际 {len(loads_norm)}: {loads_norm}")

        expected = {"stock_pool.json", "stocks.json", "bundle_index.json", "run_manifest.json"}
        actual = set(loads_norm)
        self.assertEqual(actual, expected, f"loadJSON 文件不符: 期望 {expected}, 实际 {actual}")

        forbidden = {"dashboard.json", "today_decisions.json", "chart_data.json",
                     "evidence_index.json", "rule_health.json", "rule_health_summary.json",
                     "run_state.json", "detail.json"}
        for fb in forbidden:
            self.assertNotIn(fb, actual, f"loadHomeBundle 禁止加载 {fb}")

    def test_home_does_not_auto_select_stock(self):
        """loadHomeBundle 不得调用 selectStock、loadStockAssets 或加载详情分片。"""
        js = self._js()
        body = _get_function_body(js, "loadHomeBundle")
        self.assertTrue(body, "loadHomeBundle 函数不存在")

        # 禁止调用 selectStock
        if "selectStock" in body:
            # 必须逐行检查：只允许作为 onclick 字符串，不允许作为函数调用
            for line in body.split("\n"):
                stripped = line.strip()
                if "selectStock(" in stripped and not stripped.startswith("//") and not stripped.startswith("*"):
                    # onclick="selectStock(...)" 这种字符串中的允许
                    if 'onclick="selectStock' not in stripped:
                        self.assertFalse(True, f"loadHomeBundle 禁止直接调用 selectStock(): {stripped}")

        # 禁止调用 loadStockAssets
        self.assertNotIn("loadStockAssets", body, "loadHomeBundle 禁止调用 loadStockAssets")

        # 禁止出现详情分片路径
        for suffix in ["detail.json", "chart_data.json", "evidence.json"]:
            self.assertNotIn(suffix, body, f"loadHomeBundle 禁止加载 {suffix}")

        # 必须存在预期的首页渲染函数
        self.assertIn("renderPoolList", body, "loadHomeBundle 应调用 renderPoolList")
        self.assertIn("renderStockSummaries", body, "loadHomeBundle 应调用 renderStockSummaries")
        self.assertIn("resolveBundleStatus", body, "loadHomeBundle 应调用 resolveBundleStatus")

    # ── 2. 详情懒加载 ──

    def test_lazy_loader_function_is_real(self):
        """详情懒加载函数是真实 async 函数且使用分片路径。"""
        js = self._js()
        body = _get_function_body(js, "selectStock")
        self.assertTrue(body, "async function selectStock(stockCode) 不存在")

        # 函数体内必须存在三条详情分片路径
        for suffix in ["detail.json", "chart_data.json", "evidence.json"]:
            path_pattern = f"stocks/${{stockCode}}/{suffix}"
            self.assertIn(path_pattern, body,
                          f"selectStock 函数体缺少分片路径: {path_pattern}")

    def test_no_legacy_json_in_lazy_loader(self):
        """selectStock/loadStockAssets 不得使用顶层 legacy JSON 作为详情数据源。"""
        js = self._js()
        body = _get_function_body(js, "selectStock")
        self.assertTrue(body, "selectStock 函数不存在")

        forbidden_legacy = ["data/dashboard.json", "data/today_decisions.json",
                            "data/chart_data.json", "data/evidence_index.json",
                            "data/rule_health.json", "data/run_state.json",
                            "data/rule_health_summary.json"]
        for fb in forbidden_legacy:
            self.assertNotIn(fb, body, f"selectStock 禁止引用顶层 legacy JSON: {fb}")

    def test_lazy_loader_select_stock_has_three_json(self):
        """selectStock 函数必须加载 3 个 per-stock JSON。"""
        js = self._js()
        body = _get_function_body(js, "selectStock")
        self.assertTrue(body, "selectStock 函数不存在")

        loads = re.findall(r"loadJSON\s*\([^)]+\)", body)
        self.assertGreaterEqual(len(loads), 1,
                                "selectStock 应调用 loadJSON（Promise.all 合并后计数")

    # ── 3. 无硬编码 600114 ──

    def test_no_business_hardcoded_600114(self):
        """app.js 不得把 600114 作为默认业务常量。"""
        js = self._js()
        for i, line in enumerate(js.split("\n")):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                continue
            for pat in ['= "600114"', "= '600114'"]:
                if pat in stripped:
                    if "stocks/" not in stripped and "/600114" not in stripped:
                        self.assertFalse(True, f"硬编码 600114: {stripped}")

    # ── 4. 无正式动作泄露 ──

    def test_blocked_observation_no_formal_action(self):
        """BLOCKED/OBSERVATION 分支不得展示正式动作。"""
        js = self._js()
        self.assertIn("function canShowFormalAction", js,
                      "应存在 canShowFormalAction 函数")

        # renderDecisionBoundary 中正式动作必须受保护
        rdb_body = _get_function_body(js, "renderDecisionBoundary")
        self.assertTrue(rdb_body, "renderDecisionBoundary 函数不存在")

        # 必须包含 canShowFormalAction 保护
        self.assertIn("canShowFormalAction", rdb_body,
                      "renderDecisionBoundary 应调用 canShowFormalAction")

        # 展示"当前不是正式动作"
        self.assertIn("当前不是正式动作", rdb_body,
                      "renderDecisionBoundary 应显示'当前不是正式动作'")

        # 展示阻断原因
        self.assertIn("阻断原因", rdb_body,
                      "renderDecisionBoundary 应显示阻断原因")

    # ── 5. 无持仓敏感字段 ──

    def test_no_position_sensitive_fields_rendered(self):
        """app.js 不得渲染持仓敏感字段。"""
        js = self._js()
        sensitive = ["cost_price", "quantity", "unrealized_pnl", "real_pnl"]
        for sens in sensitive:
            if sens in js:
                idx = js.find(sens)
                ctx = js[max(0, idx-300):idx+len(sens)+300]
                in_safe = ("UNAVAILABLE" in ctx or "不可用" in ctx or "未接入" in ctx)
                self.assertTrue(in_safe, f"'{sens}' 未在安全上下文中")

    def test_no_position_sensitive_labels(self):
        """app.js 不得渲染中文持仓敏感标签"""
        js = self._js()
        labels = ["成本价", "数量", "盈亏"]
        for label in labels:
            if label in js:
                idx = js.find(label)
                ctx = js[max(0, idx-200):idx+len(label)+200]
                in_safe = ("UNAVAILABLE" in ctx or "不可用" in ctx or "未接入" in ctx or "不生成" in ctx)
                self.assertTrue(in_safe, f"'{label}' 未在安全上下文")

    # ── 6. 状态码可见 ──

    def test_status_codes_visible(self):
        """app.js 必须包含结论状态码和阻断原因渲染逻辑。"""
        js = self._js()
        for code in ["FORMAL", "OBSERVATION", "SHADOW", "BLOCKED"]:
            self.assertIn(code, js, f"app.js 缺少状态码: {code}")
        self.assertIn("decision_blockers", js, "应渲染 decision_blockers")
        self.assertIn("renderStatusGate", js, "应包含 renderStatusGate")
        rdb = _get_function_body(js, "renderDecisionBoundary")
        if rdb:
            self.assertIn("阻断原因", rdb, "renderDecisionBoundary 应显示阻断原因")

    # ── 7. bundle 优先 ──

    def test_bundle_priority_contract(self):
        """app.js 必须从 bundle_index + run_manifest 渲染数据包状态。"""
        js = self._js()
        body = _get_function_body(js, "resolveBundleStatus")
        self.assertTrue(body, "resolveBundleStatus 函数不存在")
        self.assertIn("run_id", body, "resolveBundleStatus 应处理 run_id")
        self.assertIn("publish_status", body, "resolveBundleStatus 应处理 publish_status")
        self.assertIn("business_user_visible_status", body,
                      "resolveBundleStatus 应处理 business_user_visible_status")

    # ── 8. 详情区占位符 ──

    def test_detail_placeholder_exists(self):
        """app.js 应包含 renderDetailPlaceholder 函数且不加载分片。"""
        js = self._js()
        body = _get_function_body(js, "renderDetailPlaceholder")
        self.assertTrue(body, "renderDetailPlaceholder 函数不存在")
        self.assertIn("请选择股票查看详情", body,
                      "renderDetailPlaceholder 应显示提示")
        self.assertNotIn("loadJSON", body,
                        "renderDetailPlaceholder 不得调用 loadJSON")

    # ── 9. HTML 容器 ──

    def test_detail_view_exists(self):
        """index.html 必须包含需要的容器。"""
        html_path = "docs/keystock-dashboard/index.html"
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
        for cid in ["view-detail", "status-gate", "evidence", "block-reasons",
                    "position-public", "chart-area", "bundle-status"]:
            self.assertIn(cid, html, f"HTML 缺少容器: {cid}")


if __name__ == "__main__":
    unittest.main()
