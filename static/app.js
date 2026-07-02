/* Trump Is The Best — shared front-end logic.
 *
 * SETTINGS STANDARD: every user-customizable setting is stored in ONE cookie
 * (`tib_settings`, JSON). To add a future setting, just call
 * Settings.set('yourKey', value) and read it with Settings.get('yourKey', def).
 * It will persist across sessions automatically — no extra plumbing needed.
 */

const Settings = {
  KEY: 'tib_settings',
  data: {},
  load() {
    try {
      const m = document.cookie.match(/(?:^|; )tib_settings=([^;]*)/);
      this.data = m ? JSON.parse(decodeURIComponent(m[1])) : {};
    } catch (e) { this.data = {}; }
    return this.data;
  },
  save() {
    const v = encodeURIComponent(JSON.stringify(this.data));
    const exp = new Date(Date.now() + 365 * 24 * 3600 * 1000).toUTCString();
    document.cookie = `${this.KEY}=${v}; expires=${exp}; path=/; SameSite=Lax`;
  },
  get(k, d) { return this.data[k] !== undefined ? this.data[k] : d; },
  set(k, v) { this.data[k] = v; this.save(); },
};

const $ = (sel) => document.querySelector(sel);
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------- Theme (light / dark) ---------- */
function currentTheme() { return document.documentElement.classList.contains('dark') ? 'dark' : 'light'; }
function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  Settings.set('theme', theme);
  if (typeof window.__onThemeChange === 'function') window.__onThemeChange(theme);
}

/* ---------- Font size ---------- */
function applyFontSize(px) {
  document.documentElement.style.fontSize = px + 'px';
  Settings.set('fontSize', px);
  const sel = $('#fontSizeSelect');
  if (sel) sel.value = String(px);
}

/* ---------- Greeting ---------- */
function greetingText() {
  const h = new Date().getHours();
  const g = h < 12 ? 'Buenos días' : (h < 19 ? 'Buenas tardes' : 'Buenas noches');
  return `${g}, Miguel`;
}

/* ---------- Fullscreen / restore for chart cards ---------- */
function wireFullscreen() {
  document.querySelectorAll('.card-fs').forEach((card) => {
    const fs = card.querySelector('.js-fullscreen');
    const rs = card.querySelector('.js-restore');
    if (fs) fs.onclick = () => { if (card.requestFullscreen) card.requestFullscreen(); };
    if (rs) rs.onclick = () => { if (document.exitFullscreen) document.exitFullscreen(); };
  });
  document.addEventListener('fullscreenchange', () => {
    document.querySelectorAll('.card-fs').forEach((card) => {
      const on = document.fullscreenElement === card;
      const fs = card.querySelector('.js-fullscreen');
      const rs = card.querySelector('.js-restore');
      if (fs) fs.classList.toggle('hidden', on);
      if (rs) rs.classList.toggle('hidden', !on);
      if (on) card.classList.add('overflow-auto');
    });
    const chartDiv = $('#candleChart');
    if (chartDiv) {
      chartDiv.style.height = document.fullscreenElement
        ? (window.innerHeight - 150) + 'px' : '50vh';
    }
  });
}

/* ---------- Common boot (runs on every page) ---------- */
function boot() {
  Settings.load();

  // Sync UI controls to saved settings (head script already applied visuals).
  const fontSel = $('#fontSizeSelect');
  const savedFont = Settings.get('fontSize', 16);
  applyFontSize(savedFont);
  if (fontSel) fontSel.addEventListener('change', () => applyFontSize(parseInt(fontSel.value, 10)));

  const toggle = $('#themeToggle');
  if (toggle) toggle.addEventListener('click', () =>
    applyTheme(currentTheme() === 'dark' ? 'light' : 'dark'));

  const menuBtn = $('#menuBtn');
  const sidebar = $('#sidebar');
  if (menuBtn && sidebar) menuBtn.addEventListener('click', () =>
    sidebar.classList.toggle('-translate-x-full'));

  const greet = $('#greeting');
  if (greet) greet.textContent = greetingText();
  const greetMini = $('#greetingMini');
  if (greetMini) greetMini.textContent = greetingText();

  wireFullscreen();

  if (window.__PAGE__ === 'drift') initDrift();
}

