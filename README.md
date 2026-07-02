# Trump Is The Best

A web platform for stock/ETF **option-flow analysis**: Put/Call Walls, a GEX-blended
**Magnet**, **Gamma Flip**, and IV-based price-drift projections — with an interactive
candlestick chart, a personalized greeting, light/dark mode, adjustable font size, and
a ticker autocomplete. Built with **Flask + TailwindCSS**; market data from **Massive**.

Green = **calls / bullish bias**, red = **puts / bearish bias**.

---

## ▶️ Start it (easiest way)

**Double-click `start-app.command`** in this folder. The first run sets everything up
(1–2 min); after that it just opens. Your browser opens at **http://127.0.0.1:8502**.

To close the app, close the Terminal window that opened.

### Run it manually instead

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

Then open **http://127.0.0.1:8502**.

### API key

The Massive API key lives in a `.env` file in this folder (`MASSIVE_API_KEY=...`),
which is already set up and is never committed. To change it, edit that one line.

---

## What it shows

- **Header metrics:** spot, total shares, total net notional.
- **Sentiment buckets table:** the 4 DTE buckets (320/120/90/30) with Call Wall,
  Put Wall, Magneto, notional, shares, and the 1σ projected move.
- **Interactive price chart:** real candlesticks with toggleable per-bucket
  overlays — Call/Put Walls, the GEX-blended Magnet, GEX Wall, γ-Flip, and
  ±1σ/±2σ projection lines. Toggle any combination of buckets to compare
  short-term vs long-term targets.
- **GEX blend (gamma exposure):** each bucket also shows a GEX-weighted
  **Magnet**, the **GEX Wall** (peak dealer gamma), the **γ-Flip** (zero-gamma
  pivot), and a **regime** flag (🟢 absorption vs 🔴 acceleration). Blending
  gamma in keeps the magnet meaningful for names where IV alone shows no
  absorption.
- **Drift classification:** support / rejection / breakout reasoning per bucket.
- **4 box plots:** projected price distribution per DTE bucket (GEX levels drawn).

## How the analysis works

| Concept | Rule |
|---|---|
| **Monthly only** | Expiration on the 3rd Friday of the month; weeklies excluded. |
| **DTE buckets** | Long ~320 & ~120 days, Short ~90 & ~30 days (nearest monthly used). |
| **Call/Put Wall** | Strike with the most open interest, per side, per expiration. |
| **Notional** | `shares × strike`, positive for calls, negative for puts. |
| **Magneto** | Strike with the largest accumulated net notional (the magnet level). |
| **GEX** | Dealer gamma per strike: `gamma × OI × 100 × spot² × 0.01`, calls +, puts −. Net >0 = absorption/pinning, <0 = acceleration. |
| **Magnet (GEX blend)** | Normalized notional and GEX combined into one clearer magnet; falls back to notional when a chain has no gamma. |
| **γ-Flip** | Zero-gamma pivot: the price where cumulative GEX crosses zero. |
| **Projection** | `σ = spot × IV_atm × √(DTE/365)` → ±1σ/±2σ price bands. |

## Project layout

```
start-app.command          # double-click launcher (macOS), port 8502
server.py                  # Flask app: pages + JSON API (/api/search, /api/analyze, /api/boxplot)
templates/                 # Tailwind HTML (base.html nav/sidebar/theme, index.html, drift.html)
static/app.js              # cookies/settings standard, theme, font size, autocomplete, charts
drift_sentiment/
  polygon_client.py        # fetches chain + daily candles from Massive (only network module)
  tickers.py               # ticker search for the autocomplete (symbol first, then name)
  chain_filter.py          # monthly detection + DTE bucketing
  walls.py                 # Call/Put walls
  magneto.py               # shares, notional, magneto
  gex.py                   # gamma exposure: GEX wall, γ-flip, blended magnet
  drift.py                 # drift classification
  stats.py                 # IV std-dev projection
  plotting.py              # box plots (theme-aware)
  report.py                # assembles the report
tests/                     # offline unit tests (no API needed)
```

## Adding a new page later

1. Add a template in `templates/` (extend `base.html`).
2. Add a `@app.route` in `server.py` that renders it.
3. Add one link to the sidebar list in `templates/base.html`.

All pages share the nav/sidebar, theme, font size, and cookie settings automatically.

## Run the tests

```bash
.venv/bin/python -m pytest tests/ -q
```

## Disclaimer

Educational tool for learning options-flow analysis. **Not financial advice.**
Market data is provided by Massive subject to their terms and your plan's
limits (rate limits and any data delay depend on your plan).
