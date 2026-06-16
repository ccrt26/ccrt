/* keystock-dashboard 产品化驾驶舱 JS — 会话四版
 * 首页只加载 4 JSON；股票池驱动；状态闸门；详情懒加载；证据链展示。
 */
let appData = {};
let selectedStockCode = null;

async function loadJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${path}`);
  return r.json();
}

function statusBadge(s) {
  return `<span class="badge badge-${(s || 'UNKNOWN').toLowerCase()}">${s || 'UNKNOWN'}</span>`;
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '—';
  return String(s);
}

/* ── A. 首页加载：只加载 4 JSON ── */
async function loadHomeBundle() {
  const el = document.getElementById('view-dashboard');
  try {
    const results = await Promise.allSettled([
      loadJSON('data/stock_pool.json').then(d => appData.pool = d),
      loadJSON('data/stocks.json').then(d => appData.stocks = d),
      loadJSON('data/bundle_index.json').then(d => appData.bundleIndex = d),
      loadJSON('data/run_manifest.json').then(d => appData.runManifest = d),
    ]);
    const failed = results.filter(r => r.status === 'rejected');
    if (failed.length > 0) {
      if (el) el.innerHTML = `<div class="card warn"><p>⚠ 数据加载异常 (${failed.length}/${results.length} 失败)</p><ul>${failed.map(r => `<li>${r.reason.message}</li>`).join('')}</ul></div>`;
      return;
    }
  } catch (e) {
    if (el) el.innerHTML = `<div class="card block"><p>❌ 首页加载失败: ${escapeHtml(e.message)}</p></div>`;
    return;
  }
  // 渲染 bundle 状态、股票池、默认选中
  resolveBundleStatus();
  renderPoolList();
  renderStockSummaries();

  // 默认选中股票池第一只但**不加载详情**（首页只展示占位符）
  const members = getPoolMembers();
  if (members.length > 0) {
    selectedStockCode = members[0].stock_code;
    renderPoolList();
    renderDetailPlaceholder(selectedStockCode);
  }
}

/* ── B. resolveBundleStatus ── */
function resolveBundleStatus() {
  const el = document.getElementById('bundle-status');
  if (!el) return;
  const bi = appData.bundleIndex || {};
  const rm = appData.runManifest || {};
  const biRunId = bi.run_id || '';
  const rmRunId = rm.run_id || '';

  let state = 'READY';
  let stateClass = 'badge-pass';
  let messages = [];

  if (!biRunId) {
    state = 'NO_INDEX'; stateClass = 'badge-block';
    messages.push('bundle_index 不可用');
  }
  if (!rmRunId) {
    state = 'NO_MANIFEST'; stateClass = 'badge-block';
    messages.push('run_manifest 不可用');
  }
  if (biRunId && rmRunId && biRunId !== rmRunId) {
    state = 'RUN_ID_MISMATCH'; stateClass = 'badge-block';
    messages.push(`run_id 不一致 (bi=${biRunId} rm=${rmRunId})`);
  }
  if (bi.publish_status && bi.publish_status !== 'PUBLISHED') {
    state = 'NOT_PUBLISHED'; stateClass = 'badge-warn';
    messages.push(`publish_status=${bi.publish_status}`);
  }
  if (rm.engineering_status === 'BLOCK') {
    messages.push('engineering BLOCK');
  }

  const busStatus = rm.business_user_visible_status || 'UNKNOWN';
  if (busStatus === 'BLOCK') {
    stateClass = 'badge-block';
  }

  el.innerHTML = `
    <div class="card">
      <h2>📦 数据包状态</h2>
      <table>
        <tr><td>run_id</td><td class="dim-text" style="font-size:11px">${escapeHtml(biRunId)}</td></tr>
        <tr><td>状态</td><td>${statusBadge(state)}</td></tr>
        <tr><td>publish_status</td><td>${statusBadge(bi.publish_status || '?')}</td></tr>
        <tr><td>engineering_status</td><td>${statusBadge(rm.engineering_status || '?')}</td></tr>
        <tr><td>业务可见状态</td><td>${statusBadge(busStatus)}</td></tr>
        <tr><td>bundle_version</td><td class="dim-text">${escapeHtml(bi.bundle_version || '')}</td></tr>
        <tr><td>schema_version</td><td class="dim-text" style="font-size:11px">${escapeHtml(bi.schema_version || '')}</td></tr>
        <tr><td>生成时间</td><td class="dim-text">${escapeHtml(bi.generated_at || '')}</td></tr>
        <tr><td>current_bundle_path</td><td class="dim-text" style="font-size:11px">${escapeHtml(bi.current_bundle_path || '')}</td></tr>
      </table>
      ${messages.length > 0 ? `<div class="card warn" style="margin-top:8px"><p>${messages.join('; ')}</p></div>` : ''}
      ${rm.blocks && rm.blocks.length > 0 ? `<div class="card block" style="margin-top:8px"><p>阻断原因:</p><ul>${rm.blocks.map(b => `<li class="blocker-code">${b}</li>`).join('')}</ul></div>` : ''}
      ${rm.warnings && rm.warnings.length > 0 ? `<div class="card dim" style="margin-top:8px"><p>警告: ${rm.warnings.join(', ')}</p></div>` : ''}
    </div>`;
}

/* ── C. getPoolMembers ── */
function getPoolMembers() {
  return (appData.pool || {}).members || [];
}

/* ── D. getStockSummary ── */
function getStockSummary(stockCode) {
  const stocks = (appData.stocks || {}).stocks || [];
  return stocks.find(s => s.stock_code === stockCode) || null;
}

/* ── 渲染股票池列表 ── */
function renderPoolList() {
  const el = document.getElementById('stock-pool-list');
  if (!el) return;
  const members = getPoolMembers();
  if (members.length === 0) {
    el.innerHTML = '<p class="dim-text">股票池为空</p>';
    return;
  }
  let html = '<div class="stock-pool-list">';
  for (const m of members) {
    const code = escapeHtml(m.stock_code);
    const name = escapeHtml(m.stock_name);
    const status = escapeHtml(m.status);
    const summary = getStockSummary(m.stock_code);
    const close = summary && summary.close != null ? summary.close.toFixed(2) : '—';
    const uvStatus = summary ? summary.user_visible_status : status;
    const activeClass = (selectedStockCode === m.stock_code) ? ' active' : '';
    html += `<div class="stock-item${activeClass}" onclick="selectStock('${code}')">
      <span class="stock-code">${code}</span>
      <span class="stock-name">${name}</span>
      <span class="stock-close">${close}</span>
      <span>${statusBadge(uvStatus)}</span>
    </div>`;
  }
  html += '</div>';
  el.innerHTML = html;
}

/* ── 渲染股票摘要列表 ── */
function renderStockSummaries() {
  const el = document.getElementById('stock-summaries');
  if (!el) return;
  const members = getPoolMembers();
  const stocks = (appData.stocks || {}).stocks || [];
  if (stocks.length === 0) {
    el.innerHTML = '<p class="dim-text">摘要不可用</p>';
    return;
  }
  let html = '<div class="card"><h2>📋 股票摘要</h2><table><tr><th>代码</th><th>名称</th><th>收盘</th><th>日期</th><th>状态</th></tr>';
  for (const s of stocks) {
    const code = escapeHtml(s.stock_code);
    const name = escapeHtml(s.stock_name);
    const close = s.close != null ? s.close.toFixed(2) : '—';
    const date = escapeHtml(s.actual_trade_date || '—');
    html += `<tr class="clickable" onclick="selectStock('${code}')"><td>${code}</td><td>${name}</td><td>${close}</td><td>${date}</td><td>${statusBadge(s.user_visible_status || '?')}</td></tr>`;
  }
  html += '</table></div>';
  el.innerHTML = html;
}

/* ── 详情占位符（首页不加载任何详情分片） ── */
function renderDetailPlaceholder(stockCode) {
  const detailEl = document.getElementById('view-detail');
  const statusGateEl = document.getElementById('status-gate');
  const blockEl = document.getElementById('block-reasons');
  const posEl = document.getElementById('position-public');
  const chartEl = document.getElementById('chart-area');
  const evidenceEl = document.getElementById('evidence');
  if (detailEl) detailEl.innerHTML = '<div class="card dim"><p>请选择股票查看详情</p><p class="dim-text">' + escapeHtml(stockCode || '') + '</p></div>';
  if (statusGateEl) statusGateEl.innerHTML = '';
  if (blockEl) blockEl.innerHTML = '';
  if (posEl) posEl.innerHTML = '';
  if (chartEl) chartEl.innerHTML = '';
  if (evidenceEl) evidenceEl.innerHTML = '';
}

/* ── E. selectStock / loadStockAssets ── */
async function selectStock(stockCode) {
  if (!stockCode) return;
  selectedStockCode = stockCode;
  renderPoolList();

  const detailEl = document.getElementById('view-detail');
  const statusGateEl = document.getElementById('status-gate');
  const chartEl = document.getElementById('chart-area');
  const evidenceEl = document.getElementById('evidence');
  const blockEl = document.getElementById('block-reasons');
  const posEl = document.getElementById('position-public');

  // 立即显示加载中
  if (detailEl) detailEl.innerHTML = '<div class="card"><p class="dim-text">加载详情…</p></div>';

  let detail = null;
  let chartData = null;
  let evidence = null;
  try {
    [detail, chartData, evidence] = await Promise.all([
      loadJSON(`data/stocks/${stockCode}/detail.json`),
      loadJSON(`data/stocks/${stockCode}/chart_data.json`),
      loadJSON(`data/stocks/${stockCode}/evidence.json`),
    ]);
  } catch (e) {
    if (detailEl) detailEl.innerHTML = `<div class="card block"><p>❌ 数据分片不可用: ${escapeHtml(stockCode)}</p><p class="dim-text">${escapeHtml(e.message)}</p></div>`;
    if (statusGateEl) statusGateEl.innerHTML = '';
    if (chartEl) chartEl.innerHTML = '';
    if (evidenceEl) evidenceEl.innerHTML = '';
    if (blockEl) blockEl.innerHTML = '';
    if (posEl) posEl.innerHTML = '';
    return;
  }

  // 按区域渲染
  renderStatusGate(detail, statusGateEl);
  renderDecisionBoundary(detail, blockEl);
  renderPositionPublicView(detail, posEl);
  renderCharts(chartData, chartEl);
  renderEvidence(evidence, detail, chartData, evidenceEl);
  renderStockDetailName(detail);
}

function renderStockDetailName(detail) {
  const el = document.getElementById('view-detail');
  if (!el || !detail) return;
  const name = escapeHtml(detail.stock_name || '') + ' (' + escapeHtml(detail.stock_code || '') + ')';
  const status = escapeHtml(detail.user_visible_status || '');
  const date = escapeHtml(detail.trade_date || '');
  el.innerHTML = `
    <div class="stock-header-detail">
      <h2>${name}</h2>
      <span>${statusBadge(status)}</span>
    </div>
    <p class="dim-text" style="margin-bottom:12px">交易日: ${date} | 数据新鲜度: ${escapeHtml(detail.data_freshness || '')}</p>
  `;
}

/* ── F. renderStatusGate ── */
function renderStatusGate(detail, containerEl) {
  if (!containerEl || !detail) return;
  const cs = detail.conclusion_status || 'UNKNOWN';
  const ds = (detail.status_gate || {}).data_status || '';
  const db = detail.decision_blockers || [];

  let csClass = 'badge-observation';
  if (cs === 'FORMAL') csClass = 'badge-pass';
  else if (cs === 'OBSERVATION') csClass = 'badge-warn';
  else if (cs === 'SHADOW') csClass = 'badge-obs';
  else if (cs === 'BLOCKED') csClass = 'badge-block';

  let actionsHtml = '';
  if (canShowFormalAction(detail)) {
    actionsHtml = '<div class="card pass" style="margin-top:8px"><p>✅ FORMAL — 允许正式决策展示</p></div>';
  }

  const dataStatus = detail.data_freshness || (detail.status_gate || {}).data_status || 'UNKNOWN';

  containerEl.innerHTML = `
    <div class="card">
      <h2>🛡 状态闸门</h2>
      <table>
        <tr><td>conclusion_status</td><td><span class="badge ${csClass}">${cs}</span></td></tr>
        <tr><td>user_visible_status</td><td>${statusBadge(detail.user_visible_status || '?')}</td></tr>
        <tr><td>data_status</td><td>${statusBadge(dataStatus)}</td></tr>
        <tr><td>decision_blockers</td><td>${db.length > 0 ? db.map(b => `<span class="blocker-code">${b}</span>`).join(' ') : '—'}</td></tr>
      </table>
      <div style="margin-top:8px">
        <span class="badge badge-pass">FORMAL</span>
        <span class="badge badge-warn">OBSERVATION</span>
        <span class="badge badge-obs">SHADOW</span>
        <span class="badge badge-block">BLOCKED</span>
      </div>
      ${actionsHtml}
    </div>`;
}

/* ── G. canShowFormalAction ── */
function canShowFormalAction(detail) {
  if (!detail) return false;
  const cs = detail.conclusion_status;
  const uv = detail.user_visible_status;
  const blockers = detail.decision_blockers || [];
  const posStatus = (((detail.position_public_view || {}).position_status) || 'UNAVAILABLE');
  if (cs !== 'FORMAL') return false;
  if (uv === 'BLOCK') return false;
  if (blockers.length > 0) return false;
  if (posStatus === 'UNAVAILABLE') return false;
  return true;
}

/* ── H. renderDecisionBoundary ── */
function renderDecisionBoundary(detail, containerEl) {
  if (!containerEl || !detail) return;
  const cs = detail.conclusion_status || 'UNKNOWN';
  const db = detail.decision_blockers || [];
  const ruleHealth = detail.rule_health_status || '?';
  const freshness = detail.data_freshness || (detail.status_gate || {}).data_status || '?';

  if (canShowFormalAction(detail)) {
    containerEl.innerHTML = `
      <div class="card pass">
        <h2>📊 正式动作</h2>
        <p>当前结论状态支持正式决策展示。</p>
        <p class="dim-text">（正式动作区域预留）</p>
      </div>`;
    return;
  }

  // BLOCKED / OBSERVATION / SHADOW — 仅展示观察条件
  let boundaryClass = 'dim';
  let boundaryLabel = '观察模式';
  if (cs === 'BLOCKED') { boundaryClass = 'block'; boundaryLabel = '阻断模式'; }

  containerEl.innerHTML = `
    <div class="card ${boundaryClass}">
      <h2>🔒 决策边界 — ${boundaryLabel}</h2>
      <p class="dim-text">当前不是正式动作。当前结论: ${statusBadge(cs)}</p>
      ${db.length > 0 ? `<div style="margin-top:8px"><strong>阻断原因:</strong><ul>${db.map(b => `<li class="blocker-code">${b}</li>`).join('')}</ul></div>` : ''}
      <div style="margin-top:8px">
        <table>
          <tr><td>规则健康</td><td>${statusBadge(ruleHealth)}</td></tr>
          <tr><td>数据新鲜度</td><td>${statusBadge(freshness)}</td></tr>
        </table>
      </div>
      <p class="dim-text" style="margin-top:8px">观察条件：数据新鲜后重新评估。</p>
    </div>`;
}

/* ── I. renderPositionPublicView ── */
function renderPositionPublicView(detail, containerEl) {
  if (!containerEl || !detail) return;
  const ppv = detail.position_public_view || {};
  const posStatus = ppv.position_status || 'UNAVAILABLE';
  const userPos = detail.user_position || {};
  const db = detail.decision_blockers || [];
  const hasBlock = db.includes('POSITION_UNAVAILABLE');

  containerEl.innerHTML = `
    <div class="card dim">
      <h2>🔑 持仓（公开视图）</h2>
      <table>
        <tr><td>持仓状态</td><td>${statusBadge(posStatus)}</td></tr>
        <tr><td>has_position</td><td>${userPos.has_position === true ? 'true' : 'false'}</td></tr>
        <tr><td>阻断标记</td><td>${hasBlock ? '<span class="blocker-code">POSITION_UNAVAILABLE</span>' : '—'}</td></tr>
      </table>
      <p class="dim-text" style="margin-top:8px">${escapeHtml(ppv.display_note || userPos.note || '持仓未接入')}</p>
    </div>`;
}

/* ── J. renderEvidence ── */
function renderEvidence(evidence, detail, chartData, containerEl) {
  if (!containerEl || !evidence) return;
  const items = evidence.evidence_items || [];
  const evNames = (evidence.evidence_ids || []).map(e => escapeHtml(e)).join(', ');
  const fieldEv = detail && detail.field_evidence;
  const sourceRefs = detail && detail.source_refs;

  let html = `<div class="card"><h2>🔍 证据链</h2>`;
  html += `<p class="dim-text">evidence_ids: ${evNames || '—'}</p>`;

  if (items.length > 0) {
    html += `<table style="margin-top:8px"><tr><th>类型</th><th>来源</th><th>摘要</th><th>状态</th></tr>`;
    for (const item of items) {
      const st = escapeHtml(item.source_type || '');
      const sp = escapeHtml(item.source_path || '');
      const sm = escapeHtml(item.summary || '');
      const ss = item.status || '';
      html += `<tr><td>${st}</td><td class="evidence-path">${sp}</td><td>${sm}</td><td>${statusBadge(ss)}</td></tr>`;
    }
    html += `</table>`;
  }

  if (sourceRefs && sourceRefs.length > 0) {
    html += `<div style="margin-top:8px"><p class="dim-text">source_refs:</p><ul>`;
    for (const sr of sourceRefs) {
      html += `<li class="evidence-path">${escapeHtml(sr)}</li>`;
    }
    html += `</ul></div>`;
  }

  if (chartData) {
    html += `<div style="margin-top:8px"><h3>📈 数据源</h3><table>`;
    html += `<tr><td>source_path</td><td class="evidence-path">${escapeHtml(chartData.source_path || '')}</td></tr>`;
    html += `<tr><td>source_last_date</td><td>${escapeHtml(chartData.source_last_date || '')}</td></tr>`;
    html += `<tr><td>feature_snapshot_actual_date</td><td>${escapeHtml(chartData.feature_snapshot_actual_date || '')}</td></tr>`;
    if (chartData.data_date_divergence) {
      html += `<tr><td>日期分歧</td><td class="down">${escapeHtml(chartData.date_divergence_warning || '')}</td></tr>`;
    }
    html += `</table></div>`;
  }

  html += `</div>`;
  containerEl.innerHTML = html;
}

/* ── K. renderCharts ── */
function renderCharts(chartData, containerEl) {
  if (!containerEl) return;
  if (!chartData || !chartData.ohlc || chartData.ohlc.length < 5) {
    containerEl.innerHTML = '<div class="card dim"><p>📉 K 线数据不足 (≥5 根)</p></div>';
    return;
  }
  containerEl.innerHTML = `
    <div class="card">
      <h2>📈 走势</h2>
      <div class="grid-2">
        <div><canvas id="chart-kline" height="220" style="width:100%"></canvas></div>
        <div><canvas id="chart-volume" height="200" style="width:100%"></canvas></div>
      </div>
    </div>`;
  // 延迟绘制确保 DOM 渲染
  setTimeout(() => {
    renderKlineChart('chart-kline', chartData);
    renderVolumeChart('chart-volume', chartData);
  }, 50);
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

/* ── 遗留视图（兼容） ── */
function renderDeepAnalysis() { /* keep for nav compatibility */ }
function renderDailyAnalysis() { /* keep for nav compatibility */ }
function renderRuleHealth() { /* keep for nav compatibility */ }

/* ── init ── */
async function init() {
  await loadHomeBundle();
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
  ctx.strokeStyle = '#2a3a4a'; ctx.lineWidth = 0.5;
  for (let y = pad.t; y < pad.t + chartH; y += 40) { ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke(); }

  for (const [key, color] of [['ma5','#4fc3f7'], ['ma20','#ff9800'], ['ma60','#ab47bc']]) {
    const vals = cd[key] || [];
    if (vals.length < 2) continue;
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
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

  ctx.font = '11px sans-serif'; let lx = pad.l;
  for (const [key, color, label] of [['close','#e0e8f0','收盘'], ['ma5','#4fc3f7','MA5'], ['ma20','#ff9800','MA20']]) {
    ctx.fillStyle = color; ctx.fillRect(lx, 5, 12, 8);
    ctx.fillStyle = '#8899aa'; ctx.fillText(label, lx + 16, 13); lx += 50;
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
