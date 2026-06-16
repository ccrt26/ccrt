/* keystock-dashboard 驾驶舱 JS */
let appData = {};

async function loadJSON(path) {
  const r = await fetch(path);
  return r.json();
}

function statusBadge(s) {
  return `<span class="status-badge status-${s}">${s}</span>`;
}

async function init() {
  try {
    appData.dashboard = await loadJSON('data/dashboard.json');
    appData.stocks = await loadJSON('data/stocks.json');
    appData.runState = await loadJSON('data/run_state.json');
    appData.evidence = await loadJSON('data/evidence_index.json');
    appData.ruleHealth = await loadJSON('data/rule_health.json');
  } catch(e) {
    document.getElementById('view-dashboard').innerHTML = `<div class="card"><p>数据加载失败: ${e.message}</p><p>请先运行 <code>scripts/build_keystock_product_api_bundle.py</code></p></div>`;
  }
  renderDashboard();
  renderStocks();
  renderRuleHealth();
  // Default view
  showView('dashboard');
}

function showView(name) {
  document.querySelectorAll('.main').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
  let link = document.querySelector(`nav a[data-view="${name}"]`);
  if (link) link.classList.add('active');
}

/* ── Dashboard ── */
function renderDashboard() {
  const el = document.getElementById('view-dashboard');
  const dash = appData.dashboard || {};
  const stocks = appData.stocks?.stocks || [];

  let html = `<div class="grid-4">`;
  html += `<div class="card metric"><div class="metric-value">${stocks.length}</div><div class="metric-label">跟踪股票</div></div>`;
  html += `<div class="card metric"><div class="metric-value">${appData.runState?.run_status || '-'}</div><div class="metric-label">运行状态</div></div>`;
  html += `<div class="card metric"><div class="metric-value ${dash.feature_snapshot?.close > dash.feature_snapshot?.ma20 ? 'up' : 'down'}">${dash.feature_snapshot?.close || '-'}</div><div class="metric-label">600114 收盘</div></div>`;
  html += `<div class="card metric"><div class="metric-value">${dash.feature_snapshot?.ma20 || '-'}</div><div class="metric-label">MA20</div></div>`;
  html += `</div>`;

  html += `<div class="card"><h2>股票概览</h2><table><tr><th>代码</th><th>名称</th><th>收盘</th><th>涨跌幅</th><th>状态</th></tr>`;
  for (const s of stocks) {
    const pct = s.change_pct;
    const pctCls = pct > 0 ? 'up' : pct < 0 ? 'down' : '';
    html += `<tr onclick="showStockDetail('${s.stock_code}')" style="cursor:pointer">
      <td>${s.stock_code}</td><td>${s.stock_name}</td>
      <td>${s.close}</td>
      <td class="${pctCls}">${pct > 0 ? '+' : ''}${pct}%</td>
      <td>${statusBadge(s.user_visible_status)}</td></tr>`;
  }
  html += `</table></div>`;
  html += `<div class="card"><h2>技术特征</h2><div class="chart-placeholder">📈 K 线走势图区域 — 此处展示 600114 K 线+MA5/MA20+成本线</div></div>`;
  el.innerHTML = html;
}

/* ── Stocks / Detail ── */
function renderStocks() {
  const el = document.getElementById('view-stocks');
  const stocks = appData.stocks?.stocks || [];
  let html = `<div class="card"><h2>全部股票</h2><table><tr><th>代码</th><th>名称</th><th>收盘</th><th>涨跌幅</th><th>状态</th><th></th></tr>`;
  for (const s of stocks) {
    const pct = s.change_pct;
    const pctCls = pct > 0 ? 'up' : pct < 0 ? 'down' : '';
    html += `<tr>
      <td>${s.stock_code}</td><td>${s.stock_name}</td>
      <td>${s.close}</td>
      <td class="${pctCls}">${pct > 0 ? '+' : ''}${pct}%</td>
      <td>${statusBadge(s.user_visible_status)}</td>
      <td><a onclick="showStockDetail('${s.stock_code}')">详情 →</a></td></tr>`;
  }
  html += `</table></div>`;
  el.innerHTML = html;
}

function showStockDetail(code) {
  showView('detail');
  const el = document.getElementById('view-detail');
  const stocks = appData.stocks?.stocks || [];
  const s = stocks.find(x => x.stock_code === code) || {stock_code: code, stock_name: code};

  const ev = appData.evidence;
  const items = ev?.evidence_items || [];

  let html = `<span class="back-link" onclick="showView('dashboard')">← 返回驾驶舱</span>`;
  html += `<div class="grid-2">`;
  html += `<div class="card"><h2>${s.stock_name} (${s.stock_code}) — 今日决策</h2>`;
  html += `<table><tr><td>收盘</td><td>${s.close}</td></tr>`;
  html += `<tr><td>涨跌幅</td><td class="${s.change_pct > 0 ? 'up' : 'down'}">${s.change_pct > 0 ? '+' : ''}${s.change_pct}%</td></tr>`;
  html += `<tr><td>状态</td><td>${statusBadge(s.user_visible_status)}</td></tr></table>`;
  html += `<div class="chart-placeholder" style="margin-top:12px">📊 技术分析图表 — MA5/MA20/MACD/RSI</div>`;
  html += `</div>`;

  html += `<div class="card"><h2>证据链</h2><ul class="evidence-list">`;
  for (const item of items) {
    html += `<li><strong>${item.source_type}</strong>: ${item.summary} <span style="color:var(--text-dim);font-size:12px">[${item.chart_hint}]</span></li>`;
  }
  html += `</ul></div></div>`;

  html += `<div class="card"><h2>次日决策</h2>
    <p>主要动作: <strong>持有/观察</strong></p>
    <p>触发条件: 若跌破 MA20 则减仓; 若放量突破压力位则加仓</p>
    <p>禁止动作: 不要在无确认信号前提早止损</p>
  </div>`;

  el.innerHTML = html;
}

