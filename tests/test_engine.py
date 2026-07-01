"""Offline unit tests for the drift-sentiment engine (no network)."""

from __future__ import annotations

from datetime import date

import pytest

from drift_sentiment import chain_filter, drift, gex, magneto, stats, walls
from drift_sentiment.models import Contract, Wall
from drift_sentiment.report import build_report


# --- monthly detection -------------------------------------------------------

def test_third_friday_is_monthly():
    # 2026-01-16 is the third Friday of Jan 2026.
    assert chain_filter.is_monthly_expiration(date(2026, 1, 16))


def test_non_third_friday_is_not_monthly():
    assert not chain_filter.is_monthly_expiration(date(2026, 1, 9))   # 2nd Friday
    assert not chain_filter.is_monthly_expiration(date(2026, 1, 23))  # 4th Friday
    assert not chain_filter.is_monthly_expiration(date(2026, 1, 14))  # Wednesday


# --- nearest expiration ------------------------------------------------------

def test_nearest_expiration_picks_closest_dte():
    as_of = date(2026, 1, 1)
    exps = [date(2026, 1, 16), date(2026, 4, 17), date(2026, 11, 20)]
    # target 120 -> closest is 2026-04-17 (~106 days)
    assert chain_filter.nearest_expiration(exps, 120, as_of) == date(2026, 4, 17)


def test_nearest_expiration_ignores_past():
    as_of = date(2026, 6, 1)
    exps = [date(2026, 1, 16), date(2026, 7, 17)]
    assert chain_filter.nearest_expiration(exps, 30, as_of) == date(2026, 7, 17)


# --- walls -------------------------------------------------------------------

def _c(strike, ctype, oi, exp=date(2026, 1, 16), iv=0.3):
    return Contract(strike, exp, ctype, oi, iv)


def _cg(strike, ctype, oi, gamma, exp=date(2026, 1, 16), iv=0.3):
    """Contract with a gamma, for GEX tests."""
    return Contract(strike, exp, ctype, oi, iv, gamma)


def test_call_and_put_walls():
    cs = [
        _c(100, "call", 50), _c(110, "call", 200), _c(120, "call", 30),
        _c(90, "put", 80), _c(95, "put", 300), _c(85, "put", 20),
    ]
    assert walls.call_wall(cs) == Wall(110, 200)
    assert walls.put_wall(cs) == Wall(95, 300)


# --- notional sign + magneto -------------------------------------------------

def test_call_notional_positive_put_negative():
    assert _c(100, "call", 10).notional == 100_000   # 10*100*100
    assert _c(100, "put", 10).notional == -100_000


def test_magneto_picks_largest_abs_net_notional():
    cs = [
        _c(100, "call", 10),   # +100k
        _c(100, "put", 5),     # -50k  -> net +50k at 100
        _c(120, "put", 40),    # -480k at 120  (largest magnitude)
        _c(120, "call", 1),    # +12k  -> net -468k at 120
    ]
    strike, net = magneto.magneto(cs)
    assert strike == 120
    assert net == pytest.approx(-468_000)


# --- GEX (gamma exposure) blend ----------------------------------------------

def test_contract_gamma_defaults_none():
    assert _c(100, "call", 10).gamma is None


def test_gex_sign_calls_positive_puts_negative():
    spot = 100.0
    gc = gex.gex_by_strike([_cg(100, "call", 10, 0.05)], spot)[100]
    gp = gex.gex_by_strike([_cg(100, "put", 10, 0.05)], spot)[100]
    assert gc > 0 and gp < 0
    assert gc == pytest.approx(-gp)


def test_gex_skips_contracts_without_gamma():
    # A chain with no greeks yields an empty GEX map (fall back to notional).
    assert gex.gex_by_strike([_c(100, "call", 10)], 100.0) == {}


def test_gex_magnet_picks_peak_abs():
    spot = 100.0
    cs = [_cg(100, "call", 10, 0.02), _cg(120, "call", 5, 0.20)]
    strike, _ = gex.gex_magnet(cs, spot)
    assert strike == 120


def test_gamma_flip_between_puts_and_calls():
    spot = 100.0
    # Puts pull GEX negative low, calls push it positive higher -> flip between.
    cs = [_cg(90, "put", 100, 0.05), _cg(110, "call", 200, 0.05)]
    flip = gex.gamma_flip(cs, spot)
    assert flip is not None
    assert 90 <= flip <= 110


def test_blended_magnet_falls_back_to_notional_without_gamma():
    cs = [_c(100, "call", 10), _c(120, "put", 40)]
    result = gex.blended_magnet(cs, 100.0)
    assert result is not None
    strike, _score, has_gex = result
    assert has_gex is False
    assert strike == magneto.magneto(cs)[0]


def test_blended_magnet_uses_gex_when_present():
    spot = 100.0
    # Notional peaks at 120 (big put), but gamma is concentrated at 105.
    cs = [
        _c(120, "put", 400),               # dominant notional, no gamma
        _cg(105, "call", 50, 0.30),        # dominant gamma
        _cg(105, "put", 10, 0.30),
    ]
    strike, _score, has_gex = gex.blended_magnet(cs, spot)
    assert has_gex is True
    assert strike == 105


# --- std-dev projection ------------------------------------------------------

def test_projected_sigma():
    # spot 100, IV 0.20, 365 DTE -> sigma = 100*0.2*sqrt(1) = 20
    assert stats.projected_sigma(100, 0.20, 365) == pytest.approx(20.0)


def test_projected_sigma_none_without_iv():
    assert stats.projected_sigma(100, None, 30) is None


# --- drift classification ----------------------------------------------------

def test_intra_range_positive_magneto_is_attraction():
    desc, breakout = drift.classify_drift(
        spot=100, call_wall=Wall(110, 1), put_wall=Wall(90, 1),
        magneto_strike=105, magneto_notional=500_000,
    )
    assert not breakout
    assert "ATTRACTION" in desc


def test_intra_range_negative_magneto_is_rejection():
    desc, breakout = drift.classify_drift(
        spot=100, call_wall=Wall(110, 1), put_wall=Wall(90, 1),
        magneto_strike=95, magneto_notional=-500_000,
    )
    assert not breakout
    assert "REJECTION" in desc


def test_extra_range_is_breakout():
    desc, breakout = drift.classify_drift(
        spot=130, call_wall=Wall(110, 1), put_wall=Wall(90, 1),
        magneto_strike=105, magneto_notional=500_000,
    )
    assert breakout
    assert "BREAKOUT" in desc and "upside" in desc


# --- end-to-end report (offline synthetic chain) -----------------------------

def test_build_report_end_to_end():
    as_of = date(2026, 1, 1)
    # Two monthly expirations: ~30 DTE and ~320 DTE.
    near = date(2026, 1, 16)   # 15 DTE -> nearest to 30
    far = date(2026, 11, 20)   # 323 DTE -> nearest to 320
    contracts = []
    for exp in (near, far):
        contracts += [
            _c(110, "call", 500, exp), _c(120, "call", 100, exp),
            _c(90, "put", 400, exp), _c(80, "put", 50, exp),
        ]
    report = build_report("TEST", spot=100.0, contracts=contracts, as_of=as_of)
    assert report.ticker == "TEST"
    assert len(report.buckets) >= 2
    for b in report.buckets:
        assert b.call_wall.strike == 110
        assert b.put_wall.strike == 90
        assert b.sigma is not None
        # GEX fields are populated; this chain has no gamma so it degrades cleanly.
        assert b.blended_magnet_strike is not None
        assert b.has_gex is False
