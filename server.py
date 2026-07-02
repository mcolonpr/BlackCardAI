"""Flask server for the "Trump Is The Best" trading-analysis platform.

Serves the Tailwind UI (multipage, connected by the nav/sidebar links) and a
small JSON API backed by the drift_sentiment engine (Drift Sentiment + GEX).
Runs on port 8502.

Adding a new page later is intentionally trivial: drop a template in
`templates/`, add a `@app.route`, and add one link in the sidebar of
`templates/base.html`.
"""

from __future__ import annotations

import io
import time

import matplotlib.pyplot as plt
from flask import Flask, abort, jsonify, render_template, request, send_file

from drift_sentiment import polygon_client, tickers
from drift_sentiment.plotting import build_box_plots
from drift_sentiment.polygon_client import PolygonError
from drift_sentiment.report import build_report, format_text_report

app = Flask(__name__)

_CACHE_TTL = 300  # seconds; mirrors the original app's 5-minute data cache
_report_cache: dict[str, tuple[float, object, list]] = {}  # ticker -> (ts, report, bars)


def _get_report(ticker: str):
    """Return (report, bars) for a ticker, using a short-lived cache."""
    tk = ticker.strip().upper()
    now = time.time()
    hit = _report_cache.get(tk)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1], hit[2]
    spot, contracts = polygon_client.fetch_chain(tk)
    report = build_report(tk, spot, contracts, polygon_client.today())
    try:
        bars = polygon_client.fetch_daily_bars(tk)
    except PolygonError:
        bars = []
    _report_cache[tk] = (now, report, bars)
    return report, bars


def _bias(b, spot: float) -> str:
    """Directional bias for a bucket: Bullish (green) / Bearish (red) / Neutral."""
    magnet = b.blended_magnet_strike if b.blended_magnet_strike is not None else b.magneto_strike
    if b.breakout:
        return "Bullish" if spot > b.call_wall.strike else "Bearish"
    if magnet is None:
        return "Neutral"
    if magnet > spot * 1.002:
        return "Bullish"
    if magnet < spot * 0.998:
        return "Bearish"
    return "Neutral"


def _bucket_dict(b, spot: float) -> dict:
    return {
        "label": b.label,
        "sentiment": b.sentiment,
        "target_dte": b.target_dte,
        "actual_dte": b.actual_dte,
        "expiration": b.expiration.isoformat(),
        "call_wall": b.call_wall.strike,
        "call_wall_oi": b.call_wall.open_interest,
        "put_wall": b.put_wall.strike,
        "put_wall_oi": b.put_wall.open_interest,
        "magneto": b.magneto_strike,
        "magneto_notional": b.magneto_notional,
        "blended_magnet": b.blended_magnet_strike,
        "gex_wall": b.gex_magnet_strike,
        "gamma_flip": b.gamma_flip,
        "total_gex": b.total_gex,
        "has_gex": b.has_gex,
        "sigma": b.sigma,
        "total_shares": b.total_shares,
        "total_notional": b.total_notional,
        "drift": b.drift,
        "breakout": b.breakout,
        "bias": _bias(b, spot),
    }


@app.route("/")
def home():
    return render_template("index.html", active="home")


@app.route("/drift")
def drift_page():
    return render_template("drift.html", active="drift")


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    try:
        return jsonify({"results": tickers.search_tickers(q, limit=8)})
    except Exception as e:  # noqa: BLE001 - never break the type-ahead
        return jsonify({"results": [], "error": str(e)})


@app.route("/api/analyze")
def api_analyze():
    ticker = request.args.get("ticker", "").strip()
    if not ticker:
        return jsonify({"error": "No ticker provided."}), 400
    try:
        report, bars = _get_report(ticker)
    except PolygonError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    spot = report.spot
    return jsonify(
        {
            "ticker": report.ticker,
            "spot": spot,
            "as_of": report.as_of.isoformat(),
            "total_shares": report.total_shares,
            "total_notional": report.total_notional,
            "total_gex": report.total_gex,
            "has_gex": report.has_gex,
            "buckets": [_bucket_dict(b, spot) for b in report.buckets],
            "bars": bars,
            "text_report": format_text_report(report),
        }
    )


@app.route("/api/boxplot")
def api_boxplot():
    ticker = request.args.get("ticker", "").strip().upper()
    theme = "dark" if request.args.get("theme") == "dark" else "light"
    hit = _report_cache.get(ticker)
    if not hit:
        try:
            _get_report(ticker)
            hit = _report_cache.get(ticker)
        except Exception:  # noqa: BLE001
            abort(404)
    report = hit[1]
    if not getattr(report, "buckets", None):
        abort(404)
    fig = build_box_plots(report.buckets, report.spot, theme=theme)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8502, debug=False)