/* ── Deep Analysis ── */
window.renderDeepAnalysis = function() {
  const el = document.getElementById('view-deep');
  el.innerHTML = `<div class="grid-2">
    <div class="card"><h2>深度分析 — 600114 东睦股份</h2>
      <h3>核心结论</h3>
      <p style="color:var(--text-dim);margin-bottom:12px">基于 Phase 1 本地 K 线缓存和 MA20 止损规则，当前走势偏弱，建议持有/观察。</p>
      <h3>风险</h3>
      <p style="color:var(--warn)">⚠ MA20 破位止损规则近期表现 WARN（3Y 胜率 21%）</p>
      <h3>建议动作</h3>
      <p>持有为主，若收盘跌破 MA20（38.68）考虑减仓。</p>
    </div>
    <div class="card"><h2>证据支持</h2>
      <div class="chart-placeholder">📈 MA20 破位历史回测图表 — 3Y/1Y/6M 窗口对比</div>
      <div style="margin-top:12px"><h3>来源与时间</h3>
      <p class="evidence-list">数据来源: kline_cache/600114.json<br>最后更新: 20260615<br>规则版本: v1.0</p></div>
    </div>
  </div>`;
};

/* ── Daily Analysis ── */
window.renderDailyAnalysis = function() {
  const el = document.getElementById('view-daily');
  el.innerHTML = `<div class="card"><h2>每日分析 — 2026-06-16 东睦股份</h2>
    <div class="grid-2">
      <div><h3>今日走势</h3>
        <div class="chart-placeholder" style="height:150px">📊 日内 K 线图</div>
        <p style="margin-top:8px">开盘/最高/最低/收盘: 40.20 / 41.23 / 38.26 / 38.57</p>
        <p>走势类型: 冲高回落</p>
      </div>
      <div><h3>相对于 Baseline</h3>
        <p>支撑: -</p>
        <p>压力: -</p>
        <p>止损: MA20 (38.68)</p>
        <p style="color:var(--warn)">⚠ 当前价格 (38.57) 已跌破 MA20</p>
      </div>
    </div>
    <h3 style="margin-top:16px">次日决策</h3>
    <p>若明日反弹回 MA20 上方: 继续持有</p>
    <p>若继续跌破前低: 考虑减仓至 50%</p>
  </div>`;
};

/* ── Rule Health ── */
function renderRuleHealth() {
  const el = document.getElementById('view-rules');
  const rh = appData.ruleHealth || {};
  const cells = rh.recent_cells || [];

  let html = `<div class="grid-2">`;
  html += `<div class="card"><h2>${rh.rule_name || 'MA20 破位止损'}</h2>`;
  html += `<table><tr><td>状态</td><td>${statusBadge(rh.rule_status)}</td></tr>`;
  html += `<tr><td>样本数</td><td>${rh.sample_count}</td></tr>`;
  html += `<tr><td>命中</td><td>${rh.hit_count}</td></tr>`;
  html += `<tr><td>偏离</td><td>${rh.miss_count}</td></tr>`;
  html += `<tr><td>观察</td><td>${rh.observe_count}</td></tr>`;
  html += `<tr><td>衰减分数</td><td>${rh.decay_score ?? '-'}</td></tr>`;
  html += `<tr><td>未来函数风险</td><td>${rh.future_leakage_risk ? '⚠ 是' : '✅ 否'}</td></tr>`;
  html += `<tr><td>影响股票</td><td>${(rh.affected_stocks || []).join(', ') || '-'}</td></tr>`;
  html += `</table></div>`;

  html += `<div class="card"><h2>说明</h2><p>${rh.explanation || ''}</p>
    <div style="margin-top:12px"><h3>格子状态含义</h3>
    <p><span class="status-badge status-PASS" style="margin-right:4px">HIT</span> 规则判断被后续走势验证</p>
    <p><span class="status-badge status-BLOCK" style="margin-right:4px">MISS</span> 规则判断与后续走势偏离</p>
    <p><span class="status-badge status-OBSERVE" style="margin-right:4px">OBS</span> 样本不足，只观察不处罚</p>
    <p><span class="status-badge status-WARN" style="margin-right:4px">WARN</span> 衰减/未来函数风险/证据缺失</p>
    </div>
  </div></div>`;

  if (cells.length > 0) {
    html += `<div class="card"><h2>规则矩阵</h2><div class="matrix">`;
    html += `<div class="matrix-row matrix-header"><span>样本</span>`;
    for (const c of cells) html += `<span>${c.trade_date.slice(-4)}</span>`;
    html += `</div>`;
    html += `<div class="matrix-row"><span>${rh.rule_id}</span>`;
    for (const c of cells) html += `<div class="matrix-cell ${c.state}">${c.state}</div>`;
    html += `</div></div>`;
    html += `<p style="color:var(--text-dim);font-size:12px;margin-top:8px">每列代表一个窗口样本。点击行可展开详情。</p>`;
    html += `</div>`;
  }

  html += `<div class="card"><h2>影响股票详情</h2><table><tr><th>股票</th><th>窗口</th><th>状态</th><th>原因</th></tr>`;
  for (const c of cells) {
    html += `<tr><td>${c.stock_code}</td><td>${c.trade_date}</td><td>${statusBadge(c.state)}</td><td>${c.reason || '-'}</td></tr>`;
  }
  html += `</table></div>`;

  el.innerHTML = html;
}