/* ========================================================================
 *  Drift Sentiment + GEX page
 * ===================================================================== */
function initDrift() {
  const input = $('#tickerInput');
  const dd = $('#tickerDropdown');
  const wrap = $('#tickerWrap');
  const btn = $('#analyzeBtn');
  let debounce;
  // In-session autocomplete cache: query -> results. Ticker reference data is
  // static within a session, so re-typing/backspacing a query serves instantly
  // from here with no extra network round-trip (same results the API returns).
  const searchCache = new Map();

  // Remember the last ticker across sessions.
  input.value = Settings.get('lastTicker', '');

  function closeDD() { dd.classList.add('hidden'); dd.innerHTML = ''; }
  function openDD() { dd.classList.remove('hidden'); }

  function renderDD(items) {
    if (!items.length) { closeDD(); return; }
    dd.innerHTML = items.map((it) => `
      <li data-ticker="${escapeHtml(it.ticker)}"
          class="px-4 py-2.5 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 border-b border-slate-100 dark:border-slate-800 last:border-0 flex items-center justify-between gap-3">
        <span class="font-semibold">${escapeHtml(it.ticker)}</span>
        <span class="text-slate-500 dark:text-slate-400 text-sm truncate">${escapeHtml(it.name || '')}</span>
      </li>`).join('');
    openDD();
    dd.querySelectorAll('li').forEach((li) => {
      // mousedown fires before the input's blur, and preventDefault keeps focus,
      // so the click always registers even with the pointer over the dropdown.
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        input.value = li.dataset.ticker;
        closeDD();
      });
    });
  }

  async function search(q) {
    if (!q) { closeDD(); return; }
    const key = q.toLowerCase();
    if (searchCache.has(key)) { renderDD(searchCache.get(key)); return; }
    try {
      const r = await fetch('/api/search?q=' + encodeURIComponent(q));
      const j = await r.json();
      const items = j.results || [];
      if (items.length) searchCache.set(key, items);  // don't cache empty/error
      renderDD(items);
    } catch (e) { closeDD(); }
  }

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    debounce = setTimeout(() => search(q), 180);
  });
  // Re-open on focus if there is already text (dropdown never closes on blur,
  // so moving the mouse across the gap-free boundary keeps it visible).
  input.addEventListener('focus', () => { if (input.value.trim() && dd.children.length) openDD(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { closeDD(); analyze(); }
    if (e.key === 'Escape') closeDD();
  });
  document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) closeDD(); });

  btn.addEventListener('click', analyze);

  // ---- Tabs (Buckets · Gráfico · Precio Proyectado · Clasificación · Reporte) ----
  const TABS = ['buckets', 'grafico', 'proyeccion', 'clasificacion', 'reporte'];
  function activateTab(name) {
    if (!TABS.includes(name)) name = 'buckets';
    document.querySelectorAll('#tabBar .tab-btn').forEach((b) => {
      const on = b.dataset.tab === name;
      b.classList.toggle('border-brand', on);
      b.classList.toggle('text-brand', on);
      b.classList.toggle('border-transparent', !on);
      b.classList.toggle('text-slate-500', !on);
    });
    document.querySelectorAll('.tab-panel').forEach((p) =>
      p.classList.toggle('hidden', p.dataset.panel !== name));
    Settings.set('activeTab', name);
    // The candlestick chart is built in a hidden panel; nudge its layout on show.
    if (name === 'grafico' && window.__chart) {
      requestAnimationFrame(() => { try { window.__chart.timeScale().fitContent(); } catch (e) {} });
    }
  }
  const tabBar = $('#tabBar');
  if (tabBar) tabBar.addEventListener('click', (e) => {
    const b = e.target.closest('.tab-btn');
    if (b) activateTab(b.dataset.tab);
  });

  // ---- Show / hide GEX levels (γ-Flip, GEX Wall) on the price chart ----
  const gexToggle = $('#gexToggle');
  if (gexToggle) {
    gexToggle.checked = Settings.get('showGex', true);
    gexToggle.addEventListener('change', () => {
      Settings.set('showGex', gexToggle.checked);
      if (window.__chartRedraw) window.__chartRedraw();
    });
  }

  // Rebuild visuals when theme changes.
  window.__onThemeChange = () => {
    if (window.__lastData) buildChart(window.__lastData, currentTheme());
    refreshBoxplot();
  };

  function refreshBoxplot() {
    const d = window.__lastData;
    if (!d) return;
    $('#boxplotImg').src =
      `/api/boxplot?ticker=${encodeURIComponent(d.ticker)}&theme=${currentTheme()}&t=${Date.now()}`;
  }

  async function analyze() {
    const tk = input.value.trim().toUpperCase();
    if (!tk) { setStatus('Escribe un ticker primero.'); return; }
    Settings.set('lastTicker', tk);
    closeDD();
    btn.disabled = true;
    setStatus(`Analizando ${tk}…`, true);
    $('#results').classList.add('hidden');
    try {
      const r = await fetch('/api/analyze?ticker=' + encodeURIComponent(tk));
      const j = await r.json();
      if (j.error) { setStatus('⚠️ ' + j.error); return; }
      if (!j.buckets || !j.buckets.length) {
        setStatus(`No se hallaron expiraciones mensuales con walls de call y put para ${tk}.`);
        return;
      }
      window.__lastData = j;
      render(j);
    } catch (e) {
      setStatus('⚠️ Error de red: ' + e.message);
    } finally {
      btn.disabled = false;
    }
  }

  function setStatus(msg, loading) {
    const el = $('#status');
    el.classList.remove('hidden');
    el.innerHTML = (loading ? '<span class="inline-block animate-pulse">⏳ </span>' : '') + escapeHtml(msg);
  }

  function render(d) {
    $('#status').classList.add('hidden');
    $('#results').classList.remove('hidden');
    renderMetrics(d);
    renderTable(d);
    buildChart(d, currentTheme());
    refreshBoxplot();
    renderDriftCards(d);
    $('#textReport').textContent = d.text_report || '';
    activateTab(Settings.get('activeTab', 'buckets'));
  }
}

