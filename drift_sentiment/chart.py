"""TradingView Lightweight-Charts HTML with toggleable per-bucket overlays."""

from __future__ import annotations

import json

from .models import BucketResult

# A distinct color per bucket, in the canonical 320/120/90/30 order.
_BUCKET_COLORS = ["#2962FF", "#00897B", "#F57C00", "#AD1457"]


def _bucket_levels(b: BucketResult, spot: float, color: str) -> dict:
    """Build the overlay payload (price lines) for one bucket."""
    magnet = b.blended_magnet_strike if b.blended_magnet_strike is not None else b.magneto_strike
    lines = [
        {"price": b.call_wall.strike, "title": "Call Wall", "style": "solid"},
        {"price": b.put_wall.strike, "title": "Put Wall", "style": "solid"},
        # Blended notional+GEX magnet — the headline magnet (drawn thick).
        {"price": magnet, "title": "Magnet", "style": "solid", "width": 3},
    ]
    if b.has_gex:
        if b.gex_magnet_strike is not None:
            lines.append(
                {"price": b.gex_magnet_strike, "title": "GEX Wall", "style": "largedashed"}
            )
        if b.gamma_flip is not None:
            lines.append(
                {"price": b.gamma_flip, "title": "γ-Flip", "style": "dashed"}
            )
    if b.sigma:
        lines += [
            {"price": spot + b.sigma, "title": "+1σ", "style": "dotted"},
            {"price": spot - b.sigma, "title": "-1σ", "style": "dotted"},
            {"price": spot + 2 * b.sigma, "title": "+2σ", "style": "dotted"},
            {"price": spot - 2 * b.sigma, "title": "-2σ", "style": "dotted"},
        ]
    label = f"{b.label} (exp {b.expiration.isoformat()}, {b.actual_dte}d)"
    if b.has_gex:
        label += "  ·  " + ("+GEX absorb" if b.total_gex >= 0 else "−GEX accel")
    return {"label": label, "color": color, "lines": lines}


def build_chart_html(
    bars: list[dict], buckets: list[BucketResult], spot: float, ticker: str
) -> str:
    """Return self-contained HTML for an interactive candlestick chart.

    Each bucket's Call/Put Wall, Magneto, and ±σ projection levels render as
    labeled price lines, toggled by a checkbox per bucket (handled in JS so the
    chart keeps its zoom/pan state).
    """
    payload = {
        "bars": bars,
        "spot": spot,
        "ticker": ticker,
        "buckets": [
            _bucket_levels(b, spot, _BUCKET_COLORS[i % len(_BUCKET_COLORS)])
            for i, b in enumerate(buckets)
        ],
    }
    data_json = json.dumps(payload)

    return """
<div id="wrap" style="font-family: system-ui, sans-serif;">
  <div id="toggles" style="display:flex;flex-wrap:wrap;gap:14px;margin:4px 0 10px;"></div>
  <div id="chart" style="height:460px;width:100%;"></div>
  <div style="font-size:11px;color:#888;margin-top:6px;">
    Solid = Walls &amp; Magnet (GEX blend) · Large-dash = GEX Wall · Dashed = γ-Flip · Dotted = ±σ. Toggle buckets above.
  </div>
</div>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
const DATA = __DATA__;

const chart = LightweightCharts.createChart(document.getElementById('chart'), {
  layout: { background: { color: '#ffffff' }, textColor: '#333' },
  grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
  rightPriceScale: { borderColor: '#ccc' },
  timeScale: { borderColor: '#ccc', timeVisible: false },
  autoSize: true,
});

const series = chart.addCandlestickSeries({
  upColor: '#26a69a', downColor: '#ef5350',
  borderUpColor: '#26a69a', borderDownColor: '#ef5350',
  wickUpColor: '#26a69a', wickDownColor: '#ef5350',
});
series.setData(DATA.bars);

// Spot reference line (always on).
series.createPriceLine({
  price: DATA.spot, color: '#000', lineWidth: 1,
  lineStyle: LightweightCharts.LineStyle.Solid,
  axisLabelVisible: true, title: 'Spot',
});

const STYLE = {
  solid: LightweightCharts.LineStyle.Solid,
  dashed: LightweightCharts.LineStyle.Dashed,
  dotted: LightweightCharts.LineStyle.Dotted,
  largedashed: LightweightCharts.LineStyle.LargeDashed,
  sparsedotted: LightweightCharts.LineStyle.SparseDotted,
};

// Track created price-line objects per bucket so we can remove them on toggle.
const active = {};

function showBucket(i) {
  const b = DATA.buckets[i];
  active[i] = b.lines.map(l => series.createPriceLine({
    price: l.price,
    color: b.color,
    lineWidth: l.width || (l.style === 'solid' ? 2 : 1),
    lineStyle: STYLE[l.style],
    axisLabelVisible: true,
    title: l.title,
  }));
}
function hideBucket(i) {
  (active[i] || []).forEach(pl => series.removePriceLine(pl));
  active[i] = null;
}

// Build a checkbox per bucket. First bucket starts enabled.
const togglesEl = document.getElementById('toggles');
DATA.buckets.forEach((b, i) => {
  const lbl = document.createElement('label');
  lbl.style.cssText = 'display:flex;align-items:center;gap:5px;font-size:13px;cursor:pointer;';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = (i === 0);
  cb.addEventListener('change', () => cb.checked ? showBucket(i) : hideBucket(i));
  const swatch = document.createElement('span');
  swatch.style.cssText = 'width:12px;height:12px;border-radius:2px;background:' + b.color + ';display:inline-block;';
  lbl.appendChild(cb);
  lbl.appendChild(swatch);
  lbl.appendChild(document.createTextNode(b.label));
  togglesEl.appendChild(lbl);
  if (cb.checked) showBucket(i);
});

chart.timeScale().fitContent();
</script>
""".replace("__DATA__", data_json)
