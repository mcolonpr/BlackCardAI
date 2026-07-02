"""Assemble a full DriftReport from a chain snapshot."""

from __future__ import annotations

from datetime import date

from . import chain_filter, drift, gex, magneto, stats, walls
from .models import BucketResult, Contract, DriftReport


def build_report(
    ticker: str,
    spot: float,
    contracts: list[Contract],
    as_of: date,
) -> DriftReport:
    """Run the full pipeline and return a DriftReport.

    `contracts` is the raw chain (calls + puts, all expirations). Filtering to
    monthly contracts and bucketing by DTE happens here.
    """
    report = DriftReport(ticker=ticker.upper(), spot=spot, as_of=as_of)

    for sentiment, target_dte, exp in chain_filter.select_buckets(contracts, as_of):
        bucket_contracts = chain_filter.contracts_for_expiration(contracts, exp)
        cw = walls.call_wall(bucket_contracts)
        pw = walls.put_wall(bucket_contracts)
        if cw is None or pw is None:
            continue  # need both sides to classify drift

        notional_map = magneto.net_notional_by_strike(bucket_contracts)
        mag = magneto.magneto(bucket_contracts, notional_map=notional_map)
        if mag is None:
            continue
        mag_strike, mag_notional = mag

        iv = stats.atm_iv(bucket_contracts, spot)
        actual_dte = (exp - as_of).days
        sigma = stats.projected_sigma(spot, iv, actual_dte)

        drift_desc, breakout = drift.classify_drift(
            spot, cw, pw, mag_strike, mag_notional
        )

        # --- GEX (gamma-exposure) blend ---
        # gex_map and notional_map are each computed once and reused by the
        # blend and the gamma flip below, rather than recomputed inside them.
        gex_map = gex.gex_by_strike(bucket_contracts, spot)
        if gex_map:
            gmag_strike = max(gex_map, key=lambda s: abs(gex_map[s]))
            gmag_value = gex_map[gmag_strike]
        else:
            gmag_strike, gmag_value = None, 0.0
        blended = gex.blended_magnet(
            bucket_contracts, spot, notional_map=notional_map, gex_map=gex_map
        )
        blended_strike = blended[0] if blended else mag_strike

        report.buckets.append(
            BucketResult(
                label=f"{sentiment} ~{target_dte} DTE",
                sentiment=sentiment,
                target_dte=target_dte,
                expiration=exp,
                actual_dte=actual_dte,
                call_wall=cw,
                put_wall=pw,
                magneto_strike=mag_strike,
                magneto_notional=mag_notional,
                iv_atm=iv,
                sigma=sigma,
                total_shares=magneto.total_shares(bucket_contracts),
                total_notional=magneto.total_notional(bucket_contracts),
                drift=drift_desc,
                breakout=breakout,
                total_gex=sum(gex_map.values()),
                gamma_flip=gex.gamma_flip(bucket_contracts, spot, gex_map=gex_map),
                gex_magnet_strike=gmag_strike,
                gex_magnet_value=gmag_value,
                blended_magnet_strike=blended_strike,
                has_gex=bool(gex_map),
                gex_by_strike=gex_map,
            )
        )

    return report


def format_text_report(report: DriftReport) -> str:
    """Render the required Section-8 outputs as plain text."""
    lines: list[str] = []
    lines.append(f"=== Drift Sentiment Report: {report.ticker} ===")
    lines.append(f"Spot: {report.spot:.2f}   As of: {report.as_of.isoformat()}")
    lines.append(f"Total shares (all zones): {report.total_shares:,}")
    lines.append(f"Total net notional (all zones): {report.total_notional:,.0f}")
    lines.append("")

    for b in report.buckets:
        lines.append(f"--- {b.label} | exp {b.expiration.isoformat()} ({b.actual_dte} DTE) ---")
        lines.append(f"  Sentiment classification: {b.sentiment} ({b.actual_dte} days)")
        lines.append(f"  Call Wall: {b.call_wall.strike:.2f} (OI {b.call_wall.open_interest:,})")
        lines.append(f"  Put Wall:  {b.put_wall.strike:.2f} (OI {b.put_wall.open_interest:,})")
        lines.append(f"  Magneto:   {b.magneto_strike:.2f} (net notional {b.magneto_notional:,.0f})")
        if b.has_gex:
            regime = "long-gamma / absorption" if b.total_gex >= 0 else "short-gamma / acceleration"
            lines.append(f"  Magnet (GEX blend): {b.blended_magnet_strike:.2f}")
            lines.append(f"  GEX regime: {regime} (net GEX {b.total_gex:,.0f} $/1%)")
            if b.gex_magnet_strike is not None:
                lines.append(f"  GEX wall:  {b.gex_magnet_strike:.2f} (GEX {b.gex_magnet_value:,.0f})")
            if b.gamma_flip is not None:
                lines.append(f"  Gamma flip: {b.gamma_flip:.2f} (zero-gamma pivot)")
        else:
            lines.append(f"  Magnet (GEX blend): {b.blended_magnet_strike:.2f} (no gamma data; notional only)")
        lines.append(f"  Shares in zone: {b.total_shares:,}")
        lines.append(f"  Net notional in zone: {b.total_notional:,.0f}")
        if b.sigma is not None:
            lines.append(f"  IV(atm): {b.iv_atm:.4f}   1-sigma move: +/-{b.sigma:.2f}")
        else:
            lines.append("  IV(atm): n/a")
        lines.append(f"  Drift: {b.drift}")
        lines.append(f"  Note: {drift.drift_correlation_note(b.magneto_notional, b.breakout)}")
        lines.append("")

    return "\n".join(lines)