/* ---------- Formatting helpers ---------- */
const fmtMoney = (v) => '$' + Math.round(v).toLocaleString('en-US');
const fmtNum = (v, dec = 2) => (v === null || v === undefined) ? '—'
  : Number(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
function biasClasses(bias) {
  if (bias === 'Bullish') return 'bg-bull/15 text-bull';
  if (bias === 'Bearish') return 'bg-bear/15 text-bear';
  return 'bg-slate-400/20 text-slate-500';
}
function biasLabel(bias) {
  return bias === 'Bullish' ? 'Alcista' : bias === 'Bearish' ? 'Bajista' : 'Neutral';
}
function biasBadge(bias) {
  return `<span class="px-2 py-0.5 rounded-full text-xs font-semibold ${biasClasses(bias)}">${biasLabel(bias)}</span>`;
}
function regimeText(b) {
  if (!b.has_gex) return '—';
  return b.total_gex >= 0 ? '🟢 Absorción' : '🔴 Aceleración';
}

/* ---------- Metrics ---------- */
function renderMetrics(d) {
  const gexRegime = d.has_gex ? (d.total_gex >= 0 ? '🟢 Absorción' : '🔴 Aceleración') : 'sin gamma';
  const gexVal = d.has_gex ? fmtMoney(d.total_gex) : 'n/a';
  const card = (label, val, sub, cls = '') => `
    <div class="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div class="text-xs uppercase tracking-wide text-slate-400">${label}</div>
      <div class="text-2xl font-bold mt-1 ${cls}">${val}</div>
      ${sub ? `<div class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">${sub}</div>` : ''}
    </div>`;
  $('#metrics').innerHTML =
    card('Spot', fmtMoney(d.spot), d.ticker + ' · ' + d.as_of) +
    card('Total acciones', Number(d.total_shares).toLocaleString('en-US'), 'todas las zonas') +
    card('Notional neto', fmtMoney(d.total_notional), 'calls + / puts −') +
    card('Net GEX', gexVal, gexRegime, d.has_gex ? (d.total_gex >= 0 ? 'text-bull' : 'text-bear') : '');
}

/* ---------- Table ---------- */
function renderTable(d) {
  const head = `
    <thead class="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 text-left">
      <tr>
        ${['Bucket', 'Sesgo', 'Sentimiento', 'Exp', 'Call Wall', 'Put Wall', 'Magneto', 'Magnet (GEX)', 'GEX Wall', 'γ-Flip', 'Net GEX', 'Régimen', '1σ']
          .map((h) => `<th class="px-3 py-2 font-medium whitespace-nowrap">${h}</th>`).join('')}
      </tr>
    </thead>`;
  const rows = d.buckets.map((b) => `
    <tr class="border-t border-slate-100 dark:border-slate-800">
      <td class="px-3 py-2 font-medium whitespace-nowrap">${escapeHtml(b.label)}</td>
      <td class="px-3 py-2">${biasBadge(b.bias)}</td>
      <td class="px-3 py-2 whitespace-nowrap">${escapeHtml(b.sentiment)} (${b.actual_dte}d)</td>
      <td class="px-3 py-2 whitespace-nowrap">${escapeHtml(b.expiration)}</td>
      <td class="px-3 py-2 font-semibold text-bull">${fmtNum(b.call_wall)}</td>
      <td class="px-3 py-2 font-semibold text-bear">${fmtNum(b.put_wall)}</td>
      <td class="px-3 py-2">${fmtNum(b.magneto)}</td>
      <td class="px-3 py-2 font-semibold">${fmtNum(b.blended_magnet)}</td>
      <td class="px-3 py-2">${fmtNum(b.gex_wall)}</td>
      <td class="px-3 py-2">${fmtNum(b.gamma_flip)}</td>
      <td class="px-3 py-2 whitespace-nowrap ${b.has_gex ? (b.total_gex >= 0 ? 'text-bull' : 'text-bear') : ''}">${b.has_gex ? fmtMoney(b.total_gex) : '—'}</td>
      <td class="px-3 py-2 whitespace-nowrap">${regimeText(b)}</td>
      <td class="px-3 py-2">${b.sigma ? '±' + fmtNum(b.sigma) : '—'}</td>
    </tr>`).join('');
  $('#bucketsTable').innerHTML = head + `<tbody>${rows}</tbody>`;
}

/* ---------- Drift classification cards ---------- */
function renderDriftCards(d) {
  const icon = (b) => b.breakout ? '🚀' : (b.total_gex >= 0 && b.has_gex ? '🧲' : (b.magneto_notional > 0 ? '🧲' : '⛔'));
  $('#driftCards').innerHTML = d.buckets.map((b) => {
    const edge = b.bias === 'Bullish' ? 'border-l-bull' : b.bias === 'Bearish' ? 'border-l-bear' : 'border-l-slate-400';
    return `
      <div class="rounded-xl border border-slate-200 dark:border-slate-800 border-l-4 ${edge} bg-slate-50 dark:bg-slate-800/40 p-4">
        <div class="flex items-center justify-between gap-2">
          <div class="font-semibold">${icon(b)} ${escapeHtml(b.label)} <span class="text-slate-400 font-normal">· ${escapeHtml(b.expiration)}</span></div>
          ${biasBadge(b.bias)}
        </div>
        <p class="text-sm text-slate-600 dark:text-slate-300 mt-2">${escapeHtml(b.drift)}</p>
      </div>`;
  }).join('');
}

/* ---------- Interactive candlestick chart ---------- */
function chartColors(theme) {
  const dark = theme === 'dark';
  return {
    bg: dark ? '#0f172a' : '#ffffff',
    text: dark ? '#e2e8f0' : '#334155',
    grid: dark ? '#1e293b' : '#f1f5f9',
    border: dark ? '#334155' : '#cbd5e1',
  };
}
function bucketLines(b, spot, showGex) {
  const magnet = (b.blended_magnet != null) ? b.blended_magnet : b.magneto;
  const L = LightweightCharts.LineStyle;
  const lines = [
    { price: b.call_wall, title: `Call Wall ${b.actual_dte}d`, color: '#16a34a', style: L.Solid, width: 2 },
    { price: b.put_wall, title: `Put Wall ${b.actual_dte}d`, color: '#dc2626', style: L.Solid, width: 2 },
    { price: magnet, title: `Magnet ${b.actual_dte}d`, color: '#6366f1', style: L.Solid, width: 3 },
  ];
  if (b.has_gex && showGex) {
    if (b.gex_wall != null) lines.push({ price: b.gex_wall, title: `GEX Wall ${b.actual_dte}d`, color: '#f59e0b', style: L.LargeDashed, width: 2 });
    if (b.gamma_flip != null) lines.push({ price: b.gamma_flip, title: `γ-Flip ${b.actual_dte}d`, color: '#14b8a6', style: L.Dashed, width: 1 });
  }
  if (b.sigma) {
    [[1, '+1σ'], [-1, '-1σ'], [2, '+2σ'], [-2, '-2σ']].forEach(([k, t]) =>
      lines.push({ price: spot + k * b.sigma, title: t, color: '#94a3b8', style: L.Dotted, width: 1 }));
  }
  return lines;
}
function buildChart(d, theme) {
  const el = $('#candleChart');
  const tg = $('#chartToggles');
  if (window.__chart) { window.__chart.remove(); window.__chart = null; }
  el.innerHTML = '';
  tg.innerHTML = '';
  const c = chartColors(theme);
  const chart = LightweightCharts.createChart(el, {
    layout: { background: { color: c.bg }, textColor: c.text },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.border },
    timeScale: { borderColor: c.border, timeVisible: false },
    autoSize: true,
  });
  window.__chart = chart;
  const series = chart.addCandlestickSeries({
    upColor: '#16a34a', downColor: '#dc2626',
    borderUpColor: '#16a34a', borderDownColor: '#dc2626',
    wickUpColor: '#16a34a', wickDownColor: '#dc2626',
  });
  series.setData(d.bars || []);
  series.createPriceLine({
    price: d.spot, color: theme === 'dark' ? '#f8fafc' : '#111', lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'Spot',
  });

  const active = {};
  function show(i) {
    active[i] = bucketLines(d.buckets[i], d.spot, Settings.get('showGex', true)).map((l) => series.createPriceLine({
      price: l.price, color: l.color, lineWidth: l.width, lineStyle: l.style,
      axisLabelVisible: true, title: l.title,
    }));
  }
  function hide(i) { (active[i] || []).forEach((pl) => series.removePriceLine(pl)); active[i] = null; }
  // Redraw currently-visible buckets in place (keeps zoom/pan) after a GEX toggle.
  window.__chartRedraw = () => {
    Object.keys(active).filter((i) => active[i]).forEach((i) => { hide(Number(i)); show(Number(i)); });
  };

  d.buckets.forEach((b, i) => {
    const regime = b.has_gex ? (b.total_gex >= 0 ? ' · 🟢' : ' · 🔴') : '';
    const id = 'tg' + i;
    const lbl = document.createElement('label');
    lbl.className = 'flex items-center gap-2 cursor-pointer';
    lbl.innerHTML = `<input type="checkbox" id="${id}" ${i === 0 ? 'checked' : ''} class="accent-brand">
      <span>${escapeHtml(b.label)} <span class="text-slate-400">(${b.actual_dte}d)${regime}</span></span>`;
    tg.appendChild(lbl);
    lbl.querySelector('input').addEventListener('change', (e) => e.target.checked ? show(i) : hide(i));
    if (i === 0) show(i);
  });

  chart.timeScale().fitContent();
}

document.addEventListener('DOMContentLoaded', boot);
