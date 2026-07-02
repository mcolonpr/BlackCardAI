"""Projected-price panels: one annotated ±sigma distribution per DTE bucket.

Each bucket renders the projected price distribution (a ±1σ box with ±3σ
whiskers, median at spot) plus the key levels — Call/Put walls, the GEX-blend
magnet, GEX wall and γ-flip. Instead of a legend, every level is called out with
a colored value label connected by a leader line to its exact price, so values
read at a glance. Labels never overlap (they are spread vertically while keeping
price order), and Put (red) always sits below Call (green).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend; safe for servers
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .models import BucketResult

# Level colors (chosen so white label text stays legible on each swatch).
_CALL = "#16a34a"    # green  — Call Wall
_PUT = "#dc2626"     # red    — Put Wall
_MAGNET = "#9333ea"  # purple — Imán (GEX blend)
_GEXW = "#d97706"    # amber  — GEX Wall
_FLIP = "#0d9488"    # teal   — γ-Flip
_SPOT = "#334155"    # slate  — Spot


def _levels(b: BucketResult, spot: float) -> list[tuple[float, str, str, int]]:
    """(price, label, color, rank) for a bucket; rank breaks ties bottom->top.

    Rank keeps Put (red) below and Call (green) above when levels share a strike.
    """
    magnet = b.blended_magnet_strike if b.blended_magnet_strike is not None else b.magneto_strike
    # γ-Flip / GEX wall only appear when gamma data is present.
    out: list[tuple[float, str, str, int]] = []
    out.append((b.put_wall.strike, f"Put Wall  {b.put_wall.strike:.1f}", _PUT, 0))
    if b.has_gex and b.gamma_flip is not None:
        out.append((b.gamma_flip, f"γ-Flip  {b.gamma_flip:.1f}", _FLIP, 1))
    out.append((magnet, f"Imán (GEX)  {magnet:.1f}", _MAGNET, 2))
    out.append((spot, f"Spot  {spot:.1f}", _SPOT, 3))
    if b.has_gex and b.gex_magnet_strike is not None:
        out.append((b.gex_magnet_strike, f"GEX Wall  {b.gex_magnet_strike:.1f}", _GEXW, 4))
    out.append((b.call_wall.strike, f"Call Wall  {b.call_wall.strike:.1f}", _CALL, 5))
    return out


def _spread(targets: list[float], sep: float, lo: float, hi: float) -> list[float]:
    """Vertical label positions: order-preserving, min gap `sep`, within [lo, hi].

    `targets` must already be sorted ascending. Labels start at their true price
    and are nudged apart only as needed, so they stay near their value.
    """
    n = len(targets)
    if n == 0:
        return []
    if n > 1 and sep * (n - 1) > (hi - lo):
        sep = (hi - lo) / (n - 1)
    pos = list(targets)
    for i in range(1, n):                         # push overlapping labels up
        if pos[i] < pos[i - 1] + sep:
            pos[i] = pos[i - 1] + sep
    if pos[-1] > hi:                              # overflow top -> pull cluster down
        pos[-1] = hi
        for i in range(n - 2, -1, -1):
            if pos[i] > pos[i + 1] - sep:
                pos[i] = pos[i + 1] - sep
    if pos[0] < lo:                              # clamp bottom, re-push up
        pos[0] = lo
        for i in range(1, n):
            if pos[i] < pos[i - 1] + sep:
                pos[i] = pos[i - 1] + sep
    return pos


def _draw_bucket(ax, b: BucketResult, spot: float, fg: str, spot_line: str) -> None:
    """Render one bucket's projected distribution and labeled levels."""
    s = b.sigma
    lo3, hi3 = spot - 3 * s, spot + 3 * s
    box_l, box_r, cx = 0.55, 1.55, 1.05
    tip_x, label_x = box_r + 0.05, 2.0

    items = sorted(_levels(b, spot), key=lambda it: (it[0], it[3]))
    prices = [p for p, *_ in items]
    ymin, ymax = min([lo3] + prices), max([hi3] + prices)
    span = (ymax - ymin) or 1.0
    pad = span * 0.09
    ymin, ymax = ymin - pad, ymax + pad
    ax.set_xlim(0, 3.4)
    ax.set_ylim(ymin, ymax)

    # --- projected distribution: ±2σ band, ±1σ box, ±3σ whisker, median=spot ---
    ax.add_patch(Rectangle((box_l, spot - 2 * s), box_r - box_l, 4 * s,
                           facecolor="#3b82f6", alpha=0.10, edgecolor="none", zorder=1))
    ax.add_patch(Rectangle((box_l, spot - s), box_r - box_l, 2 * s,
                           facecolor="#3b82f6", alpha=0.22, edgecolor="#3b82f6",
                           lw=1.4, zorder=2))
    ax.plot([cx, cx], [lo3, hi3], color=fg, lw=1.2, zorder=2)
    for y in (lo3, hi3):
        ax.plot([cx - 0.07, cx + 0.07], [y, y], color=fg, lw=1.2, zorder=2)
    ax.plot([box_l, box_r], [spot, spot], color=spot_line, lw=2.2, zorder=3)

    # σ ticks on the LEFT of the box (never collide with right-side labels).
    for mult, tag in ((3, "+3σ"), (1, "+1σ"), (-1, "−1σ"), (-3, "−3σ")):
        ax.text(box_l - 0.06, spot + mult * s, tag, ha="right", va="center",
                fontsize=7, color=fg, alpha=0.6)

    # --- level markers + leader-line value labels (legend replacement) ---
    sep = span * 0.082
    positions = _spread(prices, sep, ymin + span * 0.02, ymax - span * 0.02)
    for (price, text, color, _rank), ly in zip(items, positions):
        ax.plot([box_l, box_r], [price, price], color=color, lw=1.8, alpha=0.95, zorder=3)
        ax.annotate(
            text,
            xy=(tip_x, price), xycoords="data",
            xytext=(label_x, ly), textcoords="data",
            va="center", ha="left", fontsize=9, fontweight="bold", color="#ffffff",
            bbox=dict(boxstyle="round,pad=0.3", fc=color, ec="none", alpha=0.96),
            arrowprops=dict(arrowstyle="-", color=color, lw=1.1, shrinkA=0, shrinkB=2),
            annotation_clip=False, zorder=5,
        )

    regime = ""
    if b.has_gex:
        regime = "   ·  +GEX absorción" if b.total_gex >= 0 else "   ·  −GEX aceleración"
    ax.set_title(f"{b.label} · exp {b.expiration.isoformat()} ({b.actual_dte}d){regime}",
                 color=fg, fontsize=11, fontweight="bold")
    ax.set_ylabel("Precio", color=fg, fontsize=9)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=fg, labelsize=8)


