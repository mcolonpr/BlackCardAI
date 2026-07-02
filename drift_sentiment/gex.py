"""Gamma Exposure (GEX) blend: dealer-gamma levels and a clearer magnet.

The notional-only Magneto can read flat or noisy for names where implied
volatility is not producing clear absorption. Weighting each strike by dealer
gamma exposure (GEX) surfaces where hedging flows actually pin or repel price,
so the "magnet" reads more clearly. Blending the two signals gives one headline
magnet that stays meaningful across very different tickers.

All GEX figures are dollar gamma per 1% underlying move, using the common
convention that dealers are long call gamma and short put gamma (calls +,
puts -). A positive net GEX is a long-gamma / absorption (pinning) regime; a
negative net GEX is a short-gamma / acceleration regime.
"""

from __future__ import annotations

from collections import defaultdict

from .magneto import net_notional_by_strike
from .models import Contract

CONTRACT_MULTIPLIER = 100   # shares represented by one option contract
GEX_BLEND_WEIGHT = 0.6      # weight on the GEX signal in the blend, in [0, 1]


def _dollar_gamma(gamma: float, open_interest: int, spot: float) -> float:
    """Dollar gamma per 1% move for one side's contracts at a strike."""
    return gamma * open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01


def gex_by_strike(contracts: list[Contract], spot: float) -> dict[float, float]:
    """Net dealer GEX per strike (calls +, puts -).

    Contracts missing a gamma are skipped, so a chain with no greeks yields an
    empty map and callers fall back to the notional-only signal.
    """
    acc: dict[float, float] = defaultdict(float)
    if spot <= 0:
        return {}
    for c in contracts:
        if c.gamma is None:
            continue
        dg = _dollar_gamma(c.gamma, c.open_interest, spot)
        acc[c.strike] += dg if c.is_call else -dg
    return dict(acc)


def total_gex(contracts: list[Contract], spot: float) -> float:
    """Net GEX across all strikes.

    >0 = long-gamma (absorption / pinning); <0 = short-gamma (moves amplify).
    """
    return sum(gex_by_strike(contracts, spot).values())


def gex_magnet(contracts: list[Contract], spot: float) -> tuple[float, float] | None:
    """Strike carrying the largest |GEX| — the dominant gamma wall.

    Returns (strike, signed_gex) or None when no gamma data is present.
    """
    acc = gex_by_strike(contracts, spot)
    if not acc:
        return None
    strike = max(acc, key=lambda s: abs(acc[s]))
    return strike, acc[strike]


def gamma_flip(contracts: list[Contract], spot: float) -> float | None:
    """Approx zero-gamma pivot: the strike where cumulative GEX crosses zero.

    Walks strikes low->high accumulating GEX and linearly interpolates every
    price where the running total changes sign, then returns the crossing
    nearest spot (real chains have noisy far-tail crossings; the meaningful
    flip is the one by the money). Returns None if it never flips.
    """
    acc = gex_by_strike(contracts, spot)
    if not acc:
        return None
    prev_strike: float | None = None
    prev_cum = 0.0
    cum = 0.0
    crossings: list[float] = []
    for s in sorted(acc):
        cum += acc[s]
        crossed = prev_strike is not None and (prev_cum < 0) != (cum < 0)
        if crossed and cum != prev_cum:
            frac = -prev_cum / (cum - prev_cum)
            crossings.append(prev_strike + frac * (s - prev_strike))
        prev_strike, prev_cum = s, cum
    if not crossings:
        return None
    return min(crossings, key=lambda x: abs(x - spot))


def _normalized_abs(d: dict[float, float]) -> dict[float, float]:
    """Scale a strike->value map to [0, 1] by its largest magnitude."""
    if not d:
        return {}
    top = max(abs(v) for v in d.values())
    if top == 0:
        return {k: 0.0 for k in d}
    return {k: abs(v) / top for k, v in d.items()}


def blended_magnet(
    contracts: list[Contract], spot: float, *, gex_weight: float = GEX_BLEND_WEIGHT
) -> tuple[float, float, bool] | None:
    """Blend the notional magnet with the GEX magnet into one clearer level.

    Each signal is normalised to [0, 1] by its own peak, then combined as
    ``(1 - w) * notional + w * gex``. When no gamma data is present the GEX
    weight collapses to 0, so the blend degrades gracefully to notional-only and
    every ticker still yields a magnet.

    Returns (strike, score, has_gex) or None if there is no data at all.
    """
    notional = net_notional_by_strike(contracts)
    gex = gex_by_strike(contracts, spot)
    if not notional and not gex:
        return None
    has_gex = bool(gex)
    w = gex_weight if has_gex else 0.0
    n_norm = _normalized_abs(notional)
    g_norm = _normalized_abs(gex)
    strikes = set(n_norm) | set(g_norm)
    scores = {
        s: (1.0 - w) * n_norm.get(s, 0.0) + w * g_norm.get(s, 0.0) for s in strikes
    }
    strike = max(scores, key=lambda s: scores[s])
    return strike, scores[strike], has_gex
