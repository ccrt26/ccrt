/* keystock-dashboard 产品化驾驶舱 JS — 真实数据驱动，无硬编码业务结论 */
let appData = {};

async function loadJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${path}`);
  return r.json();
}

function statusBadge(s) {
  return `<span class="badge badge-${(s || 'UNKNOWN').toLowerCase()}">${s || 'UNKNOWN'}</span>`;
}

async function init() {
  const el = document.getElementById('view-dashboard');
  try {
    const results = await Promise.allSettled([
      loadJSON('data/dashboard.json').then(d => appData.dashboard = d),
      loadJSON('data/stocks.json').then(d => appData.stocks = d),
      loadJSON('data/today_decisions.json').then(d => appData.decisions = d),
      loadJSON('data/chart_data.json').then(d => appData.chartData = d),
      loadJSON('data/evidence_index.json').then(d => appData.evidence = d),
      loadJSON('data/rule_health.json').then(d => appData.ruleHealth = d),
    ]);
    const failed = results.filter(r => r.status === 'rejected');
    if (failed.length > 0) {
      el.innerHTML = `<div class="card warn"><p>数据加载异常 (${failed.length}/${results.length} 失败)</p><ul>${failed.map(r => `<li>${r.reason.message}</li>`).join('')}</ul></div>`;
    }
  } catch(e) {
    el.innerHTML = `<div class="card warn"><p>数据加载失败: ${e.message}</p></div>`;
  }
  renderDashboard();
  renderStocks();
  renderRuleHealth();
}

/* ── 视图切换 ── */
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const el = document.getElementById('view-' + name);
  if (el) el.classList.add('active');
  document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
  const link = document.querySelector(`.sidebar a[data-view="${name}"]`);
  if (link) link.classList.add('active');
}

/* ── 驾驶舱首页 ── */
function renderDashboard() {
  const el = document.getElementById('view-dashboard');
  const d = appData.dashboard || {};
  const dec = appData.decisions || {};
  const pos = dec.user_position || {};
  const mkt = dec.market_today || {};
  const cd = appData.chartData || {};

  let warnHtml = '';
  const warnings = d.warnings || [];
  if (warnings.length > 0) warnHtml = `<div class="card warn"><p>⚠ ${warnings.join('; ')}</p></div>`;

  const missingFlags = d.missing_data_flags || [];
  let missHtml = '';
  if (missingFlags.length > 0) missHtml = `<div class="card dim"><p>缺失数据: ${missingFlags.join(', ')}</p></div>`;

  el.innerHTML = `
    <div class="card">
      <div class="stock-header">
        <div>
          <h2>${d.primary_stock_name || '-'} (${d.primary_stock_code || '-'})</h2>
          <span class="meta">as_of: ${d.as_of_date || '-'} | 数据源: ${d.source_summary || '-'}</span>
        </div>
        <div>${statusBadge(d.overall_status)}</div>
      </div>
    </div>
    ${warnHtml}
    ${missHtml}

    <div class="grid-2">
      <div class="card">
        <h3>行情与状态</h3>
        <table>
          <tr><td>收盘价</td><td class="${mkt.close !== null && (dec.primary_action === 'observe' || (mkt.ma20 !== null && mkt.close < mkt.ma20)) ? 'down' : ''}">${mkt.close != null ? mkt.close.toFixed(2) : '—'}</td></tr>
          <tr><td>MA5</td><td>${mkt.ma5 != null ? mkt.ma5.toFixed(2) : '—'}</td></tr>
          <tr><td>MA20</td><td class="${mkt.ma20 != null && mkt.close < mkt.ma20 ? 'down' : ''}">${mkt.ma20 != null ? mkt.ma20.toFixed(2) : '—'}</td></tr>
          <tr><td>MA60</td><td>${mkt.ma60 != null ? mkt.ma60.toFixed(2) : '—'}</td></tr>
          <tr><td>RSI14</td><td>${mkt.rsi14 != null ? mkt.rsi14.toFixed(2) : '—'}</td></tr>
          <tr><td>规则健康</td><td>${statusBadge(dec.rule_health_status)}</td></tr>
          <tr><td>K线数</td><td>${cd.total_kline_rows || '—'}</td></tr>
        </table>
      </div>
      <div class="card">
        <h3>持仓</h3>
        <table>
          <tr><td>持仓状态</td><td>${pos.has_position ? '有持仓' : '未接入持仓账本'}</td></tr>
          <tr><td>成本价</td><td>${pos.cost_price != null ? pos.cost_price : '不可用'}</td></tr>
          <tr><td>盈亏</td><td>${pos.unrealized_pnl != null ? pos.unrealized_pnl : '不可用'}</td></tr>
          <tr><td colspan="2" class="dim-text">${pos.note || ''}</td></tr>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>今日判断</h3>
      <p><strong>建议动作</strong>: ${dec.primary_action === 'observe' ? '观察' : dec.primary_action === 'hold' ? '持有' : '—'} (置信度: ${dec.confidence != null ? (dec.confidence * 100).toFixed(0) + '%' : '—'})</p>
      <p><strong>依据</strong>: ${dec.reasoning || '数据不足'}</p>
    </div>

    <div class="grid-2">
      <div class="card"><h3>收盘价走势与 MA</h3>
        <canvas id="chart-kline" height="220" style="width:100%"></canvas>
        <p class="dim-text">来源: 代码文件/数据/kline_cache/600114.json</p>
      </div>
      <div class="card"><h3>成交量</h3>
        <canvas id="chart-volume" height="200" style="width:100%"></canvas>
      </div>
    </div>
  `;
  renderKlineChart('chart-kline', cd);
  renderVolumeChart('chart-volume', cd);
}

/* ── 股票列表 ── */
function renderStocks() {
  const el = document.getElementById('view-stocks');
  const stocks = (appData.stocks || {}).stocks || [];
  let html = `<div class="card"><h3>全部股票</h3><table><tr><th>代码</th><th>名称</th><th>收盘</th><th>日期</th><th>状态</th></tr>`;
  for (const s of stocks) {
    html += `<tr><td>${s.stock_code}</td><td>${s.stock_name}</td><td>${s.close != null ? s.close.toFixed(2) : '—'}</td><td>${s.actual_trade_date || '—'}</td><td>${statusBadge(s.user_visible_status)}</td></tr>`;
  }
  html += `</table><p class="dim-text">仅展示有真实证据链的股票。当前证据覆盖: 600114 (kline_cache + feature_snapshot + backtest)</p></div>`;
  el.innerHTML = html;
}

/* ── 深度分析 ── */
function renderDeepAnalysis() {
  const el = document.getElementById('view-deep');
  el.innerHTML = `
    <div class="card">
      <h2>深度分析 — 600114 东睦股份</h2>
      <p class="dim-text">报告正文暂未结构化解析。以下信息来自 active baseline 和证据文件。</p>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Active Baseline</h3>
        <table>
          <tr><td>baseline 文件</td><td>重点股票/基线/东睦股份(600114)_baseline_2026W25.json</td></tr>
          <tr><td>支撑/压力/止损</td><td>见基线文件</td></tr>
          <tr><td>数据新鲜度</td><td>可能需验证</td></tr>
        </table>
        <p class="dim-text" style="margin-top:8px">源文件只读，未作为本阶段交付物。</p>
      </div>
      <div class="card">
        <h3>证据链引用</h3>
        <table>
          <tr><td>feature_snapshot</td><td>运行产物/.../feature_snapshot_600114_20260616.json</td></tr>
          <tr><td>backtest</td><td>运行产物/.../backtest_TECH_MA20_BREAK_STOP_LOSS_600114.json</td></tr>
          <tr><td>kline_cache</td><td>代码文件/数据/kline_cache/600114.json</td></tr>
        </table>
      </div>
    </div>
  `;
}

/* ── 每日分析 ── */
function renderDailyAnalysis() {
  const el = document.getElementById('view-daily');
  const cd = appData.chartData || {};
  const ohlc = cd.ohlc || [];
  const last = ohlc.length > 0 ? ohlc[ohlc.length - 1] : null;
  const prev = ohlc.length > 1 ? ohlc[ohlc.length - 2] : null;

  el.innerHTML = `
    <div class="card">
      <h2>每日分析 — ${last ? last.date : '—'} 600114 东睦股份</h2>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>今日行情 (kline_cache)</h3>
        <table>
          <tr><td>日期</td><td>${last ? last.date : '—'}</td></tr>
          <tr><td>开盘</td><td>${last ? last.open.toFixed(2) : '—'}</td></tr>
          <tr><td>最高</td><td>${last ? last.high.toFixed(2) : '—'}</td></tr>
          <tr><td>最低</td><td>${last ? last.low.toFixed(2) : '—'}</td></tr>
          <tr><td>收盘</td><td class="${last && prev && last.close < prev.close ? 'down' : ''}">${last ? last.close.toFixed(2) : '—'}</td></tr>
          <tr><td>数据源</td><td class="dim-text">代码文件/数据/kline_cache/600114.json</td></tr>
        </table>
      </div>
      <div class="card">
        <h3>次日观察条件</h3>
        <p>当前未生成强买卖动作。建议关注:</p>
        <ul style="margin-left:16px;margin-top:8px;color:var(--text-dim)">
          ${last && cd.ma20 && cd.ma20.length > 0 ? `<li>收盘价 (${last.close.toFixed(2)}) 相对 MA20 (${cd.ma20[cd.ma20.length-1].ma20.toFixed(2)})</li>` : ''}
          <li>规则健康状态: ${statusBadge((appData.ruleHealth || {}).rule_status)}</li>
          <li>持仓未接入, 不生成持仓比例建议</li>
        </ul>
      </div>
    </div>
    <div class="card"><canvas id="chart-kline-daily" height="220" style="width:100%"></canvas></div>
  `;
  renderKlineChart('chart-kline-daily', cd);
}

/* ── 规则健康 ── */
function renderRuleHealth() {
  const el = document.getElementById('view-rules');
  const rh = appData.ruleHealth || {};
  const cells = rh.recent_cells || [];

  let html = `<div class="grid-2">
    <div class="card"><h3>${rh.rule_name || 'MA20 破位止损'}</h3>
      <table>
        <tr><td>状态</td><td>${statusBadge(rh.rule_status)}</td></tr>
        <tr><td>样本数</td><td>${rh.sample_count}</td></tr>
        <tr><td>命中</td><td>${rh.hit_count} <span class="dim-text">(${rh.sample_count > 0 ? (rh.hit_count / rh.sample_count * 100).toFixed(0) : 0}%)</span></td></tr>
        <tr><td>偏离</td><td>${rh.miss_count}</td></tr>
        <tr><td>观察</td><td>${rh.observe_count}</td></tr>
        <tr><td>衰减分数</td><td>${rh.decay_score ?? '—'}</td></tr>
        <tr><td>未来函数风险</td><td>${rh.future_leakage_risk ? '⚠ 有风险' : '✅ 未检测到'}</td></tr>
        <tr><td>影响股票</td><td>${(rh.affected_stocks || []).join(', ') || '—'}</td></tr>
      </table>
    </div>
    <div class="card"><h3>格子状态说明</h3>
      <p><span class="badge badge-hit">HIT</span> 规则判断被后续走势验证</p>
      <p><span class="badge badge-miss">MISS</span> 规则判断与后续走势偏离</p>
      <p><span class="badge badge-obs">OBS</span> 样本不足，只观察不处罚</p>
      <p><span class="badge badge-warn">WARN</span> 衰减/未来函数风险/证据缺失</p>
      <p class="dim-text" style="margin-top:8px">${rh.explanation || ''}</p>
    </div>
  </div>`;

  if (cells.length > 0) {
    html += `<div class="card"><h3>规则矩阵</h3><div class="matrix"><div class="matrix-row matrix-header"><span>样本</span>${cells.map(c => `<span class="dim-text">${c.trade_date.slice(-4)}</span>`).join('')}</div>`;
    html += `<div class="matrix-row"><span>${rh.rule_id}</span>${cells.map(c => `<div class="matrix-cell ${c.state}">${c.state}</div>`).join('')}</div></div></div>`;
  }

  html += `<div class="card"><h3>影响股票</h3><table><tr><th>股票</th><th>窗口</th><th>状态</th><th>原因</th></tr>`;
  for (const c of cells) html += `<tr><td>${c.stock_code}</td><td>${c.trade_date}</td><td>${statusBadge(c.state)}</td><td class="dim-text">${c.reason || '—'}</td></tr>`;
  html += `</table></div>`;

  el.innerHTML = html;
}

/* ── K 线图表 ── */
function renderKlineChart(canvasId, cd) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width || 600;
  canvas.height = canvas.height || 220;

  const ohlc = cd.ohlc || [];
  if (ohlc.length < 5) {
    ctx.font = '14px sans-serif'; ctx.fillStyle = '#8899aa';
    ctx.fillText('K 线数据不足 (≥5 根)', 20, 40); return;
  }

  const W = canvas.width, H = canvas.height;
  const pad = {t: 20, r: 10, b: 30, l: 50};
  const chartW = W - pad.l - pad.r;
  const chartH = H - pad.t - pad.b;

  const prices = ohlc.map(o => o.close);
  const minP = Math.min(...prices) * 0.98, maxP = Math.max(...prices) * 1.02;
  const xStep = chartW / (ohlc.length - 1);
  const yScale = (v) => pad.t + chartH - (v - minP) / (maxP - minP) * chartH;

  ctx.clearRect(0, 0, W, H);

  // grid
  ctx.strokeStyle = '#2a3a4a'; ctx.lineWidth = 0.5;
  for (let y = pad.t; y < pad.t + chartH; y += 40) { ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke(); }

  // MA lines
  for (const [key, color] of [['ma5','#4fc3f7'], ['ma20','#ff9800'], ['ma60','#ab47bc']]) {
    const vals = cd[key] || [];
    if (vals.length < 2) continue;
    ctx.strokeStyle = color; ctx.lineWidth = 1.5;
    ctx.beginPath();
    let first = true;
    for (const v of vals) {
      const idx = ohlc.findIndex(o => o.date === v.date);
      if (idx < 0) continue;
      const x = pad.l + idx * xStep;
      const y = yScale(v[key]);
      if (first) { ctx.moveTo(x, y); first = false; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // Legend
  ctx.font = '11px sans-serif';
  let lx = pad.l;
  for (const [key, color, label] of [['close','#e0e8f0','收盘'], ['ma5','#4fc3f7','MA5'], ['ma20','#ff9800','MA20']]) {
    ctx.fillStyle = color; ctx.fillRect(lx, 5, 12, 8);
    ctx.fillStyle = '#8899aa'; ctx.fillText(label, lx + 16, 13);
    lx += 50;
  }
}
function renderVolumeChart(canvasId, cd) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width || 600;
  canvas.height = canvas.height || 200;

  const vols = cd.volume || [];
  if (vols.length < 5) { ctx.font = '14px sans-serif'; ctx.fillStyle = '#8899aa'; ctx.fillText('量能数据不足', 20, 40); return; }

  const W = canvas.width, H = canvas.height;
  const pad = {t: 10, r: 10, b: 20, l: 50};
  const chartW = W - pad.l - pad.r, chartH = H - pad.t - pad.b;
  const maxVol = Math.max(...vols.map(v => v.volume));
  const barW = Math.max(2, (chartW / vols.length) * 0.6);

  ctx.clearRect(0, 0, W, H);
  for (let i = 0; i < vols.length; i++) {
    const x = pad.l + (chartW) * i / (vols.length - 1);
    const h = (vols[i].volume / maxVol) * chartH;
    ctx.fillStyle = '#2a5a8a';
    ctx.fillRect(x - barW/2, pad.t + chartH - h, barW, h);
  }
}