def build_box_plots(buckets: list[BucketResult], spot: float, theme: str = "light"):
    """Return a matplotlib Figure with one annotated projection panel per bucket.

    Each panel shows the ±σ projected price distribution with every key level
    called out by a colored value label and leader line (no legend). `theme`
    ("light"/"dark") controls the background/foreground to match the app.
    """
    dark = theme == "dark"
    bg = "#0f172a" if dark else "#ffffff"
    fg = "#e2e8f0" if dark else "#334155"
    grid = "#334155" if dark else "#e5e7eb"
    spot_line = "#f8fafc" if dark else "#0f172a"

    n = len(buckets)
    cols = 2
    rows = max(1, (n + cols - 1) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(12, 5.0 * rows))
    fig.patch.set_facecolor(bg)
    axes = axes.flatten() if n > 1 else [axes]

    for ax, b in zip(axes, buckets):
        ax.set_facecolor(bg)
        if b.sigma is None:
            ax.text(0.5, 0.5, f"{b.label}\n(sin datos de IV)", ha="center", va="center",
                    color=fg, fontsize=11)
            ax.set_axis_off()
            continue
        _draw_bucket(ax, b, spot, fg, spot_line)
        for spine in ax.spines.values():
            spine.set_color(grid)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    for ax in axes[len(buckets):]:
        ax.set_axis_off()

    fig.suptitle("Distribución de precio proyectada (±σ) con niveles clave",
                 fontsize=14, fontweight="bold", color=fg)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig
