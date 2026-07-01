"""Streamlit UI for the Drift Sentiment Agent."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from drift_sentiment import polygon_client
from drift_sentiment.chart import build_chart_html
from drift_sentiment.plotting import build_box_plots
from drift_sentiment.polygon_client import PolygonError
from drift_sentiment.report import build_report, format_text_report

st.set_page_config(page_title="Drift Sentiment Agent", layout="wide")
st.title("📊 Drift Sentiment Agent")
st.caption(
    "Option-chain analysis: Put/Call Walls, Magneto levels, and price-drift "
    "projection. Monthly contracts only."
)

with st.sidebar:
    st.header("Input")
    ticker = st.text_input("Ticker", value="AAPL").strip().upper()
    run = st.button("Analyze", type="primary")
    st.markdown("---")
    st.caption("API key is read from `.env` (MASSIVE_API_KEY).")


@st.cache_data(ttl=300, show_spinner=False)
def _analyze(tk: str):
    spot, contracts = polygon_client.fetch_chain(tk)
    report = build_report(tk, spot, contracts, polygon_client.today())
    return report


@st.cache_data(ttl=300, show_spinner=False)
def _daily_bars(tk: str):
    return polygon_client.fetch_daily_bars(tk)


if run and ticker:
    try:
        with st.spinner(f"Fetching option chain for {ticker}…"):
            report = _analyze(ticker)
    except PolygonError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001 - surface any unexpected failure
        st.error(f"Unexpected error: {e}")
        st.stop()

    if not report.buckets:
        st.warning(
            "No monthly expirations with both call and put walls were found for "
            f"{ticker}. The chain may be sparse or illiquid."
        )
        st.stop()

    # --- Header metrics (shares + total notional + GEX regime) ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Spot", f"${report.spot:,.2f}")
    c2.metric("Total Shares (all zones)", f"{report.total_shares:,}")
    c3.metric("Total Net Notional", f"${report.total_notional:,.0f}")
    if report.has_gex:
        regime = "🟢 Absorption" if report.total_gex >= 0 else "🔴 Acceleration"
        c4.metric("Net GEX (all zones)", f"${report.total_gex:,.0f}", regime)
    else:
        c4.metric("Net GEX (all zones)", "n/a", "no gamma data")

    # --- Per-bucket summary table (Section 8: shares by zone, classification) ---
    st.subheader("Sentiment buckets")
    rows = []
    for b in report.buckets:
        rows.append(
            {
                "Bucket": b.label,
                "Sentiment": f"{b.sentiment} ({b.actual_dte}d)",
                "Expiration": b.expiration.isoformat(),
                "Call Wall": b.call_wall.strike,
                "Put Wall": b.put_wall.strike,
                "Magneto": b.magneto_strike,
                "Magnet (GEX)": b.blended_magnet_strike,
                "GEX Wall": b.gex_magnet_strike,
                "γ-Flip": round(b.gamma_flip, 2) if b.gamma_flip is not None else None,
                "Net GEX": round(b.total_gex) if b.has_gex else None,
                "Regime": ("Absorb" if b.total_gex >= 0 else "Accel") if b.has_gex else "—",
                "Shares": b.total_shares,
                "Net Notional": round(b.total_notional),
                "1σ Move": round(b.sigma, 2) if b.sigma else None,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "**Magnet (GEX)** blends net notional with dealer gamma exposure so the "
        "magnet stays clear even when IV alone shows no absorption. **Regime:** "
        "🟢 Absorb = net long-gamma (price pins), 🔴 Accel = net short-gamma "
        "(moves amplify). **γ-Flip** is the zero-gamma pivot; **GEX Wall** is the "
        "strike with the strongest dealer gamma."
    )

    # --- Interactive price chart with toggleable bucket overlays ---
    st.subheader("Price chart with projection levels")
    st.caption(
        "Candlesticks from Massive. Toggle each DTE bucket to overlay its "
        "Call/Put Walls, GEX-blended Magnet, GEX Wall, γ-Flip, and ±σ "
        "projection on the price."
    )
    try:
        bars = _daily_bars(ticker)
        if bars:
            html = build_chart_html(bars, report.buckets, report.spot, ticker)
            components.html(html, height=560, scrolling=False)
        else:
            st.info("No daily price history available for this ticker.")
    except PolygonError as e:
        st.warning(f"Could not load price history: {e}")

    # --- Drift classification per bucket ---
    st.subheader("Drift classification")
    for b in report.buckets:
        icon = "🚀" if b.breakout else ("🧲" if b.magneto_notional > 0 else "⛔")
        with st.expander(f"{icon} {b.label} — {b.expiration.isoformat()}"):
            st.write(b.drift)

    # --- 4 box plots (Section 7) ---
    st.subheader("Projected price distribution (4 box plots)")
    fig = build_box_plots(report.buckets, report.spot)
    st.pyplot(fig)

    # --- Raw text report ---
    with st.expander("📄 Full text report"):
        st.code(format_text_report(report), language="text")

elif not ticker:
    st.info("Enter a ticker in the sidebar and click Analyze.")
